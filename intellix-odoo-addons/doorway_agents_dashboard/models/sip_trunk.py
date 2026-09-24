# -*- coding: utf-8 -*-
from odoo import fields, models


class DoorwaySipTrunk(models.Model):
    _name = "doorway.sip.trunk"
    _description = "SIP trunk (Twilio BYOC ou indépendant)"
    _order = "name"

    name = fields.Char(string="Nom", required=True)
    provider = fields.Selection(
        [
            ("twilio", "Twilio BYOC"),
            ("custom", "SIP trunk indépendant"),
        ],
        string="Type",
        default="twilio",
        required=True,
    )
    twilio_trunk_sid = fields.Char(
        string="Twilio Trunk SID",
        help="Identifiant TK… depuis la console Twilio.",
    )
    termination_uri = fields.Char(
        string="URI de terminaison SIP",
        help="Ex. sip.votre-fournisseur.com pour un trunk indépendant.",
    )
    sip_username = fields.Char(string="Utilisateur SIP")
    sip_password = fields.Char(string="Mot de passe SIP")
    sip_port = fields.Integer(string="Port SIP", default=5060)
    notes = fields.Text(string="Notes")
    company_id = fields.Many2one(
        "res.company",
        string="Société",
        default=lambda self: self.env.company,
    )
    active = fields.Boolean(default=True)
    phone_number_ids = fields.One2many(
        "doorway.agent.phone.number",
        "trunk_id",
        string="Numéros liés",
    )
