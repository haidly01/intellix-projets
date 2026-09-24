# -*- coding: utf-8 -*-
from odoo import _, api, fields, models


class IaCampaignWizard(models.TransientModel):
    _name = "doorway.ia.campaign.wizard"
    _description = "Wizard lancement campagne IA"

    name = fields.Char(
        string="Nom campagne",
        required=True,
        default=lambda self: "Campagne IA %s" % fields.Date.today(),
    )
    agent_ia = fields.Selection([
        ("sofia", "Sofia — France/Espagne"),
        ("lea", "Léa — Québec/Canada"),
    ], string="Agent IA", required=True, default="sofia")
    marche = fields.Selection([
        ("FR", "France"),
        ("ES", "Espagne"),
        ("MA", "Maroc"),
        ("CA", "Canada/Québec"),
    ], string="Marché", required=True, default="FR")
    cadence_par_heure = fields.Integer(string="Appels / heure", default=500)
    caller_id = fields.Char(string="CallerID", default="15817058118")
    lead_ids = fields.Many2many("doorway.leads.bruts", string="Leads sélectionnés")
    total_leads = fields.Integer(compute="_compute_total")
    total_avec_telephone = fields.Integer(compute="_compute_total")

    @api.depends("lead_ids")
    def _compute_total(self):
        for rec in self:
            rec.total_leads = len(rec.lead_ids)
            rec.total_avec_telephone = len(rec.lead_ids.filtered(lambda l: l.phone))

    def action_launch(self):
        self.ensure_one()
        campaign = self.env["doorway.ia.campaign"].create({
            "name": self.name,
            "agent_ia": self.agent_ia,
            "marche": self.marche,
            "cadence_par_heure": self.cadence_par_heure,
            "caller_id": self.caller_id,
            "lead_ids": [(6, 0, self.lead_ids.ids)],
        })
        campaign.action_launch()
        return {
            "type": "ir.actions.act_window",
            "name": _("Campagne IA lancée"),
            "res_model": "doorway.ia.campaign",
            "res_id": campaign.id,
            "view_mode": "form",
            "target": "current",
        }
