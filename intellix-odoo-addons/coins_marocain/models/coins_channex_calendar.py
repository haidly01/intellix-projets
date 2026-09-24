# -*- coding: utf-8 -*-
"""Calendrier tarif / min-stay / dispo OTA — save IntelliX → file Channex."""
import logging
from datetime import date

from odoo import api, fields, models
from odoo.exceptions import UserError

from odoo.addons.coins_marocain.services.channex_service import (
    ChannexNotConfigured,
    ChannexService,
)

_logger = logging.getLogger(__name__)


def _extract_task_ids(body):
    try:
        from odoo.addons.coins_marocain.services.channex_ari import task_ids
        return list(task_ids(body) or [])
    except Exception:  # noqa: BLE001
        pass
    data = (body or {}).get("data") if isinstance(body, dict) else None
    if isinstance(data, list):
        return [str(item.get("id")) for item in data if isinstance(item, dict) and item.get("id")]
    if isinstance(data, dict) and data.get("id"):
        return [str(data["id"])]
    return []


class CoinsChannexCalendar(models.Model):
    _name = "coins.channex.calendar"
    _description = "Calendrier tarif OTA (Channex)"
    _order = "date_from desc, id desc"

    name = fields.Char(string="Libellé", compute="_compute_name", store=True)
    property_id = fields.Many2one(
        "coins.property",
        string="Bien",
        required=True,
        ondelete="cascade",
        index=True,
    )
    mapping_id = fields.Many2one(
        "coins.channex.mapping",
        string="Plan tarifaire",
        required=True,
        ondelete="restrict",
        domain="[('property_id', '=', property_id), ('kind', '=', 'rate_plan')]",
    )
    date_from = fields.Date(string="Du", required=True, default=fields.Date.context_today)
    date_to = fields.Date(string="Au", required=True, default=fields.Date.context_today)
    rate = fields.Float(string="Prix / nuit (USD)", digits=(16, 2))
    min_stay = fields.Integer(string="Min stay (nuits)")
    stop_sell = fields.Boolean(string="Stop sell")
    closed_to_arrival = fields.Boolean(string="Fermé à l'arrivée (CTA)")
    closed_to_departure = fields.Boolean(string="Fermé au départ (CTD)")
    max_stay = fields.Integer(string="Max stay (nuits)")
    push_availability = fields.Boolean(string="Pousser aussi la dispo")
    availability = fields.Integer(string="Disponibilité", default=0)
    state = fields.Selection(
        [
            ("draft", "Brouillon"),
            ("done", "Poussé Channex"),
            ("error", "Erreur"),
        ],
        string="Statut",
        default="draft",
        required=True,
    )
    last_task_ids = fields.Char(string="Task IDs Channex")
    error_message = fields.Text(string="Erreur")
    push_id = fields.Many2one("coins.channex.push", string="Ligne de file", ondelete="set null")

    @api.depends("mapping_id", "date_from", "date_to", "rate")
    def _compute_name(self):
        for rec in self:
            rec.name = "%s %s → %s @ %s" % (
                rec.mapping_id.note or rec.mapping_id.channex_id or "tarif",
                rec.date_from or "",
                rec.date_to or "",
                rec.rate or "",
            )

    @api.onchange("property_id")
    def _onchange_property_id(self):
        if self.mapping_id and self.mapping_id.property_id != self.property_id:
            self.mapping_id = False

    @api.model_create_multi
    def create(self, vals_list):
        recs = super().create(vals_list)
        field_map = {
            rec.id: frozenset(vals.keys()) for rec, vals in zip(recs, vals_list)
        }
        recs.with_context(
            channex_calendar_silent=True,
            channex_written_fields=field_map,
        )._push_to_channex()
        return recs

    def write(self, vals):
        res = super().write(vals)
        if self.env.context.get("channex_calendar_silent"):
            return res
        watched = {
            "mapping_id",
            "date_from",
            "date_to",
            "rate",
            "min_stay",
            "stop_sell",
            "closed_to_arrival",
            "closed_to_departure",
            "max_stay",
            "push_availability",
            "availability",
        }
        if watched.intersection(vals):
            field_map = {rec.id: frozenset(vals.keys()) for rec in self}
            self.with_context(
                channex_calendar_silent=True,
                channex_written_fields=field_map,
            )._push_to_channex()
        return res

    def action_push_now(self):
        self._push_to_channex()
        return True

    def _property_uuid(self):
        self.ensure_one()
        mapping = self.env["coins.channex.mapping"].search(
            [("kind", "=", "property"), ("local_id", "=", self.property_id.id)],
            limit=1,
        )
        if not mapping:
            raise UserError("Ce bien n'a pas de mapping Channex (UUID propriété).")
        return mapping.channex_id

    def _room_uuid_for_rate(self):
        self.ensure_one()
        note = (self.mapping_id.note or "").lower()
        rooms = self.env["coins.channex.mapping"].search(
            [("kind", "=", "room_type"), ("property_id", "=", self.property_id.id)]
        )
        if "twin" in note:
            hit = rooms.filtered(lambda m: "twin" in (m.note or "").lower())
        elif "double" in note:
            hit = rooms.filtered(lambda m: "double" in (m.note or "").lower())
        else:
            hit = rooms[:1]
        return hit[:1].channex_id if hit else False

    def _written_fields(self):
        field_map = self.env.context.get("channex_written_fields") or {}
        return field_map.get(self.id)

    def _restriction_payload(self):
        """N'envoie que les champs réellement sauvés (min stay sans CTA/CTD/stop sell)."""
        self.ensure_one()
        from odoo.addons.coins_marocain.services.channex_ari import date_range

        restrict = {
            "property_id": self._property_uuid(),
            "rate_plan_id": self.mapping_id.channex_id,
        }
        restrict.update(date_range(self.date_from, self.date_to))
        written = self._written_fields()

        def include(field):
            return written is None or field in written

        if include("rate") and self.rate:
            restrict["rate"] = "%.2f" % self.rate
        if include("min_stay") and self.min_stay:
            restrict["min_stay_arrival"] = int(self.min_stay)
            restrict["min_stay_through"] = int(self.min_stay)
        if include("max_stay") and self.max_stay:
            restrict["max_stay"] = int(self.max_stay)
        if include("stop_sell") and (written is not None or self.stop_sell):
            restrict["stop_sell"] = bool(self.stop_sell)
        if include("closed_to_arrival") and (
            written is not None or self.closed_to_arrival
        ):
            restrict["closed_to_arrival"] = bool(self.closed_to_arrival)
        if include("closed_to_departure") and (
            written is not None or self.closed_to_departure
        ):
            restrict["closed_to_departure"] = bool(self.closed_to_departure)
        return restrict

    def _availability_payload(self):
        self.ensure_one()
        from odoo.addons.coins_marocain.services.channex_ari import date_range

        room_uuid = self._room_uuid_for_rate()
        if not room_uuid:
            raise UserError("Room type Twin/Double introuvable pour ce plan.")
        payload = {
            "property_id": self._property_uuid(),
            "room_type_id": room_uuid,
            "availability": int(self.availability or 0),
        }
        payload.update(date_range(self.date_from, self.date_to))
        return payload

    def _push_to_channex(self):
        """Un POST restrictions + un POST availability pour tout le recordset."""
        from odoo.addons.coins_marocain.services.channex_ari import (
            merge_availability_values,
            restriction_has_update,
        )

        svc = ChannexService(self.env)
        ready = []
        for rec in self:
            if not rec.date_from or not rec.date_to:
                continue
            if rec.date_to < rec.date_from:
                rec.write(
                    {
                        "state": "error",
                        "error_message": "Date Au antérieure à Du.",
                    }
                )
                continue
            if rec.date_to < date.today():
                rec.write(
                    {
                        "state": "error",
                        "error_message": "Plage déjà passée — Channex n'accepte pas le passé.",
                    }
                )
                continue
            if not svc.ready:
                rec.write(
                    {
                        "state": "error",
                        "error_message": "Channex pas prêt (clé / enabled).",
                    }
                )
                continue
            ready.append(rec)
        if not ready:
            return
        try:
            restricts = [
                row
                for rec in ready
                for row in [rec._restriction_payload()]
                if restriction_has_update(row)
            ]
            avails = [
                rec._availability_payload()
                for rec in ready
                if rec.push_availability
            ]
            tasks = []
            if restricts:
                body_r = svc.push_restrictions(restricts)
                tasks.extend(_extract_task_ids(body_r))
            if avails:
                body_a = svc.push_availability(merge_availability_values(avails))
                tasks.extend(_extract_task_ids(body_a))
            for rec in ready:
                push = rec.env["coins.channex.push"].create(
                    {
                        "property_id": rec.property_id.id,
                        "date_from": rec.date_from,
                        "date_to": rec.date_to,
                        "action": "recompute",
                        "reason": "manuel",
                        "origin": "calendrier tarif %s" % (rec.mapping_id.note or rec.id),
                        "state": "done",
                        "payload_preview": "task_ids=%s" % tasks,
                    }
                )
                rec.write(
                    {
                        "state": "done",
                        "error_message": False,
                        "last_task_ids": ", ".join(str(t) for t in tasks if t),
                        "push_id": push.id,
                    }
                )
        except ChannexNotConfigured:
            for rec in ready:
                rec.write(
                    {
                        "state": "error",
                        "error_message": "Clé API Channex absente.",
                    }
                )
        except Exception as exc:  # noqa: BLE001
            _logger.exception("channex calendar batch")
            for rec in ready:
                rec.write({"state": "error", "error_message": str(exc)[:2000]})
