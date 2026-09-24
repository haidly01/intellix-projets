# -*- coding: utf-8 -*-
"""Alertes gestionnaire — suggestions uniquement (human-in-the-loop)."""
import logging

from odoo import _

_logger = logging.getLogger(__name__)


class PeopleEngineAlertService:
    def __init__(self, env):
        self.env = env

    def send_weekly_digest(self):
        """Notifie les gestionnaires des alertes actives sur leur équipe."""
        Profile = self.env["pe.employee.profile"]
        profiles = Profile.search([("pe_status", "in", ["active", "monitoring", "coaching"])])
        managers = {}
        for profile in profiles:
            if profile.score_global < 60 or profile.pe_status == "monitoring":
                employee = profile.employee_id
                manager = employee.parent_id
                if not manager or not manager.user_id:
                    continue
                managers.setdefault(manager.user_id.id, []).append(profile)
        for user_id, team_profiles in managers.items():
            user = self.env["res.users"].browse(user_id)
            if not user.partner_id:
                continue
            lines = [
                _("People Engine — alertes hebdomadaires (%s employé(s)):") % len(team_profiles)
            ]
            for p in team_profiles:
                lines.append(
                    f"• {p.employee_id.name}: {p.score_global:.0f}/100 ({p.score_trend})"
                )
            body = "\n".join(lines)
            try:
                user.partner_id.message_post(
                    body=body,
                    message_type="comment",
                    subtype_xmlid="mail.mt_note",
                )
            except Exception as exc:  # noqa: BLE001
                _logger.warning("People Engine weekly alert failed for %s: %s", user.login, exc)

    def notify_manager_alerts(self, profile, alerts):
        """Poste une note interne au gestionnaire — pas d'action automatique."""
        if not alerts:
            return
        manager = profile.employee_id.parent_id
        if not manager or not manager.user_id:
            return
        body = _("Alertes People Engine pour %s:\n") % profile.employee_id.name
        body += "\n".join(f"• [{a['level']}] {a['message']}" for a in alerts)
        manager.user_id.partner_id.message_post(
            body=body,
            message_type="comment",
            subtype_xmlid="mail.mt_note",
        )
