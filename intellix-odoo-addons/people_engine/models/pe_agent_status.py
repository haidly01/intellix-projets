# -*- coding: utf-8 -*-
import logging
from datetime import date, datetime, time, timedelta

from odoo import api, fields, models

_logger = logging.getLogger(__name__)

CC_STATUS_MAP = {
    "INCALL": "on_call",
    "QUEUE": "on_call",
    "RING": "on_call",
    "PAUSED": "pause",
    "READY": "online",
    "CLOSER": "on_call",
}


class PeEmployeeProfileCallCenter(models.Model):
    _inherit = "pe.employee.profile"

    cc_status = fields.Selection(
        [
            ("online", "En ligne"),
            ("on_call", "En appel"),
            ("pause", "En pause"),
            ("offline", "Hors ligne"),
            ("inactive", "Inactif"),
        ],
        string="Statut Call Center",
        default="offline",
    )
    cc_status_since = fields.Datetime(string="Statut depuis")
    appels_jour = fields.Integer(string="Appels aujourd'hui")
    demos_bookees_jour = fields.Integer(string="Démos bookées aujourd'hui")
    ventes_jour = fields.Integer(string="Ventes aujourd'hui")
    score_ia_moy_jour = fields.Float(string="Score IA moyen aujourd'hui")
    points_jour = fields.Integer(string="Points aujourd'hui")
    points_semaine = fields.Integer(string="Points cette semaine")
    points_mois = fields.Integer(string="Points ce mois")
    cc_call_log_ids = fields.One2many(
        "pe.call.log",
        "profile_id",
        string="Appels Call Center",
    )
    cc_rank_jour = fields.Integer(string="Rang journalier")
    cc_rank_semaine = fields.Integer(string="Rang hebdomadaire")

    def _today_range(self):
        today = fields.Date.today()
        start = datetime.combine(today, time.min)
        end = datetime.combine(today, time.max)
        return start, end

    def refresh_daily_cc_stats(self):
        CallLog = self.env["pe.call.log"].sudo()
        PointTx = self.env["pe.point.transaction"].sudo()
        today = fields.Date.today()
        week_start = today - timedelta(days=today.weekday())
        month_start = today.replace(day=1)
        for profile in self:
            emp = profile.employee_id
            if not emp:
                continue
            day_start, day_end = profile._today_range()
            logs = CallLog.search(
                [
                    ("employee_id", "=", emp.id),
                    ("date_call", ">=", day_start),
                    ("date_call", "<=", day_end),
                ]
            )
            profile.appels_jour = len(logs)
            demos = len(logs.filtered(lambda l: l.outcome == "demo_bookee"))
            if profile.user_id:
                demos += self.env["crm.lead"].sudo().search_count(
                    [
                        ("user_id", "=", profile.user_id.id),
                        ("source_vicidial", "=", True),
                        ("qualification_statut", "=", "rdv"),
                        ("write_date", ">=", day_start),
                        ("write_date", "<=", day_end),
                    ]
                )
            profile.demos_bookees_jour = demos
            profile.ventes_jour = len(logs.filtered(lambda l: l.outcome == "vendu"))
            scores = [l.ai_score for l in logs if l.ai_score]
            profile.score_ia_moy_jour = (
                sum(scores) / len(scores) if scores else 0.0
            )
            txs = PointTx.search([("profile_id", "=", profile.id)])
            profile.points_jour = sum(
                t.points
                for t in txs
                if t.date and fields.Datetime.to_datetime(t.date).date() == today
            )
            profile.points_semaine = sum(
                t.points
                for t in txs
                if t.date
                and fields.Datetime.to_datetime(t.date).date() >= week_start
            )
            profile.points_mois = sum(
                t.points
                for t in txs
                if t.date
                and fields.Datetime.to_datetime(t.date).date() >= month_start
            )

    @api.model
    def sync_cc_status_from_vicidial(self):
        """Cron : statut temps réel depuis VICIdial MySQL."""
        profiles = self.sudo().search(
            [
                ("vicidial_user", "!=", False),
                ("department_pe_id.work_type", "in", ("mixte", "qualification")),
            ]
        )
        if not profiles:
            return True
        try:
            from odoo.addons.doorway_vicidial_campaigns.services.vicidial_service import (
                VicidialService,
            )

            svc = VicidialService(self.env)
            if not svc.is_available():
                return True
            conn = svc._connect()
            cur = conn.cursor(dictionary=True)
            users = [p.vicidial_user for p in profiles if p.vicidial_user]
            if not users:
                conn.close()
                return True
            placeholders = ",".join(["%s"] * len(users))
            cur.execute(
                """
                SELECT user, status, last_call_time
                FROM vicidial_live_agents
                WHERE user IN (%s)
                """
                % placeholders,
                tuple(users),
            )
            live_map = {row["user"]: row for row in cur.fetchall()}
            cur.close()
            conn.close()
            now = fields.Datetime.now()
            for profile in profiles:
                row = live_map.get(profile.vicidial_user)
                new_status = "offline"
                if row:
                    new_status = CC_STATUS_MAP.get(row.get("status"), "online")
                if profile.cc_status != new_status:
                    profile.write(
                        {"cc_status": new_status, "cc_status_since": now}
                    )
        except Exception as exc:
            _logger.warning("PE CC sync VICIdial: %s", exc)
        return True
