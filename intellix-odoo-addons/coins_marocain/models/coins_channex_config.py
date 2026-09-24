# -*- coding: utf-8 -*-
from odoo import fields, models
from odoo.exceptions import UserError

from odoo.addons.coins_marocain.services.channex_env import (
    DEFAULT_URL,
    ENV_KEY,
    ENVIRONMENT_PRODUCTION,
    ENVIRONMENT_STAGING,
    PARAM_ENABLED,
    PARAM_ENV,
    PARAM_STAGING_URL,
    PARAM_URL,
    STAGING_URL,
    resolve_api_key,
    resolve_base_url,
    resolve_environment,
    rollback_url,
)
from odoo.addons.coins_marocain.services.channex_service import ChannexService


class CoinsChannexConfig(models.TransientModel):
    _name = "coins.channex.config"
    _description = "Configuration Channex (production, staging en repli)"

    environment = fields.Selection(
        [
            (ENVIRONMENT_PRODUCTION, "Production (app.channex.io)"),
            (ENVIRONMENT_STAGING, "Staging (repli — staging.channex.io)"),
        ],
        string="Environnement",
        required=True,
        default=ENVIRONMENT_PRODUCTION,
    )
    api_key = fields.Char(
        string="Clé API (ne pas coller ici)",
        help="La clé production se pose dans /etc/odoo-doorway.env "
        "comme CHANNEX_API_KEY. Ce champ n'écrit plus ir.config_parameter.",
    )
    api_key_source = fields.Char(string="Source de la clé", readonly=True)
    base_url = fields.Char(string="URL API", default=DEFAULT_URL)
    staging_url = fields.Char(string="URL staging (repli)", default=STAGING_URL)
    enabled = fields.Boolean(
        string="Activer les push OTA",
        help="Laisser décoché jusqu'à ce que la clé et le mapping d'un riad pilote soient prêts.",
    )
    last_ping = fields.Text(string="Dernier test", readonly=True)

    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        ICP = self.env["ir.config_parameter"].sudo()
        environment = resolve_environment(
            icp_environment=ICP.get_param(PARAM_ENV) or "",
            icp_url=ICP.get_param(PARAM_URL) or "",
        )
        key = resolve_api_key(ICP.get_param("coins.channex.api_key") or "")
        from_env = bool((__import__("os").environ.get(ENV_KEY) or "").strip())
        res.update(
            {
                "environment": environment,
                "api_key": "",
                "api_key_source": (
                    "CHANNEX_API_KEY (environnement)"
                    if from_env
                    else ("ICP héritée" if key else "absente — générer dans app.channex.io")
                ),
                "base_url": resolve_base_url(
                    icp_url=ICP.get_param(PARAM_URL) or "",
                    environment=environment,
                    staging_url=ICP.get_param(PARAM_STAGING_URL) or STAGING_URL,
                ),
                "staging_url": ICP.get_param(PARAM_STAGING_URL) or STAGING_URL,
                "enabled": ICP.get_param(PARAM_ENABLED, "False") == "True",
            }
        )
        return res

    def action_save(self):
        self.ensure_one()
        ICP = self.env["ir.config_parameter"].sudo()
        if (self.api_key or "").strip():
            raise UserError(
                "Ne collez pas la clé ici. Ajoutez CHANNEX_API_KEY dans "
                "/etc/odoo-doorway.env (chmod 640, jamais commitée), "
                "puis redémarrez odoo-server."
            )
        environment = self.environment or ENVIRONMENT_PRODUCTION
        staging = (self.staging_url or STAGING_URL).strip().rstrip("/")
        if environment == ENVIRONMENT_STAGING:
            base = rollback_url(staging)
        else:
            base = (self.base_url or DEFAULT_URL).strip().rstrip("/") or DEFAULT_URL
        ICP.set_param(PARAM_ENV, environment)
        ICP.set_param(PARAM_STAGING_URL, staging)
        ICP.set_param(PARAM_URL, base)
        ICP.set_param(PARAM_ENABLED, "True" if self.enabled else "False")
        if self.enabled and resolve_api_key(ICP.get_param("coins.channex.api_key") or ""):
            pending = self.env["coins.channex.push"].search([("state", "=", "pending")])
            pending.write({"state": "ready"})
        return True

    def action_use_staging_rollback(self):
        """Repli explicite — ne supprime pas la config production."""
        self.ensure_one()
        self.environment = ENVIRONMENT_STAGING
        self.base_url = rollback_url(self.staging_url)
        return self.action_save()

    def action_use_production(self):
        self.ensure_one()
        self.environment = ENVIRONMENT_PRODUCTION
        self.base_url = DEFAULT_URL
        return self.action_save()

    def action_ping(self):
        self.ensure_one()
        self.action_save()
        svc = ChannexService(self.env)
        if not svc.ready:
            raise UserError(
                "Clé absente. Générez-la dans app.channex.io → Organisation → "
                "API Keys, stockez-la dans CHANNEX_API_KEY, cochez les push."
            )
        data = svc.ping()
        n = len(data) if isinstance(data, list) else 1
        self.last_ping = "OK %s — %s propriété(s) — %s" % (
            svc.environment,
            n,
            svc.base_url,
        )
        return {
            "type": "ir.actions.act_window",
            "res_model": "coins.channex.config",
            "res_id": self.id,
            "view_mode": "form",
            "target": "new",
        }
