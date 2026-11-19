#!/usr/bin/env python3
"""
Application Packaging Script for Visual Reference Workflow.

Builds:
1. Native macOS .app bundle (Visual Reference App.app)
2. macOS DMG installer (Visual-Reference-App-macOS.dmg)
3. macOS application ZIP (Visual-Reference-App-macOS.zip)
4. Cross-platform portable bundle with run.sh and run.bat (Visual-Reference-App-Portable.zip)
"""

import argparse
import os
import platform
import plistlib
import tempfile
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


def build_macos_app(archive=None, previous_workspace=None, app_only=False, sdk_path=None):
    """Compile the SwiftUI app and package it without user media."""
    DIST.mkdir(parents=True, exist_ok=True)
    bundle_name = "Visual Reference App.app"
    app_bundle = DIST / bundle_name
    plist = {
        "CFBundleExecutable": "VisualReference",
        "CFBundleIconFile": "AppIcon",
        "CFBundleIdentifier": "com.visualreference.app",
        "CFBundleName": "Visual Reference App",
        "CFBundleDisplayName": "Visual Reference App",
        "CFBundlePackageType": "APPL",
        "CFBundleShortVersionString": "1.1.0",
        "CFBundleVersion": "2",
        "LSMinimumSystemVersion": "13.0",
        "NSHighResolutionCapable": True,
        "NSDesktopFolderUsageDescription": "Открывает выбранный архив визуальных референсов.",
        "NSDocumentsFolderUsageDescription": "Открывает выбранные материалы.",
    }
    if archive:
        plist["VRWInitialArchive"] = str(archive.resolve())
    if previous_workspace:
        plist["VRWPreviousWorkspace"] = str(previous_workspace.resolve())

    with tempfile.TemporaryDirectory(prefix="native-", dir=DIST) as directory:
        stage = Path(directory)
        staged_app = stage / bundle_name
        contents = staged_app / "Contents"
        macos = contents / "MacOS"
        resources = contents / "Resources"
        app_dir = resources / "app"
        macos.mkdir(parents=True)
        app_dir.mkdir(parents=True)
        for name in ("desktop_bootstrap.py", "server.py", "workflow.py"):
            shutil.copy2(APP_SRC / name, app_dir / name)
        icns_src = APP_SRC / "AppIcon.icns"
        if icns_src.is_file():
            shutil.copy2(icns_src, resources / "AppIcon.icns")
        with (contents / "Info.plist").open("wb") as destination:
            plistlib.dump(plist, destination)
        sources = sorted((ROOT / "scripts" / "native").glob("*.swift"))
        cache = stage / "modules"
        cache.mkdir()
        build_env = dict(os.environ, CLANG_MODULE_CACHE_PATH=str(cache), SWIFT_MODULE_CACHE_PATH=str(cache))
        sdk = ["-sdk", str(sdk_path)] if sdk_path else []
        subprocess.run(["xcrun", "swiftc", *sdk, "-O", "-swift-version", "5", "-parse-as-library",
                        "-target", f"{platform.machine()}-apple-macosx13.0", "-module-cache-path", str(cache),
                        *map(str, sources), "-o", str(macos / "VisualReference")], check=True, env=build_env)
        if shutil.which("codesign"):
            subprocess.run(["codesign", "--force", "--deep", "-s", "-", str(staged_app)], check=True)
        zip_app = DIST / "Visual-Reference-App-macOS.zip"
        zip_staged = stage / zip_app.name
        subprocess.run(["ditto", "-c", "-k", "--sequesterRsrc", "--keepParent", str(staged_app), str(zip_staged)], check=True)
        if app_bundle.exists():
            app_bundle.rename(stage / "previous.app")
        staged_app.rename(app_bundle)
        zip_staged.replace(zip_app)
    print(f"Built {app_bundle}")
    print(f"Built {zip_app}")
    if app_only:
        return

    icns_path = app_bundle / "Contents" / "Resources" / "AppIcon.icns"
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

    # Portable package
    portable = DIST / "Visual-Reference-Workflow"
    if portable.exists():
        shutil.rmtree(portable)
    portable.mkdir(parents=True)
    shutil.copytree(APP_SRC, portable / "app", ignore=shutil.ignore_patterns("__pycache__", "uploads", "*.sqlite3*", "*.mp3", "*.mp4"))

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
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--app-only", action="store_true", help="Build the .app and desktop ZIP")
    parser.add_argument("--archive-dir", type=Path, help="Preselect a local media archive")
    parser.add_argument("--previous-workspace", type=Path, help="Copy an existing database on first launch")
    parser.add_argument("--sdk-path", type=Path, help="Build with a specified macOS SDK")
    args = parser.parse_args()
    build_macos_app(args.archive_dir, args.previous_workspace, args.app_only, args.sdk_path)
