# -*- coding: utf-8 -*-
from datetime import datetime

from odoo import api, fields, models


class ResPartner(models.Model):
    _inherit = "res.partner"

    monthly_lead_capacity = fields.Integer(
        string="Capacité mensuelle (leads)",
        default=15,
    )
    leads_used_this_month = fields.Integer(
        string="Leads utilisés ce mois",
        compute="_compute_leads_used_this_month",
    )
    partner_pause_mode = fields.Boolean(
        string="Mode Pause",
        help="Aucun lead attribué lorsque activé.",
    )
    partner_score = fields.Integer(
        string="Score partenaire",
        default=80,
        help="Score de performance affiché au partenaire (0-100).",
    )
    active_bloc_id = fields.Many2one(
        "intellix.partner.lead.bloc",
        string="Bloc actif",
        compute="_compute_active_bloc",
        store=True,
    )
    mandate_ids = fields.One2many(
        "intellix.partner.lead.mandate",
        "partner_id",
        string="Mandats leads",
    )
    bloc_ids = fields.One2many(
        "intellix.partner.lead.bloc",
        "partner_id",
        string="Blocs de leads",
    )
    portal_accepted_count = fields.Integer(
        compute="_compute_portal_stats",
    )
    portal_converted_count = fields.Integer(
        compute="_compute_portal_stats",
    )

    @api.depends("mandate_ids.status", "mandate_ids.delivered_date")
    def _compute_leads_used_this_month(self):
        now = fields.Datetime.now()
        month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        for partner in self:
            partner.leads_used_this_month = len(
                partner.mandate_ids.filtered(
                    lambda m: m.delivered_date
                    and m.delivered_date >= month_start
                    and m.status not in ("refused",)
                )
            )

    @api.depends("bloc_ids.state", "bloc_ids.create_date")
    def _compute_active_bloc(self):
        for partner in self:
            active = partner.bloc_ids.filtered(lambda b: b.state == "active")
            partner.active_bloc_id = active[:1]

    @api.depends("mandate_ids.status")
    def _compute_portal_stats(self):
        for partner in self:
            mandates = partner.mandate_ids
            partner.portal_accepted_count = len(
                mandates.filtered(lambda m: m.status in ("accepted", "converted", "replacement_pending"))
            )
            partner.portal_converted_count = len(
                mandates.filtered(lambda m: m.status == "converted")
            )

    def _ipp_portal_partner(self):
        """Partenaire commercial pour le portail (société si contact)."""
        self.ensure_one()
        return self.commercial_partner_id or self
