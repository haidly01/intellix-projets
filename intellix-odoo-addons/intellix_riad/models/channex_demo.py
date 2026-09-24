# -*- coding: utf-8 -*-
"""Réservations fictives Channex — clairement marquées, jamais mélangées au réel."""
from datetime import date

from odoo import api, models

DEMO_PREFIX = "DEMO-CHANNEX-"
DEMO_NOTE = (
    "DÉMO CHANNNEX — données fictives pour la présentation Module Hébergement. "
    "Ne pas traiter comme une réservation réelle. Ne pas facturer. "
    "Ne pas pousser vers une OTA."
)
PROTECTED_RESERVATION_NAMES = ("CQ-RES/2026/0001",)
PROTECTED_PROPERTY_NAMES = ("gîte test coins québec", "gite test coins quebec")

# Occupancy 60–85 % on Riad Anna Sweety (5 existing rooms), 25/08 → 07/09/2026.
# check_out exclusive. Mixed Booking / direct / Channex.
DEMO_STAYS = (
    ("001", "Suite Anna Sweety", "2026-08-25", "2026-08-28", "channex"),
    ("002", "Suite Rose de Paris", "2026-08-25", "2026-08-29", "booking"),
    ("003", "Suite Jasmin d'Orient", "2026-08-26", "2026-08-29", "direct"),
    ("004", "Secret d'Amour", "2026-08-25", "2026-08-27", "booking"),
    ("005", "Suite Perle de Marrakech", "2026-08-28", "2026-09-01", "channex"),
    ("006", "Suite Anna Sweety", "2026-08-29", "2026-09-02", "direct"),
    ("007", "Secret d'Amour", "2026-08-28", "2026-09-01", "direct"),
    ("008", "Suite Rose de Paris", "2026-08-30", "2026-09-03", "channex"),
    ("009", "Suite Jasmin d'Orient", "2026-09-01", "2026-09-04", "booking"),
    ("010", "Suite Perle de Marrakech", "2026-09-02", "2026-09-06", "booking"),
    ("011", "Suite Anna Sweety", "2026-09-03", "2026-09-07", "channex"),
    ("012", "Secret d'Amour", "2026-09-02", "2026-09-05", "direct"),
    ("013", "Suite Rose de Paris", "2026-09-04", "2026-09-08", "booking"),
    ("014", "Suite Jasmin d'Orient", "2026-09-04", "2026-09-07", "channex"),
    ("015", "Suite Perle de Marrakech", "2026-09-07", "2026-09-10", "direct"),
    ("016", "Suite Jasmin d'Orient", "2026-09-07", "2026-09-09", "booking"),
)


class CoinsReservationChannexDemo(models.Model):
    _inherit = "coins.reservation"

    def _channex_demo_property(self):
        Prop = self.env["coins.property"].sudo()
        prop = Prop.search([("name", "=", "Riad Anna Sweety")], limit=1)
        if not prop:
            return Prop.browse()
        if (prop.name or "").strip().lower() in PROTECTED_PROPERTY_NAMES:
            return Prop.browse()
        return prop

    def _channex_demo_rooms(self, prop):
        rooms = {}
        for room in prop.room_ids.filtered("active"):
            rooms[(room.name or "").strip()] = room
        return rooms

    def _channex_demo_partner(self, suffix):
        Partner = self.env["res.partner"].sudo()
        name = "[DÉMO CHANNNEX] Invité %s" % suffix
        partner = Partner.search([("name", "=", name)], limit=1)
        if partner:
            return partner
        return Partner.create(
            {
                "name": name,
                "comment": DEMO_NOTE,
                "email": "demo.channex.%s@example.invalid" % suffix.lower(),
            }
        )

    def _is_protected_reservation(self, rec):
        name = (rec.name or "").strip()
        if name in PROTECTED_RESERVATION_NAMES:
            return True
        prop = (rec.property_id.name or "").strip().lower()
        return prop in PROTECTED_PROPERTY_NAMES

    @api.model
    def ensure_channex_demo_data(self):
        """Crée les résas démo manquantes. Ne touche pas aux résas réelles."""
        Res = self.sudo()
        prop = self._channex_demo_property()
        if not prop:
            return True
        rooms = self._channex_demo_rooms(prop)
        if not rooms:
            return True

        existing = {
            (r.name or "").strip(): r
            for r in Res.with_context(active_test=False).search(
                [("name", "like", DEMO_PREFIX)]
            )
        }
        created = 0
        for suffix, room_name, cin, cout, source in DEMO_STAYS:
            ref = "%s%s" % (DEMO_PREFIX, suffix)
            if ref in existing:
                rec = existing[ref]
                if self._is_protected_reservation(rec):
                    continue
                if not rec.is_demo:
                    rec.write(
                        {
                            "is_demo": True,
                            "notes": DEMO_NOTE,
                            "client_nom": rec.client_nom or "[DÉMO] %s" % suffix,
                        }
                    )
                continue
            room = rooms.get(room_name)
            if not room:
                continue
            partner = self._channex_demo_partner(suffix)
            channel = "ota" if source in ("channex", "booking") else "backoffice"
            Res.with_context(skip_calendar_sync=True).create(
                {
                    "name": ref,
                    "is_demo": True,
                    "traveler_id": partner.id,
                    "property_id": prop.id,
                    "room_id": room.id,
                    "check_in": date.fromisoformat(cin),
                    "check_out": date.fromisoformat(cout),
                    "state": "confirmed",
                    "source": source,
                    "booking_channel": channel,
                    "client_nom": "[DÉMO] Voyageur %s" % suffix,
                    "notes": DEMO_NOTE,
                    "channex_booking_id": ref if source == "channex" else False,
                    "amount_property": 1800.0,
                    "payment_status": "paid",
                    "voyageurs": 2,
                    "calendar_color": 3,
                }
            )
            created += 1
        return True
