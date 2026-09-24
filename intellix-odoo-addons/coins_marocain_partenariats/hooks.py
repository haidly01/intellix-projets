# -*- coding: utf-8 -*-
"""Lier l'équipe Coins Marocain existante et restreindre Zakaria à ce pipeline."""


def _bind_team_xmlid(env):
    Imd = env["ir.model.data"].sudo()
    Team = env["crm.team"].sudo()
    rec = Imd.search(
        [
            ("module", "=", "coins_marocain_partenariats"),
            ("name", "=", "crm_team_coins_marocain"),
        ],
        limit=1,
    )
    existing = Team.search([("name", "=", "Coins Marocain")], order="id asc")
    if len(existing) > 1 and rec:
        keep = Team.browse(rec.res_id) if rec.res_id in existing.ids else existing[0]
        extras = existing - keep
        env["crm.lead"].sudo().search([("team_id", "in", extras.ids)]).write(
            {"team_id": keep.id}
        )
        extras.write({"active": False})
        if rec.res_id != keep.id:
            rec.res_id = keep.id
        return keep
    return Team.browse(rec.res_id) if rec else existing[:1]


def setup_zakaria_coins_pipeline(env):
    team = _bind_team_xmlid(env)
    if not team:
        return
    user = env["res.users"].sudo().search(
        [("login", "=", "zakaria@agencedoorway.com")], limit=1
    )
    if not user:
        return

    Member = env["crm.team.member"].sudo()
    team_voy = env.ref(
        "coins_marocain_partenariats.crm_team_coins_voyageurs",
        raise_if_not_found=False,
    )
    keep_teams = team
    if team_voy:
        keep_teams |= team_voy
        if "is_agence_doorway_pipeline" in team_voy._fields:
            team_voy.is_agence_doorway_pipeline = False
    others = Member.search(
        [("user_id", "=", user.id), ("crm_team_id", "not in", keep_teams.ids)]
    )
    others.write({"active": False})
    for keep in keep_teams:
        if not Member.search(
            [("user_id", "=", user.id), ("crm_team_id", "=", keep.id)]
        ):
            Member.create({"user_id": user.id, "crm_team_id": keep.id})
    if "is_agence_doorway_pipeline" in team._fields:
        team.is_agence_doorway_pipeline = False
    team.user_id = user.id
    user.sale_team_id = team.id
    if "doorway_assigned_pipeline_ids" in user._fields:
        user.doorway_assigned_pipeline_ids = [(6, 0, keep_teams.ids)]

    drop_xmlids = [
        "renovation_conciergerie.group_agence_doorway_crm",
        "renovation_conciergerie.group_pipeline_admin",
        "renovation_conciergerie.group_pipeline_supervisor",
        "renovation_conciergerie.group_pipeline_tab_renovation",
        "renovation_conciergerie.group_pipeline_tab_immobilier",
        "renovation_conciergerie.group_pipeline_tab_marketing",
        "renovation_conciergerie.group_pipeline_tab_driven",
        "renovation_conciergerie.group_pipeline_tab_doorway_b2b",
        "renovation_conciergerie.group_pipeline_tab_assurance",
        "doorway_hiba_qualif.group_pipeline_tab_coins_quebec",
        "doorway_leads_bruts.group_admin_commercial",
        "renovation_conciergerie.group_agence_doorway_crm_sales",
    ]
    drop_groups = env["res.groups"].sudo()
    for xid in drop_xmlids:
        grp = env.ref(xid, raise_if_not_found=False)
        if grp:
            drop_groups |= grp
    keep_xmlids = [
        "coins_marocain_partenariats.group_pipeline_tab_coins_marocain",
        "coins_marocain.group_coins_user",
        "coins_marocain.group_coins_agent_terrain",
        "renovation_conciergerie.group_doorway_pipeline_assigned",
    ]
    keep_groups = env["res.groups"].sudo()
    for xid in keep_xmlids:
        grp = env.ref(xid, raise_if_not_found=False)
        if grp:
            keep_groups |= grp
    # SQL : un write ORM res.users re-accorde la vue globale (groupe system).
    if drop_groups:
        env.cr.execute(
            "DELETE FROM res_groups_users_rel WHERE uid=%s AND gid = ANY(%s)",
            [user.id, drop_groups.ids],
        )
    if keep_groups:
        for gid in keep_groups.ids:
            env.cr.execute(
                "INSERT INTO res_groups_users_rel (uid, gid) "
                "SELECT %s, %s WHERE NOT EXISTS ("
                "SELECT 1 FROM res_groups_users_rel WHERE uid=%s AND gid=%s)",
                [user.id, gid, user.id, gid],
            )

    stage_new = env.ref(
        "coins_marocain_partenariats.crm_stage_cm_nouveau",
        raise_if_not_found=False,
    )
    team_voy = env.ref(
        "coins_marocain_partenariats.crm_team_coins_voyageurs",
        raise_if_not_found=False,
    )
    stage_voy_new = env.ref(
        "coins_marocain_partenariats.crm_stage_voy_nouveau",
        raise_if_not_found=False,
    )
    Lead = env["crm.lead"].sudo()
    events = Lead.search(
        [
            ("user_id", "=", user.id),
            ("active", "=", True),
            "|",
            ("name", "ilike", "[Événement]"),
            ("team_id.name", "=", "Événements"),
        ]
    )
    if events:
        vals = {"team_id": team.id, "coins_fiche_type": "evenement"}
        if stage_new:
            vals["stage_id"] = stage_new.id
        events.write(vals)
    concierge = Lead.search(
        [
            ("user_id", "=", user.id),
            ("active", "=", True),
            ("name", "ilike", "Concierge"),
        ]
    )
    if concierge:
        vals = {"coins_fiche_type": "voyageur"}
        if team_voy:
            vals["team_id"] = team_voy.id
        if stage_voy_new:
            vals["stage_id"] = stage_voy_new.id
        concierge.write(vals)
    leftovers = Lead.search(
        [
            ("user_id", "=", user.id),
            ("active", "=", True),
            ("team_id", "not in", keep_teams.ids),
            ("coins_fiche_type", "!=", "voyageur"),
        ]
    )
    if leftovers:
        vals = {"team_id": team.id}
        if stage_new:
            vals["stage_id"] = stage_new.id
        leftovers.write(vals)


def setup_coins_info_alias(env):
    """info@coinsmarocain.com reçoit aussi les leads voyageurs à traiter."""
    Alias = env["mail.alias"].sudo()
    aliases = Alias.search(
        [
            ("alias_name", "=", "info"),
            ("alias_model_id.model", "=", "crm.lead"),
        ]
    )
    coins = aliases.filtered(
        lambda a: (a.alias_domain_id.name or "") == "coinsmarocain.com"
    )
    team = env.ref(
        "coins_marocain_partenariats.crm_team_coins_marocain",
        raise_if_not_found=False,
    )
    for alias in coins or aliases.filtered(
        lambda a: team and "team_id" in (a.alias_defaults or {}) and team.id in str(a.alias_defaults)
    ):
        alias.alias_contact = "everyone"


def _add_group(env, user, group):
    if not user or not group or user.id in group.user_ids.ids:
        return
    env.cr.execute(
        "INSERT INTO res_groups_users_rel (uid, gid) "
        "SELECT %s, %s WHERE NOT EXISTS ("
        "SELECT 1 FROM res_groups_users_rel WHERE uid=%s AND gid=%s)",
        [user.id, group.id, user.id, group.id],
    )


def setup_coins_pipeline_users(env):
    """Karine Barmaki et Zakaria doivent écrire stage_id sur les leads CM."""
    tab = env.ref(
        "coins_marocain_partenariats.group_pipeline_tab_coins_marocain",
        raise_if_not_found=False,
    )
    all_leads = env.ref(
        "sales_team.group_sale_salesman_all_leads", raise_if_not_found=False
    )
    salesman = env.ref("sales_team.group_sale_salesman", raise_if_not_found=False)
    User = env["res.users"].sudo()
    for login in (
        "karine@agencedoorway.com",
        "zakaria@agencedoorway.com",
        "zakaria@coinsmarocain.com",
    ):
        user = User.search([("login", "=", login)], limit=1)
        if not user:
            continue
        _add_group(env, user, tab)
        _add_group(env, user, salesman)
        _add_group(env, user, all_leads)


def setup_devis_workspace(env):
    """Contacts restreints + menus Zak (CRM, Ventes, Hébergement, Coins, Messages)."""
    own = env.ref(
        "coins_marocain_partenariats.group_devis_own_contacts",
        raise_if_not_found=False,
    )
    workspace = env.ref(
        "coins_marocain_partenariats.group_devis_workspace",
        raise_if_not_found=False,
    )
    riad = env.ref("intellix_riad.group_riad_user", raise_if_not_found=False)
    manager = env.ref("sales_team.group_sale_manager", raise_if_not_found=False)
    salesman = env.ref("sales_team.group_sale_salesman", raise_if_not_found=False)
    all_leads = env.ref(
        "sales_team.group_sale_salesman_all_leads", raise_if_not_found=False
    )
    assigned = env.ref(
        "renovation_conciergerie.group_doorway_pipeline_assigned",
        raise_if_not_found=False,
    )
    User = env["res.users"].sudo()
    # Compte limité devis uniquement — pas zakaria@agencedoorway.com
    # (il doit voir toutes les apps, comme Karine et Martin).
    zak_workspace = User.search(
        [
            (
                "login",
                "in",
                (
                    "zakaria@coinsmarocain.com",
                ),
            )
        ]
    )
    if workspace:
        for user in zak_workspace:
            _add_group(env, user, workspace)
    zak_coins = User.search([("login", "=", "zakaria@coinsmarocain.com")], limit=1)
    if riad and zak_coins:
        _add_group(env, zak_coins, riad)

    skip_ids = set()
    if manager:
        skip_ids.update(manager.user_ids.ids)
    skip_ids.update(
        User.search(
            [
                (
                    "login",
                    "in",
                    (
                        "zakaria@agencedoorway.com",
                        "karine@agencedoorway.com",
                        "admin",
                    ),
                )
            ]
        ).ids
    )
    skip_ids.add(env.ref("base.user_admin").id)
    skip_ids.add(env.ref("base.user_root").id)

    candidates = User.browse()
    for grp in (salesman, all_leads, assigned):
        if grp:
            candidates |= grp.user_ids
    candidates = candidates.filtered(
        lambda u: u.active and not u.share and u.id not in skip_ids
    )
    if own:
        for user in candidates:
            _add_group(env, user, own)

    for user in zak_workspace | candidates:
        leads = env["crm.lead"].sudo().search(
            [("user_id", "=", user.id), ("partner_id", "!=", False)]
        )
        partners = leads.mapped("partner_id").filtered(lambda p: not p.user_id)
        if partners:
            partners.write({"user_id": user.id})

    env.registry.clear_cache()


def fix_quebec_entente_clauses(env):
    """Corrige la fuite du texte Maroc vers les ententes Québec non signées."""
    Entente = env["coins.entente"].sudo()
    if "clauses_html" not in Entente._fields:
        return
    for rec in Entente.search(
        [
            ("type_partenaire", "=", "hebergement"),
            ("date_signature", "=", False),
        ]
    ):
        if not rec._coins_is_quebec_entente():
            continue
        if rec._coins_clauses_are_quebec(rec.clauses_html):
            continue
        rec.clauses_html = rec._coins_default_clauses_html()


def post_init_hook(env):
    setup_zakaria_coins_pipeline(env)
    setup_coins_pipeline_users(env)
    setup_coins_info_alias(env)
    env["crm.lead"]._coins_align_partnership_stages()
    setup_devis_workspace(env)
    fix_quebec_entente_clauses(env)
