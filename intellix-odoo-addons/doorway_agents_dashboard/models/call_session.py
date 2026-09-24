# -*- coding: utf-8 -*-
import logging
from datetime import timedelta

from odoo import _, api, fields, models

from odoo.addons.doorway_agents_dashboard.services.claude_service import ClaudeService
from odoo.addons.doorway_agents_dashboard.services.vicidial_coaching_service import VicidialService

_logger = logging.getLogger(__name__)


class DoorwayCallSession(models.Model):
    _name = "doorway.call.session"
    _description = "Session d'appel agent IA"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "date_start desc"

    name = fields.Char(compute="_compute_name", store=True)
    agent_id = fields.Many2one(
        "doorway.agent.profile", string="Agent IA", tracking=True, index=True
    )
    legacy_agent_ia_id = fields.Many2one(
        "doorway.agent.ia",
        string="Agent IA (legacy)",
        help="Champ conservé pour migration depuis doorway_agents_ia.",
    )
    lead_id = fields.Many2one("crm.lead", string="Lead CRM", tracking=True)
    twilio_call_sid = fields.Char(index=True)
    call_status = fields.Selection(
        [
            ("initiated", "Initié"),
            ("ringing", "Sonnerie"),
            ("in-progress", "En cours"),
            ("completed", "Terminé"),
            ("failed", "Échoué"),
            ("busy", "Occupé"),
            ("no-answer", "Pas de réponse"),
            ("voicemail", "Répondeur"),
        ],
        default="initiated",
        tracking=True,
    )
    from_number = fields.Char()
    to_number = fields.Char()
    date_start = fields.Datetime(default=fields.Datetime.now)
    date_end = fields.Datetime()
    duration = fields.Integer(string="Durée (s)", compute="_compute_duration", store=True)
    recording_url = fields.Char(string="URL enregistrement")
    transcript = fields.Text()
    claude_analysis_realtime = fields.Text(string="Analyse Claude (temps réel)")
    coaching_notes = fields.Text(string="Notes coaching")
    vicidial_campaign_id = fields.Char(string="Campagne VICIdial")
    last_coaching_at = fields.Datetime()
    report_id = fields.Many2one("doorway.call.report", string="Rapport", readonly=True)
    is_live = fields.Boolean(compute="_compute_is_live")

    @api.depends("lead_id", "agent_id", "twilio_call_sid")
    def _compute_name(self):
        for rec in self:
            parts = [rec.agent_id.name or "Appel", rec.lead_id.name or rec.twilio_call_sid or ""]
            rec.name = " — ".join(p for p in parts if p)

    @api.depends("date_start", "date_end")
    def _compute_duration(self):
        for rec in self:
            if rec.date_start and rec.date_end:
                rec.duration = int((rec.date_end - rec.date_start).total_seconds())
            else:
                rec.duration = 0

    @api.depends("call_status")
    def _compute_is_live(self):
        live = {"initiated", "ringing", "in-progress"}
        for rec in self:
            rec.is_live = rec.call_status in live

    def action_open_coaching(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": _("Coaching en direct"),
            "res_model": "doorway.call.coaching.wizard",
            "view_mode": "form",
            "target": "new",
            "context": {"default_session_id": self.id},
        }

    def run_realtime_coaching(self):
        """Analyse Claude sur le delta transcript (~30 s, Haiku + cache)."""
        for rec in self:
            if not rec.transcript or rec.call_status == "voicemail":
                continue
            prompt = rec.agent_id.system_prompt if rec.agent_id else ""
            previous = {
                "summary": (rec.claude_analysis_realtime or "Début d appel")[:200],
            }
            analysis = ClaudeService(rec.env).analyze_call_realtime(
                rec.transcript,
                previous_analysis=previous,
                agent_prompt=prompt,
                call_id=rec.twilio_call_sid,
            )
            if isinstance(analysis, dict) and analysis.get("error"):
                continue
            if analysis:
                rec.write(
                    {
                        "claude_analysis_realtime": analysis,
                        "last_coaching_at": fields.Datetime.now(),
                    }
                )

    def finalize_call(self):
        """Clôture l'appel et génère le rapport post-appel (sauf répondeur AMD)."""
        Report = self.env["doorway.call.report"]
        for rec in self:
            if rec.call_status == "voicemail":
                rec.write({"date_end": fields.Datetime.now()})
                VicidialService(rec.env).sync_with_odoo()
                continue
            vals_end = {"date_end": fields.Datetime.now(), "call_status": "completed"}
            rec.write(vals_end)
            if not rec.report_id:
                report = Report.create_from_session(rec)
                rec.report_id = report.id
            rec._export_to_google_sheet()
            VicidialService(rec.env).sync_with_odoo()

    def _export_to_google_sheet(self):
        self.ensure_one()
        try:
            from odoo.addons.doorway_agents_dashboard.services.google_sheets_service import (
                GoogleSheetsService,
            )

            GoogleSheetsService(self.env).export_call_session(self)
        except Exception as exc:  # noqa: BLE001
            _logger.warning("Export Google Sheet session %s: %s", self.id, exc)

    @api.model
    def sync_from_vicidial(self):
        """Importe les appels récents depuis vicidial_log (si tables existent)."""
        svc = VicidialService(self.env)
        if not svc.is_available():
            return 0
        count = 0
        try:
            rows = svc._query(
                """
                SELECT uniqueid, campaign_id, phone_number, call_date, length_in_sec, status
                FROM vicidial_log
                WHERE call_date >= DATE_SUB(NOW(), INTERVAL 1 DAY)
                ORDER BY call_date DESC
                LIMIT 100
                """
            )
        except Exception:  # noqa: BLE001
            return 0
        for row in rows:
            sid = "vicidial-%s" % row.get("uniqueid")
            if self.search([("twilio_call_sid", "=", sid)], limit=1):
                continue
            start = row.get("call_date")
            length = int(row.get("length_in_sec") or 0)
            end = start + timedelta(seconds=length) if start and length else start
            self.create(
                {
                    "twilio_call_sid": sid,
                    "call_status": "completed",
                    "to_number": row.get("phone_number"),
                    "vicidial_campaign_id": row.get("campaign_id"),
                    "date_start": start,
                    "date_end": end,
                }
            )
            count += 1
        return count

    @api.model
    def _cron_realtime_coaching(self):
        """Cron : coaching Claude pour appels en cours (transcript mis à jour)."""
        sessions = self.search(
            [
                ("call_status", "in", ["in-progress", "ringing"]),
                ("transcript", "!=", False),
            ]
        )
        for session in sessions:
            if (
                session.last_coaching_at
                and session.last_coaching_at
                > fields.Datetime.now() - timedelta(seconds=12)
            ):
                continue
            session.run_realtime_coaching()
