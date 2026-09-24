# -*- coding: utf-8 -*-
from odoo import _, api, fields, models

from .reno_rdv_tz import (
    RENO_MARTIN_RDV_TEAM_XMLIDS,
    reno_format_canada_short,
)


class CrmLeadMartinBooking(models.Model):
    _inherit = "crm.lead"

    reno_martin_rdv_ok = fields.Boolean(
        compute="_compute_reno_martin_rdv_ok",
        search="_search_reno_martin_rdv_ok",
    )
    reno_rdv_event_id = fields.Many2one(
        "calendar.event",
        string="RDV Martin (Réno)",
        copy=False,
        ondelete="set null",
        index=True,
    )
    reno_rdv_ids = fields.One2many(
        "renovation.partner.rdv",
        "lead_id",
        string="RDV partenaires Réno",
    )
    reno_rdv_slot_display = fields.Char(
        compute="_compute_reno_rdv_display",
        string="Créneau client",
    )
    reno_rdv_booked_display = fields.Char(
        compute="_compute_reno_rdv_display",
        string="RDV pris le",
    )
    reno_rdv_meeting_label = fields.Char(
        compute="_compute_reno_rdv_display",
    )

    def _reno_martin_rdv_team_ids(self):
        ids = []
        for xmlid in RENO_MARTIN_RDV_TEAM_XMLIDS:
            team = self.env.ref(xmlid, raise_if_not_found=False)
            if team:
                ids.append(team.id)
        return ids

    @api.depends("team_id")
    def _compute_reno_martin_rdv_ok(self):
        team_ids = set(self._reno_martin_rdv_team_ids())
        for lead in self:
            lead.reno_martin_rdv_ok = bool(lead.team_id.id in team_ids)

    def _search_reno_martin_rdv_ok(self, operator, value):
        team_ids = self._reno_martin_rdv_team_ids()
        if operator in ("=", "==") and value:
            return [("team_id", "in", team_ids)]
        if operator in ("=", "==") and not value:
            return [("team_id", "not in", team_ids)]
        if operator in ("!=", "<>") and value:
            return [("team_id", "not in", team_ids)]
        return [("team_id", "in", team_ids)]

    @api.depends(
        "reno_rdv_event_id",
        "reno_rdv_event_id.start",
        "reno_rdv_event_id.create_date",
        "reno_rdv_event_id.active",
    )
    def _compute_reno_rdv_display(self):
        for lead in self:
            event = lead.reno_rdv_event_id
            if event and event.active and event.start:
                lead.reno_rdv_meeting_label = _("Prochaine réunion")
                lead.reno_rdv_slot_display = reno_format_canada_short(event.start)
                booked = reno_format_canada_short(event.create_date)
                lead.reno_rdv_booked_display = (
                    _("Pris le %s") % booked if booked else False
                )
            else:
                lead.reno_rdv_meeting_label = _("Aucune réunion")
                lead.reno_rdv_slot_display = False
                lead.reno_rdv_booked_display = False

    def action_reno_book_martin(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": _("Planifier une réunion (Martin)"),
            "res_model": "renovation.book.martin.wizard",
            "view_mode": "form",
            "target": "new",
            "context": {"default_lead_id": self.id},
        }

    def action_reno_meeting_stat(self):
        self.ensure_one()
        event = self.reno_rdv_event_id
        if event and event.active:
            return {
                "type": "ir.actions.act_window",
                "name": _("Réunion"),
                "res_model": "calendar.event",
                "view_mode": "form",
                "res_id": event.id,
                "target": "current",
            }
        return self.action_reno_book_martin()
