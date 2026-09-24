# -*- coding: utf-8 -*-
from odoo import fields, models


class DoorwaySeoKeywordPosition(models.Model):
    """Positions mot-clé individuelles (Chantier 3) — une ligne par
    (site, requête), liste complète (pas un échantillon), remplacée chaque
    jour. Alimentée depuis le serveur France (export GSC complet, même
    source que keyword_positions.py)."""

    _name = "doorway.seo.keyword.position"
    _description = "Portfolio Doorway — positions mot-clé (liste complète)"
    _order = "position asc"
    _rec_name = "query"

    site_id = fields.Char("Site (id)", required=True, index=True)
    domain = fields.Char("Domaine", required=True, index=True)
    query = fields.Char("Requête", required=True)
    position = fields.Float("Position", index=True)
    clicks = fields.Float("Clics")
    impressions = fields.Float("Impressions")
    ctr = fields.Float("CTR")
    bucket = fields.Selection(
        [("1-3", "1-3"), ("4-10", "4-10"), ("11-20", "11-20"), ("21-50", "21-50"), ("50+", "50+")],
        string="Tranche",
        index=True,
    )
    captured_at = fields.Datetime("Capturé le", required=True, index=True)
