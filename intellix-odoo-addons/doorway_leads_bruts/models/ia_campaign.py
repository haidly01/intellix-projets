# -*- coding: utf-8 -*-
from odoo import _, api, fields, models
import requests


class IaCampaign(models.Model):
    _name = "doorway.ia.campaign"
    _description = "Campagne IA Africa-Con"
    _order = "create_date desc"

    name = fields.Char(string="Nom campagne", required=True)
    state = fields.Selection([
        ("draft", "Brouillon"),
        ("running", "En cours"),
        ("paused", "Pausée"),
        ("done", "Terminée"),
        ("error", "Erreur"),
    ], default="draft", tracking=True)
    agent_ia = fields.Selection([
        ("sofia", "Sofia — France/Espagne"),
        ("lea", "Léa — Québec/Canada"),
    ], string="Agent IA", required=True, default="sofia")
    marche = fields.Selection([
        ("FR", "France"),
        ("ES", "Espagne"),
        ("MA", "Maroc"),
        ("CA", "Canada/Québec"),
    ], string="Marché", required=True)
    lead_ids = fields.Many2many(
        "doorway.leads.bruts",
        "doorway_ia_campaign_lead_rel",
        "campaign_id", "lead_id",
        string="Leads à appeler",
    )
    total_leads = fields.Integer(compute="_compute_stats", store=True)
    leads_appeles = fields.Integer(default=0)
    leads_interesses = fields.Integer(default=0)
    leads_rappel = fields.Integer(default=0)
    leads_refus = fields.Integer(default=0)
    cadence_par_heure = fields.Integer(string="Appels / heure", default=500)
    caller_id = fields.Char(string="CallerID", default="15817058118")
    n8n_webhook_url = fields.Char(
        string="Webhook n8n",
        default="https://n8n.intellixcrm.com/webhook/ia-campaign-start",
    )
    n8n_batch_id = fields.Char(string="Batch ID n8n", readonly=True)
    error_message = fields.Text(readonly=True)
    notes = fields.Text()

    @api.depends("lead_ids")
    def _compute_stats(self):
        for rec in self:
            rec.total_leads = len(rec.lead_ids)

    def action_launch(self):
        self.ensure_one()
        if not self.lead_ids:
            from odoo.exceptions import UserError
            raise UserError(_("Aucun lead sélectionné."))
        leads_data = []
        for lead in self.lead_ids:
            if lead.phone:
                leads_data.append({
                    "id": lead.id,
                    "name": lead.name or "",
                    "phone": lead.phone,
                    "email": lead.email or "",
                    "company": lead.company_name or "",
                    "city": lead.city or "",
                    "country": self.marche,
                })
        payload = {
            "campaign_id": self.id,
            "campaign_name": self.name,
            "agent": self.agent_ia,
            "marche": self.marche,
            "caller_id": self.caller_id,
            "cadence_par_heure": self.cadence_par_heure,
            "leads": leads_data,
            "odoo_callback_url": "%s/api/ia-campaign/callback" % (
                self.env["ir.config_parameter"].sudo().get_param("web.base.url")
            ),
        }
        try:
            resp = requests.post(self.n8n_webhook_url, json=payload, timeout=30)
            resp.raise_for_status()
            data = resp.json()
            self.write({
                "state": "running",
                "n8n_batch_id": data.get("batch_id", ""),
                "error_message": False,
            })
        except Exception as e:
            self.write({"state": "error", "error_message": str(e)})
            raise

    def action_pause(self):
        self.ensure_one()
        self.state = "paused"

    def action_resume(self):
        self.ensure_one()
        self.state = "running"

    def action_mark_done(self):
        self.ensure_one()
        self.state = "done"
