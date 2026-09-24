# -*- coding: utf-8 -*-
import logging

_logger = logging.getLogger(__name__)

COURSE_XMLID = "people_engine.course_renovation_immobilier"
CONTENT_URL = "/people_engine/static/src/html/formation_renovation_immobilier_fr.html"
TITLE = "Formation Rénovation & Immobilier — Qualification Lead IA"


def migrate(cr, version):
    env = globals().get("env")
    if not env:
        return
    course = env.ref(COURSE_XMLID, raise_if_not_found=False)
    vals = {
        "title": TITLE,
        "category": "crm",
        "course_type": "internal",
        "duration_hours": 7.0,
        "difficulty": "intermediate",
        "points_on_completion": 60,
        "description": (
            "Formation complète qualification lead IA rénovation et immobilier — 9 modules "
            "interactifs : produits Léa/Sofia, fiche propriété, écoénergie, réno intérieure/"
            "extérieure, immobilier, besoins & entrepreneurs, transfert & RDV, objections."
        ),
        "content_url": CONTENT_URL,
        "is_active": True,
    }
    if course:
        course.write(vals)
        _logger.info(
            "PE migration 19.0.6.0.39: cours Rénovation & Immobilier mis à jour (id=%s)",
            course.id,
        )
    else:
        course = env["pe.course"].create(vals)
        env["ir.model.data"].create({
            "name": "course_renovation_immobilier",
            "module": "people_engine",
            "model": "pe.course",
            "res_id": course.id,
            "noupdate": False,
        })
        _logger.info(
            "PE migration 19.0.6.0.39: cours Rénovation & Immobilier créé (id=%s)",
            course.id,
        )
