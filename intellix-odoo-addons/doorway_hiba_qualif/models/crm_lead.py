# -*- coding: utf-8 -*-

from datetime import datetime

import pytz

from odoo import api, fields, models


def _toronto_month_bounds():
    tz = pytz.timezone("America/Toronto")
    now = datetime.now(tz)
    start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    if start.month == 12:
        end = start.replace(year=start.year + 1, month=1)
    else:
        end = start.replace(month=start.month + 1)
    return (
        start.astimezone(pytz.utc).replace(tzinfo=None),
        end.astimezone(pytz.utc).replace(tzinfo=None),
    )


class CrmLead(models.Model):
    _inherit = "crm.lead"

    is_coins_quebec_pipeline = fields.Boolean(compute="_compute_is_coins_quebec_pipeline")
    hiba_interest_coins = fields.Boolean(string="Intérêt Coins Québec")
    hiba_interest_itex = fields.Boolean(string="Intérêt ITEX")
    hiba_interest_driven = fields.Boolean(string="Intérêt Driven")
    hiba_interest_marketing = fields.Boolean(string="Intérêt marketing général")
    hiba_interest_intellix = fields.Boolean(string="Intérêt IntelliX")
    hiba_interest_immobilier = fields.Boolean(string="Intérêt immobilier")
    hiba_interest_renovation = fields.Boolean(string="Intérêt rénovation")
    hiba_comment = fields.Text(string="Commentaires Hiba")
    hiba_rdv_event_id = fields.Many2one("calendar.event", string="RDV Martin", copy=False)
    hiba_rdv_start = fields.Datetime(related="hiba_rdv_event_id.start", string="Date RDV")
    hiba_rdv_booked_display = fields.Char(
        compute="_compute_hiba_rdv_booked_display",
        string="RDV pris le",
    )
    hiba_rdv_state = fields.Selection(
        [
            ("none", "Pas de RDV"),
            ("booked", "RDV booké"),
            ("present", "Présent"),
            ("noshow", "Absent"),
        ],
        string="Statut RDV",
        default="none",
        copy=False,
        index=True,
    )
    hiba_kpi_booked_month = fields.Integer(
        string="RDV bookés ce mois",
        compute="_compute_hiba_kpis",
    )
    hiba_kpi_present_month = fields.Integer(
        string="Présents ce mois",
        compute="_compute_hiba_kpis",
    )

    @api.depends(
        "hiba_rdv_event_id",
        "hiba_rdv_event_id.create_date",
        "hiba_rdv_event_id.start",
    )
    def _compute_hiba_rdv_booked_display(self):
        tz = pytz.timezone("America/Toronto")
        for lead in self:
            event = lead.hiba_rdv_event_id
            if not event or not event.create_date:
                lead.hiba_rdv_booked_display = False
                continue
            dt = event.create_date
            local = (
                dt.astimezone(tz)
                if getattr(dt, "tzinfo", None)
                else pytz.UTC.localize(dt).astimezone(tz)
            )
            lead.hiba_rdv_booked_display = local.strftime("%d/%m/%Y %Hh%M") + " (Canada)"

    @api.depends("team_id")
    def _compute_is_coins_quebec_pipeline(self):
        team = self.env.ref(
            "doorway_hiba_qualif.crm_team_coins_quebec", raise_if_not_found=False
        )
        for lead in self:
            lead.is_coins_quebec_pipeline = bool(team and lead.team_id == team)

    def _compute_hiba_kpis(self):
        start, end = _toronto_month_bounds()
        Event = self.env["calendar.event"].sudo()
        booked = Event.search_count(
            [
                ("hiba_booked_by", "=", self.env.uid),
                ("start", ">=", start),
                ("start", "<", end),
            ]
        )
        present = Event.search_count(
            [
                ("hiba_booked_by", "=", self.env.uid),
                ("hiba_presence", "=", "present"),
                ("start", ">=", start),
                ("start", "<", end),
            ]
        )
        for lead in self:
            lead.hiba_kpi_booked_month = booked
            lead.hiba_kpi_present_month = present

    def action_hiba_book_martin(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": "Prendre RDV Martin",
            "res_model": "hiba.book.martin.wizard",
            "view_mode": "form",
            "target": "new",
            "context": {"default_lead_id": self.id},
        }

    def action_hiba_mark_present(self):
        for lead in self:
            lead.hiba_rdv_state = "present"
            if lead.hiba_rdv_event_id:
                lead.hiba_rdv_event_id.sudo().write({"hiba_presence": "present"})
            stage = self.env.ref(
                "doorway_hiba_qualif.stage_coins_quebec_present",
                raise_if_not_found=False,
            )
            if stage and lead.team_id == self.env.ref(
                "doorway_hiba_qualif.crm_team_coins_quebec", raise_if_not_found=False
            ):
                lead.stage_id = stage
        return True

    def action_hiba_mark_noshow(self):
        for lead in self:
            lead.hiba_rdv_state = "noshow"
            if lead.hiba_rdv_event_id:
                lead.hiba_rdv_event_id.sudo().write({"hiba_presence": "noshow"})
            stage = self.env.ref(
                "doorway_hiba_qualif.stage_coins_quebec_noshow",
                raise_if_not_found=False,
            )
            if stage and lead.team_id == self.env.ref(
                "doorway_hiba_qualif.crm_team_coins_quebec", raise_if_not_found=False
            ):
                lead.stage_id = stage
        return True
