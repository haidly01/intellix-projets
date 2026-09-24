# -*- coding: utf-8 -*-
from odoo import api, fields, models


class IntellixPartnerLeadBloc(models.Model):
    _name = "intellix.partner.lead.bloc"
    _description = "Bloc de leads partenaire"
    _order = "create_date desc"

    name = fields.Char(string="Référence", required=True)
    partner_id = fields.Many2one(
        "res.partner",
        string="Partenaire",
        required=True,
        ondelete="cascade",
        index=True,
    )
    size = fields.Integer(string="Taille du bloc", default=10, required=True)
    delivered_count = fields.Integer(
        string="Leads livrés",
        compute="_compute_delivered_count",
        store=True,
    )
    state = fields.Selection(
        [
            ("active", "Actif"),
            ("done", "Terminé"),
        ],
        default="active",
        required=True,
    )
    mandate_ids = fields.One2many(
        "intellix.partner.lead.mandate",
        "bloc_id",
        string="Mandats",
    )
    remaining_count = fields.Integer(
        string="Restants",
        compute="_compute_delivered_count",
    )
    progress_percent = fields.Float(
        string="Progression %",
        compute="_compute_delivered_count",
    )

    @api.depends("mandate_ids", "size")
    def _compute_delivered_count(self):
        for bloc in self:
            delivered = len(bloc.mandate_ids)
            bloc.delivered_count = delivered
            bloc.remaining_count = max(bloc.size - delivered, 0)
            bloc.progress_percent = (
                (delivered / bloc.size * 100.0) if bloc.size else 0.0
            )
