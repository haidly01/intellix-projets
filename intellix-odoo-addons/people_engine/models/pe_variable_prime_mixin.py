# -*- coding: utf-8 -*-
from odoo import api, fields, models


class PeVariablePrimeMixin(models.AbstractModel):
    _name = "pe.variable.prime.mixin"
    _description = "Lien modèle de prime variable / personnalisation"

    variable_prime_template_id = fields.Many2one(
        "pe.prime.template",
        string="Modèle de prime variable",
        ondelete="set null",
        domain="[('active', '=', True)]",
        help="Modèle réutilisable reliant la part variable aux objectifs KPI. "
        "Laisser vide pour une règle entièrement personnalisée.",
    )
    variable_prime_customize = fields.Boolean(
        string="Personnaliser",
        default=False,
        help="Active l'édition manuelle des montants et taux même lorsqu'un modèle est sélectionné.",
    )

    def _variable_prime_template_values(self):
        template = self.variable_prime_template_id
        if not template:
            return {}
        return {
            "montant_variable": template.montant_variable,
            "taux_commission": template.taux_commission,
            "description_variable": template.description_variable,
        }

    def _apply_variable_prime_from_template(self):
        values = self._variable_prime_template_values()
        if not values:
            return
        self.with_context(pe_skip_variable_prime_apply=True).write(values)

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        records.filtered(
            lambda r: r.variable_prime_template_id and not r.variable_prime_customize
        )._apply_variable_prime_from_template()
        return records

    def write(self, vals):
        res = super().write(vals)
        if self.env.context.get("pe_skip_variable_prime_apply"):
            return res
        trigger_fields = {"variable_prime_template_id", "variable_prime_customize"}
        if trigger_fields.intersection(vals):
            self.filtered(
                lambda r: r.variable_prime_template_id and not r.variable_prime_customize
            )._apply_variable_prime_from_template()
        return res

    @api.onchange("variable_prime_template_id")
    def _onchange_variable_prime_template_id(self):
        if self.variable_prime_template_id:
            self.variable_prime_customize = False
            values = self._variable_prime_template_values()
            if values:
                self.update(values)

    @api.onchange("variable_prime_customize")
    def _onchange_variable_prime_customize(self):
        if not self.variable_prime_customize and self.variable_prime_template_id:
            values = self._variable_prime_template_values()
            if values:
                self.update(values)
