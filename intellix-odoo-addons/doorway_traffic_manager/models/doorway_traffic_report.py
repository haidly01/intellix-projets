# -*- coding: utf-8 -*-
import logging
from datetime import timedelta

from odoo import api, fields, models

_logger = logging.getLogger(__name__)


class DoorwayTrafficReport(models.Model):
    _name = "doorway.traffic.report"
    _description = "Rapport Traffic Manager"
    _order = "date_to desc"

    name = fields.Char(compute="_compute_name", store=True)
    foundation_id = fields.Many2one(
        "doorway.brand.foundation", required=True, ondelete="cascade"
    )
    pipeline_id = fields.Many2one(
        related="foundation_id.pipeline_id", store=True, readonly=True
    )
    period = fields.Selection(
        [("weekly", "Hebdomadaire"), ("monthly", "Mensuel")],
        default="weekly",
    )
    date_from = fields.Date(required=True)
    date_to = fields.Date(required=True)

    summary = fields.Text()
    wins = fields.Text("Victoires")
    concerns = fields.Text("Points d'attention")
    next_actions = fields.Text("Actions recommandées")
    kpi_vs_objectives = fields.Text("KPIs vs objectifs")

    @api.depends("foundation_id.brand_name", "date_from", "date_to")
    def _compute_name(self):
        for rec in self:
            brand = rec.foundation_id.brand_name or "Marque"
            rec.name = "%s — %s → %s" % (
                brand,
                rec.date_from or "",
                rec.date_to or "",
            )

    @api.model
    def cron_weekly_report(self):
        foundations = self.env["doorway.brand.foundation"].search([
            ("state", "=", "validated"),
        ])
        today = fields.Date.today()
        date_from = today - timedelta(days=7)
        for foundation in foundations:
            campaigns = self.env["doorway.traffic.campaign"].search([
                ("foundation_id", "=", foundation.id),
                ("ai_status", "in", ["active", "paused"]),
            ])
            if not campaigns:
                continue
            try:
                self._generate_for_foundation(
                    foundation, campaigns, date_from, today
                )
            except Exception as exc:  # noqa: BLE001
                _logger.warning(
                    "Rapport hebdo %s: %s", foundation.brand_name, exc
                )
        return True

    def _aggregate_performance(self, campaigns):
        total_spend = sum(campaigns.mapped("spend"))
        total_conv = sum(campaigns.mapped("conversions"))
        avg_cpa = total_spend / total_conv if total_conv else 0
        avg_roas = (
            sum(campaigns.mapped("roas")) / len(campaigns) if campaigns else 0
        )
        return {
            "depense_totale": total_spend,
            "conversions": total_conv,
            "cpa_moyen": round(avg_cpa, 2),
            "roas_moyen": round(avg_roas, 2),
            "campagnes_actives": len(
                campaigns.filtered(lambda c: c.ai_status == "active")
            ),
            "recommandations_en_attente": len(
                campaigns.filtered(lambda c: c.ai_action_pending != "none")
            ),
            "wins": "—",
            "concerns": "—",
            "kpi_status": "—",
        }

    def _generate_for_foundation(self, foundation, campaigns, date_from, date_to):
        perf = self._aggregate_performance(campaigns)
        report_data = self.env["doorway.traffic.claude.service"].weekly_report(
            foundation, perf
        )
        self.create({
            "foundation_id": foundation.id,
            "period": "weekly",
            "date_from": date_from,
            "date_to": date_to,
            "summary": report_data.get("summary"),
            "wins": report_data.get("wins"),
            "concerns": report_data.get("concerns"),
            "next_actions": report_data.get("next_actions"),
            "kpi_vs_objectives": report_data.get("kpi_status"),
        })
        foundation.pipeline_id.message_post(
            body=(
                "📊 Rapport Traffic Manager — Semaine du %s\n\n%s"
                % (date_to, report_data.get("summary", ""))
            ),
            subject="Rapport Traffic Manager hebdomadaire",
        )
