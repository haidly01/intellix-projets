# -*- coding: utf-8 -*-
from odoo import fields, models


class DoorwayPlacement(models.Model):
    _name = "doorway.placement"
    _description = "Placement publicitaire Traffic Manager"
    _order = "priority desc, create_date desc"

    campaign_id = fields.Many2one(
        "doorway.traffic.campaign", required=True, ondelete="cascade"
    )
    foundation_id = fields.Many2one(
        related="campaign_id.foundation_id", store=True, readonly=True
    )
    name = fields.Char(required=True, string="Placement")
    placement_group = fields.Selection(
        [
            ("facebook_feed", "Facebook — Fil"),
            ("instagram_feed", "Instagram — Fil"),
            ("instagram_reels", "Instagram — Reels"),
            ("instagram_stories", "Instagram — Stories"),
            ("facebook_stories", "Facebook — Stories"),
            ("facebook_reels", "Facebook — Reels"),
            ("audience_network", "Audience Network"),
            ("messenger", "Messenger"),
            ("marketplace", "Marketplace"),
            ("explore", "Explore / Découvrir"),
            ("search", "Résultats de recherche"),
        ],
    )
    platform = fields.Selection(
        [
            ("meta", "Meta Ads"),
            ("google", "Google Ads"),
            ("tiktok", "TikTok Ads"),
        ],
        default="meta",
    )
    priority = fields.Selection(
        [
            ("high", "Prioritaire"),
            ("medium", "Standard"),
            ("low", "Test"),
            ("exclude", "À exclure"),
        ],
        default="medium",
    )
    placement_rationale = fields.Text("Justification IA")
    source = fields.Selection(
        [
            ("manual", "Manuel"),
            ("ai_generated", "Généré par IA"),
        ],
        default="ai_generated",
    )
    ai_status = fields.Selection(
        [
            ("proposed", "Proposé par IA"),
            ("approved", "Approuvé"),
            ("rejected", "Ignoré"),
            ("active", "Actif"),
        ],
        default="proposed",
    )

    def action_approve(self):
        self.write({"ai_status": "approved"})
        return True

    def action_reject(self):
        self.write({"ai_status": "rejected"})
        return True

    def action_activate(self):
        self.write({"ai_status": "active"})
        return True
