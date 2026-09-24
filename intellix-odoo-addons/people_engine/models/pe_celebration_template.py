# -*- coding: utf-8 -*-
from odoo import api, fields, models
from odoo.exceptions import ValidationError


class PeCelebrationTemplate(models.Model):
    _name = "pe.celebration.template"
    _description = "Modèle de félicitation RH"
    _order = "occasion_type, lang, anniversary_years, name"

    OCCASION_TYPES = [
        ("birthday", "Anniversaire"),
        ("anniversary_1y", "Ancienneté — 1 an"),
        ("anniversary_3y", "Ancienneté — 3 ans"),
        ("anniversary_5y", "Ancienneté — 5 ans"),
        ("anniversary_10y", "Ancienneté — 10 ans et +"),
        ("anniversary_other", "Ancienneté — palier personnalisé"),
        ("performance", "Performance / objectif"),
        ("promotion", "Promotion"),
        ("custom", "Personnalisé / autre"),
        ("praise", "Félicitation libre"),
    ]

    name = fields.Char(required=True)
    occasion_type = fields.Selection(
        selection=OCCASION_TYPES,
        required=True,
        index=True,
    )
    lang = fields.Selection(
        [
            ("fr_FR", "Français (FR)"),
            ("fr_CA", "Français (CA)"),
            ("en_US", "English (US)"),
        ],
        default="fr_FR",
        required=True,
    )
    email_subject = fields.Char(string="Sujet e-mail", required=True)
    email_body = fields.Html(
        string="Corps e-mail",
        sanitize_attributes=False,
        required=True,
    )
    notification_message = fields.Text(
        string="Message notification",
        required=True,
        help="Message court affiché dans le flux d'activité Odoo.",
    )
    active = fields.Boolean(default=True)
    anniversary_years = fields.Integer(
        string="Années d'ancienneté",
        help="Uniquement pour le type « palier personnalisé » (ex: 2, 7, 15, 20).",
    )

    @api.constrains("occasion_type", "anniversary_years")
    def _check_anniversary_years(self):
        for rec in self:
            if rec.occasion_type == "anniversary_other" and not rec.anniversary_years:
                raise ValidationError(
                    "Les paliers personnalisés doivent préciser le nombre d'années."
                )
