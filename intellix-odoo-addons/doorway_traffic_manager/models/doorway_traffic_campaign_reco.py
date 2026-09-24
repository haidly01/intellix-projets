# -*- coding: utf-8 -*-
from datetime import timedelta

from odoo import _, api, fields, models


class DoorwayTrafficCampaignReco(models.Model):
    _name = "doorway.traffic.campaign.reco"
    _description = "Recommandation IA Traffic Manager"
    _order = "urgency_order desc, confidence desc, create_date desc"

    campaign_id = fields.Many2one(
        "doorway.traffic.campaign", required=True, ondelete="cascade", index=True
    )
    title = fields.Char(required=True)
    body = fields.Text()
    action_type = fields.Selection(
        [
            ("scale_up", "Augmenter le budget"),
            ("scale_down", "Réduire le budget"),
            ("pause", "Mettre en pause"),
            ("new_audience", "Nouvelle audience"),
            ("new_creative", "Nouveau créatif"),
            ("new_campaign", "Nouvelle campagne"),
            ("fix_link", "Corriger lien Meta"),
            ("info", "Information"),
        ],
        required=True,
    )
    urgency = fields.Selection(
        [
            ("urgent", "Urgent"),
            ("opportunity", "Opportunité"),
            ("info", "Information"),
        ],
        default="info",
        required=True,
    )
    urgency_order = fields.Integer(compute="_compute_urgency_order", store=True)
    confidence = fields.Integer("Confiance IA (%)", default=80)
    state = fields.Selection(
        [
            ("pending", "En attente"),
            ("applied", "Appliqué"),
            ("modified", "Modifié"),
            ("ignored", "Ignoré"),
        ],
        default="pending",
        index=True,
    )
    applied_date = fields.Datetime(readonly=True)
    applied_by = fields.Many2one("res.users", readonly=True)

    # Champs liés pour l'inbox
    campaign_name = fields.Char(related="campaign_id.name", store=True)
    campaign_zone = fields.Selection(related="campaign_id.zone", store=True)
    campaign_cpa = fields.Float(related="campaign_id.cpa", store=True)
    campaign_target_cpa = fields.Float(
        related="campaign_id.effective_target_cpa", store=True
    )
    campaign_currency = fields.Char(
        related="campaign_id.target_cpa_currency", store=True
    )
    channel_name = fields.Char(related="campaign_id.channel_id.name", store=True)

    @staticmethod
    def _urgency_rank(urgency):
        return {"urgent": 3, "opportunity": 2, "info": 1}.get(urgency, 0)

    def _compute_urgency_order(self):
        for rec in self:
            rec.urgency_order = self._urgency_rank(rec.urgency)

    def action_apply(self):
        for reco in self:
            campaign = reco.campaign_id
            handlers = {
                "scale_up": campaign._reco_apply_scale_up,
                "scale_down": campaign._reco_apply_scale_down,
                "pause": campaign._reco_apply_pause,
                "new_audience": campaign._reco_apply_new_audience,
                "new_creative": campaign._reco_apply_new_creative,
                "fix_link": campaign._reco_apply_fix_link,
            }
            handler = handlers.get(reco.action_type)
            if handler:
                handler()
            reco.write({
                "state": "applied",
                "applied_date": fields.Datetime.now(),
                "applied_by": self.env.uid,
            })
            self.env["doorway.traffic.log"].sudo().create({
                "campaign_id": campaign.id,
                "action": reco.title,
                "source": "ai_applied",
                "details": reco.body,
            })
            campaign.ai_action_pending = "none"
        return True

    def action_ignore(self):
        for reco in self:
            reco.write({"state": "ignored"})
            if reco.campaign_id.ai_action_pending != "none":
                reco.campaign_id.ai_action_pending = "none"
        return True

    @api.model
    def get_inbox_data(self):
        self.env["doorway.traffic.campaign"].search([])._ensure_reco_from_pending()
        pending = self.search([("state", "=", "pending")], order="urgency_order desc")
        applied_month = self.search_count([
            ("state", "=", "applied"),
            ("applied_date", ">=", fields.Datetime.now() - timedelta(days=30)),
        ])
        urgency_labels = dict(self._fields["urgency"].selection)
        rows = []
        for r in pending:
            rows.append({
                "id": r.id,
                "campaign_id": r.campaign_id.id,
                "campaign_name": r.campaign_name,
                "zone_label": dict(r.campaign_id._fields["zone"].selection).get(
                    r.campaign_zone, ""
                ),
                "channel": r.channel_name or "—",
                "title": r.title,
                "body": r.body or "",
                "action_type": r.action_type,
                "urgency": r.urgency,
                "urgency_label": urgency_labels.get(r.urgency, ""),
                "confidence": r.confidence,
                "cpa": r.campaign_cpa,
                "target_cpa": r.campaign_target_cpa,
                "currency": r.campaign_currency,
            })
        return {"pending_count": len(rows), "applied_month": applied_month, "recos": rows}

    @api.model
    def analyze_all_campaigns(self):
        campaigns = self.env["doorway.traffic.campaign"].search([
            ("ai_status", "in", ("active", "approved")),
        ])
        Rules = self.env["doorway.traffic.optimizer.rules"]
        for c in campaigns:
            Rules.apply_to_campaign(c)
            c._ensure_reco_from_pending()
        return True
