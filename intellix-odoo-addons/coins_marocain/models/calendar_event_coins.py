# -*- coding: utf-8 -*-
from odoo import _, models


class CalendarEvent(models.Model):
    _inherit = 'calendar.event'

    def action_open_coins_source(self):
        self.ensure_one()
        model = getattr(self, 'res_model', False)
        res_id = getattr(self, 'res_id', False)
        if not model or not res_id:
            return False
        if model not in ('coins.detente_booking', 'coins.reservation'):
            return False
        return {
            'type': 'ir.actions.act_window',
            'name': _('Réservation Coins'),
            'res_model': model,
            'res_id': res_id,
            'view_mode': 'form',
            'target': 'current',
        }
