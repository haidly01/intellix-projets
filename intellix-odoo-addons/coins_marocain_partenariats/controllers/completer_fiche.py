# -*- coding: utf-8 -*-
import base64
import json
import logging
import re
from pathlib import Path

from odoo import http
from odoo.http import request
from odoo.modules.module import get_module_path

_logger = logging.getLogger(__name__)

CAT_CODE = {
    "decouverte": "decouverte",
    "hebergement": "hebergement",
    "evenements": "evenements",
    "privatisation": "privatisation",
    "bienetre": "bien_etre",
}

CM_BRAND = {
    "id": "coins_marocain",
    "label": "Coins Marocain",
    "kicker": "COINS MAROCAIN — ESPACE PARTENAIRE",
    "lead": (
        "Votre partenariat est confirmé — il ne reste qu'à remplir les "
        "informations de votre établissement pour qu'il soit visible auprès de nos clients."
    ),
    "theme": {
        "bg": "#f6f4ef",
        "surface": "#ffffff",
        "border": "#e2ddd0",
        "text": "#2a2620",
        "muted": "#8a8375",
        "accent": "#7c5cbf",
        "accentDark": "#6a4bab",
        "accentTint": "#efe9f9",
        "sand": "#c9a876",
        "serif": False,
    },
    "categories": [
        {"id": "decouverte", "label": "Découverte", "desc": "Activité ou expérience à l'unité (journée, atelier, excursion)"},
        {"id": "hebergement", "label": "Hébergement", "desc": "Chambres louables à l'unité"},
        {"id": "evenements", "label": "Événements", "desc": "Réceptions, mariages, séminaires"},
        {"id": "privatisation", "label": "Privatisation", "desc": "Lieu complet réservé en exclusivité"},
        {"id": "bienetre", "label": "Bien-être", "desc": "Massages, soins, hammam", "wide": True},
    ],
}


def _strip_html(html):
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", str(html or ""))).replace("&nbsp;", " ").strip()


def _wizard_from_property(prop):
    codes = prop.category_ids.mapped("code") if prop.category_ids else []
    if getattr(prop, "onboarding_kind", False) == "hebergement" and "hebergement" not in codes:
        codes = list(codes) + ["hebergement"]
    cats = [c["id"] for c in CM_BRAND["categories"] if c["id"] in codes or (c["id"] == "hebergement" and "hebergement" in codes)]
    if not cats and "hebergement" in codes:
        cats = ["hebergement"]
    rooms = []
    if "room_ids" in prop._fields:
        for room in prop.room_ids:
            rooms.append(
                {
                    "nom": room.name or "",
                    "capacite": str(getattr(room, "sleeps", "") or ""),
                    "prix": str(getattr(room, "price_per_night", "") or ""),
                    "description": getattr(room, "description", "") or "",
                }
            )
    ville = ", ".join(p for p in [prop.city or "", getattr(prop, "district", "") or ""] if p)
    photos_n = len(prop.photo_ids) if "photo_ids" in prop._fields else 0
    videos_n = len(prop.fiche_video_ids) if "fiche_video_ids" in prop._fields else 0
    histoire = _strip_html(getattr(prop, "narrative", "") or getattr(prop, "description", "") or "")
    return {
        "etablissement": prop.name or "",
        "ville": ville,
        "contact_nom": getattr(prop, "onboarding_contact_name", "") or "",
        "telephone": getattr(prop, "onboarding_phone", "") or "",
        "courriel": getattr(prop, "onboarding_email", "") or "",
        "categories": cats or ["hebergement"],
        "hebergement": {
            "chambres": rooms,
            "petit_dejeuner": "oui" if getattr(prop, "meal_breakfast_available", None) else "",
            "espaces": ["Piscine"] if getattr(prop, "daypass_piscine", False) else [],
            "espaces_desc": getattr(prop, "amenities", "") or "",
        },
        "histoire": histoire,
        "details": "",
        "video_url": "",
        "media": {"photos": photos_n, "videos": videos_n},
        "menu": [],
        "privatisation": {
            "tarif": str(getattr(prop, "tarif_privatisation_jour", "") or ""),
            "capacite": str(getattr(prop, "capacity", "") or ""),
        },
        "evenements": {},
        "bienetre": {"duree": getattr(prop, "be_duree_moyenne", "") or ""},
        "decouverte": {},
        "currency": (
            prop.currency_id.name
            if getattr(prop, "currency_id", False) and prop.currency_id
            else "EUR"
        ),
    }


class CompleterFicheController(http.Controller):
    def _find_property(self, token):
        token = (token or "").strip()
        if not token:
            return request.env["coins.property"]
        Prop = request.env["coins.property"].sudo()
        return Prop.search([("portal_token", "=", token)], limit=1)

    def _bootstrap(self, prop):
        wizard = _wizard_from_property(prop)
        prefilled = {
            k: bool(wizard.get(k))
            for k in ("etablissement", "ville", "contact_nom", "telephone", "courriel")
        }
        return {
            "token": prop.portal_token,
            "brand": CM_BRAND,
            "wizard": wizard,
            "prefilled": prefilled,
            "odoo": {"model": "coins.property", "id": prop.id, "module": "coins_marocain"},
        }

    @http.route(
        ["/coins/completer-fiche/<string:token>"],
        type="http",
        auth="public",
        csrf=False,
        website=False,
    )
    def completer_fiche(self, token, **kwargs):
        prop = self._find_property(token)
        if not prop:
            return request.not_found()
        module_path = Path(get_module_path("coins_marocain_partenariats"))
        html_path = module_path / "static" / "src" / "fiche-maquette" / "index.html"
        html = html_path.read_text(encoding="utf-8")
        inject = (
            "<script>window.FICHE_BOOTSTRAP = %s;</script>"
            % json.dumps(self._bootstrap(prop), ensure_ascii=False)
        )
        html = html.replace("</head>", inject + "\n</head>", 1)
        return request.make_response(html, headers=[("Content-Type", "text/html; charset=utf-8")])

    def _json(self, payload, status=200):
        return request.make_response(
            json.dumps(payload, ensure_ascii=False),
            headers=[("Content-Type", "application/json; charset=utf-8")],
            status=status,
        )

    @http.route(
        ["/api/partenaire/<string:token>"],
        type="http",
        auth="public",
        csrf=False,
        methods=["GET"],
    )
    def api_partenaire_get(self, token, **kwargs):
        prop = self._find_property(token)
        if not prop:
            return self._json({"error": "Lien partenaire invalide ou expiré."}, 404)
        return self._json(self._bootstrap(prop))

    @http.route(
        ["/api/partenaire/<string:token>/fiche"],
        type="http",
        auth="public",
        csrf=False,
        methods=["POST"],
    )
    def api_partenaire_fiche(self, token, **kwargs):
        prop = self._find_property(token)
        if not prop:
            return self._json({"error": "Lien partenaire invalide ou expiré."}, 404)
        try:
            wizard = self._parse_wizard()
        except (json.JSONDecodeError, TypeError, ValueError):
            return self._json({"error": "Données de fiche illisibles."}, 400)
        if not str(wizard.get("etablissement") or prop.name or "").strip():
            return self._json({"error": "Le nom de l’établissement est obligatoire."}, 400)
        cats = wizard.get("categories") or []
        if not isinstance(cats, list) or not cats:
            return self._json({"error": "Choisissez au moins une catégorie."}, 400)
        try:
            written = self._save_wizard(prop, wizard)
        except Exception:
            _logger.exception("envoi fiche partenaire token=%s", token)
            return self._json(
                {"error": "L’enregistrement a échoué. Réessayez, ou écrivez à Zakaria."},
                500,
            )
        return self._json({"ok": True, "id": prop.id, "odoo_written": written})

    def _parse_wizard(self):
        form = request.httprequest.form
        raw = form.get("payload") if form else None
        if raw:
            data = json.loads(raw)
            return data.get("wizard") or data
        body = request.httprequest.get_data(cache=True) or b"{}"
        if not body.strip():
            return {}
        data = json.loads(body.decode("utf-8"))
        return data.get("wizard") or data

    def _empty(self, value):
        if value is None:
            return True
        if isinstance(value, bool):
            return False
        if isinstance(value, (int, float)):
            return False
        if isinstance(value, (list, dict)):
            return len(value) == 0
        return not str(value).strip()

    def _sparse_vals(self, prop, incoming):
        vals = {}
        for key, nxt in incoming.items():
            if key not in prop._fields:
                continue
            if self._empty(nxt):
                continue
            prev = prop[key]
            if not self._empty(prev) and str(prev).strip() == str(nxt).strip():
                continue
            vals[key] = nxt
        return vals

    def _number(self, value):
        if value is None or value == "":
            return None
        try:
            return float(str(value).replace(",", ".").replace(" ", ""))
        except (TypeError, ValueError):
            return None

    def _save_wizard(self, prop, wizard):
        heberg = wizard.get("hebergement") or {}
        priv = wizard.get("privatisation") or {}
        evt = wizard.get("evenements") or {}
        be = wizard.get("bienetre") or {}
        ville = str(wizard.get("ville") or "")
        city = ville.split(",")[0].strip()
        district = ville.split(",", 1)[1].strip() if "," in ville else ""
        rooms = heberg.get("chambres") or []
        capacity = sum(int(self._number(r.get("capacite")) or 0) for r in rooms) or None
        story_parts = [
            str(wizard.get("histoire") or "").strip(),
            str(wizard.get("details") or "").strip(),
        ]
        story = "\n\n".join(p for p in story_parts if p)
        incoming = {
            "name": wizard.get("etablissement"),
            "city": city,
            "district": district,
            "onboarding_contact_name": wizard.get("contact_nom"),
            "onboarding_phone": wizard.get("telephone"),
            "onboarding_email": wizard.get("courriel"),
            "amenities": heberg.get("espaces_desc"),
            "narrative": story or None,
            "description": story or None,
            "be_duree_moyenne": be.get("duree"),
            "tarif_privatisation_jour": self._number(priv.get("tarif")),
            "capacity": capacity or self._number(priv.get("capacite")),
            "rg_capacite_groupe_max": self._number(evt.get("capacite")),
            "onboarding_status": "en_attente_validation",
        }
        cur_code = str(wizard.get("currency") or "").strip().upper()
        if not cur_code:
            rooms_cur = [
                str(r.get("currency") or "").strip().upper()
                for r in rooms
                if str(r.get("currency") or "").strip()
            ]
            cur_code = rooms_cur[0] if rooms_cur else ""
        if cur_code in ("EUR", "MAD", "CAD"):
            cur = request.env["res.currency"].sudo().search(
                [("name", "=", cur_code)], limit=1
            )
            if cur:
                incoming["currency_id"] = cur.id
        if heberg.get("petit_dejeuner") in ("oui", "non"):
            incoming["meal_breakfast_available"] = heberg.get("petit_dejeuner") == "oui"
        espaces = heberg.get("espaces") or []
        if any(re.search(r"piscine", str(a), re.I) for a in espaces):
            incoming["daypass_piscine"] = True
        cats = wizard.get("categories") or []
        if "privatisation" in cats:
            incoming["rg_privatisation_possible"] = True
        if "hebergement" in cats:
            incoming["location_chambre_unite"] = True
            incoming["onboarding_kind"] = "hebergement"
        vals = self._sparse_vals(prop, incoming)
        if vals:
            prop.with_context(coins_partner_portal=True).write(vals)
        self._add_categories(prop, cats)
        self._upsert_rooms(prop, rooms)
        self._save_uploads(prop)
        self._save_video_url(prop, wizard.get("video_url"))
        self._notify_team(prop)
        return list(vals.keys())

    def _add_categories(self, prop, cat_ids):
        if "category_ids" not in prop._fields:
            return
        Cat = request.env["coins.property.category"].sudo()
        have = set(prop.category_ids.mapped("code"))
        add = []
        for cid in cat_ids:
            code = CAT_CODE.get(cid)
            if not code or code in have:
                continue
            rec = Cat.search([("code", "=", code)], limit=1)
            if rec:
                add.append(rec.id)
                have.add(code)
        if add:
            prop.write({"category_ids": [(4, i) for i in add]})

    def _upsert_rooms(self, prop, rooms):
        if "room_ids" not in prop._fields or not rooms:
            return
        Room = request.env["coins.property.room"].sudo()
        existing = {(r.name or "").strip().lower(): r for r in prop.room_ids}
        for seq, room in enumerate(rooms, start=1):
            name = str(room.get("nom") or "").strip()
            if not name:
                continue
            vals = {"name": name, "sequence": seq * 10, "active": True, "property_id": prop.id}
            sleeps = int(self._number(room.get("capacite")) or 0)
            if sleeps and "sleeps" in Room._fields:
                vals["sleeps"] = sleeps
            price = self._number(room.get("prix"))
            if price and "price_per_night" in Room._fields:
                vals["price_per_night"] = price
            desc = str(room.get("description") or "").strip()
            if desc and "description" in Room._fields:
                vals["description"] = desc
            hit = existing.get(name.lower())
            if hit:
                hit.write({k: v for k, v in vals.items() if k != "property_id"})
                rec = hit
            else:
                rec = Room.create(vals)
                existing[name.lower()] = rec
            self._save_room_photos(prop, rec, seq - 1)

    def _save_room_photos(self, prop, room, index):
        files = request.httprequest.files
        uploads = files.getlist("room_photos_%s" % index)
        Photo = request.env["coins.property.photo"].sudo() if "coins.property.photo" in request.env else None
        if not Photo:
            return
        for upload in uploads:
            raw = upload.read() if upload else b""
            if not raw:
                continue
            Photo.create(
                {
                    "property_id": prop.id,
                    "room_id": room.id,
                    "image": base64.b64encode(raw),
                    "legende": (upload.filename or room.name or "")[:80],
                }
            )

    def _save_video_url(self, prop, url):
        url = str(url or "").strip()
        if not url or "coins.fiche_video" not in request.env:
            return
        Video = request.env["coins.fiche_video"].sudo()
        if Video.search([("fiche_id", "=", prop.id), ("video_url", "=", url)], limit=1):
            return
        vals = {
            "fiche_id": prop.id,
            "source": "proprietaire",
            "video_url": url,
            "titre": "Vidéo partenaire",
            "statut": "en_attente",
        }
        Video.create(vals)

    def _public_attachment_url(self, attachment):
        base = (request.env["ir.config_parameter"].sudo().get_param("web.base.url") or "").rstrip("/")
        if not base:
            base = (request.httprequest.host_url or "").rstrip("/")
        return "%s/web/content/%s" % (base, attachment.id)

    def _save_uploads(self, prop):
        files = request.httprequest.files
        Photo = request.env["coins.property.photo"].sudo() if "coins.property.photo" in request.env else None
        for upload in files.getlist("photos"):
            raw = upload.read() if upload else b""
            if not raw or not Photo:
                continue
            Photo.create(
                {
                    "property_id": prop.id,
                    "image": base64.b64encode(raw),
                    "legende": (upload.filename or "")[:80],
                }
            )
        Attach = request.env["ir.attachment"].sudo()
        for upload in files.getlist("videos"):
            raw = upload.read() if upload else b""
            if not raw:
                continue
            att = Attach.create(
                {
                    "name": (upload.filename or "video")[:80],
                    "res_model": "coins.property",
                    "res_id": prop.id,
                    "type": "binary",
                    "datas": base64.b64encode(raw),
                    "mimetype": getattr(upload, "mimetype", None) or "application/octet-stream",
                }
            )
            self._save_video_url(prop, self._public_attachment_url(att))

    def _notify_team(self, prop):
        try:
            if hasattr(prop, "_notify_karine_onboarding_submission"):
                prop._notify_karine_onboarding_submission()
        except Exception:
            _logger.exception("notification fiche %s", prop.id)
        try:
            if "message_post" in dir(prop):
                prop.message_post(
                    body="Fiche partenaire reçue via Compléter ma fiche.",
                    subtype_xmlid="mail.mt_note",
                )
        except Exception:
            _logger.exception("chatter fiche %s", prop.id)
        Lead = request.env["crm.lead"].sudo()
        domain = []
        if "coins_property_id" in Lead._fields:
            domain = [("coins_property_id", "=", prop.id)]
        elif "coins_etablissement" in Lead._fields:
            domain = [("coins_etablissement", "ilike", prop.name)]
        if domain:
            lead = Lead.search(domain, limit=1)
            if lead:
                lead.message_post(
                    body="La partenaire a renvoyé sa fiche (%s). Statut : en attente de validation."
                    % (prop.name or ""),
                    subtype_xmlid="mail.mt_note",
                )
