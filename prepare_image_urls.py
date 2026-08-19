#!/usr/bin/env python3
"""Assign a matching R2 image to every unpublished Threads post.

The script is intentionally deterministic: the same post ID always receives the
same visual variant.  It updates queue.json first, then mirrors image URLs and
statuses to the configured Google Sheet when service-account credentials exist.
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from urllib.parse import quote


BASE = Path(__file__).resolve().parent
DEFAULT_QUEUE = BASE / "queue.json"
VALID_STATUSES = {"pending", "hold", "posted", "failed", "skipped"}

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
    with path.open(encoding="utf-8") as handle:
        data = json.load(handle)
    if not isinstance(data, list):
        raise SystemExit(f"{path} нь JSON жагсаалт биш байна.")
    return data


def save_queue(path: Path, queue: list[dict]) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(queue, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)


def assign_images(queue: list[dict], base_url: str, force: bool = False) -> tuple[int, int]:
    assigned = activated = 0
    for post in queue:
        item_id = int(post.get("id") or 0)
        status = str(post.get("status") or "pending").lower()
        if item_id <= 1 or status == "posted":
            continue
        if status not in VALID_STATUSES:
            post["status"] = "pending"
        if force or not post.get("image_url"):
            post["image_url"] = public_url(base_url, item_id)
            assigned += 1
        if post.get("status") == "hold" and post.get("image_url"):
            post["status"] = "pending"
            post.pop("note", None)
            activated += 1
    return assigned, activated


def sync_google_sheet(queue: list[dict]) -> int:
    """Mirror image URL and status to columns discovered from Sheet headers."""
    raw_credentials = os.environ.get("GOOGLE_SERVICE_ACCOUNT_JSON", "").strip()
    sheet_id = os.environ.get("THREADS_SHEET_ID", "").strip()
    if not raw_credentials or not sheet_id:
        print("Sheets sync skipped: GOOGLE_SERVICE_ACCOUNT_JSON or THREADS_SHEET_ID is missing.")
        return 0

    try:
        from google.auth.transport.requests import AuthorizedSession
        from google.oauth2 import service_account
    except ImportError as exc:
        raise SystemExit("google-auth is required; install requirements.txt first.") from exc

    info = json.loads(raw_credentials)
    credentials = service_account.Credentials.from_service_account_info(
        info,
        scopes=("https://www.googleapis.com/auth/spreadsheets",),
    )
    session = AuthorizedSession(credentials)
    api_root = f"https://sheets.googleapis.com/v4/spreadsheets/{sheet_id}"

    metadata = session.get(
        api_root,
        params={"fields": "sheets.properties(sheetId,title,index)"},
        timeout=45,
    )
    metadata.raise_for_status()
    sheets = [item.get("properties", {}) for item in metadata.json().get("sheets", [])]
    if not sheets:
        raise SystemExit("Google Sheet has no worksheets.")

    gid = os.environ.get("THREADS_SHEET_GID", "").strip()
    selected = next((item for item in sheets if gid and str(item.get("sheetId")) == gid), None)
    if selected is None:
        selected = min(sheets, key=lambda item: item.get("index", 0))
    title = selected["title"]
    escaped = title.replace("'", "''")

    response = session.get(
        f"{api_root}/values/'{escaped}'!A:Z",
        params={"majorDimension": "ROWS", "valueRenderOption": "FORMATTED_VALUE"},
        timeout=45,
    )
    response.raise_for_status()
    rows = response.json().get("values", [])
    if not rows:
        raise SystemExit("Google Sheet is empty.")

    headers = [str(value).strip().casefold() for value in rows[0]]

    def find_header(*names: str) -> int:
        accepted = {name.casefold() for name in names}
        try:
            return next(index for index, value in enumerate(headers) if value in accepted)
        except StopIteration as exc:
            raise SystemExit(f"Missing Google Sheet column: {names[0]}") from exc

    id_col = find_header("id", "дугаар")
    image_col = find_header("зургийн_холбоос", "зургийн холбоос", "image_url", "зураг")
    status_col = find_header("төлөв", "status")

    by_id = {int(post["id"]): post for post in queue if post.get("id")}
    updates = []

    def column_name(index: int) -> str:
        result = ""
        index += 1
        while index:
            index, remainder = divmod(index - 1, 26)
            result = chr(65 + remainder) + result
        return result

    image_letter = column_name(image_col)
    status_letter = column_name(status_col)
    for row_number, row in enumerate(rows[1:], start=2):
        if id_col >= len(row):
            continue
        try:
            item_id = int(float(str(row[id_col]).strip()))
        except (TypeError, ValueError):
            continue
        post = by_id.get(item_id)
        if not post:
            continue
        desired_url = str(post.get("image_url") or "")
        desired_status = str(post.get("status") or "pending")
        current_url = str(row[image_col]).strip() if image_col < len(row) else ""
        current_status = str(row[status_col]).strip().lower() if status_col < len(row) else ""
        if current_url != desired_url:
            updates.append({
                "range": f"'{escaped}'!{image_letter}{row_number}",
                "values": [[desired_url]],
            })
        if current_status != desired_status:
            updates.append({
                "range": f"'{escaped}'!{status_letter}{row_number}",
                "values": [[desired_status]],
            })

    if updates:
        result = session.post(
            f"{api_root}/values:batchUpdate",
            json={"valueInputOption": "RAW", "data": updates},
            timeout=45,
        )
        result.raise_for_status()
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
    save_queue(args.queue, queue)
    sheet_updates = 0 if args.no_sheet else sync_google_sheet(queue)
    print(
        f"Image assignment complete: {assigned} URLs assigned, "
        f"{activated} held posts activated, {sheet_updates} Sheet cells updated."
    )


if __name__ == "__main__":
    main()
