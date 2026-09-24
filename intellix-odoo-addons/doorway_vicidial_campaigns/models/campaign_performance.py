# -*- coding: utf-8 -*-
from odoo import api, fields, models

COST_PER_MINUTE_EUR = 0.22
QUALIFIED_DISPOSITIONS = ("VENTE", "INTERET")


class DoorwayCampaignPerformance(models.Model):
    _inherit = "doorway.campaign"

    appels_effectues = fields.Integer(
        string="Appelés",
        compute="_compute_performance_kpis",
    )
    taux_decroches = fields.Float(
        string="Taux décroché (%)",
        compute="_compute_performance_kpis",
        digits=(5, 1),
    )
    leads_qualifies = fields.Integer(
        string="Leads qualifiés",
        compute="_compute_performance_kpis",
    )
    taux_conversion = fields.Float(
        string="Taux conversion (%)",
        compute="_compute_performance_kpis",
        digits=(5, 1),
    )
    cout_total_eur = fields.Float(
        string="Coût total (€)",
        compute="_compute_performance_kpis",
        digits=(10, 4),
    )
    cout_par_lead = fields.Float(
        string="Coût / lead (€)",
        compute="_compute_performance_kpis",
        digits=(8, 2),
    )

    @api.depends(
        "call_log_ids",
        "call_log_ids.amd_result",
        "call_log_ids.disposition",
        "call_log_ids.duration",
    )
    def _compute_performance_kpis(self):
        CallLog = self.env["doorway.call.log"]
        for rec in self:
            base = [("campaign_id", "=", rec.id)]
            total = CallLog.search_count(base)
            humains = CallLog.search_count(
                base + [("amd_result", "=", "human")]
            )
            leads_ok = CallLog.search_count(
                base + [("disposition", "in", QUALIFIED_DISPOSITIONS)]
            )
            dur_rows = CallLog.read_group(
                base + [("amd_result", "=", "human")],
                ["duration:sum"],
                [],
            )
            dur_sum = int((dur_rows[0].get("duration") or 0) if dur_rows else 0)
            rec.appels_effectues = total
            rec.taux_decroches = (
                (humains / total * 100.0) if total else 0.0
            )
            rec.leads_qualifies = leads_ok
            rec.taux_conversion = (
                (leads_ok / humains * 100.0) if humains else 0.0
            )
            rec.cout_total_eur = dur_sum * COST_PER_MINUTE_EUR / 60.0
            rec.cout_par_lead = (
                rec.cout_total_eur / leads_ok if leads_ok else 0.0
            )
