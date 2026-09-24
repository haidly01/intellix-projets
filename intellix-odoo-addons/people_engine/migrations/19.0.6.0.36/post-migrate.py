# -*- coding: utf-8 -*-
import logging

_logger = logging.getLogger(__name__)

COURSE_XMLID = "people_engine.course_rh_gamification"
CONTENT_URL = "/people_engine/static/src/html/formation_rh_gamification_fr.html"
TITLE = "Formation RH & Gamification — IntelliX People Engine"


def migrate(cr, version):
    env = globals().get("env")
    if not env:
        return
    course = env.ref(COURSE_XMLID, raise_if_not_found=False)
    vals = {
        "title": TITLE,
        "category": "leadership",
        "course_type": "internal",
        "duration_hours": 5.0,
        "difficulty": "intermediate",
        "points_on_completion": 50,
        "description": (
            "Formation complète RH & gamification People Engine — 8 modules interactifs : "
            "objectifs, score /100, gamification, badges, coaching IA, optimisation équipe "
            "et rituels."
        ),
        "content_url": CONTENT_URL,
        "is_active": True,
    }
    if course:
        course.write(vals)
        _logger.info("PE migration 19.0.6.0.36: cours RH Gamification mis à jour (id=%s)", course.id)
    else:
        course = env["pe.course"].create(vals)
        env["ir.model.data"].create({
            "name": "course_rh_gamification",
            "module": "people_engine",
            "model": "pe.course",
            "res_id": course.id,
            "noupdate": False,
        })
        _logger.info("PE migration 19.0.6.0.36: cours RH Gamification créé (id=%s)", course.id)
