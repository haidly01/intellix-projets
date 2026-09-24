# -*- coding: utf-8 -*-
from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = "res.config.settings"

    leads_bruts_marge_defaut = fields.Float(
        related="leads_bruts_credit_config_id.marge_defaut_pct",
        readonly=False,
    )
    leads_bruts_mode_commercial = fields.Boolean(
        related="leads_bruts_credit_config_id.mode_commercial",
        readonly=False,
    )
    leads_bruts_devise = fields.Selection(
        related="leads_bruts_credit_config_id.devise",
        readonly=False,
    )
    leads_bruts_prix_vente = fields.Float(
        related="leads_bruts_credit_config_id.prix_credit_vente",
        readonly=False,
    )
    leads_bruts_prix_revient = fields.Float(
        related="leads_bruts_credit_config_id.prix_credit_revient",
        readonly=False,
        groups="doorway_leads_bruts.group_admin_commercial",
    )
    leads_bruts_stripe_public = fields.Char(
        related="leads_bruts_credit_config_id.stripe_public_key",
        readonly=False,
    )
    leads_bruts_stripe_secret = fields.Char(
        related="leads_bruts_credit_config_id.stripe_secret_key",
        readonly=False,
        groups="doorway_leads_bruts.group_admin_commercial",
    )
    leads_bruts_credit_config_id = fields.Many2one(
        "doorway.credit.config",
        default=lambda self: self.env["doorway.credit.config"].get_config(),
    )

    # --- Configurateur de Campagnes (INTLX-EXT) ---
    leads_bruts_claude_api_key = fields.Char(
        string="Clé API Claude (Anthropic)",
        config_parameter="doorway_leads_bruts.claude_api_key",
        help="Clé x-api-key Anthropic pour la recommandation IA du configurateur. "
        "Si vide, les clés Anthropic d'autres modules Intellix sont réutilisées.",
    )
    leads_bruts_n8n_url = fields.Char(
        string="URL n8n",
        config_parameter="doorway_leads_bruts.n8n_url",
        default="http://127.0.0.1:5678",
    )
    leads_bruts_n8n_api_key = fields.Char(
        string="Clé API n8n (X-N8N-API-KEY)",
        config_parameter="doorway_leads_bruts.n8n_api_key",
        help="n8n → Settings → API → Create an API key. Requise pour déployer les workflows.",
    )
    leads_bruts_odoo_base_url = fields.Char(
        string="URL Odoo (callback n8n → Odoo)",
        config_parameter="doorway_leads_bruts.odoo_base_url",
        help="Base URL utilisée par le workflow n8n pour créer les crm.lead. "
        "Si vide, web.base.url est utilisé.",
    )
    leads_bruts_crm_tag_id = fields.Many2one(
        "crm.tag",
        string="Étiquette CRM par défaut",
        config_parameter="doorway_leads_bruts.crm_tag_id",
    )
    leads_bruts_crm_team_id = fields.Many2one(
        "crm.team",
        string="Équipe commerciale par défaut",
        config_parameter="doorway_leads_bruts.crm_team_id",
    )
