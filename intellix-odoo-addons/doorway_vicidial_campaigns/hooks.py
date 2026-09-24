# -*- coding: utf-8 -*-

_LEILA_VICIDIAL_LOGIN = "leiladaouadi"
_LEILA_ONLY_CAMPAIGN = "DW_FRB2C"
_LEILA_PHONE_EXTENSION = "86021"


def _leila_agent(env):
    return env["doorway.campaign.agent.user"].sudo().search(
        [("vicidial_user", "=", _LEILA_VICIDIAL_LOGIN)], limit=1
    )


def _ensure_leila_france_only(env):
    """Disabled: Leila now has France B2B (DW_FRB2B) in addition to B2C — no campaign lock."""
    return
    leila = _leila_agent(env)
    if not leila:
        return
    frb2c = env["doorway.campaign"].sudo().search(
        [("vicidial_campaign_id", "=", _LEILA_ONLY_CAMPAIGN)], limit=1
    )
    if frb2c:
        env.cr.execute(
            "DELETE FROM campaign_human_agent_rel WHERE agent_id = %s AND campaign_id != %s",
            (leila.id, frb2c.id),
        )
        if leila not in frb2c.human_agent_ids:
            frb2c.write({"human_agent_ids": [(4, leila.id)]})
    from odoo.addons.doorway_vicidial_campaigns.services.vicidial_service import (
        VicidialService,
    )

    svc = VicidialService(env)
    if not svc.is_available():
        return
    conn = svc._connect()
    try:
        cur = conn.cursor()
        cur.execute(
            "DELETE FROM vicidial_campaign_agents WHERE user = %s AND campaign_id != %s",
            (_LEILA_VICIDIAL_LOGIN, _LEILA_ONLY_CAMPAIGN),
        )
        cur.execute(
            """
            SELECT 1 FROM vicidial_campaign_agents
            WHERE user = %s AND campaign_id = %s LIMIT 1
            """,
            (_LEILA_VICIDIAL_LOGIN, _LEILA_ONLY_CAMPAIGN),
        )
        if not cur.fetchone():
            cur.execute(
                """
                INSERT INTO vicidial_campaign_agents (
                    user, campaign_id, campaign_rank, campaign_weight, campaign_grade
                ) VALUES (%s, %s, 1, 10, 1)
                """,
                (_LEILA_VICIDIAL_LOGIN, _LEILA_ONLY_CAMPAIGN),
            )
        cur.execute(
            "UPDATE vicidial_users SET phone_login = %s, active = 'Y' WHERE user = %s",
            (_LEILA_PHONE_EXTENSION, _LEILA_VICIDIAL_LOGIN),
        )
        conn.commit()
        cur.close()
    finally:
        conn.close()


def _ensure_vicidial_tags(env):

    Tag = env["crm.tag"].sudo()

    old_tag = Tag.search([("name", "=", "VICIdial")], limit=1)
    if old_tag and not Tag.search([("name", "=", "Appels")], limit=1):
        old_tag.write({"name": "Appels"})

    for name, color in (("Appels", 4), ("France", 2), ("À qualifier", 1)):
        if not Tag.search([("name", "=", name)], limit=1):
            Tag.create({"name": name, "color": color})





def _ensure_human_france_campaigns(env):

    """Campagnes humaines France visibles sur le poste VICIdial."""

    Campaign = env["doorway.campaign"].sudo()

    specs = (

        {

            "xmlid": "doorway_vicidial_campaigns.campaign_renovation",

            "name": "Rénovation — sortants",

            "vicidial_campaign_id": "DW_RENOV",

            "pipeline": "renovation",

            "campaign_mode": "mixed",

        },

        {

            "xmlid": None,

            "name": "Thermopompe — sortants France",

            "vicidial_campaign_id": "DW_THERM",

            "pipeline": "thermopompe",

            "campaign_mode": "human_agent",

        },

        {

            "xmlid": None,

            "name": "Photovoltaïque — sortants France",

            "vicidial_campaign_id": "DW_PV",

            "pipeline": "toitures",

            "campaign_mode": "human_agent",

        },

    )

    campaigns = Campaign.browse()

    for spec in specs:

        camp = False

        if spec["xmlid"]:

            camp = env.ref(spec["xmlid"], raise_if_not_found=False)

        if not camp:

            camp = Campaign.search(

                [("vicidial_campaign_id", "=", spec["vicidial_campaign_id"])],

                limit=1,

            )

        vals = {

            "name": spec["name"],

            "vicidial_campaign_id": spec["vicidial_campaign_id"],

            "pipeline": spec["pipeline"],

            "campaign_mode": spec["campaign_mode"],

            "state": "ready",

        }

        if camp:

            camp.write(vals)

        else:

            camp = Campaign.create(vals)

        campaigns |= camp

    return campaigns





def _link_qualifiers_to_human_campaigns(env, agents):

    campaigns = _ensure_human_france_campaigns(env)

    if not agents or not campaigns:

        return

    leila = agents.filtered(lambda a: a.vicidial_user == _LEILA_VICIDIAL_LOGIN)
    others = agents - leila
    for camp in campaigns:
        ids = list(others.ids)
        if camp.vicidial_campaign_id == _LEILA_ONLY_CAMPAIGN and leila:
            ids.append(leila.id)
        camp.write({"human_agent_ids": [(6, 0, ids)]})


def _ensure_door_app0_qualifier_campaigns(env):
    """France B2C + Québec B2C visibles sur le poste d'appels (qualificateurs actifs)."""
    Campaign = env["doorway.campaign"].sudo()
    agents = env["doorway.campaign.agent.user"].sudo().search(
        [("vicidial_qualification_active", "=", True), ("active", "=", True)]
    )
    if not agents:
        return
    specs = (
        ("DW_FRB2C", {"campaign_mode": "mixed", "state": "active"}),
        ("DW_QCB2C", {"campaign_mode": "mixed", "state": "active"}),
    )
    import os

    hostinger_flags = {
        "DW_QCB2C": "/opt/doorway/LEA_QC_HOSTINGER_ONLY.flag",
        "DW_QCB2B": "/opt/doorway/ALEX_HOSTINGER_ONLY.flag",
    }
    for vici_id, vals in specs:
        if os.path.isfile(hostinger_flags.get(vici_id, "")):
            vals = dict(vals, state="paused")
        camp = Campaign.search([("vicidial_campaign_id", "=", vici_id)], limit=1)
        if not camp:
            continue
        camp.write(vals)
        to_add = agents
        if vici_id != _LEILA_ONLY_CAMPAIGN:
            to_add = agents.filtered(
                lambda a: a.vicidial_user != _LEILA_VICIDIAL_LOGIN
            )
        camp.write({"human_agent_ids": [(4, a.id) for a in to_add]})
        if vici_id == _LEILA_ONLY_CAMPAIGN:
            leila = agents.filtered(lambda a: a.vicidial_user == _LEILA_VICIDIAL_LOGIN)
            if leila:
                camp.write({"human_agent_ids": [(4, leila.id)]})
    _sync_vicidial_qualifier_campaign_access(env, agents)
    _ensure_leila_france_only(env)


def _sync_vicidial_qualifier_campaign_access(env, agents):
    """VICIdial : campagnes autorisées + vicidial_campaign_agents pour les qualificateurs."""
    from odoo.addons.doorway_vicidial_campaigns.services.vicidial_service import (
        VicidialService,
    )

    svc = VicidialService(env)
    if not svc.is_available():
        return
    campaign_ids = ("DW_FRB2C", "DW_QCB2C")
    conn = svc._connect()
    try:
        cur = conn.cursor()
        cur.execute(
            """
            UPDATE vicidial_user_groups
            SET allowed_campaigns = %s
            WHERE user_group = 'AGENTS'
            """,
            (" %s %s - -" % campaign_ids,),
        )
        for agent in agents:
            login = (agent.vicidial_user or "").strip()[:20]
            if not login:
                continue
            allowed = (
                (_LEILA_ONLY_CAMPAIGN,)
                if login == _LEILA_VICIDIAL_LOGIN
                else campaign_ids
            )
            for cid in allowed:
                cur.execute(
                    """
                    SELECT 1 FROM vicidial_campaign_agents
                    WHERE user = %s AND campaign_id = %s LIMIT 1
                    """,
                    (login, cid),
                )
                if not cur.fetchone():
                    cur.execute(
                        """
                        INSERT INTO vicidial_campaign_agents (
                            user, campaign_id, campaign_rank, campaign_weight, campaign_grade
                        ) VALUES (%s, %s, 1, 10, 1)
                        """,
                        (login, cid),
                    )
            cur.execute(
                """
                UPDATE vicidial_users
                SET change_agent_campaign = '1'
                WHERE user = %s AND change_agent_campaign = '0'
                """,
                (login,),
            )
        conn.commit()
        cur.close()
    finally:
        conn.close()


def _ensure_agent_user(env, user, vicidial_user, team, stage, group):

    AgentUser = env["doorway.campaign.agent.user"].sudo()

    if not user or not vicidial_user:

        return AgentUser.browse()



    if group and group not in user.group_ids:

        user.write({"group_ids": [(4, group.id)]})

    pe_group = env.ref("people_engine.group_employee", raise_if_not_found=False)

    if pe_group and pe_group not in user.group_ids:

        user.write({"group_ids": [(4, pe_group.id)]})

    if team:

        user.sudo().write({"sale_team_id": team.id})



    if "pe.employee.profile" in env.registry:

        profile = env["pe.employee.profile"].sudo().search(

            [

                "|",

                ("employee_id.user_id", "=", user.id),

                ("vicidial_agent_id", "=", vicidial_user),

            ],

            limit=1,

        )

        if profile and profile.employee_id and not user.employee_id:

            user.sudo().write({"employee_id": profile.employee_id.id})



    agent = AgentUser.search([("user_id", "=", user.id)], limit=1)

    if not agent:

        agent = AgentUser.search([("vicidial_user", "=", vicidial_user)], limit=1)



    vals = {

        "user_id": user.id,

        "vicidial_user": vicidial_user,

        "full_name": user.name,

        "vicidial_qualification_active": True,

        "vicidial_crm_team_id": team.id if team else False,

        "vicidial_crm_stage_id": stage.id if stage else False,

    }

    if agent:

        agent.write(vals)

    else:

        agent = AgentUser.create(vals)

    return agent





def _setup_vicidial_qualification_agents(env):

    """Pipeline + droits pour tous les agents VICIdial (dont Leila et Karine)."""

    _ensure_vicidial_tags(env)

    team = env.ref(

        "doorway_vicidial_campaigns.crm_team_vicidial_qualification_france",

        raise_if_not_found=False,

    )

    stage = env.ref(

        "doorway_vicidial_campaigns.crm_stage_vicidial_nouveau",

        raise_if_not_found=False,

    )

    icp = env["ir.config_parameter"].sudo()

    if team:

        icp.set_param("doorway.vicidial_default_team_id", str(team.id))

    if stage:

        icp.set_param("doorway.vicidial_default_stage_id", str(stage.id))



    group = env.ref(

        "doorway_vicidial_campaigns.group_vicidial_qualifier",

        raise_if_not_found=False,

    )

    AgentUser = env["doorway.campaign.agent.user"].sudo()



    if "pe.employee.profile" in env.registry:

        Profile = env["pe.employee.profile"].sudo()

        profiles = Profile.search(

            [

                "|",

                "|",

                ("type_usager_pe", "=", "prospecteur_vicidial"),

                ("vicidial_agent_id", "!=", False),

                ("vicidial_user", "!=", False),

            ]

        )

        for profile in profiles:

            user = profile.employee_id.user_id

            vicidial_login = (

                profile.vicidial_user or profile.vicidial_agent_id or ""

            ).strip()

            if not user or not vicidial_login:

                continue

            _ensure_agent_user(env, user, vicidial_login, team, stage, group)



    agents = AgentUser.search([("active", "=", True)])

    for agent in agents:

        vals = {}

        if team and not agent.vicidial_crm_team_id:

            vals["vicidial_crm_team_id"] = team.id

        if stage and not agent.vicidial_crm_stage_id:

            vals["vicidial_crm_stage_id"] = stage.id

        if not agent.vicidial_qualification_active:

            vals["vicidial_qualification_active"] = True

        if vals:

            agent.write(vals)

        if agent.user_id and group and group not in agent.user_id.group_ids:

            agent.user_id.write({"group_ids": [(4, group.id)]})



    for login, vicidial_user in (

        ("leiladaouadi@gmail.com", "leiladaouadi"),

        ("zakaria@agencedoorway.com", "zakaria"),

        ("karine@agencedoorway.com", "karine"),

        ("martin@agencedoorway.com", "martin"),

    ):

        user = env["res.users"].sudo().search([("login", "=", login)], limit=1)

        if user:

            _ensure_agent_user(env, user, vicidial_user, team, stage, group)



    qualifier_agents = AgentUser.search(

        [("vicidial_qualification_active", "=", True), ("active", "=", True)]

    )

    _link_qualifiers_to_human_campaigns(env, qualifier_agents)
    _ensure_door_app0_qualifier_campaigns(env)


def _rename_vicidial_branding(env):
    """Renomme les libellés VICIdial existants en Appels."""
    _ensure_vicidial_tags(env)
    refs = (
        ("doorway_vicidial_campaigns.crm_team_vicidial_qualification_france", "Appels — Qualification"),
        ("doorway_vicidial_campaigns.group_vicidial_qualifier", "Appels — Qualification CRM"),
    )
    for xmlid, label in refs:
        rec = env.ref(xmlid, raise_if_not_found=False)
        if rec and rec.name != label:
            rec.sudo().write({"name": label})




def _setup_vicidial_supervisors(env):
    """Accès tableau Superviseurs : Karine, Zakaria, Martin uniquement."""
    group = env.ref(
        "doorway_vicidial_campaigns.group_vicidial_supervisor",
        raise_if_not_found=False,
    )
    if not group:
        return
    for login in (
        "zakaria@agencedoorway.com",
        "karine@agencedoorway.com",
        "martin@agencedoorway.com",
    ):
        user = env["res.users"].sudo().search(
            [("login", "=", login), ("active", "=", True)], limit=1
        )
        if user and group not in user.group_ids:
            user.write({"group_ids": [(4, group.id)]})


def setup_rappel_quebec_campaign(env):
    """Campagne VICIdial B2C rappels Québec + import liste RAPPEL_B2C_QC."""
    import os

    from odoo.addons.doorway_vicidial_campaigns.services.file_importer import (
        FileImporter,
    )

    Campaign = env["doorway.campaign"].sudo()
    camp = env.ref(
        "doorway_vicidial_campaigns.campaign_rappel_quebec", raise_if_not_found=False
    )
    if not camp:
        camp = Campaign.search(
            [
                "|",
                ("vicidial_campaign_id", "=", "DW_RAPQC"),
                ("name", "ilike", "Rappels Québec"),
            ],
            limit=1,
        )
    if not camp:
        return False
    svc = camp._vicidial_svc()
    if not svc.is_available():
        return False
    setup = svc.setup_rappel_quebec_campaign()
    camp.write(
        {
            "vicidial_campaign_id": setup.get("campaign_id"),
            "vicidial_list_id": setup.get("list_id"),
            "state": "ready",
        }
    )
    csv_path = os.path.join(
        os.path.dirname(__file__), "data", "leads", "b2c_rappel_quebec.csv"
    )
    if os.path.isfile(csv_path):
        with open(csv_path, "rb") as handle:
            rows = FileImporter().parse_bytes(
                handle.read(), "b2c_rappel_quebec.csv"
            )
        if rows:
            svc.inject_contacts(
                setup["campaign_id"],
                rows,
                phone_code="1",
                list_name=setup.get("list_name") or "RAPPEL_B2C_QC",
            )
    agents = env["doorway.campaign.agent.user"].sudo().search(
        [("vicidial_qualification_active", "=", True), ("active", "=", True)]
    )
    if agents:
        camp.write({"human_agent_ids": [(6, 0, agents.ids)]})
    return True


def _reset_qualifier_onboarding(env, logins=None):
    """Force la visite guidée call center (ex. Leila) à la prochaine ouverture Appels."""
    logins = logins or ("leiladaouadi@gmail.com",)
    for login in logins:
        user = env["res.users"].sudo().search(
            [("login", "=", login), ("active", "=", True)], limit=1
        )
        if not user:
            continue
        state = user.doorway_onboarding_state
        if not isinstance(state, dict):
            state = {}
        else:
            state = dict(state)
        state.pop("vicidial_call_center", None)
        user.write({"doorway_onboarding_state": state})


def _fix_vicidial_onboarding_tour_copy(env):
    """Texte visite guidée : équipe/campagnes dynamiques, pas « France » en dur."""
    Step = env["doorway.onboarding.tour.step"].sudo()
    welcome = env.ref(
        "doorway_onboarding.tour_vicidial_step_welcome", raise_if_not_found=False
    )
    qual = env.ref(
        "doorway_onboarding.tour_vicidial_step_qualification",
        raise_if_not_found=False,
    )
    if welcome:
        welcome.write(
            {
                "body_html": """
            <p>Tu rejoins l'équipe <strong>Appels</strong> sur Intellix CRM.</p>
            <p>Claude t'a préparé une présentation personnalisée ci-dessous (campagnes VICIdial et pipeline CRM).</p>
            <div class="alert alert-info border-0 pe-xp-callout" role="status">
                <strong>+40 XP</strong> — termine la quête pour le badge
                <em>Qualificateur Appels</em> 📞
            </div>
        """
            }
        )
    if qual:
        qual.write(
            {
                "body_html": """
            <p>Après chaque appel, qualifie le lead dans ton <strong>pipeline Appels</strong> (assigné sur ton profil).</p>
            <ul>
                <li>Étape <em>Nouveau</em> → <em>Qualifié</em> / <em>RDV</em> / <em>Rappel</em> / <em>Non qualifié</em></li>
                <li>Tags automatiques : Appels, À qualifier</li>
                <li>Notes et prochaine action obligatoires</li>
            </ul>
        """
            }
        )


def setup_espagne_renovation_campaign(env):
    """Campagne + liste VICIdial Espagne rénovation, trunk TrustSIP, agent Sofía."""
    Campaign = env["doorway.campaign"].sudo()
    Profile = env["doorway.agent.profile"].sudo()
    Trunk = env["doorway.sip.trunk"].sudo()
    Phone = env["doorway.agent.phone.number"].sudo()

    camp = env.ref(
        "doorway_vicidial_campaigns.campaign_espagne_renovation",
        raise_if_not_found=False,
    )
    if not camp:
        camp = Campaign.search([("vicidial_campaign_id", "=", "DW_ESREN")], limit=1)
    if not camp:
        return False

    sofia = env.ref(
        "doorway_agents_dashboard.agent_sofia_renov", raise_if_not_found=False
    )
    if not sofia:
        sofia = Profile.search(
            [
                ("external_agent_id", "=", "sofia-test-maroc-juin2026"),
                ("status", "=", "active"),
            ],
            limit=1,
        )

    trunk = env.ref(
        "doorway_agents_dashboard.sip_trunk_trustsip_espagne",
        raise_if_not_found=False,
    )
    if not trunk:
        trunk = Trunk.search([("name", "=", "TrustSIP — Espagne")], limit=1)
    if not trunk:
        trunk = Trunk.create(
            {
                "name": "TrustSIP — Espagne",
                "provider": "custom",
                "termination_uri": "116.202.233.75",
                "sip_username": "trustsip",
                "sip_password": "4i9jgo7",
                "sip_port": 5060,
                "notes": "Compte web: trustsip / 9f4k8fm",
            }
        )

    if sofia:
        for phone in sofia.phone_number_ids:
            phone.write(
                {
                    "trunk_id": trunk.id,
                    "phone_source": "sip_trunk",
                    "sip_trunk_name": trunk.name,
                }
            )
        camp.write(
            {
                "ia_agent_id": sofia.id,
                "ia_call_script_hint": (
                    "Agent Sofía ES — renov-aides — campagne %s"
                    % (sofia.external_agent_id or "")
                ),
            }
        )

    svc = camp._vicidial_svc()
    if not svc.is_available():
        return False
    setup = svc.setup_espagne_renovation_campaign()
    svc.ensure_spain_outbound_dialing()
    camp.write(
        {
            "vicidial_campaign_id": setup.get("campaign_id"),
            "vicidial_list_id": setup.get("list_id"),
            "state": "ready",
            "description": (
                "Espagne rénovation — liste %s, trunk TrustSIP (116.202.233.75)"
                % (setup.get("list_name") or "ESPAGNE_RENOVATION")
            ),
        }
    )
    return True


def _ensure_frb2b_manual_campaigns(env):
    """Campagnes manuelles B2B France (Twilio + Africa-Con) visibles sur le poste Odoo."""
    Campaign = env["doorway.campaign"].sudo()
    AgentUser = env["doorway.campaign.agent.user"].sudo()
    karine = AgentUser.search([("vicidial_user", "=", "karine")], limit=1)
    specs = (
        (
            "doorway_vicidial_campaigns.campaign_france_b2b",
            "DW_FRB2B",
            "France B2B — Twilio manual",
        ),
        (
            "doorway_vicidial_campaigns.campaign_france_b2ac",
            "DW_FRAC",
            "France B2B — Africa-Con manual",
        ),
    )
    for xmlid, vici_id, name in specs:
        camp = env.ref(xmlid, raise_if_not_found=False)
        if not camp:
            camp = Campaign.search(
                [("vicidial_campaign_id", "=", vici_id)], limit=1
            )
        vals = {
            "name": name,
            "vicidial_campaign_id": vici_id,
            "pipeline": "driven",
            "campaign_mode": "human_agent",
            "state": "ready",
        }
        if camp:
            camp.write(vals)
        else:
            camp = Campaign.create(vals)
        if karine and karine not in camp.human_agent_ids:
            camp.write({"human_agent_ids": [(4, karine.id)]})


def _backfill_human_agent_users(env):
    """Remplit human_agent_user_ids depuis les agents humains déjà liés."""
    Campaign = env["doorway.campaign"].sudo()
    for camp in Campaign.search([("human_agent_ids", "!=", False)]):
        users = camp.human_agent_ids.mapped("user_id")
        if users and set(camp.human_agent_user_ids.ids) != set(users.ids):
            camp.with_context(sync_human_agent_vicidial=False).write(
                {"human_agent_user_ids": [(6, 0, users.ids)]}
            )


def post_init_hook(env):
    _rename_vicidial_branding(env)
    _setup_vicidial_supervisors(env)
    _setup_vicidial_qualification_agents(env)
    setup_rappel_quebec_campaign(env)
    setup_espagne_renovation_campaign(env)
    _fix_vicidial_onboarding_tour_copy(env)
    _ensure_leila_france_only(env)
    _ensure_frb2b_manual_campaigns(env)
    _backfill_human_agent_users(env)

