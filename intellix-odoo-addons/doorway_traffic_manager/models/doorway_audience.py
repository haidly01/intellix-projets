# -*- coding: utf-8 -*-
from odoo import fields, models


class DoorwayAudience(models.Model):
    _name = "doorway.audience"
    _description = "Audience Traffic Manager"
    _order = "create_date desc"

    campaign_id = fields.Many2one(
        "doorway.traffic.campaign", required=True, ondelete="cascade"
    )
    foundation_id = fields.Many2one(
        related="campaign_id.foundation_id", store=True, readonly=True
    )
    name = fields.Char(required=True)
    description = fields.Text()
    audience_type = fields.Selection(
        [
            ("cold", "Cold — Prospection"),
            ("warm", "Warm — Engagement"),
            ("hot", "Hot — Conversion"),
            ("lookalike", "Lookalike"),
            ("retargeting", "Remarketing / Retargeting"),
            ("custom", "Custom"),
        ],
    )
    remarketing_source = fields.Selection(
        [
            ("website_visitors", "Visiteurs site web"),
            ("lead_form_openers", "Lead form — ouvreurs"),
            ("lead_form_submitters", "Lead form — soumissions"),
            ("video_viewers", "Visionneurs vidéo (75 %)"),
            ("page_engagers", "Engagés page Facebook"),
            ("ig_engagers", "Engagés Instagram"),
            ("messenger", "Conversations Messenger"),
            ("customer_list", "Liste clients / CRM"),
            ("lookalike_source", "Source lookalike"),
        ],
        string="Source remarketing",
    )
    window_days = fields.Integer(
        string="Fenêtre (jours)",
        default=30,
        help="Nombre de jours pour le remarketing (ex. 7, 30, 90).",
    )
    targeting_rationale = fields.Text("Justification IA")
    targeting = fields.Text("Paramètres de ciblage (JSON)")
    platform = fields.Selection(
        [
            ("meta", "Meta Ads"),
            ("google", "Google Ads"),
            ("tiktok", "TikTok Ads"),
            ("linkedin", "LinkedIn Ads"),
        ],
    )
    estimated_size = fields.Integer("Taille estimée")
    source = fields.Selection(
        [
            ("manual", "Manuel"),
            ("ai_generated", "Généré par IA"),
            ("imported", "Importé"),
        ],
        default="manual",
    )
    ai_status = fields.Selection(
        [
            ("proposed", "Proposé par IA — en attente"),
            ("approved", "Approuvé"),
            ("rejected", "Ignoré"),
            ("active", "Actif"),
        ],
        default="proposed",
    )

    impressions = fields.Integer(readonly=True)
    ctr = fields.Float(readonly=True)
    cpa = fields.Float(readonly=True)
    frequency = fields.Float("Fréquence", readonly=True)

    def action_approve(self):
        self.write({"ai_status": "approved"})
        return True

    def action_reject(self):
        self.write({"ai_status": "rejected"})
        return True

    def action_activate(self):
        self.write({"ai_status": "active"})
        return True
