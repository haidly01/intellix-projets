# -*- coding: utf-8 -*-
from odoo import _, api, fields, models


class DoorwayOnboardingWizard(models.TransientModel):
    _name = "doorway.onboarding.wizard"
    _description = "Assistant visite guidée Doorway"

    tour_id = fields.Many2one("doorway.onboarding.tour", required=True)
    tour_code = fields.Char(related="tour_id.code")
    current_step_key = fields.Char(default="welcome")
    is_admin = fields.Boolean(compute="_compute_is_admin")
    is_last_step = fields.Boolean(compute="_compute_progress")
    progress_percent = fields.Integer(compute="_compute_progress")
    progress_label = fields.Char(compute="_compute_progress")
    step_title = fields.Char(compute="_compute_current_step")
    step_body_html = fields.Html(compute="_compute_current_step", sanitize=False)
    step_action_xmlid = fields.Char(compute="_compute_current_step")
    step_action_label = fields.Char(compute="_compute_current_step")
    quest_label = fields.Char(related="tour_id.quest_label")
    reward_badge_icon = fields.Char()
    reward_badge_name = fields.Char()
    reward_points = fields.Integer()
    reward_message = fields.Char()

    @api.depends()
    def _compute_is_admin(self):
        is_admin = self.env.user.has_group("base.group_system")
        for wiz in self:
            wiz.is_admin = is_admin

    def _visible_steps(self):
        self.ensure_one()
        steps = self.tour_id.step_ids
        if not self.is_admin:
            steps = steps.filtered(lambda s: not s.admin_only)
        return steps.sorted("sequence")

    @api.depends("current_step_key", "tour_id", "is_admin")
    def _compute_progress(self):
        for wiz in self:
            if wiz.current_step_key == "celebrate":
                wiz.is_last_step = False
                wiz.progress_percent = 100
                wiz.progress_label = _("Terminé !")
                continue
            steps = wiz._visible_steps()
            keys = [s.key for s in steps]
            if not keys:
                wiz.is_last_step = True
                wiz.progress_percent = 100
                wiz.progress_label = ""
                continue
            if wiz.current_step_key not in keys:
                wiz.current_step_key = keys[0]
            idx = keys.index(wiz.current_step_key)
            total = len(keys)
            wiz.is_last_step = idx == total - 1
            wiz.progress_percent = int(((idx + 1) / total) * 100)
            wiz.progress_label = _("Étape %(c)s / %(t)s") % {"c": idx + 1, "t": total}

    @api.depends("current_step_key", "tour_id")
    def _compute_current_step(self):
        for wiz in self:
            step = wiz._visible_steps().filtered(
                lambda s: s.key == wiz.current_step_key
            )[:1]
            wiz.step_title = step.title if step else ""
            wiz.step_body_html = step.body_html if step else ""
            wiz.step_action_xmlid = step.action_xmlid if step else False
            wiz.step_action_label = step.action_label if step else ""

    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        tour = self.env["doorway.onboarding.tour"].browse(
            self.env.context.get("default_tour_id")
        )
        if not tour and self.env.context.get("default_tour_code"):
            tour = self.env["doorway.onboarding.tour"].search(
                [("code", "=", self.env.context["default_tour_code"])], limit=1
            )
        if tour:
            res["tour_id"] = tour.id
            steps = tour.step_ids.sorted("sequence")
            if not self.env.user.has_group("base.group_system"):
                steps = steps.filtered(lambda s: not s.admin_only)
            if steps:
                res["current_step_key"] = steps[0].key
        return res

    def _reopen(self):
        return {
            "type": "ir.actions.act_window",
            "res_model": self._name,
            "res_id": self.id,
            "view_mode": "form",
            "target": "new",
        }

    def action_next(self):
        self.ensure_one()
        if self.current_step_key == "celebrate":
            return self.action_go_home()
        keys = [s.key for s in self._visible_steps()]
        idx = keys.index(self.current_step_key)
        if idx < len(keys) - 1:
            self.current_step_key = keys[idx + 1]
        return self._reopen()

    def action_previous(self):
        self.ensure_one()
        if self.current_step_key == "celebrate":
            keys = [s.key for s in self._visible_steps()]
            self.current_step_key = keys[-1] if keys else "welcome"
            return self._reopen()
        keys = [s.key for s in self._visible_steps()]
        idx = keys.index(self.current_step_key)
        if idx > 0:
            self.current_step_key = keys[idx - 1]
        return self._reopen()

    def action_skip(self):
        self.ensure_one()
        self.env["doorway.onboarding.service"]._mark_onboarding_done(
            self.tour_id.code
        )
        return self.env["doorway.onboarding.service"]._action_home_after_tour(
            self.tour_id.code
        )

    def action_finish(self):
        self.ensure_one()
        result = self.env["doorway.onboarding.service"].award_tour_reward(
            self.tour_id
        )
        self.write(
            {
                "current_step_key": "celebrate",
                "reward_badge_icon": result.get("badge_icon") or "🏆",
                "reward_badge_name": result.get("badge_name") or self.tour_id.name,
                "reward_points": result.get("points") or self.tour_id.reward_points,
                "reward_message": result.get("message") or "",
            }
        )
        self.env["doorway.onboarding.service"]._mark_onboarding_done(
            self.tour_id.code
        )
        return self._reopen()

    def action_go_home(self):
        self.ensure_one()
        return self.env["doorway.onboarding.service"]._action_home_after_tour(
            self.tour_id.code
        )

    def action_open_step_link(self):
        self.ensure_one()
        if not self.step_action_xmlid:
            return self._reopen()
        action = self.env.ref(self.step_action_xmlid, raise_if_not_found=False)
        if not action:
            return self._reopen()
        return action.read()[0]
