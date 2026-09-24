from odoo import fields, models


class RenovationPartnerPostalCode(models.Model):
    _name = "renovation.partner.postal.code"
    _description = "Code postal desservi par le partenaire"
    _order = "postal_code"

    partner_id = fields.Many2one(
        "res.partner",
        string="Partenaire",
        required=True,
        ondelete="cascade",
    )
    postal_code = fields.Char(
        string="Code postal",
        required=True,
    )
    city = fields.Char(string="Ville associée")
    country_id = fields.Many2one(
        "res.country",
        string="Pays",
        default=lambda self: self.env.ref("base.ca", raise_if_not_found=False),
    )
