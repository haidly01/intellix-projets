# -*- coding: utf-8 -*-
"""Fiche et résas démo Mon Coin — isolées, jamais mélangées au réel."""
import base64
import io
import logging
import secrets
from datetime import date

from odoo import api, models

_logger = logging.getLogger(__name__)

DEMO_EMAIL = "portal.demo.moncoin@intellixcrm.com"
DEMO_LOGIN = DEMO_EMAIL
DEMO_PARTNERSHIP_NAME = "[DÉMO] Café des Trois Rives"
DEMO_PROPERTY_NAME = "[DÉMO] Café des Trois Rives"
DEMO_RES_PREFIX = "DEMO-MONCOIN-"
DEMO_NOTE = (
    "DÉMO MON COIN — Café des Trois Rives, Sorel-Tracy. "
    "Données fictives, hors production. Ne pas facturer."
)
PROTECTED_RESERVATION_NAMES = ("CQ-RES/2026/0001",)
PROTECTED_NAME_FRAGMENTS = (
    "atelier du pin",
    "gîte test coins québec",
    "gite test coins quebec",
)

# Occupation crédible (~70 %) sur 5 chambres, 25/08 → 07/09/2026.
# check_out exclusif. Montants CAD réalistes pour un gîte Laurentides.
DEMO_STAYS = (
    ("001", "2026-08-25", "2026-08-28", 867.0, "direct", "Sophie Tremblay"),
    ("002", "2026-08-26", "2026-08-30", 1156.0, "booking", "Marc Lavoie"),
    ("003", "2026-08-28", "2026-09-01", 1156.0, "airbnb", "Amélie Roy"),
    ("004", "2026-08-30", "2026-09-02", 578.0, "direct", "Jean-François Côté"),
    ("005", "2026-09-02", "2026-09-06", 1156.0, "booking", "Nadia Benoit"),
    ("006", "2026-09-04", "2026-09-07", 867.0, "direct", "Olivier Gagnon"),
)

DEMO_SERVICES = (
    ("Espresso", 3.5, "/ tasse"),
    ("Brunch du samedi", 24.0, "/ pers."),
)

DEMO_OFFERS = (
    ("Carte 10 cafés", 32.0, "10 consommations"),
)


def _name_is_protected_real(name):
    n = (name or "").strip().lower()
    if not n:
        return False
    if n in {p.lower() for p in PROTECTED_RESERVATION_NAMES}:
        return True
    return any(frag in n for frag in PROTECTED_NAME_FRAGMENTS)


class CoinsQuebecPartenariatDemo(models.Model):
    _inherit = "coins.quebec.partenariat"

    def _name_is_protected_real(self):
        self.ensure_one()
        return _name_is_protected_real(self.name)

    def _demo_placeholder_image(self):
        try:
            from PIL import Image, ImageDraw, ImageFont
        except ImportError:
            # PNG 1×1 vert forêt — fallback si Pillow absent.
            return (
                "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+"
                "M9QDwADhgGAWjR9awAAAABJRU5ErkJggg=="
            )
        img = Image.new("RGB", (640, 400), (27, 58, 47))
        draw = ImageDraw.Draw(img)
        draw.rectangle([0, 300, 640, 400], fill=(18, 40, 34))
        draw.ellipse([420, 40, 560, 180], fill=(46, 111, 126))
        try:
            font = ImageFont.load_default()
            draw.text((36, 320), "[DEMO] Cafe des Trois Rives", fill=(242, 232, 213), font=font)
        except Exception:  # noqa: BLE001
            draw.text((36, 320), "[DEMO] Cafe des Trois Rives", fill=(242, 232, 213))
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=82)
        return base64.b64encode(buf.getvalue()).decode("ascii")

    def _demo_partner(self, name, email):
        Partner = self.env["res.partner"].sudo()
        rec = Partner.search([("email", "=", email)], limit=1)
        if rec:
            return rec
        rec = Partner.search([("name", "=", name)], limit=1)
        if rec:
            return rec
        return Partner.create(
            {
                "name": name,
                "email": email,
                "comment": DEMO_NOTE,
                "is_company": name.startswith("[DÉMO]"),
            }
        )

    def _demo_property(self):
        Prop = self.env["coins.quebec.property"].sudo()
        prop = Prop.with_context(active_test=False).search(
            [("is_demo", "=", True)], limit=1
        )
        if not prop:
            prop = Prop.with_context(active_test=False).search(
                [("name", "=", DEMO_PROPERTY_NAME)], limit=1
            )
        if prop and _name_is_protected_real(prop.name):
            return Prop.browse()
        vals = {
            "name": DEMO_PROPERTY_NAME,
            "is_demo": True,
            "property_type": "auberge",
            "state": "active",
            "street": "128 rue Augusta",
            "city": "Sorel-Tracy",
            "province": "Québec",
            "phone": "450 746-2210",
            "email": DEMO_EMAIL,
            "nb_chambres": 2,
            "location_chambre_unite": True,
            "tarif_nuit": 0.0,
            "commission_pct": 15.0,
            "notes": DEMO_NOTE,
        }
        if prop:
            prop.write(vals)
            return prop
        return Prop.create(vals)

    def _demo_reservations(self, prop):
        if not prop:
            return self.env["coins.quebec.reservation"]
        Res = self.env["coins.quebec.reservation"].sudo()
        existing = {
            (r.name or "").strip(): r
            for r in Res.with_context(active_test=False).search(
                [("name", "like", DEMO_RES_PREFIX)]
            )
        }
        created = self.env["coins.quebec.reservation"]
        for suffix, cin, cout, amount, source, guest in DEMO_STAYS:
            ref = "%s%s" % (DEMO_RES_PREFIX, suffix)
            if ref in PROTECTED_RESERVATION_NAMES:
                continue
            partner = self._demo_partner(
                "[DÉMO] %s" % guest,
                "demo.moncoin.%s@example.invalid" % suffix,
            )
            vals = {
                "name": ref,
                "is_demo": True,
                "traveler_id": partner.id,
                "property_id": prop.id,
                "check_in": date.fromisoformat(cin),
                "check_out": date.fromisoformat(cout),
                "state": "confirmed",
                "source": source,
                "amount_property": amount,
                "amount_tax": round(amount * 0.14975, 2),
                "payment_status": "paid",
                "notes": DEMO_NOTE,
            }
            rec = existing.get(ref)
            if rec:
                if (rec.name or "").strip() in PROTECTED_RESERVATION_NAMES:
                    continue
                if _name_is_protected_real(rec.property_id.name):
                    continue
                rec.write(vals)
            else:
                rec = Res.create(vals)
            created |= rec
        return created

    def _demo_portal_user(self, partnership):
        Users = self.env["res.users"].sudo().with_context(active_test=False)
        user = partnership.portal_user_id
        if not user:
            user = Users.search([("login", "=", DEMO_LOGIN)], limit=1)
        if user and user.exists():
            if partnership.portal_user_id != user:
                partnership.sudo().write({"portal_user_id": user.id})
            return user
        partner = partnership.partner_id or self._demo_partner(
            DEMO_PARTNERSHIP_NAME, DEMO_EMAIL
        )
        if not partnership.partner_id:
            partnership.sudo().write({"partner_id": partner.id})
        pwd = secrets.token_urlsafe(12)
        self.env["ir.config_parameter"].sudo().set_param(
            "coins_quebec.mon_coin_demo_password", pwd
        )
        groups = partnership._portal_group_ids()
        vals = {
            "name": "Portail Démo Mon Coin",
            "login": DEMO_LOGIN,
            "email": DEMO_EMAIL,
            "password": pwd,
            "partner_id": partner.id,
            "share": True,
        }
        if "group_ids" in self.env["res.users"]._fields:
            vals["group_ids"] = [(6, 0, groups)]
        else:
            vals["groups_id"] = [(6, 0, groups)]
        user = Users.with_context(no_reset_password=True, mail_create_nolog=True).create(
            vals
        )
        partnership.sudo().write({"portal_user_id": user.id, "partner_id": partner.id})
        return user

    def _fill_demo_lines(self, partnership):
        Svc = self.env["coins.quebec.partenariat.service"].sudo()
        Off = self.env["coins.quebec.partenariat.forfait"].sudo()
        Photo = self.env["coins.quebec.partenariat.photo"].sudo()
        svc_names = set(partnership.service_ids.mapped("name"))
        if partnership.service_ids and "Espresso" not in svc_names:
            partnership.service_ids.unlink()
        if not partnership.service_ids:
            seq = 10
            for name, price, unit in DEMO_SERVICES:
                Svc.create(
                    {
                        "partenariat_id": partnership.id,
                        "name": name,
                        "price": price,
                        "unit": unit,
                        "sequence": seq,
                    }
                )
                seq += 10
        off_names = set(partnership.offer_ids.mapped("name"))
        if partnership.offer_ids and "Carte 10 cafés" not in off_names:
            partnership.offer_ids.unlink()
        if not partnership.offer_ids:
            seq = 10
            for name, price, unit in DEMO_OFFERS:
                Off.create(
                    {
                        "partenariat_id": partnership.id,
                        "name": name,
                        "price": price,
                        "unit": unit,
                        "sequence": seq,
                    }
                )
                seq += 10
        if not partnership.photo_ids:
            Photo.create(
                {
                    "partenariat_id": partnership.id,
                    "image": self._demo_placeholder_image(),
                    "caption": "[DÉMO] Terrasse — Café des Trois Rives",
                    "sequence": 10,
                }
            )

    @api.model
    def ensure_mon_coin_demo_data(self):
        """Crée / complète la fiche démo isolée. Ne touche jamais une fiche réelle."""
        Part = self.sudo().with_context(active_test=False)
        rec = Part.search([("is_demo", "=", True)], limit=1)
        if not rec:
            rec = Part.search([("email", "=", DEMO_EMAIL)], limit=1)
        if not rec:
            rec = Part.search([("name", "=", DEMO_PARTNERSHIP_NAME)], limit=1)
        if rec and not rec.is_demo and rec._name_is_protected_real():
            _logger.warning(
                "ensure_mon_coin_demo_data: fiche réelle protégée id=%s, abandon", rec.id
            )
            return Part.browse()
        prop = self._demo_property()
        if not prop:
            _logger.warning("ensure_mon_coin_demo_data: bien démo refusé (nom protégé)")
            return Part.browse()
        self._demo_reservations(prop)
        partner = self._demo_partner(DEMO_PARTNERSHIP_NAME, DEMO_EMAIL)
        vals = {
            "name": DEMO_PARTNERSHIP_NAME,
            "is_demo": True,
            "contact_name": "Camille Rivard",
            "phone": "450 746-2210",
            "email": DEMO_EMAIL,
            "type_partenaire": "resto",
            "region": "sorel",
            "zone": False,
            "city": "Sorel-Tracy",
            "street": "128 rue Augusta, Sorel-Tracy, QC",
            "partner_lat": 46.0428,
            "partner_lng": -73.1123,
            "source": "manuel",
            "stage": "gagne",
            "publish_state": "published",
            "property_id": prop.id,
            "partner_id": partner.id,
            "description": (
                "Café de quartier sur le Richelieu : grains torréfiés sur place, "
                "pâtisserie du matin et épicerie fine locale. Salle intérieure et terrasse. "
                "Fiche de démonstration Mon Coin — hors production."
            ),
            "video_url": "https://www.youtube.com/watch?v=exemple-trois-rives",
            "pin_view_count": 86,
            "pin_click_count": 31,
            "notes": DEMO_NOTE,
            "fiche_lien": "https://intellixcrm.com/mon-coin/demo",
            "active": True,
        }
        if rec:
            rec.write(vals)
        else:
            rec = Part.create(vals)
        if rec._name_is_protected_real() or not rec.is_demo:
            _logger.warning(
                "ensure_mon_coin_demo_data: isolation échouée id=%s", rec.id
            )
            return Part.browse()
        extras = Part.search([("is_demo", "=", True), ("id", "!=", rec.id)])
        if extras:
            extras.write({"active": False, "notes": DEMO_NOTE + " Doublon archivé."})
        self._fill_demo_lines(rec)
        self._demo_portal_user(rec)
        _logger.info(
            "Mon Coin démo prêt: partenariat id=%s property id=%s user=%s",
            rec.id,
            rec.property_id.id,
            rec.portal_user_id.login,
        )
        return rec
