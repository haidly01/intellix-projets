# -*- coding: utf-8 -*-
from odoo import fields, models


class PeDisciplinarySanctionWizard(models.TransientModel):
    _name = "pe.disciplinary.sanction.wizard"
    _description = "Appliquer sanction disciplinaire"

    procedure_id = fields.Many2one("pe.disciplinary.procedure", required=True)
    type_sanction = fields.Selection(
        related="procedure_id.type_sanction",
        readonly=True,
    )
    generate_letter = fields.Boolean(string="Générer lettre", default=True)
    letter_type = fields.Selection(
        [
            ("convocation", "Convocation"),
            ("avertissement_ecrit", "Avertissement écrit"),
            ("avertissement_verbal", "Avertissement verbal"),
            ("mise_en_demeure", "Mise en demeure"),
            ("mise_a_pied", "Mise à pied"),
            ("licenciement", "Licenciement"),
        ],
        string="Type de lettre",
    )
    apply_payroll = fields.Boolean(string="Appliquer impact paie")
    jours_mise_a_pied = fields.Integer(related="procedure_id.jours_mise_a_pied", readonly=False)
    heures_deduction = fields.Float(related="procedure_id.heures_deduction", readonly=False)

    def action_apply(self):
        self.ensure_one()
        proc = self.procedure_id
        self.env["pe.disciplinary.service"].sudo().enforce_human_validation(
            proc.type_sanction, "appliquer la sanction"
        )
        proc.write(
            {
                "jours_mise_a_pied": self.jours_mise_a_pied,
                "heures_deduction": self.heures_deduction,
                "impact_paie": self.apply_payroll or proc.impact_paie,
                "statut": "sanction",
                "date_sanction": fields.Date.today(),
            }
        )
        svc = self.env["pe.disciplinary.service"].sudo()
        letter_type = self.letter_type
        if not letter_type:
            mapping = {
                "avertissement_verbal": "avertissement_verbal",
                "avertissement_ecrit": "avertissement_ecrit",
                "mise_en_demeure": "mise_en_demeure",
                "mise_a_pied": "mise_a_pied",
                "licenciement_faute_grave": "licenciement",
                "licenciement_insuffisance": "licenciement",
            }
            letter_type = mapping.get(proc.type_sanction, "avertissement_ecrit")
        if self.generate_letter:
            svc.generate_letter(proc, letter_type)
        if self.apply_payroll and proc.impact_paie:
            svc.appliquer_impact_paie(proc)
        return {
            "type": "ir.actions.act_window",
            "res_model": "pe.disciplinary.procedure",
            "res_id": proc.id,
            "view_mode": "form",
        }
