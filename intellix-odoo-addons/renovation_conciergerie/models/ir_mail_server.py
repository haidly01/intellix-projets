from odoo import api, models


class IrMailServer(models.Model):
    _inherit = "ir.mail_server"

    @api.model
    def _get_default_bounce_address(self):
        """Hostinger only authorizes info@agencedoorway.com as envelope sender."""
        bounce = super()._get_default_bounce_address()
        default_from = self.env.company.default_from_email
        if (
            bounce
            and default_from
            and bounce.endswith("@agencedoorway.com")
            and bounce != default_from
        ):
            return default_from
        return bounce
