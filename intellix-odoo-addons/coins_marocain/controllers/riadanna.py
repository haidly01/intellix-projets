# -*- coding: utf-8 -*-
"""Site Riad Anna Sweety → coins.reservation (Intellix).

Channex se branche ensuite via coins.channex.mapping sur cette même propriété.
"""
import json

from odoo import fields, http
from odoo.http import request

PROPERTY_ICP = "coins.riadanna.property_id"
BLOCKING_STATES = ("confirmed", "in_progress")


def _json(payload, status=200):
    body = json.dumps(payload, ensure_ascii=False, default=str)
    return request.make_response(
        body,
        status=status,
        headers=[
            ("Content-Type", "application/json; charset=utf-8"),
            ("Access-Control-Allow-Origin", "*"),
            ("Access-Control-Allow-Methods", "GET, POST, OPTIONS"),
            ("Access-Control-Allow-Headers", "Content-Type"),
        ],
    )


def _body():
    raw = request.httprequest.get_data(as_text=True) or ""
    if not raw:
        return {}
    try:
        data = json.loads(raw)
    except ValueError:
        return {}
    return data if isinstance(data, dict) else {}


def _clean(value, maxlen=200):
    return (value or "").strip()[:maxlen]


def _riad_property(env):
    icp = env["ir.config_parameter"].sudo()
    raw_id = (icp.get_param(PROPERTY_ICP) or "").strip()
    Property = env["coins.property"].sudo()
    if raw_id.isdigit():
        prop = Property.browse(int(raw_id))
        if prop.exists() and prop.active:
            return prop
    return Property.search(
        [("name", "=", "Riad Anna Sweety"), ("active", "=", True)],
        limit=1,
    )


def _room_blocked(env, property_id, room_id, check_in, check_out):
    domain = [
        ("property_id", "=", property_id),
        ("state", "in", list(BLOCKING_STATES)),
        ("check_in", "<", check_out),
        ("check_out", ">", check_in),
    ]
    if room_id:
        domain.append(("room_id", "=", room_id))
    return bool(env["coins.reservation"].sudo().search(domain, limit=1))


def _room_nightly_rate(room):
    room_rate = getattr(room, "price_per_night", None)
    if room_rate:
        return float(room_rate)
    return float(room.property_id.price_per_night or 150)


def _serialize_room(room, check_in=None, check_out=None):
    available = True
    if check_in and check_out:
        available = not _room_blocked(
            room.env, room.property_id.id, room.id, check_in, check_out
        )
    return {
        "id": room.id,
        "name": room.name,
        "sleeps": int(room.sleeps or 2),
        "description": room.description or "",
        "available": available,
        "price_per_night": _room_nightly_rate(room),
        "emplacement": getattr(room, "emplacement", None) or "",
        "breakfast_included": bool(getattr(room, "breakfast_included", True)),
    }


class RiadAnnaBookingApi(http.Controller):
    @http.route(
        ["/api/riadanna/offer", "/api/riadanna/offer/"],
        type="http",
        auth="public",
        methods=["GET", "OPTIONS"],
        csrf=False,
        cors="*",
    )
    def offer(self, **kw):
        if request.httprequest.method == "OPTIONS":
            return _json({"ok": True})
        env = request.env
        prop = _riad_property(env)
        if not prop:
            return _json({"ok": False, "error": "property_missing"}, 404)

        check_in = check_out = None
        try:
            if kw.get("check_in"):
                check_in = fields.Date.to_date(kw.get("check_in"))
            if kw.get("check_out"):
                check_out = fields.Date.to_date(kw.get("check_out"))
        except Exception:
            check_in = check_out = None
        if check_in and check_out and check_out <= check_in:
            check_in = check_out = None

        rooms = []
        for index, room in enumerate(prop.room_ids.filtered("active").sorted("sequence"), start=1):
            payload = _serialize_room(room, check_in, check_out)
            payload["code"] = "chambre-%s" % index
            rooms.append(payload)
        return _json(
            {
                "ok": True,
                "property": {
                    "id": prop.id,
                    "name": prop.name,
                    "city": prop.city or "Marrakech",
                    "district": prop.district or "Kasbah",
                    "price_per_night": float(prop.price_per_night or 150),
                    "currency": "EUR",
                    "capacity": int(prop.capacity or 10),
                    "channex_ready": True,
                },
                "rooms": rooms,
            }
        )

    @http.route(
        ["/api/riadanna/reservations", "/api/riadanna/reservations/"],
        type="http",
        auth="public",
        methods=["POST", "OPTIONS"],
        csrf=False,
        cors="*",
    )
    def create_reservation(self, **kw):
        if request.httprequest.method == "OPTIONS":
            return _json({"ok": True})
        data = _body()
        if _clean(data.get("company_website") or data.get("website"), 80):
            return _json({"ok": True, "ignored": True})

        env = request.env
        prop = _riad_property(env)
        if not prop:
            return _json({"ok": False, "error": "property_missing"}, 404)

        try:
            check_in = fields.Date.to_date(data.get("check_in") or data.get("date_debut"))
            check_out = fields.Date.to_date(data.get("check_out") or data.get("date_fin"))
        except Exception:
            return _json({"ok": False, "error": "invalid_dates"}, 400)

        client_nom = _clean(data.get("client_nom") or data.get("name"), 120)
        client_email = _clean(data.get("client_email") or data.get("email"), 120).lower()
        client_tel = _clean(data.get("client_telephone") or data.get("phone"), 40)
        message = _clean(data.get("message") or data.get("notes"), 2000)
        referral = _clean(
            data.get("referral_code")
            or data.get("promo")
            or data.get("ref")
            or data.get("referral"),
            80,
        )
        try:
            voyageurs = max(int(data.get("voyageurs") or data.get("guests") or 1), 1)
        except (TypeError, ValueError):
            voyageurs = 1
        voyageurs = min(voyageurs, 6)

        if not check_in or not check_out or check_out <= check_in:
            return _json({"ok": False, "error": "invalid_dates"}, 400)
        if (check_out - check_in).days > 30:
            return _json({"ok": False, "error": "stay_too_long"}, 400)
        today = fields.Date.context_today(prop)
        if check_in < today:
            return _json({"ok": False, "error": "past_date"}, 400)
        if not client_nom or not client_email or "@" not in client_email:
            return _json({"ok": False, "error": "invalid_client"}, 400)

        room = False
        try:
            room_id = int(data.get("room_id") or 0)
        except (TypeError, ValueError):
            room_id = 0
        if room_id:
            room = env["coins.property.room"].sudo().browse(room_id)
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
                        "detail": "Cette chambre accueille au plus %s personnes."
                        % room.sleeps,
                    },
                    400,
                )
            if _room_blocked(env, prop.id, room.id, check_in, check_out):
                return _json({"ok": False, "error": "unavailable"}, 409)

        nights = (check_out - check_in).days
        prix_nuit = _room_nightly_rate(room) if room else float(prop.price_per_night or 150)
        montant = round(prix_nuit * nights, 2)
        eur = env["res.currency"].sudo().search([("name", "=", "EUR")], limit=1)

        Partner = env["res.partner"].sudo()
        partner = Partner.search([("email", "=ilike", client_email)], limit=1)
        if not partner:
            partner = Partner.create(
                {
                    "name": client_nom,
                    "email": client_email,
                    "phone": client_tel or False,
                    "comment": "Créé via riadanna — Riad Anna Sweety",
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

        note_bits = [
            "Site : agencedoorway.com/riadanna",
            "Voyageurs : %s" % voyageurs,
        ]
        if room:
            note_bits.append("Chambre : %s" % room.name)
        if message:
            note_bits.append(message)
        note_bits.append("Prêt Channex : oui (mapping propriété / chambres à brancher).")

        resa_vals = {
                "traveler_id": partner.id,
                "property_id": prop.id,
                "check_in": check_in,
                "check_out": check_out,
                "state": "draft",
                "source": "direct",
                "booking_channel": "riad_website",
                "meal_breakfast": True,
                "client_nom": client_nom,
                "client_email": client_email,
                "client_telephone": client_tel,
                "currency_id": eur.id if eur else False,
                "amount_property": montant,
                "payment_status": "unpaid",
                "voyageurs": voyageurs,
                "room_id": room.id if room else False,
                "notes": "\n".join(note_bits),
        }
        if referral:
            resa_vals["referral_code"] = referral
        resa = env["coins.reservation"].sudo().create(resa_vals)

        return _json(
            {
                "ok": True,
                "reservation_id": resa.id,
                "reference": resa.name,
                "nights": nights,
                "amount": montant,
                "currency": "EUR",
                "room": room.name if room else None,
                "check_in": fields.Date.to_string(check_in),
                "check_out": fields.Date.to_string(check_out),
            }
        )
