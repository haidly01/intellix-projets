import logging
import re
import unicodedata

from odoo import _, models
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)

MAX_MESSAGES = 15

SUMMARY_SYSTEM = (
    "Tu es un assistant de gestion de projet. À partir des informations et de "
    "l'historique fournis, résume l'état de la tâche de façon claire et concise. "
    "Structure : un court paragraphe de contexte, puis une liste à puces des points "
    "clés, et enfin les éventuels blocages ou risques. Réponds en français, en HTML "
    "simple (paragraphes <p>, listes <ul><li>). Ne réponds rien d'autre que le résumé."
)

NEXT_STEPS_SYSTEM = (
    "Tu es un assistant de gestion de projet. À partir des informations et de "
    "l'historique fournis, propose les prochaines étapes concrètes (3 à 6 actions) "
    "pour faire avancer cette tâche, dans l'ordre logique. Sois actionnable et "
    "spécifique. Réponds en français, en HTML simple, sous forme de liste numérotée "
    "<ol><li>. Ne réponds rien d'autre que la liste."
)

ASSIGNMENT_SYSTEM = (
    "Tu es un assistant de gestion de projet spécialisé dans l'attribution des "
    "tâches basée sur l'historique de l'équipe."
)


class ProjectTaskAiAssistant(models.Model):
    _inherit = "project.task"

    @staticmethod
    def _html_to_text(value):
        if not value:
            return ""
        text = re.sub(r"<br\s*/?>", "\n", value)
        text = re.sub(r"</p>", "\n", text)
        text = re.sub(r"<[^>]+>", " ", text)
        text = re.sub(r"[ \t]+", " ", text)
        return text.strip()

    def _ai_context(self):
        self.ensure_one()
        lines = [
            _("Tâche : %s") % (self.name or ""),
            _("Projet : %s") % (self.project_id.name or "—"),
            _("Étape : %s") % (self.stage_id.name or "—"),
            _("Assigné(s) : %s") % (", ".join(self.user_ids.mapped("name")) or "—"),
            _("Échéance : %s") % (self.date_deadline or "—"),
            _("Priorité : %s") % dict(self._fields["priority"].selection).get(
                self.priority, self.priority
            ),
        ]
        description = self._html_to_text(self.description)
        if description:
            lines.append(_("Description :\n%s") % description)

        messages = self.message_ids.filtered(
            lambda m: m.message_type in ("comment", "email") and m.body
        )[:MAX_MESSAGES]
        if messages:
            lines.append(_("\nHistorique des échanges (du plus récent au plus ancien) :"))
            for message in messages:
                author = message.author_id.name or _("Système")
                body = self._html_to_text(message.body)
                if body:
                    lines.append("- [%s] %s" % (author, body[:600]))
        return "\n".join(lines)

    def _run_ai_assistant(self, system_prompt, title):
        self.ensure_one()
        prompt = self._ai_context()
        purpose = "%s — tâche %s" % (title, self.name)
        answer = self.env["renovation.ai.service"]._call(
            [{"role": "user", "content": prompt}],
            system=system_prompt,
            purpose=purpose,
        )
        return self._post_assistant_result(answer, title)

    def _post_assistant_result(self, answer, title):
        body = answer or _("(Aucune réponse générée.)")
        self.message_post(
            body='<p><b>🤖 Assistant IA — %s</b></p>%s' % (title, body),
            subject=title,
        )
        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": _("Assistant IA"),
                "message": _("%s ajouté(e) au fil de discussion.") % title,
                "type": "success",
                "sticky": False,
                "next": {"type": "ir.actions.act_window_close"},
            },
        }

    def action_ai_summarize(self):
        self.ensure_one()
        prompt = self.env["renovation.ai.service"]._get_prompt(
            "task_summary", SUMMARY_SYSTEM
        )
        return self._run_ai_assistant(prompt, _("Résumé"))

    def action_ai_next_steps(self):
        self.ensure_one()
        prompt = self.env["renovation.ai.service"]._get_prompt(
            "task_next_steps", NEXT_STEPS_SYSTEM
        )
        return self._run_ai_assistant(prompt, _("Prochaines étapes"))

    def _ai_candidate_users(self):
        self.ensure_one()
        users = self.env["res.users"]
        if self.project_id.user_id:
            users |= self.project_id.user_id
        siblings = self.search([("project_id", "=", self.project_id.id)])
        users |= siblings.mapped("user_ids")
        users |= self.project_id.collaborator_ids.mapped("partner_id.user_ids")
        return users.filtered(lambda u: u.active and u.share is False)

    @staticmethod
    def _normalize(text):
        text = unicodedata.normalize("NFKD", text or "")
        text = "".join(char for char in text if not unicodedata.combining(char))
        return text.lower()

    def _ai_task_keywords(self):
        self.ensure_one()
        words = re.findall(r"\w+", self._normalize(self.name))
        return {word for word in words if len(word) > 3}

    def _ai_assignee_stats(self, candidates):
        """Statistiques d'historique par membre pour scorer l'assignation.

        Pour chaque membre : tâches clôturées, taux de respect des échéances,
        nombre de tâches similaires déjà traitées (mots-clés / étiquettes) et
        charge ouverte actuelle.
        """
        self.ensure_one()
        Task = self.env["project.task"]
        keywords = self._ai_task_keywords()
        tag_ids = set(self.tag_ids.ids)
        stats = {}
        for candidate in candidates:
            done = Task.search(
                [("user_ids", "in", candidate.id), ("stage_id.fold", "=", True)],
                limit=300,
            )
            on_time = rated = similar = 0
            for done_task in done:
                if done_task.date_deadline and done_task.date_last_stage_update:
                    rated += 1
                    if done_task.date_last_stage_update <= done_task.date_deadline:
                        on_time += 1
                task_name = self._normalize(done_task.name)
                if keywords and any(word in task_name for word in keywords):
                    similar += 1
                elif tag_ids and (set(done_task.tag_ids.ids) & tag_ids):
                    similar += 1
            load = Task.search_count(
                [
                    ("user_ids", "in", candidate.id),
                    ("active", "=", True),
                    ("stage_id.fold", "=", False),
                ]
            )
            stats[candidate.id] = {
                "name": candidate.name,
                "done": len(done),
                "on_time_rate": (on_time / rated) if rated else None,
                "similar": similar,
                "load": load,
            }
        return stats

    @staticmethod
    def _ai_assignee_score(stat):
        expertise = min(stat["similar"], 5) / 5.0
        on_time = stat["on_time_rate"] if stat["on_time_rate"] is not None else 0.5
        load_score = 1.0 / (1.0 + stat["load"])
        return 0.40 * expertise + 0.35 * on_time + 0.25 * load_score

    def action_ai_suggest_assignee(self):
        self.ensure_one()
        candidates = self._ai_candidate_users()
        if not candidates:
            raise UserError(
                _(
                    "Aucun membre identifié pour ce projet. Ajoutez un responsable, "
                    "des assignés ou des collaborateurs."
                )
            )
        stats = self._ai_assignee_stats(candidates)
        ranked = sorted(
            candidates,
            key=lambda candidate: self._ai_assignee_score(stats[candidate.id]),
            reverse=True,
        )
        best = ranked[0]

        def _otr(stat):
            return (
                _("n.d.")
                if stat["on_time_rate"] is None
                else "%.0f%%" % (stat["on_time_rate"] * 100)
            )

        stat_rows = "".join(
            "<li><b>%s</b> — score %.2f · %s tâche(s) similaire(s) · "
            "ponctualité %s · %s ouverte(s)</li>"
            % (
                stats[candidate.id]["name"],
                self._ai_assignee_score(stats[candidate.id]),
                stats[candidate.id]["similar"],
                _otr(stats[candidate.id]),
                stats[candidate.id]["load"],
            )
            for candidate in ranked
        )

        if self.env["renovation.ai.service"]._available():
            members_text = "\n".join(
                "- %s : %s tâche(s) clôturée(s), %s similaire(s), "
                "ponctualité %s, %s tâche(s) ouverte(s)"
                % (
                    stats[candidate.id]["name"],
                    stats[candidate.id]["done"],
                    stats[candidate.id]["similar"],
                    _otr(stats[candidate.id]),
                    stats[candidate.id]["load"],
                )
                for candidate in ranked
            )
            prompt = _(
                "Tâche à attribuer : %(task)s\n"
                "Projet : %(project)s\n"
                "Description : %(desc)s\n\n"
                "Historique des membres (tâches clôturées, expérience sur des "
                "tâches similaires, ponctualité, charge ouverte) :\n%(members)s\n\n"
                "En te basant sur l'EXPÉRIENCE sur des tâches similaires, la "
                "ponctualité passée et une charge équilibrée, recommande LA "
                "personne la plus adaptée. Réponds en HTML simple : une phrase en "
                "gras avec le nom recommandé, puis 1 à 2 phrases de justification."
            ) % {
                "task": self.name,
                "project": self.project_id.name,
                "desc": self._html_to_text(self.description) or "—",
                "members": members_text,
            }
            answer = self.env["renovation.ai.service"]._call(
                [{"role": "user", "content": prompt}],
                system=self.env["renovation.ai.service"]._get_prompt(
                    "assignment", ASSIGNMENT_SYSTEM
                ),
                purpose="Suggestion d'assignation — tâche %s" % self.name,
            )
            body = (
                "<p><b>🤖 Suggestion d'assignation (IA + historique)</b></p>"
                "%s"
                "<p class='text-muted'>Classement basé sur l'historique :</p>"
                "<ul>%s</ul>" % (answer or "", stat_rows)
            )
        else:
            body = (
                "<p><b>🤖 Suggestion d'assignation (historique)</b></p>"
                "<p>Membre recommandé : <b>%s</b> (meilleur score "
                "expérience / ponctualité / charge).</p>"
                "<p class='text-muted'>Classement basé sur l'historique :</p>"
                "<ul>%s</ul>" % (best.name, stat_rows)
            )

        self.message_post(body=body, subject=_("Suggestion d'assignation"))
        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": _("Suggestion d'assignation"),
                "message": _("Recommandation ajoutée au fil de discussion."),
                "type": "success",
                "sticky": False,
            },
        }
