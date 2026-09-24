# -*- coding: utf-8 -*-
import logging

_logger = logging.getLogger(__name__)

COURSE_XMLID = "people_engine.course_agents_ia_basics"
CONTENT_URL = "/people_engine/static/src/html/formation_agent_ia_qualification_fr.html"


def migrate(cr, version):
    env = globals().get("env")
    if not env:
        return
    course = env.ref(COURSE_XMLID, raise_if_not_found=False)
    if not course:
        _logger.warning("PE migration 19.0.6.0.33: course %s introuvable", COURSE_XMLID)
        return
    course.write({
        "title": "Formation Agent IA de Qualification — Marché France",
        "category": "ia_tools",
        "course_type": "internal",
        "duration_hours": 6.0,
        "difficulty": "intermediate",
        "points_on_completion": 60,
        "description": (
            "Formation complète pour configurer et optimiser un agent IA de qualification "
            "téléphonique sur le marché France — 6 modules interactifs (script, voix, "
            "conformité, n8n, KPIs, cas pratiques)."
        ),
        "content_url": CONTENT_URL,
    })
    _logger.info("PE migration 19.0.6.0.33: cours Agent IA qualification mis à jour (id=%s)", course.id)
