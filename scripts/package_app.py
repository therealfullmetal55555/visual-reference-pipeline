#!/usr/bin/env python3
"""
Application Packaging Script for Visual Reference Workflow.

Builds:
1. Native macOS .app bundle (Visual Reference App.app)
2. macOS DMG installer (Visual-Reference-App-macOS.dmg)
3. macOS application ZIP (Visual-Reference-App-macOS.zip)
4. Cross-platform portable bundle with run.sh and run.bat (Visual-Reference-App-Portable.zip)
"""

import os
import sys
import shutil
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DIST = ROOT / "dist"
APP_SRC = ROOT / "reference_app"


def build_icon(logo_path: Path, output_icns: Path):
    """Generate macOS .icns file from PNG using sips and iconutil."""
    iconset = Path("/tmp/AppIcon.iconset")
    if iconset.exists():
        shutil.rmtree(iconset)
    iconset.mkdir(parents=True)

    sizes = [16, 32, 64, 128, 256, 512]
    for s in sizes:
        subprocess.run(
            ["sips", "-z", str(s), str(s), str(logo_path), "--out", str(iconset / f"icon_{s}x{s}.png")],
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL
        )
        s2 = s * 2
        if s2 <= 1024:
            subprocess.run(
                ["sips", "-z", str(s2), str(s2), str(logo_path), "--out", str(iconset / f"icon_{s}x{s}@2x.png")],
                check=True,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL
            )

    if output_icns.exists():
        output_icns.unlink()
    subprocess.run(["iconutil", "-c", "icns", str(iconset), "-o", str(output_icns)], check=True)
    shutil.rmtree(iconset, ignore_errors=True)
    print(f"[✓] Generated macOS icon: {output_icns.name}")


def build_macos_app():
    """Build macOS .app bundle and DMG installer."""
    if DIST.exists():
        shutil.rmtree(DIST)
    DIST.mkdir(parents=True, exist_ok=True)

    # Ensure official icons are generated
    icns_src = APP_SRC / "AppIcon.icns"
    if not icns_src.exists():
        icon_gen = ROOT / "scripts" / "generate_icons.py"
        if icon_gen.exists():
            subprocess.run([sys.executable, str(icon_gen)], check=True)

    app_bundle = DIST / "Visual Reference App.app"
    contents = app_bundle / "Contents"
    macos = contents / "MacOS"
    resources = contents / "Resources"
    app_dir = resources / "app"

    macos.mkdir(parents=True, exist_ok=True)
    app_dir.mkdir(parents=True, exist_ok=True)

    # Copy reference_app files
    for item in APP_SRC.iterdir():
        if item.name in [".git", "__pycache__", "references.sqlite3", "references.sqlite3-wal", "references.sqlite3-shm"]:
            continue
        if item.is_dir():
            shutil.copytree(
                item,
                app_dir / item.name,
                ignore=shutil.ignore_patterns("__pycache__", "*.sqlite3*", "*.mp3", "*.mp4")
            )
        else:
            shutil.copy2(item, app_dir / item.name)

    # Copy official macOS icon
    icns_path = resources / "AppIcon.icns"
    if icns_src.exists():
        shutil.copy2(icns_src, icns_path)
        print(f"[✓] Installed official macOS icon: {icns_path.name}")

    # Info.plist
    info_plist = """<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>CFBundleExecutable</key>
    <string>launcher</string>
    <key>CFBundleIconFile</key>
    <string>AppIcon</string>
    <key>CFBundleIdentifier</key>
    <string>com.visualreference.app</string>
    <key>CFBundleName</key>
    <string>Visual Reference App</string>
    <key>CFBundleDisplayName</key>
    <string>Visual Reference App</string>
    <key>CFBundlePackageType</key>
    <string>APPL</string>
    <key>CFBundleShortVersionString</key>
    <string>1.0.0</string>
    <key>CFBundleVersion</key>
    <string>1.0.0</string>
    <key>LSMinimumSystemVersion</key>
    <string>11.0</string>
    <key>NSHighResolutionCapable</key>
    <true/>
</dict>
</plist>"""
    (contents / "Info.plist").write_text(info_plist, encoding="utf-8")

    # Launcher script
    launcher = """#!/bin/bash
DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" >/dev/null 2>&1 && pwd )"
APP_DIR="$DIR/../Resources/app"

cd "$APP_DIR" || exit 1

PORT=8765
if curl -s -I "http://127.0.0.1:$PORT/" 2>/dev/null | grep -qi "Visual Reference"; then
    open "http://127.0.0.1:$PORT/"
    exit 0
fi

while lsof -i :$PORT >/dev/null 2>&1; do
    PORT=$((PORT+1))
done

cleanup() {
    if [ -n "$SERVER_PID" ]; then
        kill "$SERVER_PID" 2>/dev/null
    fi
    exit 0
}
trap cleanup SIGINT SIGTERM EXIT

PORT=$PORT python3 server.py >/dev/null 2>&1 &
SERVER_PID=$!

for i in {1..25}; do
    if curl -s -I "http://127.0.0.1:$PORT/" >/dev/null 2>&1; then
        break
    fi
    sleep 0.2
done

open "http://127.0.0.1:$PORT/"
wait "$SERVER_PID"
"""
    launcher_file = macos / "launcher"
    launcher_file.write_text(launcher, encoding="utf-8")
    launcher_file.chmod(0o755)

    if shutil.which("codesign"):
        subprocess.run(["codesign", "--force", "--deep", "-s", "-", str(app_bundle)], check=True)
        print("[✓] Ad-hoc signed: Visual Reference App.app")

    # Build DMG
    if shutil.which("hdiutil"):
        staging = DIST / "dmg_staging"
        if staging.exists():
            shutil.rmtree(staging)
        staging.mkdir(parents=True)
        shutil.copytree(app_bundle, staging / "Visual Reference App.app", symlinks=True)
        os.symlink("/Applications", staging / "Applications")

        # DMG volume icon
        vol_icon = staging / ".VolumeIcon.icns"
        if icns_path.exists():
            shutil.copy2(icns_path, vol_icon)
            if shutil.which("SetFile"):
                subprocess.run(["SetFile", "-a", "C", str(staging)], check=False)

        dmg_path = DIST / "Visual-Reference-App-macOS.dmg"
        subprocess.run(
            ["hdiutil", "create", "-volname", "Visual Reference App", "-srcfolder", str(staging), "-ov", "-format", "UDZO", str(dmg_path)],
            check=True,
            stdout=subprocess.DEVNULL
        )
        shutil.rmtree(staging)
        print(f"[✓] Built DMG: {dmg_path.name} ({dmg_path.stat().st_size / (1024*1024):.2f} MB)")

    # Zip macOS app
    zip_app = DIST / "Visual-Reference-App-macOS.zip"
    subprocess.run(
        ["ditto", "-c", "-k", "--sequesterRsrc", "--keepParent", str(app_bundle), str(zip_app)],
        check=True
    )
    print(f"[✓] Built macOS ZIP: {zip_app.name} ({zip_app.stat().st_size / (1024*1024):.2f} MB)")

    # Portable package
    portable = DIST / "Visual-Reference-Workflow"
    if portable.exists():
        shutil.rmtree(portable)
    portable.mkdir(parents=True)
    shutil.copytree(APP_SRC, portable / "app", ignore=shutil.ignore_patterns("__pycache__", "*.sqlite3*", "*.mp3", "*.mp4"))

    run_sh = """#!/bin/bash
cd "$(dirname "$0")/app" || exit 1
echo "Starting Visual Reference Workflow on http://127.0.0.1:8765 ..."
if command -v python3 >/dev/null 2>&1; then
    (sleep 1 && (open "http://127.0.0.1:8765" 2>/dev/null || xdg-open "http://127.0.0.1:8765" 2>/dev/null)) &
    python3 server.py
else
    echo "Error: python3 is required to run Visual Reference Workflow."
    exit 1
fi
"""
    (portable / "run.sh").write_text(run_sh, encoding="utf-8")
    (portable / "run.sh").chmod(0o755)

    run_bat = """@echo off
cd /d "%~dp0app"
echo Starting Visual Reference Workflow on http://127.0.0.1:8765 ...
start http://127.0.0.1:8765
python server.py
pause
"""
    (portable / "run.bat").write_text(run_bat, encoding="utf-8")

    (portable / "README.txt").write_text("""Visual Reference Workflow (Portable Edition)

Launch:
- macOS / Linux: run ./run.sh
- Windows: run run.bat

Requires Python 3.9+ (no external dependencies).
Web interface: http://127.0.0.1:8765
""", encoding="utf-8")

    zip_portable = DIST / "Visual-Reference-App-Portable.zip"
    subprocess.run(
        ["ditto", "-c", "-k", "--sequesterRsrc", "--keepParent", str(portable), str(zip_portable)],
        check=True
    )
    shutil.rmtree(portable)
    print(f"[✓] Built Portable ZIP: {zip_portable.name} ({zip_portable.stat().st_size / (1024*1024):.2f} MB)")


if __name__ == "__main__":
    build_macos_app()
