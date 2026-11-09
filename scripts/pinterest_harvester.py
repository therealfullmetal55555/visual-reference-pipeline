#!/usr/bin/env python3
"""
Pinterest Harvester for Visual Reference Pipeline.

Downloads high-resolution images from Pinterest boards, user profiles, or RSS feeds,
automatically upscaling preview links to high-res (1200x/originals), deduplicating,
and appending structured records to archive_index.json.
"""

import os
import re
import json
import argparse
import urllib.request
import xml.etree.ElementTree as ET
from typing import Dict, List, Optional
from pathlib import Path


DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)


def upscale_pinterest_url(cdn_url: str) -> str:
    """Upscale thumbnail Pinterest CDN URL to 1200px uncompressed variant."""
    return re.sub(r"/(?:236x|474x|736x)/", "/1200x/", cdn_url)


class PinterestHarvester:
    def __init__(self, output_dir: str, index_path: str):
        self.output_dir = Path(output_dir).expanduser().resolve()
        self.index_path = Path(index_path).expanduser().resolve()
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.index = self._load_index()

    def _load_index(self) -> List[Dict]:
        if self.index_path.exists():
            try:
                with self.index_path.open("r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception as e:
                print(f"[!] Warning: failed to load existing index: {e}")
        return []

    def save_index(self) -> None:
        with self.index_path.open("w", encoding="utf-8") as f:
            json.dump(self.index, f, ensure_ascii=False, indent=2)
        print(f"[✓] Archive index updated: {len(self.index)} total records.")

    def download_image(self, cdn_url: str, filename_base: str) -> Optional[Path]:
        """Download image trying 1200x with fallback to original cdn_url."""
        high_res_url = upscale_pinterest_url(cdn_url)
        target = self.output_dir / f"{filename_base}.jpg"

        if target.exists():
            return target

        headers = {
            "User-Agent": DEFAULT_USER_AGENT,
            "Referer": "https://www.pinterest.com/"
        }

        for candidate_url in [high_res_url, cdn_url]:
            try:
                req = urllib.request.Request(candidate_url, headers=headers)
                with urllib.request.urlopen(req, timeout=15) as resp:
                    if resp.status == 200:
                        data = resp.read()
                        with open(target, "wb") as f:
                            f.write(data)
                        return target
            except Exception:
                continue

        return None

    def harvest_pins(self, pin_items: List[Dict], default_author: str = "Pinterest", default_category: str = "Референсы") -> int:
        """Ingest a list of structured pin items into archive and index."""
        existing_urls = {entry.get("canonical_url") for entry in self.index}
        existing_files = {entry.get("file") for entry in self.index}
        added = 0

        for item in pin_items:
            cdn_url = item.get("url") or item.get("highRes") or item.get("src")
            if not cdn_url:
                continue

            hash_id = item.get("hash")
            if not hash_id:
                clean_url = cdn_url.split("?")[0]
                hash_id = clean_url.split("/")[-1].split(".")[0]

            filename_base = f"pinterest_{hash_id}"
            filename = f"{filename_base}.jpg"

            canonical_url = item.get("canonical_url") or f"https://www.pinterest.com/pin/{hash_id}/"

            if canonical_url in existing_urls or filename in existing_files:
                continue

            target = self.download_image(cdn_url, filename_base)
            if not target:
                continue

            record = {
                "title": item.get("title") or "Pinterest Референс",
                "author": item.get("author") or default_author,
                "canonical_url": canonical_url,
                "file": filename,
                "local_path": f"images/Референсы/{filename}",
                "observation": item.get("observation") or "Референс из сохранённых Pinterest",
                "tags": item.get("tags") or ["pinterest", "референс", "сохранённое"],
                "category": item.get("category") or default_category,
                "format": item.get("format") or "Пост",
                "review_depth": item.get("review_depth") or "Частично просмотрено",
                "download_status": "downloaded"
            }
            self.index.append(record)
            existing_urls.add(canonical_url)
            existing_files.add(filename)
            added += 1
            print(f"[+] Downloaded: {filename}")

        if added > 0:
            self.save_index()
        return added

    def harvest_feed(self, rss_url: str, author: str = "Pinterest", category: str = "Исследовать") -> int:
        """Harvest pins from an open Pinterest board RSS feed."""
        headers = {"User-Agent": DEFAULT_USER_AGENT}
        req = urllib.request.Request(rss_url, headers=headers)
        with urllib.request.urlopen(req, timeout=15) as resp:
            content = resp.read()

        root = ET.fromstring(content)
        items = root.findall(".//item")
        pin_items = []

        for item in items:
            link = item.find("link").text if item.find("link") is not None else ""
            desc = item.find("description").text if item.find("description") is not None else ""
            title = item.find("title").text if item.find("title") is not None else ""
            title = title.strip() or "Pinterest Референс"

            img_match = re.search(r'src="([^"]+)"', desc)
            if not img_match:
                continue

            cdn_url = img_match.group(1)
            pin_items.append({
                "url": cdn_url,
                "title": title,
                "author": author,
                "canonical_url": link,
                "category": category,
                "tags": ["pinterest", "референс", "сохранённое"]
            })

        return self.harvest_pins(pin_items, default_author=author, default_category=category)


def main():
    parser = argparse.ArgumentParser(description="Pinterest Harvester for Visual Reference Pipeline")
    parser.add_argument("--rss", help="URL of Pinterest board RSS feed")
    parser.add_argument("--pins-json", help="Path to JSON file containing list of pin objects")
    parser.add_argument("--author", default="millyrock2900 (Pinterest)", help="Default author tag")
    parser.add_argument("--category", default="Референсы", help="Default category")
    parser.add_argument("--output", default="~/Desktop/instagram_archive/images/Референсы")
    parser.add_argument("--index", default="~/Desktop/instagram_archive/archive_index.json")
    args = parser.parse_args()

    harvester = PinterestHarvester(args.output, args.index)

    if args.rss:
        added = harvester.harvest_feed(args.rss, author=args.author, category=args.category)
        print(f"Готово. Добавлено {added} новых пинов из RSS.")
    elif args.pins_json:
        json_path = Path(args.pins_json).expanduser().resolve()
        with open(json_path, "r", encoding="utf-8") as f:
            pins = json.load(f)
        added = harvester.harvest_pins(pins, default_author=args.author, default_category=args.category)
        print(f"Готово. Добавлено {added} новых пинов из JSON.")
    else:
        print("Использование: --rss <url> или --pins-json <path.json>")


if __name__ == "__main__":
    main()
