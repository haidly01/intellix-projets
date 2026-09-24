# -*- coding: utf-8 -*-

from odoo import fields, models

EVENT_KINDS = [
    ("privatisation_weekend", "Privatisation weekend"),
    ("mariage", "Mariage"),
    ("retraite_corpo", "Retraite corporative"),
    ("celebration", "Célébration"),
    ("anniversaire", "Anniversaire"),
    ("excursion", "Excursion"),
    ("other", "Autre"),
]

CHECKLIST_KINDS = [
    ("privatisation_weekend", "Privatisation weekend"),
    ("mariage", "Mariage"),
    ("retraite_corpo", "Retraite corporative"),
    ("celebration", "Célébration"),
    ("none", "Aucun modèle"),
]

TEMPLATE_XMLIDS = {
    "privatisation_weekend": "intellix_riad.event_template_privatisation_weekend",
    "mariage": "intellix_riad.event_template_mariage",
    "retraite_corpo": "intellix_riad.event_template_retraite",
    "celebration": "intellix_riad.event_template_celebration",
}


class IntellixRiadEventTemplate(models.Model):
    _name = "intellix.riad.event.template"
    _description = "Modèle de checklist événement"
    _order = "name"

    name = fields.Char(required=True)
    event_kind = fields.Selection(EVENT_KINDS, string="Type d'événement", required=True)
    active = fields.Boolean(default=True)
    line_ids = fields.One2many(
        "intellix.riad.event.template.line",
        "template_id",
        string="Tâches",
    )


class IntellixRiadEventTemplateLine(models.Model):
    _name = "intellix.riad.event.template.line"
    _description = "Ligne de modèle de checklist"
    _order = "sequence, id"

    template_id = fields.Many2one(
        "intellix.riad.event.template",
        required=True,
        ondelete="cascade",
    )
    sequence = fields.Integer(default=10)
    name = fields.Char(string="Tâche", required=True)
    offset_days = fields.Integer(
        string="Échéance (jours avant le début)",
        default=0,
        help="0 = jour J. 1 = la veille. Négatif = après le début.",
    )
