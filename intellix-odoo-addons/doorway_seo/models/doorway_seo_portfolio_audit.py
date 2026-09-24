# -*- coding: utf-8 -*-
from odoo import fields, models


class DoorwaySeoPortfolioAudit(models.Model):
    """Instantané des 4 chantiers d'audit du portfolio Doorway (sites externes,
    pas le site Odoo lui-même) — une ligne par (site, chantier, métrique).
    Alimenté depuis le serveur France par push XML-RPC (portfolio_audit),
    pas de calcul côté Odoo. Rafraîchi une fois par 24h avec le cycle
    d'audit existant (portfolio-audit-daily.timer)."""

    _name = "doorway.seo.portfolio.audit"
    _description = "Portfolio Doorway — audit technique (4 chantiers)"
    _order = "captured_at desc, site_id, chantier"
    _rec_name = "display_name"

    site_id = fields.Char("Site (id)", required=True, index=True)
    domain = fields.Char("Domaine")
    chantier = fields.Selection(
        [
            ("render_health", "Chantier 1 — Rendu & pages blanches"),
            ("content_dilution", "Chantier 2 — Dilution de contenu"),
            ("keyword_positions", "Chantier 3 — Positions mot-clé"),
            ("lead_attribution", "Chantier 4 — Attribution des leads"),
        ],
        required=True,
        index=True,
    )
    metric = fields.Char("Métrique", required=True, index=True)
    value_float = fields.Float("Valeur (nombre)")
    value_text = fields.Char("Valeur (texte)")
    detail = fields.Text("Détail")
    captured_at = fields.Datetime("Capturé le", required=True, index=True)
    display_name = fields.Char("Nom", compute="_compute_display_name", store=True)

    def _compute_display_name(self):
        for rec in self:
            rec.display_name = f"{rec.domain or rec.site_id} — {rec.metric}"
