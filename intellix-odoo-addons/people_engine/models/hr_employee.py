# -*- coding: utf-8 -*-
from odoo import _, api, fields, models
from odoo.exceptions import AccessError


class HrEmployee(models.Model):
    _inherit = "hr.employee"

    pe_profile_ids = fields.One2many(
        "pe.employee.profile",
        "employee_id",
        string="Profils People Engine",
    )
    pe_profile_id = fields.Many2one(
        "pe.employee.profile",
        string="Profil People Engine",
        compute="_compute_pe_profile",
        store=True,
        index=True,
    )
    pe_profile_count = fields.Integer(
        compute="_compute_pe_profile",
        store=True,
    )
    celebration_opt_out = fields.Boolean(
        string="Exclure des félicitations publiques",
        help="Retire l'employé des annonces d'équipe (anniversaire, ancienneté, etc.).",
        tracking=True,
    )
    last_performance_milestone = fields.Date(
        string="Dernière performance célébrée",
        help="Date de l'objectif atteint à diffuser à l'équipe.",
        tracking=True,
    )
    last_performance_detail = fields.Text(
        string="Détail performance",
        help="Texte injecté dans {{detail}} pour les félicitations performance.",
    )
    last_promotion_date = fields.Date(
        string="Date de promotion",
        help="Alimentée automatiquement lors d'un changement de poste.",
        tracking=True,
    )
    people_score = fields.Float(
        string="Score People Engine",
        compute="_compute_people_dashboard_fields",
        store=True,
    )
    people_score_trend = fields.Selection(
        [
            ("up", "En hausse"),
            ("down", "En baisse"),
            ("stable", "Stable"),
        ],
        string="Tendance score",
        compute="_compute_people_dashboard_fields",
        store=True,
    )
    people_alerts_count = fields.Integer(
        string="Alertes ouvertes",
        compute="_compute_people_dashboard_fields",
        store=True,
    )
    people_band = fields.Selection(
        [
            ("watch", "À surveiller"),
            ("growing", "En progression"),
            ("top", "Performant"),
        ],
        string="Bande score",
        compute="_compute_people_dashboard_fields",
        store=True,
    )

    @api.depends(
        "pe_profile_id",
        "pe_profile_id.score_global",
        "pe_profile_id.score_trend",
    )
    def _compute_people_dashboard_fields(self):
        Alert = self.env["pe.supervisor.alert"].sudo()
        for emp in self:
            profile = emp.pe_profile_id
            score = profile.score_global if profile else 0.0
            emp.people_score = score
            trend_map = {
                "up": "up",
                "down": "down",
                "stable": "stable",
            }
            emp.people_score_trend = trend_map.get(
                profile.score_trend if profile else "stable", "stable"
            )
            emp.people_alerts_count = Alert.search_count(
                [
                    ("employee_id", "=", emp.id),
                    ("state", "=", "active"),
                ]
            ) if emp.id else 0
            if score < 60:
                emp.people_band = "watch"
            elif score < 80:
                emp.people_band = "growing"
            else:
                emp.people_band = "top"

    @api.depends("pe_profile_ids")
    def _compute_pe_profile(self):
        for emp in self:
            profile = emp.pe_profile_ids[:1]
            emp.pe_profile_id = profile.id if profile else False
            emp.pe_profile_count = len(emp.pe_profile_ids)

    def _expanded_company_ids(self, records=None):
        """Union sociétés actives, sociétés utilisateur et société des fiches."""
        recs = records or self
        cids = set(self.env.user.company_ids.ids) | set(self.env.companies.ids)
        if recs:
            cids |= set(recs.sudo().mapped("company_id").ids)
        return list(cids)

    @api.model
    def pe_resolve_user_employee(self, user=None):
        """Retourne la fiche hr.employee liée à l'utilisateur courant.

        Odoo filtre ``user.employee_id`` sur la société active ; si l'employé
        est rattaché à une autre société autorisée (ex. Doorway SARL vs Agence
        Doorway Inc.), le hub RH renvoyait ``no_employee``.
        """
        user = user or self.env.user
        employee = user.employee_id
        if employee:
            return employee
        return self.sudo().search(
            [("user_id", "=", user.id), ("active", "=", True)],
            limit=1,
        )

    def _env_multi_company(self, records=None):
        return self.env(context=dict(
            self.env.context,
            allowed_company_ids=self._expanded_company_ids(records),
        ))

    def _action_company_context(self, action):
        """Inclut la société de l'employé pour éviter les boucles multi-sociétés."""
        self.ensure_one()
        company_id = self.sudo().company_id.id
        if not company_id:
            return action
        ctx = dict(action.get("context") or {})
        cids = self._expanded_company_ids(self)
        ctx["allowed_company_ids"] = cids
        action["context"] = ctx
        return action

    def _should_open_pe_profile(self):
        self.ensure_one()
        if self.env.context.get("force_hr_employee_form"):
            return False
        if self.env.context.get("open_technical_hr_form"):
            return False
        if self.env.user.has_group("base.group_system"):
            return False
        if not self.env["pe.employee.profile"].sudo().search_count(
            [("employee_id", "=", self.id)]
        ):
            return False
        return (
            self.env.user.has_group("people_engine.group_employee")
            or self.env.user.has_group("people_engine.group_manager")
            or self.env.user.has_group("people_engine.group_hr")
        )

    def get_formview_action(self, access_uid=None):
        self.ensure_one()
        if self._should_open_pe_profile():
            profile = self.env["pe.employee.profile"].sudo().search(
                [("employee_id", "=", self.id)], limit=1
            )
            return profile.get_formview_action(access_uid=access_uid)
        action = super().get_formview_action(access_uid=access_uid)
        return self._action_company_context(action)

    def _with_hr_company_access(self):
        if not (
            self.env.user.has_group("base.group_system")
            or self.env.user.has_group("hr.group_hr_user")
            or self.env.user.has_group("people_engine.group_hr")
            or self.env.user.has_group("people_engine.group_manager")
        ):
            return self
        return self.with_context(
            allowed_company_ids=self._expanded_company_ids(self),
        )

    def read(self, fields=None, load="_classic_read"):
        return super(HrEmployee, self._with_hr_company_access()).read(
            fields, load
        )

    def web_read(self, specification):
        return super(HrEmployee, self._with_hr_company_access()).web_read(
            specification
        )

    def _fix_work_address(self):
        for emp in self:
            if not emp.work_contact_id:
                continue
            company_partner = emp.company_id.partner_id
            if (
                emp.address_id
                and emp.address_id != company_partner
                and emp.address_id == emp.work_contact_id
            ):
                continue
            if not emp.address_id or emp.address_id == company_partner:
                emp.write({"address_id": emp.work_contact_id.id})

    def _ensure_pe_profile(self):
        Profile = self.env["pe.employee.profile"]
        for emp in self:
            if Profile.search_count([("employee_id", "=", emp.id)]):
                continue
            user = emp.user_id
            if user and user.doorway_segment == "b2c":
                continue
            Profile.create({"employee_id": emp.id})

    def _sync_user_company(self):
        for emp in self.filtered("user_id"):
            user = emp.user_id
            company = emp.company_id
            if not company:
                continue
            vals = {}
            if user.company_id != company:
                vals["company_id"] = company.id
            company_ids = set(user.company_ids.ids)
            company_ids.add(company.id)
            if company_ids != set(user.company_ids.ids):
                vals["company_ids"] = [(6, 0, list(company_ids))]
            if vals:
                user.sudo().write(vals)

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if not vals.get("company_id") and vals.get("user_id"):
                user = self.env["res.users"].browse(vals["user_id"])
                if user.company_id:
                    vals["company_id"] = user.company_id.id
        employees = super().create(vals_list)
        employees._fix_work_address()
        employees._ensure_pe_profile()
        employees._sync_user_company()
        return employees

    def write(self, vals):
        track_promotion = "job_id" in vals
        old_jobs = {}
        if track_promotion:
            for emp in self:
                old_jobs[emp.id] = emp.job_id.id
        res = super().write(vals)
        if track_promotion:
            today = fields.Date.context_today(self)
            for emp in self:
                if old_jobs.get(emp.id) and emp.job_id and emp.job_id.id != old_jobs[emp.id]:
                    emp.sudo().write({"last_promotion_date": today})
        if {"work_contact_id", "company_id", "address_id"} & set(vals):
            self._fix_work_address()
        if "user_id" in vals:
            self._ensure_pe_profile()
        if "company_id" in vals:
            self._sync_user_company()
        return res

    def action_open_pe_profile(self):
        self.ensure_one()
        Profile = self.env["pe.employee.profile"].sudo()
        profile = Profile.search([("employee_id", "=", self.id)], limit=1)
        if not profile:
            profile = Profile.create({"employee_id": self.id})
        action = {
            "type": "ir.actions.act_window",
            "name": profile.display_name or self.name,
            "res_model": "pe.employee.profile",
            "res_id": profile.id,
            "view_mode": "form",
            "target": "current",
        }
        ctx = dict(action.get("context") or {})
        ctx["allowed_company_ids"] = self._expanded_company_ids(self)
        action["context"] = ctx
        return action

    @api.model
    def action_admin_all_employees(self):
        """Super admin : accès employés Odoo toutes organisations."""
        if not self.env.user.has_group("base.group_system"):
            raise AccessError(
                _("Réservé aux administrateurs système Odoo.")
            )
        companies = self.env["res.company"].sudo().search([])
        action = self.env["ir.actions.actions"]._for_xml_id(
            "hr.open_view_employee_list_my"
        )
        action["name"] = _("Employés — toutes organisations")
        action["domain"] = []
        ctx = action.get("context") or {}
        if not isinstance(ctx, dict):
            ctx = {}
        ctx["allowed_company_ids"] = companies.ids
        ctx["open_technical_hr_form"] = True
        ctx.pop("searchpanel_default_company_id", None)
        action["context"] = ctx
        return action

    def action_open_safe(self):
        """Ouvre le profil PE (recommandé) ou la fiche RH selon les droits."""
        self.ensure_one()
        if self.env.user.has_group("hr.group_hr_user"):
            return self._action_company_context(
                {
                    "type": "ir.actions.act_window",
                    "res_model": "hr.employee",
                    "res_id": self.id,
                    "view_mode": "form",
                    "target": "current",
                }
            )
        if self.env.user.has_group("people_engine.group_employee"):
            return self.action_open_pe_profile()
        return self.env["hr.employee.public"].browse(self.id).get_formview_action()
