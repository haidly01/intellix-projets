# -*- coding: utf-8 -*-
from odoo import fields, models


class PeopleEngineLegalTag(models.Model):
    _name = "pe.legal.tag"
    _description = "Mot-clé article juridique"
    _order = "name"

    name = fields.Char(required=True)
    color = fields.Integer(default=0)


class PeopleEngineLegalArticle(models.Model):
    _name = "pe.legal.article"
    _description = "Article droit du travail"
    _rec_name = "code"
    _order = "jurisdiction_id, code"

    jurisdiction_id = fields.Many2one(
        "pe.legal.jurisdiction", required=True, ondelete="cascade", index=True
    )
    code = fields.Char(required=True, index=True)
    title = fields.Char(required=True)
    content = fields.Text(required=True)
    plain_language = fields.Text(string="Explication en langage clair")
    category = fields.Selection(
        [
            ("dismissal", "Congédiement et mise à pied"),
            ("discipline", "Mesures disciplinaires"),
            ("harassment", "Harcèlement et discrimination"),
            ("leave", "Congés et absences"),
            ("compensation", "Rémunération et avantages"),
            ("hours", "Heures de travail"),
            ("privacy", "Vie privée et surveillance"),
            ("notice", "Délais de congé"),
            ("probation", "Période de probation"),
            ("unionized", "Travail syndiqué"),
            ("health_safety", "Santé et sécurité"),
            ("non_compete", "Non-concurrence"),
            ("general", "Général"),
        ],
        required=True,
        default="general",
    )
    applicable_action_ids = fields.Many2many(
        "pe.action.type",
        "pe_legal_article_action_rel",
        "article_id",
        "action_id",
        string="Actions RH concernées",
    )
    jurisprudence_notes = fields.Text(string="Jurisprudence notable")
    employer_obligations = fields.Text(string="Obligations de l'employeur")
    employee_rights = fields.Text(string="Droits de l'employé")
    penalties = fields.Text(string="Sanctions potentielles")
    last_updated = fields.Date()
    is_current = fields.Boolean(default=True)
    source_url = fields.Char(string="Source officielle (URL)")
    tag_ids = fields.Many2many("pe.legal.tag", string="Mots-clés")

    def name_get(self):
        return [
            (r.id, "[%s] %s" % (r.code, r.title) if r.code else r.title)
            for r in self
        ]
