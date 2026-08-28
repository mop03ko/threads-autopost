#!/usr/bin/env python3
"""
Threads автомат постлогч
=======================

Meta-гийн албан ёсны Threads API ашиглан товлосон цагт пост нийтэлдэг хэрэгсэл.

Тушаалууд:
    auth-url                Зөвшөөрлийн холбоос хэвлэнэ
    exchange --code CODE    Кодыг урт хугацааны токен болгон солино
    refresh                 Токеныг сунгана (60 хоног тутам)
    doctor                  Тохиргоо, токен, ээлжийг шалгана
    list                    Ээлжийн товч жагсаалт
    show [--next N]         Товлогдсон постын БҮТЭН бичвэр
    editor                  Ээлжийг засах вэб интерфейс
    sync                    Google Sheet-ээс ээлжийг татах
    sheet-status            Нийтэлсэн төлөвийг Google Sheet рүү буцааж бичих
    add --text "..." --at "2026-08-20 08:30" [--image URL]
    run [--live]            Хугацаа болсон постуудыг нийтэлнэ
        [--id N]            тодорхой постыг яг одоо нийтлэх
        [--force]           хоцорсон постыг ч нийтлэх

Анхдагчаар `run` нь ЗӨВХӨН ТУРШИЛТЫН горимд ажиллана. Бодитоор нийтлэхийн
тулд --live тугийг заавал өгнө.
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import time
from datetime import datetime, timedelta
import pathlib
from pathlib import Path

try:
    from zoneinfo import ZoneInfo
except ImportError:  # Python < 3.9
    print("Python 3.9 буюу түүнээс дээш хувилбар шаардлагатай.", file=sys.stderr)
    raise

try:
    import requests
except ImportError:
    print("requests сан суулгаагүй байна. Ажиллуулна уу: pip install requests", file=sys.stderr)
    sys.exit(1)


# ---------------------------------------------------------------- тохиргоо

BASE = Path(__file__).resolve().parent
TOKEN_FILE = BASE / "token.json"
QUEUE_FILE = BASE / "queue.json"
LOG_FILE = BASE / "threads-autopost.log"

TZ = ZoneInfo(os.environ.get("THREADS_TZ", "Asia/Ulaanbaatar"))

# Threads API эндпойнтууд. Meta эдгээрийг өөрчилвөл энд засна.
AUTH_URL = "https://threads.net/oauth/authorize"
TOKEN_URL = "https://graph.threads.net/oauth/access_token"
LONG_LIVED_URL = "https://graph.threads.net/access_token"
REFRESH_URL = "https://graph.threads.net/refresh_access_token"
GRAPH = "https://graph.threads.net/v1.0"

SCOPES = "threads_basic,threads_content_publish"

# Хамгаалалтын хязгаар
MAX_CHARS = 500              # Threads-ийн хатуу хязгаар
SOFT_MAX_CHARS = 200         # Үүнээс урт бол анхааруулна (оролцоо буурдаг)
MAX_POSTS_PER_RUN = 3        # Нэг ажиллагаанд нийтлэх дээд хэмжээ
MAX_POSTS_PER_DAY = 15       # Өөрийн хамгаалалт (API-ийн хязгаар 250)
CONTAINER_WAIT_SEC = 30      # Meta-гийн зөвлөсөн хүлээх хугацаа
LATE_GRACE_MIN = int(os.environ.get("THREADS_LATE_GRACE", "90"))  # хоцролтын хамгаалалт
REFRESH_BEFORE_DAYS = 10     # Дуусахаас хэдэн хоногийн өмнө автоматаар сунгах вэ

log = logging.getLogger("threads")


def setup_logging(verbose: bool = False) -> None:
    log.setLevel(logging.DEBUG if verbose else logging.INFO)
    fmt = logging.Formatter("%(asctime)s  %(levelname)-7s  %(message)s", "%Y-%m-%d %H:%M:%S")
    sh = logging.StreamHandler(sys.stdout)
    sh.setFormatter(fmt)
    log.addHandler(sh)
    fh = logging.FileHandler(LOG_FILE, encoding="utf-8")
    fh.setFormatter(fmt)
    log.addHandler(fh)


# ---------------------------------------------------------------- туслах

def load_json(path: Path, default):
    if not path.exists():
        return default
    with path.open(encoding="utf-8") as f:
        return json.load(f)


def save_json(path: Path, data) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    with tmp.open("w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    tmp.replace(path)


def env(name: str) -> str:
    val = os.environ.get(name, "").strip()
    if not val:
        raise SystemExit(
            f"Орчны хувьсагч {name} тохируулаагүй байна.\n"
            f".env файлаа шалгана уу (.env.example-г үлгэр болгоно)."
        )
    return val


def load_dotenv() -> None:
    """Гуравдагч сан ашиглахгүйгээр .env файлыг уншина."""
    path = BASE / ".env"
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, val = line.partition("=")
        os.environ.setdefault(key.strip(), val.strip().strip('"').strip("'"))


def now() -> datetime:
    return datetime.now(TZ)


def parse_local(text: str) -> datetime:
    """'2026-08-20 08:30' эсвэл ISO хэлбэрийг орон нутгийн цагаар уншина."""
    text = text.strip().replace("T", " ")
    for fmt in ("%Y-%m-%d %H:%M", "%Y-%m-%d %H:%M:%S"):
        try:
            return datetime.strptime(text, fmt).replace(tzinfo=TZ)
        except ValueError:
            continue
    raise SystemExit(f"Огноог таньж чадсангүй: {text!r}. Жишээ: 2026-08-20 08:30")


def api(method: str, url: str, **kwargs) -> dict:
    """HTTP дуудлага хийж, алдааг ойлгомжтой болгоно."""
    try:
        resp = requests.request(method, url, timeout=45, **kwargs)
    except requests.RequestException as exc:
        raise RuntimeError(f"Сүлжээний алдаа: {exc}") from exc

    try:
        data = resp.json()
    except ValueError:
        raise RuntimeError(f"JSON биш хариу ирлээ (HTTP {resp.status_code}): {resp.text[:300]}")

    if resp.status_code >= 400 or "error" in data:
        err = data.get("error", {})
        msg = err.get("message") or json.dumps(data, ensure_ascii=False)[:300]
        code = err.get("code")
        raise RuntimeError(f"API алдаа (HTTP {resp.status_code}, код {code}): {msg}")
    return data


# ---------------------------------------------------------------- токен

def read_token() -> dict:
    tok = load_json(TOKEN_FILE, None)
    if not tok:
        raise SystemExit(
            "token.json олдсонгүй. Эхлээд эрх авна уу:\n"
            "  1) python threads_post.py auth-url\n"
            "  2) холбоосыг браузерт нээж зөвшөөрнө\n"
            "  3) python threads_post.py exchange --code <КОД>"
        )
    return tok


def write_token(access_token: str, expires_in: int, user_id: str = "", username: str = "") -> dict:
    tok = load_json(TOKEN_FILE, {})
    tok["access_token"] = access_token
    tok["expires_at"] = (now() + timedelta(seconds=int(expires_in))).isoformat()
    if user_id:
        tok["user_id"] = user_id
    if username:
        tok["username"] = username
    save_json(TOKEN_FILE, tok)
    try:
        os.chmod(TOKEN_FILE, 0o600)
    except OSError:
        pass
    return tok


def token_days_left(tok: dict) -> float:
    exp = datetime.fromisoformat(tok["expires_at"])
    return (exp - now()).total_seconds() / 86400


def ensure_fresh_token() -> dict:
    """Токен дуусахад ойрхон бол автоматаар сунгана."""
    if not TOKEN_FILE.exists() and os.environ.get("THREADS_ACCESS_TOKEN", "").strip():
        log.info("token.json алга. Орчны хувьсагчаас үүсгэж байна.")
        cmd_token_import(None)
    tok = read_token()
    days = token_days_left(tok)
    if days <= 0:
        raise SystemExit(
            "Токен хугацаа нь дууссан байна. Дахин зөвшөөрөл авна уу:\n"
            "  python threads_post.py auth-url"
        )
    if days < REFRESH_BEFORE_DAYS:
        log.info("Токен %.1f хоногийн дараа дуусна. Сунгаж байна.", days)
        tok = cmd_refresh(quiet=True)
    return tok


# ---------------------------------------------------------------- тушаалууд

def cmd_auth_url(_args) -> None:
    load_dotenv()
    client_id = env("THREADS_APP_ID")
    redirect = env("THREADS_REDIRECT_URI")
    url = (
        f"{AUTH_URL}?client_id={client_id}"
        f"&redirect_uri={redirect}"
        f"&scope={SCOPES}"
        f"&response_type=code"
    )
    print("\nДараах холбоосыг браузертаа нээж, @mop03ko дансаараа зөвшөөрнө үү:\n")
    print(url)
    print(
        "\nЗөвшөөрсний дараа хаяг руу буцаана. URL дотор ?code=XXXX байна.\n"
        "Тэр кодыг (# тэмдгээс өмнөх хэсэг) хуулж дараах тушаалд өгнө:\n"
        "  python threads_post.py exchange --code <КОД>\n"
    )


def cmd_exchange(args) -> None:
    load_dotenv()
    code = args.code.split("#")[0].strip()
    log.info("Богино хугацааны токен авч байна.")
    short = api(
        "POST",
        TOKEN_URL,
        data={
            "client_id": env("THREADS_APP_ID"),
            "client_secret": env("THREADS_APP_SECRET"),
            "grant_type": "authorization_code",
            "redirect_uri": env("THREADS_REDIRECT_URI"),
            "code": code,
        },
    )
    short_token = short["access_token"]

    log.info("Урт хугацааны токен (60 хоног) болгон солиж байна.")
    long = api(
        "GET",
        LONG_LIVED_URL,
        params={
            "grant_type": "th_exchange_token",
            "client_secret": env("THREADS_APP_SECRET"),
            "access_token": short_token,
        },
    )

    me = api("GET", f"{GRAPH}/me", params={"fields": "id,username", "access_token": long["access_token"]})
    tok = write_token(long["access_token"], long.get("expires_in", 60 * 86400), me.get("id", ""), me.get("username", ""))
    log.info("Амжилттай. Данс: @%s (id %s)", tok.get("username"), tok.get("user_id"))
    log.info("Токен %.0f хоногийн дараа дуусна. `refresh` тушаалаар сунгана.", token_days_left(tok))


def cmd_refresh(_args=None, quiet: bool = False) -> dict:
    load_dotenv()
    tok = read_token()
    data = api("GET", REFRESH_URL, params={"grant_type": "th_refresh_token", "access_token": tok["access_token"]})
    tok = write_token(data["access_token"], data.get("expires_in", 60 * 86400))
    if not quiet:
        log.info("Токен сунгагдлаа. Үлдсэн хугацаа: %.0f хоног.", token_days_left(tok))
    return tok


def cmd_doctor(_args) -> None:
    load_dotenv()
    print("\n=== Тохиргооны шалгалт ===\n")

    ok = True
    for key in ("THREADS_APP_ID", "THREADS_APP_SECRET", "THREADS_REDIRECT_URI"):
        val = os.environ.get(key, "")
        mark = "OK " if val else "ДУТУУ"
        shown = (val[:6] + "…") if val and "SECRET" in key else (val or "-")
        print(f"  [{mark}] {key:24s} {shown}")
        ok = ok and bool(val)

    if TOKEN_FILE.exists():
        tok = read_token()
        days = token_days_left(tok)
        state = "OK " if days > 0 else "ДУУССАН"
        print(f"  [{state}] token.json              @{tok.get('username','?')}  ({days:.0f} хоног үлдсэн)")
        try:
            me = api("GET", f"{GRAPH}/me", params={"fields": "id,username", "access_token": tok["access_token"]})
            print(f"  [OK ] API холболт            @{me.get('username')} (id {me.get('id')})")
        except RuntimeError as exc:
            print(f"  [АЛДАА] API холболт          {exc}")
            ok = False
    else:
        print("  [ДУТУУ] token.json              эрх аваагүй байна")
        ok = False

    queue = load_json(QUEUE_FILE, [])
    pending = [p for p in queue if p.get("status") == "pending"]
    posted = [p for p in queue if p.get("status") == "posted"]
    failed = [p for p in queue if p.get("status") == "failed"]
    held = [p for p in queue if p.get("status") == "hold"]
    print(f"\n  Ээлж: нийт {len(queue)} | хүлээгдэж буй {len(pending)} | нийтэлсэн {len(posted)} "
          f"| алдаатай {len(failed)} | зураг хүлээж буй {len(held)}")
    if held:
        print(f"  САНАМЖ: {len(held)} пост зураг шаардаж байна. image_url бичээд status-ыг 'pending' болгоно.")

    long_posts = [p for p in pending if len(p.get("text", "")) > MAX_CHARS]
    if long_posts:
        print(f"  АНХААР: {len(long_posts)} пост {MAX_CHARS} тэмдэгтээс урт байна. Эдгээр нийтлэгдэхгүй.")

    nxt = sorted(pending, key=lambda p: p["scheduled_at"])[:1]
    if nxt:
        print(f"  Дараагийн пост: {nxt[0]['scheduled_at']}  ({len(nxt[0]['text'])} тэмдэгт)")

    print("\n  Ерөнхий байдал:", "БЭЛЭН" if ok else "ДУТУУ ЗҮЙЛ БАЙНА")
    print()


def cmd_list(_args) -> None:
    queue = load_json(QUEUE_FILE, [])
    if not queue:
        print("Ээлж хоосон байна.")
        return
    for p in sorted(queue, key=lambda x: x["scheduled_at"]):
        icon = {"pending": "·", "processing": "~", "posted": "+", "failed": "!", "skipped": "-", "hold": "o"}.get(p.get("status"), "?")
        first = p["text"].splitlines()[0][:58]
        img = " [зураг]" if p.get("image_url") else ""
        print(f"{icon} {p['scheduled_at']}  {len(p['text']):3d}т{img}  {first}")


SHEET_STATUSES = ("pending", "hold", "posted", "failed", "skipped")


def cmd_token_import(_args) -> None:
    """THREADS_ACCESS_TOKEN орчны хувьсагчаас token.json үүсгэнэ (CI-д зориулав)."""
    load_dotenv()
    raw = os.environ.get("THREADS_ACCESS_TOKEN", "").strip()
    if not raw:
        raise SystemExit("THREADS_ACCESS_TOKEN орчны хувьсагч хоосон байна.")

    me = api("GET", f"{GRAPH}/me", params={"fields": "id,username", "access_token": raw})

    # Хугацааг нь мэдэхийн тулд сунгахыг оролдоно. Токен 24 цагаас
    # залуу бол Meta татгалздаг тул алдааг зөөлөн барина.
    expires = 50 * 86400
    try:
        data = api("GET", REFRESH_URL, params={"grant_type": "th_refresh_token", "access_token": raw})
        raw = data["access_token"]
        expires = data.get("expires_in", expires)
        log.info("Токен сунгагдлаа.")
    except RuntimeError as exc:
        log.warning("Сунгаж чадсангүй (%s). 50 хоногийн болзошгүй хугацаагаар тэмдэглэв.", exc)

    tok = write_token(raw, expires, me.get("id", ""), me.get("username", ""))
    log.info("Токен бэлэн. Данс: @%s, үлдсэн %.0f хоног.",
             tok.get("username"), token_days_left(tok))


def cmd_token_export(args) -> None:
    """Одоогийн токеныг файлд бичнэ. Консол руу ХЭВЛЭХГҮЙ."""
    tok = read_token()
    out = pathlib.Path(args.out)
    out.write_text(tok["access_token"], encoding="utf-8")
    try:
        os.chmod(out, 0o600)
    except OSError:
        pass
    log.info("Токен %s файлд бичигдлээ (%.0f хоног үлдсэн).", out, token_days_left(tok))


def parse_sheet_datetime(raw: str) -> str:
    """Google Sheets-ээс ирэх олон янзын огнооны хэлбэрийг нэг стандартад оруулна.

    Google нь нүдийг огнооны төрөл болгон хувиргадаг тул экспортлохдоо
    хуудасны хэлний тохиргооноос хамаарч өөр өөр хэлбэрээр гаргадаг.
    """
    text = (raw or "").strip().replace("T", " ")
    if not text:
        raise ValueError("огноо хоосон байна")

    formats = (
        "%Y-%m-%d %H:%M", "%Y-%m-%d %H:%M:%S",
        "%m/%d/%Y %H:%M", "%m/%d/%Y %H:%M:%S",
        "%d/%m/%Y %H:%M", "%d/%m/%Y %H:%M:%S",
        "%Y.%m.%d %H:%M", "%Y/%m/%d %H:%M",
    )
    for fmt in formats:
        try:
            return datetime.strptime(text, fmt).strftime("%Y-%m-%d %H:%M")
        except ValueError:
            continue

    # 12 цагийн хэлбэр (8:30 PM)
    for fmt in ("%m/%d/%Y %I:%M:%S %p", "%m/%d/%Y %I:%M %p", "%Y-%m-%d %I:%M %p"):
        try:
            return datetime.strptime(text.upper().replace("AM", "AM").replace("PM", "PM"),
                                     fmt).strftime("%Y-%m-%d %H:%M")
        except ValueError:
            continue

    raise ValueError(f"огноог таньж чадсангүй: {raw!r}")


def sheet_csv_url() -> str:
    """.env доторх тохиргооноос CSV татах хаягийг бүрдүүлнэ."""
    url = os.environ.get("THREADS_SHEET_CSV_URL", "").strip()
    if url:
        return url
    sheet_id = os.environ.get("THREADS_SHEET_ID", "").strip()
    if not sheet_id:
        raise SystemExit(
            "Google Sheet тохируулаагүй байна.\n"
            ".env файлдаа дараах мөрийг нэмнэ:\n"
            "  THREADS_SHEET_ID=таны_sheet_id\n\n"
            "Sheet ID нь хаягийн /d/ ба /edit хоёрын хоорондох урт текст."
        )
    # gid-г ЗААВАЛ өгөхгүй. Импортлосон хуудсанд эхний хуудасны gid нь 0 биш
    # байх тохиолдол бий бөгөөд буруу gid өгвөл HTTP 400 буцаадаг.
    # gid-гүй бол Google эхний хуудсыг өөрөө сонгоно.
    gid = os.environ.get("THREADS_SHEET_GID", "").strip()
    base = f"https://docs.google.com/spreadsheets/d/{sheet_id}/export?format=csv"
    return f"{base}&gid={gid}" if gid else base


def fetch_sheet_rows() -> list:
    """Sheet-ээс мөрүүдийг татаж, толь бичгийн жагсаалт болгож буцаана."""
    import csv
    import io

    url = sheet_csv_url()
    log.info("Google Sheet-ээс татаж байна.")
    try:
        resp = requests.get(url, timeout=45, allow_redirects=True)
    except requests.RequestException as exc:
        raise SystemExit(f"Sheet татаж чадсангүй: {exc}")

    ctype = resp.headers.get("Content-Type", "").lower()
    looks_like_html = "text/html" in ctype
    if resp.status_code != 200 or looks_like_html:
        raise SystemExit(
            f"Sheet-ийг уншиж чадсангүй (HTTP {resp.status_code}).\n"
            "Хуудас нээлттэй эсэхийг шалгана уу: Share -> General access ->\n"
            "'Anyone with the link' -> Viewer."
        )

    resp.encoding = "utf-8"
    reader = csv.DictReader(io.StringIO(resp.text))
    if not reader.fieldnames:
        raise SystemExit("Sheet хоосон байна.")

    # баганын нэрийг уян хатан таних
    def pick(*names):
        for field in reader.fieldnames:
            key = (field or "").strip().lower()
            if key in names:
                return field
        return None

    col_id = pick("id", "дугаар")
    col_when = pick("огноо_цаг", "огноо цаг", "when", "scheduled_at")
    col_text = pick("бичвэр", "text", "пост")
    col_img = pick("зургийн_холбоос", "зургийн холбоос", "image_url", "зураг")
    col_status = pick("төлөв", "status")

    missing = [n for n, c in
               (("огноо_цаг", col_when), ("бичвэр", col_text)) if not c]
    if missing:
        raise SystemExit(
            f"Sheet-д дараах багана олдсонгүй: {', '.join(missing)}\n"
            f"Одоо байгаа баганууд: {', '.join(reader.fieldnames)}"
        )

    rows = []
    for line_no, row in enumerate(reader, start=2):
        text = (row.get(col_text) or "").strip()
        when_raw = (row.get(col_when) or "").strip()
        if not text and not when_raw:
            continue  # хоосон мөр
        if not text:
            log.warning("Мөр %d: бичвэр хоосон тул алгаслаа.", line_no)
            continue
        try:
            when = parse_sheet_datetime(when_raw)
        except ValueError as exc:
            log.warning("Мөр %d: %s. Алгаслаа.", line_no, exc)
            continue

        raw_id = (row.get(col_id) or "").strip() if col_id else ""
        try:
            item_id = int(float(raw_id)) if raw_id else 0
        except ValueError:
            item_id = 0

        status = (row.get(col_status) or "pending").strip().lower() if col_status else "pending"
        if status not in SHEET_STATUSES:
            status = "pending"

        rows.append({
            "id": item_id,
            "scheduled_at": when,
            "text": text,
            "image_url": ((row.get(col_img) or "").strip() or None) if col_img else None,
            "status": status,
            "_line": line_no,
        })
    return rows


def google_sheet_session():
    """Service account-аар Google Sheets API session үүсгэнэ."""
    raw = os.environ.get("GOOGLE_SERVICE_ACCOUNT_JSON", "").strip()
    if not raw:
        return None
    try:
        info = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise RuntimeError("GOOGLE_SERVICE_ACCOUNT_JSON зөв JSON биш байна.") from exc

    try:
        from google.auth.transport.requests import AuthorizedSession
        from google.oauth2 import service_account
    except ImportError as exc:
        raise RuntimeError(
            "google-auth сан суулгаагүй байна. requirements.txt-ээ дахин суулгана уу."
        ) from exc

    credentials = service_account.Credentials.from_service_account_info(
        info,
        scopes=("https://www.googleapis.com/auth/spreadsheets",),
    )
    log.info("Sheet бичих эрх: %s", info.get("client_email", "service account"))
    return AuthorizedSession(credentials)


def google_json(session, method: str, url: str, **kwargs) -> dict:
    """Google API дуудлагын алдааг нууц мэдээлэлгүйгээр ойлгомжтой болгоно."""
    try:
        resp = session.request(method, url, timeout=45, **kwargs)
    except requests.RequestException as exc:
        raise RuntimeError(f"Google Sheets сүлжээний алдаа: {exc}") from exc
    if resp.status_code >= 400:
        raise RuntimeError(
            f"Google Sheets API алдаа (HTTP {resp.status_code}): {resp.text[:300]}"
        )
    try:
        return resp.json()
    except ValueError as exc:
        raise RuntimeError("Google Sheets API JSON биш хариу буцаалаа.") from exc


def sheet_column_name(index: int) -> str:
    """Тэгээс эхэлсэн баганын индексийг A1 үсэг болгоно."""
    result = ""
    index += 1
    while index:
        index, remainder = divmod(index - 1, 26)
        result = chr(65 + remainder) + result
    return result


def update_google_sheet_status(queue: list) -> int:
    """queue.json дахь эцсийн төлөвүүдийг Sheet-ийн төлөв баганад бичнэ."""
    session = google_sheet_session()
    if session is None:
        log.warning(
            "GOOGLE_SERVICE_ACCOUNT_JSON тохируулаагүй тул Sheet төлөв шинэчлэхийг алгаслаа."
        )
        return 0

    sheet_id = os.environ.get("THREADS_SHEET_ID", "").strip()
    if not sheet_id:
        raise RuntimeError("THREADS_SHEET_ID тохируулаагүй байна.")

    base = f"https://sheets.googleapis.com/v4/spreadsheets/{sheet_id}"
    metadata = google_json(
        session,
        "GET",
        base,
        params={"fields": "sheets.properties(sheetId,title,index)"},
    )
    sheets = [s.get("properties", {}) for s in metadata.get("sheets", [])]
    if not sheets:
        raise RuntimeError("Google Sheet дотор хуудас олдсонгүй.")

    gid = os.environ.get("THREADS_SHEET_GID", "").strip()
    selected = next((s for s in sheets if gid and str(s.get("sheetId")) == gid), None)
    if selected is None:
        selected = min(sheets, key=lambda s: s.get("index", 0))
    title = selected["title"]
    quoted_title = title.replace("'", "''")
    table_range = f"'{quoted_title}'!A:Z"

    values = google_json(
        session,
        "GET",
        f"{base}/values:batchGet",
        params={
            "ranges": table_range,
            "majorDimension": "ROWS",
            "valueRenderOption": "FORMATTED_VALUE",
        },
    )
    rows = (values.get("valueRanges") or [{}])[0].get("values", [])
    if not rows:
        raise RuntimeError("Google Sheet хоосон байна.")

    headers = [str(value).strip().lower() for value in rows[0]]
    try:
        id_col = next(i for i, name in enumerate(headers) if name in ("id", "дугаар"))
        status_col = next(i for i, name in enumerate(headers) if name in ("төлөв", "status"))
    except StopIteration as exc:
        raise RuntimeError("Sheet-д id эсвэл төлөв багана олдсонгүй.") from exc

    final_by_id = {
        int(post["id"]): post["status"]
        for post in queue
        if post.get("id") and post.get("status") in ("posted", "failed", "skipped")
    }
    status_letter = sheet_column_name(status_col)
    updates = []
    for row_number, row in enumerate(rows[1:], start=2):
        if id_col >= len(row):
            continue
        try:
            item_id = int(float(str(row[id_col]).strip()))
        except (TypeError, ValueError):
            continue
        desired = final_by_id.get(item_id)
        if not desired:
            continue
        current = str(row[status_col]).strip().lower() if status_col < len(row) else ""
        if current == desired:
            continue
        updates.append({
            "range": f"'{quoted_title}'!{status_letter}{row_number}",
            "values": [[desired]],
        })

    if not updates:
        log.info("Google Sheet-ийн төлөв аль хэдийн шинэ байна.")
        return 0

    google_json(
        session,
        "POST",
        f"{base}/values:batchUpdate",
        json={"valueInputOption": "RAW", "data": updates},
    )
    log.info("Google Sheet дээр %d постын төлөв шинэчлэгдлээ.", len(updates))
    return len(updates)


def cmd_sheet_status(_args) -> None:
    """Нийтэлсэн/алдаатай/алгассан төлөвийг Google Sheet рүү буцааж бичнэ."""
    load_dotenv()
    update_google_sheet_status(load_json(QUEUE_FILE, []))


def cmd_sync(args) -> None:
    """Google Sheet-ийн агуулгыг локал ээлж рүү татна."""
    load_dotenv()
    rows = fetch_sheet_rows()
    local = load_json(QUEUE_FILE, [])
    by_id = {p.get("id"): p for p in local if p.get("id")}

    merged, added, updated, locked = [], 0, 0, 0
    next_id = max([p.get("id", 0) for p in local] + [r["id"] for r in rows] + [0]) + 1

    for row in rows:
        item_id = row["id"]
        if not item_id:
            item_id = next_id
            next_id += 1

        existing = by_id.get(item_id)

        # Нийтлэгдсэн/боловсруулж буй постыг Sheet-ээс дарж бичихгүй.
        # failed/skipped мөрийг Sheet дээр pending болгосон бол зассан агуулгаар
        # дахин оролдохыг зөвшөөрнө (жишээ нь эвдэрсэн image_url-г арилгах).
        if existing and (
            existing.get("status") in ("posted", "processing")
            or (
                existing.get("status") in ("failed", "skipped")
                and row["status"] != "pending"
            )
        ):
            merged.append(existing)
            locked += 1
            continue

        entry = {
            "id": item_id,
            "scheduled_at": row["scheduled_at"],
            "text": row["text"],
            "image_url": row["image_url"],
            "status": row["status"],
        }
        if existing:
            if any(existing.get(k) != entry[k] for k in
                   ("scheduled_at", "text", "image_url", "status")):
                updated += 1
        else:
            added += 1
        merged.append(entry)

    # Sheet-д байхгүй боловч нийтлэгдсэн постуудыг хадгална
    sheet_ids = {e["id"] for e in merged}
    for post in local:
        if post.get("id") not in sheet_ids and post.get("status") in ("posted", "failed", "skipped", "processing"):
            merged.append(post)
            locked += 1

    removed = len(local) - len([p for p in local if p.get("id") in sheet_ids]) - \
              len([p for p in local if p.get("id") not in sheet_ids
                   and p.get("status") in ("posted", "failed", "skipped", "processing")])

    if QUEUE_FILE.exists():
        QUEUE_FILE.with_suffix(".bak.json").write_text(
            QUEUE_FILE.read_text(encoding="utf-8"), encoding="utf-8")

    merged.sort(key=lambda p: p["scheduled_at"])
    save_json(QUEUE_FILE, merged)

    log.info("Sync дууслаа: нэмэгдсэн %d, шинэчлэгдсэн %d, хасагдсан %d, хамгаалагдсан %d",
             added, updated, max(0, removed), locked)

    too_long = [p for p in merged if p["status"] == "pending" and len(p["text"]) > MAX_CHARS]
    if too_long:
        log.warning("%d пост %d тэмдэгтээс урт байна. Эдгээр нийтлэгдэхгүй.",
                    len(too_long), MAX_CHARS)
    log.info("Ээлжинд нийт %d пост байна.", len(merged))


def cmd_editor(args) -> None:
    """Ээлжийг засах локал вэб интерфейс нээнэ (зөвхөн энэ компьютерээс хандана)."""
    import http.server
    import threading
    import webbrowser

    try:
        from editor_ui import HTML
    except ImportError:
        raise SystemExit("editor_ui.py файл олдсонгүй. Багцаа бүтнээр нь задалсан эсэхээ шалгана уу.")

    port = args.port

    class Handler(http.server.BaseHTTPRequestHandler):
        def _send(self, code, body, ctype="application/json; charset=utf-8"):
            data = body.encode("utf-8") if isinstance(body, str) else body
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(data)

        def do_GET(self):
            if self.path in ("/", "/index.html"):
                self._send(200, HTML, "text/html; charset=utf-8")
            elif self.path == "/api/queue":
                self._send(200, json.dumps(load_json(QUEUE_FILE, []), ensure_ascii=False))
            else:
                self._send(404, '{"error":"not found"}')

        def do_POST(self):
            if self.path != "/api/queue":
                self._send(404, '{"error":"not found"}')
                return
            try:
                length = int(self.headers.get("Content-Length", 0))
                if length > 5_000_000:
                    raise ValueError("хэт том өгөгдөл")
                incoming = json.loads(self.rfile.read(length).decode("utf-8"))
                if not isinstance(incoming, list):
                    raise ValueError("жагсаалт биш өгөгдөл ирлээ")

                cleaned = []
                for item in incoming:
                    text = str(item.get("text", "")).strip()
                    when = str(item.get("scheduled_at", "")).strip()[:16]
                    if not text or not when:
                        continue
                    parse_local(when)  # огноог шалгана
                    entry = {
                        "id": int(item.get("id") or len(cleaned) + 1),
                        "scheduled_at": when,
                        "text": text,
                        "image_url": (item.get("image_url") or None),
                        "status": item.get("status") if item.get("status") in
                                  ("pending", "hold", "posted", "failed", "skipped", "processing") else "pending",
                    }
                    for keep in ("posted_at", "threads_id", "error", "note", "processing_token", "processing_at"):
                        if item.get(keep):
                            entry[keep] = item[keep]
                    cleaned.append(entry)

                # нөөц хуулбар үлдээнэ
                if QUEUE_FILE.exists():
                    backup = QUEUE_FILE.with_suffix(".bak.json")
                    backup.write_text(QUEUE_FILE.read_text(encoding="utf-8"), encoding="utf-8")

                save_json(QUEUE_FILE, cleaned)
                log.info("Ээлж шинэчлэгдлээ: %d пост", len(cleaned))
                self._send(200, json.dumps({"ok": True, "count": len(cleaned)}))
            except (Exception, SystemExit) as exc:
                # parse_local нь SystemExit шиднэ. Түүнийг барихгүй бол
                # холболт таслагдаж, браузер алдааг харуулж чадахгүй.
                self._send(400, json.dumps({"error": str(exc)}, ensure_ascii=False))

        def log_message(self, *a):
            pass  # консолыг цэвэр байлгана

    server = http.server.ThreadingHTTPServer(("127.0.0.1", port), Handler)
    url = f"http://127.0.0.1:{port}/"
    print()
    print("  Засварлагч ажиллаж байна:", url)
    print("  Браузер автоматаар нээгдэнэ. Нээгдэхгүй бол дээрх хаягийг хуулж тавина.")
    print("  Дуусахдаа энэ цонхон дээр Ctrl+C дарна.")
    print()
    threading.Timer(0.6, lambda: webbrowser.open(url)).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n  Засварлагч хаагдлаа.")
        server.shutdown()


def cmd_show(args) -> None:
    """Товлогдсон постуудын БҮТЭН бичвэрийг харуулна (урьдчилан харах)."""
    queue = load_json(QUEUE_FILE, [])
    upcoming = [p for p in queue if p.get("status") in ("pending", "hold")]
    if not upcoming:
        print("Товлогдсон пост алга.")
        return

    upcoming.sort(key=lambda x: x["scheduled_at"])
    limit = args.next if args.next else len(upcoming)
    current = now()

    print(f"\n  Одоо: {current.strftime('%Y-%m-%d %H:%M')} ({TZ})\n")

    for p in upcoming[:limit]:
        when = parse_local(p["scheduled_at"])
        delta = when - current
        if delta.total_seconds() < 0:
            rel = "ХУГАЦАА НЬ ӨНГӨРСӨН"
        else:
            hrs = int(delta.total_seconds() // 3600)
            mins = int((delta.total_seconds() % 3600) // 60)
            rel = f"{hrs} цаг {mins} минутын дараа" if hrs else f"{mins} минутын дараа"

        state = "ЗУРАГ ХҮЛЭЭЖ БАЙНА" if p.get("status") == "hold" else "НИЙТЛЭГДЭНЭ"
        print("=" * 66)
        print(f"  id {p['id']}  |  {p['scheduled_at']}  |  {rel}")
        print(f"  {state}  |  {len(p['text'])} тэмдэгт")
        if p.get("image_url"):
            print(f"  Зураг: {p['image_url']}")
        elif p.get("status") == "hold":
            print(f"  Санамж: {p.get('note', 'зураг оруулах шаардлагатай')}")
        print("-" * 66)
        for line in p["text"].splitlines():
            print(f"  {line}")
        print()


def cmd_add(args) -> None:
    queue = load_json(QUEUE_FILE, [])
    when = parse_local(args.at)
    text = args.text.strip()
    if len(text) > MAX_CHARS:
        raise SystemExit(f"Бичвэр {len(text)} тэмдэгт байна. Хязгаар {MAX_CHARS}.")
    if len(text) > SOFT_MAX_CHARS:
        log.warning("Бичвэр %d тэмдэгт. %d-аас урт бол оролцоо буурдаг.", len(text), SOFT_MAX_CHARS)
    new_id = max([p.get("id", 0) for p in queue], default=0) + 1
    queue.append({
        "id": new_id,
        "scheduled_at": when.strftime("%Y-%m-%d %H:%M"),
        "text": text,
        "image_url": args.image or None,
        "status": "pending",
    })
    save_json(QUEUE_FILE, queue)
    log.info("Нэмэгдлээ (id %d): %s", new_id, when.strftime("%Y-%m-%d %H:%M"))


def publish_one(user_id: str, token: str, post: dict, live: bool) -> str:
    """Нэг постыг нийтэлж, Threads дээрх ID-г буцаана."""
    text = post["text"]
    image_url = post.get("image_url")

    if not live:
        kind = "IMAGE" if image_url else "TEXT"
        log.info("[ТУРШИЛТ] %s пост нийтлэх байсан (%d тэмдэгт): %s",
                 kind, len(text), text.splitlines()[0][:60])
        return "dry-run"

    params = {"access_token": token, "text": text}
    if image_url:
        params["media_type"] = "IMAGE"
        params["image_url"] = image_url
    else:
        params["media_type"] = "TEXT"

    container = api("POST", f"{GRAPH}/{user_id}/threads", data=params)
    creation_id = container["id"]
    log.info("Контейнер үүслээ: %s. %d секунд хүлээж байна.", creation_id, CONTAINER_WAIT_SEC)
    time.sleep(CONTAINER_WAIT_SEC)

    result = api(
        "POST",
        f"{GRAPH}/{user_id}/threads_publish",
        data={"access_token": token, "creation_id": creation_id},
    )
    return result["id"]


def cmd_run(args) -> None:
    load_dotenv()
    if getattr(args, "sync", False):
        try:
            cmd_sync(args)
        except SystemExit as exc:
            log.warning("Sync алгаслаа: %s", exc)
    live = bool(args.live)
    if not live:
        log.info("ТУРШИЛТЫН ГОРИМ. Бодитоор нийтлэхгүй. --live туг өгвөл нийтэлнэ.")

    queue = load_json(QUEUE_FILE, [])
    if not queue:
        log.info("Ээлж хоосон байна.")
        return

    tok = ensure_fresh_token() if live else load_json(TOKEN_FILE, {"user_id": "TEST", "access_token": "TEST"})
    user_id = tok.get("user_id")
    if live and not user_id:
        raise SystemExit("token.json дотор user_id алга. `exchange` тушаалыг дахин ажиллуулна уу.")

    current = now()
    today = current.strftime("%Y-%m-%d")
    posted_today = sum(
        1 for p in queue
        if p.get("status") == "posted" and str(p.get("posted_at", "")).startswith(today)
    )
    if posted_today >= MAX_POSTS_PER_DAY:
        log.warning("Өнөөдөр аль хэдийн %d пост нийтэлсэн. Хязгаарт хүрсэн.", posted_today)
        return

    only_ids = set(getattr(args, "id", None) or [])
    force = bool(getattr(args, "force", False))

    if only_ids:
        # Тодорхой постыг хуваарь харгалзахгүй яг одоо нийтэлнэ
        due = []
        for p in queue:
            if p.get("id") not in only_ids:
                continue
            if p.get("status") == "posted":
                log.warning("id %s аль хэдийн нийтлэгдсэн тул алгаслаа.", p.get("id"))
                continue
            p["status"] = "pending"     # hold/skipped/failed байсныг сэргээнэ
            p.pop("note", None)
            p.pop("error", None)
            due.append(p)
        missing = only_ids - {p.get("id") for p in queue}
        for m in sorted(missing):
            log.warning("id %s ээлжинд олдсонгүй.", m)
        if not due:
            log.info("Нийтлэх пост олдсонгүй.")
            save_json(QUEUE_FILE, queue)
            return
        log.info("Гар аргаар нийтлэх: %d пост (хуваарь харгалзахгүй).", len(due))
    else:
        due = []
        for p in queue:
            if p.get("status") != "pending":
                continue
            when = parse_local(p["scheduled_at"])
            if when > current:
                continue
            if not force and current - when > timedelta(minutes=LATE_GRACE_MIN):
                p["status"] = "skipped"
                p["note"] = f"{LATE_GRACE_MIN} минутаас их хоцорсон тул алгассан"
                log.warning("Алгаслаа (хэт хоцорсон): %s", p["scheduled_at"])
                continue
            due.append(p)
        if force and due:
            log.info("--force: хоцролтын хамгаалалт түр идэвхгүй.")

    due.sort(key=lambda p: p["scheduled_at"])
    if not due:
        log.info("Хугацаа болсон пост алга.")
        save_json(QUEUE_FILE, queue)
        return

    budget = min(MAX_POSTS_PER_RUN, MAX_POSTS_PER_DAY - posted_today)
    if len(due) > budget:
        log.warning("%d пост хугацаа болсон ч энэ удаад зөвхөн %d-г нийтэлнэ.", len(due), budget)
        due = due[:budget]

    for p in due:
        text = p["text"]
        if len(text) > MAX_CHARS:
            p["status"] = "failed"
            p["error"] = f"{len(text)} тэмдэгт, хязгаар {MAX_CHARS}"
            log.error("Нийтлэхээс татгалзлаа (хэт урт): id %s", p.get("id"))
            continue
        try:
            post_id = publish_one(user_id, tok["access_token"], p, live)
            if live:
                p["status"] = "posted"
                p["posted_at"] = now().strftime("%Y-%m-%d %H:%M")
                p["threads_id"] = post_id
                log.info("Нийтэллээ: id %s -> %s", p.get("id"), post_id)
        except RuntimeError as exc:
            p["status"] = "failed"
            p["error"] = str(exc)
            log.error("Амжилтгүй: id %s | %s", p.get("id"), exc)

    save_json(QUEUE_FILE, queue)
    remaining = sum(1 for p in queue if p.get("status") == "pending")
    log.info("Дууслаа. Ээлжинд %d пост үлдлээ.", remaining)


# ---------------------------------------------------------------- эхлэл

def main() -> None:
    ap = argparse.ArgumentParser(description="Threads автомат постлогч")
    ap.add_argument("-v", "--verbose", action="store_true", help="дэлгэрэнгүй бүртгэл")
    sub = ap.add_subparsers(dest="cmd", required=True)

    sub.add_parser("auth-url", help="зөвшөөрлийн холбоос хэвлэх")

    ex = sub.add_parser("exchange", help="кодыг токен болгон солих")
    ex.add_argument("--code", required=True)

    sub.add_parser("refresh", help="токен сунгах")
    sub.add_parser("doctor", help="тохиргоог шалгах")
    sub.add_parser("list", help="ээлжийг харуулах")

    ed = sub.add_parser("editor", help="ээлжийг засах вэб интерфейс нээх")
    ed.add_argument("--port", type=int, default=8765)

    sw = sub.add_parser("show", help="товлогдсон постын бүтэн бичвэрийг харах")
    sw.add_argument("--next", type=int, default=None, help="зөвхөн дараагийн N постыг харуулах")

    ad = sub.add_parser("add", help="ээлжид пост нэмэх")
    ad.add_argument("--text", required=True)
    ad.add_argument("--at", required=True, help='жишээ: "2026-08-20 08:30"')
    ad.add_argument("--image", default=None, help="нээлттэй зургийн URL")

    sub.add_parser("sync", help="Google Sheet-ээс ээлжийг татах")
    sub.add_parser("sheet-status", help="Эцсийн төлөвүүдийг Google Sheet рүү бичих")
    sub.add_parser("token-import", help="THREADS_ACCESS_TOKEN-оос token.json үүсгэх")

    te = sub.add_parser("token-export", help="токеныг файлд бичих (CI)")
    te.add_argument("--out", default="token.txt")

    rn = sub.add_parser("run", help="хугацаа болсон постуудыг нийтлэх")
    rn.add_argument("--live", action="store_true", help="бодитоор нийтлэх")
    rn.add_argument("--sync", action="store_true", help="эхлээд Google Sheet-ээс татах")
    rn.add_argument("--id", type=int, nargs="+", metavar="N",
                    help="тодорхой постыг хуваарь харгалзахгүй яг одоо нийтлэх")
    rn.add_argument("--force", action="store_true",
                    help="хоцорсон постыг ч нийтлэх (90 минутын хамгаалалтыг үл тоох)")

    args = ap.parse_args()
    setup_logging(args.verbose)

    handlers = {
        "auth-url": cmd_auth_url,
        "exchange": cmd_exchange,
        "refresh": cmd_refresh,
        "doctor": cmd_doctor,
        "list": cmd_list,
        "show": cmd_show,
        "editor": cmd_editor,
        "sync": cmd_sync,
        "sheet-status": cmd_sheet_status,
        "token-import": cmd_token_import,
        "token-export": cmd_token_export,
        "add": cmd_add,
        "run": cmd_run,
    }
    try:
        handlers[args.cmd](args)
    except KeyboardInterrupt:
        log.warning("Тасаллаа.")
        sys.exit(130)


if __name__ == "__main__":
    main()
