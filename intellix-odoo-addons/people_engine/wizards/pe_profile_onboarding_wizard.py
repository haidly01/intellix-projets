# -*- coding: utf-8 -*-
import logging
_logger = logging.getLogger(__name__)
from odoo import _, api, fields, models
from odoo.exceptions import UserError


class PeProfileOnboardingWizard(models.TransientModel):
    _name = "pe.profile.onboarding.wizard"
    _description = "Assistant onboarding depuis la fiche profil"

    profile_id = fields.Many2one("pe.employee.profile", required=True)
    employee_id = fields.Many2one(related="profile_id.employee_id")
    pe_access = fields.Selection(
        [
            ("employee", "Employé"),
            ("manager", "Gestionnaire"),
            ("hr", "Responsable RH"), ("freelance", "Freelance"),
        ],
        string="Niveau RH",
        default="employee",
        required=True,
    )
    salaire_base = fields.Float(string="Salaire de base")
    devise_remuneration = fields.Selection(
        [("MAD", "MAD"), ("EUR", "EUR"), ("CAD", "CAD")],
        default="MAD",
        required=True,
    )
    variable_prime_template_id = fields.Many2one(
        "pe.prime.template",
        string="Template prime",
    )
    montant_variable = fields.Float(string="Montant variable")
    description_variable = fields.Text(string="Modalités primes")
    contract_type = fields.Selection(
        [("cdd", "CDD"), ("cdi", "CDI"), ("freelance", "Freelance")],
        default="cdi",
        required=True,
    )
    date_start = fields.Date(
        string="Date début contrat",
        default=fields.Date.context_today,
        required=True,
    )
    date_end = fields.Date(string="Date fin (CDD)")
    send_arrival_pack = fields.Boolean(
        string="Envoyer le pack arrivée après validation",
        default=True,
    )
    copy_objectives = fields.Boolean(
        string="Reprendre les objectifs du profil dans le contrat",
        default=True,
        help="Copie la synthèse des objectifs opérationnels du profil "
        "dans le champ objectifs contractuels.",
    )
    objectifs_text = fields.Html(
        string="Objectifs contractuels",
        help="Prérempli depuis le profil si des objectifs existent.",
    )

    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        profile_id = res.get("profile_id") or self.env.context.get("default_profile_id")
        # Auto-détecter freelance depuis le profil
        if profile_id:
            profile = self.env["pe.employee.profile"].browse(profile_id)
            if profile.type_remuneration == "honoraire":
                res["contract_type"] = "freelance"
        if profile_id and res.get("copy_objectives", True):
            profile = self.env["pe.employee.profile"].browse(profile_id)
            if "objectifs_text" in fields_list and not res.get("objectifs_text"):
                res["objectifs_text"] = profile._format_objectives_for_contract() or False
            if "salaire_base" in fields_list and not res.get("salaire_base"):
                res["salaire_base"] = profile.salaire_base
            if "devise_remuneration" in fields_list and not res.get("devise_remuneration"):
                res["devise_remuneration"] = profile.devise_remuneration or "MAD"
        return res

    @api.onchange("profile_id", "copy_objectives")
    def _onchange_copy_objectives(self):
        if self.profile_id and self.copy_objectives:
            self.objectifs_text = (
                self.profile_id._format_objectives_for_contract() or False
            )
        elif not self.copy_objectives:
            self.objectifs_text = False

    @api.onchange("pe_access")
    def _onchange_pe_access(self):
        if self.pe_access == "freelance":
            self.contract_type = "freelance"
        elif self.pe_access in ("employee", "manager", "hr", "admin") and self.contract_type == "freelance":
            self.contract_type = "cdi"

    @api.onchange("contract_type")
    def _onchange_contract_type(self):
        if self.contract_type != "cdd":
            self.date_end = False

    def _apply_pe_access(self):
        self.ensure_one()
        user = self.profile_id.user_id
        if not user:
            raise UserError(_("Aucun utilisateur lié à ce profil."))
        pe = {
            "employee": self.env.ref(
                "people_engine.group_employee", raise_if_not_found=False
            ),
            "manager": self.env.ref(
                "people_engine.group_manager", raise_if_not_found=False
            ),
            "hr": self.env.ref("people_engine.group_hr", raise_if_not_found=False),
        }
        wanted = set()
        base_user = self.env.ref("base.group_user")
        if self.pe_access == "hr" and pe["hr"]:
            wanted = {pe["employee"], pe["manager"], pe["hr"]} - {None}
        elif self.pe_access == "manager" and pe["manager"]:
            wanted = {pe["employee"], pe["manager"]} - {None}
        elif self.pe_access == "freelance" and pe["employee"]:
            wanted = {pe["employee"]}
        elif pe["employee"]:
            wanted = {pe["employee"]}
        pe_ids = {g.id for g in wanted if g}
        pe_privilege = self.env.ref(
            "people_engine.res_groups_privilege_people_engine",
            raise_if_not_found=False,
        )
        keep = user.group_ids.filtered(
            lambda g: not pe_privilege
            or g.privilege_id.id != pe_privilege.id
        )
        user.sudo().write(
            {"group_ids": [(6, 0, list(keep.ids) + list(pe_ids | {base_user.id}))]}
        )
        user._sync_people_engine_role_groups()

    def action_confirm(self):
        self.ensure_one()
        profile = self.profile_id
        arrival = self.env.ref(
            "people_engine.lifecycle_stage_arrival",
            raise_if_not_found=False,
        )
        vals = {
            "salaire_base": self.salaire_base,
            "devise_remuneration": self.devise_remuneration,
        }
        if arrival:
            vals["lifecycle_stage_id"] = arrival.id
        profile.write(vals)
        self._apply_pe_access()
        contract_vals = profile._contract_create_vals(
            contract_type=self.contract_type,
            date_start=self.date_start,
            salaire_base=self.salaire_base,
            devise=self.devise_remuneration,
        )
        if self.copy_objectives and self.objectifs_text:
            contract_vals["objectifs_text"] = self.objectifs_text
        elif not self.copy_objectives:
            contract_vals.pop("objectifs_text", None)
        if self.contract_type == "cdd" and self.date_end:
            contract_vals["date_end"] = self.date_end
        contract = self.env["pe.employment.contract"].create(contract_vals)
        # Auto-appliquer objectifs et primes call center
        job_name = (profile.job_id.name or "").lower()
        dept_name = (profile.department_id.name or "").lower()
        pe_access = self.pe_access or ""
        is_call_center = any(kw in job_name + dept_name for kw in [
            "call", "télé", "agent", "conseiller", "qualification"
        ]) or pe_access in ("employee", "freelance")
        is_supervisor = pe_access in ("manager", "hr", "admin")

        # Auto-créer utilisateur VICIdial
        if is_call_center or is_supervisor:
            try:
                import subprocess, re as re_mod
                user = profile.user_id
                if user and user.login:
                    vicidial_user = re_mod.sub(r"[^a-z0-9]", "", user.login.split("@")[0].lower())[:20]
                    vicidial_pass = user.login.split("@")[0]
                    vicidial_group = "SUPERVISORS" if is_supervisor else "AGENTS"
                    # Trouver prochaine extension libre
                    import subprocess
                    result = subprocess.run([
                        "mysql", "-u", "root", "asterisk",
                        "-e", "SELECT COALESCE(MAX(CAST(phone_login AS UNSIGNED)), 86019) + 1 FROM vicidial_users WHERE phone_login REGEXP '^[0-9]+$' AND CAST(phone_login AS UNSIGNED) >= 86020;"
                    ], capture_output=True, text=True)
                    next_ext = "86020"
                    if result.stdout:
                        lines = result.stdout.strip().split(chr(10))
                        if len(lines) > 1:
                            next_ext = lines[1].strip() or "86020"
                    # Vérifier si user existe déjà
                    check = subprocess.run([
                        "mysql", "-u", "root", "asterisk",
                        "-e", "SELECT COUNT(*) FROM vicidial_users WHERE user=" + chr(34) + vicidial_user + chr(34) + ";"
                    ], capture_output=True, text=True)
                    already_exists = "1" in (check.stdout or "")
                    if not already_exists:
                        full_name = profile.employee_id.name or user.login
                        subprocess.run([
                            "mysql", "-u", "root", "asterisk",
                            "-e", "INSERT INTO vicidial_users (user, pass, full_name, email, user_level, user_group, phone_login, phone_pass, agent_choose_ingroups) VALUES (" + chr(34) + vicidial_user + chr(34) + ", " + chr(34) + vicidial_pass + chr(34) + ", " + chr(34) + full_name + chr(34) + ", " + chr(34) + user.login + chr(34) + ", 1, " + chr(34) + vicidial_group + chr(34) + ", " + chr(34) + next_ext + chr(34) + ", " + chr(34) + vicidial_pass + chr(34) + ", " + chr(34) + "1" + chr(34) + ");"
                        ], capture_output=True, text=True)
                        _logger.info("VICIdial user créé: %s ext %s groupe %s", vicidial_user, next_ext, vicidial_group)
            except Exception as e:
                _logger.warning("VICIdial auto-create error: %s", e)
        if is_call_center:
            # Appliquer template objectifs call center (id=2)
            obj_template = self.env["pe.objective.template"].browse(2)
            if obj_template.exists() and hasattr(profile, "objective_ids"):
                for line in obj_template.line_ids:
                    existing = profile.objective_ids.filtered(
                        lambda o: o.name == line.name
                    )
                    if not existing:
                        self.env["pe.objective"].create({
                            "profile_id": profile.id,
                            "name": line.name,
                            "objective_type": line.objective_type,
                            "target_value": line.target_value,
                            "unit": line.unit,
                            "period": line.period,
                        })
            # Appliquer template prime call center (id=4)
            if not contract.variable_prime_template_id:
                prime_template = self.env["pe.prime.template"].browse(4)
                if prime_template.exists():
                    contract.write({
                        "variable_prime_template_id": prime_template.id,
                        "prime_performance_base": prime_template.prime_performance_base,
                        "challenges_eligible": prime_template.challenges_eligible,
                    })

        self.env["pe.action.log"].log_action(
            profile,
            "status_changed",
            _("Assistant onboarding : stade Arrivée, contrat %s créé.")
            % contract.name,
            actor_type="hr",
        )
        if self.send_arrival_pack:
            return profile.action_send_arrival_pack()
        return profile._contract_form_action(
            contract, title=_("Contrat créé — %s") % profile.display_name
        )
