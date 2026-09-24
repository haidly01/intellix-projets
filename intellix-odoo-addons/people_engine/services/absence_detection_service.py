# -*- coding: utf-8 -*-
import datetime
import logging

from odoo import api, fields, models

from odoo.addons.people_engine.services.disciplinary_config import (
    HEURES_JOURNEE_ABSENCE,
    SEUILS_ABSENCES,
    SHIFT_DEBUT_HEURE,
    SHIFT_FIN_HEURE,
    est_jour_ouvrable,
)

_logger = logging.getLogger(__name__)


class PeAbsenceDetectionService(models.AbstractModel):
    _name = "pe.absence.detection.service"
    _description = "Détection automatique des absences"

    @api.model
    def _active_employees(self):
        return self.env["hr.employee"].sudo().search([("active", "=", True)])

    @api.model
    def _has_timesheet_on_day(self, employee_id, day):
        AnalyticLine = self.env["account.analytic.line"].sudo()
        if "employee_id" not in AnalyticLine._fields:
            return False
        return bool(
            AnalyticLine.search_count(
                [
                    ("employee_id", "=", employee_id),
                    ("date", "=", day),
                    ("unit_amount", ">", 0),
                ]
            )
        )

    @api.model
    def _has_session_on_day(self, employee_id, day):
        Session = self.env.get("doorway.vicidial.agent.session")
        if not Session:
            return False
        employee = self.env["hr.employee"].browse(employee_id)
        if not employee.user_id:
            return False
        debut = datetime.datetime.combine(day, datetime.time.min)
        fin = datetime.datetime.combine(day, datetime.time.max)
        domain = [
            ("date_start", "<=", fin),
            "|",
            ("date_end", "=", False),
            ("date_end", ">=", debut),
        ]
        if "employee_id" in Session._fields:
            domain.insert(0, ("employee_id", "=", employee_id))
        else:
            domain.insert(0, ("user_id", "=", employee.user_id.id))
        return bool(Session.sudo().search_count(domain))

    @api.model
    def _has_valid_leave_on_day(self, employee_id, day):
        Leave = self.env.get("hr.leave")
        if not Leave:
            return False
        return bool(
            Leave.sudo().search_count(
                [
                    ("employee_id", "=", employee_id),
                    ("state", "=", "validate"),
                    ("date_from", "<=", day),
                    ("date_to", ">=", day),
                ]
            )
        )

    @api.model
    def has_activity_on_day(self, employee_id, day):
        """True si au moins une source signale une activité ou un congé validé."""
        if self._has_valid_leave_on_day(employee_id, day):
            return True, "conge"
        if self._has_timesheet_on_day(employee_id, day):
            return True, "timesheet"
        if self._has_session_on_day(employee_id, day):
            return True, "session"
        return False, None

    @api.model
    def _has_activity_since_shift_start(self, employee_id, day):
        """Activité depuis le début du shift (9h) le jour J."""
        AnalyticLine = self.env["account.analytic.line"].sudo()
        shift_start = datetime.datetime.combine(day, datetime.time(SHIFT_DEBUT_HEURE, 0))
        if "employee_id" in AnalyticLine._fields:
            if AnalyticLine.search_count(
                [
                    ("employee_id", "=", employee_id),
                    ("date", "=", day),
                    ("unit_amount", ">", 0),
                ]
            ):
                return True
        Session = self.env.get("doorway.vicidial.agent.session")
        if Session:
            employee = self.env["hr.employee"].browse(employee_id)
            if employee.user_id:
                domain = [("date_start", ">=", shift_start)]
                if "employee_id" in Session._fields:
                    domain.append(("employee_id", "=", employee_id))
                else:
                    domain.append(("user_id", "=", employee.user_id.id))
                if Session.sudo().search_count(domain):
                    return True
        return False

    @api.model
    def _create_or_get_absence(self, employee_id, day, source):
        Absence = self.env["pe.absence.detected"].sudo()
        existing = Absence.search(
            [("employee_id", "=", employee_id), ("date_absence", "=", day)],
            limit=1,
        )
        if existing:
            return existing
        return Absence.create(
            {
                "employee_id": employee_id,
                "date_absence": day,
                "heure_detection": fields.Datetime.now(),
                "statut": "detectee",
                "source_detection": source,
            }
        )

    @api.model
    def _alert_supervisor_absence(self, employee, day):
        disc = self.env["pe.disciplinary.service"].sudo()
        disc._create_alert_if_new(
            employee.id,
            "absence",
            "Absence non déclarée — %s" % employee.name,
            "%s absent(e) le %s — aucune activité IntelliX depuis l'ouverture du shift."
            % (employee.name, day.strftime("%d/%m/%Y")),
            niveau="critique",
        )

    @api.model
    def _notify_rh_absence(self, absence):
        body = (
            "<p>Absence injustifiée confirmée : <strong>%s</strong> "
            "le %s (%s h déduites).</p>"
            % (
                absence.employee_id.name,
                absence.date_absence.strftime("%d/%m/%Y"),
                absence.heures_deduites,
            )
        )
        hr_group = self.env.ref("people_engine.group_hr", raise_if_not_found=False)
        partners = hr_group.users.mapped("partner_id").ids if hr_group else []
        if partners:
            absence.message_post(
                body=body,
                partner_ids=partners,
                message_type="notification",
                subtype_xmlid="mail.mt_comment",
            )

    @api.model
    def classifier_injustifiee(self, absence):
        """Classer une absence comme injustifiée et créer incident si besoin."""
        disc = self.env["pe.disciplinary.service"].sudo()
        absence.write(
            {
                "statut": "injustifiee",
                "impact_paie": SEUILS_ABSENCES.get("deduction_paie", True),
                "heures_deduites": HEURES_JOURNEE_ABSENCE,
            }
        )
        if not absence.incident_id:
            incident = disc._create_incident_if_new(
                absence.employee_id.id,
                "absence",
                "Absence injustifiée le %s — détection automatique IntelliX."
                % absence.date_absence.strftime("%d/%m/%Y"),
                gravite="modere",
                heures_concernees=absence.heures_deduites,
            )
            if incident:
                absence.incident_id = incident.id
        self._notify_rh_absence(absence)
        return absence

    @api.model
    def detection_matin(self):
        """Cron 10h — détection provisoire + alerte superviseur."""
        today = fields.Date.today()
        if not est_jour_ouvrable(today, self.env):
            return True
        created = 0
        for employee in self._active_employees():
            active, source = self.has_activity_on_day(employee.id, today)
            if source == "conge":
                self._create_or_get_absence(employee.id, today, "cron_matin").write(
                    {"statut": "conge_valide"}
                )
                continue
            if active:
                continue
            if not self._has_activity_since_shift_start(employee.id, today):
                self._create_or_get_absence(employee.id, today, "cron_matin")
                self._alert_supervisor_absence(employee, today)
                created += 1
        _logger.info("PE absence matin : %s détections", created)
        return True

    @api.model
    def detection_soir(self):
        """Cron 18h — confirmation ou reclassement des absences du jour."""
        today = fields.Date.today()
        if not est_jour_ouvrable(today, self.env):
            return True
        Absence = self.env["pe.absence.detected"].sudo()
        absences = Absence.search(
            [
                ("date_absence", "=", today),
                ("statut", "in", ("detectee",)),
            ]
        )
        for absence in absences:
            active, source = self.has_activity_on_day(
                absence.employee_id.id, today
            )
            if source == "conge":
                absence.write({"statut": "conge_valide", "impact_paie": False})
                continue
            if active:
                absence.write(
                    {
                        "statut": "justifiee",
                        "motif": "Présence partielle détectée après alerte matin",
                        "impact_paie": False,
                    }
                )
                continue
            self.classifier_injustifiee(absence)
        return True
