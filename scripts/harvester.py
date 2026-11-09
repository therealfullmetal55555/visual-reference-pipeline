#!/usr/bin/env python3
"""
Visual Reference Harvester & Local Archive Engine.

Downloads high-resolution reference images from curated Instagram embeds/sources,
extracts raw CDN URLs, saves files with deterministic naming, and maintains
a structured archive_index.json catalog with visual observations.
"""

import os
import re
import json
import html
import urllib.request
import argparse
from typing import Dict, List, Optional, Tuple


DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)


class ReferenceHarvester:
    def __init__(self, output_dir: str, index_path: str, user_agent: str = DEFAULT_USER_AGENT):
        self.output_dir = os.path.expanduser(output_dir)
        self.index_path = os.path.expanduser(index_path)
        self.user_agent = user_agent
        os.makedirs(self.output_dir, exist_ok=True)
        self.index: List[Dict] = self._load_index()

    def _load_index(self) -> List[Dict]:
        if os.path.exists(self.index_path):
            try:
                with open(self.index_path, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception as e:
                print(f"[!] Warning: Failed to load existing index: {e}")
        return []

    def save_index(self) -> None:
        with open(self.index_path, "w", encoding="utf-8") as f:
            json.dump(self.index, f, ensure_ascii=False, indent=2)
        print(f"[✓] Archive index updated: {self.index_path} ({len(self.index)} entries)")

    def extract_image_url(self, shortcode: str, is_reel: bool = False) -> Optional[str]:
        """Extract original CDN image URL from Instagram embed markup."""
        prefix = "reel" if is_reel else "p"
        embed_url = f"https://www.instagram.com/{prefix}/{shortcode}/embed/captioned/"
        req = urllib.request.Request(embed_url, headers={"User-Agent": self.user_agent})
        try:
            with urllib.request.urlopen(req, timeout=15) as resp:
                markup = resp.read().decode("utf-8", errors="ignore")
        except Exception as e:
            print(f"[!] Network error fetching embed for {shortcode}: {e}")
            return None

        # Primary pattern: standard embedded image tag
        img_match = re.search(r'<img[^>]+class="EmbeddedMediaImage"[^>]+src="([^">]+)"', markup)
        if img_match:
            return html.unescape(img_match.group(1))

        # Secondary fallback: any high-res CDN source in the markup
        cdn_matches = re.findall(r'https://[^"\'\s<>]+cdninstagram\.com/[^"\'\s<>]+', markup)
        if cdn_matches:
            # Pick largest/cleanest candidate (avoiding thumbnail sizes)
            filtered = [url for url in cdn_matches if "150x150" not in url and "320x320" not in url]
            return html.unescape(filtered[0] if filtered else cdn_matches[0])

        return None

    def harvest_item(
        self,
        author: str,
        shortcode: str,
        title: str,
        observation: str,
        tags: List[str],
        category: str = "Исследовать",
        format_type: str = "Пост",
    ) -> bool:
        """Download asset and record metadata in catalog."""
        filename = f"{author}_{shortcode}.jpg"
        filepath = os.path.join(self.output_dir, filename)

        # Check if already cataloged and downloaded
        for entry in self.index:
            if entry.get("canonical_url", "").endswith(shortcode) or entry.get("file") == filename:
                if os.path.exists(filepath):
                    print(f"[-] Skipped (already exists): {filename}")
                    return True

        print(f"[*] Harvesting {author} [{shortcode}]...")
        img_url = self.extract_image_url(shortcode, is_reel=(format_type.lower() == "reel"))
        if not img_url:
            print(f"[!] Could not extract CDN image URL for {shortcode}")
            return False

        # Download binary payload
        try:
            req = urllib.request.Request(img_url, headers={"User-Agent": self.user_agent})
            with urllib.request.urlopen(req, timeout=20) as resp:
                data = resp.read()

            with open(filepath, "wb") as f:
                f.write(data)
            print(f"[✓] Saved ({len(data)} bytes): {filename}")
        except Exception as e:
            print(f"[!] Download failed for {filename}: {e}")
            return False

        # Append to catalog
        record = {
            "title": title,
            "author": author,
            "canonical_url": f"https://www.instagram.com/p/{shortcode}/",
            "file": filename,
            "local_path": f"images/Референсы/{filename}",
            "observation": observation,
            "tags": tags,
            "category": category,
            "format": format_type,
            "review_depth": "Частично просмотрено",
            "download_status": "downloaded",
        }
        self.index.append(record)
        return True


def main():
    parser = argparse.ArgumentParser(description="Visual Reference Harvester")
    parser.add_argument("--output", default="~/Desktop/instagram_archive/images/Референсы")
    parser.add_argument("--index", default="~/Desktop/instagram_archive/archive_index.json")
    args = parser.parse_args()

    harvester = ReferenceHarvester(output_dir=args.output, index_path=args.index)
    print(f"Loaded harvester with {len(harvester.index)} existing index entries.")


if __name__ == "__main__":
    main()
