import logging

from odoo import _, api, fields, models

_logger = logging.getLogger(__name__)

KARMA_TASK_CREATED = 2
KARMA_TASK_DONE_BASE = 15
KARMA_ONTIME_BONUS = 5
KARMA_GOAL_BONUS = 30
PRIORITY_BONUS = {"0": 0, "1": 5, "2": 10, "3": 15}


class ProjectTaskGamification(models.Model):
    _inherit = "project.task"

    gamification_done_awarded = fields.Boolean(
        string="Points « terminée » attribués", default=False, copy=False
    )

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    def _award_karma(self, user, points, reason):
        if user and user._doorway_is_equipe_interne() and points:
            try:
                user.sudo()._add_karma(points, reason=reason)
            except Exception:  # noqa: BLE001
                _logger.exception("Gamification projet : échec attribution karma")

    def _task_done_points(self):
        self.ensure_one()
        points = KARMA_TASK_DONE_BASE + PRIORITY_BONUS.get(self.priority, 0)
        if self.date_deadline and self.date_deadline >= fields.Datetime.now():
            points += KARMA_ONTIME_BONUS
        return points

    def _is_done_stage(self):
        self.ensure_one()
        return bool(self.stage_id and self.stage_id.fold)

    def _handle_done_gamification(self):
        self.ensure_one()
        assignees = self.user_ids.filtered(lambda u: u._doorway_is_equipe_interne())
        if not assignees:
            return
        points = self._task_done_points()
        ontime = bool(
            self.date_deadline and self.date_deadline >= fields.Datetime.now()
        )
        for user in assignees:
            self._award_karma(
                user,
                points,
                _("Tâche terminée : %(name)s (+%(pts)s pts)")
                % {"name": self.name or "", "pts": points},
            )
            self._grant_first_task_badge(user)
            self._check_project_goal(user)
        try:
            self.message_post(
                body=_(
                    "<p>🎉 <b>Tâche terminée !</b> +%(pts)s points%(bonus)s. Bravo "
                    "%(who)s ! 👏</p>"
                )
                % {
                    "pts": points,
                    "bonus": _(" (dont bonus ponctualité)") if ontime else "",
                    "who": ", ".join(assignees.mapped("name")),
                },
                subject=_("Tâche terminée"),
            )
        except Exception:  # noqa: BLE001
            _logger.exception("Gamification projet : échec note de félicitations")

    def _check_project_goal(self, user):
        target = user.project_monthly_goal
        if not target:
            return
        month_start = fields.Datetime.now().replace(
            day=1, hour=0, minute=0, second=0, microsecond=0
        )
        done_this_month = self.sudo().search_count(
            [
                ("user_ids", "in", user.id),
                ("stage_id.fold", "=", True),
                ("date_last_stage_update", ">=", fields.Datetime.to_string(month_start)),
            ]
        )
        if done_this_month != target:
            return
        self._award_karma(
            user,
            KARMA_GOAL_BONUS,
            _("Objectif mensuel de tâches atteint (%s tâches)") % target,
        )
        try:
            self.message_post(
                body=_(
                    "<p>🎯 <b>Objectif mensuel atteint !</b> %(user)s a terminé ses "
                    "<b>%(n)s</b> tâches du mois. Bonus de %(b)s points ! 🏆</p>"
                )
                % {"user": user.name, "n": target, "b": KARMA_GOAL_BONUS},
                subject=_("Objectif mensuel de tâches atteint"),
                partner_ids=user.partner_id.ids,
            )
        except Exception:  # noqa: BLE001
            _logger.exception("Gamification projet : échec notification objectif")

    def _grant_first_task_badge(self, user):
        badge = self.env.ref(
            "renovation_conciergerie.badge_first_task", raise_if_not_found=False
        )
        if not badge:
            return
        BadgeUser = self.env["gamification.badge.user"].sudo()
        if BadgeUser.search_count(
            [("badge_id", "=", badge.id), ("user_id", "=", user.id)]
        ):
            return
        others_done = self.sudo().search_count(
            [
                ("user_ids", "in", user.id),
                ("stage_id.fold", "=", True),
                ("id", "!=", self.id),
            ]
        )
        if others_done:
            return
        try:
            rec = BadgeUser.create({"badge_id": badge.id, "user_id": user.id})
            rec._send_badge()
        except Exception:  # noqa: BLE001
            _logger.exception("Gamification projet : échec badge Première tâche")

    # ------------------------------------------------------------------
    # ORM
    # ------------------------------------------------------------------
    @api.model_create_multi
    def create(self, vals_list):
        tasks = super().create(vals_list)
        for task in tasks:
            task._award_karma(
                self.env.user,
                KARMA_TASK_CREATED,
                _("Nouvelle tâche : %s") % (task.name or ""),
            )
            if task._is_done_stage() and not task.gamification_done_awarded:
                task.gamification_done_awarded = True
                task._handle_done_gamification()
        return tasks

    def write(self, vals):
        track = "stage_id" in vals
        res = super().write(vals)
        if track:
            for task in self:
                if task._is_done_stage() and not task.gamification_done_awarded:
                    task.gamification_done_awarded = True
                    task._handle_done_gamification()
        return res

    # ------------------------------------------------------------------
    # Défis projet (best-effort)
    # ------------------------------------------------------------------
    @api.model
    def _setup_project_gamification(self):
        """Crée (une fois) la définition d'objectif et les défis projet."""
        try:
            GoalDef = self.env["gamification.goal.definition"]
            Challenge = self.env["gamification.challenge"]
            Field = self.env["ir.model.fields"]

            model = self.env["ir.model"]._get("project.task")
            field_user = Field.search(
                [("model", "=", "project.task"), ("name", "=", "user_ids")], limit=1
            )
            if not field_user:
                return

            definition = GoalDef.search(
                [("name", "=", "Tâches terminées Doorway")], limit=1
            )
            if not definition:
                definition = GoalDef.create(
                    {
                        "name": "Tâches terminées Doorway",
                        "computation_mode": "count",
                        "model_id": model.id,
                        "domain": "[('stage_id.fold', '=', True)]",
                        "batch_mode": True,
                        "batch_distinctive_field": field_user.id,
                        "batch_user_expression": "user.id",
                        "condition": "higher",
                        "display_mode": "progress",
                    }
                )

            badge = self.env.ref(
                "renovation_conciergerie.badge_task_champion",
                raise_if_not_found=False,
            )
            specs = [
                ("Défi mensuel Tâches Doorway", "monthly", 20),
                ("Défi hebdo Tâches Doorway", "weekly", 5),
            ]
            for name, period, target in specs:
                if Challenge.search([("name", "=", name)], limit=1):
                    continue
                vals = {
                    "name": name,
                    "description": "Classement des tâches de projet terminées.",
                    "period": period,
                    "visibility_mode": "ranking",
                    "report_message_frequency": period,
                    "user_domain": self.env["res.users"]._doorway_equipe_interne_domain_expr(),
                    "line_ids": [
                        (0, 0, {"definition_id": definition.id, "target_goal": target})
                    ],
                }
                if badge and period == "monthly":
                    vals["reward_first_id"] = badge.id
                challenge = Challenge.create(vals)
                if hasattr(challenge, "action_start"):
                    challenge.action_start()
        except Exception:  # noqa: BLE001
            _logger.exception("Gamification projet : échec configuration des défis")
