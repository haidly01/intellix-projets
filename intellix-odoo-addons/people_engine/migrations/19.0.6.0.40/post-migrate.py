# -*- coding: utf-8 -*-
import logging

_logger = logging.getLogger(__name__)

QUIZ_XMLID = "people_engine.quiz_renovation_demo"
COURSE_XMLID = "people_engine.course_renovation_immobilier"


def migrate(cr, version):
    env = globals().get("env")
    if not env:
        return

    # Migration champs legacy pe.quiz.question (question → question_text)
    cr.execute(
        """
        SELECT column_name FROM information_schema.columns
        WHERE table_name = 'pe_quiz_question' AND column_name = 'question'
        """
    )
    if cr.fetchone():
        cr.execute(
            """
            SELECT column_name FROM information_schema.columns
            WHERE table_name = 'pe_quiz_question' AND column_name = 'question_text'
            """
        )
        if not cr.fetchone():
            cr.execute("ALTER TABLE pe_quiz_question RENAME COLUMN question TO question_text")
            _logger.info("PE 19.0.6.0.40: pe_quiz_question.question → question_text")

    cr.execute(
        """
        SELECT column_name FROM information_schema.columns
        WHERE table_name = 'pe_quiz' AND column_name = 'time_limit_minutes'
        """
    )
    if cr.fetchone():
        cr.execute(
            """
            SELECT column_name FROM information_schema.columns
            WHERE table_name = 'pe_quiz' AND column_name = 'time_limit'
            """
        )
        if not cr.fetchone():
            cr.execute("ALTER TABLE pe_quiz RENAME COLUMN time_limit_minutes TO time_limit")
            _logger.info("PE 19.0.6.0.40: pe_quiz.time_limit_minutes → time_limit")

    quiz = env.ref(QUIZ_XMLID, raise_if_not_found=False)
    course = env.ref(COURSE_XMLID, raise_if_not_found=False)
    if quiz and course and not course.quiz_id:
        course.write({"quiz_id": quiz.id, "passing_score": quiz.passing_score})
        _logger.info(
            "PE 19.0.6.0.40: cours Rénovation lié au quiz demo (course=%s quiz=%s)",
            course.id,
            quiz.id,
        )
