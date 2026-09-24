from odoo import fields, models


class RenovationRetellCallLog(models.Model):
    _name = "renovation.retell.call.log"
    _description = "Journal des appels Agent IA (legacy)"
    _order = "create_date desc"

    lead_id = fields.Many2one("crm.lead", string="Lead", required=True, ondelete="cascade", index=True)
    partner_id = fields.Many2one("res.partner", string="Contact")
    phone_number = fields.Char(string="Numero appele")
    status = fields.Char(string="Statut")
    retell_call_id = fields.Char(string="Retell Call ID", index=True)
    duration_seconds = fields.Integer(string="Duree (s)")
    transcript_url = fields.Char(string="URL transcription")
    recording_url = fields.Char(string="URL enregistrement")
    error_message = fields.Text(string="Erreur")
    raw_payload = fields.Text(string="Payload brut")


class CrmLead(models.Model):
    _inherit = "crm.lead"

    retell_call_log_ids = fields.One2many(
        "renovation.retell.call.log",
        "lead_id",
        string="Appels Agent IA (historique)",
    )

    def action_call_contact_via_retell(self):
        """Alias legacy → appel via agent IA (ElevenLabs / Twilio / n8n)."""
        return self.action_call_contact_via_agent_ia()
