import json
import logging

import requests

from odoo import _, api, models
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)

ANTHROPIC_URL = "https://api.anthropic.com/v1/messages"
ANTHROPIC_VERSION = "2023-06-01"
DEFAULT_MODEL = "claude-3-5-sonnet-latest"
DEFAULT_MAX_TOKENS = 1024
REQUEST_TIMEOUT = 60


class RenovationAiService(models.AbstractModel):
    """Service d'appel IA centralisé (LLM).

    Toutes les fonctionnalités IA du module passent par ce service afin de
    centraliser la configuration, la gestion d'erreurs et la journalisation
    (transparence / éthique).
    """

    _name = "renovation.ai.service"
    _description = "Service d'appel IA centralisé (LLM)"

    @api.model
    def _config(self):
        icp = self.env["ir.config_parameter"].sudo()
        enabled = icp.get_param("renovation_conciergerie.ai_enabled", "0")
        try:
            max_tokens = int(
                icp.get_param("renovation_conciergerie.ai_max_tokens", DEFAULT_MAX_TOKENS)
                or DEFAULT_MAX_TOKENS
            )
        except (TypeError, ValueError):
            max_tokens = DEFAULT_MAX_TOKENS
        return {
            "provider": icp.get_param(
                "renovation_conciergerie.ai_provider", "anthropic"
            )
            or "anthropic",
            "api_key": icp.get_param("renovation_conciergerie.anthropic_api_key", "")
            or "",
            "model": icp.get_param("renovation_conciergerie.ai_model", DEFAULT_MODEL)
            or DEFAULT_MODEL,
            "enabled": str(enabled) in ("1", "True", "true"),
            "max_tokens": max_tokens,
        }

    @api.model
    def _available(self):
        """True si l'IA est activée ET correctement configurée."""
        config = self._config()
        return bool(config["enabled"] and config["api_key"])

    @api.model
    def _get_prompt(self, code, default=""):
        """Renvoie le prompt système éditable pour ``code``, sinon ``default``."""
        record = self.env["renovation.ai.prompt"].sudo().search(
            [("code", "=", code)], limit=1
        )
        if record and record.system_prompt:
            return record.system_prompt
        return default

    @api.model
    def _call(self, messages, system=None, max_tokens=None, purpose=None):
        """Appelle le LLM et renvoie le texte de la réponse.

        :param messages: liste [{"role": "user"/"assistant", "content": "..."}]
        :param system: prompt système (optionnel)
        :param max_tokens: surcharge le maximum de tokens
        :param purpose: libellé pour le journal IA
        :raises UserError: si l'IA est indisponible ou en cas d'échec d'appel
        """
        config = self._config()
        if not config["enabled"]:
            raise UserError(
                _(
                    "L'IA est désactivée. Activez-la dans "
                    "Paramètres → Rénovation Conciergerie → Intelligence Artificielle."
                )
            )
        if not config["api_key"]:
            raise UserError(
                _("Aucune clé API IA n'est configurée. Renseignez-la dans les paramètres.")
            )
        if config["provider"] != "anthropic":
            raise UserError(
                _("Fournisseur IA non pris en charge pour l'instant : %s")
                % config["provider"]
            )

        payload = {
            "model": config["model"],
            "max_tokens": max_tokens or config["max_tokens"],
            "messages": messages,
        }
        if system:
            payload["system"] = system
        headers = {
            "x-api-key": config["api_key"],
            "anthropic-version": ANTHROPIC_VERSION,
            "content-type": "application/json",
        }

        text = ""
        input_tokens = output_tokens = 0
        status = "error"
        error_message = False
        try:
            response = requests.post(
                ANTHROPIC_URL,
                headers=headers,
                data=json.dumps(payload),
                timeout=REQUEST_TIMEOUT,
            )
            if response.status_code != 200:
                error_message = "HTTP %s: %s" % (
                    response.status_code,
                    response.text[:300],
                )
                raise UserError(_("Erreur de l'API IA : %s") % error_message)
            data = response.json()
            parts = data.get("content") or []
            text = "".join(
                part.get("text", "")
                for part in parts
                if part.get("type") == "text"
            )
            usage = data.get("usage") or {}
            input_tokens = usage.get("input_tokens", 0)
            output_tokens = usage.get("output_tokens", 0)
            status = "success"
        except UserError:
            raise
        except Exception as error:  # noqa: BLE001
            error_message = str(error)
            _logger.warning("Échec d'appel IA : %s", error_message)
            raise UserError(_("Échec d'appel IA : %s") % error_message)
        finally:
            self._log_call(
                purpose, config, messages, text, input_tokens, output_tokens, status, error_message
            )
        return text

    @api.model
    def _log_call(
        self, purpose, config, messages, response, input_tokens, output_tokens, status, error_message
    ):
        try:
            request_summary = json.dumps(messages, ensure_ascii=False)[:4000]
            self.env["renovation.ai.log"].sudo().create(
                {
                    "purpose": purpose or _("Appel IA"),
                    "ai_provider": config.get("provider"),
                    "model_used": config.get("model"),
                    "request_summary": request_summary,
                    "response_summary": (response or "")[:4000],
                    "input_tokens": input_tokens,
                    "output_tokens": output_tokens,
                    "status": status,
                    "error_message": error_message or False,
                }
            )
        except Exception:  # noqa: BLE001
            _logger.exception("Création du journal IA impossible")
