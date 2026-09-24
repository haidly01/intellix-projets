# -*- coding: utf-8 -*-
from odoo import _, api, fields, models
from odoo.exceptions import UserError


class DoorwaySocialTiktokAppWizard(models.TransientModel):
    _name = "doorway.social.tiktok.app.wizard"
    _description = "Configurer l'app TikTok et connecter un compte"

    pipeline_id = fields.Many2one("crm.team", string="Marque / Pipeline")
    account_id = fields.Many2one("doorway.social.account", string="Compte TikTok")
    client_key = fields.Char(string="Client Key", required=True)
    client_secret = fields.Char(string="Client Secret", required=True)
    redirect_uri = fields.Char(string="Redirect URI", readonly=True)
    expected_handle = fields.Char(string="Page TikTok à connecter", readonly=True)
    has_existing_credentials = fields.Boolean(readonly=True)

    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        svc = self.env["doorway.social.tiktok.service"]
        svc.ensure_brand_tiktok_accounts()
        key, secret = svc.get_app_credentials()
        res["redirect_uri"] = svc.get_redirect_uri()
        res["has_existing_credentials"] = bool(key and secret)
        if key:
            res["client_key"] = key
        if secret:
            res["client_secret"] = secret
        account_id = self.env.context.get("default_account_id")
        if account_id:
            account = self.env["doorway.social.account"].browse(account_id)
            if account.exists():
                res["account_id"] = account.id
                res["pipeline_id"] = account.pipeline_id.id
                handle = (account.tiktok_username or "").strip().lstrip("@")
                if handle:
                    res["expected_handle"] = "https://www.tiktok.com/@%s" % handle
        if not res.get("expected_handle"):
            pipeline = self.env["crm.team"].browse(res.get("pipeline_id") or 0)
            name = (pipeline.name or "") if pipeline.exists() else ""
            if "Québec" in name or "Quebec" in name:
                res["expected_handle"] = ""
            else:
                res["expected_handle"] = "https://www.tiktok.com/@coinsmarrakech"
        return res

    def action_save_credentials(self):
        self.ensure_one()
        if not (self.client_key or "").strip() or not (self.client_secret or "").strip():
            raise UserError(_("Renseignez la Client Key et le Client Secret TikTok."))
        self.env["doorway.social.tiktok.service"].set_app_credentials(
            self.client_key, self.client_secret
        )
        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": _("App TikTok"),
                "message": _("Client key / secret enregistrés."),
                "type": "success",
                "sticky": False,
            },
        }

    def action_save_and_connect(self):
        self.ensure_one()
        if not (self.client_key or "").strip() or not (self.client_secret or "").strip():
            raise UserError(_("Renseignez la Client Key et le Client Secret TikTok."))
        svc = self.env["doorway.social.tiktok.service"]
        svc.set_app_credentials(self.client_key, self.client_secret)
        svc.ensure_brand_tiktok_accounts()
        account = self.account_id
        if account and account.platform != "tiktok":
            account = False
        if not account and self.pipeline_id:
            account = self.env["doorway.social.account"].search(
                [
                    ("platform", "=", "tiktok"),
                    ("pipeline_id", "=", self.pipeline_id.id),
                ],
                limit=1,
            )
        if account and not account.tiktok_username:
            handle = ""
            if account.pipeline_id and "Marocain" in (account.pipeline_id.name or ""):
                handle = "coinsmarrakech"
            if handle:
                account.tiktok_username = handle
        if not account:
            handle = ""
            if self.pipeline_id and "Marocain" in (self.pipeline_id.name or ""):
                handle = "coinsmarrakech"
            account = self.env["doorway.social.account"].create(
                {
                    "name": "%s — TikTok"
                    % (self.pipeline_id.name if self.pipeline_id else "TikTok"),
                    "platform": "tiktok",
                    "connection_state": "disconnected",
                    "pipeline_id": self.pipeline_id.id if self.pipeline_id else False,
                    "tiktok_username": handle or False,
                }
            )
        return {
            "type": "ir.actions.act_url",
            "url": "/doorway/publication/tiktok/oauth/start?account_id=%s" % account.id,
            "target": "self",
        }
