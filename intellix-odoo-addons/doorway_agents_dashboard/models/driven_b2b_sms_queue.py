# -*- coding: utf-8 -*-
import logging

from odoo import api, fields, models

_logger = logging.getLogger(__name__)

SMS_TEMPLATES = {
    "j2": "Bonjour {prenom}, avez-vous eu la chance de vérifier votre préqualification Driven ? driven.ca/partners/agence-doorway",
    "j5": "Bonjour {prenom}, dernière relance — des PME comme la vôtre ont obtenu 50K$-200K$ en 24h. driven.ca/partners/agence-doorway",
}


class DrivenB2bSmsQueue(models.Model):
    _name = "driven.b2b.sms.queue"
    _description = "Relances SMS Alex Driven B2B (J+2, J+5)"
    _order = "scheduled_at asc"

    partner_id = fields.Many2one("res.partner", ondelete="cascade", index=True)
    phone = fields.Char(required=True, index=True)
    prenom = fields.Char()
    variant = fields.Selection(
        [("j2", "J+2"), ("j5", "J+5")],
        required=True,
        default="j2",
    )
    scheduled_at = fields.Datetime(required=True, index=True)
    state = fields.Selection(
        [("pending", "En attente"), ("sent", "Envoyé"), ("error", "Erreur"), ("cancelled", "Annulé")],
        default="pending",
        index=True,
    )
    error_message = fields.Char()

    @api.model
    def cron_send_pending(self):
        now = fields.Datetime.now()
        pending = self.search(
            [("state", "=", "pending"), ("scheduled_at", "<=", now)],
            limit=50,
        )
        for rec in pending:
            rec._send_one()

    def _send_one(self):
        self.ensure_one()
        prenom = self.prenom or "Bonjour"
        tpl = SMS_TEMPLATES.get(self.variant, SMS_TEMPLATES["j2"])
        body = tpl.format(prenom=prenom)
        try:
            from odoo.addons.doorway_messaging.services.sms_service import SmsService

            SmsService(self.env).send_sms(self.phone, body)
            self.write({"state": "sent", "error_message": False})
        except Exception as exc:
            _logger.warning("Driven SMS %s failed: %s", self.id, exc)
            self.write({"state": "error", "error_message": str(exc)[:200]})
