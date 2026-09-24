import json

from odoo import _, api, fields, models
from odoo.exceptions import UserError

class ResConfigSettings(models.TransientModel):
    _inherit = "res.config.settings"

    @api.model
    def get_values(self):
        res = super().get_values()
        # JSON Meta / Énergie : édition via renovation.meta.leads.map.editor (pas dans le form).
        return res

    def set_values(self):
        super().set_values()

    ai_enabled = fields.Boolean(
        string="Activer l'IA",
        config_parameter="renovation_conciergerie.ai_enabled",
    )
    ai_provider = fields.Selection(
        selection=[("anthropic", "Anthropic (Claude)")],
        string="Fournisseur IA",
        default="anthropic",
        config_parameter="renovation_conciergerie.ai_provider",
    )
    anthropic_api_key = fields.Char(
        string="Anthropic API Key",
        config_parameter="renovation_conciergerie.anthropic_api_key",
    )
    ai_model = fields.Char(
        string="Modèle IA",
        default="claude-3-5-sonnet-latest",
        config_parameter="renovation_conciergerie.ai_model",
    )
    ai_max_tokens = fields.Integer(
        string="Tokens maximum par réponse",
        default=1024,
        config_parameter="renovation_conciergerie.ai_max_tokens",
    )
    project_ai_webhook_token = fields.Char(
        string="Token webhook tâches IA",
        config_parameter="renovation_conciergerie.project_ai_webhook_token",
        readonly=True,
    )
    project_ai_webhook_url = fields.Char(
        string="URL webhook tâches IA",
        compute="_compute_project_ai_webhook_url",
        readonly=True,
    )

    def _compute_project_ai_webhook_url(self):
        base = (
            self.env["ir.config_parameter"].sudo().get_param("web.base.url") or ""
        ).rstrip("/")
        for record in self:
            record.project_ai_webhook_url = (
                f"{base}/project/ai/webhook" if base else "/project/ai/webhook"
            )

    def action_open_meta_leads_map_editor(self):
        return {
            "type": "ir.actions.act_window",
            "name": _("Mapping Meta Lead Ads"),
            "res_model": "renovation.meta.leads.map.editor",
            "view_mode": "form",
            "target": "new",
        }

    def action_reset_meta_leads_global_map(self):
        self.env["renovation.meta.leads.routing"].sudo()._ensure_meta_leads_global_map()
        from odoo.addons.renovation_conciergerie.models.meta_leads_routing import (
            DEFAULT_META_LEADS_GLOBAL_MAP,
        )

        self.env["ir.config_parameter"].sudo().set_param(
            "renovation_conciergerie.meta_leads_global_page_map",
            json.dumps(DEFAULT_META_LEADS_GLOBAL_MAP, ensure_ascii=False, indent=2),
        )
        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": _("Mapping Meta"),
                "message": _("Mapping global réinitialisé depuis les valeurs Doorway."),
                "type": "success",
                "sticky": False,
            },
        }

    def action_test_meta_immo_facebook_page(self):
        result = (
            self.env["renovation.meta.immo.webhook"]
            .sudo()
            .validate_meta_immo_facebook_page()
        )
        if not result.get("ok"):
            raise UserError(result.get("message") or _("Échec validation page Meta."))
        msg = _("Page « %(name)s » (ID %(pid)s) accessible.") % {
            "name": result.get("page_name"),
            "pid": result.get("page_id"),
        }
        if result.get("instagram_username"):
            msg += _("\nInstagram : @%(user)s") % {
                "user": result["instagram_username"],
            }
        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": _("Page Meta immo OK"),
                "message": msg,
                "type": "success",
                "sticky": False,
            },
        }

    def action_regenerate_meta_immo_webhook_token(self):
        token = self.env["renovation.meta.immo.webhook"].sudo().regenerate_meta_immo_webhook_token()
        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": _("Token Meta immo régénéré"),
                "message": _("Copiez le nouveau token depuis ce formulaire (champ ci-dessus)."),
                "type": "success",
                "sticky": True,
            },
        }

    def action_generate_project_ai_token(self):
        self.ensure_one()
        import secrets

        token = secrets.token_urlsafe(32)
        self.env["ir.config_parameter"].sudo().set_param(
            "renovation_conciergerie.project_ai_webhook_token", token
        )
        self.project_ai_webhook_token = token
        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": _("Token généré"),
                "message": _("Nouveau token de webhook tâches IA généré."),
                "type": "success",
                "sticky": False,
            },
        }

    def action_test_ai_connection(self):
        self.ensure_one()
        icp = self.env["ir.config_parameter"].sudo()
        icp.set_param("renovation_conciergerie.ai_provider", self.ai_provider or "anthropic")
        icp.set_param("renovation_conciergerie.anthropic_api_key", self.anthropic_api_key or "")
        icp.set_param("renovation_conciergerie.ai_model", self.ai_model or "")
        icp.set_param("renovation_conciergerie.ai_enabled", "1" if self.ai_enabled else "0")
        icp.set_param(
            "renovation_conciergerie.ai_max_tokens", str(self.ai_max_tokens or 1024)
        )
        try:
            answer = self.env["renovation.ai.service"]._call(
                [{"role": "user", "content": "Réponds uniquement par le mot: OK"}],
                system="Tu es un service de test de connexion.",
                max_tokens=10,
                purpose="Test de connexion IA",
            )
            message = _("Connexion IA réussie. Réponse du modèle : %s") % (
                (answer or "").strip()[:120]
            )
            kind = "success"
        except Exception as error:  # noqa: BLE001
            message = _("Échec de la connexion IA : %s") % str(error)
            kind = "danger"
        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": _("Test de connexion IA"),
                "message": message,
                "type": kind,
                "sticky": kind == "danger",
            },
        }

    twilio_account_sid = fields.Char(
        string="Twilio Account SID",
        config_parameter="renovation_conciergerie.twilio_account_sid",
    )
    twilio_auth_token = fields.Char(
        string="Twilio Auth Token",
        config_parameter="renovation_conciergerie.twilio_auth_token",
    )
    twilio_from_number = fields.Char(
        string="Twilio Numero emetteur",
        config_parameter="renovation_conciergerie.twilio_from_number",
    )
    twilio_base_url = fields.Char(
        string="URL publique Odoo",
        help="Ex: https://votre-domaine.com",
        config_parameter="renovation_conciergerie.twilio_base_url",
    )
    retell_api_key = fields.Char(
        string="Retell API Key",
        config_parameter="renovation_conciergerie.retell_api_key",
    )
    retell_from_number = fields.Char(
        string="Retell Numero emetteur",
        config_parameter="renovation_conciergerie.retell_from_number",
    )
    retell_agent_id = fields.Char(
        string="Retell Agent ID",
        config_parameter="renovation_conciergerie.retell_agent_id",
    )
    retell_base_url = fields.Char(
        string="Retell API Base URL",
        config_parameter="renovation_conciergerie.retell_base_url",
        default="https://api.retellai.com",
    )
    retell_webhook_base_url = fields.Char(
        string="Retell URL publique webhook",
        help="Ex: https://votre-domaine.com",
        config_parameter="renovation_conciergerie.retell_webhook_base_url",
    )
    retell_webhook_token = fields.Char(
        string="Token webhook Retell (secours)",
        config_parameter="renovation_conciergerie.retell_webhook_token",
        readonly=True,
    )
    retell_webhook_url = fields.Char(
        string="URL webhook Retell (Rénovation → Retell)",
        compute="_compute_retell_webhook_url",
        readonly=True,
    )
    marketing_retell_webhook_token = fields.Char(
        string="Token webhook Retell Marketing (secours)",
        config_parameter="renovation_conciergerie.marketing_retell_webhook_token",
        readonly=True,
    )
    marketing_retell_webhook_url = fields.Char(
        string="URL webhook Retell (Marketing → Retell)",
        compute="_compute_marketing_retell_webhook_url",
        readonly=True,
    )
    immobilier_agent_webhook_token = fields.Char(
        string="Token webhook Agent IA (Immobilier)",
        config_parameter="renovation_conciergerie.immobilier_agent_webhook_token",
        readonly=True,
    )
    immobilier_agent_webhook_url = fields.Char(
        string="Webhook CRM Agent IA (Immobilier / Maison Recherchée)",
        compute="_compute_immobilier_agent_webhook_url",
        readonly=True,
    )
    agents_ia_call_webhook_url = fields.Char(
        string="Webhook fin d'appel (n8n / ElevenLabs)",
        compute="_compute_agents_ia_call_webhook_url",
        readonly=True,
    )
    agents_ia_call_webhook_token = fields.Char(
        string="Token webhook fin d'appel (X-Doorway-Key)",
        compute="_compute_agents_ia_call_webhook_token",
        readonly=True,
    )
    meta_immo_webhook_token = fields.Char(
        string="Token webhook Meta Ads immobilier",
        config_parameter="renovation_conciergerie.meta_immo_webhook_token",
        readonly=True,
    )
    meta_immo_lead_webhook_url = fields.Char(
        string="Webhook création lead Meta (n8n node 3)",
        compute="_compute_meta_immo_webhook_urls",
        readonly=True,
    )
    meta_immo_lead_update_url = fields.Char(
        string="Webhook mise à jour lead (n8n node 11)",
        compute="_compute_meta_immo_webhook_urls",
        readonly=True,
    )
    meta_immo_facebook_page_id = fields.Char(
        string="Page Facebook — Maison Recherchée (Lead Ads)",
        config_parameter="renovation_conciergerie.meta_immo_facebook_page_id",
    )
    meta_immo_facebook_page_name = fields.Char(
        string="Nom page Facebook immo (réf.)",
        config_parameter="renovation_conciergerie.meta_immo_facebook_page_name",
    )
    meta_immo_reference_ad_id = fields.Char(
        string="ID publicité Meta de référence",
        config_parameter="renovation_conciergerie.meta_immo_reference_ad_id",
    )
    meta_leads_hub_webhook_url = fields.Char(
        string="Hub n8n — toutes pages Meta",
        config_parameter="renovation_conciergerie.meta_leads_hub_webhook_url",
        readonly=True,
    )
    meta_leads_routing_token = fields.Char(
        string="Token hub /api/meta/leads/resolve",
        config_parameter="renovation_conciergerie.meta_leads_routing_token",
        readonly=True,
    )
    meta_leadgen_webhook_verify_token = fields.Char(
        string="Token vérification Meta Leadgen (hub.verify_token)",
        config_parameter="renovation_conciergerie.meta_leadgen_webhook_verify_token",
        readonly=True,
    )
    meta_leadgen_webhook_url = fields.Char(
        string="URL webhook Meta Leadgen (Odoo direct)",
        compute="_compute_meta_leadgen_webhook_url",
        readonly=True,
    )
    marketing_meta_lead_webhook_url = fields.Char(
        string="URL webhook Meta Marketing (payload JSON)",
        compute="_compute_marketing_meta_lead_webhook_url",
        readonly=True,
    )
    marketing_meta_webhook_token = fields.Char(
        string="Token webhook Meta Marketing",
        config_parameter="renovation_conciergerie.marketing_meta_webhook_token",
        readonly=True,
    )

    energie_webhook_token = fields.Char(
        string="Token webhook Énergie Pro",
        config_parameter="renovation_conciergerie.energie_webhook_token",
        readonly=True,
    )
    energie_lead_webhook_url = fields.Char(
        string="Webhook création lead Énergie",
        compute="_compute_energie_webhook_urls",
        readonly=True,
    )
    energie_lead_update_url = fields.Char(
        string="Webhook mise à jour lead Énergie",
        compute="_compute_energie_webhook_urls",
        readonly=True,
    )
    energie_facebook_page_ids = fields.Char(
        string="Pages Facebook Énergie Pro (IDs)",
        config_parameter="renovation_conciergerie.energie_facebook_page_ids",
        help="Séparées par virgule. Lead Ads Meta → agent Alex.",
    )
    haidly_webhook_token = fields.Char(
        string="Token webhook Haidly",
        config_parameter="renovation_conciergerie.haidly_webhook_token",
        readonly=True,
    )
    haidly_lead_webhook_url = fields.Char(
        string="Webhook création lead Haidly",
        compute="_compute_haidly_webhook_urls",
        readonly=True,
    )
    haidly_lead_update_url = fields.Char(
        string="Webhook mise à jour lead Haidly",
        compute="_compute_haidly_webhook_urls",
        readonly=True,
    )

    def action_regenerate_meta_leadgen_verify_token(self):
        token = (
            self.env["renovation.meta.leadgen.webhook"].sudo().regenerate_verify_token()
        )
        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": _("Token Meta Leadgen régénéré"),
                "message": token,
                "type": "success",
                "sticky": True,
            },
        }

    def action_regenerate_haidly_webhook_token(self):
        token = (
            self.env["renovation.haidly.webhook"].sudo().regenerate_haidly_webhook_token()
        )
        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": _("Token Haidly régénéré"),
                "message": token,
                "type": "success",
                "sticky": True,
            },
        }

    def action_test_energie_facebook_pages(self):
        result = (
            self.env["renovation.energie.webhook"].sudo().validate_energie_facebook_pages()
        )
        if not result.get("ok"):
            raise UserError(result.get("message") or _("Échec validation pages Meta."))
        lines = [
            _("Page « %(name)s » (%(pid)s)")
            % {"name": p.get("name"), "pid": p.get("id")}
            for p in result.get("pages") or []
        ]
        msg = "\n".join(lines) or _("Aucune page validée.")
        for err in result.get("errors") or []:
            msg += "\n⚠ " + err
        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": _("Pages Meta Énergie Pro"),
                "message": msg,
                "type": "success" if not result.get("errors") else "warning",
                "sticky": True,
            },
        }

    def action_regenerate_energie_webhook_token(self):
        token = (
            self.env["renovation.energie.webhook"].sudo().regenerate_energie_webhook_token()
        )
        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": _("Token Énergie Pro régénéré"),
                "message": token,
                "type": "success",
                "sticky": True,
            },
        }
    website_lead_webhook_token = fields.Char(
        string="Token webhook leads site web",
        config_parameter="renovation_conciergerie.website_lead_webhook_token",
        readonly=True,
    )
    website_lead_webhook_url = fields.Char(
        string="URL webhook leads site web (Rénovation)",
        compute="_compute_website_lead_webhook_url",
        readonly=True,
    )
    marketing_website_lead_webhook_token = fields.Char(
        string="Token webhook site web (Marketing)",
        config_parameter="renovation_conciergerie.marketing_website_lead_webhook_token",
        readonly=True,
    )
    marketing_website_lead_webhook_url = fields.Char(
        string="URL webhook leads site web (Marketing)",
        compute="_compute_marketing_website_lead_webhook_url",
        readonly=True,
    )

    def _compute_website_lead_webhook_url(self):
        base = (
            self.env["ir.config_parameter"].sudo().get_param("web.base.url") or ""
        ).rstrip("/")
        for record in self:
            record.website_lead_webhook_url = (
                f"{base}/renovation/lead/website" if base else "/renovation/lead/website"
            )

    def _compute_marketing_website_lead_webhook_url(self):
        base = (
            self.env["ir.config_parameter"].sudo().get_param("web.base.url") or ""
        ).rstrip("/")
        for record in self:
            record.marketing_website_lead_webhook_url = (
                f"{base}/marketing/lead/website"
                if base
                else "/marketing/lead/website"
            )

    def _compute_retell_webhook_url(self):
        base = (
            self.env["ir.config_parameter"].sudo().get_param("web.base.url") or ""
        ).rstrip("/")
        for record in self:
            record.retell_webhook_url = (
                f"{base}/renovation/agents/webhook/crm"
                if base
                else "/renovation/agents/webhook/crm"
            )

    def _compute_marketing_retell_webhook_url(self):
        base = (
            self.env["ir.config_parameter"].sudo().get_param("web.base.url") or ""
        ).rstrip("/")
        for record in self:
            record.marketing_retell_webhook_url = (
                f"{base}/marketing/agents/webhook/crm"
                if base
                else "/marketing/agents/webhook/crm"
            )

    def _compute_immobilier_agent_webhook_url(self):
        base = (
            self.env["ir.config_parameter"].sudo().get_param("web.base.url") or ""
        ).rstrip("/")
        for record in self:
            record.immobilier_agent_webhook_url = (
                f"{base}/immobilier/agents/webhook/crm"
                if base
                else "/immobilier/agents/webhook/crm"
            )

    def _compute_agents_ia_call_webhook_url(self):
        base = (
            self.env["ir.config_parameter"].sudo().get_param("web.base.url") or ""
        ).rstrip("/")
        for record in self:
            record.agents_ia_call_webhook_url = (
                f"{base}/api/agents/webhook/n8n" if base else "/api/agents/webhook/n8n"
            )

    def _compute_meta_immo_webhook_urls(self):
        base = (
            self.env["ir.config_parameter"].sudo().get_param("web.base.url") or ""
        ).rstrip("/")
        for record in self:
            record.meta_immo_lead_webhook_url = (
                f"{base}/api/immo/meta-lead" if base else "/api/immo/meta-lead"
            )
            record.meta_immo_lead_update_url = (
                f"{base}/api/immo/lead/update" if base else "/api/immo/lead/update"
            )

    def _compute_energie_webhook_urls(self):
        base = (
            self.env["ir.config_parameter"].sudo().get_param("web.base.url") or ""
        ).rstrip("/")
        for record in self:
            record.energie_lead_webhook_url = (
                f"{base}/api/energie/lead" if base else "/api/energie/lead"
            )
            record.energie_lead_update_url = (
                f"{base}/api/energie/lead/update"
                if base
                else "/api/energie/lead/update"
            )

    def _compute_haidly_webhook_urls(self):
        base = (
            self.env["ir.config_parameter"].sudo().get_param("web.base.url") or ""
        ).rstrip("/")
        for record in self:
            record.haidly_lead_webhook_url = (
                f"{base}/api/haidly/lead" if base else "/api/haidly/lead"
            )
            record.haidly_lead_update_url = (
                f"{base}/api/haidly/lead/update"
                if base
                else "/api/haidly/lead/update"
            )

    def _compute_agents_ia_call_webhook_token(self):
        from odoo.addons.doorway_agents_dashboard.services.config_loader import get_secret

        token = get_secret(
            self.env,
            "DOORWAY_AGENTS_WEBHOOK_KEY",
            "doorway_agents_dashboard.webhook_token",
        )
        for record in self:
            record.agents_ia_call_webhook_token = token or ""
