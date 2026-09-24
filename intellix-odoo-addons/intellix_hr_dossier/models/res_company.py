# -*- coding: utf-8 -*-
from odoo import fields, models


class ResCompany(models.Model):
    _inherit = "res.company"

    x_hr_signatory_name = fields.Char(string="Signataire RH — Nom")
    x_hr_signatory_title = fields.Char(string="Signataire RH — Fonction")
    x_cnss_employer_number = fields.Char(string="N° CNSS employeur")
    x_morocco_ice = fields.Char(string="ICE")
    x_morocco_rc = fields.Char(string="Registre de commerce (RC)")
    x_attestation_city = fields.Char(
        string="Ville attestations (Fait à)",
        help="Ville affichée dans le bloc « Fait à …, le … » des attestations.",
    )
