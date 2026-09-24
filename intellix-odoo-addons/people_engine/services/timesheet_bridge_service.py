# -*- coding: utf-8 -*-
import datetime
import logging

from odoo import api, fields, models

_logger = logging.getLogger(__name__)


class PeTimesheetBridgeService(models.AbstractModel):
    _name = "pe.timesheet.bridge.service"
    _description = "Pont sessions VICIdial → account.analytic.line"

    @api.model
    def _icp_int(self, key, default=0):
        return int(
            self.env["ir.config_parameter"].sudo().get_param(key, str(default)) or default
        )

    @api.model
    def get_default_project(self):
        project_id = self._icp_int("people_engine.payroll_project_id", 0)
        if project_id:
            project = self.env["project.project"].sudo().browse(project_id)
            if project.exists():
                return project
        return self.env["project.project"].sudo().search(
            [("name", "ilike", "Interne")], limit=1
        )

    @api.model
    def log_session_to_timesheet(self, session):
        """Crée une ligne analytic pour une session VICIdial terminée."""
        if not session.employee_id or not session.duree_travail_secondes:
            return False
        AnalyticLine = self.env["account.analytic.line"].sudo()
        if "employee_id" not in AnalyticLine._fields:
            return False
        ref = "vicidial-session-%s" % session.id
        existing = AnalyticLine.search([("ref", "=", ref)], limit=1)
        if existing:
            return existing

        project = self.get_default_project()
        if not project:
            _logger.warning("PE timesheet bridge: aucun projet configuré")
            return False

        hours = round(session.duree_travail_secondes / 3600.0, 2)
        session_date = (
            fields.Datetime.to_datetime(session.date_end).date()
            if session.date_end
            else fields.Date.today()
        )
        vals = {
            "name": "Session call center — %s" % (session.campaign_id.name or "VICIdial"),
            "employee_id": session.employee_id.id,
            "user_id": session.user_id.id,
            "project_id": project.id,
            "unit_amount": hours,
            "date": session_date,
            "ref": ref,
            "company_id": session.employee_id.company_id.id
            or self.env.company.id,
        }
        if project.account_id:
            vals["account_id"] = project.account_id.id
        return AnalyticLine.create(vals)

    @api.model
    def sync_ended_sessions(self, days_back=2):
        """Cron : journalise les sessions terminées récentes."""
        Session = self.env.get("doorway.vicidial.agent.session")
        if not Session:
            return True
        since = fields.Datetime.now() - datetime.timedelta(days=days_back)
        sessions = Session.sudo().search(
            [
                ("state", "=", "ended"),
                ("date_end", ">=", since),
                ("duree_travail_secondes", ">", 0),
            ]
        )
        for session in sessions:
            try:
                self.log_session_to_timesheet(session)
            except Exception as exc:  # noqa: BLE001
                _logger.warning(
                    "Timesheet bridge session %s: %s", session.id, exc
                )
        return True
