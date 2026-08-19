#!/usr/bin/env python3
"""Validate Magnific API access or upscale one queued post image."""

from __future__ import annotations

import argparse
import base64
import io
import json
import os
import time
from pathlib import Path

import requests
from PIL import Image


BASE = Path(__file__).resolve().parent
QUEUE_PATH = BASE / "queue.json"
API_ROOT = "https://api.magnific.com/v1/ai/image-upscaler-precision"


def api_key() -> str:
    value = os.environ.get("MAGNIFIC_API_KEY", "").strip()
    if not value:
        raise SystemExit("MAGNIFIC_API_KEY is missing.")
    return value


def headers() -> dict[str, str]:
    return {
        "x-magnific-api-key": api_key(),
        "Content-Type": "application/json",
    }


def check_connection() -> None:
    response = requests.get(API_ROOT, headers=headers(), timeout=45)
    response.raise_for_status()
    payload = response.json()
    if "data" not in payload:
        raise SystemExit("Magnific API returned an unexpected response.")
    print("Magnific API authentication: OK")


def queued_post(post_id: int) -> dict:
    queue = json.loads(QUEUE_PATH.read_text(encoding="utf-8"))
    post = next((item for item in queue if int(item.get("id") or 0) == post_id), None)
    if post is None:
        raise SystemExit(f"Post ID {post_id} not found.")
    image_url = str(post.get("image_url") or "").strip()
    if not image_url.startswith("https://"):
        raise SystemExit(f"Post ID {post_id} has no public HTTPS image URL.")
    return post


def image_as_base64(url: str) -> str:
    response = requests.get(url, timeout=90)
    response.raise_for_status()
    if len(response.content) > 20 * 1024 * 1024:
        raise SystemExit("Input image exceeds the 20 MiB workflow limit.")
    return base64.b64encode(response.content).decode("ascii")


def submit(image: str) -> str:
    payload = {
        "image": image,
        "sharpen": int(os.environ.get("MAGNIFIC_SHARPEN", "35")),
        "smart_grain": int(os.environ.get("MAGNIFIC_SMART_GRAIN", "4")),
        "ultra_detail": int(os.environ.get("MAGNIFIC_ULTRA_DETAIL", "20")),
        "filter_nsfw": True,
    }
    response = requests.post(API_ROOT, headers=headers(), json=payload, timeout=90)
    response.raise_for_status()
    data = response.json().get("data", {})
    task_id = str(data.get("task_id") or "")
    if not task_id:
        raise SystemExit("Magnific did not return a task_id.")
    print(f"Magnific task created: {task_id}")
    return task_id


def wait_for_result(task_id: str, timeout_seconds: int = 900) -> str:
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        response = requests.get(f"{API_ROOT}/{task_id}", headers=headers(), timeout=45)
        response.raise_for_status()
        data = response.json().get("data", {})
        status = str(data.get("status") or "").upper()
        print(f"Magnific task {task_id}: {status}")
        if status == "COMPLETED":
            generated = data.get("generated") or []
            if not generated:
                raise SystemExit("Magnific completed without an output URL.")
            return str(generated[0])
        if status in {"FAILED", "ERROR", "CANCELLED"}:
            raise SystemExit(f"Magnific task ended with status {status}.")
        time.sleep(10)
    raise SystemExit("Magnific task timed out after 15 minutes.")


def save_as_jpeg(url: str, output: Path) -> None:
    response = requests.get(url, timeout=120)
    response.raise_for_status()
    with Image.open(io.BytesIO(response.content)) as source:
        image = source.convert("RGB")
        output.parent.mkdir(parents=True, exist_ok=True)
        image.save(output, "JPEG", quality=95, optimize=True)
    print(f"Magnific output saved: {output}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("check", help="validate the API key without creating a task")
    upscale = sub.add_parser("upscale", help="upscale one queued post image")
    upscale.add_argument("--id", type=int, required=True)
    upscale.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    if args.command == "check":
        check_connection()
        return

    post = queued_post(args.id)
    encoded = image_as_base64(str(post["image_url"]))
    task_id = submit(encoded)
    result_url = wait_for_result(task_id)
    save_as_jpeg(result_url, args.output)


if __name__ == "__main__":
    main()
