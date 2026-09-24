# -*- coding: utf-8 -*-
from odoo import api, models


class CoinsQuebecCalendarEvent(models.Model):
    """Un vrai RDV (pas un rappel / activité Call) → fiche CQ en colonne En RDV."""

    _inherit = "calendar.event"

    def _cq_linked_partenariat(self):
        self.ensure_one()
        Part = self.env["coins.quebec.partenariat"].sudo()
        part = Part.search([("cq_rdv_event_id", "=", self.id)], limit=1)
        if part:
            return part
        if self.res_model == "coins.quebec.partenariat" and self.res_id:
            rec = Part.browse(self.res_id)
            return rec if rec.exists() else Part.browse()
        return Part.browse()

    def _cq_try_move_fiche_en_rdv(self):
        if self.env.context.get("doorway_skip_activity_sync"):
            return
        if self.env.context.get("cq_skip_rdv_stage"):
            return
        Part = self.env["coins.quebec.partenariat"].sudo()
        for event in self:
            if not Part._cq_is_real_rdv_event(event):
                continue
            part = event._cq_linked_partenariat()
            if part:
                part._cq_mark_en_rdv_from_event(event)

    @api.model_create_multi
    def create(self, vals_list):
        events = super().create(vals_list)
        events._cq_try_move_fiche_en_rdv()
        return events

    def write(self, vals):
        res = super().write(vals)
        if {
            "start",
            "stop",
            "active",
            "res_id",
            "res_model_id",
            "name",
        }.intersection(vals):
            self._cq_try_move_fiche_en_rdv()
        return res

    @api.depends("partner_ids", "user_id", "create_uid")
    @api.depends_context("uid")
    def _compute_user_can_edit(self):
        """Leila / booker CQ : le formulaire Odoo cache date, heure et
        suppression si ``user_can_edit`` est faux. L'hôte reste Martin
        (user_id), donc le booker n'est souvent pas organisateur ni invité.
        On autorise la créatrice — pas tous les RDV du calendrier CQ.
        """
        super()._compute_user_can_edit()
        uid = self.env.uid
        for event in self:
            if event.user_can_edit:
                continue
            if event.create_uid.id == uid:
                event.user_can_edit = True
