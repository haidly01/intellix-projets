from odoo import fields, models

class RenovationPackageType(models.Model):
    _name = "renovation.package.type"
    _description = "Type de forfait partenaire"
    _order = "sequence, name"

    name = fields.Char(required=True)
    code = fields.Char()
    sequence = fields.Integer(default=10)
    leads_included = fields.Integer(string="Leads inclus", required=True, default=10)
    price = fields.Float(string="Prix")
    validity_days = fields.Integer(string="Durée (jours)", default=365)
    active = fields.Boolean(default=True)
    description = fields.Html(translate=True)
