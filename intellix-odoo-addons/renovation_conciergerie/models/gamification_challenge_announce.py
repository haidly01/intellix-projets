import logging

from odoo import _, api, fields, models

_logger = logging.getLogger(__name__)

DOORWAY_CHALLENGE_NAMES = [
    "Défi mensuel Doorway",
    "Défi hebdo Doorway",
    "Défi mensuel Tâches Doorway",
    "Défi hebdo Tâches Doorway",
]


class GamificationChallengeAnnounce(models.Model):
    _inherit = "gamification.challenge"

    doorway_last_announce = fields.Date(
        string="Dernière annonce de clôture Doorway", copy=False
    )

    @staticmethod
    def _fmt(value):
        return "%d" % value if float(value).is_integer() else "%.1f" % value

    def _announce_finished_period(self):
        """Annonce le gagnant de la dernière période close (best-effort)."""
        self.ensure_one()
        today = fields.Date.today()
        Goal = self.env["gamification.goal"]
        goals = Goal.search(
            [("challenge_id", "=", self.id), ("end_date", "<", today)],
            order="end_date desc",
        )
        if not goals:
            return False
        latest_end = goals[0].end_date
        if self.doorway_last_announce == latest_end:
            return False
        period_goals = goals.filtered(lambda goal: goal.end_date == latest_end)

        ranked = period_goals.sorted(lambda goal: goal.current, reverse=True)
        winner = ranked[0] if ranked and ranked[0].current > 0 else None

        participants = self.user_ids or period_goals.mapped("user_id")
        participants = participants.filtered(lambda u: u._doorway_is_equipe_interne())
        partner_ids = participants.partner_id.ids
        if not partner_ids:
            self.doorway_last_announce = latest_end
            return False

        if winner:
            badge_txt = (
                _(" Le badge « %s » lui est décerné. 🏅") % self.reward_first_id.name
                if self.reward_first_id
                else ""
            )
            podium = "".join(
                "<li>%s — %s</li>"
                % (goal.user_id.name, self._fmt(goal.current))
                for goal in ranked[:3]
                if goal.current > 0
            )
            body = _(
                "<p>🏁 <b>Fin du défi « %(name)s » !</b></p>"
                "<p>🥇 Bravo <b>%(winner)s</b> avec <b>%(score)s</b> !%(badge)s</p>"
                "<p>Podium :</p><ol>%(podium)s</ol>"
                "<p>Un nouveau défi recommence — à vos tâches ! 💪</p>"
            ) % {
                "name": self.name,
                "winner": winner.user_id.name,
                "score": self._fmt(winner.current),
                "badge": badge_txt,
                "podium": podium,
            }
        else:
            body = _(
                "<p>🏁 <b>Fin du défi « %(name)s » !</b></p>"
                "<p>Aucun point marqué cette période. Nouveau départ, "
                "c'est le moment de prendre la tête ! 💪</p>"
            ) % {"name": self.name}

        try:
            self.message_post(
                body=body,
                subject=_("Fin du défi : %s") % self.name,
                partner_ids=partner_ids,
            )
        except Exception:  # noqa: BLE001
            _logger.exception("Annonce de fin de défi : échec notification")

        self.doorway_last_announce = latest_end
        return True

    @api.model
    def _cron_doorway_announce_challenges(self):
        challenges = self.search([("name", "in", DOORWAY_CHALLENGE_NAMES)])
        count = 0
        for challenge in challenges:
            try:
                if challenge._announce_finished_period():
                    count += 1
            except Exception:  # noqa: BLE001
                _logger.exception(
                    "Annonce de fin de défi : échec pour %s", challenge.name
                )
        _logger.info("Annonces de fin de défi envoyées : %s", count)
        return count
