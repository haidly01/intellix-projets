# -*- coding: utf-8 -*-
from odoo import api, fields, models


class PeCcCampaign(models.Model):
    _name = "pe.cc.campaign"
    _description = "Campagne Call Center"
    _order = "date_start desc, id desc"

    name = fields.Char(required=True)
    type = fields.Selection(
        [
            ("outbound", "Sortant"),
            ("inbound", "Entrant"),
            ("whatsapp", "WhatsApp"),
            ("email", "Email"),
            ("sms", "SMS"),
        ],
        default="outbound",
        required=True,
    )
    department_id = fields.Many2one("pe.department", string="Département")
    date_start = fields.Date()
    date_end = fields.Date()
    objectif_appels = fields.Integer(string="Objectif appels")
    objectif_conv_pct = fields.Float(string="Taux conversion cible (%)")
    lead_ids = fields.Many2many("crm.lead", string="Leads")
    statut = fields.Selection(
        [
            ("draft", "Brouillon"),
            ("active", "Actif"),
            ("paused", "Pausé"),
            ("done", "Terminé"),
        ],
        default="draft",
    )
    vicidial_campaign_id = fields.Char(string="ID campagne VICIdial")
    call_log_ids = fields.One2many("pe.call.log", "campaign_id")
    call_count = fields.Integer(compute="_compute_stats")
    conv_rate = fields.Float(string="Taux conversion (%)", compute="_compute_stats")
    demo_count = fields.Integer(compute="_compute_stats")
    sale_count = fields.Integer(compute="_compute_stats")

    @api.depends("call_log_ids", "call_log_ids.outcome")
    def _compute_stats(self):
        for rec in self:
            logs = rec.call_log_ids
            rec.call_count = len(logs)
            rec.demo_count = len(logs.filtered(lambda l: l.outcome == "demo_bookee"))
            rec.sale_count = len(logs.filtered(lambda l: l.outcome == "vendu"))
            if logs:
                converted = len(
                    logs.filtered(
                        lambda l: l.outcome
                        in ("interesse", "demo_bookee", "vendu", "rappel")
                    )
                )
                rec.conv_rate = converted / len(logs) * 100
            else:
                rec.conv_rate = 0.0
