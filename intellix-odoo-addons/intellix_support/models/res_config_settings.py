# -*- coding: utf-8 -*-
import secrets

from odoo import _, api, fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = "res.config.settings"

    intellix_support_api_token = fields.Char(
        string="Token API support",
        config_parameter="intellix_support.api_token",
        help="En-tête X-Doorway-Token (ou X-Doorway-Key) pour POST /doorway/api/support/*",
    )
    intellix_support_copilot_ai_ready = fields.Boolean(
        string="Copilot Claude disponible",
        compute="_compute_intellix_support_copilot_ai_ready",
    )
    intellix_support_copilot_ai_hint = fields.Char(
        string="Configuration IA Copilot",
        compute="_compute_intellix_support_copilot_ai_ready",
    )
    intellix_support_cursor_api_key = fields.Char(
        string="Clé API Cursor",
        config_parameter="intellix_support.cursor_api_key",
        help="Optionnel si CURSOR_API_KEY est défini sur le serveur. Utilisé par le bridge Cursor (Phase B).",
    )
    intellix_support_anydesk_enabled = fields.Boolean(
        string="AnyDesk activé",
        config_parameter="intellix_support.anydesk_enabled",
        default=False,
        help="Phase 3 — active les actions session distante dans le Copilot.",
    )
    intellix_support_anydesk_rest_token = fields.Char(
        string="Token REST my.anydesk",
        config_parameter="intellix_support.anydesk_rest_token",
        help="Phase 3 — API my.anydesk (sessions, clients). Pas de REST public pour connexion directe.",
    )
    intellix_support_alert_enabled = fields.Boolean(
        string="Alertes support actives",
        config_parameter="intellix_support.alert_enabled",
        default=False,
        help="Webhook ou mail aux responsables support sur tickets urgents / SLA / diagnostic plateforme.",
    )
    intellix_support_alert_webhook_url = fields.Char(
        string="URL webhook alertes",
        config_parameter="intellix_support.alert_webhook_url",
        help="POST JSON (Slack/n8n). Si vide, envoi mail au groupe responsables support.",
    )
    intellix_support_cursor_bridge_enabled = fields.Boolean(
        string="Bridge Cursor actif",
        config_parameter="intellix_support.cursor_bridge_enabled",
        default=False,
        help="POC — analyse Cursor sur ticket / proposition approuvée (mode plan, sans deploy).",
    )
    intellix_support_cursor_repo_url = fields.Char(
        string="Repo GitHub Cursor (optionnel)",
        config_parameter="intellix_support.cursor_repo_url",
        help="URL repo pour agents cloud Cursor (ex. https://github.com/org/doorway).",
    )
    intellix_support_karine_partner_id = fields.Many2one(
        "res.partner",
        string="Contact alerte produit (Karine)",
        config_parameter="intellix_support.karine_partner_id",
        help="Destinataire des alertes feature / enhancement / question (défaut : Karine Barmaki).",
    )
    intellix_support_karine_alert_email = fields.Char(
        string="Email alerte produit (fallback)",
        config_parameter="intellix_support.karine_alert_email",
        help="Email alternatif si le contact Karine n'est pas trouvé automatiquement.",
    )

    @api.depends_context("company")
    def _compute_intellix_support_copilot_ai_ready(self):
        icp = self.env["ir.config_parameter"].sudo()
        ai_enabled = str(icp.get_param("renovation_conciergerie.ai_enabled", "0")) in (
            "1",
            "True",
            "true",
        )
        api_key = (icp.get_param("renovation_conciergerie.anthropic_api_key") or "").strip()
        model = icp.get_param("renovation_conciergerie.ai_model", "") or "claude-sonnet-4-6"
        for record in self:
            ready = ai_enabled and bool(api_key)
            record.intellix_support_copilot_ai_ready = ready
            if ready:
                record.intellix_support_copilot_ai_hint = _(
                    "Claude actif via Rénovation Conciergerie (modèle %(model)s). "
                    "Sinon le Copilot utilise les règles locales.",
                    model=model,
                )
            elif not ai_enabled:
                record.intellix_support_copilot_ai_hint = _(
                    "Activez l'IA dans Paramètres → Rénovation Conciergerie → Intelligence Artificielle."
                )
            else:
                record.intellix_support_copilot_ai_hint = _(
                    "Renseignez anthropic_api_key dans Rénovation Conciergerie "
                    "(ir.config_parameter renovation_conciergerie.anthropic_api_key)."
                )

    def action_intellix_support_generate_api_token(self):
        self.ensure_one()
        token = secrets.token_urlsafe(32)
        self.env["ir.config_parameter"].sudo().set_param("intellix_support.api_token", token)
        self.intellix_support_api_token = token
        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": _("Token API support"),
                "message": _(
                    "Nouveau token généré. Copiez-le dans n8n (en-tête X-Doorway-Token)."
                ),
                "type": "success",
                "sticky": True,
            },
        }
