# -*- coding: utf-8 -*-
from odoo import _, fields, models
from odoo.exceptions import UserError

from odoo.addons.doorway_veille_sociale.services.reddit_service import RedditService


class RedditOAuthCodeWizard(models.TransientModel):
    _name = "doorway.reddit.oauth.code.wizard"
    _description = "Échange manuel du code OAuth Reddit"

    code = fields.Char(
        string="Code d'autorisation Reddit",
        required=True,
        help="Copiez le paramètre « code » depuis l'URL après autorisation sur Reddit.",
    )
    redirect_uri = fields.Char(
        string="Redirect URI utilisée",
        readonly=True,
    )

    def action_exchange_code(self):
        self.ensure_one()
        cfg = self.env["doorway.veille.config"].get_config()
        svc = RedditService(self.env)
        code = (self.code or "").strip().split("#")[0].strip()
        if not code:
            raise UserError(_("Collez le code OAuth Reddit."))
        session = self.env["doorway.reddit.oauth.state"].sudo().search(
            [("config_id", "=", cfg.id), ("consumed", "=", False)],
            order="id desc",
            limit=1,
        )
        result = svc.exchange_authorization_code(cfg, code, session=session or None)
        if not result.get("ok"):
            raise UserError(result.get("message") or _("Échec OAuth Reddit."))
        if session:
            session.sudo().write(
                {
                    "consumed": True,
                    "result": "ok",
                    "result_message": (result.get("message") or "")[:500],
                }
            )
        test = svc.validate_config(cfg)
        cfg.sudo().write(
            {
                "reddit_last_check": fields.Datetime.now(),
                "reddit_status_message": "\n".join(test.get("messages") or []),
                "reddit_actif": test.get("ok", False),
            }
        )
        sync_msg = cfg._run_reddit_n8n_sync()
        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": _("Reddit connecté"),
                "message": "%s\n%s"
                % (result.get("message"), sync_msg),
                "type": "success",
                "sticky": False,
            },
        }
