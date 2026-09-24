# -*- coding: utf-8 -*-
from odoo import api, fields, models


class PeDisciplinaryLetter(models.Model):
    _name = "pe.disciplinary.letter"
    _description = "Lettre disciplinaire RH"
    _inherit = ["mail.thread"]
    _order = "date_lettre desc, id desc"

    name = fields.Char(
        string="Référence",
        required=True,
        copy=False,
        default=lambda self: self.env["ir.sequence"].next_by_code("pe.disciplinary.letter")
        or "LETTRE",
    )
    procedure_id = fields.Many2one(
        "pe.disciplinary.procedure",
        required=True,
        ondelete="cascade",
        index=True,
    )
    employee_id = fields.Many2one(
        related="procedure_id.employee_id",
        store=True,
    )
    type_lettre = fields.Selection(
        [
            ("convocation", "Convocation entretien préalable"),
            ("avertissement_verbal", "Avertissement verbal"),
            ("avertissement_ecrit", "Avertissement écrit"),
            ("mise_en_demeure", "Mise en demeure"),
            ("mise_a_pied", "Notification mise à pied"),
            ("licenciement", "Notification licenciement"),
            ("solde_tout_compte", "Solde de tout compte"),
        ],
        required=True,
    )
    date_lettre = fields.Date(default=fields.Date.context_today, required=True)
    legal_article_id = fields.Many2one("pe.legal.article", string="Modèle juridique")
    content_html = fields.Html(string="Contenu", sanitize_attributes=False)
    state = fields.Selection(
        [
            ("draft", "Brouillon"),
            ("generated", "Générée"),
            ("sent", "Envoyée"),
            ("signed", "Signée"),
        ],
        default="draft",
    )
    signed_date = fields.Date(string="Date signature employé")
    attachment_id = fields.Many2one("ir.attachment", string="PDF", readonly=True)
    impact_paie_preview = fields.Float(string="Aperçu impact paie")
    company_id = fields.Many2one(related="procedure_id.company_id", store=True)

    def action_print_letter(self):
        self.ensure_one()
        return self.env.ref(
            "people_engine.action_report_pe_disciplinary_letter"
        ).report_action(self)

    def action_mark_sent(self):
        self.write({"state": "sent"})

    def action_mark_signed(self):
        self.write({"state": "signed", "signed_date": fields.Date.today()})
