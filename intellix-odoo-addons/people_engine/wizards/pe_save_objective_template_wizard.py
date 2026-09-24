# -*- coding: utf-8 -*-
from odoo import fields, models
from odoo.exceptions import UserError


class PeSaveObjectiveTemplateWizard(models.TransientModel):
    _name = "pe.save.objective.template.wizard"
    _description = "Enregistrer comme modèle d'objectifs"

    name = fields.Char(string="Nom du modèle", required=True)
    description = fields.Text(string="Description")
    objective_ids = fields.Many2many(
        "pe.objective",
        string="Objectifs source",
        required=True,
    )

    def action_save_template(self):
        self.ensure_one()
        if not self.objective_ids:
            raise UserError("Sélectionnez au moins un objectif à enregistrer.")

        Template = self.env["pe.objective.template"]
        template = Template.create(
            {
                "name": self.name,
                "description": self.description,
            }
        )
        line_vals = []
        for seq, obj in enumerate(self.objective_ids, start=1):
            line_vals.append(
                {
                    "template_id": template.id,
                    "sequence": seq * 10,
                    "name": obj.name,
                    "objective_type": obj.objective_type,
                    "period": obj.period,
                    "target_value": obj.target_value,
                    "unit": obj.unit,
                }
            )
        self.env["pe.objective.template.line"].create(line_vals)

        return {
            "type": "ir.actions.act_window",
            "name": "Modèle d'objectifs",
            "res_model": "pe.objective.template",
            "view_mode": "form",
            "res_id": template.id,
            "target": "current",
        }
