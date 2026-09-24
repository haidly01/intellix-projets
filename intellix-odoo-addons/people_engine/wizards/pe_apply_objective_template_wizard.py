# -*- coding: utf-8 -*-
from odoo import api, fields, models
from odoo.exceptions import UserError


class PeApplyObjectiveTemplateWizard(models.TransientModel):
    _name = "pe.apply.objective.template.wizard"
    _description = "Appliquer un modèle d'objectifs"

    template_id = fields.Many2one(
        "pe.objective.template",
        string="Modèle",
        required=True,
        domain=[("active", "=", True)],
    )
    contract_id = fields.Many2one("pe.employment.contract", string="Contrat")
    profile_id = fields.Many2one("pe.employee.profile", string="Profil employé")
    target = fields.Selection(
        [
            ("contract", "Objectifs contractuels (contrat)"),
            ("profile", "Suivi opérationnel (profil)"),
            ("both", "Contrat + profil"),
        ],
        string="Appliquer sur",
        required=True,
        default="contract",
    )
    replace_existing = fields.Boolean(
        string="Remplacer les objectifs existants",
        help="Supprime les objectifs existants sur la cible avant d'appliquer le modèle.",
    )
    activate = fields.Boolean(
        string="Activer immédiatement",
        default=True,
        help="Passe les objectifs créés au statut « En cours ».",
    )

    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        contract_id = res.get("contract_id") or self.env.context.get(
            "default_contract_id"
        )
        profile_id = res.get("profile_id") or self.env.context.get(
            "default_profile_id"
        )
        if contract_id and not profile_id:
            contract = self.env["pe.employment.contract"].browse(contract_id)
            if contract.profile_id:
                res["profile_id"] = contract.profile_id.id
        if profile_id and not contract_id:
            res.setdefault("target", "profile")
        elif contract_id:
            res.setdefault("target", "contract")
        return res

    @api.onchange("contract_id")
    def _onchange_contract_id(self):
        if self.contract_id and self.contract_id.profile_id:
            self.profile_id = self.contract_id.profile_id

    def action_apply(self):
        self.ensure_one()
        if not self.template_id.line_ids:
            raise UserError("Le modèle sélectionné ne contient aucune ligne d'objectif.")

        Objective = self.env["pe.objective"]
        created = Objective

        if self.target in ("contract", "both"):
            if not self.contract_id:
                raise UserError("Sélectionnez un contrat pour les objectifs contractuels.")
            if not self.profile_id and self.contract_id.profile_id:
                self.profile_id = self.contract_id.profile_id
            if not self.profile_id:
                raise UserError(
                    "Aucun profil People Engine lié à ce contrat. Créez d'abord le profil employé."
                )
            if self.replace_existing:
                existing = Objective.search(
                    [("contract_id", "=", self.contract_id.id)]
                )
                existing.unlink()
            created = self._create_from_template(
                contract_id=self.contract_id.id,
                profile_id=self.profile_id.id,
            )

        if self.target in ("profile", "both"):
            if not self.profile_id:
                raise UserError("Sélectionnez un profil pour le suivi opérationnel.")
            if self.replace_existing and self.target == "profile":
                existing = Objective.search(
                    [
                        ("profile_id", "=", self.profile_id.id),
                        ("contract_id", "=", False),
                    ]
                )
                existing.unlink()
            elif self.replace_existing and self.target == "both":
                existing = Objective.search(
                    [
                        ("profile_id", "=", self.profile_id.id),
                        ("contract_id", "=", False),
                    ]
                )
                existing.unlink()
            profile_created = self._create_from_template(
                contract_id=False,
                profile_id=self.profile_id.id,
            )
            created = profile_created if created == Objective else created | profile_created

        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": "Modèle appliqué",
                "message": "%s objectif(s) créé(s)." % len(created),
                "type": "success",
                "sticky": False,
                "next": {"type": "ir.actions.act_window_close"},
            },
        }

    def _create_from_template(self, contract_id, profile_id):
        Objective = self.env["pe.objective"]
        status = "active" if self.activate else "draft"
        vals_list = []
        for line in self.template_id.line_ids:
            vals_list.append(
                {
                    "name": line.name,
                    "objective_type": line.objective_type,
                    "period": line.period,
                    "target_value": line.target_value,
                    "unit": line.unit,
                    "profile_id": profile_id,
                    "contract_id": contract_id or False,
                    "status": status,
                }
            )
        return Objective.create(vals_list)
