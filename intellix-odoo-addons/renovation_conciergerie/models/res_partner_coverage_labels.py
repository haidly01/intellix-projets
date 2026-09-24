from odoo import fields, models


class ResPartnerCoverageLabels(models.Model):
    _inherit = "res.partner"

    coverage_mode = fields.Selection(
        selection=[
            ("city", "Villes spécifiques"),
            ("radius", "Rayon (km)"),
            ("postal", "Codes postaux"),
            ("province", "Province / région"),
        ],
        default="city",
        string="Mode de couverture",
    )
