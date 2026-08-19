#!/usr/bin/env python3
"""Build one deterministic, non-repeating editorial image per queued post.

The generator combines AI-created source art and a paper-texture atlas with
theme-specific layouts.  A post's ID and text form the seed, so reruns are
stable while every post still receives a distinct 1080x1350 JPEG.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import random
from collections import Counter
from pathlib import Path

from PIL import Image, ImageDraw, ImageEnhance, ImageFilter, ImageOps

from prepare_image_urls import classify


WIDTH, HEIGHT = 1080, 1350
PALETTES = {
    "typography": ("#F4EDDF", "#153E9F", "#14161B", "#F37A2A"),
    "layout": ("#F2EEE6", "#2156C8", "#15171B", "#E96F2C"),
    "color": ("#F5EADB", "#2459C4", "#202124", "#F1762B"),
    "photo": ("#ECE8E0", "#315EA8", "#16191E", "#E67A35"),
    "brand": ("#F3EEE4", "#184DB7", "#111318", "#F27D2F"),
    "process": ("#F1EBDD", "#2857B8", "#1C1D22", "#EF762B"),
    "career": ("#F5EFE5", "#244FA7", "#17191D", "#E97835"),
    "ai-tech": ("#EDF0EA", "#164FC2", "#10151C", "#FF7A2C"),
    "marketing": ("#F5EDDF", "#2758B7", "#17191E", "#EF792F"),
}


def seed_for(post: dict) -> int:
    raw = f"{post.get('id')}|{post.get('text', '')}".encode("utf-8")
    return int(hashlib.sha256(raw).hexdigest()[:16], 16)


def rgb(hex_color: str) -> tuple[int, int, int]:
    value = hex_color.lstrip("#")
    return tuple(int(value[index:index + 2], 16) for index in (0, 2, 4))


def cover(source: Image.Image, size: tuple[int, int], rng: random.Random,
          zoom_min: float = 1.0, zoom_max: float = 1.22) -> Image.Image:
    """Scale and crop an image to cover size using seeded art direction."""
    target_w, target_h = size
    src = source.convert("RGB")
    base_scale = max(target_w / src.width, target_h / src.height)
    scale = base_scale * rng.uniform(zoom_min, zoom_max)
    resized = src.resize(
        (max(target_w, round(src.width * scale)), max(target_h, round(src.height * scale))),
        Image.Resampling.LANCZOS,
    )
    max_x = max(0, resized.width - target_w)
    max_y = max(0, resized.height - target_h)
    x = round(max_x * rng.random())
    y = round(max_y * rng.random())
    return resized.crop((x, y, x + target_w, y + target_h))


def tuned(source: Image.Image, rng: random.Random) -> Image.Image:
    image = ImageEnhance.Color(source).enhance(rng.uniform(0.86, 1.12))
    image = ImageEnhance.Contrast(image).enhance(rng.uniform(0.94, 1.10))
    image = ImageEnhance.Brightness(image).enhance(rng.uniform(0.96, 1.05))
    if rng.random() < 0.35:
        image = image.filter(ImageFilter.GaussianBlur(rng.uniform(0.15, 0.45)))
    return image


def paste_rounded(canvas: Image.Image, artwork: Image.Image, box: tuple[int, int, int, int],
                  radius: int = 36) -> None:
    x0, y0, x1, y1 = box
    art = artwork.resize((x1 - x0, y1 - y0), Image.Resampling.LANCZOS)
    mask = Image.new("L", art.size, 0)
    ImageDraw.Draw(mask).rounded_rectangle((0, 0, art.width, art.height), radius=radius, fill=255)
    canvas.paste(art, (x0, y0), mask)


def paste_polygon(canvas: Image.Image, artwork: Image.Image,
                  points: list[tuple[int, int]]) -> None:
    mask = Image.new("L", canvas.size, 0)
    ImageDraw.Draw(mask).polygon(points, fill=255)
    canvas.paste(artwork.resize(canvas.size, Image.Resampling.LANCZOS), (0, 0), mask)


def texture_background(texture: Image.Image, palette: tuple[str, ...],
                       rng: random.Random) -> Image.Image:
    paper = cover(texture, (WIDTH, HEIGHT), rng, 1.05, 1.65)
    flat = Image.new("RGB", (WIDTH, HEIGHT), rgb(palette[0]))
    return Image.blend(flat, paper, rng.uniform(0.25, 0.48)).convert("RGBA")


def build_layout(sources: list[Image.Image], texture: Image.Image,
                 palette: tuple[str, ...], template: int,
                 rng: random.Random) -> Image.Image:
    bg = texture_background(texture, palette, rng)
    primary = tuned(cover(sources[0], (WIDTH, HEIGHT), rng), rng).convert("RGBA")
    secondary = tuned(cover(sources[1], (WIDTH, HEIGHT), rng), rng).convert("RGBA")
    tertiary = tuned(cover(sources[2], (WIDTH, HEIGHT), rng), rng).convert("RGBA")
    accent = rgb(palette[3])
    blue = rgb(palette[1])
    ink = rgb(palette[2])
    paper = rgb(palette[0])

    if template == 0:
        canvas = primary
        wash = Image.new("RGBA", canvas.size, (*blue, rng.randint(12, 34)))
        canvas = Image.alpha_composite(canvas, wash)
        draw = ImageDraw.Draw(canvas, "RGBA")
        inset = rng.randint(38, 70)
        draw.rounded_rectangle((inset, inset, WIDTH - inset, HEIGHT - inset),
                               radius=28, outline=(*paper, 210), width=rng.randint(3, 8))
        draw.rectangle((inset, HEIGHT - rng.randint(250, 360),
                        WIDTH - rng.randint(160, 280), HEIGHT - inset),
                       fill=(*paper, rng.randint(26, 54)))
    elif template == 1:
        canvas = bg
        margin = rng.randint(70, 120)
        top = rng.randint(95, 210)
        paste_rounded(canvas, primary, (margin, top, WIDTH - margin, HEIGHT - rng.randint(120, 220)), 52)
        draw = ImageDraw.Draw(canvas, "RGBA")
        draw.rounded_rectangle((margin - 18, top + 45, margin + 20, top + 285),
                               radius=16, fill=(*accent, 235))
        draw.ellipse((WIDTH - 255, 35, WIDTH - 65, 225), fill=(*blue, 115))
    elif template == 2:
        canvas = Image.new("RGBA", (WIDTH, HEIGHT), (*paper, 255))
        split = rng.randint(410, 670)
        canvas.paste(primary.crop((0, 0, split, HEIGHT)), (0, 0))
        canvas.paste(secondary.crop((split, 0, WIDTH, HEIGHT)), (split, 0))
        draw = ImageDraw.Draw(canvas, "RGBA")
        band = rng.randint(20, 58)
        draw.rectangle((split - band // 2, 0, split + band // 2, HEIGHT), fill=(*paper, 225))
        draw.rectangle((0, rng.randint(180, 420), WIDTH, rng.randint(460, 690)),
                       fill=(*accent, rng.randint(18, 46)))
    elif template == 3:
        canvas = bg
        diameter = rng.randint(760, 1010)
        cx = rng.randint(WIDTH // 2 - 90, WIDTH // 2 + 90)
        cy = rng.randint(HEIGHT // 2 - 120, HEIGHT // 2 + 90)
        circle = secondary.resize((diameter, diameter), Image.Resampling.LANCZOS)
        mask = Image.new("L", (diameter, diameter), 0)
        ImageDraw.Draw(mask).ellipse((0, 0, diameter, diameter), fill=255)
        canvas.paste(circle, (cx - diameter // 2, cy - diameter // 2), mask)
        paste_rounded(canvas, tertiary, (rng.randint(60, 170), HEIGHT - 390,
                                         rng.randint(430, 590), HEIGHT - 70), 34)
        draw = ImageDraw.Draw(canvas, "RGBA")
        draw.ellipse((cx - diameter // 2 - 18, cy - diameter // 2 - 18,
                      cx + diameter // 2 + 18, cy + diameter // 2 + 18),
                     outline=(*accent, 210), width=10)
    elif template == 4:
        canvas = bg
        cuts = sorted([0, rng.randint(330, 520), rng.randint(770, 980), HEIGHT])
        for index, (y0, y1) in enumerate(zip(cuts, cuts[1:])):
            strip = cover(sources[index], (WIDTH, y1 - y0), rng, 1.0, 1.35)
            canvas.paste(strip, (0, y0))
        draw = ImageDraw.Draw(canvas, "RGBA")
        for y in cuts[1:-1]:
            draw.rectangle((0, y - 8, WIDTH, y + 8), fill=(*paper, 230))
        draw.rectangle((rng.randint(80, 240), 0, rng.randint(300, 430), HEIGHT),
                       fill=(*blue, rng.randint(18, 38)))
    elif template == 5:
        canvas = bg
        cards = [primary, secondary, tertiary]
        specs = [
            (rng.randint(-80, 60), rng.randint(60, 160), rng.uniform(-7, 4)),
            (rng.randint(280, 420), rng.randint(330, 470), rng.uniform(-4, 7)),
            (rng.randint(40, 190), rng.randint(730, 870), rng.uniform(-6, 5)),
        ]
        for art, (x, y, angle) in zip(cards, specs):
            card = cover(art, (680, 520), rng, 1.0, 1.3)
            card = ImageOps.expand(card, border=18, fill=paper).convert("RGBA")
            card = card.rotate(angle, resample=Image.Resampling.BICUBIC, expand=True,
                               fillcolor=(0, 0, 0, 0))
            canvas.alpha_composite(card, (x, y))
    elif template == 6:
        canvas = bg
        slant = rng.randint(170, 360)
        paste_polygon(canvas, primary, [(0, 0), (WIDTH - slant, 0),
                                        (WIDTH, HEIGHT), (slant, HEIGHT)])
        draw = ImageDraw.Draw(canvas, "RGBA")
        draw.line((WIDTH - slant, 0, WIDTH, HEIGHT), fill=(*accent, 225), width=18)
        draw.line((0, rng.randint(200, 420), WIDTH, rng.randint(100, 300)),
                  fill=(*paper, 185), width=7)
    else:
        canvas = bg
        gap = rng.randint(18, 34)
        mid_x = rng.randint(430, 650)
        mid_y = rng.randint(520, 820)
        boxes = [
            (gap, gap, mid_x - gap, mid_y - gap),
            (mid_x + gap, gap, WIDTH - gap, mid_y - gap),
            (gap, mid_y + gap, mid_x - gap, HEIGHT - gap),
            (mid_x + gap, mid_y + gap, WIDTH - gap, HEIGHT - gap),
        ]
        for index, box in enumerate(boxes):
            x0, y0, x1, y1 = box
            art = cover(sources[index % 3], (x1 - x0, y1 - y0), rng, 1.0, 1.4)
            paste_rounded(canvas, art, box, rng.randint(12, 42))
        draw = ImageDraw.Draw(canvas, "RGBA")
        draw.ellipse((mid_x - 80, mid_y - 80, mid_x + 80, mid_y + 80), fill=(*accent, 225))

    # A light, differently cropped grain pass unifies the collection.
    grain = cover(texture, (WIDTH, HEIGHT), rng, 1.2, 2.0).convert("RGBA")
    grain.putalpha(rng.randint(13, 27))
    return Image.alpha_composite(canvas.convert("RGBA"), grain)


def draw_motif(canvas: Image.Image, category: str, palette: tuple[str, ...],
               item_id: int, rng: random.Random) -> None:
    draw = ImageDraw.Draw(canvas, "RGBA")
    paper, blue, ink, accent = map(rgb, palette)
    stroke = rng.randint(5, 12)

    if category == "typography":
        x = rng.randint(80, 260)
        for index in range(rng.randint(3, 6)):
            offset = index * rng.randint(42, 74)
            draw.line((x + offset, 90, x + offset, rng.randint(300, 590)),
                      fill=(*ink, 125), width=stroke)
        draw.arc((WIDTH - 380, HEIGHT - 430, WIDTH - 70, HEIGHT - 120),
                 25, 315, fill=(*accent, 210), width=stroke + 4)
    elif category == "layout":
        ox, oy = rng.randint(60, 170), rng.randint(70, 210)
        cell = rng.randint(75, 130)
        for row in range(3):
            for col in range(3):
                if rng.random() > 0.25:
                    draw.rounded_rectangle((ox + col * cell, oy + row * cell,
                                            ox + col * cell + cell - 14,
                                            oy + row * cell + cell - 14),
                                           radius=12, outline=(*paper, 165), width=5)
    elif category == "color":
        size = rng.randint(105, 165)
        x, y = rng.randint(70, 260), rng.randint(70, 220)
        for index, color in enumerate((blue, accent, ink, paper)):
            draw.rounded_rectangle((x + index * (size // 2), y + index * (size // 2),
                                    x + index * (size // 2) + size,
                                    y + index * (size // 2) + size),
                                   radius=22, fill=(*color, 190))
    elif category == "photo":
        cx, cy = rng.randint(280, 800), rng.randint(320, 980)
        for radius in (210, 150, 88):
            draw.ellipse((cx - radius, cy - radius, cx + radius, cy + radius),
                         outline=(*paper, 175), width=stroke)
        for angle in range(0, 360, 60):
            dx, dy = math.cos(math.radians(angle)) * 210, math.sin(math.radians(angle)) * 210
            draw.line((cx, cy, cx + dx, cy + dy), fill=(*accent, 95), width=4)
    elif category == "brand":
        cx, cy = rng.randint(260, 820), rng.randint(300, 900)
        draw.ellipse((cx - 190, cy - 190, cx + 190, cy + 190),
                     outline=(*paper, 175), width=stroke)
        draw.polygon([(cx, cy - 145), (cx + 125, cy + 80), (cx - 125, cy + 80)],
                     outline=(*accent, 220))
        draw.ellipse((cx - 38, cy - 38, cx + 38, cy + 38), fill=(*blue, 215))
    elif category == "process":
        points = []
        for index in range(5):
            points.append((rng.randint(100, WIDTH - 100), 150 + index * 230))
        draw.line(points, fill=(*paper, 170), width=stroke)
        for index, (x, y) in enumerate(points):
            radius = 24 + index * 5
            draw.ellipse((x - radius, y - radius, x + radius, y + radius),
                         fill=(*(accent if index % 2 else blue), 225), outline=(*paper, 220), width=4)
    elif category == "career":
        base_y = HEIGHT - 120
        for index in range(5):
            w, h = rng.randint(110, 190), 120 + index * rng.randint(48, 72)
            x = 70 + index * 190
            draw.rounded_rectangle((x, base_y - h, x + w, base_y), radius=18,
                                   fill=(*(blue if index % 2 else accent), 150))
    elif category == "ai-tech":
        nodes = [(rng.randint(90, WIDTH - 90), rng.randint(100, HEIGHT - 100)) for _ in range(8)]
        for a, b in zip(nodes, nodes[1:]):
            draw.line((*a, *b), fill=(*paper, 135), width=stroke // 2 + 2)
        for index, (x, y) in enumerate(nodes):
            radius = rng.randint(15, 34)
            draw.ellipse((x - radius, y - radius, x + radius, y + radius),
                         fill=(*(accent if index % 3 == 0 else blue), 225))
    else:
        for index in range(4):
            x = rng.randint(70, WIDTH - 350)
            y = rng.randint(80, HEIGHT - 230)
            w, h = rng.randint(180, 360), rng.randint(90, 180)
            draw.rounded_rectangle((x, y, x + w, y + h), radius=h // 2,
                                   outline=(*(accent if index % 2 else paper), 175), width=stroke)

    # Twelve-dot binary signature: a non-text micro-mark unique to each post ID.
    dot_y = HEIGHT - 54
    for bit in range(12):
        on = (item_id >> bit) & 1
        radius = 7 if on else 3
        x = WIDTH - 54 - bit * 24
        draw.ellipse((x - radius, dot_y - radius, x + radius, dot_y + radius),
                     fill=(*(accent if on else paper), 215))


def generate(queue: list[dict], asset_dir: Path, texture_path: Path,
             output_dir: Path) -> list[dict]:
    output_dir.mkdir(parents=True, exist_ok=True)
    texture = Image.open(texture_path).convert("RGB")
    manifest = []
    hashes: set[str] = set()

    for post in queue:
        item_id = int(post.get("id") or 0)
        if item_id <= 1 or post.get("status") == "posted":
            continue
        category = classify(str(post.get("text") or ""))
        palette = PALETTES[category]
        rng = random.Random(seed_for(post))
        first_variant = ((item_id - 1) % 3) + 1
        variants = [first_variant, (first_variant % 3) + 1, ((first_variant + 1) % 3) + 1]
        sources = [
            Image.open(asset_dir / f"{category}-{variant:02d}.jpg").convert("RGB")
            for variant in variants
        ]
        canvas = build_layout(sources, texture, palette, seed_for(post) % 8, rng)
        draw_motif(canvas, category, palette, item_id, rng)
        final = canvas.convert("RGB")
        filename = f"post-{item_id:03d}.jpg"
        path = output_dir / filename
        final.save(path, "JPEG", quality=88, optimize=True, progressive=True)
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        if digest in hashes:
            raise SystemExit(f"Duplicate image generated for post {item_id}: {digest}")
        hashes.add(digest)
        manifest.append({
            "id": item_id,
            "file": filename,
            "category": category,
            "sha256": digest,
        })

    (output_dir / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--queue", type=Path, default=Path("queue.json"))
    parser.add_argument("--assets", type=Path, default=Path("assets/threads"))
    parser.add_argument("--texture", type=Path,
                        default=Path("assets/threads/unique-texture.png"))
    parser.add_argument("--output", type=Path, default=Path("generated-images"))
    args = parser.parse_args()

    queue = json.loads(args.queue.read_text(encoding="utf-8"))
    manifest = generate(queue, args.assets, args.texture, args.output)
    categories = Counter(item["category"] for item in manifest)
    if len({item["sha256"] for item in manifest}) != len(manifest):
        raise SystemExit("Image uniqueness verification failed.")
    print(f"Generated {len(manifest)} unique images at {WIDTH}x{HEIGHT}.")
    print("Categories:", ", ".join(f"{key}={value}" for key, value in sorted(categories.items())))


if __name__ == "__main__":
    main()
