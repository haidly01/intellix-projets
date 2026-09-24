# -*- coding: utf-8 -*-


def post_init_hook(env):
    cad = env.ref("base.CAD", raise_if_not_found=False)
    if cad:
        env["ir.config_parameter"].sudo().set_param(
            "coins_quebec.currency_id", str(cad.id)
        )
    user = env.ref("coins_quebec.group_coins_quebec_user", raise_if_not_found=False)
    manager = env.ref(
        "coins_quebec.group_coins_quebec_manager", raise_if_not_found=False
    )
    if user:
        internals = env["res.users"].sudo().search(
            [("share", "=", False), ("id", "!=", 1)]
        )
        internals.write({"group_ids": [(4, user.id)]})
    if manager:
        env.ref("base.user_admin").sudo().write({"group_ids": [(4, manager.id)]})
    _detach_demo_crm_leads_from_cq_teams(env)
    _hide_legacy_crm_coins_quebec_tab(env)
    sync_cq_human_assignees(env)
    _sync_cq_martin_calendar_color(env)


def _sync_cq_martin_calendar_color(env):
    """Pastille calendrier Martin Houle = mauve. Ne touche pas Michel."""
    Part = env["coins.quebec.partenariat"]
    if hasattr(Part, "_cq_ensure_martin_calendar_color"):
        Part._cq_ensure_martin_calendar_color()


def sync_cq_human_assignees(env):
    """Copie user_id → coins_commercial_assigne sans toucher aux assignations IA."""
    if "coins_commercial_assigne" not in env["coins.quebec.partenariat"]._fields:
        return
    recs = (
        env["coins.quebec.partenariat"]
        .sudo()
        .with_context(active_test=False)
        .search(
            [
                ("user_id", "!=", False),
                ("coins_commercial_assigne", "=", False),
                ("coins_agent_ia_id", "=", False),
            ]
        )
    )
    for rec in recs:
        rec.write(
            {
                "assignee_kind": "humain",
                "coins_commercial_assigne": rec.user_id.id,
            }
        )


def _hide_legacy_crm_coins_quebec_tab(env):
    """Masque les menus CRM / Doorway qui ouvrent encore crm.lead « Coins Québec »."""
    for xmlid in (
        "doorway_hiba_qualif.menu_crm_coins_quebec",
        "doorway_hiba_qualif.menu_doorway_pipeline_coins_quebec",
    ):
        menu = env.ref(xmlid, raise_if_not_found=False)
        if menu and menu.active:
            menu.active = False
    action = env.ref(
        "doorway_hiba_qualif.action_pipeline_coins_quebec", raise_if_not_found=False
    )
    if action and action.res_model == "crm.lead":
        if action.path != "legacy-crm-coins-quebec-disabled":
            action.path = "legacy-crm-coins-quebec-disabled"


def _detach_demo_crm_leads_from_cq_teams(env):
    """Ancien nettoyage démo : vidait team_id de TOUTES les fiches CRM CQ.

    Ça renvoyait les partenaires à contacter dans Réno Immobilier / Coins
    Marocain (équipe par défaut de Leila / Zakaria). Ne plus le faire.
    """
    return
