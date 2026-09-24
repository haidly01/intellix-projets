# -*- coding: utf-8 -*-

from odoo import fields, models


class IntellixRiadPresenceCorrection(models.Model):
    _name = "intellix.riad.presence.correction"
    _description = "Historique de correction de pointage"
    _order = "changed_at desc, id desc"

    summary_id = fields.Many2one(
        "pe.presence.summary",
        string="Pointage",
        required=True,
        ondelete="cascade",
        index=True,
    )
    employee_id = fields.Many2one("hr.employee", string="Employé", required=True, index=True)
    date = fields.Date(string="Jour concerné", required=True, index=True)
    establishment_id = fields.Many2one("intellix.riad.establishment", string="Établissement")
    changed_by_id = fields.Many2one(
        "res.users",
        string="Corrigé par",
        required=True,
        default=lambda self: self.env.user,
    )
    changed_at = fields.Datetime(
        string="Corrigé le",
        required=True,
        default=fields.Datetime.now,
    )
    previous_label = fields.Char(string="Valeur précédente")
    new_label = fields.Char(string="Nouvelle valeur")
    previous_value = fields.Text(string="Détail précédent")
    new_value = fields.Text(string="Détail nouveau")
