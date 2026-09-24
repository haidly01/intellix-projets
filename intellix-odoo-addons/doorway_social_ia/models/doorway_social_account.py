# -*- coding: utf-8 -*-
from odoo import api, fields, models


class DoorwaySocialAccount(models.Model):
    _name = "doorway.social.account"
    _description = "Compte réseau social"
    _order = "id desc"

    name = fields.Char(required=True)
    platform = fields.Selection(
        [
            ("tiktok", "TikTok"),
            ("facebook", "Facebook"),
            ("instagram", "Instagram"),
            ("linkedin", "LinkedIn"),
            ("pinterest", "Pinterest"),
            ("youtube", "YouTube"),
            ("whatsapp", "WhatsApp"),
            ("messenger", "Messenger"),
            ("telegram", "Telegram"),
            ("gmb", "Google My Business"),
        ],
        required=True,
    )
    channel_config_ids = fields.One2many(
        "doorway.channel.config",
        "social_account_id",
        string="Canaux OAuth",
    )
    linkedin_profile_ids = fields.One2many(
        "doorway.social.linkedin.profile",
        "account_id",
        string="Profils LinkedIn",
    )
    gmb_location_ids = fields.One2many(
        "doorway.social.gmb.location",
        "account_id",
        string="Établissements GMB",
    )
    pipeline_id = fields.Many2one("crm.team", string="Marque / Pipeline")
    active = fields.Boolean(default=True)

    connection_state = fields.Selection(
        [
            ("connected", "Connecté"),
            ("expired", "Expiré"),
            ("disconnected", "Non connecté"),
        ],
        default="disconnected",
        string="Statut",
    )
    external_account_id = fields.Char("ID externe")
    page_count = fields.Integer(compute="_compute_page_count")
    whatsapp_display_number = fields.Char(
        string="Numéro affiché",
        compute="_compute_whatsapp_setup",
    )
    whatsapp_webhook_url = fields.Char(
        string="URL webhook entrant",
        compute="_compute_whatsapp_setup",
    )
    whatsapp_verify_token = fields.Char(
        string="Token vérification Meta",
        compute="_compute_whatsapp_setup",
    )

    access_token = fields.Char(groups="base.group_system")
    refresh_token = fields.Char(groups="base.group_system")
    token_expiry = fields.Datetime(groups="base.group_system")

    tiktok_username = fields.Char(
        string="Compte TikTok",
        help="Identifiant @ sans le @. Exemple : coinsmarrakech",
    )
    tiktok_open_id = fields.Char(groups="base.group_system")
    tiktok_access_token = fields.Char(groups="base.group_system")
    tiktok_refresh_token = fields.Char(groups="base.group_system")

    heygen_avatar_id = fields.Char("Avatar HeyGen")
    heygen_voice_id = fields.Char("Voix HeyGen")
    heygen_language = fields.Selection(
        [
            ("fr", "Français (Canada)"),
            ("fr-FR", "Français (France)"),
            ("es", "Espagnol"),
            ("en", "Anglais"),
        ],
        default="fr",
    )

    pinterest_board_ids = fields.One2many(
        "doorway.pinterest.board", "account_id", string="Tableaux Pinterest"
    )
    facebook_group_ids = fields.One2many(
        "doorway.social.group",
        "account_id",
        string="Groupes Facebook",
        domain=[("platform", "=", "facebook")],
    )
    linkedin_group_ids = fields.One2many(
        "doorway.social.group",
        "account_id",
        string="Groupes LinkedIn",
        domain=[("platform", "=", "linkedin")],
    )
    post_ids = fields.Many2many(
        "doorway.social.post",
        "doorway_social_post_account_rel",
        "account_id",
        "post_id",
        string="Posts",
    )

    @api.depends("platform")
    def _compute_whatsapp_setup(self):
        icp = self.env["ir.config_parameter"].sudo()
        base_url = (icp.get_param("web.base.url") or "").rstrip("/")
        verify = icp.get_param("doorway_social_ia.whatsapp_webhook_verify_token") or "doorway_wa_2026"
        display = icp.get_param("intellix.whatsapp_display") or ""
        for rec in self:
            if rec.platform != "whatsapp":
                rec.whatsapp_display_number = False
                rec.whatsapp_webhook_url = False
                rec.whatsapp_verify_token = False
                continue
            rec.whatsapp_display_number = display
            rec.whatsapp_webhook_url = "%s/doorway/social/webhook/whatsapp" % base_url
            rec.whatsapp_verify_token = verify

    def _compute_page_count(self):
        for rec in self:
            if rec.platform == "linkedin":
                rec.page_count = len(rec.linkedin_profile_ids.filtered("active"))
            elif rec.platform == "gmb":
                rec.page_count = len(rec.gmb_location_ids.filtered("active"))
            else:
                rec.page_count = 1 if rec.connection_state == "connected" else 0

    @api.model
    def _sync_inbox_access_for_team(self):
        """Karine + Zakaria : accès inbox Messages / WhatsApp."""
        group_user = self.env.ref(
            "doorway_social_ia.group_social_user",
            raise_if_not_found=False,
        )
        group_manager = self.env.ref(
            "doorway_social_ia.group_social_manager",
            raise_if_not_found=False,
        )
        if not group_user:
            return False
        users = self.env["res.users"].sudo().search(
            [
                ("login", "in", ("karine@agencedoorway.com", "zakaria@agencedoorway.com")),
                ("active", "=", True),
                ("share", "=", False),
            ]
        )
        for user in users:
            groups = [(4, group_user.id)]
            if group_manager:
                groups.append((4, group_manager.id))
            user.write({"group_ids": groups})
        return True

    @api.model
    def _apply_whatsapp_haidly_config(self):
        """Numéro actif : Haidly +1 555-652-9942 (Phone ID Meta)."""
        icp = self.env["ir.config_parameter"].sudo()
        icp.set_param(
            "doorway_social_ia.whatsapp_phone_number_id", "1167890213071649"
        )
        icp.set_param(
            "doorway_social_ia.whatsapp_business_account_id", "1423717526185944"
        )
        icp.set_param("intellix.whatsapp_sender_e164", "15556529942")
        icp.set_param("intellix.whatsapp_display", "+1 555-652-9942")
        icp.set_param("intellix.whatsapp_brand", "Haidly")
        return self._ensure_whatsapp_from_config()

    @api.model
    def _ensure_whatsapp_from_config(self):
        """Crée ou met à jour le compte WhatsApp inbox depuis les paramètres système."""
        icp = self.env["ir.config_parameter"].sudo()
        phone_id = (icp.get_param("doorway_social_ia.whatsapp_phone_number_id") or "").strip()
        if not phone_id:
            return False
        display = icp.get_param("intellix.whatsapp_display") or "+1 555-652-9942"
        brand = icp.get_param("intellix.whatsapp_brand") or "Haidly"
        account = self.sudo().search([("platform", "=", "whatsapp")], limit=1)
        if not account:
            account = self.sudo().search(
                [("platform", "=", "whatsapp"), ("external_account_id", "=", phone_id)],
                limit=1,
            )
        team = self.env.ref(
            "renovation_conciergerie.crm_team_marketing",
            raise_if_not_found=False,
        )
        vals = {
            "name": "%s — WhatsApp (%s)" % (brand, display),
            "platform": "whatsapp",
            "connection_state": "connected",
            "external_account_id": phone_id,
            "active": True,
        }
        if team:
            vals["pipeline_id"] = team.id
        if account:
            account.write(vals)
        else:
            account = self.sudo().create(vals)
        self.env["doorway.social.inbox"].sudo().search(
            [
                ("inbox_source", "=", "whatsapp"),
                ("account_id", "=", False),
            ]
        ).write({"account_id": account.id})
        return account.id

    def action_connect(self):
        """Ouvre l'URL OAuth selon la plateforme (webhook/controller)."""
        self.ensure_one()
        if self.platform == "tiktok":
            svc = self.env["doorway.social.tiktok.service"]
            key, secret = svc.get_app_credentials()
            if not key or not secret:
                return {
                    "type": "ir.actions.act_window",
                    "name": "Configurer l'app TikTok",
                    "res_model": "doorway.social.tiktok.app.wizard",
                    "view_mode": "form",
                    "target": "new",
                    "context": {"default_account_id": self.id},
                }
            return {
                "type": "ir.actions.act_url",
                "url": "/doorway/publication/tiktok/oauth/start?account_id=%s" % self.id,
                "target": "new",
            }
        if self.platform in ("facebook", "instagram", "whatsapp", "messenger"):
            return {
                "type": "ir.actions.act_window",
                "res_model": "doorway.social.connect.wizard",
                "view_mode": "form",
                "target": "new",
                "context": {"default_pipeline_id": self.pipeline_id.id},
            }
        if self.platform in ("linkedin", "gmb"):
            canal = self.platform
            return {
                "type": "ir.actions.act_window",
                "name": "Configurer OAuth",
                "res_model": "doorway.channel.config",
                "view_mode": "list,form",
                "domain": [("canal", "=", canal)],
                "context": {
                    "default_canal": canal,
                    "default_name": self.name,
                    "default_social_account_id": self.id,
                },
            }
        return {
            "type": "ir.actions.act_url",
            "url": f"/doorway/social/oauth/{self.platform}?account_id={self.id}",
            "target": "new",
        }

    def action_sync_from_channels(self):
        """Resynchronise profils / établissements depuis les canaux Messaging."""
        Channel = self.env["doorway.channel.config"].sudo()
        for rec in self:
            if rec.platform == "linkedin":
                channels = Channel.search(
                    [("canal", "=", "linkedin"), ("social_account_id", "=", rec.id)]
                )
            elif rec.platform == "gmb":
                channels = Channel.search(
                    [("canal", "=", "gmb"), ("social_account_id", "=", rec.id)]
                )
            else:
                continue
            for ch in channels:
                ch.action_sync_social_account()
        return True

    def action_validate_connection(self):
        Meta = self.env["doorway.social.meta.service"]
        TikTok = self.env["doorway.social.tiktok.service"]
        for rec in self.filtered(lambda a: a.platform in ("facebook", "instagram")):
            Meta.validate_account(rec)
        for rec in self.filtered(lambda a: a.platform == "tiktok"):
            token = TikTok.refresh_account_token(rec)
            if token:
                rec.connection_state = "connected"
            else:
                rec.connection_state = "expired"
        return True
