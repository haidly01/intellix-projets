# -*- coding: utf-8 -*-
from odoo import api, fields, models

# Groupes IntelliX accordés aux superadmins Odoo (base.group_system) pour les démos.
INTELLIX_DEMO_SUPERADMIN_GROUP_XMLIDS = (
    # People Engine — RH complet
    "people_engine.group_employee",
    "people_engine.group_manager",
    "people_engine.group_hr",
    "people_engine.group_admin",
    # Appels — VICIdial
    "doorway_vicidial_campaigns.group_vicidial_qualifier",
    "doorway_vicidial_campaigns.group_vicidial_supervisor",
    # Agents IA
    "doorway_agents_dashboard.group_doorway_agent_viewer",
    "doorway_agents_dashboard.group_doorway_agent_tester",
    "doorway_agents_dashboard.group_doorway_agent_manager",
    # Extracteur
    "doorway_leads_bruts.group_leads_bruts_user",
    "doorway_leads_bruts.group_leads_bruts_manager",
    "doorway_leads_bruts.group_admin_commercial",
    # CRM Doorway — vue globale + rôles
    "renovation_conciergerie.group_agence_doorway_crm",
    "renovation_conciergerie.group_doorway_b2b",
    "renovation_conciergerie.group_doorway_role_admin",
    "renovation_conciergerie.group_pipeline_supervisor",
    "renovation_conciergerie.group_automation_configurator",
    # Onglets pipelines CRM
    "renovation_conciergerie.group_pipeline_tab_renovation",
    "renovation_conciergerie.group_pipeline_tab_immobilier",
    "renovation_conciergerie.group_pipeline_tab_marketing",
    "renovation_conciergerie.group_pipeline_tab_driven",
    "renovation_conciergerie.group_pipeline_tab_doorway_b2b",
    "renovation_conciergerie.group_pipeline_tab_assurance",
    # Crédits IA
    "doorway_credits.group_doorway_credits_admin",
    # Réseaux sociaux IA
    "doorway_social_ia.group_social_manager",
    # Traffic Manager
    "doorway_traffic_manager.group_traffic_manager",
    # Veille sociale
    "doorway_veille_sociale.group_veille_settings",
)


class ResUsers(models.Model):
    _inherit = "res.users"

    pe_onboarding_done = fields.Boolean(
        string="Visite guidée People Engine terminée (legacy)",
        default=False,
        help="Champ historique — voir doorway_onboarding_state.",
    )

    def _is_intellix_demo_superadmin(self):
        """Superadmin IntelliX = utilisateur Odoo Administration / Paramètres."""
        self.ensure_one()
        return self.active and not self.share and self.has_group("base.group_system")

    @api.model
    def _intellix_demo_superadmin_groups(self):
        """Résout les groupes IntelliX à accorder aux superadmins (modules optionnels ignorés)."""
        groups = self.env["res.groups"]
        resolved = self.env["res.groups"]
        for xmlid in INTELLIX_DEMO_SUPERADMIN_GROUP_XMLIDS:
            group = self.env.ref(xmlid, raise_if_not_found=False)
            if group:
                resolved |= group
        return resolved

    def _ensure_demo_superadmin_groups(self):
        """Accorde tous les groupes IntelliX aux superadmins — jamais de retrait."""
        demo_groups = self._intellix_demo_superadmin_groups()
        if not demo_groups:
            return
        for user in self:
            if not user._is_intellix_demo_superadmin():
                continue
            missing = demo_groups - user.group_ids
            if missing:
                user.sudo().with_context(skip_intellix_superadmin_sync=True).write(
                    {"group_ids": [(4, g.id) for g in missing]}
                )

    @api.model
    def _migrate_pe_onboarding_to_doorway(self):
        """Migre l'ancien flag vers doorway_onboarding_state."""
        users = self.search([("pe_onboarding_done", "=", True)])
        for user in users:
            if not user.doorway_onboarding_is_done("people_engine"):
                user.doorway_onboarding_mark_done("people_engine")

    @api.model
    def _init_sync_people_engine_access(self):
        """Appelé au chargement du module : aligne les accès PE."""
        users = self.search([("active", "=", True), ("share", "=", False)])
        users._sync_people_engine_role_groups()
        users._ensure_demo_superadmin_groups()

    @api.model
    def _init_ensure_demo_superadmin_groups(self):
        """Upgrade / post-init : accorde tous les groupes IntelliX aux superadmins."""
        system_group = self.env.ref("base.group_system", raise_if_not_found=False)
        if not system_group:
            return
        users = self.search(
            [
                ("active", "=", True),
                ("share", "=", False),
                ("all_group_ids", "in", system_group.id),
            ]
        )
        users._ensure_demo_superadmin_groups()

    @api.model_create_multi
    def create(self, vals_list):
        users = super().create(vals_list)
        if not self.env.context.get("skip_intellix_superadmin_sync"):
            users._ensure_demo_superadmin_groups()
        return users

    def write(self, vals):
        res = super().write(vals)
        if not self.env.context.get("skip_intellix_superadmin_sync"):
            self._ensure_demo_superadmin_groups()
        return res

    def _pe_group_refs(self):
        return {
            "employee": self.env.ref("people_engine.group_employee", raise_if_not_found=False),
            "manager": self.env.ref("people_engine.group_manager", raise_if_not_found=False),
            "hr": self.env.ref("people_engine.group_hr", raise_if_not_found=False),
            "admin": self.env.ref("people_engine.group_admin", raise_if_not_found=False),
        }

    def _wanted_people_engine_groups(self, user, pe):
        """Groupes People Engine selon rôle Doorway / profil RH / pipelines."""
        if not user.active or user.share:
            return set()
        if user._is_intellix_demo_superadmin():
            return {g for g in pe.values() if g}

        wanted = set()

        def add(*keys):
            for key in keys:
                if pe.get(key):
                    wanted.add(pe[key])

        try:
            from odoo.addons.renovation_conciergerie.models.res_users import (
                DOORWAY_HR_DIRECTOR_LOGINS,
            )
        except ImportError:
            DOORWAY_HR_DIRECTOR_LOGINS = ()

        if user.login in DOORWAY_HR_DIRECTOR_LOGINS:
            add("employee", "manager", "hr", "admin")
            return wanted

        profile = self.env["pe.employee.profile"].sudo().search(
            [("user_id", "=", user.id)], limit=1
        )
        if profile and profile.type_usager_pe:
            profile_map = {
                "gestionnaire": ("employee", "manager"),
                "mixte": ("employee", "manager"),
                "closeur": ("employee",),
                "prospecteur_vicidial": ("employee",),
                "prospecteur_social": ("employee",),
            }
            add(*profile_map.get(profile.type_usager_pe, ("employee",)))
            return wanted

        if user.has_group("renovation_conciergerie.group_agence_doorway_crm"):
            add("employee", "manager", "hr", "admin")
            return wanted

        is_pe_admin = (
            user.has_group("renovation_conciergerie.group_pipeline_admin")
            or user.has_group("renovation_conciergerie.group_doorway_role_admin")
            or user.doorway_role == "admin"
        )
        is_pe_supervisor = (
            user.has_group("renovation_conciergerie.group_pipeline_supervisor")
            or user.has_group("renovation_conciergerie.group_doorway_role_supervisor")
            or user.doorway_role == "supervisor"
        )

        if is_pe_admin:
            add("employee", "manager", "hr", "admin")
            return wanted

        if is_pe_supervisor:
            add("employee", "manager")
            return wanted

        if user.doorway_segment == "b2b" and user.doorway_role == "user":
            add("employee")
            return wanted

        if user.doorway_segment == "b2b" and user.doorway_role:
            add("employee")

        return wanted

    def _apply_pe_group_commands(self, user, wanted, pe):
        """Applique les groupes PE sans retirer ceux des superadmins démo."""
        all_pe = {g for g in pe.values() if g}
        if not wanted and not user._is_intellix_demo_superadmin():
            return []
        if user._is_intellix_demo_superadmin():
            wanted = all_pe
        commands = []
        for group in wanted:
            if group not in user.group_ids:
                commands.append((4, group.id))
        if not user._is_intellix_demo_superadmin():
            for group in all_pe:
                if group in user.group_ids and group not in wanted:
                    commands.append((3, group.id))
        return commands

    def sync_pe_groups_from_profile(self):
        """Réaligne les groupes PE depuis le profil RH (prioritaire B2C)."""
        pe = self._pe_group_refs()
        if not pe.get("employee"):
            return
        for user in self:
            if user._is_intellix_demo_superadmin():
                continue
            wanted = self._wanted_people_engine_groups(user, pe)
            commands = self._apply_pe_group_commands(user, wanted, pe)
            if commands:
                user.sudo().with_context(skip_pe_group_resync=True).write(
                    {"group_ids": commands}
                )

    def _sync_people_engine_role_groups(self):
        """Synchronise les groupes People Engine (priorité profil RH)."""
        pe = self._pe_group_refs()
        if not pe.get("employee"):
            return
        for user in self:
            wanted = self._wanted_people_engine_groups(user, pe)
            commands = self._apply_pe_group_commands(user, wanted, pe)
            if commands:
                user.sudo().with_context(skip_pe_group_resync=True).write(
                    {"group_ids": commands}
                )
