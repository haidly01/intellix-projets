# -*- coding: utf-8 -*-
from datetime import timedelta

from odoo import fields


def _seed_demo_calendar(env):
    """Crée des publications passées et futures si le calendrier est vide."""
    Post = env["doorway.social.post"].sudo()
    if Post.search_count([]):
        return
    team = env.ref(
        "renovation_conciergerie.crm_team_marketing",
        raise_if_not_found=False,
    )
    if not team:
        team = env["crm.team"].sudo().search([], limit=1)
    if not team:
        return

    now = fields.Datetime.now()
    demos = [
        {
            "hook": "5 astuces pour convertir plus de leads",
            "platform": "linkedin",
            "post_format": "publication",
            "state": "published",
            "days": -14,
            "caption": "Découvrez nos conseils Doorway pour la prospection B2B.",
        },
        {
            "hook": "Témoignage client — +40% de RDV",
            "platform": "facebook",
            "post_format": "reel",
            "state": "published",
            "days": -7,
            "caption": "Retour d'expérience Agence Doorway.",
        },
        {
            "hook": "IA + humain : le duo gagnant",
            "platform": "instagram",
            "post_format": "carrousel",
            "state": "published",
            "days": -2,
            "caption": "Comment nos agents IA soutiennent les équipes commerciales.",
        },
        {
            "hook": "Lancement campagne B2C France",
            "platform": "facebook",
            "post_format": "publication",
            "state": "scheduled",
            "days": 2,
            "caption": "Nouvelle offre Doorway pour le marché français.",
        },
        {
            "hook": "Webinaire prospection digitale",
            "platform": "linkedin",
            "post_format": "publication",
            "state": "scheduled",
            "days": 5,
            "caption": "Inscrivez-vous à notre prochain live.",
        },
        {
            "hook": "Reel — coulisses équipe commerciale",
            "platform": "instagram",
            "post_format": "reel",
            "state": "scheduled",
            "days": 9,
            "caption": "Une journée type chez Agence Doorway.",
        },
        {
            "hook": "Offre été — audit CRM gratuit",
            "platform": "gmb",
            "post_format": "publication",
            "state": "ready",
            "days": 12,
            "caption": "Réservez votre audit avant la fin du mois.",
        },
    ]
    for item in demos:
        dt = now + timedelta(days=item["days"])
        vals = {
            "pipeline_id": team.id,
            "platform": item["platform"],
            "post_format": item["post_format"],
            "hook": item["hook"],
            "caption": item["caption"],
            "scheduled_date": dt,
            "state": item["state"],
        }
        if item["state"] == "published":
            vals["published_date"] = dt
        Post.create(vals)


def post_init_hook(env):
    _seed_demo_calendar(env)
    env["doorway.social.account"]._ensure_whatsapp_from_config()
    env["doorway.social.account"]._sync_inbox_access_for_team()
