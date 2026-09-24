import logging

from odoo import _, api, fields, models

_logger = logging.getLogger(__name__)

KARMA_LEAD_CREATED = 5
KARMA_WON_PER_100 = 1        # 1 point par tranche de 100 $ gagnée
KARMA_WON_MIN = 10          # plancher de points pour une vente gagnée
KARMA_GOAL_BONUS = 30       # bonus à l'atteinte de l'objectif mensuel perso
BIG_DEAL_THRESHOLD = 10000  # seuil "grosse vente" notifiée à l'équipe


class CrmLeadGamification(models.Model):
    _inherit = "crm.lead"

    gamification_won_awarded = fields.Boolean(
        string="Points « gagné » attribués",
        default=False,
        copy=False,
    )

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    def _award_karma(self, user, points, reason):
        if user and user._doorway_is_equipe_interne() and points:
            try:
                user.sudo()._add_karma(points, reason=reason)
            except Exception:
                _logger.exception("Gamification: échec attribution karma")

    def _won_karma_points(self):
        """Points proportionnels au montant gagné (avec plancher)."""
        self.ensure_one()
        revenue = self.expected_revenue or 0.0
        return max(KARMA_WON_MIN, int(revenue / 100.0) * KARMA_WON_PER_100)

    def _handle_won_gamification(self):
        """Tout ce qui se déclenche quand une opportunité est gagnée."""
        self.ensure_one()
        user = self.user_id
        if not user:
            return
        points = self._won_karma_points()
        self._award_karma(
            user, points,
            _("Opportunité gagnée : %(name)s (+%(pts)s pts)")
            % {"name": self.name or "", "pts": points},
        )
        self._grant_first_sale_badge(user)
        self._notify_big_deal(user)
        self._check_personal_goal(user)

    def _grant_first_sale_badge(self, user):
        badge = self.env.ref(
            "renovation_conciergerie.badge_first_sale", raise_if_not_found=False
        )
        if not badge:
            return
        BadgeUser = self.env["gamification.badge.user"].sudo()
        if BadgeUser.search_count(
            [("badge_id", "=", badge.id), ("user_id", "=", user.id)]
        ):
            return
        others_won = self.sudo().search_count([
            ("user_id", "=", user.id),
            ("stage_id.is_won", "=", True),
            ("id", "!=", self.id),
        ])
        if others_won:
            return
        try:
            rec = BadgeUser.create({"badge_id": badge.id, "user_id": user.id})
            rec._send_badge()
        except Exception:
            _logger.exception("Gamification: échec attribution badge Première vente")

    def _notify_big_deal(self, user):
        if (self.expected_revenue or 0.0) < BIG_DEAL_THRESHOLD:
            return
        Team = self.env["crm.team"]
        members = self.team_id.crm_team_member_ids.user_id
        admins = Team._get_agence_doorway_admin_users()
        partners = (members | admins | user).partner_id
        body = _(
            "<p>🎉 <b>Grosse vente !</b> %(user)s vient de conclure "
            "<b>%(deal)s</b> pour <b>%(amount)s $</b>. Bravo l'équipe ! 👏</p>"
        ) % {
            "user": user.name,
            "deal": self.name or "",
            "amount": "{:,.0f}".format(self.expected_revenue or 0.0).replace(",", " "),
        }
        try:
            self.message_post(
                body=body,
                subject=_("Grosse vente conclue"),
                partner_ids=partners.ids,
            )
        except Exception:
            _logger.exception("Gamification: échec notification grosse vente")

    def _check_personal_goal(self, user):
        target = user.gamification_monthly_goal
        if not target:
            return
        month_start = fields.Datetime.now().replace(
            day=1, hour=0, minute=0, second=0, microsecond=0
        )
        won_this_month = self.sudo().search_count([
            ("user_id", "=", user.id),
            ("stage_id.is_won", "=", True),
            ("date_closed", ">=", fields.Datetime.to_string(month_start)),
        ])
        if won_this_month != target:
            return
        # Atteint pile l'objectif : félicitations + bonus (une seule fois)
        self._award_karma(
            user, KARMA_GOAL_BONUS,
            _("Objectif mensuel atteint (%s ventes)") % target,
        )
        try:
            self.message_post(
                body=_(
                    "<p>🎯 <b>Objectif mensuel atteint !</b> %(user)s a conclu ses "
                    "<b>%(n)s</b> ventes du mois. Bonus de %(b)s points ! 🏆</p>"
                ) % {"user": user.name, "n": target, "b": KARMA_GOAL_BONUS},
                subject=_("Objectif mensuel atteint"),
                partner_ids=user.partner_id.ids,
            )
        except Exception:
            _logger.exception("Gamification: échec notification objectif perso")

    # ------------------------------------------------------------------
    # ORM
    # ------------------------------------------------------------------
    @api.model_create_multi
    def create(self, vals_list):
        leads = super().create(vals_list)
        for lead in leads:
            user = lead.user_id or self.env.user
            lead._award_karma(
                user, KARMA_LEAD_CREATED, _("Nouveau lead : %s") % (lead.name or "")
            )
            if lead.stage_id.is_won and not lead.gamification_won_awarded:
                lead.gamification_won_awarded = True
                lead._handle_won_gamification()
        return leads

    def write(self, vals):
        track_won = "stage_id" in vals or "probability" in vals
        res = super().write(vals)
        if track_won:
            for lead in self:
                if lead.stage_id.is_won and not lead.gamification_won_awarded:
                    lead.gamification_won_awarded = True
                    lead._handle_won_gamification()
        return res

    def action_set_won_rainbowman(self):
        res = super().action_set_won_rainbowman()
        if isinstance(res, dict) and res.get("effect"):
            pts = self._won_karma_points() if len(self) == 1 else 0
            res["effect"]["message"] = _(
                "Bravo %(user)s ! Opportunité gagnée 🎉 (+%(pts)s points)"
            ) % {"user": self.env.user.name, "pts": pts}
            res["effect"]["fadeout"] = "slow"
        return res

    @api.model
    def _setup_doorway_gamification(self):
        """Crée (une fois) les défis de classement Doorway. Best-effort."""
        try:
            Challenge = self.env["gamification.challenge"]
            GoalDef = self.env["gamification.goal.definition"]
            badge = self.env.ref(
                "renovation_conciergerie.badge_best_seller", raise_if_not_found=False
            )

            def _lines(opp_target, lead_target):
                cmds = []
                for dname, target in (
                    ("New Opportunities", opp_target),
                    ("New Leads", lead_target),
                ):
                    d = GoalDef.search([("name", "=", dname)], limit=1)
                    if d:
                        cmds.append((0, 0, {"definition_id": d.id, "target_goal": target}))
                return cmds

            specs = [
                ("Défi mensuel Doorway", "monthly", 10, 30),
                ("Défi hebdo Doorway", "weekly", 3, 8),
            ]
            for name, period, opp_t, lead_t in specs:
                if Challenge.search([("name", "=", name)], limit=1):
                    continue
                lines = _lines(opp_t, lead_t)
                if not lines:
                    continue
                vals = {
                    "name": name,
                    "description": "Classement %s des leads et opportunités gagnées." % (
                        "mensuel" if period == "monthly" else "hebdomadaire"),
                    "period": period,
                    "visibility_mode": "ranking",
                    "report_message_frequency": period,
                    "user_domain": self.env["res.users"]._doorway_equipe_interne_domain_expr(),
                    "line_ids": lines,
                }
                if badge and period == "monthly":
                    vals["reward_first_id"] = badge.id
                challenge = Challenge.create(vals)
                if hasattr(challenge, "action_start"):
                    challenge.action_start()
        except Exception:
            _logger.exception("Gamification: échec configuration des défis")
