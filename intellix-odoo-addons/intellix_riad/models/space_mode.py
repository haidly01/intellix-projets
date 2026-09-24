# -*- coding: utf-8 -*-

from odoo import api, fields, models


class IntellixRiadSpaceMode(models.Model):
    _name = "intellix.riad.space.mode"
    _description = "Mode d'espace (terrasse bien-être / restaurant)"
    _order = "date desc, weekday, id"

    establishment_id = fields.Many2one(
        "intellix.riad.establishment",
        required=True,
        ondelete="cascade",
        index=True,
    )
    name = fields.Char(compute="_compute_name", store=True)
    is_template = fields.Boolean(string="Modèle hebdomadaire", default=False)
    weekday = fields.Selection(
        [
            ("0", "Lundi"),
            ("1", "Mardi"),
            ("2", "Mercredi"),
            ("3", "Jeudi"),
            ("4", "Vendredi"),
            ("5", "Samedi"),
            ("6", "Dimanche"),
        ],
        string="Jour",
    )
    date = fields.Date(string="Date (override)")
    wellness_start = fields.Float(string="Bien-être dès", default=10.0)
    wellness_end = fields.Float(string="Bien-être jusqu'à", default=17.0)
    restaurant_start = fields.Float(string="Restaurant dès", default=18.0)
    restaurant_end = fields.Float(string="Restaurant jusqu'à", default=23.0)
    wellness_label = fields.Char(string="Libellé bien-être")
    restaurant_label = fields.Char(string="Libellé restaurant")

    @api.depends("date", "weekday")
    def _compute_name(self):
        for rec in self:
            if rec.date:
                rec.name = rec.date.strftime("%d/%m/%Y")
            elif rec.weekday:
                rec.name = dict(rec._fields["weekday"].selection).get(rec.weekday, "")
            else:
                rec.name = "Mode terrasse"
