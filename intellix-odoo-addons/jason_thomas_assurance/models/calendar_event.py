from odoo import fields, models


class CalendarEvent(models.Model):
    _inherit = 'calendar.event'

    jt_client_id = fields.Many2one(
        'jt.client', string='Client JT', index=True, ondelete='set null',
    )

    def action_open_jt_client(self):
        self.ensure_one()
        if not self.jt_client_id:
            return False
        return {
            'type': 'ir.actions.act_window',
            'name': 'Client',
            'res_model': 'jt.client',
            'view_mode': 'form',
            'res_id': self.jt_client_id.id,
            'target': 'current',
        }
