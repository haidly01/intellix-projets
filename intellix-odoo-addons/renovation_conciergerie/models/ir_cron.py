from odoo import api, models


class IrCron(models.Model):
    _inherit = "ir.cron"

    @api.model
    def _doorway_enable_base_automation_cron(self):
        """Active le cron des règles planifiées (désactivé par défaut dans Odoo)."""
        cron = self.env.ref(
            "base_automation.ir_cron_data_base_automation_check",
            raise_if_not_found=False,
        )
        if cron:
            cron.sudo().write(
                {"active": True, "interval_number": 1, "interval_type": "hours"}
            )
