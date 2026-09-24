# -*- coding: utf-8 -*-
"""API publique site coinsmarocain.com — villas + checkout Stripe."""
from __future__ import annotations

import json
import logging
import re
from datetime import timedelta

from odoo import fields, http
from odoo.http import request

from odoo.addons.coins_marocain.services.coins_stripe import CoinsStripeService
from odoo.addons.coins_marocain.services.cross_sell_catalog import (
    CROSS_SELL_PACKS,
    GROUP_LABELS,
    PACKS_BY_CODE,
)

_logger = logging.getLogger(__name__)

_HTML_TAG = re.compile(r"<[^>]+>")


def _strip_html(html):
    if not html:
        return ""
    text = _HTML_TAG.sub(" ", html)
    return re.sub(r"\s+", " ", text).strip()


def _public_description(html):
    """Descriptif site : sans mention Airbnb / n° d’annonce / consignes internes."""
    text = _strip_html(html)
    if not text:
        return ""
    text = re.split(r"\bSource Airbnb\b", text, flags=re.I)[0]
    text = re.split(r"À compléter\s*:", text, flags=re.I)[0]
    text = re.sub(
        r"\bannonce\s*#?\s*\d+\b",
        "",
        text,
        flags=re.I,
    )
    text = re.sub(r"https?://\S*airbnb\S*", "", text, flags=re.I)
    return re.sub(r"\s+", " ", text).strip(" ·-\t")


def _json(payload, status=200, cache=None):
    headers = [("Content-Type", "application/json")]
    headers.append(("Access-Control-Allow-Origin", "*"))
    headers.append(("Access-Control-Allow-Methods", "GET, POST, OPTIONS"))
    headers.append(("Access-Control-Allow-Headers", "Content-Type, Stripe-Signature"))
    if cache:
        headers.append(("Cache-Control", cache))
    else:
        headers.append(("Cache-Control", "no-store"))
    return request.make_response(json.dumps(payload, default=str), headers=headers, status=status)


def _body():
    try:
        raw = request.httprequest.get_data(as_text=True) or "{}"
        return json.loads(raw)
    except Exception:
        return {}


def _mad_per_cad(env):
    raw = (
        env["ir.config_parameter"]
        .sudo()
        .get_param("coins_marocain.mad_per_cad", "7.2")
    )
    try:
        v = float(raw)
        return v if v > 0 else 7.2
    except (TypeError, ValueError):
        return 7.2


def _pack_price_cad(env, price_mad):
    return round(float(price_mad) / _mad_per_cad(env), 2)


def _cad_currency(env):
    cad = env.ref("base.CAD", raise_if_not_found=False)
    if cad:
        return cad
    return env["res.currency"].sudo().search([("name", "=", "CAD")], limit=1)


class CoinsPublicApi(http.Controller):

    @http.route(
        "/api/coins-marocain/proprietes.json",
        type="http",
        auth="public",
        methods=["GET", "OPTIONS"],
        csrf=False,
        cors="*",
    )
    def proprietes_json(self, **kw):
        if request.httprequest.method == "OPTIONS":
            return _json({"ok": True})
        Property = request.env["coins.property"].sudo()
        props = Property.search(
            [("active", "=", True), ("state", "=", "active")]
            + Property._domain_exclude_unpublished_onboarding(),
            order="name",
        )
        mad_per_cad = _mad_per_cad(request.env)
        items = []
        for p in props:
            # URLs relatives → même origine (coinsmarocain.com via nginx)
            photos = []
            for ph in p.photo_ids.sorted("sequence"):
                if not ph.image:
                    continue
                base = "/api/coins-marocain/photos/%s" % ph.id
                photos.append(
                    {
                        "id": ph.id,
                        "url": "%s?w=720" % base,
                        "url_thumb": "%s?w=360" % base,
                        "url_full": "%s?w=1600" % base,
                        "legende": ph.legende or "",
                    }
                )
            if not photos and p.image_1920:
                base = "/api/coins-marocain/photos/property/%s" % p.id
                photos.append(
                    {
                        "id": "main",
                        "url": "%s?w=720" % base,
                        "url_thumb": "%s?w=360" % base,
                        "url_full": "%s?w=1600" % base,
                        "legende": p.name or "",
                    }
                )
            dispos = [
                {
                    "date_debut": fields.Date.to_string(d.date_debut),
                    "date_fin": fields.Date.to_string(d.date_fin),
                }
                for d in p.disponibilite_ids.sorted("date_debut")
            ]
            prix = float(p.price_per_night or 0.0)
            rooms = [
                {
                    "id": r.id,
                    "nom": r.name,
                    "sleeps": r.sleeps or 0,
                    "description": r.description or "",
                }
                for r in p.room_ids.filtered("active").sorted("sequence")
            ]
            items.append(
                {
                    "id": p.id,
                    "nom": p.name,
                    "type": p.property_type,
                    "capacite": p.capacity or 0,
                    "ville": p.city or "",
                    "description": _public_description(
                        p.description or p.narrative or ""
                    ),
                    "prix_nuit_cad": prix,
                    "frais_service_pct": float(p.frais_service_pct or 0.0),
                    "photos": photos,
                    "disponibilites": dispos,
                    "reservable": bool(p.online_booking),
                    "rooms": rooms,
                    "daypass_piscine": bool(p.daypass_piscine),
                    "daypass_price_cad": float(p.daypass_price or 0.0),
                    "daypass_capacity_day": int(p.daypass_capacity_day or 0),
                    "meals": {
                        "breakfast": {
                            "available": bool(p.meal_breakfast_available),
                            "price_cad": float(p.meal_breakfast_price or 0.0),
                        },
                        "lunch": {
                            "available": bool(p.meal_lunch_available),
                            "price_cad": float(p.meal_lunch_price or 0.0),
                        },
                        "dinner": {
                            "available": bool(p.meal_dinner_available),
                            "price_cad": float(p.meal_dinner_price or 0.0),
                        },
                    },
                }
            )
        packs = []
        for pack in CROSS_SELL_PACKS:
            packs.append(
                {
                    **pack,
                    "group_label": GROUP_LABELS.get(pack.get("group") or "forfait", ""),
                    "unit": pack.get("unit") or "person",
                    "price_cad": _pack_price_cad(request.env, pack["price_mad"]),
                }
            )
        return _json(
            {
                "ok": True,
                "currency_charge": "CAD",
                "mad_per_cad": mad_per_cad,
                "display_note": (
                    "Paiement en ligne (cartes internationales) ou sur place "
                    "(espèces / carte) — montants affichés en DH ou €."
                ),
                "proprietes": items,
                "cross_sell": packs,
            },
            cache="public, max-age=300",
        )

    @http.route(
        [
            "/api/coins-marocain/photos/<int:photo_id>",
            "/api/coins-marocain/photos/property/<int:property_id>",
        ],
        type="http",
        auth="public",
        methods=["GET"],
        csrf=False,
    )
    def public_photo(self, photo_id=None, property_id=None, **kw):
        import base64
        import hashlib
        import io
        import os

        from PIL import Image

        def _bytes(val):
            if not val:
                return b""
            if isinstance(val, bytes):
                try:
                    return base64.b64decode(val)
                except Exception:
                    return val
            if isinstance(val, str):
                return base64.b64decode(val)
            return bytes(val)

        def _max_w():
            raw = (request.params.get("w") or kw.get("w") or "").strip()
            try:
                w = int(raw) if raw else 1200
            except (TypeError, ValueError):
                w = 1200
            return max(120, min(w, 1920))

        def _jpeg_resized(raw, max_w, quality=78):
            im = Image.open(io.BytesIO(raw))
            if im.mode not in ("RGB", "L"):
                im = im.convert("RGB")
            elif im.mode == "L":
                im = im.convert("RGB")
            w, h = im.size
            if w > max_w:
                nh = int(round(h * (max_w / float(w))))
                im = im.resize((max_w, max(1, nh)), Image.Resampling.LANCZOS)
            out = io.BytesIO()
            im.save(out, format="JPEG", quality=quality, optimize=True, progressive=True)
            return out.getvalue()

        def _jpeg_via_ffmpeg(raw, max_w, quality=78):
            """Fallback quand Pillow n'ouvre pas certains WebP."""
            import subprocess
            import tempfile

            qscale = max(2, min(8, int(round((100 - quality) / 12.0)) or 3))
            with tempfile.TemporaryDirectory() as td:
                src = os.path.join(td, "in.bin")
                dst = os.path.join(td, "out.jpg")
                with open(src, "wb") as fh:
                    fh.write(raw)
                vf = "scale='min(%d,iw)':-2" % int(max_w)
                subprocess.check_call(
                    [
                        "ffmpeg",
                        "-y",
                        "-loglevel",
                        "error",
                        "-i",
                        src,
                        "-frames:v",
                        "1",
                        "-update",
                        "1",
                        "-vf",
                        vf,
                        "-q:v",
                        str(qscale),
                        dst,
                    ],
                    timeout=30,
                )
                with open(dst, "rb") as fh:
                    return fh.read()

        def _to_jpeg(raw, max_w, quality=78):
            try:
                return _jpeg_resized(raw, max_w, quality=quality)
            except Exception:
                _logger.warning(
                    "PIL resize failed — ffmpeg fallback key_w=%s", max_w, exc_info=True
                )
                return _jpeg_via_ffmpeg(raw, max_w, quality=quality)

        def _serve(raw, cache_key):
            if not raw:
                return request.not_found()
            max_w = _max_w()
            cache_dir = "/var/cache/coins_photos"
            try:
                os.makedirs(cache_dir, mode=0o755, exist_ok=True)
            except OSError:
                cache_dir = "/tmp/coins_photos"
                os.makedirs(cache_dir, mode=0o755, exist_ok=True)
            digest = hashlib.sha1(
                ("%s|%s|%s" % (cache_key, max_w, len(raw))).encode()
            ).hexdigest()
            path = os.path.join(cache_dir, "%s.jpg" % digest)
            data = None

            def _is_jpeg(blob):
                return bool(blob) and blob[:2] == b"\xff\xd8"

            if os.path.isfile(path) and os.path.getsize(path) > 500:
                with open(path, "rb") as fh:
                    data = fh.read()
                # Cache pollué (ex. WebP brut étiqueté .jpg) → régénérer
                if not _is_jpeg(data):
                    data = None
                    try:
                        os.unlink(path)
                    except OSError:
                        pass
            if data is None:
                try:
                    data = _to_jpeg(raw, max_w)
                    with open(path, "wb") as fh:
                        fh.write(data)
                except Exception:
                    _logger.exception("photo resize fail key=%s", cache_key)
                    return request.not_found()
            return request.make_response(
                data,
                headers=[
                    ("Content-Type", "image/jpeg"),
                    ("Cache-Control", "public, max-age=604800, immutable"),
                    ("X-Content-Type-Options", "nosniff"),
                ],
            )

        if property_id:
            prop = request.env["coins.property"].sudo().browse(property_id)
            if (
                not prop.exists()
                or not prop.active
                or prop.state != "active"
                or not prop._is_publicly_listed()
            ):
                return request.not_found()
            return _serve(_bytes(prop.image_1920), "prop-%s" % property_id)

        photo = request.env["coins.property.photo"].sudo().browse(photo_id)
        if not photo.exists() or not photo.property_id.active:
            return request.not_found()
        if photo.property_id.state != "active":
            return request.not_found()
        return _serve(_bytes(photo.image), "photo-%s" % photo_id)

    @http.route(
        "/api/coins-marocain/reservations/checkout",
        type="http",
        auth="public",
        methods=["POST", "OPTIONS"],
        csrf=False,
        cors="*",
    )
    def checkout(self, **kw):
        if request.httprequest.method == "OPTIONS":
            return _json({"ok": True})
        data = _body()
        try:
            prop_id = int(data.get("propriete_id") or 0)
            check_in = fields.Date.to_date(data.get("date_debut") or data.get("check_in"))
            check_out = fields.Date.to_date(data.get("date_fin") or data.get("check_out"))
        except Exception:
            return _json({"ok": False, "error": "invalid_payload"}, 400)

        client_nom = (data.get("client_nom") or "").strip()[:120]
        client_email = (data.get("client_email") or "").strip()[:120]
        client_tel = (data.get("client_telephone") or "").strip()[:40]
        cross = data.get("cross_sell") or []
        try:
            voyageurs = max(int(data.get("voyageurs") or data.get("guests") or 1), 1)
        except (TypeError, ValueError):
            voyageurs = 1
        voyageurs = min(voyageurs, 30)

        if not prop_id or not check_in or not check_out or check_out <= check_in:
            return _json({"ok": False, "error": "invalid_dates"}, 400)
        if not client_nom or not client_email or "@" not in client_email:
            return _json({"ok": False, "error": "invalid_client"}, 400)

        Property = request.env["coins.property"].sudo()
        prop = Property.browse(prop_id)
        if not prop.exists() or not prop.online_booking:
            return _json({"ok": False, "error": "not_reservable"}, 400)

        last_night = check_out - timedelta(days=1)
        if not prop.est_disponible(check_in, last_night):
            return _json({"ok": False, "error": "unavailable"}, 409)

        nights = (check_out - check_in).days
        prix_nuit = float(prop.price_per_night or 0.0)
        if prix_nuit <= 0 or nights < 1:
            return _json({"ok": False, "error": "no_price"}, 400)

        montant_villa = round(prix_nuit * nights, 2)
        frais_pct = float(prop.frais_service_pct or 0.0)
        frais = round(montant_villa * (frais_pct / 100.0), 2) if frais_pct > 0 else 0.0

        room_id = 0
        try:
            room_id = int(data.get("room_id") or 0)
        except (TypeError, ValueError):
            room_id = 0
        room = False
        if room_id:
            room = request.env["coins.property.room"].sudo().browse(room_id)
            if (
                not room.exists()
                or room.property_id.id != prop.id
                or not room.active
            ):
                return _json({"ok": False, "error": "invalid_room"}, 400)
            if room.sleeps and voyageurs > int(room.sleeps):
                return _json(
                    {
                        "ok": False,
                        "error": "too_many_guests",
                        "detail": "Cette chambre accueille max %s personnes."
                        % room.sleeps,
                    },
                    400,
                )
        elif prop.capacity and voyageurs > int(prop.capacity):
            return _json(
                {
                    "ok": False,
                    "error": "too_many_guests",
                    "detail": "Capacité max %s personnes." % prop.capacity,
                },
                400,
            )

        want_daypass = bool(data.get("daypass_piscine"))
        want_breakfast = bool(data.get("meal_breakfast"))
        want_lunch = bool(data.get("meal_lunch"))
        want_dinner = bool(data.get("meal_dinner"))
        allergies = (data.get("allergies") or "").strip()[:2000]

        if want_daypass and not prop.daypass_piscine:
            return _json({"ok": False, "error": "daypass_unavailable"}, 400)
        if want_breakfast and not prop.meal_breakfast_available:
            return _json({"ok": False, "error": "meal_unavailable"}, 400)
        if want_lunch and not prop.meal_lunch_available:
            return _json({"ok": False, "error": "meal_unavailable"}, 400)
        if want_dinner and not prop.meal_dinner_available:
            return _json({"ok": False, "error": "meal_unavailable"}, 400)

        if want_daypass and prop.daypass_capacity_day:
            Slot = request.env["coins.property.ops.slot"].sudo()
            day_start = fields.Datetime.to_datetime(
                "%s 00:00:00" % fields.Date.to_string(check_in)
            )
            day_end = fields.Datetime.to_datetime(
                "%s 23:59:59" % fields.Date.to_string(check_in)
            )
            booked = Slot.search_count(
                [
                    ("property_id", "=", prop.id),
                    ("slot_type", "=", "daypass"),
                    ("state", "!=", "cancelled"),
                    ("date_start", ">=", day_start),
                    ("date_start", "<=", day_end),
                ]
            )
            if booked >= int(prop.daypass_capacity_day):
                return _json(
                    {
                        "ok": False,
                        "error": "daypass_full",
                        "detail": "Daypass complet pour cette date.",
                    },
                    409,
                )

        Partner = request.env["res.partner"].sudo()
        partner = Partner.search([("email", "=ilike", client_email)], limit=1)
        if not partner:
            partner = Partner.create(
                {
                    "name": client_nom,
                    "email": client_email,
                    "phone": client_tel or False,
                    "comment": "Créé via checkout coinsmarocain.com",
                }
            )
        else:
            vals = {}
            if client_nom and partner.name != client_nom:
                vals["name"] = client_nom
            if client_tel and not partner.phone:
                vals["phone"] = client_tel
            if vals:
                partner.write(vals)

        cad = _cad_currency(request.env)
        Reservation = request.env["coins.reservation"].sudo()
        note_bits = ["Voyageurs : %s" % voyageurs]
        if room:
            note_bits.append("Chambre : %s" % room.name)
        if allergies:
            note_bits.append("Allergies : %s" % allergies)
        resa = Reservation.create(
            {
                "traveler_id": partner.id,
                "property_id": prop.id,
                "check_in": check_in,
                "check_out": check_out,
                "state": "draft",
                "source": "direct",
                "booking_channel": "website",
                "client_nom": client_nom,
                "client_email": client_email,
                "client_telephone": client_tel,
                "currency_id": cad.id if cad else False,
                "amount_property": montant_villa + frais,
                "amount_activities": 0.0,
                "amount_transport": 0.0,
                "payment_status": "unpaid",
                "payment_method": "stripe",
                "voyageurs": voyageurs,
                "room_id": room.id if room else False,
                "daypass_piscine": want_daypass,
                "meal_breakfast": want_breakfast,
                "meal_lunch": want_lunch,
                "meal_dinner": want_dinner,
                "allergies": allergies or False,
                "notes": "\n".join(note_bits),
            }
        )

        Line = request.env["coins.reservation.line"].sudo()
        amount_activities = 0.0
        extras = []
        if want_daypass and float(prop.daypass_price or 0) > 0:
            extras.append(
                (
                    "daypass_piscine",
                    "Daypass piscine",
                    voyageurs,
                    float(prop.daypass_price),
                )
            )
        meal_extras = [
            (want_breakfast, "meal_breakfast", "Petit-déjeuner", prop.meal_breakfast_price),
            (want_lunch, "meal_lunch", "Déjeuner", prop.meal_lunch_price),
            (want_dinner, "meal_dinner", "Dîner", prop.meal_dinner_price),
        ]
        for enabled, code, label, price in meal_extras:
            if enabled and float(price or 0) > 0:
                extras.append((code, label, voyageurs, float(price)))
        for code, label, qty, unit_price in extras:
            Line.create(
                {
                    "reservation_id": resa.id,
                    "code": code,
                    "name": "%s (%s pers.)" % (label, qty),
                    "qty": qty,
                    "price_unit_cad": unit_price,
                }
            )
            amount_activities += unit_price * qty

        for item in cross:
            code = (item.get("code") or "").strip()
            pack = PACKS_BY_CODE.get(code)
            if not pack:
                continue
            unit = pack.get("unit") or "person"
            qty = 1 if unit == "group" else voyageurs
            price_cad = _pack_price_cad(request.env, pack["price_mad"])
            label = pack["name"]
            if unit == "person":
                label = "%s (%s pers.)" % (pack["name"], qty)
            else:
                label = "%s (groupe)" % pack["name"]
            Line.create(
                {
                    "reservation_id": resa.id,
                    "code": code,
                    "name": label,
                    "qty": qty,
                    "price_unit_cad": price_cad,
                }
            )
            line_total = price_cad * qty
            if pack.get("group") == "activite":
                amount_activities += line_total
        if amount_activities:
            resa.write({"amount_activities": amount_activities})
        # recompute totals
        resa.invalidate_recordset()
        resa = Reservation.browse(resa.id)

        try:
            stripe_svc = CoinsStripeService(request.env)
            session = stripe_svc.create_checkout_session(resa)
        except Exception as exc:
            _logger.exception("checkout stripe fail resa=%s", resa.id)
            resa.write({"state": "cancelled", "notes": "stripe_error: %s" % exc})
            return _json({"ok": False, "error": "stripe_error", "detail": str(exc)}, 502)

        resa.write(
            {
                "stripe_checkout_session_id": session.id,
                "payment_reference": session.id,
            }
        )
        return _json(
            {
                "ok": True,
                "reservation_id": resa.id,
                "reservation_name": resa.name,
                "amount_total_cad": resa.amount_total,
                "currency": "cad",
                "url": session.url,
            }
        )

    @http.route(
        "/api/coins-marocain/stripe-webhook",
        type="http",
        auth="public",
        methods=["POST"],
        csrf=False,
    )
    def stripe_webhook(self, **kw):
        payload = request.httprequest.get_data()
        sig = request.httprequest.headers.get("Stripe-Signature") or ""
        svc = CoinsStripeService(request.env)
        try:
            event = svc.construct_webhook_event(payload, sig)
        except Exception as exc:
            _logger.warning("stripe webhook signature fail: %s", exc)
            return _json({"ok": False, "error": "invalid_signature"}, 400)

        if event["type"] != "checkout.session.completed":
            return _json({"ok": True, "ignored": event["type"]})

        session = event["data"]["object"]
        resa_id = int(
            (session.get("metadata") or {}).get("reservation_id")
            or session.get("client_reference_id")
            or 0
        )
        Reservation = request.env["coins.reservation"].sudo()
        resa = Reservation.browse(resa_id) if resa_id else Reservation.browse()
        if not resa.exists():
            sid = session.get("id")
            resa = Reservation.search(
                [("stripe_checkout_session_id", "=", sid)], limit=1
            )
        if not resa:
            _logger.error("stripe webhook: reservation not found session=%s", session.get("id"))
            return _json({"ok": False, "error": "reservation_not_found"}, 404)

        pi = session.get("payment_intent") or ""
        if isinstance(pi, dict):
            pi = pi.get("id") or ""
        resa.write({"stripe_payment_intent_id": pi or resa.stripe_payment_intent_id})

        if resa.state == "confirmed":
            return _json({"ok": True, "already": True})

        last_night = resa.check_out - timedelta(days=1)
        if not resa.property_id.est_disponible(resa.check_in, last_night):
            _logger.warning(
                "stripe webhook conflict resa=%s — refund",
                resa.id,
            )
            svc.refund_session_payment(pi, reason="double_booking_conflict")
            resa.write(
                {
                    "state": "cancelled",
                    "payment_status": "unpaid",
                    "notes": (resa.notes or "")
                    + "\n[auto] conflit dates post-paiement → refund Stripe",
                }
            )
            # notify ops
            mail_to = (
                request.env["ir.config_parameter"]
                .sudo()
                .get_param(
                    "coins_marocain.booking_notify_email",
                    "karine@agencedoorway.com",
                )
            )
            request.env["mail.mail"].sudo().create(
                {
                    "subject": "[Coins] CONFLIT réservation remboursée %s" % resa.name,
                    "body_html": "<p>Réservation %s remboursée (dates prises entre checkout et paiement).</p>"
                    % resa.name,
                    "email_to": mail_to,
                    "auto_delete": True,
                }
            ).send()
            return _json({"ok": True, "refunded": True, "reason": "conflict"})

        try:
            resa._confirm_website_booking()
        except Exception:
            _logger.exception("confirm website booking fail resa=%s", resa.id)
            svc.refund_session_payment(pi, reason="confirm_failed")
            resa.write({"state": "cancelled"})
            return _json({"ok": False, "error": "confirm_failed"}, 500)

        return _json({"ok": True, "confirmed": True, "reservation_id": resa.id})
