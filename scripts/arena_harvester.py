#!/usr/bin/env python3
"""Download selected Are.na channel images into the local reference archive."""
import argparse
import json
import mimetypes
import os
import re
import sys
import tempfile
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlparse
from urllib.request import Request, urlopen

API = "https://api.are.na/v2/channels/{}/contents?per=100&page={}"
USER_AGENT = "visual-reference-pipeline/1.0"
EXTENSIONS = {"image/jpeg": ".jpg", "image/png": ".png", "image/webp": ".webp", "image/gif": ".gif", "image/avif": ".avif"}


def load_index(path):
    if not path.exists():
        return []
    with path.open(encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, list) or any(not isinstance(item, dict) for item in data):
        raise ValueError("Индекс должен содержать массив объектов; исходный файл не изменён")
    return data


def save_index(path, index):
    path.parent.mkdir(parents=True, exist_ok=True)
    name = None
    try:
        with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=path.parent, delete=False) as f:
            name = f.name
            json.dump(index, f, ensure_ascii=False, indent=2)
            f.write("\n")
            f.flush()
            os.fsync(f.fileno())
        os.replace(name, path)
    finally:
        if name and os.path.exists(name):
            os.unlink(name)


def fetch_page(channel, page, token):
    headers = {"User-Agent": USER_AGENT, "Accept": "application/json"}
    if token:
        headers["Authorization"] = "Bearer " + token
    request = Request(API.format(quote(channel, safe=""), page), headers=headers)
    with urlopen(request, timeout=30) as response:
        data = json.load(response)
    if not isinstance(data, dict) or not isinstance(data.get("contents"), list):
        raise ValueError("Неожиданный ответ API: отсутствует массив contents")
    return data["contents"]


def download(url, output, base):
    if urlparse(url).scheme != "https":
        raise ValueError("Ожидалась HTTPS-ссылка на изображение")
    request = Request(url, headers={"User-Agent": USER_AGENT, "Accept": "image/*"})
    temp = None
    try:
        with urlopen(request, timeout=60) as response:
            content_type = response.headers.get_content_type().lower()
            if not content_type.startswith("image/"):
                raise ValueError("Сервер вернул не изображение: " + content_type)
            ext = EXTENSIONS.get(content_type) or mimetypes.guess_extension(content_type)
            if not ext or not re.fullmatch(r"\.[a-z0-9]{1,8}", ext):
                raise ValueError("Неизвестный формат изображения: " + content_type)
            target = output / (base + ext)
            if target.exists():
                raise FileExistsError("Файл уже существует и не будет перезаписан: " + str(target))
            with tempfile.NamedTemporaryFile("wb", dir=output, delete=False) as f:
                temp = f.name
                size = 0
                while True:
                    chunk = response.read(1024 * 1024)
                    if not chunk:
                        break
                    size += len(chunk)
                    f.write(chunk)
                if size == 0:
                    raise ValueError("Пустой файл изображения")
                f.flush()
                os.fsync(f.fileno())
        # Create without overwriting an existing archive file.
        os.link(temp, target)
        return target
    finally:
        if temp and os.path.exists(temp):
            os.unlink(temp)


def harvest(channel, output, index_path, token=None, category="Исследовать"):
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]*", channel):
        raise ValueError("Укажите slug канала, а не URL или путь")
    output, index_path = output.expanduser().resolve(), index_path.expanduser().resolve()
    index = load_index(index_path)
    output.mkdir(parents=True, exist_ok=True)
    urls = {entry.get("canonical_url") for entry in index}
    files = {entry.get("file") for entry in index}
    page, added, skipped, failed = 1, 0, 0, 0
    while True:
        blocks = fetch_page(channel, page, token)
        if not blocks:
            break
        for block in blocks:
            if not isinstance(block, dict):
                continue
            image = block.get("image") or {}
            if block.get("class") not in ("Image", "Link", "Attachment") or not isinstance(image, dict):
                continue
            original = image.get("original") or {}
            image_url = original.get("url") if isinstance(original, dict) else None
            block_id = block.get("id")
            if not image_url or not isinstance(block_id, int) or isinstance(block_id, bool):
                continue
            canonical = f"https://www.are.na/block/{block_id}"
            base = f"arena_{channel}_{block_id}"
            if canonical in urls or any(isinstance(f, str) and Path(f).stem == base for f in files):
                skipped += 1
                continue
            if any(output.glob(base + ".*")):
                print(f"[!] Уже существует неиндексированный файл {base}; пропущен", file=sys.stderr)
                skipped += 1
                continue
            try:
                target = download(image_url, output, base)
                try:
                    local_path = target.relative_to(index_path.parent).as_posix()
                except ValueError:
                    local_path = os.path.relpath(target, index_path.parent).replace(os.sep, "/")
                source = block.get("source") or {}
                source_url = source.get("url") if isinstance(source, dict) else None
                user = block.get("user") or {}
                author = block.get("connected_by_username") or (user.get("username") if isinstance(user, dict) else None) or ""
                description = block.get("description") or f"Канал {channel}; тип блока: {block.get('class')}"
                if source_url:
                    description += f"\nПервоисточник: {source_url}"
                record = {"title": block.get("title") or target.name, "author": author,
                          "canonical_url": canonical, "file": target.name, "local_path": local_path,
                          "observation": description, "tags": ["are.na", channel],
                          "category": category, "format": "Пост", "review_depth": "Частично просмотрено",
                          "download_status": "downloaded"}
                index.append(record)
                try:
                    save_index(index_path, index)
                except Exception:
                    index.pop()
                    target.unlink()
                    raise
                urls.add(canonical)
                files.add(target.name)
                added += 1
                print(f"[+] {target.name}")
            except (OSError, ValueError, URLError) as exc:
                failed += 1
                print(f"[!] Блок {block_id}: {exc}", file=sys.stderr)
        page += 1
    print(f"Готово: добавлено {added}, пропущено {skipped}, ошибок {failed}.")
    return 1 if failed else 0


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--channel", required=True, help="slug канала Are.na")
    parser.add_argument("--output", type=Path, default=Path("~/Desktop/instagram_archive/images/Референсы"))
    parser.add_argument("--index", type=Path, default=Path("~/Desktop/instagram_archive/archive_index.json"))
    parser.add_argument("--token", default=None, help="токен API (лучше задать ARENA_API_TOKEN)")
    parser.add_argument("--category", default="Исследовать")
    args = parser.parse_args(argv)
    try:
        return harvest(args.channel, args.output, args.index, args.token or os.environ.get("ARENA_API_TOKEN"), args.category)
    except HTTPError as exc:
        print(f"Ошибка API Are.na: HTTP {exc.code}. Проверьте канал и доступ.", file=sys.stderr)
    except (OSError, ValueError, URLError) as exc:
        print(f"Ошибка: {exc}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())
