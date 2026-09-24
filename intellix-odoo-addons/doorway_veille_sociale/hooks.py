# -*- coding: utf-8 -*-
import logging

_logger = logging.getLogger(__name__)


def post_init_hook(env):
    """Initialisation à la première installation :

    - crée l'enregistrement de configuration unique (avec token webhook) ;
    - crée le projet "Gestion Communauté Doorway" et ses étapes s'ils manquent.
    """
    try:
        cfg = env["doorway.veille.config"].get_config()
        cfg.sudo()._sync_source_flags()
    except Exception:  # noqa: BLE001
        _logger.exception("doorway_veille_sociale: impossible de créer la configuration")
    try:
        env["doorway.community.post"].get_community_project()
    except Exception:  # noqa: BLE001
        _logger.exception("doorway_veille_sociale: impossible de créer le projet communauté")
    try:
        _ensure_veille_crm_stage(env)
    except Exception:  # noqa: BLE001
        _logger.exception("doorway_veille_sociale: impossible de créer l'étape CRM veille")
    try:
        env["doorway.veille.signal"].migrate_signaux_reactivation()
    except Exception:  # noqa: BLE001
        _logger.exception("doorway_veille_sociale: migration réactivation ignorée")
    try:
        migrate_veille_settings_group(env)
    except Exception:  # noqa: BLE001
        _logger.exception("doorway_veille_sociale: migration groupe configuration")


def migrate_veille_settings_group(env):
    """Donne l'accès Configuration veille à tous les utilisateurs internes."""
    group = env.ref(
        "doorway_veille_sociale.group_veille_settings", raise_if_not_found=False
    )
    if not group:
        return
    users = env["res.users"].sudo().search([("share", "=", False), ("active", "=", True)])
    group.sudo().write({"user_ids": [(4, uid) for uid in users.ids]})
    _logger.info(
        "doorway_veille_sociale: groupe configuration veille → %s utilisateurs",
        len(users),
    )


def _ensure_veille_crm_stage(env):
    """Étape « Nouveau lead — Veille sociale » sur le pipeline Rénovation."""
    team = env.ref(
        "renovation_conciergerie.crm_team_renovation", raise_if_not_found=False
    )
    if not team:
        return
    Stage = env["crm.stage"].sudo()
    stage = Stage.search(
        [
            ("name", "=", "Nouveau lead — Veille sociale"),
            ("team_ids", "in", team.id),
        ],
        limit=1,
    )
    if not stage:
        Stage.create(
            {
                "name": "Nouveau lead — Veille sociale",
                "sequence": 1,
                "team_ids": [(6, 0, [team.id])],
            }
        )
