# -*- coding: utf-8 -*-
from odoo import api, fields, models


class PeObjectiveTemplate(models.Model):
    _name = "pe.objective.template"
    _description = "Modèle d'objectifs"
    _order = "name"

    name = fields.Char(required=True, string="Nom du modèle")
    description = fields.Text(string="Description")
    active = fields.Boolean(default=True)
    line_ids = fields.One2many(
        "pe.objective.template.line",
        "template_id",
        string="Lignes d'objectifs",
        copy=True,
    )
    line_count = fields.Integer(compute="_compute_line_count")

    @api.depends("line_ids")
    def _compute_line_count(self):
        for rec in self:
            rec.line_count = len(rec.line_ids)

    def action_apply_to_contract(self):
        self.ensure_one()
        contract_id = self.env.context.get("default_contract_id")
        return {
            "type": "ir.actions.act_window",
            "name": "Appliquer le modèle d'objectifs",
            "res_model": "pe.apply.objective.template.wizard",
            "view_mode": "form",
            "target": "new",
            "context": {
                **self.env.context,
                "default_template_id": self.id,
                "default_contract_id": contract_id,
            },
        }


class PeObjectiveTemplateLine(models.Model):
    _name = "pe.objective.template.line"
    _description = "Ligne modèle d'objectif"
    _order = "sequence, id"

    template_id = fields.Many2one(
        "pe.objective.template",
        required=True,
        ondelete="cascade",
        index=True,
    )
    sequence = fields.Integer(default=10)
    name = fields.Char(required=True, string="Libellé")
    objective_type = fields.Selection(
        selection="_selection_objective_type",
        required=True,
        default="custom",
        string="Type de KPI",
    )
    period = fields.Selection(
        selection="_selection_period",
        string="Période",
        required=True,
        default="monthly",
    )
    target_value = fields.Float(string="Valeur cible")
    unit = fields.Char(string="Unité", help="%, MAD, nombre…")

    @api.model
    def _selection_objective_type(self):
        return self.env["pe.objective"]._objective_type_selection()

    @api.model
    def _selection_period(self):
        return self.env["pe.objective"]._period_selection()

    @api.onchange("objective_type")
    def _onchange_objective_type(self):
        defaults = self.env["pe.objective"]._default_unit_for_type(
            self.objective_type
        )
        if defaults and not self.unit:
            self.unit = defaults
        if not self.name and self.objective_type:
            label = dict(self._fields["objective_type"].selection).get(
                self.objective_type
            )
            if label:
                self.name = label
