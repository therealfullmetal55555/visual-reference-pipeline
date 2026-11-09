#!/usr/bin/env python3
"""
Icon Generation Pipeline for Visual Reference Workflow.

Generates official platform icons from the brand clover mark:
1. macOS AppIcon.icns (Apple HIG standard: 1024x1024 canvas, 824px squircle, continuous curvature,
   standard ambient + key drop shadow, embedded retina resolutions: 16 to 1024).
2. Windows app.ico (Microsoft Windows 10/11 Fluent standard: multi-resolution 16, 24, 32, 48, 64, 128, 256).
3. Web icons (favicon.ico, apple-touch-icon.png 180x180, favicon-32x32.png, favicon-16x16.png, icon-512.png).
"""

import shutil
import subprocess
from pathlib import Path
import numpy as np
from PIL import Image, ImageChops, ImageDraw, ImageFilter


def extract_clover_emblem(source_jpg: Path) -> Image.Image:
    """Extract clean, anti-aliased white clover with inner gothic D cutout."""
    raw = Image.open(source_jpg).convert("L")
    arr = np.array(raw)

    # Crop to exact clover bounds with anti-aliasing padding
    crop = arr[150:658, 399:874].astype(np.float32)

    # Smooth threshold curve capturing all subpixel edge transitions
    alpha = np.clip((crop - 10.0) / (205.0 - 10.0) * 255.0, 0.0, 255.0).astype(np.uint8)

    # Pure white emblem with isolated alpha
    emblem = Image.new("RGBA", (crop.shape[1], crop.shape[0]), (255, 255, 255, 255))
    emblem.putalpha(Image.fromarray(alpha, mode="L"))
    return emblem


def build_macos_tile(clover_emblem: Image.Image, tile_size: int = 824, radius: int = 185) -> Image.Image:
    """Build the 824x824 squircle tile with Apple continuous curvature, gradient, and rim highlight."""
    scale = 4  # 4x supersampling for ultra-smooth edges
    hr_w = tile_size * scale
    hr_h = tile_size * scale
    hr_r = radius * scale

    # 1. Supersampled squircle mask
    hr_mask = Image.new("L", (hr_w, hr_h), 0)
    hr_draw = ImageDraw.Draw(hr_mask)
    hr_draw.rounded_rectangle([0, 0, hr_w, hr_h], radius=hr_r, fill=255)
    squircle_mask = hr_mask.resize((tile_size, tile_size), Image.Resampling.LANCZOS)

    # 2. Luxury matte obsidian gradient (#1c1c20 top to #09090b bottom)
    top_color = np.array([28, 28, 32], dtype=np.float32)
    bot_color = np.array([9, 9, 11], dtype=np.float32)
    grad_arr = np.zeros((tile_size, tile_size, 4), dtype=np.uint8)
    for y in range(tile_size):
        t = y / (tile_size - 1)
        t = t * t * (3 - 2 * t)  # smoothstep ease
        col = (1.0 - t) * top_color + t * bot_color
        grad_arr[y, :, :3] = col.astype(np.uint8)
        grad_arr[y, :, 3] = 255
    tile = Image.fromarray(grad_arr, mode="RGBA")
    tile.putalpha(squircle_mask)

    # 3. Inner border / Apple rim light (1.5px stroke: white 16% at top to 4% at bottom)
    stroke_w = 2
    hr_inner = Image.new("L", (hr_w, hr_h), 0)
    hr_inner_draw = ImageDraw.Draw(hr_inner)
    hr_inner_draw.rounded_rectangle(
        [stroke_w * scale, stroke_w * scale, hr_w - stroke_w * scale, hr_h - stroke_w * scale],
        radius=(radius - stroke_w) * scale,
        fill=255,
    )
    inner_mask = hr_inner.resize((tile_size, tile_size), Image.Resampling.LANCZOS)
    border_mask = ImageChops.subtract(squircle_mask, inner_mask)

    rim_arr = np.zeros((tile_size, tile_size, 4), dtype=np.uint8)
    for y in range(tile_size):
        alpha_val = int(42 * (1.0 - y / tile_size) + 10 * (y / tile_size))
        rim_arr[y, :, :3] = 255
        rim_arr[y, :, 3] = alpha_val
    rim_img = Image.fromarray(rim_arr, mode="RGBA")
    rim_img.putalpha(ImageChops.multiply(rim_img.split()[-1], border_mask))
    tile = Image.alpha_composite(tile, rim_img)

    # 4. Clover emblem scaling and positioning (height = 560 px inside 824 px tile)
    target_h = 560
    target_w = int(clover_emblem.width * (target_h / clover_emblem.height))
    clover_scaled = clover_emblem.resize((target_w, target_h), Image.Resampling.LANCZOS)

    clover_x = (tile_size - target_w) // 2
    clover_y = (tile_size - target_h) // 2 - 4  # optical lift

    # Delicate drop shadow under clover
    shadow_layer = Image.new("RGBA", (tile_size, tile_size), (0, 0, 0, 0))
    black_clover = Image.new("RGBA", (target_w, target_h), (0, 0, 0, int(255 * 0.40)))
    black_clover.putalpha(clover_scaled.split()[-1])
    shadow_layer.paste(black_clover, (clover_x, clover_y + 6), black_clover)
    shadow_layer = shadow_layer.filter(ImageFilter.GaussianBlur(radius=8))

    tile = Image.alpha_composite(tile, shadow_layer)
    tile.paste(clover_scaled, (clover_x, clover_y), clover_scaled)

    return tile, squircle_mask


def build_macos_master_1024(clover_emblem: Image.Image) -> Image.Image:
    """Build full 1024x1024 canvas with Apple standard drop shadows."""
    canvas = Image.new("RGBA", (1024, 1024), (0, 0, 0, 0))
    tile, squircle_mask = build_macos_tile(clover_emblem, tile_size=824, radius=185)

    tile_x = (1024 - 824) // 2  # 100
    tile_y = (1024 - 824) // 2  # 100

    # Key shadow (lower, softer)
    key_shadow = Image.new("RGBA", (1024, 1024), (0, 0, 0, 0))
    key_tile = Image.new("RGBA", (824, 824), (0, 0, 0, int(255 * 0.32)))
    key_tile.putalpha(squircle_mask)
    key_shadow.paste(key_tile, (tile_x, tile_y + 24), key_tile)
    key_shadow = key_shadow.filter(ImageFilter.GaussianBlur(radius=36))

    # Ambient shadow (all around, tight)
    amb_shadow = Image.new("RGBA", (1024, 1024), (0, 0, 0, 0))
    amb_tile = Image.new("RGBA", (824, 824), (0, 0, 0, int(255 * 0.22)))
    amb_tile.putalpha(squircle_mask)
    amb_shadow.paste(amb_tile, (tile_x, tile_y + 10), amb_tile)
    amb_shadow = amb_shadow.filter(ImageFilter.GaussianBlur(radius=18))

    canvas = Image.alpha_composite(canvas, key_shadow)
    canvas = Image.alpha_composite(canvas, amb_shadow)
    canvas.paste(tile, (tile_x, tile_y), tile)

    return canvas


def build_windows_master_512(clover_emblem: Image.Image) -> Image.Image:
    """Build Windows 11 Fluent 512x512 master (tight 22px margin, 468px squircle)."""
    canvas_size = 512
    tile_size = 468
    radius = 104
    tile_offset = (canvas_size - tile_size) // 2  # 22 px

    scale = 4
    hr_w = tile_size * scale
    hr_h = tile_size * scale
    hr_r = radius * scale

    hr_mask = Image.new("L", (hr_w, hr_h), 0)
    hr_draw = ImageDraw.Draw(hr_mask)
    hr_draw.rounded_rectangle([0, 0, hr_w, hr_h], radius=hr_r, fill=255)
    squircle_mask = hr_mask.resize((tile_size, tile_size), Image.Resampling.LANCZOS)

    top_color = np.array([28, 28, 32], dtype=np.float32)
    bot_color = np.array([9, 9, 11], dtype=np.float32)
    grad_arr = np.zeros((tile_size, tile_size, 4), dtype=np.uint8)
    for y in range(tile_size):
        t = y / (tile_size - 1)
        t = t * t * (3 - 2 * t)
        col = (1.0 - t) * top_color + t * bot_color
        grad_arr[y, :, :3] = col.astype(np.uint8)
        grad_arr[y, :, 3] = 255
    tile = Image.fromarray(grad_arr, mode="RGBA")
    tile.putalpha(squircle_mask)

    # Rim stroke
    stroke_w = 2
    hr_inner = Image.new("L", (hr_w, hr_h), 0)
    hr_inner_draw = ImageDraw.Draw(hr_inner)
    hr_inner_draw.rounded_rectangle(
        [stroke_w * scale, stroke_w * scale, hr_w - stroke_w * scale, hr_h - stroke_w * scale],
        radius=(radius - stroke_w) * scale,
        fill=255,
    )
    inner_mask = hr_inner.resize((tile_size, tile_size), Image.Resampling.LANCZOS)
    border_mask = ImageChops.subtract(squircle_mask, inner_mask)

    rim_arr = np.zeros((tile_size, tile_size, 4), dtype=np.uint8)
    for y in range(tile_size):
        alpha_val = int(45 * (1.0 - y / tile_size) + 12 * (y / tile_size))
        rim_arr[y, :, :3] = 255
        rim_arr[y, :, 3] = alpha_val
    rim_img = Image.fromarray(rim_arr, mode="RGBA")
    rim_img.putalpha(ImageChops.multiply(rim_img.split()[-1], border_mask))
    tile = Image.alpha_composite(tile, rim_img)

    # Clover
    target_h = 320
    target_w = int(clover_emblem.width * (target_h / clover_emblem.height))
    clover_scaled = clover_emblem.resize((target_w, target_h), Image.Resampling.LANCZOS)

    clover_x = (tile_size - target_w) // 2
    clover_y = (tile_size - target_h) // 2 - 2

    shadow_layer = Image.new("RGBA", (tile_size, tile_size), (0, 0, 0, 0))
    black_clover = Image.new("RGBA", (target_w, target_h), (0, 0, 0, int(255 * 0.40)))
    black_clover.putalpha(clover_scaled.split()[-1])
    shadow_layer.paste(black_clover, (clover_x, clover_y + 4), black_clover)
    shadow_layer = shadow_layer.filter(ImageFilter.GaussianBlur(radius=6))

    tile = Image.alpha_composite(tile, shadow_layer)
    tile.paste(clover_scaled, (clover_x, clover_y), clover_scaled)

    # Canvas with subtle Windows shadow
    canvas = Image.new("RGBA", (canvas_size, canvas_size), (0, 0, 0, 0))
    shadow = Image.new("RGBA", (canvas_size, canvas_size), (0, 0, 0, 0))
    shadow_tile = Image.new("RGBA", (tile_size, tile_size), (0, 0, 0, int(255 * 0.35)))
    shadow_tile.putalpha(squircle_mask)
    shadow.paste(shadow_tile, (tile_offset, tile_offset + 8), shadow_tile)
    shadow = shadow.filter(ImageFilter.GaussianBlur(radius=16))

    canvas = Image.alpha_composite(canvas, shadow)
    canvas.paste(tile, (tile_offset, tile_offset), tile)
    return canvas


def compile_icns(master_1024: Image.Image, output_path: Path):
    """Compile Apple .icns using iconutil with all 10 standard sizes."""
    iconset = Path("/tmp/AppIcon.iconset")
    if iconset.exists():
        shutil.rmtree(iconset)
    iconset.mkdir(parents=True)

    sizes = [
        ("icon_16x16.png", 16),
        ("icon_16x16@2x.png", 32),
        ("icon_32x32.png", 32),
        ("icon_32x32@2x.png", 64),
        ("icon_128x128.png", 128),
        ("icon_128x128@2x.png", 256),
        ("icon_256x256.png", 256),
        ("icon_256x256@2x.png", 512),
        ("icon_512x512.png", 512),
        ("icon_512x512@2x.png", 1024),
    ]

    for filename, sz in sizes:
        resized = master_1024.resize((sz, sz), Image.Resampling.LANCZOS)
        resized.save(iconset / filename, "PNG")

    if output_path.exists():
        output_path.unlink()

    subprocess.run(["iconutil", "-c", "icns", str(iconset), "-o", str(output_path)], check=True)
    shutil.rmtree(iconset, ignore_errors=True)
    print(f"[✓] Compiled macOS ICNS: {output_path.name} ({output_path.stat().st_size / 1024:.1f} KB)")


def compile_ico(master_win: Image.Image, output_path: Path):
    """Compile multi-resolution Windows .ico file."""
    ico_sizes = [(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)]
    # Create resized images
    frames = []
    for s in ico_sizes:
        frame = master_win.resize(s, Image.Resampling.LANCZOS)
        frames.append(frame)

    if output_path.exists():
        output_path.unlink()

    master_win.save(output_path, format="ICO", sizes=ico_sizes)
    print(f"[✓] Compiled Windows ICO: {output_path.name} ({output_path.stat().st_size / 1024:.1f} KB)")


def generate_all_icons(clover_jpg: Path, target_dir: Path):
    """Generate complete icon set into target_dir."""
    target_dir.mkdir(parents=True, exist_ok=True)
    print(f"Extracting clover emblem from {clover_jpg} ...")
    emblem = extract_clover_emblem(clover_jpg)

    print("Building macOS 1024x1024 master icon ...")
    macos_master = build_macos_master_1024(emblem)
    macos_master.save(target_dir / "icon-1024.png", "PNG")
    macos_master.resize((512, 512), Image.Resampling.LANCZOS).save(target_dir / "icon-512.png", "PNG")

    print("Compiling macOS AppIcon.icns ...")
    compile_icns(macos_master, target_dir / "AppIcon.icns")
    # Duplicate as icon.icns for standard compatibility
    shutil.copy2(target_dir / "AppIcon.icns", target_dir / "icon.icns")

    print("Building Windows master icon & compiling app.ico ...")
    win_master = build_windows_master_512(emblem)
    compile_ico(win_master, target_dir / "app.ico")
    compile_ico(win_master, target_dir / "icon.ico")

    print("Generating web icons (favicon.ico, apple-touch-icon, pngs) ...")
    # Web favicon
    compile_ico(win_master, target_dir / "favicon.ico")

    # Apple touch icon (180x180 squircle tile without canvas drop shadow)
    touch_tile, _ = build_macos_tile(emblem, tile_size=180, radius=40)
    touch_tile.save(target_dir / "apple-touch-icon.png", "PNG")

    # Favicon PNGs
    win_master.resize((32, 32), Image.Resampling.LANCZOS).save(target_dir / "favicon-32x32.png", "PNG")
    win_master.resize((16, 16), Image.Resampling.LANCZOS).save(target_dir / "favicon-16x16.png", "PNG")

    print("[✓] All icons successfully generated in:", target_dir)


if __name__ == "__main__":
    import sys
    base_dir = Path(__file__).resolve().parents[1]
    clover = base_dir / "reference_app" / "clover-original.jpg"
    out_dir = base_dir / "reference_app"
    generate_all_icons(clover, out_dir)
