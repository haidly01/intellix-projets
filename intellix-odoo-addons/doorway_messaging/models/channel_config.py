# -*- coding: utf-8 -*-
import logging
import secrets
from datetime import timedelta

from odoo import _, api, fields, models
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)

CANAL_SELECTION = [
    ("email", "Email (SMTP Brevo)"),
    ("sms", "SMS (Twilio)"),
    ("whatsapp", "WhatsApp (Twilio)"),
    ("linkedin", "LinkedIn"),
    ("gmb", "Google My Business"),
]


class DoorwayChannelConfig(models.Model):
    _name = "doorway.channel.config"
    _description = "Configuration canal de messagerie"
    _order = "canal, name"

    name = fields.Char("Nom", required=True)
    canal = fields.Selection(CANAL_SELECTION, required=True)
    actif = fields.Boolean(default=True)

    api_key = fields.Char("API Key / Client ID")
    api_secret = fields.Char("API Secret / Client Secret")
    access_token = fields.Char("Access Token OAuth")
    refresh_token = fields.Char("Refresh Token OAuth")
    token_expiry = fields.Datetime("Expiration token")

    linkedin_profile_type = fields.Selection(
        [
            ("personal", "Profil personnel"),
            ("organization", "Page entreprise"),
        ],
        string="Type de profil LinkedIn",
        default="organization",
        help="Créez un canal par profil : personnel, entreprise A, entreprise B, etc.",
    )
    linkedin_org_id = fields.Char("Organization URN (urn:li:organization:XXXXX)")
    linkedin_person_id = fields.Char("Person URN (urn:li:person:XXXXX)")

    gmb_account_id = fields.Char("Account ID GMB")
    gmb_location_id = fields.Char("Location ID GMB")
    gmb_location_name = fields.Char("Nom établissement")

    twilio_from_sms = fields.Char("Numéro SMS sortant")
    twilio_from_wa = fields.Char("Numéro WhatsApp sortant (whatsapp:+1...)")

    oauth_state = fields.Char(copy=False)
    last_test_message = fields.Text(readonly=True)
    last_test_ok = fields.Boolean(readonly=True)

    @api.model
    def _icp(self):
        return self.env["ir.config_parameter"].sudo()

    def _base_url(self):
        return self._icp().get_param("web.base.url", "").rstrip("/")

    def _linkedin_redirect_uri(self):
        return "%s/doorway/messaging/oauth/linkedin/callback" % self._base_url()

    def _google_redirect_uri(self):
        return "%s/doorway/messaging/oauth/google/callback" % self._base_url()

    def action_tester_connexion(self):
        self.ensure_one()
        ok, msg = False, ""
        if self.canal == "linkedin":
            from odoo.addons.doorway_messaging.services.linkedin_service import (
                LinkedInService,
            )

            svc = LinkedInService(
                self.access_token or "",
                org_id=(self.linkedin_org_id or "").replace("urn:li:organization:", ""),
                person_id=(self.linkedin_person_id or "").replace("urn:li:person:", ""),
            )
            info = svc.get_organization_info() if self.linkedin_org_id else svc.get_me()
            ok = bool(info)
            msg = "Connexion LinkedIn OK" if ok else (info or {}).get("error", "Échec")
        elif self.canal == "gmb":
            from odoo.addons.doorway_messaging.services.gmb_service import GMBService

            svc = GMBService(
                self.access_token or "",
                self.gmb_account_id or "",
                self.gmb_location_id or "",
            )
            info = svc.get_location_info()
            ok = bool(info)
            msg = "Connexion GMB OK" if ok else (info or {}).get("error", "Échec")
        elif self.canal in ("sms", "whatsapp"):
            from odoo.addons.doorway_messaging.services.sms_service import SmsService

            ok = SmsService(self.env).is_available()
            msg = "Twilio configuré" if ok else "Twilio SID/token manquant"
        elif self.canal == "email":
            ok = bool(self.env["ir.mail_server"].sudo().search([], limit=1))
            msg = "Serveur mail Odoo trouvé" if ok else "Aucun serveur SMTP"
        else:
            msg = "Canal non supporté pour le test"
        self.write({"last_test_ok": ok, "last_test_message": msg})
        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": _("Test connexion"),
                "message": msg,
                "type": "success" if ok else "danger",
                "sticky": False,
            },
        }

    def action_oauth_linkedin(self):
        self.ensure_one()
        if self.canal != "linkedin":
            raise UserError(_("Ce canal n'est pas LinkedIn."))
        client_id = self.api_key or self._icp().get_param(
            "doorway_messaging.linkedin_client_id", ""
        )
        if not client_id:
            raise UserError(_("Renseignez le Client ID LinkedIn."))
        state = secrets.token_urlsafe(24)
        self.sudo().write({"oauth_state": state})
        scopes = "w_member_social,w_organization_social,r_organization_social,r_liteprofile"
        url = (
            "https://www.linkedin.com/oauth/v2/authorization"
            "?response_type=code"
            "&client_id=%s"
            "&redirect_uri=%s"
            "&state=%s"
            "&scope=%s"
        ) % (client_id, self._linkedin_redirect_uri(), state, scopes)
        return {"type": "ir.actions.act_url", "url": url, "target": "new"}

    def action_oauth_gmb(self):
        self.ensure_one()
        if self.canal != "gmb":
            raise UserError(_("Ce canal n'est pas Google My Business."))
        client_id = self.api_key or self._icp().get_param(
            "doorway_messaging.google_client_id", ""
        )
        if not client_id:
            raise UserError(_("Renseignez le Client ID Google."))
        state = secrets.token_urlsafe(24)
        self.sudo().write({"oauth_state": state})
        scope = "https://www.googleapis.com/auth/business.manage"
        url = (
            "https://accounts.google.com/o/oauth2/auth"
            "?response_type=code"
            "&client_id=%s"
            "&redirect_uri=%s"
            "&state=%s"
            "&scope=%s"
            "&access_type=offline"
            "&prompt=consent"
        ) % (client_id, self._google_redirect_uri(), state, scope)
        return {"type": "ir.actions.act_url", "url": url, "target": "new"}

    def _refresh_token_if_needed(self):
        self.ensure_one()
        if not self.token_expiry or fields.Datetime.now() < self.token_expiry:
            return True
        if self.canal == "linkedin" and self.refresh_token:
            from odoo.addons.doorway_messaging.services.linkedin_service import (
                LinkedInService,
            )

            data = LinkedInService("", "").refresh_access_token(
                self.api_key or self._icp().get_param(
                    "doorway_messaging.linkedin_client_id", ""
                ),
                self.api_secret or self._icp().get_param(
                    "doorway_messaging.linkedin_client_secret", ""
                ),
                self.refresh_token,
            )
            if data:
                self.sudo().write(
                    {
                        "access_token": data["access_token"],
                        "refresh_token": data.get("refresh_token", self.refresh_token),
                        "token_expiry": fields.Datetime.now()
                        + timedelta(seconds=int(data.get("expires_in", 3600))),
                    }
                )
                return True
        return bool(self.access_token)
