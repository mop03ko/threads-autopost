#!/usr/bin/env python3
"""Generate unique Magnific images for unpublished queued posts and sync them."""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import os
import random
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import requests
from PIL import Image, ImageOps

from prepare_image_urls import classify, load_queue, save_queue, sync_google_sheet


BASE = Path(__file__).resolve().parent
QUEUE_PATH = BASE / "queue.json"
API_ROOT = "https://api.magnific.com/v1/ai/text-to-image/nano-banana-pro-flash"
OUTPUT_SIZE = (1080, 1350)

PALETTES = (
    "deep navy, cobalt blue, warm ivory, and a restrained coral accent",
    "forest green, stone gray, cream, and muted amber",
    "charcoal, electric cyan, soft white, and a small vermilion accent",
    "ultramarine, lavender gray, warm sand, and black",
    "burgundy, dusty rose, parchment, and graphite",
    "teal, mineral blue, off-white, and copper",
    "midnight blue, slate, pale aqua, and tangerine",
    "olive, sage, bone white, and dark chocolate",
    "indigo, cool gray, lemon yellow, and ink black",
    "terracotta, peach, linen, and dark green",
    "plum, lilac, silver gray, and midnight",
    "monochrome black and ivory with one vivid red accent",
)

COMPOSITIONS = (
    "asymmetric editorial grid with one dominant focal object",
    "bold diagonal composition with layered depth",
    "central sculptural still life with generous negative space",
    "top-down studio arrangement with precise geometric spacing",
    "macro close-up with dramatic crop and tactile detail",
    "architectural composition with strong light and shadow",
    "floating objects arranged in a controlled visual rhythm",
    "modular collage with clean cut-paper geometry",
    "cinematic foreground-background separation",
    "minimal museum-display composition with a single visual metaphor",
    "balanced triptych-like arrangement without borders",
    "dynamic spiral composition with a quiet central pause",
)

MATERIALS = (
    "matte paper, translucent acrylic, and brushed aluminum",
    "cut paper, linen fabric, and soft ceramic",
    "frosted glass, polished stone, and subtle chrome",
    "ink, embossed paper, and fine-grain photographic texture",
    "recycled card, colored acetate, and painted wood",
    "silk, glass, and anodized metal",
    "concrete, vellum, and soft rubber",
    "glazed ceramic, cotton paper, and warm wood",
)

CATEGORY_DIRECTION = {
    "typography": "abstract letterform-inspired sculptures and rhythm, but no readable characters",
    "layout": "modular spatial relationships, alignment, hierarchy, and intentional negative space",
    "color": "color-system swatches interpreted as physical objects and light, with disciplined contrast",
    "photo": "camera, light, shadow, framing, and observation expressed through a conceptual studio photograph",
    "brand": "identity, recognition, consistency, and signature forms expressed without logos",
    "process": "research, iteration, decisions, and transformation visualized as an elegant creative process",
    "career": "professional growth, craft, confidence, and progression expressed through a refined visual metaphor",
    "ai-tech": "human creativity collaborating with intelligent technology, sophisticated and non-cliché",
    "marketing": "audience attention, communication, and engagement expressed as a premium editorial concept",
}


def required_env(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        raise SystemExit(f"{name} is missing.")
    return value


def build_prompt(post: dict) -> str:
    post_id = int(post["id"])
    rng = random.Random(f"magnific-post-{post_id}")
    category = classify(str(post.get("text") or ""))
    palette = PALETTES[post_id % len(PALETTES)]
    composition = COMPOSITIONS[(post_id * 5) % len(COMPOSITIONS)]
    material = MATERIALS[(post_id * 7) % len(MATERIALS)]
    direction = CATEGORY_DIRECTION.get(category, CATEGORY_DIRECTION["marketing"])
    light = rng.choice((
        "soft directional morning light",
        "dramatic gallery lighting",
        "clean diffused daylight",
        "cinematic side light with controlled shadows",
        "high-key studio lighting with subtle depth",
    ))
    return (
        "Create a unique premium 4:5 editorial image for a professional graphic designer's "
        "Threads post. Interpret the Mongolian post concept visually; do not typeset or quote it.\n\n"
        f"Post concept:\n{str(post.get('text') or '').strip()}\n\n"
        f"Visual direction: {direction}. Use {composition}. Materials: {material}. "
        f"Color palette: {palette}. Lighting: {light}. "
        "Contemporary international design-award quality, sophisticated art direction, tactile detail, "
        "clean hierarchy, intentional whitespace, photorealistic editorial still life mixed with subtle "
        "graphic abstraction. Make this composition unmistakably different from a template or stock image. "
        f"Unique visual signature for post #{post_id}. "
        "ABSOLUTELY NO readable text, letters, numbers, logos, UI labels, watermarks, signatures, borders, "
        "mockup captions, or social-media icons. One finished image only."
    )


def request_json(method: str, url: str, *, headers: dict | None = None,
                 payload: dict | None = None, timeout: int = 90) -> dict:
    delay = 2
    for attempt in range(7):
        response = requests.request(method, url, headers=headers, json=payload, timeout=timeout)
        if response.status_code < 400:
            return response.json()
        if response.status_code not in {403, 429, 500, 502, 503, 504} or attempt == 6:
            detail = response.text.strip().replace("\n", " ")[:800]
            raise RuntimeError(f"Magnific HTTP {response.status_code}: {detail}")
        retry_after = response.headers.get("Retry-After", "").strip()
        wait = int(retry_after) if retry_after.isdigit() else delay
        time.sleep(min(wait, 60))
        delay = min(delay * 2, 60)
    raise RuntimeError("Magnific request retry loop exited unexpectedly.")


def generate_url(post: dict, api_headers: dict[str, str]) -> str:
    payload = {
        "prompt": build_prompt(post),
        "aspect_ratio": "4:5",
        "resolution": "1K",
        "use_google_search_tool": False,
    }
    created = request_json("POST", API_ROOT, headers=api_headers, payload=payload)
    data = created.get("data", {})
    task_id = str(data.get("task_id") or "")
    if not task_id:
        raise RuntimeError("Magnific did not return a task_id.")

    deadline = time.monotonic() + 900
    while time.monotonic() < deadline:
        status_response = request_json("GET", f"{API_ROOT}/{task_id}", headers=api_headers, timeout=45)
        status_data = status_response.get("data", {})
        status = str(status_data.get("status") or "").upper()
        if status == "COMPLETED":
            generated = status_data.get("generated") or []
            if not generated:
                raise RuntimeError("Magnific completed without an output URL.")
            return str(generated[0])
        if status in {"FAILED", "ERROR", "CANCELLED"}:
            raise RuntimeError(f"Magnific task ended with status {status}.")
        time.sleep(15)
    raise RuntimeError("Magnific task timed out after 15 minutes.")


def normalized_jpeg(url: str) -> tuple[bytes, str]:
    response = requests.get(url, timeout=120)
    response.raise_for_status()
    with Image.open(io.BytesIO(response.content)) as source:
        image = ImageOps.fit(source.convert("RGB"), OUTPUT_SIZE, method=Image.Resampling.LANCZOS)
        output = io.BytesIO()
        image.save(output, "JPEG", quality=94, optimize=True, progressive=True)
    data = output.getvalue()
    return data, hashlib.sha256(data).hexdigest()


def r2_client():
    import boto3

    return boto3.client(
        "s3",
        endpoint_url=f"https://{required_env('R2_ACCOUNT_ID')}.r2.cloudflarestorage.com",
        aws_access_key_id=required_env("R2_ACCESS_KEY_ID"),
        aws_secret_access_key=required_env("R2_SECRET_ACCESS_KEY"),
        region_name="auto",
    )


def process_post(post: dict, *, api_headers: dict[str, str], client,
                 bucket: str, public_base: str, run_token: str) -> dict:
    post_id = int(post["id"])
    generated_url = generate_url(post, api_headers)
    image, digest = normalized_jpeg(generated_url)
    key = f"threads/posts/magnific-generated/post-{post_id:03d}-{run_token}.jpg"
    client.put_object(
        Bucket=bucket,
        Key=key,
        Body=image,
        ContentType="image/jpeg",
        CacheControl="public,max-age=31536000,immutable",
    )
    public_url = f"{public_base.rstrip('/')}/{key}"
    check = requests.head(public_url, allow_redirects=True, timeout=45)
    check.raise_for_status()
    return {"id": post_id, "url": public_url, "sha256": digest}


def select_targets(queue: list[dict], scope: str, limit: int) -> list[dict]:
    targets = [
        post for post in queue
        if str(post.get("status") or "pending").lower() != "posted"
        and "/magnific-generated/" not in str(post.get("image_url") or "")
    ]
    targets.sort(key=lambda post: int(post.get("id") or 0))
    if scope == "pilot":
        return targets[:limit]
    return targets


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scope", choices=("pilot", "all"), default="pilot")
    parser.add_argument("--limit", type=int, default=10)
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--run-token", default=str(int(time.time())))
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--manifest", type=Path, default=Path("magnific-batch-manifest.json"))
    args = parser.parse_args()

    queue = load_queue(QUEUE_PATH)
    targets = select_targets(queue, args.scope, max(1, args.limit))
    print(f"Magnific targets: {len(targets)}")
    if not targets:
        args.manifest.write_text("[]\n", encoding="utf-8")
        return

    if args.dry_run:
        for post in targets[:3]:
            print(f"\n--- Post {post['id']} prompt ---\n{build_prompt(post)}")
        return

    api_headers = {
        "x-magnific-api-key": required_env("MAGNIFIC_API_KEY"),
        "Content-Type": "application/json",
    }
    bucket = required_env("R2_BUCKET_NAME")
    public_base = required_env("R2_PUBLIC_BASE_URL")
    client = r2_client()
    results: list[dict] = []
    failures: list[dict] = []
    digests: set[str] = set()
    lock = threading.Lock()

    with ThreadPoolExecutor(max_workers=max(1, min(args.workers, 4))) as executor:
        futures = {
            executor.submit(
                process_post,
                post,
                api_headers=api_headers,
                client=client,
                bucket=bucket,
                public_base=public_base,
                run_token=args.run_token,
            ): int(post["id"])
            for post in targets
        }
        for future in as_completed(futures):
            post_id = futures[future]
            try:
                result = future.result()
                with lock:
                    if result["sha256"] in digests:
                        raise RuntimeError("Duplicate generated image detected.")
                    digests.add(result["sha256"])
                    results.append(result)
                print(f"Generated post {post_id}: {result['url']}")
            except Exception as exc:
                failures.append({"id": post_id, "error": str(exc)})
                print(f"::error title=Magnific post {post_id}::{exc}")

    by_id = {int(post["id"]): post for post in queue if post.get("id")}
    for result in results:
        post = by_id[result["id"]]
        post["image_url"] = result["url"]
        post["status"] = "pending"
        for key in ("error", "posted_at", "threads_id"):
            post.pop(key, None)
    save_queue(QUEUE_PATH, queue)
    sheet_cells = sync_google_sheet(queue) if results else 0

    manifest = {
        "requested": len(targets),
        "generated": sorted(results, key=lambda item: item["id"]),
        "failures": sorted(failures, key=lambda item: item["id"]),
        "sheet_cells": sheet_cells,
    }
    args.manifest.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Magnific complete: {len(results)} generated, {len(failures)} failed, {sheet_cells} Sheet cells.")
    if not results and failures:
        raise SystemExit("No images were generated successfully.")


if __name__ == "__main__":
    main()
