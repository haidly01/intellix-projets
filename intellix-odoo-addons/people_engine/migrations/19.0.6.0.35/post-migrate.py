# -*- coding: utf-8 -*-
import logging

_logger = logging.getLogger(__name__)

COURSE_XMLID = "people_engine.course_crm_intellix"
CONTENT_URL = "/people_engine/static/src/html/formation_crm_intellix_fr.html"
TITLE = "Formation CRM IntelliX — Pourquoi & Comment"


def migrate(cr, version):
    env = globals().get("env")
    if not env:
        return
    course = env.ref(COURSE_XMLID, raise_if_not_found=False)
    vals = {
        "title": TITLE,
        "category": "crm",
        "course_type": "internal",
        "duration_hours": 5.0,
        "difficulty": "beginner",
        "points_on_completion": 50,
        "description": (
            "Formation complète sur le CRM IntelliX — pourquoi l'utiliser et comment en tirer "
            "le maximum : 7 modules interactifs (vision, pipelines, leads, automatisations, "
            "reporting, cas pratiques)."
        ),
        "content_url": CONTENT_URL,
        "is_active": True,
    }
    if course:
        course.write(vals)
        _logger.info("PE migration 19.0.6.0.35: cours CRM mis à jour (id=%s)", course.id)
    else:
        course = env["pe.course"].create(vals)
        env["ir.model.data"].create({
            "name": "course_crm_intellix",
            "module": "people_engine",
            "model": "pe.course",
            "res_id": course.id,
            "noupdate": False,
        })
        _logger.info("PE migration 19.0.6.0.35: cours CRM créé (id=%s)", course.id)
