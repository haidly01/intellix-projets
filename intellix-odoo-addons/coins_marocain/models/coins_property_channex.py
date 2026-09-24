# -*- coding: utf-8 -*-
from odoo import fields, models


class CoinsPropertyChannex(models.Model):
    _inherit = "coins.property"

    channex_mapping_ids = fields.One2many(
        "coins.channex.mapping",
        "property_id",
        string="Mappings Channex",
    )
    channex_push_ids = fields.One2many(
        "coins.channex.push",
        "property_id",
        string="File OTA",
    )
    channex_calendar_ids = fields.One2many(
        "coins.channex.calendar",
        "property_id",
        string="Tarifs OTA",
    )

    def _channex_range_closed(
        self, date_from, date_to, exclude_reservation_id=None, exclude_evenement_id=None
    ):
        self.ensure_one()
        domain = [
            ("property_id", "=", self.id),
            ("statut", "=", "confirme"),
            ("date_debut", "<=", date_to),
            ("date_fin", ">=", date_from),
        ]
        blocks = self.env["coins.property.blocage"].search(domain)
        if exclude_reservation_id:
            blocks = blocks.filtered(
                lambda b: b.reservation_id.id != exclude_reservation_id
            )
        if exclude_evenement_id:
            blocks = blocks.filtered(
                lambda b: b.evenement_id.id != exclude_evenement_id
            )
        return bool(blocks)

    def _flag_overlapping_ota(self, date_from, date_to, origin=""):
        """Une fermeture Coins (événement / résa) gagne : les OTA déjà confirmées restent, flag humain."""
        Res = self.env["coins.reservation"]
        otas = Res.search(
            [
                ("property_id", "=", self.id),
                ("state", "in", ("confirmed", "in_progress")),
                ("source", "in", ("booking", "airbnb", "expedia", "channex")),
                ("check_in", "<=", date_to),
                ("check_out", ">", date_from),
                ("overbooking", "=", False),
            ]
        )
        for rec in otas:
            rec.overbooking = True
            rec.activity_schedule(
                "mail.mail_activity_data_todo",
                summary="Overbooking OTA — traiter à la main",
                note=origin or "Plage fermée par un événement ou une résa Coins.",
            )

    def _close_otas(self, date_from, date_to, reason, origin, source="direct", extra=None):
        """Priorité Coins : on bloque localement puis on met la fermeture OTA en file."""
        extra = extra or {}
        for prop in self:
            if not date_from or not date_to:
                continue
            domain = [
                ("property_id", "=", prop.id),
                ("date_debut", "=", date_from),
                ("date_fin", "=", date_to),
                ("statut", "=", "confirme"),
                ("source", "=", source),
            ]
            if extra.get("reservation_id"):
                domain.append(("reservation_id", "=", extra["reservation_id"]))
            if extra.get("evenement_id"):
                domain.append(("evenement_id", "=", extra["evenement_id"]))
            existing = self.env["coins.property.blocage"].search(domain, limit=1)
            if not existing:
                vals = {
                    "property_id": prop.id,
                    "date_debut": date_from,
                    "date_fin": date_to,
                    "source": source,
                    "statut": "confirme",
                    "summary": origin or reason,
                    "reservation_id": extra.get("reservation_id") or False,
                    "evenement_id": extra.get("evenement_id") or False,
                }
                existing = self.env["coins.property.blocage"].create(vals)
            self.env["coins.channex.push"].enqueue(
                prop.id, date_from, date_to, reason, origin=origin, action="close"
            )
            if reason in ("evenement", "reservation"):
                prop._flag_overlapping_ota(
                    date_from, date_to, origin=origin or reason
                )
        return True

    def action_channex_push_calendar(self):
        """Un batch restrictions + un batch dispo pour toutes les lignes du bien."""
        self.ensure_one()
        lines = self.channex_calendar_ids
        if not lines:
            return True
        lines.with_context(channex_calendar_silent=True)._push_to_channex()
        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": "Channex calendrier",
                "message": "%s ligne(s) poussées en un batch." % len(lines),
                "type": "success",
            },
        }

    def action_channex_full_sync(self):
        """Manuel uniquement (go-live / recovery). Jamais sur un timer 5 min."""
        self.ensure_one()
        result = self.env["coins.channex.push"].full_sync_property(self.id)
        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": "Channex Full Sync",
                "message": "Availability %s — Restrictions %s"
                % (
                    ", ".join(result.get("availability_task_ids") or []),
                    ", ".join(result.get("restrictions_task_ids") or []),
                ),
                "type": "success",
                "sticky": True,
            },
        }

    def _release_otas_if_free(self, date_from, date_to, origin=""):
        for prop in self:
            if prop._channex_range_closed(date_from, date_to):
                continue
            self.env["coins.channex.push"].enqueue(
                prop.id,
                date_from,
                date_to,
                "manuel",
                origin=origin or "réouverture",
                action="recompute",
            )
