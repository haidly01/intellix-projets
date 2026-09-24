# -*- coding: utf-8 -*-





def _rename_extracteur_branding(env):

    """Renomme les libellés Leads Bruts existants en Extracteur."""

    for xmlid, label in (

        ("doorway_leads_bruts.module_category_leads_bruts", "Extracteur"),

        ("doorway_leads_bruts.res_groups_privilege_leads_bruts", "Extracteur"),

    ):

        rec = env.ref(xmlid, raise_if_not_found=False)

        if rec and rec.name != label:

            rec.sudo().write({"name": label})

    Config = env["doorway.credit.config"].sudo()

    for config in Config.search([("name", "ilike", "Leads Bruts")]):

        config.write({"name": config.name.replace("Leads Bruts", "Extracteur")})





def _sync_leads_bruts_access(env):

    """Accorde Extracteur aux admins Odoo et à l'équipe Agence Doorway CRM."""

    admin = env.ref("base.user_admin", raise_if_not_found=False)

    user_group = env.ref("doorway_leads_bruts.group_leads_bruts_user", raise_if_not_found=False)

    mgr_group = env.ref("doorway_leads_bruts.group_leads_bruts_manager", raise_if_not_found=False)

    group_xmlids = (

        "renovation_conciergerie.group_agence_doorway_crm",

        "renovation_conciergerie.group_agence_doorway_crm_sales",

        "doorway_vicidial_campaigns.group_vicidial_qualifier",

    )

    extra_logins = (

        "zakaria@agencedoorway.com",

        "karine@agencedoorway.com",

        "leiladaouadi@gmail.com",

    )

    if not user_group:

        return



    users = admin

    for xmlid in group_xmlids:

        grp = env.ref(xmlid, raise_if_not_found=False)

        if grp:

            users |= grp.user_ids



    for login in extra_logins:

        user = env["res.users"].sudo().search([("login", "=", login)], limit=1)

        if user:

            users |= user



    for user in users:

        if not user.active or user.share:

            continue

        commands = [(4, user_group.id)]

        if mgr_group:

            commands.append((4, mgr_group.id))

        user.write({"group_ids": commands})





def _import_initial_crm_leads(env):

    """Importe les opportunités CRM existantes si aucun lead brut n'est enregistré."""

    if env["doorway.leads.bruts"].sudo().search_count([]):

        return

    env["doorway.campagne.extraction"].sudo().import_from_crm_doorway(limit=500)





def _backfill_dedup_keys(env):

    """Remplit dedup_key sur les leads existants (anti-doublon inter-campagnes)."""

    Campagne = env["doorway.campagne.extraction"]

    Leads = env["doorway.leads.bruts"].sudo()

    for lead in Leads.search([("dedup_key", "in", [False, ""])]):

        key = Campagne._lead_dedup_key(lead)

        if not key:

            continue

        if Leads.search_count([("dedup_key", "=", key), ("id", "!=", lead.id)]):

            continue

        lead.write({"dedup_key": key})





def _reassign_marketing_extracteur_leads(env):

    """Les imports CRM initiaux gardent l'ancien vendeur — on force Zakaria."""

    if "doorway.leads.bruts.crm.export" not in env.registry:

        return

    env["doorway.leads.bruts.crm.export"].reassign_marketing_extracteur_leads()





def post_init_hook(env):

    _rename_extracteur_branding(env)

    _sync_leads_bruts_access(env)

    _backfill_dedup_keys(env)

    _import_initial_crm_leads(env)

    _reassign_marketing_extracteur_leads(env)

