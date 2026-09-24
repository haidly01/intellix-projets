from odoo import api, fields, models
from odoo.osv import expression
from odoo.tools.safe_eval import safe_eval

from odoo.addons.renovation_conciergerie.models.res_users import (
    DOORWAY_CRM_OWNER_LOGINS,
    DOORWAY_CRM_PEER_SALES_LOGINS,
    DOORWAY_CRM_SALES_LOGINS,
)

PIPELINE_TEAM_XMLIDS = (
    "renovation_conciergerie.crm_team_renovation",
    "renovation_conciergerie.crm_team_immobilier",
    "renovation_conciergerie.crm_team_marketing",
    "renovation_conciergerie.crm_team_driven",
    "renovation_conciergerie.crm_team_doorway_b2b",
    "renovation_conciergerie.crm_team_assurance",
)

# Segment B2C : opportunités Rénovation, Assurance, Immobilier
B2C_PIPELINE_TEAM_XMLIDS = (
    "renovation_conciergerie.crm_team_renovation",
    "renovation_conciergerie.crm_team_assurance",
    "renovation_conciergerie.crm_team_immobilier",
)

# Segment B2B : Marketing, Doorway Clients, Driven
B2B_PIPELINE_TEAM_XMLIDS = (
    "renovation_conciergerie.crm_team_marketing",
    "renovation_conciergerie.crm_team_doorway_b2b",
    "renovation_conciergerie.crm_team_driven",
)

# Pipelines avec étapes Nouveau / Réseaux Sociaux / Retell / Site web / Qualification / Relance
PROVENANCE_PIPELINE_TEAM_XMLIDS = (
    "renovation_conciergerie.crm_team_renovation",
    "renovation_conciergerie.crm_team_immobilier",
    "renovation_conciergerie.crm_team_marketing",
    "renovation_conciergerie.crm_team_driven",
)

PROVENANCE_STAGE_SUFFIXES = (
    "new",
    "social",
    "retell",
    "website",
    "qualified",
    "followup",
)


def _provenance_stage_xmlid(team_xmlid, suffix):
    team_key = team_xmlid.rsplit(".", 1)[-1].replace("crm_team_", "")
    return f"renovation_conciergerie.crm_stage_{team_key}_{suffix}"


class CrmTeam(models.Model):
    _inherit = "crm.team"

    is_agence_doorway_pipeline = fields.Boolean(
        string="Pipeline Agence Doorway",
        default=False,
        help="Affiche cette équipe dans le sélecteur de pipelines CRM.",
    )
    uses_provenance_stages = fields.Boolean(
        string="Étapes par provenance",
        default=False,
        help="Kanban : Nouveau, Réseaux Sociaux, Agent IA, Site web, Qualification, Relance.",
    )
    doorway_segment = fields.Selection(
        [
            ("b2b", "B2B"),
            ("b2c", "B2C"),
        ],
        string="Segment Doorway",
        compute="_compute_doorway_segment",
        store=True,
    )

    @api.depends()
    def _compute_doorway_segment(self):
        b2c_ids = set(self._doorway_b2c_pipeline_team_ids())
        b2b_ids = set(self._doorway_b2b_pipeline_team_ids())
        for team in self:
            if team.id in b2c_ids:
                team.doorway_segment = "b2c"
            elif team.id in b2b_ids:
                team.doorway_segment = "b2b"
            else:
                team.doorway_segment = False

    @api.model
    def _doorway_pipeline_team_ids_from_xmlids(self, xmlids):
        ids = []
        for xmlid in xmlids:
            team = self.env.ref(xmlid, raise_if_not_found=False)
            if team:
                ids.append(team.id)
        return ids

    @api.model
    def _doorway_b2c_pipeline_team_ids(self):
        return self._doorway_pipeline_team_ids_from_xmlids(B2C_PIPELINE_TEAM_XMLIDS)

    @api.model
    def _doorway_b2b_pipeline_team_ids(self):
        return self._doorway_pipeline_team_ids_from_xmlids(B2B_PIPELINE_TEAM_XMLIDS)

    @api.model
    def doorway_segment_for_team(self, team):
        """Segment d'une opportunité selon son pipeline."""
        if not team:
            return False
        if team.id in self._doorway_b2c_pipeline_team_ids():
            return "b2c"
        if team.id in self._doorway_b2b_pipeline_team_ids():
            return "b2b"
        return False

    @api.model
    def _backfill_doorway_segment(self):
        teams = self.search([("is_agence_doorway_pipeline", "=", True)])
        if teams:
            teams._compute_doorway_segment()

    def _resync_pipeline_tab_groups(self):
        users = self.env["res.users"].sudo().search(
            [("share", "=", False), ("active", "=", True)]
        )
        users._sync_pipeline_tab_groups()

    @api.model_create_multi
    def create(self, vals_list):
        teams = super().create(vals_list)
        teams._resync_pipeline_tab_groups()
        return teams

    def write(self, vals):
        res = super().write(vals)
        if "user_id" in vals:
            self._resync_pipeline_tab_groups()
        return res

    @api.model
    def _assign_renovation_default_to_martin(self):
        """Pipeline Rénovation : nouveaux leads assignés à Martin par défaut."""
        team = self.env.ref(
            "renovation_conciergerie.crm_team_renovation",
            raise_if_not_found=False,
        )
        martin = self.env["res.users"].sudo().search(
            [
                ("login", "=", "martin@agencedoorway.com"),
                ("active", "=", True),
                ("share", "=", False),
            ],
            limit=1,
        )
        if team and martin:
            team.write({"user_id": martin.id})

    @api.model
    def _assign_marketing_default_to_zakaria(self):
        """Desactive : Zakaria = pipeline Coins Marocain seulement."""
        return
        """Pipeline Marketing : Zakaria responsable + equipe commerciale par defaut."""
        team = self.env.ref(
            "renovation_conciergerie.crm_team_marketing",
            raise_if_not_found=False,
        )
        zakaria = self.env["res.users"].sudo().search(
            [
                ("login", "=", "zakaria@agencedoorway.com"),
                ("active", "=", True),
                ("share", "=", False),
            ],
            limit=1,
        )
        if not team or not zakaria:
            return
        team.write({"user_id": zakaria.id})
        zakaria.write({"sale_team_id": team.id})
        if zakaria.id not in team.crm_team_member_ids.mapped("user_id").ids:
            self.env["crm.team.member"].sudo().create(
                {"crm_team_id": team.id, "user_id": zakaria.id}
            )

    def _get_default_assignee(self):
        """Vendeur par défaut pour les leads entrants (webhooks, etc.)."""
        self.ensure_one()
        if self.user_id and not self.user_id.share:
            return self.user_id
        members = self.crm_team_member_ids.user_id.filtered(
            lambda u: u.active and not u.share
        )
        return members[:1]

    @api.model
    def _fix_webhook_leads_company(self):
        """Aligne la société des leads webhook (société du vendeur assigné)."""
        team_ids = []
        for xmlid in (
            "renovation_conciergerie.crm_team_renovation",
            "renovation_conciergerie.crm_team_marketing",
        ):
            team = self.env.ref(xmlid, raise_if_not_found=False)
            if team:
                team_ids.append(team.id)
        if not team_ids:
            return
        leads = self.env["crm.lead"].sudo().search(
            [
                ("team_id", "in", team_ids),
                ("lead_provenance", "in", ["website", "retell"]),
            ]
        )
        for lead in leads:
            company = (
                lead.team_id.company_id
                or lead.user_id.company_id
                or self.env.company
            )
            if company and lead.company_id != company:
                lead.company_id = company

    @api.model
    def _fix_webhook_leads_without_salesperson(self):
        """Réassigne les leads créés par webhook sans vendeur (ex. user public)."""
        public_user = self.env.ref("base.public_user", raise_if_not_found=False)
        domain = [
            ("team_id.is_agence_doorway_pipeline", "=", True),
            "|",
            ("user_id", "=", False),
            ("user_id", "=", public_user.id if public_user else 0),
        ]
        for lead in self.env["crm.lead"].sudo().search(domain):
            assignee = lead.team_id._get_default_assignee()
            if assignee:
                lead.user_id = assignee

    @api.model
    def _get_agence_doorway_crm_global_users(self):
        """Vue CRM globale (Karine) : tous les leads, tous les vendeurs."""
        return self.env["res.users"].sudo().search(
            [
                ("share", "=", False),
                ("active", "=", True),
                ("login", "in", DOORWAY_CRM_OWNER_LOGINS),
            ]
        )

    @api.model
    def _get_agence_doorway_pipeline_users(self):
        """Accès pipelines Doorway (favoris, membres d'équipe) sans vue globale."""
        return self.env["res.users"].sudo().search(
            [
                ("share", "=", False),
                ("active", "=", True),
                ("login", "in", DOORWAY_CRM_SALES_LOGINS),
            ]
        )

    @api.model
    def _get_agence_doorway_admin_users(self):
        """Compat : utilisateurs à inclure dans la configuration des pipelines."""
        return self._get_agence_doorway_pipeline_users()

    @api.model
    def _setup_agence_doorway_pipelines(self):
        """Membres, favoris et équipe commerciale pour l'équipe CRM Doorway."""
        pipeline_users = self._get_agence_doorway_pipeline_users()
        global_users = self._get_agence_doorway_crm_global_users()
        doorway_group = self.env.ref(
            "renovation_conciergerie.group_agence_doorway_crm",
            raise_if_not_found=False,
        )
        if doorway_group:
            to_grant = global_users.filtered(
                lambda u: doorway_group not in u.all_group_ids
            )
            if to_grant:
                to_grant.write({"group_ids": [(4, doorway_group.id)]})
        users = pipeline_users
        teams = self.env["crm.team"]
        for xmlid in PIPELINE_TEAM_XMLIDS:
            team = self.env.ref(xmlid, raise_if_not_found=False)
            if team:
                teams |= team
        if not teams or not users:
            return

        Member = self.env["crm.team.member"]
        for team in teams:
            team.write(
                {
                    "use_leads": True,
                    "use_opportunities": True,
                    "is_agence_doorway_pipeline": True,
                    "favorite_user_ids": [(4, user.id) for user in users],
                }
            )
            existing_user_ids = set(team.crm_team_member_ids.mapped("user_id").ids)
            for user in users:
                if user.id in existing_user_ids:
                    continue
                Member.create({"crm_team_id": team.id, "user_id": user.id})

        default_team = self.env.ref(
            "renovation_conciergerie.crm_team_renovation", raise_if_not_found=False
        )
        if default_team:
            users.filtered(lambda u: not u.sale_team_id).write(
                {"sale_team_id": default_team.id}
            )
            if not default_team.company_id:
                main_company = self.env["res.company"].search(
                    [("name", "ilike", "Agence Doorway")], limit=1
                )
                if main_company:
                    default_team.company_id = main_company

        for team_xmlid in PROVENANCE_PIPELINE_TEAM_XMLIDS:
            team = self.env.ref(team_xmlid, raise_if_not_found=False)
            if team:
                team.uses_provenance_stages = True
        doorway = self.env.ref(
            "renovation_conciergerie.crm_team_doorway_b2b", raise_if_not_found=False
        )
        if doorway:
            doorway.uses_provenance_stages = False
        self._assign_marketing_default_to_zakaria()

    @api.model
    def _cleanup_team_provenance_stages(self, team_xmlid):
        team = self.env.ref(team_xmlid, raise_if_not_found=False)
        if not team:
            return
        keep_xmlids = [
            _provenance_stage_xmlid(team_xmlid, suffix)
            for suffix in PROVENANCE_STAGE_SUFFIXES
        ]
        keep_ids = {
            self.env.ref(xmlid, raise_if_not_found=False).id
            for xmlid in keep_xmlids
            if self.env.ref(xmlid, raise_if_not_found=False)
        }
        extra_stages = self.env["crm.stage"].search(
            [("team_ids", "in", team.id), ("id", "not in", list(keep_ids))]
        )
        if not extra_stages:
            return
        default_stage = self.env.ref(
            _provenance_stage_xmlid(team_xmlid, "new"), raise_if_not_found=False
        )
        if default_stage:
            leads = self.env["crm.lead"].search(
                [("team_id", "=", team.id), ("stage_id", "in", extra_stages.ids)]
            )
            for lead in leads:
                lead.write({"stage_id": default_stage.id})
        still_used = extra_stages.filtered(
            lambda s: self.env["crm.lead"].with_context(active_test=False).search_count(
                [("stage_id", "=", s.id)]
            )
        )
        if still_used:
            still_used.write({"team_ids": [(3, team.id)]})
        to_unlink = extra_stages - still_used
        if to_unlink:
            to_unlink.unlink()

    @api.model
    def _cleanup_all_provenance_stages(self):
        for team_xmlid in PROVENANCE_PIPELINE_TEAM_XMLIDS:
            self._cleanup_team_provenance_stages(team_xmlid)

    @api.model
    def _cleanup_doorway_dedicated_stages(self):
        """Doorway Clients : étapes génériques Odoo uniquement."""
        doorway = self.env.ref(
            "renovation_conciergerie.crm_team_doorway_b2b", raise_if_not_found=False
        )
        if not doorway:
            return
        dedicated = self.env["crm.stage"].search([("team_ids", "in", doorway.id)])
        if not dedicated:
            return
        generic_new = self.env["crm.stage"].search(
            [("team_ids", "=", False)], order="sequence, id", limit=1
        )
        if generic_new:
            leads = self.env["crm.lead"].search(
                [("team_id", "=", doorway.id), ("stage_id", "in", dedicated.ids)]
            )
            for lead in leads:
                lead.write({"stage_id": generic_new.id})
        dedicated.write({"team_ids": [(5, 0, 0)]})

    @api.model
    def _migrate_leads_off_generic_stages(self):
        """Déplace les opportunités des étapes génériques vers la 1re étape du pipeline."""
        generic_ids = self.env["crm.stage"].search([("team_ids", "=", False)]).ids
        if not generic_ids:
            return
        teams = self.env["crm.team"].search([("uses_provenance_stages", "=", True)])
        for team in teams:
            first_stage = self.env["crm.stage"].search(
                [("team_ids", "in", team.id)], order="sequence, id", limit=1
            )
            if not first_stage:
                continue
            leads = self.env["crm.lead"].search(
                [
                    ("team_id", "=", team.id),
                    ("stage_id", "in", generic_ids),
                ]
            )
            if leads:
                for lead in leads:
                    lead.write({"stage_id": first_stage.id})

    @api.model
    def _doorway_digital_doorway_company_id(self):
        """Société Digital Doorway (leads Maroc / Marketing)."""
        main = self.env.ref("base.main_company", raise_if_not_found=False)
        if main and "digital" in (main.name or "").lower():
            return main.id
        company = self.env["res.company"].search(
            [("name", "ilike", "Digital Doorway")], limit=1
        )
        return company.id if company else False

    @api.model
    def _doorway_pipeline_allowed_company_ids(self, include_digital_doorway=False):
        """Sociétés actives : super-admins CRM = toutes leurs sociétés (+ Digital Doorway si besoin)."""
        user = self.env.user
        if user._doorway_is_crm_superuser():
            allowed = list(user._get_company_ids())
        else:
            allowed = list(user.company_ids.ids)
        if include_digital_doorway or user._doorway_is_crm_peer_sales_user():
            digital_id = self._doorway_digital_doorway_company_id()
            if digital_id:
                allowed = list(set(allowed + [digital_id]))
        return allowed

    @api.model
    def _doorway_parse_action_context(self, context):
        """Contexte d'action : chaîne (XML) ou dict déjà évalué (_get_action_dict / read)."""
        if not context:
            return {}
        if isinstance(context, dict):
            return dict(context)
        return safe_eval(context, {"uid": self.env.uid})

    @api.model
    def _doorway_parse_action_domain(self, domain):
        if not domain:
            return []
        if isinstance(domain, list):
            return list(domain)
        return safe_eval(domain, {"uid": self.env.uid})

    @api.model
    def _doorway_peer_sales_lead_domain(self):
        """Martin / Zakaria : évite les cartes « top secret » (leads de l'autre vendeur)."""
        user = self.env.user
        if user._doorway_is_crm_superuser():
            return []
        if user._doorway_is_crm_peer_sales_user():
            return ["|", ("user_id", "=", user.id), ("user_id", "=", False)]
        return []

    @api.model
    def _action_open_doorway_pipeline(self, action_xmlid, include_digital_doorway=False):
        action = self.env["ir.actions.actions"]._for_xml_id(action_xmlid)
        ctx = self._doorway_parse_action_context(action.get("context"))
        ctx["allowed_company_ids"] = self._doorway_pipeline_allowed_company_ids(
            include_digital_doorway=include_digital_doorway
        )
        peer_domain = self._doorway_peer_sales_lead_domain()
        if peer_domain:
            base_domain = self._doorway_parse_action_domain(action.get("domain"))
            action["domain"] = expression.AND([base_domain, peer_domain])
            ctx["search_default_assigned_to_me"] = 1
        action["context"] = ctx
        return action

    @api.model
    def action_open_doorway_pipeline_marketing(self):
        """Menu Marketing : accès multi-sociétés (Digital Doorway + sociétés de l'utilisateur)."""
        return self._action_open_doorway_pipeline(
            "renovation_conciergerie.doorway_action_pipeline_marketing",
            include_digital_doorway=True,
        )

    @api.model
    def action_your_pipeline(self):
        """Vue CRM Doorway : tous les pipelines combinés (sans filtre d'équipe)."""
        action = super().action_your_pipeline()
        if not self.env.user.has_group(
            "renovation_conciergerie.group_agence_doorway_crm"
        ) and not self.env.user.has_group(
            "renovation_conciergerie.group_agence_doorway_crm_sales"
        ):
            return action
        all_action = self.env["ir.actions.actions"]._for_xml_id(
            "renovation_conciergerie.doorway_action_pipeline_all"
        )
        action["domain"] = self._doorway_parse_action_domain(all_action.get("domain"))
        ctx = self._doorway_parse_action_context(all_action.get("context"))
        action["context"] = self.env["crm.lead"]._doorway_all_pipelines_action_context(
            ctx
        )
        action["display_name"] = all_action.get("name") or action.get("display_name")
        return action


class CrmTeamMember(models.Model):
    _inherit = "crm.team.member"

    def _resync_pipeline_tab_groups(self):
        self.env["res.users"].sudo().search(
            [("share", "=", False), ("active", "=", True)]
        )._sync_pipeline_tab_groups()

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        records._resync_pipeline_tab_groups()
        return records

    def unlink(self):
        teams_users = self.mapped("user_id")
        res = super().unlink()
        if teams_users:
            self.env["res.users"].sudo().search(
                [("share", "=", False), ("active", "=", True)]
            )._sync_pipeline_tab_groups()
        return res
