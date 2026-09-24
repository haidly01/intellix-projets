# -*- coding: utf-8 -*-
import json
import logging
import re
from datetime import timedelta

from odoo import _, api, fields, models
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


class DoorwayWhatsappSendWizard(models.TransientModel):
    _name = "doorway.whatsapp.send.wizard"
    _description = "Assistant envoi WhatsApp (OWL)"

    lead_id = fields.Many2one("crm.lead", string="Lead")
    partner_id = fields.Many2one("res.partner", string="Contact")
    partner_ids = fields.Many2many("res.partner", string="Destinataires")
    phone = fields.Char("Téléphone", required=True)
    message = fields.Text(string="Message")
    wa_message = fields.Text(string="Message WhatsApp")
    sms_message = fields.Text(string="Message SMS")
    email_body = fields.Text(string="Corps email")
    template_id = fields.Many2one("doorway.message.template", string="Template")
    timing = fields.Selection(
        [
            ("now", "Immédiat"),
            ("schedule", "Planifier"),
            ("retry", "Relance auto"),
        ],
        default="now",
    )
    log_crm = fields.Boolean(default=True)
    relance_auto = fields.Boolean(default=False)
    use_n8n = fields.Boolean(default=True)
    fallback_twilio = fields.Boolean(default=True)

    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        lead_id = self.env.context.get("default_lead_id")
        if lead_id and "partner_ids" in fields_list:
            lead = self.env["crm.lead"].browse(lead_id)
            partners = lead.partner_id
            if partners:
                res["partner_ids"] = [(6, 0, partners.ids)]
        return res

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
            "body": self.wa_message or self.message,
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

    def _log_crm_activity(self, body):
        self.ensure_one()
        if not self.log_crm or not self.lead_id:
            return
        note = _("WhatsApp envoyé : %s") % (body or "")[:500]
        self.lead_id.message_post(
            body=note,
            message_type="comment",
            subtype_xmlid="mail.mt_note",
        )
        try:
            activity_type = self.env.ref("mail.mail_activity_data_todo", raise_if_not_found=False)
            if activity_type:
                self.env["mail.activity"].create(
                    {
                        "activity_type_id": activity_type.id,
                        "res_model_id": self.env["ir.model"]._get("crm.lead").id,
                        "res_id": self.lead_id.id,
                        "summary": _("Relance WhatsApp"),
                        "note": body[:1000] if body else "",
                        "user_id": self.env.user.id,
                    }
                )
        except Exception:
            _logger.exception("WA wizard: création activité CRM")

    def _schedule_relance(self, body):
        self.ensure_one()
        if not self.relance_auto or self.timing != "retry" or not self.lead_id:
            return
        run_at = fields.Datetime.now() + timedelta(days=2)
        self.env["ir.cron"].sudo().create(
            {
                "name": _("Relance WhatsApp J+2 — %s") % (self.lead_id.name or self.phone),
                "model_id": self.env["ir.model"]._get("doorway.whatsapp.send.wizard").id,
                "state": "code",
                "code": (
                    "model.browse(%d).with_context(default_lead_id=%d, default_phone='%s')."
                    "create({'lead_id': %d, 'phone': '%s', 'wa_message': '''%s''', "
                    "'timing': 'now', 'log_crm': True}).action_send()"
                )
                % (
                    self.id,
                    self.lead_id.id,
                    self.phone.replace("'", "\\'"),
                    self.lead_id.id,
                    self.phone.replace("'", "\\'"),
                    (body or "").replace("'", "\\'")[:500],
                ),
                "nextcall": run_at,
                "numbercall": 1,
                "active": True,
            }
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

    def _send_via_n8n(self, phone, body, payload):
        import requests

        url = self._n8n_send_url()
        try:
            resp = requests.post(url, json=payload, timeout=25)
            data = resp.json() if resp.content else {}
        except Exception as exc:
            _logger.warning("n8n wa-send: %s", exc)
            return False, {"success": False, "error": str(exc)}, None
        if resp.status_code >= 400:
            return False, data, resp
        if data.get("success") or (data.get("ok") and not data.get("stub")):
            statut = "sent" if data.get("success") or data.get("sid") else "queued"
            self._create_log(
                statut,
                "n8n",
                external_sid=data.get("sid") or "",
                payload=payload,
                extra=data,
            )
            return True, data, resp
        return False, data, resp

    def _send_via_twilio(self, phone, body, payload):
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
            return True, result
        err = result.get("error") or _("Échec Twilio")
        self._create_log("failed", "twilio", error=err, payload=payload, extra=result)
        return False, result

    def action_send(self, message=None, timing=None, log_crm=None, relance_auto=None):
        """Envoi WhatsApp via n8n/Twilio + journal doorway.wa.log."""
        for rec in self:
            phone = rec._normalize_phone(rec.phone)
            if not phone:
                raise UserError(_("Numéro de téléphone invalide."))
            body = (message or rec.wa_message or rec.message or "").strip()
            if not body:
                raise UserError(_("Le message est vide."))

            if timing is not None:
                rec.timing = timing
            if log_crm is not None:
                rec.log_crm = log_crm
            if relance_auto is not None:
                rec.relance_auto = relance_auto

            payload = {
                "source": "odoo_doorway_messaging",
                "env": "dev",
                "lead_id": rec.lead_id.id or None,
                "partner_id": rec.partner_id.id or None,
                "phone": phone,
                "body": body,
                "user_id": rec.env.user.id,
                "timing": rec.timing,
            }

            sent = False
            if rec.use_n8n:
                ok, data, resp = rec._send_via_n8n(phone, body, payload)
                if ok:
                    sent = True
                elif rec.fallback_twilio:
                    sent, _result = rec._send_via_twilio(phone, body, payload)
                else:
                    err = (data or {}).get("error") or (
                        resp.text if resp is not None else "n8n error"
                    )
                    raise UserError(_("n8n wa-send : %s") % err)
            else:
                sent, _result = rec._send_via_twilio(phone, body, payload)

            if not sent:
                raise UserError(_("Échec de l'envoi WhatsApp."))

            rec._log_crm_activity(body)
            rec._schedule_relance(body)

        return {"type": "ir.actions.act_window_close"}
