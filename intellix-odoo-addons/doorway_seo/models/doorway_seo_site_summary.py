# -*- coding: utf-8 -*-
from odoo import fields, models


class DoorwaySeoSiteSummary(models.Model):
    """Résumé quotidien par site — trafic GSC, GEO (citations IA), citations/
    annuaires, santé technique. Alimenté depuis le serveur France par push
    XML-RPC (portfolio_audit/scripts/push_dashboard_data.py), même calculs
    que le rapport courriel existant (geo_status.py, citations_weekly.py,
    gsc.py) — remplacé chaque jour (pas d'historique ici, voir
    doorway.seo.portfolio.audit pour l'historique brut par métrique)."""

    _name = "doorway.seo.site.summary"
    _description = "Portfolio Doorway — résumé quotidien par site"
    _order = "domain"
    _rec_name = "domain"

    site_id = fields.Char("Site (id)", required=True, index=True)
    domain = fields.Char("Domaine", required=True)
    label = fields.Char("Nom")
    captured_at = fields.Datetime("Capturé le", required=True, index=True)

    # Trafic GSC (90j par défaut, voir period_days)
    period_days = fields.Integer("Fenêtre (jours)", default=90)
    traffic_ok = fields.Boolean("Trafic disponible")
    clicks = fields.Float("Clics")
    impressions = fields.Float("Impressions")
    ctr = fields.Float("CTR")
    position = fields.Float("Position moyenne")
    clicks_delta_pct = fields.Float("Δ clics %")
    impressions_delta_pct = fields.Float("Δ impressions %")
    ctr_delta_pct = fields.Float("Δ CTR %")
    position_delta_pct = fields.Float("Δ position %")
    period_comparable = fields.Boolean("Période précédente comparable", default=True, help="Faux si la période précédente n'a aucune donnée — les Δ% ne doivent pas être affichés comme +100 %% dans ce cas.")
    top_queries_json = fields.Text("Top requêtes (JSON)")

    # GEO — visibilité IA (citations ChatGPT/Perplexity/Gemini)
    geo_mentioned = fields.Integer("Mentions confirmées")
    geo_total = fields.Integer("Requêtes validées (total)")
    geo_score_label = fields.Char("Score GEO (libellé)")
    faqpage = fields.Char("FAQPage")
    last_blog_label = fields.Char("Dernier blog")
    testimonials_label = fields.Char("Avis")
    nap_phone = fields.Char("Tél. NAP")
    yaml_label = fields.Char("YAML L3")

    # Citations / annuaires
    citations_human_done = fields.Integer("Vérif. humaine faites")
    citations_human_objective = fields.Integer("Vérif. humaine objectif")
    citations_self_done = fields.Integer("Libre-service faites")
    citations_self_objective = fields.Integer("Libre-service objectif")
    citations_status_label = fields.Char("Statut citations")

    # Santé technique
    pages_audited = fields.Integer("Pages auditées")
    issues_count = fields.Integer("Problèmes actifs")
    status_label = fields.Char("Statut")
    status_class = fields.Selection(
        [("ok", "En bonne santé"), ("warn", "Corrections mineures"), ("alert", "Attention requise"), ("neutral", "Données insuffisantes")],
        string="Statut (classe)",
    )
    health_lines_json = fields.Text("Détail santé (JSON)")
    next_action = fields.Text("Prochaine action recommandée")
