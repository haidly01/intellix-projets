import requests

from odoo import _, api, fields, models
from odoo.exceptions import UserError


class RenovationTwilioCallLog(models.Model):
    _name = "renovation.twilio.call.log"
    _description = "Journal des appels Twilio"
    _order = "create_date desc"

    lead_id = fields.Many2one("crm.lead", string="Lead", required=True, ondelete="cascade", index=True)
    partner_id = fields.Many2one("res.partner", string="Contact")
    phone_number = fields.Char(string="Numero appele")
    direction = fields.Selection(
        [("outbound", "Sortant"), ("inbound", "Entrant")],
        default="outbound",
        required=True,
    )
    status = fields.Selection(
        [
            ("queued", "Queued"),
            ("ringing", "Ringing"),
            ("in-progress", "In Progress"),
            ("completed", "Completed"),
            ("busy", "Busy"),
            ("failed", "Failed"),
            ("no-answer", "No Answer"),
            ("canceled", "Canceled"),
        ],
        default="queued",
        string="Statut",
    )
    twilio_call_sid = fields.Char(string="Twilio Call SID", index=True)
    started_at = fields.Datetime(string="Debut")
    ended_at = fields.Datetime(string="Fin")
    duration_seconds = fields.Integer(string="Duree (s)")
    recording_sid = fields.Char(string="Recording SID")
    recording_url = fields.Char(string="URL enregistrement")
    recording_status = fields.Char(string="Statut enregistrement")
    error_message = fields.Text(string="Erreur")


class CrmLead(models.Model):
    _inherit = "crm.lead"

    twilio_call_log_ids = fields.One2many(
        "renovation.twilio.call.log",
        "lead_id",
        string="Appels Twilio",
    )

    twilio_call_count = fields.Integer(
        compute="_compute_twilio_call_count",
        string="Nb appels Twilio",
    )

    @api.depends("twilio_call_log_ids")
    def _compute_twilio_call_count(self):
        for lead in self:
            lead.twilio_call_count = len(lead.twilio_call_log_ids)

    def _get_contact_firstname(self):
        self.ensure_one()
        full_name = (self.partner_id.name or self.contact_name or "").strip()
        return full_name.split(" ")[0] if full_name else ""

    def _get_message_prefill_text(self):
        self.ensure_one()
        firstname = self._get_contact_firstname()
        rdv_notes = (self.rdv_notes or self.description or "").strip()
        intro = f"Bonjour {firstname}," if firstname else "Bonjour,"
        if rdv_notes:
            return (
                f"{intro}\n\n"
                f"Suite a votre demande \"{self.name}\", voici un recapitulatif.\n\n"
                f"Notes RDV:\n{rdv_notes}\n\n"
                "Cordialement,"
            )
        return (
            f"{intro}\n\n"
            f"Suite a votre demande \"{self.name}\", nous revenons vers vous.\n\n"
            "Cordialement,"
        )

    def _get_lead_media_attachment_ids(self):
        self.ensure_one()
        attachments = self.env["ir.attachment"].search(
            [("res_model", "=", "crm.lead"), ("res_id", "=", self.id)]
        )
        media_attachments = attachments.filtered(
            lambda a: (
                (a.mimetype and (a.mimetype.startswith("image/") or a.mimetype == "application/pdf"))
                or ("plan" in (a.name or "").lower())
                or ("photo" in (a.name or "").lower())
            )
        )
        return media_attachments.ids

    def _get_renovation_default_email_from(self):
        return "info@agencedoorway.com"

    def _get_renovation_partner_cc_email(self):
        self.ensure_one()
        return (self.assigned_partner_id.email or "").strip()

    def action_call_contact_via_twilio(self):
        self.ensure_one()
        to_number = self.phone or self.mobile or self.partner_id.phone or self.partner_id.mobile
        if not to_number:
            raise UserError(_("Aucun numero de telephone n'est renseigne sur ce lead."))

        params = self.env["ir.config_parameter"].sudo()
        account_sid = params.get_param("renovation_conciergerie.twilio_account_sid")
        auth_token = params.get_param("renovation_conciergerie.twilio_auth_token")
        from_number = params.get_param("renovation_conciergerie.twilio_from_number")
        base_url = params.get_param("renovation_conciergerie.twilio_base_url")
        if not all([account_sid, auth_token, from_number, base_url]):
            raise UserError(
                _(
                    "Configuration Twilio incomplete. Renseignez SID, Auth Token, numero emetteur et URL publique."
                )
            )

        status_callback = f"{base_url.rstrip('/')}/renovation/twilio/status"
        recording_callback = f"{base_url.rstrip('/')}/renovation/twilio/recording"
        twiml_url = f"{base_url.rstrip('/')}/renovation/twilio/twiml/outbound"
        endpoint = f"https://api.twilio.com/2010-04-01/Accounts/{account_sid}/Calls.json"

        response = requests.post(
            endpoint,
            data={
                "To": to_number,
                "From": from_number,
                "Url": twiml_url,
                "Record": "true",
                "StatusCallback": status_callback,
                "StatusCallbackEvent": ["initiated", "ringing", "answered", "completed"],
                "RecordingStatusCallback": recording_callback,
            },
            auth=(account_sid, auth_token),
            timeout=15,
        )
        if response.status_code >= 300:
            raise UserError(_("Erreur Twilio: %s") % response.text)

        payload = response.json()
        self.env["renovation.twilio.call.log"].create(
            {
                "lead_id": self.id,
                "partner_id": self.partner_id.id,
                "phone_number": to_number,
                "direction": "outbound",
                "status": payload.get("status") or "queued",
                "twilio_call_sid": payload.get("sid"),
            }
        )
        return True

    def action_open_email_composer(self):
        self.ensure_one()
        self.message_subscribe(partner_ids=self.partner_id.ids)
        email_from = self._get_renovation_default_email_from()
        email_cc = self._get_renovation_partner_cc_email()
        return {
            "type": "ir.actions.act_window",
            "res_model": "mail.compose.message",
            "view_mode": "form",
            "target": "new",
            "context": {
                "default_model": "crm.lead",
                "default_res_ids": [self.id],
                "default_composition_mode": "comment",
                "default_use_template": True,
                "default_subject": f"Suivi - {self.name}",
                "default_body": self._get_message_prefill_text(),
                "default_email_from": email_from,
                "default_email_cc": email_cc,
            },
        }

    def action_open_email_composer_with_attachments(self):
        self.ensure_one()
        action = self.action_open_email_composer()
        action["context"]["default_attachment_ids"] = [(6, 0, self._get_lead_media_attachment_ids())]
        return action

    def action_open_sms_composer(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "res_model": "sms.composer",
            "view_mode": "form",
            "target": "new",
            "context": {
                "default_res_model": "crm.lead",
                "default_res_ids": [self.id],
                "default_body": self._get_message_prefill_text(),
            },
        }

    def action_send_default_email_template(self):
        self.ensure_one()
        self.message_subscribe(partner_ids=self.partner_id.ids)
        template = self.env.ref(
            "renovation_conciergerie.mail_template_crm_lead_partner_followup",
            raise_if_not_found=False,
        )
        if not template:
            raise UserError(_("Gabarit email par defaut introuvable."))
        template.send_mail(
            self.id,
            force_send=True,
            email_values={
                "email_from": self._get_renovation_default_email_from(),
                "email_cc": self._get_renovation_partner_cc_email(),
            },
        )
        return True

    def action_send_default_sms_template(self):
        self.ensure_one()
        template = self.env.ref(
            "renovation_conciergerie.sms_template_crm_lead_partner_followup",
            raise_if_not_found=False,
        )
        if not template:
            raise UserError(_("Gabarit SMS par defaut introuvable."))

        composer = self.env["sms.composer"].create(
            {
                "composition_mode": "comment",
                "res_model": "crm.lead",
                "res_id": self.id,
                "template_id": template.id,
                "mass_force_send": True,
            }
        )
        composer.action_send_sms()
        return True

    def message_post(self, **kwargs):
        messages = super().message_post(**kwargs)
        if kwargs.get("message_type") == "email":
            body = kwargs.get("body") or ""
            subject = kwargs.get("subject") or _("Email lead")
            for lead in self.filtered("partner_id"):
                lead.partner_id.message_post(
                    body=body,
                    subject=subject,
                    message_type="comment",
                    subtype_xmlid="mail.mt_note",
                )
        return messages
