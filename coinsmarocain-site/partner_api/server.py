#!/usr/bin/env python3
"""Coins Marocain — API partenaire (inscription, fiche, modération)."""
from __future__ import annotations

import json
import os
import re
import secrets
import threading
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

import media_unify
import media_upload

HOST = os.environ.get("CM_API_HOST", "127.0.0.1")
PORT = int(os.environ.get("CM_API_PORT", "8098"))
DATA_PATH = os.environ.get(
    "CM_DATA_PATH",
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "store.json"),
)
SEED_PATH = os.environ.get(
    "CM_SEED_PATH",
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "seed.json"),
)
UPLOAD_DIR = os.environ.get(
    "CM_UPLOAD_DIR",
    "/var/www/coinsmarocain/uploads/partners",
)
UPLOAD_URL = "/uploads/partners"

LOCK = threading.Lock()
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
MAX_PHOTO_B64 = 550_000
MAX_PHOTOS = 6
ROLES = {"merchant", "admin"}
QUARTIERS = [
    "Médina",
    "Guéliz",
    "Hivernage",
    "Palmeraie",
    "Route de l'Ourika",
    "Agafay",
]
QUARTIER_COORDS = {
    "Médina": (31.6258, -7.9891),
    "Guéliz": (31.6342, -8.0128),
    "Hivernage": (31.6215, -8.0085),
    "Palmeraie": (31.6680, -7.9730),
    "Route de l'Ourika": (31.5480, -7.9200),
    "Agafay": (31.4800, -8.1500),
}
CATEGORIES = [
    "resto",
    "hebergement",
    "bien-etre",
    "experiences",
    "evenements",
    "autre",
]
CAT_MAP = {
    "resto": "resto",
    "restaurant": "resto",
    "route_gourmande": "resto",
    "hebergement": "hebergement",
    "hébergement": "hebergement",
    "bien-etre": "bien-etre",
    "bien_etre": "bien-etre",
    "hammam": "bien-etre",
    "experiences": "experiences",
    "plein_air": "experiences",
    "plein-air": "experiences",
    "evenements": "evenements",
    "evenement": "evenements",
    "autre": "autre",
    "other": "autre",
}


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def empty_store() -> dict:
    return {"accounts": [], "events": [], "updated_at": now_iso()}


def _migrate(store: dict) -> dict:
    if os.path.exists(SEED_PATH):
        with open(SEED_PATH, encoding="utf-8") as fh:
            seed = json.load(fh)
        have = {a.get("id") for a in store.get("accounts") or []}
        for acc in seed.get("accounts") or []:
            if acc.get("id") not in have:
                store.setdefault("accounts", []).append(acc)
    return store


def load_store() -> dict:
    if not os.path.exists(DATA_PATH):
        os.makedirs(os.path.dirname(DATA_PATH), exist_ok=True)
        store = empty_store()
        if os.path.exists(SEED_PATH):
            with open(SEED_PATH, encoding="utf-8") as fh:
                seed = json.load(fh)
            store.update(seed)
            store["updated_at"] = now_iso()
        save_store(_migrate(store))
        return store
    with open(DATA_PATH, encoding="utf-8") as fh:
        data = json.load(fh)
    data.setdefault("accounts", [])
    data.setdefault("events", [])
    return _migrate(data)


def save_store(store: dict) -> None:
    os.makedirs(os.path.dirname(DATA_PATH), exist_ok=True)
    store["updated_at"] = now_iso()
    tmp = DATA_PATH + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(store, fh, ensure_ascii=False, indent=2)
    os.replace(tmp, DATA_PATH)


def find_account(store: dict, token: str | None = None, account_id: str | None = None):
    if token:
        for acc in store["accounts"]:
            if acc.get("token") == token:
                return acc
    if account_id:
        for acc in store["accounts"]:
            if acc.get("id") == account_id:
                return acc
    return None


def apply_quartier_coords(acc: dict) -> None:
    if acc.get("lat") not in (None, "") and acc.get("lng") not in (None, ""):
        return
    coords = QUARTIER_COORDS.get(acc.get("region") or "")
    if coords:
        acc["lat"], acc["lng"] = coords


def public_listing(acc: dict) -> dict:
    apply_quartier_coords(acc)
    return {
        "id": acc.get("id"),
        "name": acc.get("name"),
        "role": acc.get("role"),
        "status": acc.get("status"),
        "region": acc.get("region"),
        "category": acc.get("category"),
        "description": acc.get("description") or "",
        "address": acc.get("address") or "",
        "lat": acc.get("lat"),
        "lng": acc.get("lng"),
        "video_url": acc.get("video_url") or "",
        "photos": acc.get("photos") or [],
        **media_unify.listing_fields(acc),
        "services": acc.get("services") or [],
        "packages": acc.get("packages") or [],
        "featured": bool(acc.get("featured")),
        "stats": acc.get("stats") or {},
        "contact_public": {
            "phone": acc.get("phone") or "",
            "email": acc.get("email") or "",
        },
    }


def new_token(prefix: str) -> str:
    return f"{prefix}-{secrets.token_urlsafe(16)}"


def clean(value, limit=240) -> str:
    return str(value or "").strip()[:limit]


def portal_url(acc: dict) -> str:
    if acc.get("role") == "admin":
        return f"/espace/admin/?token={acc.get('token')}"
    return f"/espace/commercant/?token={acc.get('token')}"


def _num(value):
    try:
        if value in (None, ""):
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _offer(item) -> dict:
    if not isinstance(item, dict):
        return {"name": clean(item, 80), "price": "", "unit": ""}
    return {
        "name": clean(item.get("name"), 80),
        "price": clean(item.get("price"), 40),
        "unit": clean(item.get("unit") or item.get("description"), 120),
    }


def _norm_cat(value) -> str:
    return CAT_MAP.get(clean(value, 40).lower(), "autre")


class Handler(BaseHTTPRequestHandler):
    server_version = "CoinsMarocainPartnerAPI/1.0"

    def log_message(self, fmt, *args):
        print("[%s] %s" % (self.log_date_time_string(), fmt % args))

    def _cors(self):
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, PUT, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization")

    def _json(self, payload, status=200):
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self._cors()
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _body(self) -> dict:
        length = int(self.headers.get("Content-Length") or 0)
        if length <= 0:
            return {}
        raw = self.rfile.read(min(length, 8_000_000))
        if not raw:
            return {}
        try:
            return json.loads(raw.decode("utf-8"))
        except json.JSONDecodeError:
            return {}

    def _token(self, data=None) -> str:
        if data and data.get("token"):
            return clean(data.get("token"), 80)
        auth = self.headers.get("Authorization") or ""
        if auth.lower().startswith("bearer "):
            return clean(auth.split(" ", 1)[1], 80)
        q = parse_qs(urlparse(self.path).query)
        return clean((q.get("token") or [""])[0], 80)

    def do_OPTIONS(self):
        self.send_response(204)
        self._cors()
        self.end_headers()

    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path.rstrip("/") or "/"
        if path in ("/api/health", "/health"):
            return self._json({"ok": True, "service": "coinsmarocain-partner", "ts": now_iso()})
        if path == "/api/public/listings":
            with LOCK:
                store = load_store()
            listings = [
                public_listing(a)
                for a in store["accounts"]
                if a.get("role") == "merchant"
                and a.get("status") == "published"
                and a.get("lat")
                and a.get("lng")
            ]
            return self._json({"ok": True, "listings": listings})
        if path == "/api/session":
            token = self._token()
            with LOCK:
                store = load_store()
                acc = find_account(store, token=token)
            if not acc:
                return self._json({"ok": False, "error": "token"}, 401)
            payload = {"ok": True, "account": acc}
            if acc.get("role") == "admin":
                payload["queue"] = [
                    public_listing(a)
                    | {
                        "email": a.get("email"),
                        "phone": a.get("phone"),
                        "contact_name": a.get("contact_name"),
                        "status": a.get("status"),
                        "id": a.get("id"),
                    }
                    for a in store["accounts"]
                    if a.get("role") == "merchant"
                ]
            return self._json(payload)
        if path == "/api/admin/queue":
            token = self._token()
            with LOCK:
                store = load_store()
                acc = find_account(store, token=token)
            if not acc or acc.get("role") != "admin":
                return self._json({"ok": False, "error": "admin"}, 403)
            return self._json({"ok": True, "accounts": store["accounts"]})
        return self._json({"ok": False, "error": "not_found", "path": path}, 404)

    def do_POST(self):
        path = urlparse(self.path).path.rstrip("/") or "/"
        if path == "/api/merchant/upload":
            return self._upload()
        if path == "/api/merchant/media-remove":
            return self._media_remove(self._body())
        data = self._body()
        if path == "/api/signup":
            return self._signup(data)
        if path == "/api/merchant/submit":
            return self._submit(data)
        if path == "/api/admin/moderate":
            return self._moderate(data)
        if path == "/api/track":
            return self._track(data)
        return self._json({"ok": False, "error": "not_found"}, 404)

    def do_PUT(self):
        path = urlparse(self.path).path.rstrip("/") or "/"
        data = self._body()
        if path == "/api/merchant":
            return self._save_merchant(data)
        return self._json({"ok": False, "error": "not_found"}, 404)

    def _signup(self, data):
        name = clean(data.get("name") or data.get("place_name"), 160)
        email = clean(data.get("email"), 120).lower()
        phone = clean(data.get("phone"), 40)
        if not name:
            return self._json({"ok": False, "error": "name"}, 400)
        if not EMAIL_RE.match(email):
            return self._json({"ok": False, "error": "email"}, 400)
        if not phone:
            return self._json({"ok": False, "error": "phone"}, 400)
        region = clean(data.get("region") or data.get("quartier"), 60) or "Médina"
        if region not in QUARTIERS:
            region = "Médina"
        category = _norm_cat(data.get("category"))
        with LOCK:
            store = load_store()
            for acc in store["accounts"]:
                if acc.get("email") == email and acc.get("role") == "merchant":
                    return self._json({
                        "ok": True,
                        "existing": True,
                        "id": acc["id"],
                        "token": acc["token"],
                        "status": acc.get("status"),
                        "portal_url": portal_url(acc),
                    })
            acc = {
                "id": f"m_{secrets.token_hex(4)}",
                "token": new_token("cm"),
                "role": "merchant",
                "status": "draft",
                "name": name,
                "contact_name": clean(data.get("contact_name"), 120),
                "email": email,
                "phone": phone,
                "region": region,
                "category": category,
                "description": clean(data.get("description"), 4000),
                "address": clean(data.get("address"), 240),
                "lat": _num(data.get("lat")),
                "lng": _num(data.get("lng")),
                "video_url": clean(data.get("video_url"), 500),
                "photos": [],
                "services": [],
                "packages": [],
                "featured": False,
                "stats": {"views": 0, "clicks": 0, "bookings": 0},
                "created_at": now_iso(),
                "updated_at": now_iso(),
            }
            apply_quartier_coords(acc)
            store["accounts"].append(acc)
            store["events"].append({"type": "signup", "account_id": acc["id"], "at": now_iso()})
            save_store(store)
        return self._json({
            "ok": True,
            "id": acc["id"],
            "token": acc["token"],
            "status": acc["status"],
            "portal_url": portal_url(acc),
        })

    def _save_merchant(self, data):
        token = self._token(data)
        with LOCK:
            store = load_store()
            acc = find_account(store, token=token)
            if not acc or acc.get("role") != "merchant":
                return self._json({"ok": False, "error": "token"}, 401)
            for key in ("name", "contact_name", "phone", "region", "category",
                        "description", "address", "video_url"):
                if key in data:
                    limit = 4000 if key == "description" else 240
                    if key == "video_url":
                        limit = 500
                    acc[key] = clean(data.get(key), limit)
            if "category" in data:
                acc["category"] = _norm_cat(data.get("category"))
            if acc.get("region") not in QUARTIERS:
                acc["region"] = "Médina"
            if "lat" in data:
                acc["lat"] = _num(data.get("lat"))
            if "lng" in data:
                acc["lng"] = _num(data.get("lng"))
            apply_quartier_coords(acc)
            if "services" in data and isinstance(data["services"], list):
                acc["services"] = [_offer(x) for x in data["services"][:20]]
            if "packages" in data and isinstance(data["packages"], list):
                acc["packages"] = [_offer(x) for x in data["packages"][:12]]
            if "photos" in data and isinstance(data["photos"], list):
                photos = []
                for p in data["photos"][:MAX_PHOTOS]:
                    url = clean(p, 600_000)
                    if url.startswith("data:") and len(url) > MAX_PHOTO_B64:
                        continue
                    if url:
                        photos.append(url)
                acc["photos"] = photos
                media_unify.mark_dirty(acc)
            if "video_url" in data:
                media_unify.mark_dirty(acc)
            if acc.get("status") == "published":
                acc["status"] = "pending"
            acc["updated_at"] = now_iso()
            save_store(store)
        return self._json({"ok": True, "account": acc})

    def _read_upload_body(self):
        length = int(self.headers.get("Content-Length") or 0)
        if length <= 0 or length > media_upload.MAX_BODY:
            return None
        return self.rfile.read(length)

    def _upload(self):
        raw = self._read_upload_body()
        if raw is None:
            return self._json({"ok": False, "error": "too_large"}, 413)
        fields, files = media_upload.parse_multipart(self.headers, raw)
        token = clean(fields.get("token") or self._token(fields), 80)
        kind = clean(fields.get("kind") or "photo", 12)
        if kind not in ("photo", "video"):
            return self._json({"ok": False, "error": "kind"}, 400)
        uploaded = files.get("file") or files.get("photo") or files.get("video")
        if not uploaded:
            return self._json({"ok": False, "error": "file"}, 400)
        with LOCK:
            store = load_store()
            acc = find_account(store, token=token)
            if not acc or acc.get("role") != "merchant":
                return self._json({"ok": False, "error": "token"}, 401)
            url, err = media_upload.save_file(
                UPLOAD_DIR, UPLOAD_URL, acc["id"], kind,
                uploaded.get("filename") or "", uploaded.get("data") or b"",
            )
            if err or not url:
                status = 413 if err == "too_large" else 400
                return self._json({"ok": False, "error": err or "save"}, status)
            if kind == "video":
                acc["video_url"] = url
            else:
                photos = [p for p in (acc.get("photos") or []) if p]
                if url not in photos:
                    photos.append(url)
                acc["photos"] = photos[:media_upload.MAX_PHOTOS]
            media_unify.mark_dirty(acc)
            if acc.get("status") == "published":
                acc["status"] = "pending"
            acc["updated_at"] = now_iso()
            save_store(store)
        return self._json({"ok": True, "url": url, "kind": kind, "account": acc})

    def _media_remove(self, data):
        token = self._token(data)
        kind = clean(data.get("kind"), 12)
        url = clean(data.get("url"), 400)
        with LOCK:
            store = load_store()
            acc = find_account(store, token=token)
            if not acc or acc.get("role") != "merchant":
                return self._json({"ok": False, "error": "token"}, 401)
            if kind == "video" and acc.get("video_url") == url:
                acc["video_url"] = ""
            elif kind == "photo":
                acc["photos"] = [p for p in (acc.get("photos") or []) if p != url]
            media_unify.mark_dirty(acc)
            acc["updated_at"] = now_iso()
            save_store(store)
        return self._json({"ok": True, "account": acc})

    def _submit(self, data):
        token = self._token(data)
        with LOCK:
            store = load_store()
            acc = find_account(store, token=token)
            if not acc or acc.get("role") != "merchant":
                return self._json({"ok": False, "error": "token"}, 401)
            if not acc.get("name") or not acc.get("description"):
                return self._json({"ok": False, "error": "incomplete"}, 400)
            acc["status"] = "pending"
            acc["updated_at"] = now_iso()
            store["events"].append({"type": "submit", "account_id": acc["id"], "at": now_iso()})
            save_store(store)
        return self._json({"ok": True, "status": "pending", "account": acc})

    def _run_unify(self, target_id: str, force: bool = False):
        with LOCK:
            store = load_store()
            acc = find_account(store, account_id=target_id)
            if not acc:
                return None, "id"
            snap = media_unify.snapshot(acc)
        recap = media_unify.process(snap, UPLOAD_DIR, UPLOAD_URL, force=force)
        if recap.get("fatal"):
            return recap, recap.get("error") or "unify_failed"
        with LOCK:
            store = load_store()
            acc = find_account(store, account_id=target_id)
            if not acc:
                return recap, "id"
            media_unify.writeback(acc, recap)
            acc["updated_at"] = now_iso()
            save_store(store)
        return recap, None

    def _moderate(self, data):
        token = self._token(data)
        action = clean(data.get("action"), 20)
        target_id = clean(data.get("id"), 40)
        with LOCK:
            store = load_store()
            admin = find_account(store, token=token)
            if not admin or admin.get("role") != "admin":
                return self._json({"ok": False, "error": "admin"}, 403)
            acc = find_account(store, account_id=target_id)
            if not acc:
                return self._json({"ok": False, "error": "id"}, 404)
        if action == "unify":
            recap, err = self._run_unify(target_id, force=True)
            if err:
                return self._json({"ok": False, "error": err, "recap": recap}, 400)
            with LOCK:
                store = load_store()
                acc = find_account(store, account_id=target_id)
                store["events"].append({
                    "type": "moderate",
                    "action": "unify",
                    "account_id": target_id,
                    "at": now_iso(),
                })
                save_store(store)
            return self._json({"ok": True, "account": public_listing(acc), "recap": recap})
        if action in ("approve", "feature"):
            recap, err = self._run_unify(target_id, force=False)
            if err:
                return self._json({"ok": False, "error": err, "recap": recap}, 400)
        with LOCK:
            store = load_store()
            acc = find_account(store, account_id=target_id)
            if not acc:
                return self._json({"ok": False, "error": "id"}, 404)
            if action == "approve":
                acc["status"] = "published"
                apply_quartier_coords(acc)
            elif action == "reject":
                acc["status"] = "rejected"
            elif action == "feature":
                acc["featured"] = True
                acc["status"] = "published"
                apply_quartier_coords(acc)
            elif action == "unfeature":
                acc["featured"] = False
            else:
                return self._json({"ok": False, "error": "action"}, 400)
            acc["updated_at"] = now_iso()
            store["events"].append({
                "type": "moderate",
                "action": action,
                "account_id": acc["id"],
                "at": now_iso(),
            })
            save_store(store)
        return self._json({"ok": True, "account": public_listing(acc)})

    def _track(self, data):
        listing_id = clean(data.get("id"), 40)
        event = clean(data.get("event"), 20) or "view"
        if event not in ("view", "click", "booking"):
            return self._json({"ok": False, "error": "event"}, 400)
        with LOCK:
            store = load_store()
            acc = find_account(store, account_id=listing_id)
            if not acc:
                return self._json({"ok": False, "error": "id"}, 404)
            stats = acc.setdefault("stats", {"views": 0, "clicks": 0, "bookings": 0})
            key = "views" if event == "view" else ("clicks" if event == "click" else "bookings")
            stats[key] = int(stats.get(key) or 0) + 1
            save_store(store)
        return self._json({"ok": True, "stats": acc.get("stats")})


def main():
    os.makedirs(os.path.dirname(DATA_PATH), exist_ok=True)
    with LOCK:
        load_store()
    httpd = ThreadingHTTPServer((HOST, PORT), Handler)
    print(f"coinsmarocain partner api on {HOST}:{PORT} data={DATA_PATH}", flush=True)
    httpd.serve_forever()


if __name__ == "__main__":
    main()
