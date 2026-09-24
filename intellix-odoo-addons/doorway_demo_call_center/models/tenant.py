# -*- coding: utf-8 -*-
from odoo import fields, models


class DoorwayTenant(models.Model):
    _inherit = "doorway.tenant"

    demo_call_center = fields.Boolean(
        string="Demo Call Center",
        help="Espace demo isolé avec tarif forfaitaire par consommation.",
    )
    demo_flat_rate_eur = fields.Float(
        string="Tarif demo (€ / unité)",
        digits=(16, 4),
        help="Si renseigné, chaque débit utilise ce tarif (ex. 0,22 €/min ou /appel).",
    )

    def _doorway_custom_service_price(self, service, quantity=1):
        self.ensure_one()
        if self.demo_call_center and self.demo_flat_rate_eur:
            return round(self.demo_flat_rate_eur * quantity, 4)
        return super()._doorway_custom_service_price(service, quantity)
