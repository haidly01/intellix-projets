# -*- coding: utf-8 -*-
import base64
import logging

from odoo import http
from odoo.http import request

from odoo.addons.coins_marocain.models.coins_deco_prestataire import (
    DECO_THEME_CODES,
    DECO_TYPE_CODES,
)

_logger = logging.getLogger(__name__)


class CoinsDecoPrestatairePortal(http.Controller):
    @http.route(
        [
            "/prestataire-deco/<string:token>",
            "/prestataire-deco/<string:token>/",
        ],
        type="http",
        auth="public",
        website=False,
        csrf=True,
        methods=["GET", "POST"],
    )
    def deco_prestataire_home(self, token, **kw):
        Deco = request.env["coins.deco.prestataire"].sudo()
        deco = Deco._lookup_by_portal_token(token)
        if not deco:
            response = request.render(
                "coins_marocain.deco_prestataire_portal_unknown",
                {},
            )
            response.status_code = 404
            return response
        submitted = False
        error = ""
        if request.httprequest.method == "POST":
            try:
                self._save_submission(deco, kw)
                submitted = True
            except Exception:
                _logger.exception("soumission prestataire-deco token=%s", token)
                error = (
                    "L’enregistrement a échoué. Vérifiez les champs "
                    "et réessayez, ou écrivez à Zakaria."
                )
        return request.render(
            "coins_marocain.deco_prestataire_portal_page",
            self._render_values(deco, token, submitted, error, kw),
        )

    def _render_values(self, deco, token, submitted, error, kw):
        Type = request.env["coins.deco.prestataire.type"].sudo()
        Theme = request.env["coins.deco.prestataire.theme"].sudo()
        types = Type.search([("code", "in", DECO_TYPE_CODES)], order="sequence, id")
        themes = Theme.search([("code", "in", DECO_THEME_CODES)], order="sequence, id")
        selected_types = self._selected_type_codes(
            deco, kw if request.httprequest.method == "POST" else None
        )
        selected_themes = self._selected_theme_codes(
            deco, kw if request.httprequest.method == "POST" else None
        )
        photos_by_theme = {
            theme.code: deco.photos_for_theme(theme) for theme in themes
        }
        return {
            "deco": deco,
            "token": token,
            "submitted": submitted,
            "error": error,
            "csrf_token": request.csrf_token(),
            "all_types": types,
            "all_themes": themes,
            "selected_types": selected_types,
            "selected_themes": selected_themes,
            "show_fleuriste": "fleuriste" in selected_types,
            "show_mobilier": "mobilier" in selected_types,
            "show_chapiteau": "chapiteau" in selected_types,
            "show_decoration": "decoration_generale" in selected_types,
            "photos_by_theme": photos_by_theme,
            "photos_min": 3,
        }

    def _selected_type_codes(self, deco, kw):
        raw = request.httprequest.form.getlist("deco_type") if kw is not None else []
        codes = [c for c in raw if c in DECO_TYPE_CODES]
        if codes:
            return codes
        return deco.type_codes_list()

    def _selected_theme_codes(self, deco, kw):
        raw = request.httprequest.form.getlist("deco_theme") if kw is not None else []
        codes = [c for c in raw if c in DECO_THEME_CODES]
        if codes:
            return codes
        return deco.theme_codes_list()

    def _save_submission(self, deco, kw):
        type_codes = self._selected_type_codes(deco, kw)
        theme_codes = self._selected_theme_codes(deco, kw)
        Type = request.env["coins.deco.prestataire.type"].sudo()
        Theme = request.env["coins.deco.prestataire.theme"].sudo()
        types = Type.search([("code", "in", type_codes)])
        themes = Theme.search([("code", "in", theme_codes)])
        vals = {
            "name": (kw.get("name") or deco.name or "").strip() or deco.name,
            "street": (kw.get("street") or "").strip() or False,
            "zone_couverture": (kw.get("zone_couverture") or "").strip() or False,
            "contact_name": (kw.get("contact_name") or "").strip() or False,
            "phone": (kw.get("phone") or "").strip() or False,
            "email": (kw.get("email") or "").strip() or False,
            "type_ids": [(6, 0, types.ids)],
            "theme_ids": [(6, 0, themes.ids)],
            "prix_minimum_commande": self._float(kw.get("prix_minimum_commande")),
            "inclus_prix_base": (kw.get("inclus_prix_base") or "").strip() or False,
            "delai_reservation_min": self._int(kw.get("delai_reservation_min")),
            "commission": self._float(kw.get("commission")),
            "onboarding_status": "en_attente_validation",
        }
        if "fleuriste" in type_codes:
            origine = kw.get("fl_fleurs_origine") or False
            if origine not in ("locales", "importees", "mixte"):
                origine = False
            vals.update(
                {
                    "fl_types_arrangements": (kw.get("fl_types_arrangements") or "").strip()
                    or False,
                    "fl_prix": (kw.get("fl_prix") or "").strip() or False,
                    "fl_prix_piece": self._float(kw.get("fl_prix_piece")),
                    "fl_prix_forfait": self._float(kw.get("fl_prix_forfait")),
                    "fl_fleurs_origine": origine,
                }
            )
        if "mobilier" in type_codes:
            vals.update(
                {
                    "mob_inventaire": (kw.get("mob_inventaire") or "").strip() or False,
                    "mob_prix": (kw.get("mob_prix") or "").strip() or False,
                    "mob_livraison_incluse": bool(kw.get("mob_livraison_incluse")),
                }
            )
        if "chapiteau" in type_codes:
            vals.update(
                {
                    "chap_tailles_disponibles": (
                        kw.get("chap_tailles_disponibles") or ""
                    ).strip()
                    or False,
                    "chap_prix_par_taille": (kw.get("chap_prix_par_taille") or "").strip()
                    or False,
                    "chap_delai_montage": (kw.get("chap_delai_montage") or "").strip()
                    or False,
                    "chap_contraintes_terrain": (
                        kw.get("chap_contraintes_terrain") or ""
                    ).strip()
                    or False,
                }
            )
        if "decoration_generale" in type_codes:
            vals.update(
                {
                    "dec_services_inclus": (kw.get("dec_services_inclus") or "").strip()
                    or False,
                    "dec_prix": (kw.get("dec_prix") or "").strip() or False,
                }
            )
        deco.with_context(coins_deco_portal=True).write(vals)
        self._save_photos(deco)

    def _save_photos(self, deco):
        Photo = request.env["coins.deco.prestataire.photo"].sudo()
        Theme = request.env["coins.deco.prestataire.theme"].sudo()
        files = request.httprequest.files.getlist("photos")
        theme_codes = request.httprequest.form.getlist("photo_theme")
        seq = max(deco.photo_ids.mapped("sequence") or [0]) + 10
        for index, upload in enumerate(files):
            raw = upload.read() if upload else b""
            if not raw:
                continue
            code = theme_codes[index] if index < len(theme_codes) else ""
            if code not in DECO_THEME_CODES:
                code = (request.httprequest.form.get("photo_theme_default") or "").strip()
            theme = Theme.search([("code", "=", code)], limit=1) if code else Theme.browse()
            if not theme:
                continue
            Photo.create(
                {
                    "prestataire_id": deco.id,
                    "image": base64.b64encode(raw),
                    "legende": (upload.filename or "")[:80],
                    "theme_id": theme.id,
                    "sequence": seq,
                }
            )
            seq += 10
        for theme in deco.theme_ids:
            extra = request.httprequest.files.getlist("photos_%s" % theme.code)
            for upload in extra:
                raw = upload.read() if upload else b""
                if not raw:
                    continue
                Photo.create(
                    {
                        "prestataire_id": deco.id,
                        "image": base64.b64encode(raw),
                        "legende": (upload.filename or theme.name or "")[:80],
                        "theme_id": theme.id,
                        "sequence": seq,
                    }
                )
                seq += 10

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
