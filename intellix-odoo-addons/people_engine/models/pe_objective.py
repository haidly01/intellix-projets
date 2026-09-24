# -*- coding: utf-8 -*-
from odoo import _, api, fields, models


class PeopleEngineObjective(models.Model):
    _name = "pe.objective"
    _description = "Objectif People Engine"
    _order = "date_deadline desc, id desc"

    PERIOD_SELECTION = [
        ("weekly", "Par semaine"),
        ("monthly", "Par mois"),
        ("quarterly", "Par trimestre"),
        ("yearly", "Par année"),
    ]

    OBJECTIVE_TYPE_SELECTION = [
        ("visites_terrain", "Nombre de visites terrain"),
        ("demos", "Nombre de démos"),
        ("appels", "Nombre d'appels"),
        ("taux_conversion_cycle", "Taux conversion cycle de vente"),
        ("taux_conversion", "Taux de conversion"),
        ("revenus", "Revenus générés"),
        ("crm_conversion", "Taux de conversion CRM"),
        ("crm_revenue", "Revenus générés (CRM)"),
        ("project_ontime", "Tâches livrées à temps"),
        ("ia_quality", "Score qualité appels IA"),
        ("ia_calls", "Volume appels IA"),
        ("leads_qualifies", "Leads qualifiés"),
        ("custom", "Objectif personnalisé"),
    ]

    profile_id = fields.Many2one(
        "pe.employee.profile", required=True, ondelete="cascade", index=True
    )
    contract_id = fields.Many2one(
        "pe.employment.contract",
        string="Contrat",
        ondelete="set null",
        index=True,
        help="Contrat auquel cet objectif mesurable est rattaché.",
    )
    coaching_plan_id = fields.Many2one(
        "pe.coaching.plan",
        string="Plan de coaching",
        ondelete="set null",
        index=True,
    )
    employee_id = fields.Many2one(related="profile_id.employee_id", store=True)
    name = fields.Char(required=True)
    description = fields.Text()
    objective_type = fields.Selection(
        selection=OBJECTIVE_TYPE_SELECTION,
        required=True,
        default="custom",
    )
    period = fields.Selection(
        selection=PERIOD_SELECTION,
        string="Période",
        required=True,
        default="monthly",
    )
    target_value = fields.Float()
    current_value = fields.Float(
        compute="_compute_current_value",
        inverse="_inverse_current_value",
        store=True,
        readonly=False,
    )
    unit = fields.Char(help="%, MAD, tâches, appels…")
    date_start = fields.Date()
    date_deadline = fields.Date()
    status = fields.Selection(
        [
            ("draft", "Brouillon"),
            ("active", "En cours"),
            ("achieved", "Atteint"),
            ("missed", "Non atteint"),
            ("cancelled", "Annulé"),
        ],
        default="draft",
    )
    achievement_rate = fields.Float(
        compute="_compute_achievement", store=True, string="Taux d'atteinte (%)"
    )
    weight = fields.Float(default=1.0, help="Poids relatif dans le score objectifs")
    manager_id = fields.Many2one("hr.employee", string="Gestionnaire")
    manager_approved = fields.Boolean(default=False)
    is_contractual = fields.Boolean(
        compute="_compute_is_contractual",
        store=True,
        string="Contractuel",
    )

    @api.model
    def _objective_type_selection(self):
        return list(self.OBJECTIVE_TYPE_SELECTION)

    @api.model
    def _period_selection(self):
        return list(self.PERIOD_SELECTION)

    @api.model
    def _default_unit_for_type(self, objective_type):
        units = {
            "visites_terrain": "visites",
            "demos": "démos",
            "appels": "appels",
            "ia_calls": "appels",
            "taux_conversion_cycle": "%",
            "taux_conversion": "%",
            "crm_conversion": "%",
            "revenus": "MAD",
            "crm_revenue": "MAD",
            "project_ontime": "%",
            "ia_quality": "/10",
        }
        return units.get(objective_type, "")

    @api.onchange("objective_type")
    def _onchange_objective_type(self):
        if self.objective_type and not self.unit:
            self.unit = self._default_unit_for_type(self.objective_type)
        if self.objective_type and self.objective_type != "custom" and not self.name:
            label = dict(self.OBJECTIVE_TYPE_SELECTION).get(self.objective_type)
            if label:
                self.name = label

    @api.depends("contract_id")
    def _compute_is_contractual(self):
        for obj in self:
            obj.is_contractual = bool(obj.contract_id)

    @api.depends(
        "objective_type",
        "profile_id.crm_conversion_rate",
        "profile_id.crm_revenue_generated",
        "profile_id.project_ontime_rate",
        "profile_id.ia_avg_quality_score",
        "profile_id.ia_calls_made",
        "profile_id.ia_conversion_rate",
        "profile_id.visites_terrain_count",
        "profile_id.demos_count",
    )
    def _compute_current_value(self):
        mapping = {
            "crm_conversion": "crm_conversion_rate",
            "taux_conversion": "crm_conversion_rate",
            "taux_conversion_cycle": "ia_conversion_rate",
            "crm_revenue": "crm_revenue_generated",
            "revenus": "crm_revenue_generated",
            "project_ontime": "project_ontime_rate",
            "ia_quality": "ia_avg_quality_score",
            "ia_calls": "ia_calls_made",
            "appels": "ia_calls_made",
            "visites_terrain": "visites_terrain_count",
            "demos": "demos_count",
        }
        manual_types = {"custom"}
        for obj in self:
            if obj.objective_type in manual_types:
                continue
            field_name = mapping.get(obj.objective_type)
            obj.current_value = (
                getattr(obj.profile_id, field_name, 0.0) if field_name else 0.0
            )

    def _inverse_current_value(self):
        manual_types = {
            "custom",
            "visites_terrain",
            "demos",
        }
        profile_fields = {
            "visites_terrain": "visites_terrain_count",
            "demos": "demos_count",
        }
        for obj in self:
            if obj.objective_type not in manual_types:
                continue
            field_name = profile_fields.get(obj.objective_type)
            if field_name and obj.profile_id:
                obj.profile_id.sudo().write({field_name: int(obj.current_value or 0)})

    @api.depends("current_value", "target_value")
    def _compute_achievement(self):
        for obj in self:
            if obj.target_value:
                obj.achievement_rate = min(
                    (obj.current_value / obj.target_value) * 100.0, 999.0
                )
            else:
                obj.achievement_rate = 0.0

    _SCORE_TRIGGER_FIELDS = {
        "target_value",
        "weight",
        "status",
        "objective_type",
        "current_value",
    }

    def _trigger_profile_score_recalc(self):
        profiles = self.mapped("profile_id").filtered(
            lambda p: p.id and p.pe_status != "inactive"
        )
        if profiles:
            profiles.with_context(pe_skip_score_recalc=False).action_calculate_score(
                calculated_by="auto"
            )

    @api.model_create_multi
    def create(self, vals_list):
        Profile = self.env["pe.employee.profile"]
        for vals in vals_list:
            if vals.get("contract_id") and not vals.get("profile_id"):
                contract = self.env["pe.employment.contract"].browse(
                    vals["contract_id"]
                )
                if contract.profile_id:
                    vals["profile_id"] = contract.profile_id.id
                elif contract.employee_id:
                    profile = Profile.search(
                        [("employee_id", "=", contract.employee_id.id)], limit=1
                    )
                    if profile:
                        vals["profile_id"] = profile.id
            if vals.get("objective_type") and not vals.get("unit"):
                vals["unit"] = self._default_unit_for_type(vals["objective_type"])
        records = super().create(vals_list)
        if not self.env.context.get("pe_skip_score_recalc"):
            records._trigger_profile_score_recalc()
        return records

    def write(self, vals):
        res = super().write(vals)
        if not self.env.context.get("pe_skip_score_recalc") and (
            self._SCORE_TRIGGER_FIELDS & set(vals.keys())
        ):
            self._trigger_profile_score_recalc()
        return res

    def unlink(self):
        profiles = self.mapped("profile_id")
        res = super().unlink()
        if not self.env.context.get("pe_skip_score_recalc"):
            profiles.filtered(lambda p: p.pe_status != "inactive").action_calculate_score(
                calculated_by="auto"
            )
        return res

    def action_activate(self):
        self.write({"status": "active"})

    def action_mark_achieved(self):
        for obj in self:
            rate = obj.achievement_rate
            status = "achieved" if rate >= 100 else "missed"
            obj.write({"status": status})

    def action_save_as_template(self):
        self.ensure_one()
        objectives = self
        if len(self) > 1:
            objectives = self
        return {
            "type": "ir.actions.act_window",
            "name": _("Enregistrer comme modèle"),
            "res_model": "pe.save.objective.template.wizard",
            "view_mode": "form",
            "target": "new",
            "context": {
                "default_objective_ids": [(6, 0, objectives.ids)],
                "default_name": objectives[0].name if len(objectives) == 1 else "",
            },
        }
