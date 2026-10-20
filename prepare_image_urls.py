#!/usr/bin/env python3
"""Assign a matching R2 image to every unpublished Threads post.

The script is intentionally deterministic: the same post ID always receives the
same visual variant.  It updates queue.json first, then mirrors image URLs and
only changed image URLs to the configured Google Sheet when service-account credentials exist.
"""

from __future__ import annotations

import argparse
import copy
import json
import os
from pathlib import Path
from urllib.parse import quote

from publishing import LOCKED
from movie_posters import is_movie_post
from queue_store import remote_store


BASE = Path(__file__).resolve().parent
DEFAULT_QUEUE = BASE / "queue.json"
_loaded_snapshots = {}

# The order matters only when two categories receive the same score.
KEYWORDS = {
    "typography": (
        "font", "typeface", "typography", "serif", "sans", "kerning",
        "leading", "tracking", "үсэг", "фонт", "бичгийн хэв", "мөр хооронд",
    ),
    "layout": (
        "layout", "grid", "alignment", "spacing", "whitespace", "hierarchy",
        "composition", "зохиомж", "байрлал", "тэнхлэг", "хоосон зай", "зай",
        "тор", "эрэмбэ", "харааны дараалал", "visual hierarchy", "cta",
    ),
    "color": (
        "color", "colour", "palette", "contrast", "өнгө", "палитр", "контраст",
        "primary", "secondary", "accent", "accessibility",
    ),
    "photo": (
        "photo", "video", "camera", "lens", "light", "shadow", "frame",
        "зураг", "видео", "камер", "линз", "гэрэл", "сүүдэр", "кадр",
        "reel", "motion",
    ),
    "brand": (
        "brand", "logo", "identity", "брэнд", "лого", "таних тэмдэг",
        "дүр төрх", "visual identity", "style guide", "system",
    ),
    "process": (
        "process", "brief", "feedback", "revision", "research", "reference",
        "concept", "prototype", "workflow", "процесс", "бриф", "засвар",
        "санал хүсэлт", "судалгаа", "лавлагаа", "концепц", "туршилт",
        "захиалагч", "шийдвэр", "асуудал",
    ),
    "career": (
        "career", "portfolio", "client", "price", "freelance", "interview",
        "burnout", "career", "портфолио", "карьер", "үйлчлүүлэгч", "үнэ",
        "ажлын санал", "ярилцлага", "фриланс", "туршлага", "чадвар",
    ),
    "ai-tech": (
        " ai ", "artificial intelligence", "midjourney", "chatgpt", "figma",
        "plugin", "automation", "tool", "technology", "хиймэл оюун", "автомат",
        "технолог", "программ", "апп", "код", "генератив",
    ),
    "marketing": (
        "marketing", "content", "social", "campaign", "audience", "engagement",
        "strategy", "threads", "instagram", "маркетинг", "контент", "сошиал",
        "кампанит", "үзэгч", "стратеги", "нийтлэл", "пост", "хандалт",
    ),
}


def classify(text: str) -> str:
    """Return the best visual category for a post."""
    haystack = f" {(text or '').casefold()} "
    scores = {
        category: sum(3 if len(keyword) > 8 else 1 for keyword in words if keyword in haystack)
        for category, words in KEYWORDS.items()
    }
    best = max(scores, key=scores.get)
    return best if scores[best] else "marketing"


def public_url(base_url: str, item_id: int) -> str:
    name = f"post-{item_id:03d}.jpg"
    return f"{base_url.rstrip('/')}/threads/posts/{quote(name)}"


def load_queue(path: Path) -> list[dict]:
    if os.environ.get("GITHUB_REPOSITORY") and os.environ.get("GITHUB_TOKEN"):
        data, _ = remote_store().read()
    else:
        with path.open(encoding="utf-8") as handle:
            data = json.load(handle)
    if not isinstance(data, list):
        raise SystemExit(f"{path} нь JSON жагсаалт биш байна.")
    _loaded_snapshots[str(path.resolve())] = copy.deepcopy(data)
    return data


def merge_image_changes(current, original, edited):
    """Apply image-only changes; preserve text, scheduling and publication state."""
    before = {p["id"]: p for p in original}
    changes = {p["id"]: p.get("image_url") for p in edited
               if p["id"] in before and p.get("image_url") != before[p["id"]].get("image_url")}
    changed = []
    for post in current:
        item_id = post["id"]
        if item_id not in changes or post.get("status") in LOCKED:
            continue
        # Another image job or a Sheet edit already won. Do not revert it.
        if post.get("image_url") != before[item_id].get("image_url"):
            continue
        if any(post.get(key) != before[item_id].get(key) for key in ('text', 'scheduled_at')):
            continue  # A reviewed illustration belongs to the reviewed text and date.
        post["image_url"] = changes[item_id]
        post.pop("synced_at", None)  # Require a fresh Sheet read before publishing.
        changed.append(item_id)
    return changed


def save_queue(path: Path, queue: list[dict]) -> list[int]:
    original = _loaded_snapshots.get(str(path.resolve()))
    if original is None:
        raise RuntimeError("Image queue must be loaded before saving.")

    def merge(current):
        return merge_image_changes(current, original, queue)

    if os.environ.get("GITHUB_REPOSITORY") and os.environ.get("GITHUB_TOKEN"):
        changed, saved = remote_store().update(merge, "Threads images updated [skip ci]")
    else:
        saved = copy.deepcopy(original)
        changed = merge(saved)
    queue[:] = saved
    _loaded_snapshots[str(path.resolve())] = copy.deepcopy(saved)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(saved, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)
    return changed


def assign_images(queue: list[dict], base_url: str, force: bool = False) -> tuple[int, int]:
    assigned = activated = 0
    for post in queue:
        item_id = int(post.get("id") or 0)
        status = str(post.get("status") or "pending").lower()
        if item_id <= 1 or status in LOCKED:
            continue
        if is_movie_post(post) or any(part in str(post.get('image_url') or '') for part in ('/editorial/', '/manual-post-', '/movie-posters/')):
            continue
        if force or not post.get("image_url"):
            post["image_url"] = public_url(base_url, item_id)
            assigned += 1
    return assigned, activated


def sync_google_sheet(queue: list[dict], only_ids: list[int], expected_posts=None,
                      expected_statuses=("pending",)) -> int:
    """Mirror only changed image URLs; never overwrite editorial/publication status."""
    if not only_ids:
        return 0
    from threads_post import (google_sheet_session, google_json, selected_sheet,
                              parse_sheet_rows, sheet_column_name)
    session = google_sheet_session()
    sheet_id = os.environ.get("THREADS_SHEET_ID", "").strip()
    if session is None or not sheet_id:
        print("Sheets image sync skipped: credentials or Sheet ID is missing.")
        return 0
    base = f"https://sheets.googleapis.com/v4/spreadsheets/{sheet_id}"
    title = selected_sheet(session, base)["title"].replace("'", "''")
    data = google_json(session, "GET", f"{base}/values:batchGet", params={
        "ranges": f"'{title}'!A1:Z10001", "majorDimension": "ROWS",
        "valueRenderOption": "FORMATTED_VALUE"})
    rows = (data.get("valueRanges") or [{}])[0].get("values", [])
    if not rows or len(rows) >= 10001:
        raise RuntimeError("Sheet хоосон эсвэл 10000 мөрийн хязгаараас давсан байна.")
    parsed = parse_sheet_rows(rows[0], [dict(zip(rows[0], row)) for row in rows[1:]])
    if expected_posts is not None:
        latest = {p['id']: p for p in parsed}
        expected = {p['id']: p for p in expected_posts}
        for item_id in only_ids:
            actual, prior = latest.get(item_id), expected.get(item_id)
            if not actual or not prior or actual.get('status') not in expected_statuses or any(
                    actual.get(key) != prior.get(key) for key in ('text','scheduled_at','image_url')):
                raise RuntimeError(f'Post {item_id}: Sheet changed since image review; no images written.')
    headers = [str(value).strip().lower() for value in rows[0]]
    id_col = next(i for i, name in enumerate(headers) if name in ("id", "дугаар"))
    image_names = ("зургийн_холбоос", "зургийн холбоос", "image_url", "зураг")
    try:
        image_col = next(i for i, name in enumerate(headers) if name in image_names)
    except StopIteration as exc:
        raise RuntimeError("Sheet зургийн багана олдсонгүй.") from exc
    ids = set(only_ids)
    by_id = {p["id"]: p for p in queue if p.get("id") in ids}
    updates = []
    for row_number, row in enumerate(rows[1:], start=2):
        if id_col >= len(row) or not str(row[id_col]).strip():
            continue
        from decimal import Decimal
        item_id = int(Decimal(str(row[id_col]).strip()))
        post = by_id.get(item_id)
        if not post:
            continue
        desired_url = str(post.get("image_url") or "")
        current_url = str(row[image_col]).strip() if image_col < len(row) else ""
        if current_url != desired_url:
            updates.append({"range": f"'{title}'!{sheet_column_name(image_col)}{row_number}",
                            "values": [[desired_url]]})
    if updates:
        google_json(session, "POST", f"{base}/values:batchUpdate",
                    json={"valueInputOption": "RAW", "data": updates})
    return len(updates)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--queue", type=Path, default=DEFAULT_QUEUE)
    parser.add_argument("--force", action="store_true", help="replace existing custom image URLs")
    parser.add_argument("--no-sheet", action="store_true", help="do not update Google Sheets")
    args = parser.parse_args()

    base_url = os.environ.get("R2_PUBLIC_BASE_URL", "").strip()
    if not base_url.startswith("https://"):
        raise SystemExit("R2_PUBLIC_BASE_URL must be a public https:// URL.")

    queue = load_queue(args.queue)
    assigned, activated = assign_images(queue, base_url, force=args.force)
    changed = save_queue(args.queue, queue)
    sheet_updates = 0 if args.no_sheet else sync_google_sheet(queue, changed)
    print(
        f"Image assignment complete: {assigned} URLs assigned, "
        f"{activated} held posts activated, {sheet_updates} Sheet cells updated."
    )


if __name__ == "__main__":
    main()

