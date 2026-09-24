# -*- coding: utf-8 -*-
from odoo import api, models


class CalendarEventRenoRdv(models.Model):
    """Leila booke pour Martin : le formulaire calendrier reste éditable
    pour la créatrice (même logique que CQ, bornée aux RDV Réno)."""

    _inherit = "calendar.event"

    @api.depends("partner_ids", "user_id", "create_uid")
    @api.depends_context("uid")
    def _compute_user_can_edit(self):
        super()._compute_user_can_edit()
        uid = self.env.uid
        candidates = self.filtered(
            lambda e: not e.user_can_edit and e.create_uid.id == uid
        )
        if not candidates:
            return
        Rdv = self.env["renovation.partner.rdv"].sudo()
        linked_ids = set(
            Rdv.search([("event_id", "in", candidates.ids)]).mapped("event_id").ids
        )
        for event in candidates:
            if event.id in linked_ids:
                event.user_can_edit = True
