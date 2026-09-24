# -*- coding: utf-8 -*-
import logging
from datetime import date

from odoo import api, fields, models

from odoo.addons.coins_marocain.services.channex_service import (
    ChannexNotConfigured,
    ChannexService,
)

_logger = logging.getLogger(__name__)


class CoinsChannexPush(models.Model):
    """File ARI : on ferme d'abord en local, on pousse vers les OTA dès que la clé est là."""

    _name = "coins.channex.push"
    _description = "File push Channex (fermeture / réouverture OTA)"
    _order = "id desc"

    name = fields.Char(string="Libellé", compute="_compute_name", store=True)
    property_id = fields.Many2one(
        "coins.property",
        string="Bien",
        required=True,
        ondelete="cascade",
        index=True,
    )
    date_from = fields.Date(string="Du", required=True)
    date_to = fields.Date(string="Au", required=True)
    action = fields.Selection(
        [
            ("close", "Fermer les OTA (dispo 0)"),
            ("recompute", "Recalculer et pousser"),
        ],
        string="Action",
        required=True,
        default="close",
    )
    reason = fields.Selection(
        [
            ("evenement", "Événement Coins (priorité 1)"),
            ("reservation", "Réservation Coins (priorité 2)"),
            ("ota", "Réservation OTA"),
            ("manuel", "Manuel"),
        ],
        string="Motif",
        required=True,
        default="reservation",
    )
    origin = fields.Char(string="Origine")
    state = fields.Selection(
        [
            ("pending", "En attente (clé API)"),
            ("ready", "Prêt à pousser"),
            ("done", "Poussé"),
            ("error", "Erreur"),
        ],
        string="Statut",
        default="pending",
        required=True,
        index=True,
    )
    error_message = fields.Text(string="Erreur")
    payload_preview = fields.Text(string="Payload")

    @api.depends("property_id", "action", "date_from", "date_to")
    def _compute_name(self):
        for rec in self:
            rec.name = "%s %s %s → %s" % (
                rec.action or "?",
                rec.property_id.display_name or "",
                rec.date_from or "",
                rec.date_to or "",
            )

    @api.model
    def enqueue(self, property_id, date_from, date_to, reason, origin="", action="close"):
        if not property_id or not date_from or not date_to:
            return self.browse()
        if date_to < date_from:
            date_from, date_to = date_to, date_from
        today = date.today()
        if date_to < today:
            return self.browse()
        if date_from < today:
            date_from = today
        twin = self.search(
            [
                ("property_id", "=", property_id),
                ("date_from", "=", date_from),
                ("date_to", "=", date_to),
                ("action", "=", action),
                ("state", "in", ("pending", "ready", "done")),
            ],
            limit=1,
        )
        if twin and action == "close":
            return twin
        svc = ChannexService(self.env)
        state = "ready" if svc.ready else "pending"
        return self.create(
            {
                "property_id": property_id,
                "date_from": date_from,
                "date_to": date_to,
                "reason": reason,
                "origin": origin,
                "action": action,
                "state": state,
            }
        )

    def action_retry(self):
        self.write({"state": "ready", "error_message": False})
        self._process()

    def _process(self):
        svc = ChannexService(self.env)
        for rec in self:
            if rec.state == "done":
                continue
            if not svc.ready:
                rec.state = "pending"
                rec.error_message = "Clé API Channex pas encore configurée."
                continue
            mapping = self.env["coins.channex.mapping"].search(
                [
                    ("kind", "=", "property"),
                    ("local_id", "=", rec.property_id.id),
                ],
                limit=1,
            )
            if not mapping:
                rec.write(
                    {
                        "state": "error",
                        "error_message": "Bien non mappé Channex — renseigner l'UUID propriété.",
                    }
                )
                continue
            rooms = self.env["coins.channex.mapping"].search(
                [
                    ("kind", "=", "room_type"),
                    ("property_id", "=", rec.property_id.id),
                ]
            )
            avail = 0 if rec.action == "close" else rec._availability_for_range()
            from odoo.addons.coins_marocain.services.channex_ari import (
                date_range,
                merge_availability_values,
            )

            window = date_range(rec.date_from, rec.date_to)
            if rooms:
                values = [
                    {
                        "property_id": mapping.channex_id,
                        "room_type_id": room.channex_id,
                        "availability": avail,
                        **window,
                    }
                    for room in rooms
                ]
            else:
                values = [
                    {
                        "property_id": mapping.channex_id,
                        "room_type_id": mapping.channex_id,
                        "availability": avail,
                        **window,
                    }
                ]
            values = merge_availability_values(values)
            rec.payload_preview = str(values)
            try:
                body = svc.push_availability(values)
                rec.write(
                    {
                        "state": "done",
                        "error_message": False,
                        "payload_preview": "task_ids=%s\n%s"
                        % (svc.task_ids(body), values),
                    }
                )
            except ChannexNotConfigured:
                rec.write({"state": "pending", "error_message": "Clé absente"})
            except Exception as exc:  # noqa: BLE001
                _logger.exception("channex push %s", rec.id)
                rec.write({"state": "error", "error_message": str(exc)[:2000]})

    def _availability_for_range(self):
        self.ensure_one()
        return 0 if self.property_id._channex_range_closed(self.date_from, self.date_to) else 1

    @api.model
    def cron_flush(self):
        """File des *changements* seulement — pas de full sync minute."""
        svc = ChannexService(self.env)
        if not svc.ready:
            return True
        todo = self.search([("state", "in", ("ready", "pending"))], limit=80)
        todo._process()
        return True

    @api.model
    def full_sync_property(self, property_id, days=500):
        """Go-live / recovery : 2 POST (dispo + restrictions), 500 jours. Pas un cron."""
        from datetime import date as date_cls

        from odoo.addons.coins_marocain.services.channex_ari import (
            assert_full_sync_restrictions,
            build_full_sync_availability,
            build_full_sync_restrictions,
            classify_rate_plan_note,
            classify_room_type_note,
        )

        prop = self.env["coins.property"].browse(property_id)
        if not prop.exists():
            raise ValueError("Bien introuvable")
        Map = self.env["coins.channex.mapping"]
        mapping = Map.search(
            [("kind", "=", "property"), ("local_id", "=", prop.id)], limit=1
        )
        if not mapping:
            raise ValueError("Bien non mappé Channex")
        rooms = {}
        for m in Map.search(
            [("kind", "=", "room_type"), ("property_id", "=", prop.id)]
        ):
            key = classify_room_type_note(m.note)
            if key:
                rooms[key] = m.channex_id
        twin = rooms.get("twin")
        double = rooms.get("double")
        if not twin or not double:
            raise ValueError("Room types Twin / Double manquants dans le mapping")
        plans = {}
        for m in Map.search([("kind", "=", "rate_plan"), ("property_id", "=", prop.id)]):
            key = classify_rate_plan_note(m.note)
            if key:
                plans[key] = m.channex_id
        if len(plans) < 4:
            raise ValueError("4 rate plans requis pour le full sync certif")
        start = date_cls.today()
        svc = ChannexService(self.env)
        try:
            svc.ensure_restriction_settings(mapping.channex_id)
        except Exception:  # noqa: BLE001
            _logger.exception("channex property settings %s", mapping.channex_id)
        avail = build_full_sync_availability(
            mapping.channex_id, twin, double, start, days=days
        )
        rates = assert_full_sync_restrictions(
            build_full_sync_restrictions(
                mapping.channex_id, plans, start, days=days
            )
        )
        body_a = svc.push_availability(avail)
        body_r = svc.push_restrictions(rates)
        return {
            "availability_task_ids": svc.task_ids(body_a),
            "restrictions_task_ids": svc.task_ids(body_r),
        }
