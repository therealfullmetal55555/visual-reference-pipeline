#!/usr/bin/env python3
"""
Notion Database Synchronizer for Visual References.

Synchronizes local archive_index.json records with Notion database properties,
mapping categories, review depths, observation notes, and media paths.
"""

import os
import json
import argparse
import urllib.request
from typing import Dict, List, Any


NOTION_API_URL = "https://api.notion.com/v1"
NOTION_VERSION = "2022-06-28"


def create_notion_page_payload(database_id: str, item: Dict[str, Any]) -> Dict[str, Any]:
    """Format catalog item into Notion API page structure."""
    return {
        "parent": {"database_id": database_id},
        "properties": {
            "Название": {
                "title": [{"text": {"content": item.get("title", "Без названия")}}]
            },
            "Автор": {
                "rich_text": [{"text": {"content": item.get("author", "")}}]
            },
            "Ссылка": {
                "url": item.get("canonical_url", "")
            },
            "Категория": {
                "select": {"name": item.get("category", "Исследовать")}
            },
            "Формат": {
                "select": {"name": item.get("format", "Пост")}
            },
            "Просмотр": {
                "select": {"name": item.get("review_depth", "Частично просмотрено")}
            },
            "Медиа": {
                "rich_text": [{"text": {"content": f"Скачано: {item.get('local_path', '')}"}}]
            },
            "Наблюдение": {
                "rich_text": [{"text": {"content": item.get("observation", "")}}]
            },
            "Теги": {
                "multi_select": [{"name": tag} for tag in item.get("tags", [])]
            }
        }
    }


def sync_batch(api_key: str, database_id: str, items: List[Dict[str, Any]]) -> None:
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Notion-Version": NOTION_VERSION,
        "Content-Type": "application/json"
    }

    print(f"[*] Starting synchronization of {len(items)} items to Notion...")
    for idx, item in enumerate(items, 1):
        payload = create_notion_page_payload(database_id, item)
        req = urllib.request.Request(
            f"{NOTION_API_URL}/pages",
            data=json.dumps(payload).encode("utf-8"),
            headers=headers,
            method="POST"
        )
        try:
            with urllib.request.urlopen(req, timeout=15) as resp:
                if resp.status in (200, 201):
                    print(f"[{idx}/{len(items)}] [✓] Synced: {item.get('title')}")
        except Exception as e:
            print(f"[{idx}/{len(items)}] [!] Error syncing {item.get('title')}: {e}")


def main():
    parser = argparse.ArgumentParser(description="Sync visual references to Notion database")
    parser.add_argument("--index", default="archive_index.json", help="Path to local catalog")
    parser.add_argument("--database-id", help="Notion Database ID (or collection ID)")
    args = parser.parse_args()

    api_key = os.environ.get("NOTION_API_KEY")
    if not api_key:
        print("[!] Note: NOTION_API_KEY environment variable required for direct sync.")
        return

    if not os.path.exists(args.index):
        print(f"[!] Index file not found: {args.index}")
        return

    with open(args.index, "r", encoding="utf-8") as f:
        items = json.load(f)

    sync_batch(api_key, args.database_id, items)


if __name__ == "__main__":
    main()
