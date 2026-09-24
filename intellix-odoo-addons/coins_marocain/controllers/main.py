# -*- coding: utf-8 -*-
"""API publique du site coinsmarocain.com -> Odoo.

Le site statique (coinsmarocain.com) poste en same-origin via un proxy nginx
(`/coins/api/...` -> 127.0.0.1:8069). Ces endpoints créent la vérité côté Odoo :
- questionnaire séjour  -> crm.lead
- demande ambassadeur   -> crm.lead
- candidature partenaire-> coins.partner_activity
- concierge Yasmine     -> Claude + bridge WhatsApp bot
"""
import base64
import hashlib
import json
import logging
import re
import unicodedata

from odoo import http
from odoo.http import request
from odoo.addons.coins_marocain.models.room_public_copy import public_room_description

from odoo.addons.coins_marocain.services.yasmine_service import (
    CONCIERGE_SYSTEM_WEB,
    YasmineService,
)

_logger = logging.getLogger(__name__)

_CORS = {
    "Access-Control-Allow-Origin": "*",
    "Access-Control-Allow-Methods": "POST, OPTIONS",
    "Access-Control-Allow-Headers": "Content-Type",
}

_SIGNUP_PHOTO_MAX = 5 * 1024 * 1024  # 5 Mo
_SIGNUP_PHOTO_MIME = {
    "image/jpeg",
    "image/jpg",
    "image/png",
    "image/webp",
}


def _json(payload, status=200):
    headers = [("Content-Type", "application/json")] + list(_CORS.items())
    return request.make_response(json.dumps(payload), headers=headers, status=status)


def _body():
    """JSON body, or form fields (multipart / urlencoded)."""
    req = request.httprequest
    ctype = (req.content_type or "").lower()
    if "application/json" in ctype:
        try:
            raw = req.get_data(as_text=True) or "{}"
            return json.loads(raw)
        except Exception:
            return {}
    # multipart / form-urlencoded — values already in kw via **kw, but
    # also expose request.params for callers that use _body() alone.
    data = {}
    try:
        for key in req.form:
            data[key] = req.form.get(key)
    except Exception:
        pass
    if not data:
        try:
            data = dict(request.params or {})
        except Exception:
            data = {}
    return data


def _clean(v, maxlen=300):
    if not v:
        return ""
    return str(v).strip()[:maxlen]


def _read_signup_photo():
    """Return (base64_str|False, error_code|None) from multipart field photo/image."""
    files = request.httprequest.files
    upload = files.get("photo") or files.get("image") or files.get("image_1920")
    if not upload:
        return False, None
    raw = upload.read()
    if not raw:
        return False, None
    if len(raw) > _SIGNUP_PHOTO_MAX:
        return False, "photo_too_large"
    mime = (getattr(upload, "content_type", None) or "").split(";")[0].strip().lower()
    # Some browsers omit type — sniff extension
    fname = (getattr(upload, "filename", None) or "").lower()
    if not mime or mime == "application/octet-stream":
        if fname.endswith((".jpg", ".jpeg")):
            mime = "image/jpeg"
        elif fname.endswith(".png"):
            mime = "image/png"
        elif fname.endswith(".webp"):
            mime = "image/webp"
    if mime not in _SIGNUP_PHOTO_MIME:
        return False, "photo_type"
    return base64.b64encode(raw).decode("ascii"), None


def _get_tag(name):
    Tag = request.env["crm.tag"].sudo()
    tag = Tag.search([("name", "=", name)], limit=1)
    if not tag:
        tag = Tag.create({"name": name})
    return tag.id


def _upsert_contact_voyageur_lead(
    partner,
    name,
    email,
    phone,
    note_block,
    event_type,
    taille_int,
    budget,
    date_arrivee,
):
    """Formulaire Contact voyageur → pipeline Voyageurs Coins Marocain."""
    Lead = request.env["crm.lead"].sudo()
    team = request.env.ref(
        "coins_marocain_partenariats.crm_team_coins_voyageurs",
        raise_if_not_found=False,
    )
    stage = request.env.ref(
        "coins_marocain_partenariats.crm_stage_voy_nouveau",
        raise_if_not_found=False,
    )
    existing = Lead.with_context(active_test=False).search(
        [
            ("coins_fiche_type", "=", "voyageur"),
            "|",
            ("partner_id", "=", partner.id),
            ("email_from", "=ilike", email),
        ],
        limit=1,
    )
    event_ok = event_type if event_type in (
        "mariage",
        "anniversaire",
        "seminaire",
        "groupe_amis",
        "reunion_famille",
        "autre",
    ) else "mariage" if event_type in ("evjf", "soiree", "privatisation") else (
        "autre" if event_type else False
    )
    service = {
        "mariage": "Fiançailles / mariage",
        "anniversaire": "Anniversaire",
        "groupe_amis": "Moment festif amis / famille",
        "reunion_famille": "Réunion de famille",
        "seminaire": "Séminaire",
    }.get(event_ok or "", "Demande formulaire site")
    vals = {
        "name": name,
        "contact_name": name,
        "partner_id": partner.id,
        "email_from": email,
        "phone": phone or False,
        "coins_whatsapp": phone or False,
        "description": note_block,
        "type": "opportunity",
        "coins_fiche_type": "voyageur",
        "coins_canal_origine": "site",
        "coins_service_demande": service,
        "coins_voyageur_budget": budget or False,
        "coins_type_evenement": event_ok or False,
        "coins_nombre_personnes": taille_int or False,
        "coins_date_souhaitee": date_arrivee or False,
        "coins_xsell_evenements": bool(event_ok),
    }
    if team:
        vals["team_id"] = team.id
    if stage:
        vals["stage_id"] = stage.id
    if existing:
        existing.write(vals)
        if not existing.active:
            existing.active = True
        return existing
    return Lead.create(vals)


class CoinsMarocainApi(http.Controller):

    @http.route(
        "/coins/api/questionnaire",
        type="http", auth="public", methods=["POST", "OPTIONS"],
        csrf=False, cors="*",
    )
    def questionnaire(self, **kw):
        if request.httprequest.method == "OPTIONS":
            return _json({"ok": True})
        d = _body()
        name = _clean(d.get("name")) or "Voyageur"
        email = _clean(d.get("email"), 120)
        if not email or "@" not in email:
            return _json({"ok": False, "error": "email"}, 400)
        desc = (
            "Questionnaire séjour sur mesure (site coinsmarocain.com)\n"
            f"- Destination : {_clean(d.get('destination'))}\n"
            f"- Expérience : {_clean(d.get('experience'))}\n"
            f"- Budget : {_clean(d.get('budget'))}\n"
            f"- Période : {_clean(d.get('periode'))}\n"
        )
        try:
            team = request.env.ref(
                "coins_marocain_partenariats.crm_team_coins_voyageurs",
                raise_if_not_found=False,
            )
            stage = request.env.ref(
                "coins_marocain_partenariats.crm_stage_voy_nouveau",
                raise_if_not_found=False,
            )
            vals = {
                "name": f"Séjour Coins Marocain — {name}",
                "contact_name": name,
                "email_from": email,
                "description": desc,
                "type": "opportunity",
                "coins_fiche_type": "voyageur",
                "coins_canal_origine": "site",
                "tag_ids": [(4, _get_tag("Coins — Questionnaire"))],
            }
            if team:
                vals["team_id"] = team.id
            if stage:
                vals["stage_id"] = stage.id
            request.env["crm.lead"].sudo().create(vals)
        except Exception as e:  # noqa: BLE001
            _logger.exception("coins questionnaire fail: %s", e)
            return _json({"ok": False, "error": "server"}, 500)
        return _json({"ok": True})

    @http.route(
        "/coins/api/ambassador",
        type="http", auth="public", methods=["POST", "OPTIONS"],
        csrf=False, cors="*",
    )
    def ambassador(self, **kw):
        if request.httprequest.method == "OPTIONS":
            return _json({"ok": True})
        d = _body()
        name = _clean(d.get("name")) or "Ambassadeur"
        email = _clean(d.get("email"), 120)
        phone = _clean(d.get("phone"), 40)
        if not email or "@" not in email:
            return _json({"ok": False, "error": "email"}, 400)
        try:
            request.env["crm.lead"].sudo().create({
                "name": f"Ambassadeur Coins Marocain — {name}",
                "contact_name": name,
                "email_from": email,
                "phone": phone or False,
                "description": "Demande programme Ambassadeur (site).",
                "tag_ids": [(4, _get_tag("Coins — Ambassadeur"))],
            })
        except Exception as e:  # noqa: BLE001
            _logger.exception("coins ambassador fail: %s", e)
            return _json({"ok": False, "error": "server"}, 500)
        return _json({"ok": True})

    @http.route(
        "/coins/api/contact",
        type="http", auth="public", methods=["POST", "OPTIONS"],
        csrf=False, cors="*",
    )
    def contact_form(self, **kw):
        """Formulaire page Contact → upsert res.partner (section Qualification)."""
        if request.httprequest.method == "OPTIONS":
            return _json({"ok": True})
        d = _body()
        req_type = _clean(d.get("request_type"), 20).lower()
        if req_type not in ("voyageur", "entreprise"):
            return _json({"ok": False, "error": "request_type"}, 400)

        name = _clean(d.get("name"), 120)
        email = _clean(d.get("email"), 120)
        phone = _clean(d.get("phone"), 40)
        message = _clean(d.get("message"), 2000)
        if not name:
            return _json({"ok": False, "error": "name"}, 400)
        if not email or "@" not in email:
            return _json({"ok": False, "error": "email"}, 400)
        if not phone:
            return _json({"ok": False, "error": "phone"}, 400)

        consent = bool(d.get("consentement_promo_whatsapp"))
        budget = _clean(d.get("budget"), 40)
        allowed_budget = {"lt_500", "500_1500", "1500_3000", "gt_3000"}
        if budget and budget not in allowed_budget:
            budget = ""

        def _parse_date(key):
            raw = _clean(d.get(key), 20)
            if not raw or len(raw) < 8:
                return False
            try:
                from datetime import datetime
                return datetime.strptime(raw[:10], "%Y-%m-%d").date()
            except ValueError:
                return False

        date_arrivee = _parse_date("date_arrivee")
        date_depart = _parse_date("date_depart")
        Interest = request.env["coins.partner.interest"].sudo()
        Partner = request.env["res.partner"].sudo()

        interest_codes = d.get("interests") or []
        if not isinstance(interest_codes, list):
            interest_codes = []
        interest_codes = [
            _clean(c, 40) for c in interest_codes if _clean(c, 40)
        ]
        if req_type == "entreprise" and "corporate" not in interest_codes:
            interest_codes.append("corporate")
        interest_ids = []
        if interest_codes:
            interest_ids = Interest.search([("code", "in", interest_codes)]).ids

        taille = d.get("taille_groupe")
        try:
            taille_int = int(taille) if taille not in (None, "", False) else False
        except (TypeError, ValueError):
            taille_int = False
        if taille_int is not False and (taille_int < 1 or taille_int > 500):
            taille_int = False

        company_name = _clean(d.get("company_name"), 120)
        event_type = _clean(d.get("event_type"), 40)
        event_labels = {
            "mariage": "Mariage",
            "evjf": "EVJF / EVG",
            "anniversaire": "Anniversaire",
            "soiree": "Soirée privée",
            "team_building": "Team building / retraite dirigeants",
            "gala": "Gala / levée de fonds",
            "privatisation": "Privatisation",
            "autre": "Autre",
        }
        event_label = event_labels.get(event_type, event_type)

        note_bits = [
            "[Formulaire site — %s]" % ("Voyageur" if req_type == "voyageur" else "Entreprise"),
        ]
        if company_name:
            note_bits.append("Entreprise : %s" % company_name)
        if event_label:
            note_bits.append("Type d'événement : %s" % event_label)
        if message:
            note_bits.append("Message : %s" % message)
        note_block = "\n".join(note_bits)

        partner = Partner.search([("email", "=ilike", email)], limit=1)
        if not partner and phone:
            # Odoo 19 : plus de champ mobile sur res.partner — phone uniquement
            partner = Partner.search([("phone", "=", phone)], limit=1)

        vals = {
            "name": name,
            "email": email,
            "phone": phone,
            "coins_consentement_promo_whatsapp": consent,
            "coins_source_connaissance": "formulaire_site",
            "coins_is_traveler": req_type == "voyageur",
        }
        if taille_int:
            vals["coins_taille_groupe_habituelle"] = taille_int
        if date_arrivee:
            vals["coins_date_arrivee"] = date_arrivee
        if date_depart:
            vals["coins_date_depart"] = date_depart

        if req_type == "voyageur":
            vals["coins_local_ou_voyageur"] = "touriste"
            if budget:
                vals["coins_budget_approximatif"] = budget
        else:
            vals["coins_type_groupe"] = "corporate"
            if company_name:
                vals["company_name"] = company_name
            if event_label:
                vals["coins_autre_occasion_recurrente"] = event_label

        try:
            if partner:
                existing_notes = (partner.coins_notes_terrain or "").strip()
                vals["coins_notes_terrain"] = (
                    (existing_notes + "\n\n" + note_block).strip()
                    if existing_notes
                    else note_block
                )
                if interest_ids:
                    merged = list(set(partner.coins_interet_ids.ids + interest_ids))
                    vals["coins_interet_ids"] = [(6, 0, merged)]
                partner.write(vals)
            else:
                vals["coins_notes_terrain"] = note_block
                if interest_ids:
                    vals["coins_interet_ids"] = [(6, 0, interest_ids)]
                partner = Partner.create(vals)

            try:
                partner.message_post(
                    body=note_block.replace("\n", "<br/>"),
                    subject="Formulaire site Coins Marocain",
                    message_type="comment",
                    subtype_xmlid="mail.mt_note",
                )
            except Exception as e:  # noqa: BLE001
                _logger.warning("coins contact chatter fail: %s", e)

            mail_to = (
                request.env["ir.config_parameter"]
                .sudo()
                .get_param(
                    "coins_marocain.contact_notify_email",
                    "karine@agencedoorway.com,zakaria@agencedoorway.com",
                )
            )
            body_html = (
                "<p>Nouvelle demande via le formulaire Contact (coinsmarocain.com).</p>"
                "<ul>"
                "<li><strong>Type</strong> : %s</li>"
                "<li><strong>Nom</strong> : %s</li>"
                "<li><strong>Email</strong> : %s</li>"
                "<li><strong>Téléphone</strong> : %s</li>"
                "%s"
                "<li><strong>Consentement promo WA</strong> : %s</li>"
                "<li><strong>Contact Odoo</strong> : #%s</li>"
                "</ul>"
                "<p>%s</p>"
            ) % (
                "Voyageur" if req_type == "voyageur" else "Entreprise",
                name,
                email,
                phone,
                ("<li><strong>Entreprise</strong> : %s</li>" % company_name)
                if company_name
                else "",
                "oui" if consent else "non",
                partner.id,
                note_block.replace("\n", "<br/>"),
            )
            request.env["mail.mail"].sudo().create({
                "subject": "[Coins] Formulaire Contact — %s (%s)" % (
                    name,
                    "Voyageur" if req_type == "voyageur" else "Entreprise",
                ),
                "body_html": body_html,
                "email_to": mail_to,
                "auto_delete": True,
            }).send()

            request.env["mail.mail"].sudo().create({
                "subject": "Coins Marocain — nous avons bien reçu votre message",
                "body_html": (
                    "<p>Bonjour %s,</p>"
                    "<p>Merci pour votre message. Notre équipe vous répond "
                    "rapidement — vous pouvez aussi nous joindre sur WhatsApp "
                    "au +212 660 15 91 77.</p>"
                    "<p>À bientôt,<br/>Coins Marocain</p>"
                ) % name,
                "email_to": email,
                "auto_delete": True,
            }).send()
            lead = None
            if req_type == "voyageur":
                lead = _upsert_contact_voyageur_lead(
                    partner,
                    name=name,
                    email=email,
                    phone=phone,
                    note_block=note_block,
                    event_type=event_type,
                    taille_int=taille_int,
                    budget=budget,
                    date_arrivee=date_arrivee,
                )
        except Exception as e:  # noqa: BLE001
            _logger.exception("coins contact form fail: %s", e)
            return _json({"ok": False, "error": "server"}, 500)
        payload = {"ok": True, "partner_id": partner.id}
        if lead:
            payload["lead_id"] = lead.id
        return _json(payload)

    # ---- Carte Google Maps (pins vidéo) + inscription libre-service ----

    _MARRAKECH_LAT = 31.6295
    _MARRAKECH_LNG = -7.9811
    # ~30 min de route ≈ 40 km
    _CARTE_RADIUS_KM = 40.0

    @staticmethod
    def _haversine_km(lat1, lng1, lat2, lng2):
        from math import asin, cos, radians, sin, sqrt
        r = 6371.0
        dlat = radians(lat2 - lat1)
        dlng = radians(lng2 - lng1)
        a = (
            sin(dlat / 2) ** 2
            + cos(radians(lat1)) * cos(radians(lat2)) * sin(dlng / 2) ** 2
        )
        return 2 * r * asin(sqrt(a))

    def _map_pillar_for(self, prop):
        if prop.map_pillar:
            return prop.map_pillar
        codes = set(prop.category_ids.mapped("code") or [])
        if "route_gourmande" in codes:
            return "route_gourmande"
        if "bien_etre" in codes:
            return "bien_etre"
        if "evenements" in codes:
            return "evenements"
        if "hebergement" in codes or prop.property_type in (
            "riad",
            "villa",
            "apartment",
            "pool_hammam",
        ):
            return "villas_riads"
        return "experiences"

    @staticmethod
    def _rg_payload(prop):
        """Champs Route gourmande exposés à la carte (filtres)."""
        if not hasattr(prop, "rg_cuisine"):
            return {}
        return {
            "cuisine": prop.rg_cuisine or "",
            "cadre": prop.rg_cadre_list() if hasattr(prop, "rg_cadre_list") else [],
            "alcool": prop.rg_alcool or "",
            "animations": (
                prop.rg_animations_list()
                if hasattr(prop, "rg_animations_list")
                else []
            ),
            "capacite_couverts": prop.rg_capacite_couverts or 0,
            "capacite_groupe_max": prop.rg_capacite_groupe_max or 0,
            "privatisation_possible": bool(prop.rg_privatisation_possible),
            "ambiance": prop.rg_ambiance or "",
            "vue": prop.rg_vue or "",
            "fourchette_prix": prop.rg_fourchette_prix or "",
        }

    @staticmethod
    def _be_payload(prop):
        """Champs Route bien-être exposés à la carte (filtres)."""
        if not hasattr(prop, "be_type_lieu"):
            return {}
        prestataire = ""
        if hasattr(prop, "be_prestataire_label"):
            prestataire = prop.be_prestataire_label()
        elif prop.be_type_lieu == "villa_evenementiel":
            prestataire = (
                prop.detente_partner_id.name if prop.detente_partner_id else ""
            ) or "Zen Traitements"
        else:
            prestataire = prop.be_prestataire_libre or ""
        return {
            "type_lieu": prop.be_type_lieu or "",
            "services": (
                prop.be_services_list() if hasattr(prop, "be_services_list") else []
            ),
            "mixte": prop.be_mixte or "",
            "capacite_simultanee": prop.be_capacite_simultanee or 0,
            "prestataire": prestataire,
            "cadre": prop.be_cadre_list() if hasattr(prop, "be_cadre_list") else [],
            "ambiance": prop.be_ambiance or "",
            "duree_moyenne": prop.be_duree_moyenne or "",
            "fourchette_prix": prop.be_fourchette_prix or "",
        }

    @staticmethod
    def _slugify(text):
        raw = unicodedata.normalize("NFKD", text or "")
        raw = "".join(c for c in raw if not unicodedata.combining(c))
        raw = raw.lower()
        slug = re.sub(r"[^a-z0-9]+", "-", raw).strip("-")
        return slug or "lieu"

    def _property_detail_url(self, prop):
        """Fiche publique du lieu (pas la liste activités / forfaits)."""
        slug = self._slugify(prop.name)
        if slug in ("la-casa-ysabella", "casa-ysabella"):
            return "/lieux/riad-medina-marrakech-la-casa-ysabella"
        if slug == "riad-asrari":
            return "/lieux/riad-asrari-medina-marrakech"
        return "/lieux/%s" % slug

    @staticmethod
    def _snippet_url(video_url):
        """URL courte pour hover carte : foo.mp4 → foo-snippet.mp4."""
        if not video_url:
            return ""
        return re.sub(r"\.mp4(\?|$)", r"-snippet.mp4\1", video_url, flags=re.I)

    def _property_photos(self, prop):
        photos = []
        for ph in prop.photo_ids.sorted("sequence"):
            if not getattr(ph, "image", None):
                continue
            base = "/api/coins-marocain/photos/%s" % ph.id
            photos.append({
                "id": ph.id,
                "url": "%s?w=720" % base,
                "url_thumb": "%s?w=360" % base,
                "url_full": "%s?w=1600" % base,
                "legende": ph.legende or "",
                "room_id": ph.room_id.id if ph.room_id else 0,
                "categories": [
                    {"code": c.code, "label": c.name}
                    for c in ph.category_ids
                    if c.code
                ],
                "category_codes": (
                    ph.public_category_codes()
                    if hasattr(ph, "public_category_codes")
                    else []
                ),
            })
        if not photos and getattr(prop, "image_1920", None):
            base = "/api/coins-marocain/photos/property/%s" % prop.id
            photos.append({
                "id": "main",
                "url": "%s?w=720" % base,
                "url_thumb": "%s?w=360" % base,
                "url_full": "%s?w=1600" % base,
                "legende": prop.name or "",
            })
        return photos

    def _property_rooms(self, prop):
        rooms = []
        for r in prop.room_ids.filtered("active").sorted("sequence"):
            room_cur = ""
            if getattr(r, "currency_id", False):
                room_cur = r.currency_id.name or ""
            elif getattr(prop, "currency_id", False):
                room_cur = prop.currency_id.name or ""
            rooms.append({
                "id": r.id,
                "nom": r.name,
                "sleeps": r.sleeps or 0,
                "description": public_room_description(r.description or ""),
                "price_per_night": float(r.price_per_night or 0.0),
                "currency": room_cur,
                "breakfast_included": bool(getattr(r, "breakfast_included", False)),
            })
        return rooms

    def _property_amenities(self, prop):
        raw = prop.amenities or ""
        return [x.strip() for x in re.split(r"[,;\n]+", raw) if x.strip()]

    def _property_reviews(self, prop):
        """Avis publiés seulement — jamais les brouillons « à valider »."""
        if not hasattr(prop, "published_reviews"):
            return []
        out = []
        for r in prop.published_reviews():
            out.append({
                "texte": r.texte or "",
                "auteur": r.author_name or "Voyageur",
                "note": r.note or 0,
            })
        return out

    def _property_nearby(self, prop, limit=3):
        """Autres lieux publiés, même catégorie principale — pas d’invention."""
        Prop = request.env["coins.property"].sudo()
        codes = set(prop.category_ids.mapped("code"))
        domain = [
            ("active", "=", True),
            ("state", "=", "active"),
            ("id", "!=", prop.id),
        ] + Prop._domain_exclude_unpublished_onboarding()
        others = Prop.search(domain, order="name")
        out = []
        for p in others:
            if codes and not (set(p.category_ids.mapped("code")) & codes):
                continue
            photos = self._property_photos(p)
            out.append({
                "id": p.id,
                "name": p.name,
                "slug": self._slugify(p.name),
                "detail_url": self._property_detail_url(p),
                "city": p.city or "Marrakech",
                "district": p.district or "",
                "photo_url": (photos[0]["url"] if photos else ""),
                "categories": [c.code for c in p.category_ids if c.code],
            })
            if len(out) >= limit:
                break
        return out

    @http.route(
        "/coins/api/carte/config",
        type="http", auth="public", methods=["GET", "OPTIONS"],
        csrf=False, cors="*",
    )
    def carte_config(self, **kw):
        if request.httprequest.method == "OPTIONS":
            return _json({"ok": True})
        key = (
            request.env["ir.config_parameter"]
            .sudo()
            .get_param("coins_marocain.google_maps_browser_key", "")
        )
        return _json({
            "ok": True,
            "google_maps_key": key,
            "center": {"lat": self._MARRAKECH_LAT, "lng": self._MARRAKECH_LNG},
            "radius_km": self._CARTE_RADIUS_KM,
        })

    def _viewer_key(self):
        ip = (
            request.httprequest.headers.get("X-Forwarded-For", "")
            .split(",")[0]
            .strip()
            or request.httprequest.remote_addr
            or ""
        )
        ua = request.httprequest.headers.get("User-Agent", "")[:80]
        raw = "%s|%s" % (ip, ua)
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:32]

    @http.route(
        "/coins/api/carte/pins",
        type="http", auth="public", methods=["GET", "OPTIONS"],
        csrf=False, cors="*",
    )
    def carte_pins(self, **kw):
        """Pins = biens actifs avec ≥1 vidéo publiée, dans le rayon Marrakech."""
        if request.httprequest.method == "OPTIONS":
            return _json({"ok": True})
        Video = request.env["coins.fiche_video"].sudo()
        View = request.env["coins.fiche_video.view"].sudo()
        trending_ids = View.trending_fiche_ids(limit=3)
        videos = Video.search([
            ("statut", "=", "publiee"),
            ("fiche_id.active", "=", True),
            ("fiche_id.state", "=", "active"),
            ("fiche_id.latitude", "!=", 0),
            ("fiche_id.longitude", "!=", 0),
        ] + request.env["coins.property"]._domain_exclude_unpublished_onboarding(
            "fiche_id"
        ), order="ordre_affichage, id")

        by_fiche = {}
        cat_labels = {
            "decouverte": "Découverte",
            "privatisation": "Privatisation",
            "evenements": "Événements",
            "bien_etre": "Bien-être",
            "hebergement": "Hébergement",
            "route_gourmande": "Route gourmande",
        }
        pillar_labels = {
            "villas_riads": "Hébergement",
            "bien_etre": "Bien-être",
            "route_gourmande": "Route gourmande",
            "plein_air": "Plein air & sport",
            "experiences": "Expériences",
            "evenements": "Événements",
        }
        for v in videos:
            prop = v.fiche_id
            # Carte publique = catégorie Découverte uniquement (adresse exacte).
            if not prop.is_carte_public():
                continue
            city = (prop.city or "").strip().lower()
            if "essaouira" in city:
                continue
            lat, lng = float(prop.latitude or 0), float(prop.longitude or 0)
            if not lat or not lng:
                continue
            dist = self._haversine_km(
                self._MARRAKECH_LAT, self._MARRAKECH_LNG, lat, lng
            )
            if dist > self._CARTE_RADIUS_KM:
                continue
            if prop.id in by_fiche:
                continue
            pillar = self._map_pillar_for(prop)
            categories = [
                {"code": c.code, "label": cat_labels.get(c.code, c.name)}
                for c in prop.category_ids.sorted("sequence")
                if c.code
            ]
            category_codes = [c["code"] for c in categories]
            photos = self._property_photos(prop)
            creator = (
                v.uploaded_by.name
                if v.uploaded_by
                else ""
            ) or ""
            badge = prop.carte_badge_for_video(v, trending_ids)
            by_fiche[prop.id] = {
                "id": prop.id,
                "name": prop.name,
                "slug": self._slugify(prop.name),
                "lat": lat,
                "lng": lng,
                "zone": prop.map_zone or "",
                "pillar": pillar,
                "pillar_label": pillar_labels.get(pillar, pillar),
                "categories": categories,
                "category_codes": category_codes,
                "district": prop.district or "",
                "city": prop.city or "Marrakech",
                "video_id": v.id,
                "video_url": v.video_url,
                "snippet_url": self._snippet_url(v.video_url),
                "video_title": v.titre or prop.name,
                "source": v.source or "proprietaire",
                "creator_name": creator,
                "badge": badge,
                "photo_url": (photos[0].get("url") if photos else "") or "",
                "detail_url": self._property_detail_url(prop),
                "rg": self._rg_payload(prop),
                "be": self._be_payload(prop),
            }
        return _json({"ok": True, "pins": list(by_fiche.values())})

    @http.route(
        "/coins/api/carte/video/view",
        type="http", auth="public", methods=["POST", "OPTIONS"],
        csrf=False, cors="*",
    )
    def carte_video_view(self, **kw):
        """Incrémente le compteur d’ouvertures (badge Tendance, 7 j)."""
        if request.httprequest.method == "OPTIONS":
            return _json({"ok": True})
        d = _body()
        try:
            video_id = int(d.get("video_id") or 0)
        except (TypeError, ValueError):
            video_id = 0
        if not video_id:
            return _json({"ok": False, "error": "video_id"}, 400)
        ok = request.env["coins.fiche_video.view"].sudo().record_view(
            video_id, self._viewer_key()
        )
        if not ok:
            return _json({"ok": False, "error": "not_found"}, 404)
        return _json({"ok": True})

    def _carnet_token_from_request(self, body=None):
        body = body or {}
        return (
            _clean(body.get("token"), 120)
            or request.httprequest.headers.get("X-Carnet-Token", "")
            or request.httprequest.cookies.get("cm_carnet_token", "")
            or ""
        ).strip()

    @http.route(
        "/coins/api/carnet/favoris",
        type="http", auth="public", methods=["GET", "OPTIONS"],
        csrf=False, cors="*",
    )
    def carnet_favoris_list(self, **kw):
        """Liste des favoris carte pour un token Carnet."""
        if request.httprequest.method == "OPTIONS":
            return _json({"ok": True})
        token = self._carnet_token_from_request()
        if not token:
            return _json({"ok": False, "error": "auth_required"}, 401)
        Favori = request.env["coins.carnet.favori"].sudo()
        items = Favori.list_for_token(token)
        if items is None:
            return _json({"ok": False, "error": "invalid_token"}, 401)
        return _json({
            "ok": True,
            "favoris": items,
            "property_ids": [f["property_id"] for f in items],
        })

    @http.route(
        "/coins/api/carnet/favoris/toggle",
        type="http", auth="public", methods=["POST", "OPTIONS"],
        csrf=False, cors="*",
    )
    def carnet_favoris_toggle(self, **kw):
        """Ajoute/retire un lieu des favoris Carnet."""
        if request.httprequest.method == "OPTIONS":
            return _json({"ok": True})
        d = _body()
        token = self._carnet_token_from_request(d)
        if not token:
            return _json({
                "ok": False,
                "error": "auth_required",
                "login_url": "/carnet#retrouver",
            }, 401)
        result = request.env["coins.carnet.favori"].sudo().toggle_for_token(
            token, d.get("property_id")
        )
        if result is None:
            return _json({
                "ok": False,
                "error": "invalid_token",
                "login_url": "/carnet#retrouver",
            }, 401)
        if not result.get("ok"):
            return _json(result, 404 if result.get("error") == "not_found" else 400)
        return _json(result)

    @http.route(
        "/coins/api/carte/lieu/<string:slug>",
        type="http", auth="public", methods=["GET", "OPTIONS"],
        csrf=False, cors="*",
    )
    def carte_lieu(self, slug, **kw):
        """Fiche publique d'un lieu (description + vidéos) pour /lieux/<slug>."""
        if request.httprequest.method == "OPTIONS":
            return _json({"ok": True})
        slug = self._slugify(slug or "")
        aliases = {
            "riad-asrari-medina-marrakech": "riad-asrari",
            "riad-asrari-piscine-medina-marrakech": "riad-asrari",
            "casa-ysabella": "la-casa-ysabella",
            "riad-medina-marrakech-la-casa-ysabella": "la-casa-ysabella",
        }
        lookup = aliases.get(slug, slug)
        Prop = request.env["coins.property"].sudo()
        props = Prop.search([
            ("active", "=", True),
            ("state", "=", "active"),
        ] + Prop._domain_exclude_unpublished_onboarding())
        prop = Prop.browse()
        for p in props:
            pslug = self._slugify(p.name)
            if pslug == slug or pslug == lookup:
                prop = p
                break
        if not prop:
            return _json({"ok": False, "error": "not_found"}, 404)
        # Fiche publique hors carte : lieux actifs liés à une catégorie visible.
        # Adresse exacte uniquement si Découverte.
        public_cats = {"decouverte", "evenements", "bien_etre", "hebergement"}
        codes = set(prop.category_ids.mapped("code"))
        if codes and not (codes & public_cats) and not prop.is_carte_public():
            return _json({"ok": False, "error": "not_found"}, 404)
        Video = request.env["coins.fiche_video"].sudo()
        videos = Video.search([
            ("fiche_id", "=", prop.id),
            ("statut", "=", "publiee"),
        ], order="ordre_affichage, id")
        pillar = self._map_pillar_for(prop)
        labels = {
            "villas_riads": "Hébergement",
            "bien_etre": "Bien-être",
            "route_gourmande": "Route gourmande",
            "plein_air": "Plein air & sport",
            "experiences": "Expériences",
            "evenements": "Événements",
        }
        cat_labels = {
            "decouverte": "Découverte",
            "privatisation": "Privatisation",
            "evenements": "Événements",
            "bien_etre": "Bien-être",
            "hebergement": "Hébergement",
            "route_gourmande": "Route gourmande",
        }
        categories = [
            {"code": c.code, "label": cat_labels.get(c.code, c.name)}
            for c in prop.category_ids.sorted("sequence")
            if c.code
        ]
        show_address = prop.is_carte_public()
        lat = float(prop.latitude or 0) if show_address else 0.0
        lng = float(prop.longitude or 0) if show_address else 0.0
        rooms = self._property_rooms(prop)
        priced = [r["price_per_night"] for r in rooms if r.get("price_per_night")]
        price_from = min(priced) if priced else float(prop.price_per_night or 0.0)
        cat_codes = [c["code"] for c in categories]
        return _json({
            "ok": True,
            "lieu": {
                "id": prop.id,
                "name": prop.name,
                "slug": slug,
                "pillar": pillar,
                "pillar_label": labels.get(pillar, pillar),
                "categories": categories,
                "category_codes": [c["code"] for c in categories],
                "zone": prop.map_zone or "",
                "district": prop.district or "",
                "city": prop.city or "Marrakech",
                "street": (prop.street or "") if show_address else "",
                "capacity": prop.capacity or 0,
                "nb_suites": prop.nb_suites or 0,
                "terrain_hectares": prop.terrain_hectares or 0,
                "tarif_privatisation_jour": prop.tarif_privatisation_jour or 0,
                "location_chambre_unite": bool(prop.location_chambre_unite),
                "lat": lat,
                "lng": lng,
                "maps_url": (
                    "https://maps.google.com/?q=%s,%s" % (lat, lng)
                    if show_address and lat and lng
                    else ""
                ),
                "description_html": prop.description or "",
                "narrative_html": prop.narrative or "",
                # Airbnb non exposé au public (sync iCal partenaire uniquement)
                "airbnb_url": "",
                "photos": self._property_photos(prop),
                "rooms": rooms,
                "amenities": self._property_amenities(prop),
                "reviews": self._property_reviews(prop),
                "nearby": self._property_nearby(prop),
                "price_from": price_from,
                "currency": (
                    prop.currency_id.name if getattr(prop, "currency_id", False) else ""
                ),
                "currency_ref": (
                    prop.currency_id.name if getattr(prop, "currency_id", False) else ""
                ),
                "can_privatise": "privatisation" in cat_codes,
                "videos": [
                    {
                        "id": v.id,
                        "title": v.titre or prop.name,
                        "url": v.video_url,
                        "upload_date": (
                            v.date_upload.strftime("%Y-%m-%d")
                            if getattr(v, "date_upload", None)
                            else ""
                        ),
                    }
                    for v in videos
                    if v.video_url
                ],
                "detail_url": self._property_detail_url(prop),
                "rg": self._rg_payload(prop),
                "be": self._be_payload(prop),
            },
        })

    @http.route(
        "/coins/api/carte/signup",
        type="http", auth="public", methods=["POST", "OPTIONS"],
        csrf=False, cors="*",
    )
    def carte_signup(self, **kw):
        """Inscription libre-service → file coins.partner_activity (en attente).

        Accepte JSON ou multipart/form-data (photo optionnelle).
        """
        if request.httprequest.method == "OPTIONS":
            return _json({"ok": True})
        d = _body()
        # Prefer explicit form kwargs when present (multipart)
        if kw:
            for key in (
                "place_name", "name", "contact_name", "email", "phone",
                "category", "description", "video_url", "signup_channel",
            ):
                if kw.get(key) not in (None, ""):
                    d[key] = kw.get(key)
        place = _clean(d.get("place_name") or d.get("name"), 160)
        contact = _clean(d.get("contact_name"), 120)
        email = _clean(d.get("email"), 120)
        phone = _clean(d.get("phone"), 40)
        description = _clean(d.get("description"), 4000)
        video_url = _clean(d.get("video_url"), 500)
        category = _clean(d.get("category"), 40).lower()
        channel = _clean(d.get("signup_channel"), 40).lower() or "carte"
        if channel not in ("carte", "site_partenaires"):
            channel = "carte"
        cat_map = {
            "resto": "resto",
            "restaurant": "resto",
            "route_gourmande": "resto",
            "hebergement": "hebergement",
            "hébergement": "hebergement",
            "bien_etre": "hammam",
            "bien-etre": "hammam",
            "hammam": "hammam",
            "plein_air": "other",
            "experiences": "other",
            "evenements": "other",
            "autre": "other",
            "other": "other",
        }
        category = cat_map.get(category, "")
        if not place:
            return _json({"ok": False, "error": "place_name"}, 400)
        if not email or "@" not in email:
            return _json({"ok": False, "error": "email"}, 400)
        if not phone:
            return _json({"ok": False, "error": "phone"}, 400)
        if not category:
            return _json({"ok": False, "error": "category"}, 400)
        photo_b64, photo_err = _read_signup_photo()
        if photo_err:
            return _json({"ok": False, "error": photo_err}, 400)
        try:
            vals = {
                "name": place,
                "contact_name": contact or False,
                "email": email,
                "phone": phone,
                "category": category,
                "relation_type": "libre_service",
                "state": "en_attente",
                "signup_channel": channel,
                "description": description or False,
                "video_url": video_url or False,
                "notes": (
                    "Inscription libre-service via coinsmarocain.com (%s).\n"
                    "Validation manuelle requise avant accès portail propriétaire.\n"
                    "Grille indicative (interne, non affichée publiquement) : "
                    "resto 10 %% / hébergement 15 %% — distincte des taux négociés.\n"
                    "%s"
                ) % (
                    channel,
                    ("Photo jointe.\n" if photo_b64 else "Sans photo.\n")
                    + (("Description : oui.\n" if description else "Description : non.\n")),
                ),
            }
            if photo_b64:
                vals["image_1920"] = photo_b64
            request.env["coins.partner_activity"].sudo().create(vals)
            mail_to = (
                request.env["ir.config_parameter"]
                .sudo()
                .get_param(
                    "coins_marocain.contact_notify_email",
                    "karine@agencedoorway.com,zakaria@agencedoorway.com",
                )
            )
            desc_html = (
                "<li><strong>Description</strong> : %s</li>"
                % (description.replace("<", "&lt;")[:500] if description else "—")
            )
            request.env["mail.mail"].sudo().create({
                "subject": "[Coins] Inscription lieu — %s" % place,
                "body_html": (
                    "<p>Nouvelle inscription libre-service (%s).</p>"
                    "<ul>"
                    "<li><strong>Lieu</strong> : %s</li>"
                    "<li><strong>Catégorie</strong> : %s</li>"
                    "<li><strong>Contact</strong> : %s</li>"
                    "<li><strong>Email</strong> : %s</li>"
                    "<li><strong>Tél</strong> : %s</li>"
                    "%s"
                    "<li><strong>Photo</strong> : %s</li>"
                    "<li><strong>Vidéo</strong> : %s</li>"
                    "</ul>"
                    "<p>Statut : En attente — file partenaires.</p>"
                ) % (
                    channel,
                    place,
                    category,
                    contact or "—",
                    email,
                    phone,
                    desc_html,
                    "jointe" if photo_b64 else "non",
                    video_url or "—",
                ),
                "email_to": mail_to,
                "auto_delete": True,
            }).send()
        except Exception as e:  # noqa: BLE001
            _logger.exception("coins carte signup fail: %s", e)
            return _json({"ok": False, "error": "server"}, 500)
        return _json({"ok": True})

    @http.route(
        "/coins/api/partner",
        type="http", auth="public", methods=["POST", "OPTIONS"],
        csrf=False, cors="*",
    )
    def partner(self, **kw):
        if request.httprequest.method == "OPTIONS":
            return _json({"ok": True})
        d = _body()
        name = _clean(d.get("name")) or "Partenaire"
        email = _clean(d.get("email"), 120)
        if not email or "@" not in email:
            return _json({"ok": False, "error": "email"}, 400)
        try:
            request.env["coins.partner_activity"].sudo().create({
                "name": name,
                "email": email,
                "phone": _clean(d.get("phone"), 40),
                "signup_channel": "site_partenaires",
                "notes": (
                    "Candidature partenaire via coinsmarocain.com.\n"
                    f"Ville : {_clean(d.get('city'))}\n"
                    f"Message : {_clean(d.get('message'), 1000)}"
                ),
            })
        except Exception as e:  # noqa: BLE001
            _logger.exception("coins partner fail: %s", e)
            return _json({"ok": False, "error": "server"}, 500)
        return _json({"ok": True})

    @http.route(
        "/coins/api/concierge",
        type="http", auth="public", methods=["POST", "OPTIONS"],
        csrf=False, cors="*",
    )
    def concierge(self, **kw):
        if request.httprequest.method == "OPTIONS":
            return _json({"ok": True})
        d = _body()
        yas = YasmineService(request.env)
        history = d.get("messages") or []
        msgs = []
        for m in history[-10:]:
            role = m.get("role")
            content = _clean(m.get("content"), 1500)
            if role in ("user", "assistant") and content:
                msgs.append({"role": role, "content": content})
        if not msgs or msgs[-1]["role"] != "user":
            return _json({"ok": False, "error": "no_message"}, 400)

        last = msgs[-1]["content"]
        found_email = yas.extract_email(last)
        found_phone = yas.extract_phone(last)

        hot = yas.detect_hot(msgs)
        offer_wa = yas.detect_conversion_interest(msgs) or bool(found_phone)
        user_bits = [m["content"] for m in msgs if m["role"] == "user"][-4:]
        wa_text = (
            "Bonjour Yasmine, je viens du chat Coins Marocain.\n"
            + "\n".join("- %s" % b for b in user_bits)
        )
        wa_url = yas.wa_me_url(wa_text)

        # Bridge : numéro fourni → session WA prête pour le bot
        if found_phone:
            try:
                yas.seed_session_from_web(found_phone, msgs)
            except Exception as e:  # noqa: BLE001
                _logger.warning("coins wa seed fail: %s", e)

        if hot:
            lead = None
            try:
                lead = yas.create_lead(
                    msgs,
                    contact_email=found_email,
                    contact_phone=found_phone,
                    hot=True,
                    channel="web",
                )
                yas.notify_hot(lead, msgs, wa_url)
            except Exception as e:  # noqa: BLE001
                _logger.exception("coins hot lead fail: %s", e)
            return _json({
                "ok": True,
                "reply": yas.hot_reply(msgs, channel="web"),
                "hot": True,
                "offer_whatsapp": True,
                "whatsapp_url": wa_url,
                "lead_id": lead.id if lead else None,
            })

        lead_id = None
        if found_email or found_phone:
            try:
                lead = yas.create_lead(
                    msgs,
                    contact_email=found_email,
                    contact_phone=found_phone,
                    hot=False,
                    channel="web",
                )
                lead_id = lead.id
            except Exception as e:  # noqa: BLE001
                _logger.warning("coins concierge lead fail: %s", e)

        reply = yas.claude_reply(msgs, CONCIERGE_SYSTEM_WEB, max_tokens=400)
        if not reply:
            reply = (
                "Je suis ravie de vous accueillir chez Coins Marocain ! "
                "Continuez avec moi sur WhatsApp (bouton ci-dessous) ou laissez "
                "votre numéro — je vous réponds directement pour composer votre séjour."
            )
            offer_wa = True

        # Si numéro capturé : confirmer le bot WA dans la réponse
        if found_phone and "whatsapp" not in (reply or "").lower():
            reply = (
                (reply or "").rstrip()
                + "\n\nParfait — ouvrez WhatsApp via le bouton : je continue "
                "moi-même la conversation (Yasmine) avec le contexte de notre échange."
            )
            offer_wa = True

        return _json({
            "ok": True,
            "reply": reply,
            "hot": False,
            "offer_whatsapp": bool(offer_wa),
            "whatsapp_url": wa_url if offer_wa else None,
            "lead_id": lead_id,
        })

    # ---- Conversation d'accueil Yasmine (remplace le quiz) ----

    @http.route(
        "/coins/api/yasmine/accueil/open",
        type="http", auth="public", methods=["POST", "OPTIONS"],
        csrf=False, cors="*",
    )
    def yasmine_accueil_open(self, **kw):
        if request.httprequest.method == "OPTIONS":
            return _json({"ok": True})
        d = _body()
        session_id = _clean(d.get("session_id"), 64)
        if not session_id:
            import uuid
            session_id = "yas-" + uuid.uuid4().hex[:16]
        language = _clean(d.get("language"), 8) or "fr"
        try:
            yas = YasmineService(request.env)
            result = yas.handle_accueil_chat(session_id, "", language=language)
            return _json(result)
        except Exception as e:  # noqa: BLE001
            _logger.exception("yasmine accueil open fail: %s", e)
            return _json({"ok": False, "error": "server"}, 500)

    @http.route(
        "/coins/api/yasmine/accueil",
        type="http", auth="public", methods=["POST", "OPTIONS"],
        csrf=False, cors="*",
    )
    def yasmine_accueil_chat(self, **kw):
        if request.httprequest.method == "OPTIONS":
            return _json({"ok": True})
        d = _body()
        session_id = _clean(d.get("session_id"), 64)
        message = _clean(d.get("message"), 2000)
        language = _clean(d.get("language"), 8) or None
        if not session_id:
            return _json({"ok": False, "error": "no_session"}, 400)
        if not message:
            return _json({"ok": False, "error": "no_message"}, 400)
        try:
            yas = YasmineService(request.env)
            result = yas.handle_accueil_chat(session_id, message, language=language)
            return _json(result)
        except Exception as e:  # noqa: BLE001
            _logger.exception("yasmine accueil chat fail: %s", e)
            return _json({"ok": False, "error": "server"}, 500)

    # ------------------------------------------------------------------
    # Airbnb iCal sync (trigger manuel / debug — le cron appelle le modèle)
    # ------------------------------------------------------------------

    @http.route(
        "/coins_marocain/airbnb_ical/sync",
        type="jsonrpc",
        auth="user",
        methods=["POST"],
    )
    def airbnb_ical_sync(self, property_id=None, **kw):
        """Déclenche l'import iCal Airbnb (cron natif préféré en prod)."""
        Property = request.env["coins.property"]
        if property_id:
            props = Property.browse(int(property_id)).exists()
            if not props:
                return {"ok": False, "error": "property_not_found"}
        else:
            props = Property.search(
                [("airbnb_ical_export_url", "!=", False), ("active", "=", True)]
            )
        stats = props._sync_airbnb_icals()
        return {"ok": True, **stats}
