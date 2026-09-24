# -*- coding: utf-8 -*-
import logging

from odoo import SUPERUSER_ID, api

_logger = logging.getLogger(__name__)

LEFTOVER_STAGE_XMLIDS = (
    "renovation_conciergerie.crm_stage_renovation_new",
    "renovation_conciergerie.crm_stage_renovation_social",
    "renovation_conciergerie.crm_stage_renovation_retell",
    "renovation_conciergerie.crm_stage_renovation_website",
    "renovation_conciergerie.crm_stage_renovation_qualified",
    "renovation_conciergerie.crm_stage_renovation_followup",
    "renovation_conciergerie.crm_stage_renovation_immo_called",
    "renovation_conciergerie.crm_stage_renovation_immo_qualified",
    "renovation_conciergerie.crm_stage_renovation_immo_development",
    "renovation_conciergerie.crm_stage_renovation_immo_unqualified",
    "renovation_conciergerie.crm_stage_immobilier_new",
    "renovation_conciergerie.crm_stage_immobilier_social",
    "renovation_conciergerie.crm_stage_immobilier_retell",
    "renovation_conciergerie.crm_stage_immobilier_website",
    "renovation_conciergerie.crm_stage_immobilier_qualified",
    "renovation_conciergerie.crm_stage_immobilier_followup",
)

OLD_MENU_XMLIDS = (
    "renovation_conciergerie.menu_reno_immobilier_root",
    "renovation_conciergerie.menu_reno_immobilier_partenaires",
    "renovation_conciergerie.menu_reno_immobilier_leads",
    "renovation_conciergerie.menu_reno_immobilier_leads_jour",
)

STATUS_FROM_STAGE = (
    (("gagne", "gagné", "won"), "gagne"),
    (("perdu", "lost", "non qualif", "hors cible"), "perdu"),
    (("à relancer", "a relancer", "relance", "rappel"), "a_relancer"),
    (("en contact", "contact", "social", "retell", "agent ia", "site", "appel", "développ"), "en_contact"),
    (("attrib", "assign", "qualif"), "attribue"),
    (("nouveau", "new", "à traiter", "a traiter"), "nouveau"),
)


def _status_from_stage_name(name):
    hay = (name or "").lower()
    for needles, status in STATUS_FROM_STAGE:
        if any(n in hay for n in needles):
            return status
    return "nouveau"


def post_init_hook(env_or_cr, registry=None):
    if registry is None:
        env = env_or_cr
    else:
        env = api.Environment(env_or_cr, SUPERUSER_ID, {})
    _align_stages(env)
    _align_app_menu_order(env)
    remapped = _remap_leads(env)
    _detach_leftover_stages(env)
    _hide_legacy_menus(env)
    env["renovation.partner.package"].search([])._compute_reno_package_health()
    _logger.info("reno_immobilier: %s leads remappés vers les 6 colonnes", remapped)
    env.cr.commit()


def _align_stages(env):
    team = env.ref("reno_immobilier.crm_team_reno_immobilier")
    wanted_teams = team
    specs = (
        ("reno_immobilier.crm_stage_nouveau", "Nouveau", 10, False, False),
        ("reno_immobilier.crm_stage_en_contact", "Contacté", 20, False, False),
        ("reno_immobilier.crm_stage_attribue", "Attribué", 30, False, False),
        ("reno_immobilier.crm_stage_a_relancer", "Relance", 40, False, False),
        ("reno_immobilier.crm_stage_gagne", "Gagné", 50, False, True),
        ("reno_immobilier.crm_stage_perdu", "Perdu", 60, True, False),
    )
    for xmlid, name, sequence, fold, is_won in specs:
        stage = env.ref(xmlid)
        stage.write({
            "name": name,
            "sequence": sequence,
            "fold": fold,
            "is_won": is_won,
            "team_ids": [(6, 0, wanted_teams.ids)],
        })


def _remap_leads(env):
    Lead = env["crm.lead"].with_context(
        tracking_disable=True,
        mail_notrack=True,
        reno_immobilier_pipeline=1,
    )
    team_ids = Lead._reno_immo_team_ids()
    stages = {
        key: env.ref(xmlid)
        for key, xmlid in (
            ("nouveau", "reno_immobilier.crm_stage_nouveau"),
            ("attribue", "reno_immobilier.crm_stage_attribue"),
            ("a_relancer", "reno_immobilier.crm_stage_a_relancer"),
            ("en_contact", "reno_immobilier.crm_stage_en_contact"),
            ("gagne", "reno_immobilier.crm_stage_gagne"),
            ("perdu", "reno_immobilier.crm_stage_perdu"),
        )
    }
    leads = Lead.with_context(active_test=False).search([("team_id", "in", team_ids)])
    remapped = 0
    for lead in leads:
        if lead.reno_facile_paused:
            continue
        target = stages[_status_from_stage_name(lead.stage_id.name)]
        if lead.stage_id != target:
            lead.write({"stage_id": target.id})
            remapped += 1
    if leads:
        leads._compute_reno_gestion_status()
        leads._compute_reno_card_fields()
    return remapped


def _detach_leftover_stages(env):
    archive = env.ref("reno_immobilier.crm_team_reno_archive")
    keep = env["crm.team"]
    for xmlid in (
        "reno_immobilier.crm_team_reno_immobilier",
        "renovation_conciergerie.crm_team_renovation",
        "renovation_conciergerie.crm_team_immobilier",
    ):
        team = env.ref(xmlid, raise_if_not_found=False)
        if team:
            keep |= team
    for xmlid in LEFTOVER_STAGE_XMLIDS:
        stage = env.ref(xmlid, raise_if_not_found=False)
        if not stage:
            continue
        others = stage.team_ids - keep
        stage.team_ids = others | archive


def _align_app_menu_order(env):
    Menu = env["ir.ui.menu"]
    if hasattr(Menu, "_reno_align_app_menu_order"):
        Menu._reno_align_app_menu_order()


def _hide_legacy_menus(env):
    for xmlid in OLD_MENU_XMLIDS:
        menu = env.ref(xmlid, raise_if_not_found=False)
        if menu:
            menu.active = False
