# -*- coding: utf-8 -*-
from odoo import _, api, fields, models
from odoo.exceptions import UserError


class PeInviteCollaborator(models.TransientModel):
    _name = "pe.invite.collaborator"
    _description = "Inviter un collaborateur People Engine"

    name = fields.Char(string="Nom complet", required=True)
    email = fields.Char(string="E-mail / identifiant", required=True)
    company_id = fields.Many2one(
        "res.company",
        string="Organisation",
        required=True,
        default=lambda self: self.env.company,
    )
    department_id = fields.Many2one("hr.department", string="Département")
    job_id = fields.Many2one("hr.job", string="Poste")
    manager_id = fields.Many2one("hr.employee", string="Manager")
    doorway_segment = fields.Selection(
        [
            ("b2b", "B2B — Marketing / Driven / Doorway Clients"),
            ("b2c", "B2C — Rénovation / Assurance / Immobilier"),
        ],
        string="Segment Doorway",
        default="b2b",
        required=True,
    )
    pe_access = fields.Selection(
        [
            ("employee", "Employé"),
            ("manager", "Gestionnaire"),
            ("hr", "RH"),
            ("admin", "Administrateur PE"), ("freelance", "Freelance"),
        ],
        string="Niveau People Engine",
        default="employee",
        required=True,
    )
    send_invitation = fields.Boolean(
        string="Envoyer l'invitation par e-mail",
        default=True,
    )

    @api.constrains("email")
    def _check_email_unique(self):
        for wiz in self:
            login = (wiz.email or "").strip().lower()
            if not login:
                continue
            if self.env["res.users"].sudo().search_count(
                [("login", "=ilike", login)]
            ):
                raise UserError(
                    _("Un utilisateur avec l'identifiant « %s » existe déjà.")
                    % wiz.email
                )

    def _pe_group_commands(self):
        self.ensure_one()
        pe = {
            "employee": self.env.ref("people_engine.group_employee", raise_if_not_found=False),
            "manager": self.env.ref("people_engine.group_manager", raise_if_not_found=False),
            "hr": self.env.ref("people_engine.group_hr", raise_if_not_found=False),
            "admin": self.env.ref("people_engine.group_admin", raise_if_not_found=False),
        }
        wanted = set()
        if self.pe_access == "admin" and pe["admin"]:
            wanted = {g for g in pe.values() if g}
        elif self.pe_access == "hr" and pe["hr"]:
            wanted = {pe["employee"], pe["manager"], pe["hr"]} - {None}
        elif self.pe_access == "manager" and pe["manager"]:
            wanted = {pe["employee"], pe["manager"]} - {None}
        elif pe["employee"]:
            wanted = {pe["employee"]}
        base_user = self.env.ref("base.group_user")
        return [(4, g.id) for g in wanted | {base_user}]

    def action_invite(self):
        self.ensure_one()
        login = (self.email or "").strip().lower()
        if not login:
            raise UserError(_("L'e-mail est obligatoire."))

        partner = self.env["res.partner"].sudo().create(
            {
                "name": self.name,
                "email": login,
                "company_id": self.company_id.id,
            }
        )
        user = self.env["res.users"].sudo().create(
            {
                "name": self.name,
                "login": login,
                "email": login,
                "partner_id": partner.id,
                "company_id": self.company_id.id,
                "company_ids": [(6, 0, [self.company_id.id])],
                "group_ids": self._pe_group_commands(),
            }
        )
        employee = self.env["hr.employee"].sudo().create(
            {
                "name": self.name,
                "user_id": user.id,
                "company_id": self.company_id.id,
                "department_id": self.department_id.id,
                "job_id": self.job_id.id,
                "parent_id": self.manager_id.id,
                "work_contact_id": partner.id,
            }
        )
        profile = self.env["pe.employee.profile"].sudo().search(
            [("employee_id", "=", employee.id)], limit=1
        )
        if not profile:
            arrival_stage = self.env.ref(
                "people_engine.lifecycle_stage_arrival",
                raise_if_not_found=False,
            )
            profile_vals = {"employee_id": employee.id}
            if arrival_stage:
                profile_vals["lifecycle_stage_id"] = arrival_stage.id
            profile = self.env["pe.employee.profile"].sudo().create(profile_vals)
        elif not profile.lifecycle_stage_id:
            arrival_stage = self.env.ref(
                "people_engine.lifecycle_stage_arrival",
                raise_if_not_found=False,
            )
            if arrival_stage:
                profile.sudo().lifecycle_stage_id = arrival_stage

        user._sync_people_engine_role_groups()

        if self.send_invitation:
            user.action_reset_password()

        return {
            "type": "ir.actions.act_window",
            "name": profile.display_name,
            "res_model": "pe.employee.profile",
            "res_id": profile.id,
            "view_mode": "form",
            "target": "current",
            "context": {
                "allowed_company_ids": list(
                    set(self.env.user.company_ids.ids) | {self.company_id.id}
                ),
            },
        }
