# -*- coding: utf-8 -*-
from odoo import fields, models


class ResUsers(models.Model):
    _inherit = "res.users"

    is_portal_manager = fields.Boolean(
        string="Gestionnaire portail",
        default=False,
        help="Partenaire portail avec droits de gestion : facturation, profil de "
             "l'organisation, invitation et retrait des membres de l'équipe. "
             "Sans effet en dehors du portail partenaire.",
    )
