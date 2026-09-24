# -*- coding: utf-8 -*-
import logging

_logger = logging.getLogger(__name__)


CC_MAROC_AGENT_LOGIN = "youness.marzguioui@gmail.com"
CC_MAROC_AGENT_NAME = "Youness Marzguioui"
CC_MAROC_DEFAULT_DEVISE = "MAD"
CC_MAROC_SALAIRE = {"MAD": 2500.0, "EUR": 250.0}


def _halve_department_objectives(department):
    """Réduit les objectifs d'un département copié depuis le template (mi-temps)."""
    for obj in department.objective_ids:
        vals = {"valeur_cible": obj.valeur_cible / 2}
        if obj.valeur_minimum:
            vals["valeur_minimum"] = obj.valeur_minimum / 2
        if obj.tolerance_chute_pct:
            vals["valeur_minimum"] = obj.valeur_cible / 2 * (
                1 - obj.tolerance_chute_pct / 100
            )
        obj.write(vals)


def setup_call_center_maroc(env):
    """Département Call Center Maroc (mi-temps) + agent par défaut."""
    Department = env["pe.department"].sudo()
    template = Department.search([("code", "=", "CC-TEMPLATE")], limit=1)
    ma = Department.search([("code", "=", "CC-MA")], limit=1)
    if not ma and template:
        ma = template.copy(
            {
                "name": "Call Center Maroc",
                "code": "CC-MA",
                "is_template": False,
                "parent_template_id": template.id,
                "employee_ids": [(5, 0)],
                "pays_affectation": "MA",
            }
        )
        _halve_department_objectives(ma)
        for prime in template.prime_config_ids:
            prime.copy({"department_id": ma.id})
        _logger.info("PE: département Call Center Maroc créé (id=%s)", ma.id)
    elif ma and not ma.objective_ids and template:
        for obj in template.objective_ids:
            obj.copy(
                {
                    "department_id": ma.id,
                    "valeur_cible": obj.valeur_cible / 2,
                    "valeur_minimum": (
                        obj.valeur_minimum / 2 if obj.valeur_minimum else False
                    ),
                }
            )
        for prime in template.prime_config_ids:
            if not ma.prime_config_ids.filtered(
                lambda p, t=prime: p.type_prime == t.type_prime
            ):
                prime.copy({"department_id": ma.id})

    if ma:
        setup_maroc_parttime_agent(
            env,
            login=CC_MAROC_AGENT_LOGIN,
            name=CC_MAROC_AGENT_NAME,
            devise=CC_MAROC_DEFAULT_DEVISE,
            department=ma,
        )
    return ma


def setup_maroc_parttime_agent(
    env,
    login=None,
    name=None,
    devise="MAD",
    department=None,
):
    """Crée ou met à jour l'agent mi-temps Maroc (salaire 2500 MAD ou 250 EUR + primes)."""
    login = login or CC_MAROC_AGENT_LOGIN
    name = name or CC_MAROC_AGENT_NAME
    devise = devise if devise in CC_MAROC_SALAIRE else CC_MAROC_DEFAULT_DEVISE
    salaire = CC_MAROC_SALAIRE[devise]

    Department = env["pe.department"].sudo()
    ma = department or Department.search([("code", "=", "CC-MA")], limit=1)
    if not ma:
        return False

    company = env["res.company"].sudo().search(
        [("partner_id.country_id.code", "=", "MA")], limit=1
    )
    if not company:
        company = env["res.company"].sudo().search([], limit=1)

    Users = env["res.users"].sudo()
    Employee = env["hr.employee"].sudo()
    Profile = env["pe.employee.profile"].sudo()

    user = Users.search([("login", "=", login)], limit=1)
    if not user:
        grp_user = env.ref("base.group_user", raise_if_not_found=False)
        grp_sales = env.ref(
            "sales_team.group_sale_salesman", raise_if_not_found=False
        )
        grp_qualifier = env.ref(
            "doorway_vicidial_campaigns.group_vicidial_qualifier",
            raise_if_not_found=False,
        )
        group_ids = [g.id for g in (grp_user, grp_sales, grp_qualifier) if g]
        user = Users.with_context(no_reset_password=True).create(
            {
                "name": name,
                "login": login,
                "email": login,
                "company_id": company.id,
                "company_ids": [(6, 0, [company.id])],
                "doorway_segment": "b2b",
                "doorway_role": "user",
                "group_ids": [(6, 0, group_ids)],
            }
        )
        _logger.info("PE: utilisateur agent CC Maroc créé (%s)", login)

    emp = user.employee_id
    if not emp:
        emp = Employee.create(
            {
                "name": name,
                "user_id": user.id,
                "company_id": company.id,
            }
        )
        user.write({"employee_id": emp.id})

    profile = Profile.search([("employee_id", "=", emp.id)], limit=1)
    if not profile:
        profile = Profile.create({"employee_id": emp.id})

    vicidial_login = login.split("@")[0].replace(".", "")[:12] or "ccmaroc"
    profile.write(
        {
            "department_pe_id": ma.id,
            "type_usager_pe": "prospecteur_vicidial",
            "type_remuneration": "mixte",
            "salaire_base": salaire,
            "devise_remuneration": devise,
            "regime_travail": "mi_temps",
            "coefficient_objectifs": 1.0,
            "pays_affectation": "MA",
            "vicidial_user": profile.vicidial_user or vicidial_login,
        }
    )
    ma.write({"employee_ids": [(4, emp.id)]})

    if "doorway.campaign.agent.user" in env:
        agent_link = _ensure_maroc_vicidial_agent(env, user, profile)
        _assign_rappel_quebec_campaign(env, agent_link)

    try:
        user._sync_people_engine_role_groups()
    except Exception:  # noqa: BLE001
        pass

    _logger.info(
        "PE: agent CC Maroc %s — %s %s/mois, département %s",
        name,
        salaire,
        devise,
        ma.name,
    )
    return profile


def _ensure_maroc_vicidial_agent(env, user, profile):
    """Agent VICIdial + pipeline qualification pour un prospecteur CC Maroc."""
    AgentUser = env["doorway.campaign.agent.user"].sudo()
    team = env.ref(
        "doorway_vicidial_campaigns.crm_team_vicidial_qualification_france",
        raise_if_not_found=False,
    )
    stage = env.ref(
        "doorway_vicidial_campaigns.crm_stage_vicidial_nouveau",
        raise_if_not_found=False,
    )
    qualifier = env.ref(
        "doorway_vicidial_campaigns.group_vicidial_qualifier",
        raise_if_not_found=False,
    )
    vicidial_login = profile.vicidial_user or user.login.split("@")[0].replace(".", "")[:16]
    agent = AgentUser.search([("user_id", "=", user.id)], limit=1)
    vals = {
        "user_id": user.id,
        "vicidial_user": vicidial_login,
        "full_name": user.name,
        "vicidial_qualification_active": True,
        "active": True,
    }
    if team:
        vals["vicidial_crm_team_id"] = team.id
    if stage:
        vals["vicidial_crm_stage_id"] = stage.id
    if agent:
        agent.write(vals)
    else:
        agent = AgentUser.create(vals)
    if qualifier and qualifier not in user.group_ids:
        user.write({"group_ids": [(4, qualifier.id)]})
    if team:
        user.write({"sale_team_id": team.id})
    try:
        agent.action_sync_vicidial()
    except Exception:  # noqa: BLE001
        _logger.exception("PE: sync VICIdial %s impossible", vicidial_login)
    return agent


def _assign_rappel_quebec_campaign(env, agent):
    """Affecte l'agent à la campagne B2C Rappels Québec (DW_RAPQC)."""
    if not agent:
        return False
    camp = env.ref(
        "doorway_vicidial_campaigns.campaign_rappel_quebec",
        raise_if_not_found=False,
    )
    if not camp:
        camp = env["doorway.campaign"].sudo().search(
            [
                "|",
                ("vicidial_campaign_id", "=", "DW_RAPQC"),
                ("name", "ilike", "Rappels Québec"),
            ],
            limit=1,
        )
    if camp and agent not in camp.human_agent_ids:
        camp.write({"human_agent_ids": [(4, agent.id)]})
        _logger.info("PE: %s assigné à %s", agent.vicidial_user, camp.name)
    return camp


def setup_call_center_qc(env):
    """Département Call Center QC (copie template) + branchement Leila."""
    Department = env["pe.department"].sudo()
    template = Department.search([("code", "=", "CC-TEMPLATE")], limit=1)
    if not template:
        return False

    qc = Department.search([("code", "=", "CC-QC")], limit=1)
    if not qc:
        qc = template.copy(
            {
                "name": "Call Center QC",
                "code": "CC-QC",
                "is_template": False,
                "parent_template_id": template.id,
                "employee_ids": [(5, 0)],
            }
        )
        _logger.info("PE: département Call Center QC créé (id=%s)", qc.id)

    profile = env["pe.employee.profile"].sudo().search(
        [("vicidial_user", "=", "leiladaouadi")], limit=1
    )
    if not profile:
        user = env["res.users"].sudo().search(
            [("login", "=", "leiladaouadi@gmail.com")], limit=1
        )
        if user and user.employee_id:
            profile = env["pe.employee.profile"].sudo().search(
                [("employee_id", "=", user.employee_id.id)], limit=1
            )

    if profile:
        profile.write(
            {
                "department_pe_id": qc.id,
                "type_usager_pe": "prospecteur_vicidial",
                "vicidial_user": profile.vicidial_user or "leiladaouadi",
            }
        )
        if profile.employee_id:
            qc.write({"employee_ids": [(4, profile.employee_id.id)]})
            user = env["res.users"].sudo().search(
                [
                    "|",
                    ("id", "=", profile.user_id.id),
                    ("login", "=", "leiladaouadi@gmail.com"),
                ],
                limit=1,
            )
            if user and not user.employee_id:
                user.write({"employee_id": profile.employee_id.id})
        _logger.info("PE: Leila assignée au département %s", qc.name)

    return qc


def post_init_hook(env):
    """Aligne People Engine pour admins / superviseurs / B2B."""
    try:
        env["res.users"]._init_sync_people_engine_access()
    except Exception:  # noqa: BLE001
        _logger.exception("people_engine: synchronisation des accès impossible")
    try:
        env["res.users"]._init_ensure_demo_superadmin_groups()
    except Exception:  # noqa: BLE001
        _logger.exception("people_engine: accès superadmin démo impossible")
    try:
        env["res.users"]._migrate_pe_onboarding_to_doorway()
    except Exception:  # noqa: BLE001
        _logger.exception("people_engine: migration onboarding impossible")
    try:
        setup_call_center_qc(env)
    except Exception:  # noqa: BLE001
        _logger.exception("people_engine: setup Call Center QC impossible")
    try:
        setup_call_center_maroc(env)
    except Exception:  # noqa: BLE001
        _logger.exception("people_engine: setup Call Center Maroc impossible")
    try:
        env["pe.document.template"].sync_catalog_templates()
    except Exception:  # noqa: BLE001
        _logger.exception("people_engine: synchronisation modèles documents impossible")
