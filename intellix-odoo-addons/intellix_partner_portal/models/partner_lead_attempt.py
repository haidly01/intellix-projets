# -*- coding: utf-8 -*-
from odoo import fields, models


ATTEMPT_CHANNELS = [
    ("phone", "Appel"),
    ("sms", "SMS"),
    ("email", "Courriel"),
    ("voicemail", "Messagerie vocale"),
]

ATTEMPT_RESULTS = [
    ("no_answer", "Pas de réponse"),
    ("callback", "À rappeler"),
    ("interested", "Intéressé — à relancer"),
    ("refused", "Ne souhaite plus donner suite"),
]


class IntellixPartnerLeadAttempt(models.Model):
    _name = "intellix.partner.lead.attempt"
    _description = "Tentative de contact partenaire"
    _order = "attempt_date, id"

    mandate_id = fields.Many2one(
        "intellix.partner.lead.mandate",
        string="Mandat",
        required=True,
        ondelete="cascade",
        index=True,
    )
    attempt_date = fields.Datetime(string="Date et heure", required=True)
    channel = fields.Selection(
        ATTEMPT_CHANNELS,
        string="Canal",
        default="phone",
    )
    result = fields.Selection(
        ATTEMPT_RESULTS,
        string="Résultat",
        required=True,
        default="no_answer",
    )
    note = fields.Text(string="Note")
    user_id = fields.Many2one("res.users", string="Auteur")

    def channel_icon(self):
        icons = {
            "phone": "📞",
            "sms": "💬",
            "email": "✉️",
            "voicemail": "📱",
        }
        self.ensure_one()
        return icons.get(self.channel, "")

    def channel_label(self):
        self.ensure_one()
        return dict(ATTEMPT_CHANNELS).get(self.channel, self.channel)

    def result_label(self):
        self.ensure_one()
        return dict(ATTEMPT_RESULTS).get(self.result, self.result)
