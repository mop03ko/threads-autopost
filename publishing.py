"""Single publishing path; claims are persisted before any Threads side effect."""
from __future__ import annotations

import copy
import os
import time
import uuid
from datetime import datetime, timedelta
from urllib.parse import urlparse

from queue_store import remote_store
from movie_posters import validate_movie_poster

LOCKED = {"posted", "processing", "needs_review"}
EDITABLE = ("scheduled_at", "text", "image_url")


def merge_snapshot(queue, rows, stamp):
    """Merge a fully validated snapshot; never reset terminal states via stale Sheets."""
    previous = {p["id"]: p for p in queue}
    merged = []
    for row in rows:
        old = previous.get(row["id"])
        if old and old.get("status") in LOCKED:
            merged.append(copy.deepcopy(old))
            continue
        post = copy.deepcopy(old) if old else {}
        post.update({k: row[k] for k in ("id", *EDITABLE, "status")})
        # A stale pending cell must not requeue failed/skipped posts every run.
        # Operators can explicitly retry these IDs with --id after inspection.
        if old and old.get("status") in {"failed", "skipped"}:
            post["status"] = old["status"]
        post["synced_at"] = stamp
        merged.append(post)
    present = {p["id"] for p in merged}
    for old in queue:
        if old["id"] in present:
            continue
        post = copy.deepcopy(old)
        if post.get("status") == "pending":
            post["status"] = "hold"
            post["note"] = "Sheet-ээс хасагдсан; автоматаар нийтлэхгүй."
        merged.append(post)
    return sorted(merged, key=lambda p: p["scheduled_at"])


def select_posts(queue, current, runtime, only_ids=(), force=False):
    today = current.strftime("%Y-%m-%d")
    used = sum(
        1 for p in queue if (
            p.get("status") == "posted" and str(p.get("posted_at", "")).startswith(today)
        ) or (
            p.get("status") in {"processing", "needs_review"}
            and str(p.get("attempted_at", p.get("processing_at", ""))).startswith(today)
        )
    )
    budget = max(0, min(runtime.MAX_POSTS_PER_RUN, runtime.MAX_POSTS_PER_DAY - used))
    selected, stale = [], []
    requested = set(only_ids)
    if requested - {p["id"] for p in queue}:
        raise RuntimeError("Нийтлэхээр сонгосон ID ээлжинд олдсонгүй.")
    for p in queue:
        if requested and p["id"] not in requested:
            continue
        if p.get("status") in LOCKED:
            continue
        if p.get("status") != "pending" and not (requested and p.get("status") in {"hold", "failed", "skipped"}):
            continue
        when = runtime.parse_local(p["scheduled_at"])
        if not requested and when > current:
            continue
        if not requested and not force and current - when > timedelta(minutes=runtime.LATE_GRACE_MIN):
            stale.append(p)
            continue
        selected.append(p)
    selected.sort(key=lambda p: p["scheduled_at"])
    return selected[:budget], stale


def validate_post(post, current, runtime):
    validate_movie_poster(post)
    text = post.get("text", "")
    if not isinstance(text, str) or not text.strip() or len(text) > runtime.MAX_CHARS:
        raise RuntimeError(f"Post {post['id']}: бичвэр хоосон эсвэл {runtime.MAX_CHARS}-аас урт.")
    if post.get("image_url"):
        url = urlparse(post["image_url"])
        if url.scheme != "https" or not url.netloc:
            raise RuntimeError(f"Post {post['id']}: зургийн HTTPS холбоос буруу.")
    try:
        synced = datetime.fromisoformat(post["synced_at"])
        age = (current - synced).total_seconds()
    except (KeyError, ValueError, TypeError) as exc:
        raise RuntimeError("Шинэ Sheets синк шаардлагатай: run --sync ашиглана уу.") from exc
    if age < -60 or age > int(os.environ.get("THREADS_SYNC_MAX_AGE", "1800")):
        raise RuntimeError("Sheets синк хуучирсан; нийтлэл түр зогслоо.")


def run(args, runtime):
    runtime.load_dotenv()
    live = bool(args.live)
    if not live:
        queue = runtime.load_json(runtime.QUEUE_FILE, [])
        if getattr(args, "sync", False):
            queue = merge_snapshot(queue, runtime.fetch_sheet_rows(), runtime.now().isoformat())
        selected, stale = select_posts(queue, runtime.now(), runtime, getattr(args, "id", None) or (), bool(args.force))
        for post in selected:
            runtime.log.info("[ТУРШИЛТ] id=%s, %s, %d тэмдэгт", post["id"], post["scheduled_at"], len(post["text"]))
        runtime.log.info("[ТУРШИЛТ] Нийтлэх %d, хоцорсон %d. Файл, төлөв өөрчлөгдөөгүй.", len(selected), len(stale))
        return

    store = remote_store()  # Fail closed: every live runner uses the same queue.
    if getattr(args, "sync", False):
        runtime.cmd_sync(args)
    tok = runtime.ensure_fresh_token()
    if not tok.get("user_id"):
        raise RuntimeError("Threads user_id тохируулаагүй байна.")
    current = runtime.now()
    claim_token = str(uuid.uuid4())

    def claim(queue):
        # Never automatically replay a request whose publish outcome is unknown.
        for post in queue:
            if post.get("status") != "processing":
                continue
            try:
                age = current - runtime.parse_local(post["processing_at"])
            except (KeyError, SystemExit, ValueError):
                age = timedelta(days=1)
            if age > timedelta(minutes=20):
                post["status"] = "needs_review"
                post["error"] = "Тасарсан ажиллагаа: Threads дээр нийтлэгдсэн эсэхийг гараар шалгана."
        selected, stale = select_posts(queue, current, runtime, getattr(args, "id", None) or (), bool(args.force))
        for post in selected:
            validate_post(post, current, runtime)
        for post in stale:
            post.update(status="skipped", note="Хоцорсон пост: дахин товлох эсвэл гараар сонгоно.")
        for post in selected:
            post.update(status="processing", processing_token=claim_token,
                        processing_at=current.strftime("%Y-%m-%d %H:%M"),
                        attempted_at=current.strftime("%Y-%m-%d %H:%M"), publication_phase="claimed")
            for field in ("error", "note", "container_id"):
                post.pop(field, None)
        return copy.deepcopy(selected)

    claims, queue = store.update(claim, "Threads post claimed [skip ci]")
    runtime.save_json(runtime.QUEUE_FILE, queue)

    def checkpoint(post, **fields):
        def mutate(queue):
            target = next((p for p in queue if p["id"] == post["id"]), None)
            if not target or target.get("processing_token") != claim_token or target.get("status") != "processing":
                raise RuntimeError("Нийтлэлийн түгжээ алдагдсан; ажиллагааг зогсоов.")
            target.update(fields)
        _, saved = store.update(mutate, f"Threads post checkpoint: {post['id']} [skip ci]")
        runtime.save_json(runtime.QUEUE_FILE, saved)

    failures = 0
    for post in claims:
        publish_started = False
        try:
            params = {"access_token": tok["access_token"], "text": post["text"],
                      "media_type": "IMAGE" if post.get("image_url") else "TEXT"}
            if post.get("image_url"):
                params["image_url"] = post["image_url"]
            container = runtime.api("POST", f"{runtime.GRAPH}/{tok['user_id']}/threads", data=params)
            container_id = container["id"]
            checkpoint(post, container_id=container_id, publication_phase="container_created")
            deadline = time.monotonic() + 90
            while True:
                status = runtime.api("GET", f"{runtime.GRAPH}/{container_id}", params={
                    "access_token": tok["access_token"], "fields": "id,status,error_message"})
                if status.get("status") == "FINISHED":
                    break
                if status.get("status") in {"ERROR", "EXPIRED"}:
                    raise RuntimeError("Threads контейнер бэлэн болсонгүй.")
                if time.monotonic() >= deadline:
                    raise RuntimeError("Threads контейнерийн хүлээх хугацаа дууслаа.")
                time.sleep(3)
            checkpoint(post, publication_phase="publishing")
            publish_started = True
            result = runtime.api("POST", f"{runtime.GRAPH}/{tok['user_id']}/threads_publish", data={
                "access_token": tok["access_token"], "creation_id": container_id})
            checkpoint(post, status="posted", threads_id=result["id"],
                       posted_at=runtime.now().strftime("%Y-%m-%d %H:%M"), publication_phase="published")
            runtime.log.info("Нийтэллээ: id %s -> %s", post["id"], result["id"])
        except Exception:
            failures += 1
            # Errors can embed credentials in URLs. Keep diagnostic state without
            # copying remote error strings or exception messages to logs/Sheets.
            state = "needs_review" if publish_started else "failed"
            checkpoint(post, status=state, error=(
                "Нийтлэлийн хариу тодорхойгүй; Threads дээр шалгана."
                if publish_started else "Нийтлэхээс өмнөх алхам амжилтгүй; тохиргоо, контейнерийг шалгана."))
            runtime.log.error("Post %s: %s", post["id"], state)
    if failures:
        raise RuntimeError(f"{failures} пост амжилтгүй. Дахин нийтлэхээс өмнө төлөвийг шалгана уу.")
