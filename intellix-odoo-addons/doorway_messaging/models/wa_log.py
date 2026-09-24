# -*- coding: utf-8 -*-
import json

from odoo import _, fields, models
from odoo.exceptions import UserError


class DoorwayWaLog(models.Model):
    _name = "doorway.wa.log"
    _description = "Journal WhatsApp (Twilio / n8n)"
    _order = "create_date desc, id desc"

    lead_id = fields.Many2one("crm.lead", ondelete="set null", index=True)
    partner_id = fields.Many2one("res.partner", ondelete="set null")
    user_id = fields.Many2one("res.users", string="Envoyé par", default=lambda self: self.env.user)

    direction = fields.Selection(
        [("outbound", "Sortant"), ("inbound", "Entrant")],
        default="outbound",
        required=True,
        index=True,
    )
    phone = fields.Char("Téléphone", required=True, index=True)
    body = fields.Text("Message")
    message = fields.Text(related="body", string="Message", readonly=True)
    statut = fields.Selection(
        [
            ("draft", "Brouillon"),
            ("queued", "File n8n"),
            ("sent", "Envoyé"),
            ("delivered", "Délivré"),
            ("failed", "Échec"),
            ("received", "Reçu"),
        ],
        default="draft",
        index=True,
    )
    provider = fields.Selection(
        [("n8n", "n8n"), ("twilio", "Twilio direct"), ("stub", "Stub DEV")],
        default="n8n",
    )
    external_sid = fields.Char("ID Twilio / Meta")
    twilio_meta_id = fields.Char(related="external_sid", string="ID Twilio / Meta", readonly=True)
    n8n_execution_id = fields.Char("ID exécution n8n")
    error_message = fields.Text("Erreur")
    payload_json = fields.Text("Payload brut (debug)")
    raw_payload = fields.Text(related="payload_json", string="Payload brut", readonly=True)
    sent_by = fields.Many2one(related="user_id", string="Envoyé par", readonly=True)

    def action_reply(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": _("Répondre WhatsApp"),
            "res_model": "doorway.whatsapp.send.wizard",
            "view_mode": "form",
            "target": "new",
            "context": {
                "default_lead_id": self.lead_id.id,
                "default_partner_id": self.partner_id.id,
                "default_phone": self.phone,
                "default_message": self.body,
                "default_wa_message": self.body,
            },
        }

    def action_link_lead(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": _("Lier un lead"),
            "res_model": "crm.lead",
            "view_mode": "list,form",
            "target": "new",
            "domain": [],
            "context": {"wa_log_link_id": self.id},
        }

    def action_copy_payload(self):
        self.ensure_one()
        payload = self.payload_json or "{}"
        try:
            parsed = json.loads(payload)
            payload = json.dumps(parsed, indent=2, ensure_ascii=False)
        except (TypeError, ValueError):
            pass
        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": _("Payload copié"),
                "message": payload[:500],
                "type": "info",
                "sticky": False,
            },
        }
