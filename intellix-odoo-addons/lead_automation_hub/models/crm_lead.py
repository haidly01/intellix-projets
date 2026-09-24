import logging
import re

from odoo import _, api, fields, models
from odoo.exceptions import ValidationError, UserError

try:
    from twilio.base.exceptions import TwilioRestException
    from twilio.rest import Client
except ImportError:
    TwilioRestException = Exception
    Client = None

_logger = logging.getLogger(__name__)
ANSI_ESCAPE_RE = re.compile(r"\x1B\[[0-?]*[ -/]*[@-~]")


class CrmLead(models.Model):
    _inherit = "crm.lead"

    lead_source_type = fields.Selection([
        ("csv", "CSV/Excel"),
        ("api", "API/Webhook"),
        ("landing", "Landing Page"),
    ], string="Source Type")

    ai_call_status = fields.Selection([
        ("pending", "Pending"),
        ("calling", "In Progress"),
        ("completed", "Completed"),
        ("failed", "Failed"),
    ], string="AI Call Status", default="pending", tracking=True)

    twilio_call_sid = fields.Char(string="Twilio Call SID", readonly=True)
    twilio_call_error = fields.Text(string="Twilio Error", readonly=True)

    ai_call_provider = fields.Selection([
        ("twilio", "Twilio"),
    ], string="AI Call Provider", readonly=True)

    campaign_id = fields.Many2one(
        "utm.campaign",
        string="Campaign",
        compute="_compute_segmentation",
        store=True,
        readonly=False,
    )

    lead_channel = fields.Selection([
        ("call", "Call"),
        ("email", "Email Only"),
    ], string="Channel", compute="_compute_segmentation", store=True)

    lead_score = fields.Integer(string="Score", compute="_compute_segmentation", store=True)

    lead_stage = fields.Selection([
        ("cold", "Cold"),
        ("hot", "Hot"),
    ], string="Lead Stage", compute="_compute_segmentation", store=True)

    # ---------------------------------------------------------
    # VALIDATION
    # ---------------------------------------------------------
    @api.constrains("email_from")
    def _check_unique_email(self):
        if self.env.context.get("doorway_skip_email_unique_check"):
            return
        if self.env.context.get("default_fetchmail_server_id"):
            return
        for record in self:
            if record.email_from and record.email_from != "email not available":
                duplicate = self.search([
                    ("email_from", "=ilike", record.email_from),
                    ("id", "!=", record.id),
                    ("active", "=", True),
                ], limit=1)
                if duplicate:
                    raise ValidationError(_("Erreur : Cet email existe deja !"))

    # ---------------------------------------------------------
    # HELPERS
    # ---------------------------------------------------------
    def _get_param(self, key, required_message=None):
        value = self.env["ir.config_parameter"].sudo().get_param(key)
        if isinstance(value, str):
            value = value.strip().strip("\"'").strip()
        if required_message and not value:
            raise UserError(required_message)
        return value

    def _get_clean_twilio_credential(self, key, required_message):
        value = self._get_param(key, required_message)
        return re.sub(r"\s+", "", value)

    def _get_twilio_credentials(self):
        account_sid = self._get_clean_twilio_credential(
            "twilio.account_sid",
            _("Missing Twilio Account SID. Set 'twilio.account_sid' in system parameters."),
        )
        auth_token = self._get_clean_twilio_credential(
            "twilio.auth_token",
            _("Missing Twilio Auth Token. Set 'twilio.auth_token' in system parameters."),
        )
        if not re.fullmatch(r"AC[0-9a-fA-F]{32}", account_sid):
            raise UserError(_(
                "Twilio Account SID must start with 'AC' and contain 32 hexadecimal characters."
            ))
        if not re.fullmatch(r"[0-9a-fA-F]{32}", auth_token):
            raise UserError(_(
                "Twilio Auth Token must contain exactly 32 hexadecimal characters."
            ))
        return account_sid, auth_token

    def _clean_error_message(self, message):
        clean_message = ANSI_ESCAPE_RE.sub("", str(message or ""))
        return clean_message.replace("\r", "").strip()

    def _get_twilio_error_message(self, exception):
        error_code = getattr(exception, "code", None)
        error_status = getattr(exception, "status", None)
        if error_code == 20003 or error_status == 401:
            return _(
                "Twilio authentication failed. Check that system parameters "
                "'twilio.account_sid' and 'twilio.auth_token' match the same "
                "Twilio account, then try again."
            )
        return self._clean_error_message(exception)

    def _get_twilio_client(self):
        self.ensure_one()
        if not Client:
            raise UserError(_(
                "The Twilio Python client is not available on this Odoo server."
            ))

        account_sid, auth_token = self._get_twilio_credentials()
        return Client(account_sid, auth_token)

    def _get_twilio_from_number(self):
        self.ensure_one()
        return self._get_param(
            "twilio.from_number",
            _("Missing Twilio From Number. Set 'twilio.from_number' in system parameters."),
        )

    def _get_twilio_call_kwargs(self):
        self.ensure_one()
        twiml = self._get_param("twilio.twiml")
        twiml_url = self._get_param("twilio.twiml_url")
        status_callback = self._get_param("twilio.status_callback_url")

        if not twiml and not twiml_url:
            lead_name = self.contact_name or self.partner_name or self.name or _("there")
            twiml = (
                "<Response>"
                f"<Say voice=\"alice\">Hello {lead_name}. This is an automated call from Lead Automation Hub.</Say>"
                "</Response>"
            )

        call_kwargs = {
            "from_": self._get_twilio_from_number(),
            "to": self._normalize_phone_number(self.phone),
        }
        if twiml:
            call_kwargs["twiml"] = twiml
        elif twiml_url:
            call_kwargs["url"] = twiml_url

        if status_callback:
            call_kwargs["status_callback"] = status_callback
            call_kwargs["status_callback_event"] = ["initiated", "ringing", "answered", "completed"]

        return call_kwargs

    def _normalize_phone_number(self, phone_number):
        self.ensure_one()

        raw_number = (phone_number or "").strip()
        if not raw_number or raw_number == "phone not available":
            raise UserError(_("This lead does not have a valid phone number."))

        normalized = re.sub(r"[^\d+]", "", raw_number)
        if normalized.startswith("00"):
            normalized = f"+{normalized[2:]}"
        elif normalized.startswith("+"):
            normalized = f"+{re.sub(r'[^0-9]', '', normalized)}"
        elif self.country_id and self.country_id.phone_code:
            digits = re.sub(r"\D", "", normalized)
            country_code = re.sub(r"\D", "", str(self.country_id.phone_code))
            if digits.startswith(country_code):
                normalized = f"+{digits}"
            else:
                normalized = f"+{country_code}{digits.lstrip('0')}"
        else:
            raise UserError(_(
                "Phone number '%s' must be in international format like "
                "'+15551234567', or the lead must have a country set."
            ) % raw_number)

        digits_only = re.sub(r"\D", "", normalized)
        if not digits_only:
            raise UserError(_("Phone number '%s' is invalid.") % raw_number)

        return f"+{digits_only}"

    def action_make_twilio_call(self):
        for lead in self:
            try:
                client = lead._get_twilio_client()
                call = client.calls.create(**lead._get_twilio_call_kwargs())
            except TwilioRestException as exc:
                error_message = lead._get_twilio_error_message(exc)
                lead.write({
                    "ai_call_status": "failed",
                    "ai_call_provider": "twilio",
                    "twilio_call_error": error_message,
                })
                _logger.exception("Twilio call failed for lead %s", lead.id)
                raise UserError(_("Twilio call failed: %s") % error_message)
            except Exception as exc:
                error_message = lead._clean_error_message(exc)
                lead.write({
                    "ai_call_status": "failed",
                    "ai_call_provider": "twilio",
                    "twilio_call_error": error_message,
                })
                _logger.exception("Unexpected Twilio error for lead %s", lead.id)
                raise UserError(_("Twilio call failed: %s") % error_message)

            lead.write({
                "ai_call_status": "calling",
                "ai_call_provider": "twilio",
                "twilio_call_sid": call.sid,
                "twilio_call_error": False,
            })
            _logger.info("Twilio call started for lead %s with sid %s", lead.id, call.sid)

        return True
    # ---------------------------------------------------------
    # SEGMENTATION (UNCHANGED)
    # ---------------------------------------------------------
    @api.depends("country_id", "tag_ids", "phone", "email_from", "lead_source_type")
    def _compute_segmentation(self):
        for lead in self:

            phone_value = lead.phone or False
            email_value = lead.email_from or False

            has_real_phone = bool(phone_value) and phone_value != "phone not available"
            has_real_email = bool(email_value) and email_value != "email not available"

            if lead.country_id:
                code = lead.country_id.code or lead.country_id.name
                target_campaign_name = f"Company {code}"
            else:
                target_campaign_name = "General"

            current_tags = [tag.name.lower().strip() for tag in lead.tag_ids]

            if lead.country_id:
                all_rules = self.env["lead.campaign.map"].sudo().search(
                    [("country_id", "=", lead.country_id.id)]
                )

                rule_found = False
                for rule in all_rules:
                    if rule.tag_name and rule.tag_name.lower().strip() in current_tags:
                        target_campaign_name = rule.campaign_name
                        rule_found = True
                        break

                if not rule_found:
                    fallback = self.env["lead.campaign.map"].sudo().search(
                        [
                            ("country_id", "=", lead.country_id.id),
                            "|",
                            ("tag_name", "=", False),
                            ("tag_name", "=", ""),
                        ],
                        limit=1,
                    )
                    if fallback:
                        target_campaign_name = fallback.campaign_name

            campaign_record = self.env["utm.campaign"].sudo().search(
                [("name", "=", target_campaign_name)],
                limit=1,
            )

            if not campaign_record and target_campaign_name:
                campaign_record = self.env["utm.campaign"].sudo().create(
                    {"name": target_campaign_name}
                )

            lead.campaign_id = campaign_record.id if campaign_record else False
            lead.lead_channel = "call" if has_real_phone else "email"

            score = 0
            if has_real_email:
                score += 15
            if has_real_phone:
                score += 30
            if lead.country_id:
                score += 10
            if lead.tag_ids:
                score += 10

            lead.lead_score = min(score, 100)
            lead.lead_stage = "hot" if score >= 50 else "cold"

            target_stage = self.env["crm.stage"].sudo().search(
                [("name", "ilike", lead.lead_stage)],
                limit=1,
            )
            if target_stage:
                lead.stage_id = target_stage.id

    # ---------------------------------------------------------
    # HOOKS
    # ---------------------------------------------------------
    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if not vals.get("name"):
                info = vals.get("email_from") or vals.get("phone") or "Unknown"
                vals["name"] = f"Lead - {info}"

        return super().create(vals_list)

# import logging
# from odoo import models, fields, api
# from odoo.exceptions import ValidationError

# _logger = logging.getLogger(__name__)

# class CrmLead(models.Model):
#     _inherit = 'crm.lead'

#     # ---------------------------------------------------------
#     # CHAMPS SUPPLÉMENTAIRES
#     # ---------------------------------------------------------
#     lead_source_type = fields.Selection([
#         ('csv', 'CSV/Excel'),
#         ('api', 'API/Webhook'),
#         ('landing', 'Landing Page')
#     ], string='Source Type')

#     ai_call_status = fields.Selection([
#         ('pending', 'Pending'),
#         ('calling', 'In Progress'),
#         ('completed', 'Completed'),
#         ('failed', 'Failed')
#     ], string='AI Call Status', default='pending')

#     campaign_id = fields.Many2one(
#         'utm.campaign', 
#         string="Campaign", 
#         compute="_compute_segmentation", 
#         store=True,
#         readonly=False
#     )

#     lead_channel = fields.Selection([
#         ('call', 'Call'),
#         ('email', 'Email Only')
#     ], string="Channel", compute="_compute_segmentation", store=True)
    
#     lead_score = fields.Integer(string="Score", compute="_compute_segmentation", store=True)
    
#     lead_stage = fields.Selection([
#         ('cold', 'Cold'),
#         ('hot', 'Hot')
#     ], string="Lead Stage", compute="_compute_segmentation", store=True)

#     # ---------------------------------------------------------
#     # VALIDATION UNIQUE EMAIL
#     # ---------------------------------------------------------
#     @api.constrains('email_from')
#     def _check_unique_email(self):
#         for record in self:
#             # On ignore la validation d'unicité pour les emails non disponibles
#             if record.email_from and record.email_from != "email not available":
#                 duplicate = self.search([
#                     ('email_from', '=', record.email_from),
#                     ('id', '!=', record.id)
#                 ], limit=1)
#                 if duplicate:
#                     raise ValidationError("Erreur : Cet email existe déjà !")

#     # ---------------------------------------------------------
#     # MOTEUR DE SEGMENTATION & NETTOYAGE
#     # ---------------------------------------------------------
#     @api.depends('country_id', 'tag_ids', 'phone', 'email_from', 'lead_source_type')
#     def _compute_segmentation(self):
#         for lead in self:
#             # --- 1. GESTION DES CHAMPS VIDES ---
#             # Si le téléphone est absent, on affiche "phone not available"
#             if not lead.phone:
#                 lead.phone = "phone not available"
            
#             # Si l'email est absent, on affiche "email not available"
#             if not lead.email_from:
#                 lead.email_from = "email not available"

#             # --- 2. GESTION DE LA CAMPAGNE ---
#             if lead.country_id:
#                 code = lead.country_id.code if lead.country_id.code else lead.country_id.name
#                 target_campaign_name = f"Company {code}"
#             else:
#                 target_campaign_name = "General"

#             current_tags = [t.name.lower().strip() for t in lead.tag_ids]
            
#             if lead.country_id:
#                 all_rules = self.env['lead.campaign.map'].sudo().search([
#                     ('country_id', '=', lead.country_id.id)
#                 ])
                
#                 rule_found = False
#                 for r in all_rules:
#                     if r.tag_name and r.tag_name.lower().strip() in current_tags:
#                         target_campaign_name = r.campaign_name
#                         rule_found = True
#                         break

#                 if not rule_found:
#                     fallback = self.env['lead.campaign.map'].sudo().search([
#                         ('country_id', '=', lead.country_id.id),
#                         '|', ('tag_name', '=', False), ('tag_name', '=', '')
#                     ], limit=1)
#                     if fallback:
#                         target_campaign_name = fallback.campaign_name

#             campaign_record = self.env['utm.campaign'].sudo().search([
#                 ('name', '=', target_campaign_name)
#             ], limit=1)
            
#             if not campaign_record and target_campaign_name:
#                 campaign_record = self.env['utm.campaign'].sudo().create({'name': target_campaign_name})
            
#             lead.campaign_id = campaign_record.id if campaign_record else False
            
#             # --- 3. LOGIQUE DE SCORING ---
#             # On vérifie la présence de vraies données (différentes des textes par défaut)
#             has_real_phone = lead.phone and lead.phone != "phone not available"
#             has_real_email = lead.email_from and lead.email_from != "email not available"

#             lead.lead_channel = 'call' if has_real_phone else 'email'
            
#             score = 0
#             if has_real_email: score += 15
#             if has_real_phone: score += 30
#             if lead.country_id: score += 10
#             if lead.tag_ids: score += 10
#             lead.lead_score = min(score, 100)
            
#             # Détermination binaire (Cold ou Hot)
#             if score >= 50: 
#                 lead.lead_stage = 'hot'
#             else: 
#                 lead.lead_stage = 'cold'

#             # Mouvement Kanban
#             target_stage = self.env['crm.stage'].sudo().search([
#                 ('name', 'ilike', lead.lead_stage)
#             ], limit=1)

#             if target_stage:
#                 lead.stage_id = target_stage.id

#     @api.model_create_multi
#     def create(self, vals_list):
#         for vals in vals_list:
#             if not vals.get('name'):
#                 # Nettoyage visuel pour le titre du lead lors de la création
#                 info = vals.get('email_from') or vals.get('phone') or "Unknown"
#                 vals['name'] = f"Lead - {info}"
#         return super(CrmLead, self).create(vals_list)
