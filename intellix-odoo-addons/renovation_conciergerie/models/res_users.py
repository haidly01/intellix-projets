from odoo import _, api, fields, models
from odoo.exceptions import AccessError

# Vue CRM globale : tous pipelines, tous les leads (tous vendeurs), toutes les apps.
DOORWAY_CRM_OWNER_LOGINS = (
    "karine@agencedoorway.com",
    "martin@agencedoorway.com",
    "zakaria@agencedoorway.com",
)

# Vendeurs CRM Doorway : tous pipelines, leads assignés à soi (+ non assignés).
DOORWAY_CRM_PEER_SALES_LOGINS = ()

DOORWAY_CRM_SALES_LOGINS = DOORWAY_CRM_OWNER_LOGINS + DOORWAY_CRM_PEER_SALES_LOGINS

# Direction Agence Doorway : RH complet (toutes sociétés) sans basculer sur Digital Doorway.
DOORWAY_HR_DIRECTOR_LOGINS = (
    "martin@agencedoorway.com",
)

# Superviseurs connus (rôle Superviseur + groupe pipeline_supervisor)
DOORWAY_SUPERVISOR_LOGINS = (
    "ouzbida.hilal@powercall.org",
)

# Pipeline (crm.team) -> groupe de visibilité de l'onglet correspondant
PIPELINE_TAB_GROUPS = {
    "coins_marocain_partenariats.crm_team_coins_marocain": "coins_marocain_partenariats.group_pipeline_tab_coins_marocain",
    "renovation_conciergerie.crm_team_renovation": "renovation_conciergerie.group_pipeline_tab_renovation",
    "renovation_conciergerie.crm_team_immobilier": "renovation_conciergerie.group_pipeline_tab_immobilier",
    "renovation_conciergerie.crm_team_marketing": "renovation_conciergerie.group_pipeline_tab_marketing",
    "renovation_conciergerie.crm_team_driven": "renovation_conciergerie.group_pipeline_tab_driven",
    "renovation_conciergerie.crm_team_doorway_b2b": "renovation_conciergerie.group_pipeline_tab_doorway_b2b",
    "renovation_conciergerie.crm_team_assurance": "renovation_conciergerie.group_pipeline_tab_assurance",
}

class ResUsers(models.Model):
    _inherit = "res.users"

    @api.model
    def _doorway_equipe_interne_group(self):
        return self.env.ref(
            "renovation_conciergerie.group_doorway_equipe_interne",
            raise_if_not_found=False,
        )

    def _doorway_is_equipe_interne(self):
        """True seulement pour l'allowlist Doorway — pas un partenaire interne."""
        self.ensure_one()
        group = self._doorway_equipe_interne_group()
        return bool(group and self.active and group in self.all_group_ids)

    @api.model
    def _doorway_equipe_interne_domain(self):
        """Domaine défis / classement. Échec fermé si le groupe manque."""
        group = self._doorway_equipe_interne_group()
        if not group:
            return [("id", "=", 0)]
        return [("group_ids", "in", [group.id]), ("active", "=", True)]

    @api.model
    def _doorway_equipe_interne_domain_expr(self):
        group = self._doorway_equipe_interne_group()
        if not group:
            return "[('id', '=', 0)]"
        return "[('group_ids', 'in', [%s]), ('active', '=', True)]" % group.id

    def _get_group_ids(self):
        """Website login : env.user vide ne doit pas perdre le groupe Public (sinon 403 res.lang)."""
        if not self:
            gid = self.env["ir.model.data"].sudo()._xmlid_to_res_id("base.group_public")
            return (gid,) if gid else ()
        return super()._get_group_ids()

    pipeline_admin_team_ids = fields.Many2many(
        "crm.team",
        "res_users_pipeline_admin_team_rel",
        "user_id",
        "team_id",
        string="Pipelines administrés",
        domain=[("is_agence_doorway_pipeline", "=", True)],
        help="Pipelines que cet administrateur restreint peut gérer entièrement "
        "(s'applique au groupe « Admin de pipeline (restreint) »).",
    )
    doorway_assigned_pipeline_ids = fields.Many2many(
        "crm.team",
        "res_users_doorway_assigned_pipeline_rel",
        "user_id",
        "team_id",
        string="Pipelines CRM assignés",
        domain=[("is_agence_doorway_pipeline", "=", True)],
        help="Pipelines visibles pour ce vendeur : onglets CRM limités, "
        "leads et commandes strictement personnels (groupe « Vendeur : pipelines assignés »).",
    )
    effective_pipeline_team_ids = fields.Many2many(
        "crm.team",
        "res_users_effective_pipeline_team_rel",
        "user_id",
        "team_id",
        string="Pipelines CRM (portée admin restreint)",
        compute="_compute_effective_pipeline_team_ids",
        store=True,
        help="Équipes visibles pour la règle d'accès « Admin de pipeline ».",
    )
    subordinate_user_ids = fields.Many2many(
        "res.users",
        compute="_compute_subordinate_user_ids",
        string="Utilisateurs supervisés",
        help="Membres des équipes CRM dont cet utilisateur est responsable.",
    )
    gamification_monthly_goal = fields.Integer(
        string="Objectif mensuel (ventes gagnées)",
        help="Objectif personnel d'opportunités gagnées par mois. "
        "Une fois atteint : félicitations + bonus de points.",
    )
    project_monthly_goal = fields.Integer(
        string="Objectif mensuel (tâches terminées)",
        help="Objectif personnel de tâches de projet terminées par mois. "
        "Une fois atteint : félicitations + bonus de points.",
    )
    doorway_segment = fields.Selection(
        [
            ("b2b", "B2B — Marketing / Driven / Doorway Clients"),
            ("b2c", "B2C — Rénovation / Assurance / Immobilier"),
        ],
        string="Segment Doorway",
        compute="_compute_doorway_segment",
        store=True,
        help="Aligné sur les pipelines CRM : B2C = Rénovation, Assurance, Immobilier. "
        "B2B = Marketing, Driven, Doorway Clients.",
    )
    doorway_role = fields.Selection(
        [
            ("user", "Utilisateur"),
            ("supervisor", "Superviseur"),
            ("admin", "Admin"),
        ],
        string="Rôle Doorway",
        compute="_compute_doorway_role",
        store=True,
        help="Niveau d'accès : utilisateur standard, superviseur d'équipe ou administrateur.",
    )

    def _compute_subordinate_user_ids(self):
        Team = self.env["crm.team"].sudo()
        for user in self:
            teams = Team.search([("user_id", "=", user.id)])
            members = teams.crm_team_member_ids.user_id
            user.subordinate_user_ids = members - user

    @api.depends(
        "group_ids",
        "pipeline_admin_team_ids",
        "doorway_assigned_pipeline_ids",
        "crm_team_ids",
        "sale_team_id",
    )
    def _compute_effective_pipeline_team_ids(self):
        """Portée CRM pour les admins de pipeline (évite un kanban vide si le champ est vide)."""
        pa_group = self.env.ref(
            "renovation_conciergerie.group_pipeline_admin", raise_if_not_found=False
        )
        assigned_group = self.env.ref(
            "renovation_conciergerie.group_doorway_pipeline_assigned",
            raise_if_not_found=False,
        )
        crm_super = self.env.ref(
            "renovation_conciergerie.group_agence_doorway_crm", raise_if_not_found=False
        )
        crm_sales = self.env.ref(
            "renovation_conciergerie.group_agence_doorway_crm_sales",
            raise_if_not_found=False,
        )
        doorway = self.env["crm.team"].search([("is_agence_doorway_pipeline", "=", True)])
        for user in self:
            if crm_super and crm_super in user.all_group_ids:
                user.effective_pipeline_team_ids = doorway
            elif crm_sales and crm_sales in user.all_group_ids:
                user.effective_pipeline_team_ids = doorway
            elif assigned_group and assigned_group in user.all_group_ids:
                user.effective_pipeline_team_ids = user.doorway_assigned_pipeline_ids
            elif pa_group and pa_group in user.all_group_ids:
                scoped = user.pipeline_admin_team_ids
                if not scoped:
                    scoped = user._allowed_pipeline_team_ids().filtered(
                        lambda t: t.is_agence_doorway_pipeline
                    )
                if not scoped:
                    scoped = doorway
                user.effective_pipeline_team_ids = scoped
            else:
                user.effective_pipeline_team_ids = False

    @api.depends(
        "group_ids",
        "share",
        "active",
        "sale_team_id",
        "crm_team_ids",
        "pipeline_admin_team_ids",
        "doorway_assigned_pipeline_ids",
    )
    def _compute_doorway_segment(self):
        Team = self.env["crm.team"]
        b2c_team_ids = set(Team._doorway_b2c_pipeline_team_ids())
        crm_super = self.env.ref(
            "renovation_conciergerie.group_agence_doorway_crm",
            raise_if_not_found=False,
        )
        for user in self:
            if user._is_renovation_partner_user():
                user.doorway_segment = "b2c"
            elif user.share or not user.active:
                user.doorway_segment = False
            elif crm_super and crm_super in user.all_group_ids:
                user.doorway_segment = "b2b"
            else:
                teams = user._allowed_pipeline_team_ids()
                if user.sale_team_id:
                    teams |= user.sale_team_id
                if teams.ids and b2c_team_ids.intersection(teams.ids):
                    user.doorway_segment = "b2c"
                else:
                    user.doorway_segment = "b2b"

    @api.depends("group_ids", "share", "active", "login")
    def _compute_doorway_role(self):
        for user in self:
            user.doorway_role = user._resolve_doorway_role()

    def _resolve_doorway_role(self):
        """Détermine le rôle Doorway sans confondre vue multi-pipelines et rôle Admin."""
        self.ensure_one()
        if not self.active or self.share:
            return False
        # Propriétaires Module Hébergement sur leur propre société :
        # pas de rôle Doorway (sinon Messages / RH / apps internes réapparaissent).
        if self._is_riad_owner_only_user():
            return False
        if self.has_group("renovation_conciergerie.group_pipeline_admin"):
            return "admin"
        if (
            self.has_group("renovation_conciergerie.group_pipeline_supervisor")
            or self.login in DOORWAY_SUPERVISOR_LOGINS
        ):
            return "supervisor"
        if self._is_renovation_partner_user() or not self.share:
            return "user"
        return False

    def _is_riad_owner_only_user(self):
        """User Module Hébergement rattaché à un établissement, hors équipes Doorway."""
        self.ensure_one()
        if "riad_establishment_ids" not in self._fields:
            return False
        if not self.riad_establishment_ids:
            return False
        if self.has_group("intellix_riad.group_riad_manager"):
            return False
        # Sociétés internes Doorway / IntelliX
        if self.company_id and self.company_id.id in (1, 2):
            return False
        return self.has_group("intellix_riad.group_riad_user")

    @api.model_create_multi
    def create(self, vals_list):
        users = super().create(vals_list)
        users._sync_agence_doorway_pipeline_access()
        users._sync_doorway_assigned_pipeline_access()
        users._sync_pipeline_tab_groups()
        users._sync_doorway_segment_groups()
        users._sync_doorway_role_groups()
        return users

    def write(self, vals):
        res = super().write(vals)
        segment_fields = {
            "group_ids",
            "pipeline_admin_team_ids",
            "doorway_assigned_pipeline_ids",
            "sale_team_id",
            "crm_team_ids",
        }
        if "group_ids" in vals:
            self._sync_agence_doorway_pipeline_access()
            self._doorway_prevent_pipeline_admin_on_crm_superusers()
            self._doorway_autofill_pipeline_admin_teams()
            self._sync_doorway_role_groups()
        if "doorway_assigned_pipeline_ids" in vals or "group_ids" in vals:
            self._sync_doorway_assigned_pipeline_access()
        if segment_fields & set(vals):
            self._sync_doorway_segment_groups()
            self.invalidate_recordset(["doorway_segment"])
            self._compute_doorway_segment()
        if {"group_ids", "pipeline_admin_team_ids", "doorway_assigned_pipeline_ids"} & set(vals):
            self._sync_pipeline_tab_groups()
        return res

    def _doorway_prevent_pipeline_admin_on_crm_superusers(self):
        """Super admin CRM ≠ admin de pipeline restreint (conflit de règles d'accès)."""
        pa = self.env.ref(
            "renovation_conciergerie.group_pipeline_admin", raise_if_not_found=False
        )
        crm_super = self.env.ref(
            "renovation_conciergerie.group_agence_doorway_crm", raise_if_not_found=False
        )
        if not pa or not crm_super:
            return
        for user in self:
            if pa in user.group_ids and crm_super in user.all_group_ids:
                user.sudo().write({"group_ids": [(3, pa.id)]})

    def _doorway_autofill_pipeline_admin_teams(self):
        """Remplit « Pipelines administrés » à l'activation du groupe admin restreint."""
        pa = self.env.ref(
            "renovation_conciergerie.group_pipeline_admin", raise_if_not_found=False
        )
        if not pa:
            return
        crm_super = self.env.ref(
            "renovation_conciergerie.group_agence_doorway_crm", raise_if_not_found=False
        )
        for user in self.filtered(lambda u: pa in u.group_ids):
            if crm_super and crm_super in user.all_group_ids:
                continue
            if user.pipeline_admin_team_ids:
                continue
            teams = user._allowed_pipeline_team_ids().filtered(
                lambda t: t.is_agence_doorway_pipeline
            )
            if teams:
                user.sudo().write({"pipeline_admin_team_ids": [(6, 0, teams.ids)]})

    def _sync_agence_doorway_pipeline_access(self):
        """Ajoute aux pipelines tout utilisateur promu administrateur CRM / système."""
        admins = self.env["crm.team"]._get_agence_doorway_admin_users()
        if admins & self:
            self.env["crm.team"]._setup_agence_doorway_pipelines()

    @api.model
    def _init_sync_pipeline_tab_groups(self):
        """Aligne les onglets de pipeline pour tous les utilisateurs internes (chargement module)."""
        users = self.search([("share", "=", False), ("active", "=", True)])
        users.filtered(
            lambda u: not u._is_renovation_partner_user()
        )._sync_pipeline_tab_groups()

    @api.model
    def _init_sync_doorway_segment_groups(self):
        """Aligne les groupes B2B / B2C sur tous les utilisateurs actifs."""
        self.search([("active", "=", True)])._sync_doorway_segment_groups()

    @api.model
    def _init_sync_doorway_role_groups(self):
        """Aligne les rôles Utilisateur / Superviseur / Admin."""
        self.search([("active", "=", True)])._sync_doorway_role_groups()

    @api.model
    def _doorway_sync_supervisor_users(self):
        """Promouvoir les superviseurs connus (ex. Hilal)."""
        sup_crm = self.env.ref(
            "renovation_conciergerie.group_pipeline_supervisor",
            raise_if_not_found=False,
        )
        users = self.search(
            [("login", "in", DOORWAY_SUPERVISOR_LOGINS), ("active", "=", True)]
        )
        if sup_crm:
            for user in users.filtered(lambda u: sup_crm not in u.group_ids):
                user.sudo().write({"group_ids": [(4, sup_crm.id)]})
        users._sync_doorway_role_groups()

    def _sync_doorway_role_groups(self):
        """
        Assigne le groupe de rôle Doorway le plus élevé applicable.
        « Agence Doorway — Pipelines CRM » ≠ Admin (simple accès multi-pipelines).
        """
        role_user = self.env.ref(
            "renovation_conciergerie.group_doorway_role_user", raise_if_not_found=False
        )
        role_supervisor = self.env.ref(
            "renovation_conciergerie.group_doorway_role_supervisor",
            raise_if_not_found=False,
        )
        role_admin = self.env.ref(
            "renovation_conciergerie.group_doorway_role_admin", raise_if_not_found=False
        )
        sup_crm = self.env.ref(
            "renovation_conciergerie.group_pipeline_supervisor",
            raise_if_not_found=False,
        )
        if not role_user:
            return
        role_groups = {
            "user": role_user,
            "supervisor": role_supervisor,
            "admin": role_admin,
        }
        for user in self:
            if not user.active:
                continue
            if user.has_group("base.group_system"):
                continue
            target_role = user._resolve_doorway_role()
            if not target_role:
                continue
            target_group = role_groups.get(target_role)
            if not target_group:
                continue
            commands = []
            if target_group not in user.group_ids:
                commands.append((4, target_group.id))
            if target_role != "admin" and role_admin and role_admin in user.group_ids:
                commands.append((3, role_admin.id))
            if target_role == "user" and role_supervisor and role_supervisor in user.group_ids:
                commands.append((3, role_supervisor.id))
            if commands:
                user.sudo().write({"group_ids": commands})
            if target_role == "supervisor" and sup_crm and sup_crm not in user.group_ids:
                user.sudo().write({"group_ids": [(4, sup_crm.id)]})
        self.invalidate_recordset(["doorway_role"])
        self._compute_doorway_role()
        self._sync_people_engine_role_groups()

    def _sync_people_engine_role_groups(self):
        """Aligne les groupes People Engine (profil RH prioritaire, sinon rôle B2B)."""
        if self.env.context.get("skip_pe_group_resync"):
            return
        if hasattr(self, "sync_pe_groups_from_profile"):
            profile_users = self.filtered(
                lambda u: self.env["pe.employee.profile"].sudo().search_count(
                    [("user_id", "=", u.id)]
                )
            )
            if profile_users:
                profile_users.sync_pe_groups_from_profile()
            self -= profile_users
            if not self:
                return
        if "people_engine.group_employee" not in self.env:
            return
        pe_employee = self.env.ref("people_engine.group_employee", raise_if_not_found=False)
        pe_manager = self.env.ref("people_engine.group_manager", raise_if_not_found=False)
        pe_hr = self.env.ref("people_engine.group_hr", raise_if_not_found=False)
        pe_admin = self.env.ref("people_engine.group_admin", raise_if_not_found=False)
        if not pe_employee:
            return
        pe_by_role = {
            "user": [pe_employee],
            "supervisor": [g for g in (pe_employee, pe_manager) if g],
            "admin": [g for g in (pe_employee, pe_manager, pe_hr) if g],
        }
        all_pe = [g for g in (pe_employee, pe_manager, pe_hr, pe_admin) if g]
        for user in self:
            if user.doorway_segment != "b2b" or not user.doorway_role:
                to_remove = [g for g in all_pe if g in user.group_ids]
                if to_remove:
                    user.sudo().with_context(skip_pe_group_resync=True).write(
                        {"group_ids": [(3, g.id) for g in to_remove]}
                    )
                continue
            wanted = pe_by_role.get(user.doorway_role, [pe_employee])
            commands = []
            for group in wanted:
                if group not in user.group_ids:
                    commands.append((4, group.id))
            for group in all_pe:
                if group in user.group_ids and group not in wanted:
                    commands.append((3, group.id))
            if commands:
                user.sudo().with_context(skip_pe_group_resync=True).write(
                    {"group_ids": commands}
                )

    def _sync_doorway_segment_groups(self):
        """
        B2C : pipelines Rénovation, Assurance, Immobilier (+ partenaires réno).
        B2B : Marketing, Driven, Doorway Clients (+ commerciaux multi-pipelines).
        """
        b2b_group = self.env.ref(
            "renovation_conciergerie.group_doorway_b2b", raise_if_not_found=False
        )
        b2c_group = self.env.ref(
            "renovation_conciergerie.group_doorway_b2c", raise_if_not_found=False
        )
        if not b2b_group or not b2c_group:
            return
        for user in self:
            if not user.active:
                continue
            if user._is_riad_owner_only_user():
                commands = []
                if b2b_group in user.group_ids:
                    commands.append((3, b2b_group.id))
                if b2c_group in user.group_ids:
                    commands.append((3, b2c_group.id))
                if commands:
                    user.sudo().with_context(skip_pe_group_resync=True).write(
                        {"group_ids": commands}
                    )
                continue
            is_b2c_partner = user._is_renovation_partner_user()
            is_internal = not user.share
            commands = []
            if is_b2c_partner:
                if b2c_group not in user.group_ids:
                    commands.append((4, b2c_group.id))
                if b2b_group in user.group_ids:
                    commands.append((3, b2b_group.id))
            elif is_internal:
                if b2b_group not in user.group_ids:
                    commands.append((4, b2b_group.id))
                if b2c_group in user.group_ids:
                    commands.append((3, b2c_group.id))
            if commands:
                user.sudo().write({"group_ids": commands})

    def _allowed_pipeline_team_ids(self):
        """Équipes dont l'utilisateur peut voir l'onglet : assignées + administrées + dirigées + membre."""
        self.ensure_one()
        Team = self.env["crm.team"].sudo()
        Member = self.env["crm.team.member"].sudo()
        led = Team.search([("user_id", "=", self.id)])
        member_teams = Member.search([("user_id", "=", self.id)]).crm_team_id
        return (
            self.doorway_assigned_pipeline_ids
            | self.pipeline_admin_team_ids
            | led
            | member_teams
        )

    def _sync_doorway_assigned_pipeline_access(self):
        """Aligne le groupe « pipelines assignés », les membres d'équipe et retire les accès CRM globaux."""
        assigned_group = self.env.ref(
            "renovation_conciergerie.group_doorway_pipeline_assigned",
            raise_if_not_found=False,
        )
        if not assigned_group:
            return
        salesman = self.env.ref("sales_team.group_sale_salesman", raise_if_not_found=False)
        crm_sales = self.env.ref(
            "renovation_conciergerie.group_agence_doorway_crm_sales",
            raise_if_not_found=False,
        )
        pa_group = self.env.ref(
            "renovation_conciergerie.group_pipeline_admin", raise_if_not_found=False
        )
        Member = self.env["crm.team.member"].sudo()
        for user in self:
            if user.share or not user.active:
                continue
            if user.login in DOORWAY_CRM_OWNER_LOGINS:
                if assigned_group in user.group_ids:
                    user.sudo().write({"group_ids": [(3, assigned_group.id)]})
                if user.doorway_assigned_pipeline_ids:
                    user.sudo().write({"doorway_assigned_pipeline_ids": [(5, 0, 0)]})
                continue
            teams = user.doorway_assigned_pipeline_ids
            if teams:
                commands = []
                if assigned_group not in user.group_ids:
                    commands.append((4, assigned_group.id))
                for grp in (salesman, crm_sales, pa_group):
                    if grp and grp in user.group_ids:
                        commands.append((3, grp.id))
                if commands:
                    user.sudo().write({"group_ids": commands})
                for team in teams:
                    if user.id not in team.crm_team_member_ids.mapped("user_id").ids:
                        Member.create({"crm_team_id": team.id, "user_id": user.id})
                    team.sudo().write({"favorite_user_ids": [(4, user.id)]})
                if not user.sale_team_id:
                    user.sudo().write({"sale_team_id": teams[0].id})
            elif assigned_group in user.group_ids:
                user.sudo().write({"group_ids": [(3, assigned_group.id)]})

    @api.model
    def _init_sync_doorway_assigned_pipeline_access(self):
        """Au chargement du module : aligne vendeurs à pipelines assignés."""
        assigned_group = self.env.ref(
            "renovation_conciergerie.group_doorway_pipeline_assigned",
            raise_if_not_found=False,
        )
        users = self.search([("active", "=", True), ("share", "=", False)]).filtered(
            lambda u: u.doorway_assigned_pipeline_ids
            or (assigned_group and assigned_group in u.all_group_ids)
        )
        users._sync_doorway_assigned_pipeline_access()
        users._sync_pipeline_tab_groups()

    def _doorway_is_crm_superuser(self):
        """Karine (et admin système avec groupe CRM global) : tous leads / sociétés."""
        user = self[:1].sudo()
        if not user:
            return False
        if user.login in DOORWAY_CRM_OWNER_LOGINS:
            return True
        return bool(
            user.has_group("base.group_system")
            and user.has_group("renovation_conciergerie.group_agence_doorway_crm")
        )

    def _doorway_is_crm_peer_sales_user(self):
        self.ensure_one()
        return self.login in DOORWAY_CRM_PEER_SALES_LOGINS or self.has_group(
            "renovation_conciergerie.group_agence_doorway_crm_sales"
        )

    @api.model
    def _migrate_zakaria_leads_to_marketing(self):
        """Transfère tous les leads de Zakaria vers le pipeline Marketing."""
        zakaria = self.sudo().search(
            [
                ("login", "=", "zakaria@agencedoorway.com"),
                ("active", "=", True),
                ("share", "=", False),
            ],
            limit=1,
        )
        marketing = self.env.ref(
            "renovation_conciergerie.crm_team_marketing",
            raise_if_not_found=False,
        )
        if not zakaria or not marketing:
            return 0
        Lead = self.env["crm.lead"].sudo()
        domain = [
            ("user_id", "=", zakaria.id),
            ("team_id", "!=", marketing.id),
        ]
        # Ne jamais vider Voyageurs / Partenariats / Événements Coins Marocain.
        if "coins_fiche_type" in Lead._fields:
            domain.append(
                ("coins_fiche_type", "not in", ("voyageur", "partenariat", "evenement"))
            )
        if "coins_is_voyageur_lead" in Lead._fields:
            domain.append(("coins_is_voyageur_lead", "!=", True))
        cm_team_ids = []
        for xid in (
            "coins_marocain_partenariats.crm_team_coins_voyageurs",
            "coins_marocain_partenariats.crm_team_coins_marocain",
            "coins_marocain.crm_team_evenements",
        ):
            team = self.env.ref(xid, raise_if_not_found=False)
            if team:
                cm_team_ids.append(team.id)
        if cm_team_ids:
            domain.append(("team_id", "not in", cm_team_ids))
        leads = Lead.search(domain)
        if leads:
            # Odoo 19 refuse un write groupé si les devises (expected_revenue) diffèrent.
            for lead in leads:
                lead.write({"team_id": marketing.id})
        return len(leads)

    def _is_renovation_partner_user(self):
        """Utilisateur partenaire (client) sans droits admin / super CRM."""
        self.ensure_one()
        if self.share or not self.active:
            return False
        partner_group = self.env.ref(
            "renovation_conciergerie.group_renovation_partner",
            raise_if_not_found=False,
        )
        if not partner_group or partner_group not in self.all_group_ids:
            return False
        if self.has_group("base.group_system"):
            return False
        if self.has_group("renovation_conciergerie.group_agence_doorway_crm"):
            return False
        return True

    def _get_visible_user_ids(self):
        """Utilisateurs visibles pour un compte partenaire (soi + admins Doorway)."""
        self.ensure_one()
        visible = {self.id}
        visible |= set(
            self.env["res.users"]
            .sudo()
            .search([("partner_id", "in", self._get_discuss_allowed_partner_ids())])
            .ids
        )
        return visible

    def _get_other_renovation_partner_partner_ids(self):
        """Partenaires concurrents (autres comptes « Partenaire Rénovation ») à masquer."""
        partner_group = self.env.ref(
            "renovation_conciergerie.group_renovation_partner",
            raise_if_not_found=False,
        )
        if not partner_group:
            return []
        others = (
            self.env["res.users"]
            .sudo()
            .search(
                [
                    ("active", "=", True),
                    ("share", "=", False),
                    ("id", "!=", self.id),
                    ("all_group_ids", "in", partner_group.id),
                ]
            )
        )
        return others.partner_id.ids

    def _get_discuss_allowed_partner_ids(self):
        """Contacts Discuss autorisés pour un partenaire : admins + super admins CRM."""
        self.ensure_one()
        group_ids = [self.env.ref("base.group_system").id]
        crm_super = self.env.ref(
            "renovation_conciergerie.group_agence_doorway_crm",
            raise_if_not_found=False,
        )
        if crm_super:
            group_ids.append(crm_super.id)
        users = (
            self.env["res.users"]
            .sudo()
            .search([("active", "=", True), ("share", "=", False)])
        )
        allowed_users = users.filtered(
            lambda u: any(g.id in u.all_group_ids.ids for g in self.env["res.groups"].browse(group_ids))
        )
        partner_ids = list(allowed_users.partner_id.ids)
        odoobot = self.env.ref("base.partner_root", raise_if_not_found=False)
        if odoobot and odoobot.id not in partner_ids:
            partner_ids.append(odoobot.id)
        return partner_ids

    def _check_discuss_partners_allowed(self, partners):
        """Lève AccessError si un partenaire tente de contacter un utilisateur non autorisé."""
        if not self.env.user._is_renovation_partner_user():
            return
        allowed = set(self.env.user._get_discuss_allowed_partner_ids())
        my_partner = self.env.user.partner_id.id
        # OdooBot (base.partner_root) is required at webclient bootstrap via mail_bot.
        odoobot = self.env.ref("base.partner_root", raise_if_not_found=False)
        if odoobot:
            allowed.add(odoobot.id)
        for partner in partners:
            if partner.id == my_partner:
                continue
            if partner.id not in allowed:
                raise AccessError(
                    _(
                        "Vous ne pouvez pas démarrer une conversation avec cet utilisateur. "
                        "Contactez un administrateur Doorway."
                    )
                )

    def _sync_pipeline_tab_groups(self):
        """Aligne les groupes d'onglets de pipeline sur le profil de chaque utilisateur."""
        superadmin = self.env.ref(
            "renovation_conciergerie.group_agence_doorway_crm", raise_if_not_found=False
        )
        crm_sales = self.env.ref(
            "renovation_conciergerie.group_agence_doorway_crm_sales",
            raise_if_not_found=False,
        )
        tab_groups = {}
        for team_xmlid, group_xmlid in PIPELINE_TAB_GROUPS.items():
            team = self.env.ref(team_xmlid, raise_if_not_found=False)
            group = self.env.ref(group_xmlid, raise_if_not_found=False)
            if team and group:
                tab_groups[team.id] = group

        for user in self:
            if user.share or not user.active:
                continue
            if user._is_renovation_partner_user():
                continue
            # Vue globale ou vendeur Doorway : onglets via implication de groupe.
            if superadmin and superadmin in user.all_group_ids:
                continue
            if crm_sales and crm_sales in user.all_group_ids:
                continue
            assigned_group = self.env.ref(
                "renovation_conciergerie.group_doorway_pipeline_assigned",
                raise_if_not_found=False,
            )
            pa_group = self.env.ref(
                "renovation_conciergerie.group_pipeline_admin", raise_if_not_found=False
            )
            if (
                assigned_group
                and assigned_group in user.all_group_ids
                and user.doorway_assigned_pipeline_ids
            ):
                allowed_team_ids = set(user.doorway_assigned_pipeline_ids.ids)
            elif pa_group and pa_group in user.all_group_ids and user.pipeline_admin_team_ids:
                allowed_team_ids = set(user.pipeline_admin_team_ids.ids)
            else:
                allowed_team_ids = set(user._allowed_pipeline_team_ids().ids)
            commands = []
            for team_id, group in tab_groups.items():
                should_have = team_id in allowed_team_ids
                has_direct = group in user.group_ids
                if should_have and not has_direct:
                    commands.append((4, group.id))
                elif not should_have and has_direct:
                    commands.append((3, group.id))
            if commands:
                user.sudo().write({"group_ids": commands})

    @api.model
    def _doorway_sync_automation_configurator_groups(self):
        """Accorde le groupe automatisation aux profils superviseur / admin pipeline."""
        automation = self.env.ref(
            "renovation_conciergerie.group_automation_configurator",
            raise_if_not_found=False,
        )
        if not automation:
            return
        source_xmlids = (
            "renovation_conciergerie.group_agence_doorway_crm",
            "renovation_conciergerie.group_pipeline_supervisor",
            "renovation_conciergerie.group_pipeline_admin",
        )
        users = self.env["res.users"]
        for xid in source_xmlids:
            group = self.env.ref(xid, raise_if_not_found=False)
            if group:
                users |= group.user_ids
        for user in users.filtered(lambda u: u.active and not u.share):
            if automation not in user.group_ids:
                user.sudo().write({"group_ids": [(4, automation.id)]})

    @api.model
    def _doorway_sync_crm_sales_team_users(self):
        """Karine / Martin / Zakaria = vue globale (tous modules, tous leads)."""
        doorway_crm = self.env.ref(
            "renovation_conciergerie.group_agence_doorway_crm", raise_if_not_found=False
        )
        doorway_crm_sales = self.env.ref(
            "renovation_conciergerie.group_agence_doorway_crm_sales",
            raise_if_not_found=False,
        )
        pipeline_admin = self.env.ref(
            "renovation_conciergerie.group_pipeline_admin", raise_if_not_found=False
        )
        all_users = self.search(
            [("login", "in", DOORWAY_CRM_SALES_LOGINS), ("active", "=", True)]
        )
        owners = all_users.filtered(lambda u: u.login in DOORWAY_CRM_OWNER_LOGINS)
        hr_directors = all_users.filtered(
            lambda u: u.login in DOORWAY_HR_DIRECTOR_LOGINS
        )
        peers = all_users.filtered(
            lambda u: u.login in DOORWAY_CRM_PEER_SALES_LOGINS
            and u.login not in DOORWAY_HR_DIRECTOR_LOGINS
        )
        if not all_users:
            return
        crm_global_users = owners
        if doorway_crm and crm_global_users:
            sales_gid = doorway_crm_sales.id if doorway_crm_sales else False
            crm_gid = doorway_crm.id
            extra_gids = []
            for xid in (
                "sales_team.group_sale_salesman_all_leads",
                "sales_team.group_sale_manager",
                "coins_quebec.group_coins_quebec_manager",
                "intellix_riad.group_riad_manager",
            ):
                grp = self.env.ref(xid, raise_if_not_found=False)
                if grp:
                    extra_gids.append(grp.id)
            strip_gids = []
            for xid in (
                "renovation_conciergerie.group_doorway_pipeline_assigned",
                "coins_marocain_partenariats.group_devis_workspace",
                "coins_marocain_partenariats.group_devis_own_contacts",
            ):
                grp = self.env.ref(xid, raise_if_not_found=False)
                if grp:
                    strip_gids.append(grp.id)
            for user in crm_global_users:
                gids = list(user.group_ids.ids)
                changed = False
                if crm_gid not in gids:
                    gids.append(crm_gid)
                    changed = True
                if sales_gid and sales_gid in gids:
                    gids = [g for g in gids if g != sales_gid]
                    changed = True
                for gid in extra_gids:
                    if gid not in gids:
                        gids.append(gid)
                        changed = True
                if any(g in gids for g in strip_gids):
                    gids = [g for g in gids if g not in strip_gids]
                    changed = True
                if changed:
                    user.sudo().write({"group_ids": [(6, 0, gids)]})
                if user.doorway_assigned_pipeline_ids:
                    user.sudo().write({"doorway_assigned_pipeline_ids": [(5, 0, 0)]})
        if hr_directors:
            agence_co = self.env["res.company"].sudo().search(
                [("name", "ilike", "Agence Doorway Inc")], limit=1
            )
            digital_id = self.env["crm.team"]._doorway_digital_doorway_company_id()
            for user in hr_directors:
                co_cmds = []
                if agence_co and agence_co.id not in user.company_ids.ids:
                    co_cmds.append((4, agence_co.id))
                if digital_id and digital_id not in user.company_ids.ids:
                    co_cmds.append((4, digital_id))
                if co_cmds:
                    user.sudo().write({"company_ids": co_cmds})
                if agence_co and user.company_id.id != agence_co.id:
                    user.sudo().write({"company_id": agence_co.id})
            if hasattr(hr_directors, "_sync_people_engine_role_groups"):
                hr_directors._sync_people_engine_role_groups()
            if hasattr(hr_directors, "_ensure_payroll_ma_groups"):
                hr_directors._ensure_payroll_ma_groups()
        crm_sales_users = (peers | hr_directors).filtered(
            lambda u: u.login not in DOORWAY_CRM_OWNER_LOGINS
        )
        if doorway_crm_sales and crm_sales_users:
            crm_gid = doorway_crm.id if doorway_crm else False
            sales_gid = doorway_crm_sales.id
            strip_gids = []
            for xid in (
                "sales_team.group_sale_manager",
                "sales_team.group_sale_salesman_all_leads",
            ):
                grp = self.env.ref(xid, raise_if_not_found=False)
                if grp:
                    strip_gids.append(grp.id)
            for user in crm_sales_users:
                gids = list(user.group_ids.ids)
                changed = False
                if sales_gid not in gids:
                    gids.append(sales_gid)
                    changed = True
                if crm_gid and crm_gid in gids:
                    gids = [g for g in gids if g != crm_gid]
                    changed = True
                stripped = [g for g in gids if g in strip_gids]
                if stripped:
                    gids = [g for g in gids if g not in strip_gids]
                    changed = True
                if changed:
                    user.sudo().write({"group_ids": [(6, 0, gids)]})
            digital_id = self.env["crm.team"]._doorway_digital_doorway_company_id()
            if digital_id:
                for user in peers:
                    if digital_id not in user.company_ids.ids:
                        user.sudo().write({"company_ids": [(4, digital_id)]})
                    if user.company_id.id != digital_id:
                        user.sudo().write({"company_id": digital_id})
        if pipeline_admin:
            for user in all_users.filtered(lambda u: pipeline_admin in u.group_ids):
                user.sudo().write({"group_ids": [(3, pipeline_admin.id)]})
        self.env["crm.team"]._setup_agence_doorway_pipelines()
        self.env["crm.team"]._assign_renovation_default_to_martin()
        self.env["crm.team"]._assign_marketing_default_to_zakaria()
        all_users._sync_pipeline_tab_groups()
        renovation = self.env.ref(
            "renovation_conciergerie.crm_team_renovation", raise_if_not_found=False
        )
        if renovation:
            all_users.filtered(lambda u: not u.sale_team_id).sudo().write(
                {"sale_team_id": renovation.id}
            )
