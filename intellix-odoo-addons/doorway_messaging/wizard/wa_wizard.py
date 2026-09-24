# -*- coding: utf-8 -*-
import json
import logging
import re

import requests

from odoo import _, api, fields, models
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


class DoorwayWaWizard(models.TransientModel):
    _name = "doorway.wa.wizard"
    _description = "Envoi WhatsApp unitaire (n8n → Twilio)"

    lead_id = fields.Many2one("crm.lead", string="Lead")
    partner_id = fields.Many2one("res.partner", string="Contact")
    phone = fields.Char("Téléphone", required=True)
    body = fields.Text("Message", required=True)
    use_n8n = fields.Boolean(
        "Passer par n8n (wa-send)",
        default=True,
        help="DEV: http://127.0.0.1:5678/webhook/wa-send",
    )
    fallback_twilio = fields.Boolean(
        "Secours Twilio direct",
        default=False,
        help="Si n8n échoue, utilise WhatsAppService.",
    )

    @api.model
    def _n8n_send_url(self):
        return (
            self.env["ir.config_parameter"]
            .sudo()
            .get_param(
                "doorway_messaging.n8n_wa_send_url",
                "http://127.0.0.1:5678/webhook/wa-send",
            )
            .rstrip("/")
        )

    @staticmethod
    def _normalize_phone(phone):
        digits = re.sub(r"[^\d+]", "", phone or "")
        if not digits:
            return ""
        if digits.startswith("+"):
            return digits
        if digits.startswith("00"):
            return "+" + digits[2:]
        return digits

    def _create_log(self, statut, provider, external_sid="", error="", payload=None, extra=None):
        self.ensure_one()
        vals = {
            "lead_id": self.lead_id.id,
            "partner_id": self.partner_id.id
            or (self.lead_id.partner_id.id if self.lead_id else False),
            "direction": "outbound",
            "phone": self.phone,
            "body": self.body,
            "statut": statut,
            "provider": provider,
            "external_sid": external_sid,
            "error_message": error or False,
        }
        if payload is not None:
            merged = dict(payload)
            if extra:
                merged["response"] = extra
            vals["payload_json"] = json.dumps(merged, ensure_ascii=False)
        return self.env["doorway.wa.log"].sudo().create(vals)

    def action_send(self):
        self.ensure_one()
        phone = self._normalize_phone(self.phone)
        if not phone:
            raise UserError(_("Numéro de téléphone invalide."))
        body = (self.body or "").strip()
        if not body:
            raise UserError(_("Le message est vide."))

        payload = {
            "source": "odoo_doorway_messaging",
            "env": "dev",
            "lead_id": self.lead_id.id or None,
            "partner_id": self.partner_id.id or None,
            "phone": phone,
            "body": body,
            "user_id": self.env.user.id,
        }

        n8n_failed = False
        if self.use_n8n:
            url = self._n8n_send_url()
            try:
                resp = requests.post(url, json=payload, timeout=25)
                data = resp.json() if resp.content else {}
            except Exception as exc:
                _logger.warning("n8n wa-send: %s", exc)
                n8n_failed = True
                data = {"success": False, "error": str(exc)}
                resp = None
            if not n8n_failed:
                if resp.status_code >= 400:
                    n8n_failed = True
                elif data.get("success") or (data.get("ok") and not data.get("stub")):
                    statut = "sent" if data.get("success") or data.get("sid") else "queued"
                    self._create_log(
                        statut,
                        "n8n",
                        external_sid=data.get("sid") or "",
                        payload=payload,
                        extra=data,
                    )
                    return {"type": "ir.actions.act_window_close"}
                else:
                    n8n_failed = True
            if n8n_failed and not self.fallback_twilio:
                err = (data or {}).get("error") or (resp.text if resp is not None else "n8n error")
                self._create_log("failed", "n8n", error=str(err), payload=payload, extra=data)
                raise UserError(_("n8n wa-send : %s") % err)

        from odoo.addons.doorway_messaging.services.whatsapp_service import WhatsAppService

        svc = WhatsAppService(self.env)
        result = svc.send_whatsapp(phone, body)
        if result.get("success"):
            self._create_log(
                "sent",
                "twilio",
                external_sid=result.get("sid") or "",
                payload=payload,
                extra=result,
            )
            return {"type": "ir.actions.act_window_close"}
        err = result.get("error") or _("Échec Twilio")
        self._create_log("failed", "twilio", error=err, payload=payload, extra=result)
        raise UserError(err)
