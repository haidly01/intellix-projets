# -*- coding: utf-8 -*-
import base64
import logging

from odoo import http
from odoo.http import request

_logger = logging.getLogger(__name__)


class CoinsPartenairePortal(http.Controller):
    @http.route(
        ["/partenaire/<string:token>", "/partenaire/<string:token>/"],
        type="http",
        auth="public",
        website=False,
        csrf=True,
        methods=["GET", "POST"],
    )
    def partenaire_home(self, token, **kw):
        Property = request.env["coins.property"].sudo()
        prop = Property._lookup_by_portal_token(token)
        if not prop:
            return request.render(
                "coins_marocain.partenaire_portal_unknown",
                {},
            )
        submitted = False
        error = ""
        if request.httprequest.method == "POST":
            try:
                self._save_submission(prop, kw)
                submitted = True
            except Exception:
                _logger.exception("soumission partenaire token=%s", token)
                error = (
                    "L’enregistrement a échoué. Vérifiez les champs "
                    "et réessayez, ou écrivez à Zakaria."
                )
        kinds = self._selected_kinds(prop, kw if request.httprequest.method == "POST" else None)
        estab = self._establishment_for_prop(prop)
        hebergement_ops_url = (
            "/partenaire/%s/hebergement" % token if estab else False
        )
        messages_url = (
            "/partenaire/%s/messages" % token if estab else False
        )
        return request.render(
            "coins_marocain.partenaire_portal_page",
            {
                "prop": prop,
                "token": token,
                "submitted": submitted,
                "error": error,
                "csrf_token": request.csrf_token(),
                "kinds": kinds,
                "show_resto": "restaurant" in kinds,
                "show_spa": "spa" in kinds,
                "show_hebergement": "hebergement" in kinds,
                "hebergement_ops_url": hebergement_ops_url,
                "messages_url": messages_url,
            },
        )

    def _kinds_for_prop(self, prop):
        """Liste des catégories portail (compat prod sans onboarding_kinds_list)."""
        if hasattr(prop, "onboarding_kinds_list"):
            return prop.onboarding_kinds_list()
        codes = set(prop.category_ids.mapped("code") or [])
        kinds = []
        if "route_gourmande" in codes:
            kinds.append("restaurant")
        if "bien_etre" in codes:
            kinds.append("spa")
        if "hebergement" in codes:
            kinds.append("hebergement")
        if kinds:
            return kinds
        kind = prop.onboarding_kind
        if kind in ("restaurant", "spa", "hebergement"):
            return [kind]
        return ["hebergement"]

    def _selected_kinds(self, prop, kw):
        raw = request.httprequest.form.getlist("onboarding_cat") if kw is not None else []
        kinds = [k for k in raw if k in ("restaurant", "spa", "hebergement")]
        if kinds:
            return kinds
        return self._kinds_for_prop(prop)

    def _save_submission(self, prop, kw):
        kinds = self._selected_kinds(prop, kw)
        if not kinds:
            kinds = self._kinds_for_prop(prop)
        vals = {
            "name": (kw.get("name") or prop.name or "").strip() or prop.name,
            "street": (kw.get("street") or "").strip() or prop.street,
            "district": (kw.get("district") or "").strip() or prop.district,
            "city": (kw.get("city") or "").strip() or prop.city or "Marrakech",
            "onboarding_contact_name": (kw.get("contact_name") or "").strip(),
            "onboarding_phone": (kw.get("phone") or "").strip(),
            "onboarding_email": (kw.get("email") or "").strip(),
            "description": (kw.get("description") or "").strip(),
            "onboarding_status": "en_attente_validation",
        }
        if "hebergement" in kinds:
            vals.update(self._vals_hebergement(kw))
        if "restaurant" in kinds:
            vals.update(self._vals_restaurant(kw))
        if "spa" in kinds:
            vals.update(self._vals_spa(kw))
        prop.with_context(coins_partner_portal=True).write(vals)
        if hasattr(prop, "_apply_onboarding_kinds"):
            prop._apply_onboarding_kinds(kinds)
        elif "onboarding_kind" in prop._fields and kinds:
            prop.with_context(coins_partner_portal=True).write(
                {
                    "onboarding_kind": (
                        "hebergement" if "hebergement" in kinds else kinds[0]
                    )
                }
            )
        if "hebergement" in kinds:
            self._save_rooms(prop, kw)
        self._save_video(prop, kw.get("video_url"))
        self._save_photos(prop)
        if hasattr(prop, "_notify_karine_onboarding_submission"):
            prop._notify_karine_onboarding_submission()

    def _vals_hebergement(self, kw):
        names = request.httprequest.form.getlist("room_name")
        named = [n.strip() for n in names if (n or "").strip()]
        vals = {
            "rg_privatisation_possible": bool(kw.get("privatisation")),
            "meal_breakfast_available": bool(kw.get("petit_dejeuner")),
            "daypass_piscine": bool(kw.get("piscine")),
        }
        if named:
            sleeps = [
                self._int(v) for v in request.httprequest.form.getlist("room_sleeps")
            ]
            prices = [
                self._float(v) for v in request.httprequest.form.getlist("room_price")
            ]
            vals["nb_suites"] = len(named)
            vals["capacity"] = sum(sleeps) or self._int(kw.get("capacite"))
            vals["price_per_night"] = min([p for p in prices if p] or [0]) or self._float(
                kw.get("tarif")
            )
        else:
            vals.update(
                {
                    "nb_suites": self._int(kw.get("nb_chambres")),
                    "capacity": self._int(kw.get("capacite")),
                    "price_per_night": self._float(kw.get("tarif")),
                }
            )
        return vals

    def _save_rooms(self, prop, kw):
        form = request.httprequest.form
        names = form.getlist("room_name")
        named = [(i, (n or "").strip()) for i, n in enumerate(names) if (n or "").strip()]
        Room = request.env["coins.property.room"].sudo()
        if not named:
            self._ensure_legacy_single_room(prop, kw)
            return
        ids = form.getlist("room_id")
        descs = form.getlist("room_description")
        sleeps = form.getlist("room_sleeps")
        prices = form.getlist("room_price")
        empls = form.getlist("room_emplacement")
        keep_ids = []
        for seq, (index, name) in enumerate(named, start=1):
            room_id = self._int(ids[index]) if index < len(ids) else 0
            vals = {
                "property_id": prop.id,
                "name": name,
                "description": (descs[index] if index < len(descs) else "") or False,
                "sleeps": self._int(sleeps[index] if index < len(sleeps) else 2) or 2,
                "sequence": seq * 10,
                "active": True,
            }
            if "price_per_night" in Room._fields:
                vals["price_per_night"] = self._float(
                    prices[index] if index < len(prices) else 0
                )
            if "emplacement" in Room._fields:
                empl = empls[index] if index < len(empls) else "etage"
                vals["emplacement"] = empl if empl in ("etage", "rdc") else "etage"
            room = Room.browse(room_id) if room_id else Room.browse()
            if room.exists() and room.property_id.id == prop.id:
                room.write(vals)
            else:
                room = Room.create(vals)
            keep_ids.append(room.id)
            self._save_room_photos(prop, room, index)
        extras = prop.room_ids.filtered(lambda r: r.id not in keep_ids)
        self._archive_or_keep_rooms(extras)

    def _ensure_legacy_single_room(self, prop, kw):
        """Fiches déjà soumises à une chambre : garder nb_suites / tarif."""
        if prop.room_ids.filtered("active"):
            return
        name = (prop.name or "Chambre").strip()
        price = self._float(kw.get("tarif")) or prop.price_per_night or 0
        sleeps = self._int(kw.get("capacite")) or prop.capacity or 2
        Room = request.env["coins.property.room"].sudo()
        vals = {
            "property_id": prop.id,
            "name": name,
            "sleeps": sleeps or 2,
            "sequence": 10,
            "active": True,
        }
        if "price_per_night" in Room._fields:
            vals["price_per_night"] = price
        Room.create(vals)

    def _archive_or_keep_rooms(self, rooms):
        Resa = request.env["coins.reservation"].sudo()
        for room in rooms:
            booked = Resa.search_count(
                [("room_id", "=", room.id), ("state", "not in", ("cancel", "cancelled"))]
            )
            room.write({"active": False})
            if booked:
                _logger.info(
                    "chambre %s archivée (réservations existantes), non supprimée",
                    room.id,
                )

    def _save_room_photos(self, prop, room, index):
        files = request.httprequest.files.getlist("room_photos_%s" % index)
        if not files:
            files = request.httprequest.files.getlist("room_photos_%s" % room.id)
        Photo = request.env["coins.property.photo"].sudo()
        for upload in files:
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

    def _vals_restaurant(self, kw):
        cadres = request.httprequest.form.getlist("cadre")
        return {
            "rg_cuisine": kw.get("rg_cuisine") or False,
            "rg_cadre": ",".join([c for c in cadres if c]),
            "rg_alcool": kw.get("rg_alcool") or False,
            "rg_animations": (kw.get("rg_animations") or "").strip() or False,
            "rg_capacite_couverts": self._int(kw.get("rg_capacite")),
            "rg_privatisation_possible": bool(kw.get("privatisation")),
            "rg_ambiance": kw.get("rg_ambiance") or False,
            "rg_vue": kw.get("rg_vue") or False,
            "rg_fourchette_prix": kw.get("rg_fourchette_prix") or False,
        }

    def _vals_spa(self, kw):
        services = request.httprequest.form.getlist("be_services")
        return {
            "be_type_lieu": kw.get("be_type_lieu") or False,
            "be_services": ",".join([s for s in services if s]),
            "be_mixte": kw.get("be_mixte") or False,
            "be_capacite_simultanee": self._int(kw.get("be_capacite")),
            "be_prestataire_libre": (kw.get("be_prestataire") or "").strip() or False,
        }

    def _save_video(self, prop, url):
        url = (url or "").strip()
        if not url:
            return
        Video = request.env["coins.fiche_video"].sudo()
        existing = Video.search(
            [("fiche_id", "=", prop.id), ("video_url", "=", url)],
            limit=1,
        )
        if existing:
            return
        Video.create(
            {
                "fiche_id": prop.id,
                "source": "proprietaire",
                "video_url": url,
                "titre": "Vidéo partenaire",
                "statut": "en_attente",
            }
        )

    def _save_photos(self, prop):
        files = request.httprequest.files.getlist("photos")
        Photo = request.env["coins.property.photo"].sudo()
        for upload in files:
            raw = upload.read() if upload else b""
            if not raw:
                continue
            Photo.create(
                {
                    "property_id": prop.id,
                    "image": base64.b64encode(raw),
                    "legende": (upload.filename or "")[:80],
                }
            )

    @staticmethod
    def _int(value):
        try:
            return int(str(value or "").strip() or 0)
        except (TypeError, ValueError):
            return 0

    @staticmethod
    def _float(value):
        try:
            return float(str(value or "0").replace(",", ".").strip() or 0)
        except (TypeError, ValueError):
            return 0.0

    def _establishment_for_prop(self, prop):
        Estab = request.env["intellix.riad.establishment"].sudo()
        return Estab.search([("property_id", "=", prop.id)], limit=1)

    @http.route(
        [
            "/partenaire/<string:token>/hebergement",
            "/partenaire/<string:token>/hebergement/",
        ],
        type="http",
        auth="public",
        website=False,
        csrf=True,
        methods=["GET", "POST"],
    )
    def partenaire_hebergement_ops(self, token, **kw):
        """Self-service Pace comps + proposition taxe — isolé par token propriété."""
        Property = request.env["coins.property"].sudo()
        prop = Property._lookup_by_portal_token(token)
        if not prop:
            return request.render("coins_marocain.partenaire_portal_unknown", {})
        estab = self._establishment_for_prop(prop)
        if not estab:
            return request.render(
                "coins_marocain.partenaire_portal_unknown",
                {},
            )
        submitted = False
        error = ""
        tax_awaiting = bool(estab.tourist_tax_awaiting_karine)
        if request.httprequest.method == "POST":
            try:
                self._save_hebergement_ops(prop, estab, kw)
                estab.invalidate_recordset()
                tax_awaiting = bool(estab.tourist_tax_awaiting_karine)
                submitted = True
            except Exception:
                _logger.exception(
                    "soumission hebergement ops token=%s prop=%s", token, prop.id
                )
                error = (
                    "L’enregistrement a échoué. Réessayez ou écrivez à "
                    "Karine Barmaki (Coins Marocain)."
                )
        return request.render(
            "coins_marocain.partenaire_hebergement_ops_page",
            self._hebergement_ops_values(
                prop, estab, token, submitted=submitted, error=error, tax_awaiting=tax_awaiting
            ),
        )

    def _hebergement_ops_values(self, prop, estab, token, submitted=False, error="", tax_awaiting=False):
        comps = estab.comp_riad_ids.filtered("active").sorted("sequence")
        pace_slots = []
        for i in range(1, 11):
            name = comps[i - 1].name if i <= len(comps) else ""
            pace_slots.append(
                {
                    "index": i,
                    "name": name or "",
                    "placeholder": "Nom exact Pace #%s" % i,
                }
            )
        active_rate = estab.tourist_tax_rate or 0.0
        if estab.tourist_tax_awaiting_karine:
            status = "Soumis — en attente de validation Karine"
        elif estab.tourist_tax_pending_confirmation:
            status = "Taux actif provisoire (à confirmer auprès de la commune)"
        elif active_rate:
            status = "Taux actif confirmé"
        else:
            status = "Aucun taux actif"
        return {
            "prop": prop,
            "estab": estab,
            "token": token,
            "submitted": submitted,
            "error": error,
            "csrf_token": request.csrf_token(),
            "pace_slots": pace_slots,
            "active_rate": active_rate,
            "active_commune": estab.tourist_tax_commune or "",
            "proposed_rate": estab.tourist_tax_owner_rate or 0.0,
            "proposed_commune": estab.tourist_tax_owner_commune or "",
            "proposed_tpt": estab.tourist_tax_owner_tpt or 0.0,
            "proposed_communal": estab.tourist_tax_owner_communal or 0.0,
            "tax_status_label": status,
            "tax_awaiting": tax_awaiting or bool(estab.tourist_tax_awaiting_karine),
            "ota_rows": estab.portal_ota_rows(),
            "lib_wifi": estab.experience_wifi or "",
            "lib_rules": estab.experience_house_rules or "",
            "lib_contacts": estab.experience_useful_contacts or "",
            "lib_tips": estab.experience_local_tips or "",
            "lib_howto": estab.experience_howto or "",
            "lib_facts": estab.experience_facts or "",
            "lib_neighborhood": estab.experience_neighborhood or "",
            "lib_checkin": estab.experience_checkin_hour or 14.0,
            "lib_checkout": estab.experience_checkout_hour or 11.0,
            "agent_enabled": bool(estab.experience_agent_enabled),
        }

    def _save_hebergement_ops(self, prop, estab, kw):
        # Isolation : estab must belong to this property only
        if estab.property_id.id != prop.id:
            raise PermissionError("establishment/property mismatch")
        names = request.httprequest.form.getlist("pace_name")
        # Ne pas écraser le comp-set si tous les champs Pace sont vides
        # (saisie taxe seule).
        if any((n or "").strip() for n in names):
            estab.apply_portal_pace_comps(names)
        rate_raw = (kw.get("tax_rate") or "").strip()
        if rate_raw != "":
            rate = self._float(rate_raw)
            commune = (kw.get("tax_commune") or "").strip()
            estab.apply_portal_tourist_tax_proposal(
                rate,
                commune,
                tpt=self._float(kw.get("tax_tpt")),
                communal=self._float(kw.get("tax_communal")),
            )
        pending_otas = request.httprequest.form.getlist("ota_pending")
        if pending_otas:
            estab.apply_portal_ota_pending(pending_otas)
        if kw.get("save_library"):
            estab.apply_portal_guest_library(
                {
                    "experience_wifi": kw.get("lib_wifi"),
                    "experience_house_rules": kw.get("lib_rules"),
                    "experience_useful_contacts": kw.get("lib_contacts"),
                    "experience_local_tips": kw.get("lib_tips"),
                    "experience_howto": kw.get("lib_howto"),
                    "experience_facts": kw.get("lib_facts"),
                    "experience_neighborhood": kw.get("lib_neighborhood"),
                    "experience_checkin_hour": kw.get("lib_checkin"),
                    "experience_checkout_hour": kw.get("lib_checkout"),
                }
            )

    @http.route(
        [
            "/partenaire/<string:token>/messages",
            "/partenaire/<string:token>/messages/",
        ],
        type="http",
        auth="public",
        website=False,
        csrf=False,
        methods=["GET"],
    )
    def partenaire_messages(self, token, **kw):
        """Onglet Messages — conversations de CE lieu uniquement."""
        Property = request.env["coins.property"].sudo()
        prop = Property._lookup_by_portal_token(token)
        if not prop:
            return request.render("coins_marocain.partenaire_portal_unknown", {})
        estab = self._establishment_for_prop(prop)
        if not estab:
            return request.render("coins_marocain.partenaire_portal_unknown", {})
        threads = estab.portal_message_threads()
        rows = []
        for t in threads:
            rows.append(
                {
                    "when": t.inbound_at,
                    "guest": t.guest_name or "Voyageur",
                    "channel": dict(t._fields["channel"].selection).get(t.channel)
                    or t.channel,
                    "inbound": (t.inbound_text or "")[:400],
                    "reply": (t.reply_text or "")[:400],
                    "decision": dict(t._fields["decision"].selection).get(t.decision)
                    or t.decision,
                }
            )
        wa_status = dict(estab._fields["whatsapp_provision_status"].selection).get(
            estab.whatsapp_provision_status or "not_started"
        )
        return request.render(
            "coins_marocain.partenaire_messages_page",
            {
                "prop": prop,
                "estab": estab,
                "token": token,
                "threads": rows,
                "wa_number": estab.whatsapp_e164 or "",
                "wa_status": wa_status,
                "hebergement_ops_url": "/partenaire/%s/hebergement" % token,
            },
        )

    def _require_estab(self, token):
        Property = request.env["coins.property"].sudo()
        prop = Property._lookup_by_portal_token(token)
        if not prop:
            return None, None, request.render(
                "coins_marocain.partenaire_portal_unknown", {}
            )
        estab = self._establishment_for_prop(prop)
        if not estab:
            return None, None, request.render(
                "coins_marocain.partenaire_portal_unknown", {}
            )
        return prop, estab, None

    @http.route(
        ["/partenaire/<string:token>/performance", "/partenaire/<string:token>/performance/"],
        type="http",
        auth="public",
        website=False,
        csrf=False,
        methods=["GET"],
    )
    def partenaire_performance(self, token, **kw):
        prop, estab, err = self._require_estab(token)
        if err:
            return err
        return request.render(
            "coins_marocain.partenaire_performance_page",
            {
                "prop": prop,
                "estab": estab,
                "token": token,
                "perf": estab.portal_performance_payload(),
            },
        )

    @http.route(
        [
            "/partenaire/<string:token>/reservations",
            "/partenaire/<string:token>/reservations/",
        ],
        type="http",
        auth="public",
        website=False,
        csrf=True,
        methods=["GET", "POST"],
    )
    def partenaire_reservations(self, token, **kw):
        prop, estab, err = self._require_estab(token)
        if err:
            return err
        nudge_ok = False
        error = ""
        if request.httprequest.method == "POST":
            try:
                if estab.property_id.id != prop.id:
                    raise PermissionError("mismatch")
                resa_id = int(kw.get("resa_id") or 0)
                action = (kw.get("action") or "relance").strip()
                estab.portal_reservation_nudge(resa_id, kind=action)
                nudge_ok = True
            except Exception:
                _logger.exception("relance reservation token=%s", token)
                error = "Relance impossible. Réessayez ou écrivez à Karine Barmaki."
        return request.render(
            "coins_marocain.partenaire_reservations_page",
            {
                "prop": prop,
                "estab": estab,
                "token": token,
                "groups": estab.portal_reservation_groups(),
                "csrf_token": request.csrf_token(),
                "nudge_ok": nudge_ok,
                "error": error,
            },
        )

    @http.route(
        ["/partenaire/<string:token>/facturation", "/partenaire/<string:token>/facturation/"],
        type="http",
        auth="public",
        website=False,
        csrf=False,
        methods=["GET"],
    )
    def partenaire_facturation(self, token, **kw):
        prop, estab, err = self._require_estab(token)
        if err:
            return err
        return request.render(
            "coins_marocain.partenaire_facturation_page",
            {
                "prop": prop,
                "estab": estab,
                "token": token,
                "bill": estab.portal_billing_payload(),
            },
        )
