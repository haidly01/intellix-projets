# -*- coding: utf-8 -*-
from odoo import fields, models


class AgentPhoneNumber(models.Model):
    _name = "doorway.agent.phone.number"
    _description = "Numéro assigné à un agent IA"
    _order = "is_primary desc, active desc, id desc"

    agent_id = fields.Many2one(
        "doorway.agent.profile",
        string="Agent IA",
        required=True,
        ondelete="cascade",
        index=True,
    )
    name = fields.Char(string="Nom", required=True, default="Ligne principale")
    phone_number = fields.Char(string="Numéro", required=True, index=True)
    phone_source = fields.Selection(
        [
            ("manual", "Numéro existant"),
            ("twilio_purchased", "Acheté via Twilio"),
            ("sip_trunk", "SIP trunk"),
        ],
        string="Source",
        default="manual",
    )
    country_code = fields.Char(string="Pays", default="CA")
    twilio_incoming_sid = fields.Char(
        string="Twilio Incoming SID",
        help="Identifiant PN… du numéro dans le compte Twilio.",
    )
    trunk_id = fields.Many2one(
        "doorway.sip.trunk",
        string="SIP trunk",
        ondelete="set null",
    )
    usage = fields.Selection(
        [
            ("inbound", "Entrant"),
            ("outbound", "Sortant"),
            ("transfer", "Transfert humain"),
            ("sms", "SMS"),
        ],
        string="Usage",
        default="outbound",
        required=True,
    )
    is_primary = fields.Boolean(string="Numéro principal", default=False)
    active = fields.Boolean(string="Actif", default=True)
    sip_trunk_name = fields.Char(
        string="SIP trunk Twilio",
        help="Ex. Digital Doorway-4387905970",
    )
    twilio_sip_trunk_sid = fields.Char(
        string="Twilio SIP Trunk SID",
        help="Ex. TK4005d66df6aefef66f0a63a711491166",
    )
    elevenlabs_phone_number_id = fields.Char(
        string="ElevenLabs phone_number_id",
        help="ID ConvAI (phnum_…) pour /convai/twilio/outbound-call.",
    )
    notes = fields.Text(string="Notes")
