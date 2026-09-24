# -*- coding: utf-8 -*-
from odoo import api, fields, models

EXHAUSTION_RATIO = 0.20


class RenovationPartnerPackageRenoImmo(models.Model):
    _inherit = "renovation.partner.package"

    health_status = fields.Selection(
        [
            ("actif_sain", "Actif — sain"),
            ("a_renouveler", "À renouveler bientôt"),
            ("epuise", "Épuisé"),
        ],
        string="Santé forfait",
        compute="_compute_reno_package_health",
        store=True,
    )
    leads_remaining_pct = fields.Float(
        string="Leads restants (%)",
        compute="_compute_reno_package_health",
        store=True,
    )
    exhaustion_threshold = fields.Float(
        string="Seuil d'épuisement",
        default=EXHAUSTION_RATIO,
        readonly=True,
    )

    @api.depends("leads_total", "leads_used", "leads_remaining", "state")
    def _compute_reno_package_health(self):
        for rec in self:
            total = rec.leads_total or 0
            remaining = rec.leads_remaining if rec.leads_remaining is not False else 0
            rec.leads_remaining_pct = (remaining / total * 100.0) if total else 0.0
            if rec.state in ("expired", "cancelled") or (total and remaining <= 0):
                rec.health_status = "epuise"
            elif rec.state == "active" and total and (remaining / total) <= EXHAUSTION_RATIO:
                rec.health_status = "a_renouveler"
            elif rec.state == "active":
                rec.health_status = "actif_sain"
            else:
                rec.health_status = "a_renouveler" if total and remaining <= 0 else "actif_sain"
