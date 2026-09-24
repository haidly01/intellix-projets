# -*- coding: utf-8 -*-
import datetime
import logging
import re

from odoo import api, fields, models
from odoo.exceptions import UserError

from odoo.addons.people_engine.services.disciplinary_config import (
    DELAIS_LEGAUX_MAROC,
    INTELLIX_DISCIPLINAIRE_CONFIG,
    SEUILS_KPI,
    SEUILS_LOG_MANQUANT,
    SEUILS_PAUSES,
    SEUILS_SAISIE_CRM,
    get_prescription_alert_days,
    get_prescription_days,
    get_recidive_window_days,
    requires_human_validation,
    requires_immediate_access_cut,
    resolve_sanction_from_matrice,
)

_logger = logging.getLogger(__name__)

LETTER_LEGAL_CODES = {
    "convocation": "MA-MDL-CONV",
    "avertissement_ecrit": "MA-MDL-AVERT",
    "avertissement_verbal": "MA-MDL-AVERT",
    "mise_en_demeure": "MA-MDL-MED",
    "mise_a_pied": "MA-MDL-AVERT",
    "licenciement": "MA-MDL-LIC",
    "solde_tout_compte": "MA-MDL-CERT",
}


class PeDisciplinaryService(models.AbstractModel):
    _name = "pe.disciplinary.service"
    _description = "Service incidents & procédures disciplinaires"

    @api.model
    def suggerer_sanction(self, type_incident, count_30d):
        """Retourne la sanction suggérée selon MATRICE_DECISION."""
        detail = self.suggerer_sanction_detail(type_incident, count_30d)
        return detail.get("sanction_odoo")

    @api.model
    def suggerer_sanction_detail(self, type_incident, count_30d):
        """Retourne le détail complet de la sanction suggérée."""
        occurrence = max(int(count_30d or 1), 1)
        code, sanction_odoo, jours, impact_paie, coaching = resolve_sanction_from_matrice(
            type_incident, occurrence
        )
        return {
            "code_matrice": code,
            "sanction_odoo": sanction_odoo,
            "jours_mise_a_pied": jours,
            "impact_paie": impact_paie,
            "coaching_requis": coaching,
            "validation_humaine_requise": requires_human_validation(sanction_odoo),
            "acces_coupe_immediat": requires_immediate_access_cut(type_incident),
        }

    @api.model
    def count_incidents_30d(self, employee_id, type_incident):
        from odoo.addons.people_engine.services.disciplinary_config import (
            normalize_incident_type,
        )

        window_days = get_recidive_window_days(self.env)
        since = fields.Datetime.now() - datetime.timedelta(days=window_days)
        matrix_key = normalize_incident_type(type_incident)
        types = {matrix_key, type_incident}
        types.discard(None)
        return self.env["pe.disciplinary.incident"].sudo().search_count(
            [
                ("employee_id", "=", employee_id),
                ("type_incident", "in", list(types)),
                ("date_incident", ">=", since),
                ("statut", "not in", ("ignore", "prescrit")),
            ]
        )

    @api.model
    def _user_has_rh_validation(self):
        return self.env.user.has_group("people_engine.group_hr")

    @api.model
    def enforce_human_validation(self, sanction_type, action="appliquer"):
        """Lève UserError si sanction grave sans groupe RH."""
        if requires_human_validation(sanction_type) and not self._user_has_rh_validation():
            raise UserError(
                "La sanction « %s » nécessite une validation RH/Direction "
                "avant de pouvoir %s. Seules les suggestions automatiques "
                "sont créées par la détection — la procédure doit être "
                "validée manuellement par un responsable RH."
                % (sanction_type, action)
            )

    @api.model
    def _get_legal_article(self, letter_type):
        code = LETTER_LEGAL_CODES.get(letter_type)
        if not code:
            return self.env["pe.legal.article"]
        return self.env["pe.legal.article"].sudo().search([("code", "=", code)], limit=1)

    @api.model
    def _personalize_letter_content(self, template_text, procedure, letter_date=None):
        employee = procedure.employee_id
        company = procedure.company_id or self.env.company
        letter_date = letter_date or fields.Date.today()
        profile = self.env["pe.employee.profile"].sudo().search(
            [("employee_id", "=", employee.id)], limit=1
        )
        from odoo.addons.people_engine.services.document_placeholder_service import (
            DocumentPlaceholderService,
        )

        svc = DocumentPlaceholderService(self.env)
        values = svc.build_values(profile or self.env["pe.employee.profile"], letter_date)
        if not profile:
            values = {
                "full_name": employee.name or "",
                "first_name": (employee.name or "").split()[0] if employee.name else "",
                "last_name": " ".join((employee.name or "").split()[1:]),
                "job": employee.job_id.name if employee.job_id else "",
                "company": company.name or "",
                "date_fr": svc.format_fr_date(letter_date),
                "start_date": svc.format_fr_date(employee.date_start),
                "department": employee.department_id.name if employee.department_id else "",
                "email": employee.work_email or "",
            }

        content = template_text or ""
        conv_days = DELAIS_LEGAUX_MAROC["delai_min_convocation_entretien"]
        replacements = {
            r"\[Ville\]": company.city or company.name or "",
            r"\[Date\]": values.get("date_fr", ""),
            r"\[Prénom Nom\]": values.get("full_name", ""),
            r"\[X\]": employee.barcode or str(employee.id),
            r"\[date\]": values.get("date_fr", ""),
            r"\[dates\]": values.get("date_fr", ""),
            r"\[Motif\]": procedure.description_faits or "",
            r"\[description précise du manquement\]": procedure.description_faits or "",
            r"\[Description précise et datée des faits — Art\. 39 §X\]": procedure.description_faits or "",
            r"\[Heure\]": "10:00",
            r"\[Lieu\]": company.name or "Siège social",
            r"\[action attendue\]": "vous conformer à vos obligations professionnelles",
            r"\[X\] jours": "%d jours" % conv_days,
        }
        for pattern, repl in replacements.items():
            content = re.sub(pattern, repl, content, flags=re.IGNORECASE)

        content = svc.render(content, profile, letter_date) if profile else content
        if procedure.date_entretien:
            content += "<p><strong>Date entretien préalable :</strong> %s</p>" % svc.format_fr_date(
                procedure.date_entretien
            )
        if procedure.montant_impact_paie:
            content += "<p><strong>Impact paie estimé :</strong> %.2f MAD</p>" % procedure.montant_impact_paie
        return content

    @api.model
    def generate_letter(self, procedure, letter_type):
        procedure.ensure_one()
        article = self._get_legal_article(letter_type)
        template = article.content if article else "<p>%s</p>" % (procedure.description_faits or "")
        content = self._personalize_letter_content(template, procedure)
        preview = self._preview_payroll_impact(procedure)
        letter = self.env["pe.disciplinary.letter"].create(
            {
                "procedure_id": procedure.id,
                "type_lettre": letter_type,
                "legal_article_id": article.id if article else False,
                "content_html": content,
                "state": "generated",
                "impact_paie_preview": preview,
            }
        )
        if article and not procedure.legal_article_id:
            procedure.legal_article_id = article.id
        return letter

    @api.model
    def _preview_payroll_impact(self, procedure):
        employee = procedure.employee_id
        payroll = self.env["pe.payroll.service"].sudo()
        contract = payroll.get_active_contract(employee.id)
        salaire = contract.salaire_base if contract else 0.0
        hourly = salaire / 191.33 if salaire else 0.0
        if procedure.type_sanction == "mise_a_pied" and procedure.jours_mise_a_pied:
            return round((salaire / 26.0) * procedure.jours_mise_a_pied, 2)
        if procedure.heures_deduction:
            return round(hourly * procedure.heures_deduction, 2)
        if procedure.incident_id and procedure.incident_id.heures_concernees:
            return round(hourly * procedure.incident_id.heures_concernees, 2)
        return 0.0

    @api.model
    def appliquer_impact_paie(self, procedure):
        """Applique les déductions disciplinaires sur le bulletin courant."""
        procedure.ensure_one()
        self.enforce_human_validation(procedure.type_sanction, "appliquer l'impact paie")
        payroll_svc = self.env["pe.payroll.service"].sudo()
        period = payroll_svc.get_payroll_period()
        Bulletin = self.env["pe.payroll.bulletin"].sudo()
        bulletin = Bulletin.search(
            [
                ("employee_id", "=", procedure.employee_id.id),
                ("period_start", "=", period["period_start"]),
                ("period_end", "=", period["period_end"]),
            ],
            limit=1,
        )
        if not bulletin:
            bulletin = Bulletin.create(
                {
                    "employee_id": procedure.employee_id.id,
                    "period_start": period["period_start"],
                    "period_end": period["period_end"],
                    "payment_date": period["payment_date"],
                }
            )

        contract = payroll_svc.get_active_contract(procedure.employee_id.id, period["period_end"])
        salaire = contract.salaire_base if contract else bulletin.salaire_base
        hourly = salaire / 191.33 if salaire else 0.0
        montant = 0.0
        heures = 0.0
        jours = 0.0
        type_ded = "autre"
        label = procedure.name

        if procedure.type_sanction == "mise_a_pied":
            jours = min(
                procedure.jours_mise_a_pied or 1,
                DELAIS_LEGAUX_MAROC["duree_max_mise_a_pied_jours"],
            )
            montant = round((salaire / 26.0) * jours, 2)
            type_ded = "mise_a_pied"
            label = "Mise à pied %s j" % jours
        elif procedure.type_sanction == "licenciement_faute_grave":
            montant = 0.0
            type_ded = "licenciement"
            label = "Licenciement faute grave — sans indemnité"
        else:
            heures = procedure.heures_deduction or (
                procedure.incident_id.heures_concernees if procedure.incident_id else 0.0
            )
            if heures:
                montant = round(hourly * heures, 2)
                type_ded = "log_manquant"
                label = "Heures non reconnues (%.2f h)" % heures

        self.env["pe.payroll.bulletin.deduction.line"].create(
            {
                "bulletin_id": bulletin.id,
                "procedure_id": procedure.id,
                "incident_id": procedure.incident_id.id if procedure.incident_id else False,
                "label": label,
                "type_deduction": type_ded,
                "heures": heures,
                "jours": jours,
                "montant": montant,
                "devise": bulletin.devise or "MAD",
            }
        )
        bulletin.action_calculate()
        procedure.write({"montant_impact_paie": montant, "paie_impact_id": bulletin.id})
        return bulletin

    @api.model
    def _create_alert_if_new(self, employee_id, type_alerte, name, message, niveau="warning"):
        Alert = self.env["pe.supervisor.alert"].sudo()
        existing = Alert.search(
            [
                ("employee_id", "=", employee_id),
                ("type_alerte", "=", type_alerte),
                ("state", "=", "active"),
            ],
            limit=1,
        )
        if existing:
            existing.write({"message": message, "niveau": niveau})
            return existing
        supervisor = self.env["hr.employee"].browse(employee_id).parent_id
        alert = Alert.create(
            {
                "employee_id": employee_id,
                "superviseur_id": supervisor.id if supervisor else False,
                "type_alerte": type_alerte,
                "name": name,
                "message": message,
                "niveau": niveau,
                "auto_generee": True,
            }
        )
        self._notify_disciplinary(alert, employee_id)
        return alert

    @api.model
    def _notify_disciplinary(self, alert, employee_id):
        """Notifications superviseur / RH selon INTELLIX_DISCIPLINAIRE_CONFIG."""
        cfg = INTELLIX_DISCIPLINAIRE_CONFIG
        if not cfg.get("notifier_superviseur") and not cfg.get("notifier_rh"):
            return
        employee = self.env["hr.employee"].browse(employee_id)
        body = "<p>%s</p><p>%s</p>" % (alert.name, alert.message)
        partners = []
        if cfg.get("notifier_superviseur") and alert.superviseur_id and alert.superviseur_id.user_id:
            partners.append(alert.superviseur_id.user_id.partner_id.id)
        if cfg.get("notifier_rh"):
            hr_group = self.env.ref("people_engine.group_hr", raise_if_not_found=False)
            if hr_group:
                partners.extend(hr_group.users.mapped("partner_id").ids)
        if cfg.get("notifier_employe_email") and employee.user_id:
            partners.append(employee.user_id.partner_id.id)
        partners = list(set(p for p in partners if p))
        if partners:
            alert.message_post(body=body, partner_ids=partners, message_type="notification")

    @api.model
    def _create_incident_if_new(self, employee_id, type_incident, description, **kwargs):
        """Crée un incident auto — jamais de procédure ni sanction appliquée."""
        Incident = self.env["pe.disciplinary.incident"].sudo()
        window_hours = 24
        recent = Incident.search_count(
            [
                ("employee_id", "=", employee_id),
                ("type_incident", "=", type_incident),
                ("date_incident", ">=", fields.Datetime.now() - datetime.timedelta(hours=window_hours)),
                ("source", "=", "cron"),
            ]
        )
        if recent:
            return False
        detail = self.suggerer_sanction_detail(
            type_incident, self.count_incidents_30d(employee_id, type_incident) + 1
        )
        vals = {
            "employee_id": employee_id,
            "type_incident": type_incident,
            "gravite": kwargs.pop("gravite", "modere"),
            "description": description,
            "source": "cron",
            "impact_paie": detail.get("impact_paie", False),
        }
        vals.update(kwargs)
        return Incident.create(vals)

    @api.model
    def _employee_has_active_shift(self, employee):
        Session = self.env.get("doorway.vicidial.agent.session")
        if not Session or not employee.user_id:
            return False
        return bool(
            Session.sudo().search_count(
                [
                    ("employee_id", "=", employee.id),
                    ("state", "=", "active"),
                ]
            )
        )

    @api.model
    def _hours_since_last_timesheet(self, employee_id):
        AnalyticLine = self.env["account.analytic.line"].sudo()
        if "employee_id" not in AnalyticLine._fields:
            return None
        last = AnalyticLine.search(
            [("employee_id", "=", employee_id)],
            order="date desc, id desc",
            limit=1,
        )
        if not last or not last.date:
            return None
        last_dt = fields.Datetime.to_datetime(last.date)
        if not last_dt:
            return None
        return (fields.Datetime.now() - last_dt).total_seconds() / 3600.0

    @api.model
    def _detect_missing_logs(self):
        """Alerte 4h (warning) / 24h (critique) + incident avec tolérance 60 min."""
        AnalyticLine = self.env["account.analytic.line"].sudo()
        if "employee_id" not in AnalyticLine._fields:
            return
        seuils = SEUILS_LOG_MANQUANT
        warning_h = seuils["alerte_warning"]
        critique_h = seuils["alerte_critique"]
        grace_h = seuils["grace_period_minutes"] / 60.0
        employees = self.env["hr.employee"].sudo().search([("active", "=", True)])
        for emp in employees:
            if not emp.user_id:
                continue
            hours_gap = self._hours_since_last_timesheet(emp.id)
            if hours_gap is None:
                continue
            on_shift = self._employee_has_active_shift(emp)
            if hours_gap >= warning_h and on_shift:
                self._create_alert_if_new(
                    emp.id,
                    "log_manquant_4h",
                    "Log manquant 4h+ — %s" % emp.name,
                    "Aucune saisie timesheet depuis %.1f h en cours de shift." % hours_gap,
                    "warning",
                )
            if hours_gap >= critique_h:
                yesterday = fields.Date.today() - datetime.timedelta(days=1)
                session_hours, _ = self.env["pe.payroll.service"].sudo().get_hours_from_sessions(
                    emp.id, yesterday, yesterday
                )
                if session_hours > 0:
                    self._create_alert_if_new(
                        emp.id,
                        "log_manquant_24h",
                        "Log manquant 24h+ — %s" % emp.name,
                        "Aucune saisie timesheet depuis 24h alors que des sessions "
                        "VICIdial ont été détectées.",
                        "critique",
                    )
                    billable_hours = max(session_hours - grace_h, 0.0)
                    self._create_incident_if_new(
                        emp.id,
                        "log_manquant",
                        "Log timesheet manquant depuis 24h (auto-détection, tolérance %d min)."
                        % seuils["grace_period_minutes"],
                        gravite="modere",
                        heures_concernees=billable_hours,
                        impact_paie=seuils["deduction_paie"],
                    )

    @api.model
    def _detect_pause_exceeded(self):
        Pause = self.env.get("pe.session.pause")
        if not Pause:
            return
        now = fields.Datetime.now()
        for pause in Pause.sudo().search([("state", "=", "active")]):
            cfg = SEUILS_PAUSES.get(pause.pause_type, SEUILS_PAUSES["personnelle"])
            duration_min = int((now - pause.date_start).total_seconds()) // 60
            alert_min = cfg.get("duree_max_minutes", 15)
            critique_min = cfg.get("duree_critique_minutes", 20)
            emp = pause.employee_id
            if duration_min >= alert_min:
                niveau = "critique" if duration_min >= critique_min else "warning"
                self._create_alert_if_new(
                    emp.id,
                    "pause_depassee",
                    "Pause dépassée — %s" % emp.name,
                    "Pause %s en cours depuis %d min (alerte %d min, critique %d min)."
                    % (pause.pause_type, duration_min, alert_min, critique_min),
                    niveau,
                )
            if duration_min >= critique_min:
                self._create_incident_if_new(
                    emp.id,
                    "pause_depassee",
                    "Pause %s dépassée (%d min, seuil critique %d min)."
                    % (pause.pause_type, duration_min, critique_min),
                    gravite="modere",
                    impact_paie=cfg.get("deductible_paie", True),
                )

    @api.model
    def _detect_pause_quota(self):
        Pause = self.env.get("pe.session.pause")
        if not Pause:
            return
        today = fields.Date.today()
        start_week = today - datetime.timedelta(days=today.weekday())
        start_month = today.replace(day=1)
        employees = self.env["hr.employee"].sudo().search([("active", "=", True)])
        for emp in employees:
            pauses_week = Pause.sudo().search(
                [
                    ("employee_id", "=", emp.id),
                    ("date_start", ">=", datetime.datetime.combine(start_week, datetime.time.min)),
                ]
            )
            quota_exceed = 0
            for pause_type, cfg in SEUILS_PAUSES.items():
                if pause_type == "escalade_quota_pauses":
                    continue
                max_shift = cfg.get("quota_max_par_shift", 99)
                today_pauses = pauses_week.filtered(
                    lambda p, pt=pause_type: p.pause_type == pt
                    and p.date_start
                    and fields.Datetime.to_datetime(p.date_start).date() == today
                )
                if len(today_pauses) > max_shift:
                    quota_exceed += len(today_pauses) - max_shift
            if quota_exceed:
                self._create_alert_if_new(
                    emp.id,
                    "pause_quota",
                    "Quota pauses dépassé — %s" % emp.name,
                    "%d dépassement(s) de quota pause aujourd'hui." % quota_exceed,
                    "warning",
                )
            week_exceed = self._count_pause_quota_exceed(emp.id, start_week, today)
            month_exceed = self._count_pause_quota_exceed(emp.id, start_month, today)
            escalade = SEUILS_PAUSES["escalade_quota_pauses"]
            for threshold, sorted_period in [(10, month_exceed), (6, week_exceed), (3, week_exceed), (1, week_exceed)]:
                if sorted_period >= threshold:
                    sanction_key = escalade.get(threshold)
                    if sanction_key == "alerte_superviseur":
                        break
                    if sanction_key in ("avertissement_verbal", "avertissement_ecrit", "mise_a_pied"):
                        count = self.count_incidents_30d(emp.id, "pause_quota") + 1
                        detail = self.suggerer_sanction_detail("pause_quota", count)
                        self._create_incident_if_new(
                            emp.id,
                            "pause_quota",
                            "Quota pauses : %d dépassements/%s (seuil %d)."
                            % (sorted_period, "mois" if threshold == 10 else "semaine", threshold),
                            gravite="modere",
                            impact_paie=True,
                        )
                    break

    @api.model
    def _count_pause_quota_exceed(self, employee_id, date_start, date_end):
        Pause = self.env["pe.session.pause"].sudo()
        pauses = Pause.search(
            [
                ("employee_id", "=", employee_id),
                ("date_start", ">=", datetime.datetime.combine(date_start, datetime.time.min)),
                ("date_start", "<=", datetime.datetime.combine(date_end, datetime.time.max)),
            ]
        )
        exceed = 0
        by_day_type = {}
        for pause in pauses:
            if pause.pause_type == "dejeuner":
                continue
            day = fields.Datetime.to_datetime(pause.date_start).date() if pause.date_start else date_start
            key = (day, pause.pause_type)
            by_day_type[key] = by_day_type.get(key, 0) + 1
        for (day, pause_type), count in by_day_type.items():
            cfg = SEUILS_PAUSES.get(pause_type, {})
            max_q = cfg.get("quota_max_par_shift", 99)
            if count > max_q:
                exceed += count - max_q
        return exceed

    @api.model
    def _detect_inactive_sessions(self):
        Session = self.env.get("doorway.vicidial.agent.session")
        if not Session:
            return
        threshold = fields.Datetime.now() - datetime.timedelta(hours=2)
        for session in Session.sudo().search([("state", "=", "active")]):
            if session.date_start and session.date_start < threshold:
                emp = session.employee_id
                if not emp:
                    continue
                self._create_alert_if_new(
                    emp.id,
                    "session_inactive",
                    "Session inactive — %s" % emp.name,
                    "Session VICIdial active depuis plus de 2h sans activité détectée.",
                    "warning",
                )

    @api.model
    def _call_has_crm_saisie(self, log):
        if log.lead_id:
            lead = log.lead_id
            if lead.description or getattr(lead, "qualification_statut", None) not in (
                False,
                None,
                "non_fait",
            ):
                return True
        note = log.transcript or log.ai_feedback or ""
        return bool(note and note.strip())

    @api.model
    def _detect_missing_crm_notes(self):
        CallLog = self.env.get("pe.call.log")
        if not CallLog:
            return
        seuils = SEUILS_SAISIE_CRM
        now = fields.Datetime.now()
        alert_delta = datetime.timedelta(minutes=seuils["alerte_superviseur_minutes"])
        incident_delta = datetime.timedelta(minutes=seuils["incident_auto_minutes"])
        saisie_delta = datetime.timedelta(minutes=seuils["delai_saisie_minutes"])
        logs = CallLog.sudo().search(
            [
                ("date_call", ">=", now - datetime.timedelta(days=1)),
                ("date_call", "<=", now),
            ]
        )
        for log in logs:
            if self._call_has_crm_saisie(log):
                continue
            emp = log.employee_id
            if not emp:
                continue
            elapsed = now - log.date_call
            if elapsed >= incident_delta:
                self._create_incident_if_new(
                    emp.id,
                    "crm_note_manquante",
                    "Appel du %s sans saisie CRM après %d min."
                    % (log.date_call, seuils["incident_auto_minutes"]),
                    gravite="grave",
                    impact_paie=True,
                )
            elif elapsed >= alert_delta:
                self._create_alert_if_new(
                    emp.id,
                    "crm_note_manquante",
                    "Saisie CRM en retard — %s" % emp.name,
                    "Appel du %s : saisie CRM attendue sous %d min, retard %d min."
                    % (
                        log.date_call,
                        seuils["delai_saisie_minutes"],
                        int(elapsed.total_seconds() // 60),
                    ),
                    "warning",
                )
            elif elapsed >= saisie_delta:
                self._create_alert_if_new(
                    emp.id,
                    "crm_saisie_retard",
                    "Saisie CRM — %s" % emp.name,
                    "Appel du %s : délai de saisie (%d min) dépassé."
                    % (log.date_call, seuils["delai_saisie_minutes"]),
                    "info",
                )

        self._detect_crm_taux_saisie()

    @api.model
    def _detect_crm_taux_saisie(self):
        CallLog = self.env.get("pe.call.log")
        if not CallLog:
            return
        seuils = SEUILS_SAISIE_CRM
        week_start = fields.Date.today() - datetime.timedelta(days=7)
        start_dt = datetime.datetime.combine(week_start, datetime.time.min)
        employees = self.env["hr.employee"].sudo().search([("active", "=", True)])
        for emp in employees:
            logs = CallLog.sudo().search(
                [
                    ("employee_id", "=", emp.id),
                    ("date_call", ">=", start_dt),
                ]
            )
            if len(logs) < 5:
                continue
            saisis = sum(1 for log in logs if self._call_has_crm_saisie(log))
            taux = saisis / len(logs) * 100.0
            if taux < seuils["taux_saisie_critique"]:
                self._create_alert_if_new(
                    emp.id,
                    "crm_taux_bas",
                    "Taux saisie CRM critique — %s" % emp.name,
                    "Taux saisie CRM %.0f%% sur 7 j (seuil critique %d%%)."
                    % (taux, seuils["taux_saisie_critique"]),
                    "critique",
                )
                self._create_incident_if_new(
                    emp.id,
                    "crm_note_manquante",
                    "Taux saisie CRM %.0f%% < seuil critique %d%% (7 jours)."
                    % (taux, seuils["taux_saisie_critique"]),
                    gravite="grave",
                )
            elif taux < seuils["taux_saisie_minimum"]:
                self._create_alert_if_new(
                    emp.id,
                    "crm_taux_bas",
                    "Taux saisie CRM bas — %s" % emp.name,
                    "Taux saisie CRM %.0f%% sur 7 j (minimum %d%%)."
                    % (taux, seuils["taux_saisie_minimum"]),
                    "warning",
                )

    @api.model
    def _detect_kpi_sous_seuil(self):
        """Détection KPI call center — challenge + métriques directes."""
        CallLog = self.env.get("pe.call.log")
        Result = self.env.get("pe.payroll.challenge.result")
        Challenge = self.env.get("pe.payroll.challenge")
        kpi_cfg = SEUILS_KPI.get("call_center", {})
        week_start = fields.Date.today() - datetime.timedelta(days=7)
        start_dt = datetime.datetime.combine(week_start, datetime.time.min)

        if CallLog:
            employees = self.env["hr.employee"].sudo().search([("active", "=", True)])
            for emp in employees:
                logs = CallLog.sudo().search(
                    [
                        ("employee_id", "=", emp.id),
                        ("date_call", ">=", start_dt),
                    ]
                )
                if len(logs) < 10:
                    continue
                contacts = len(logs)
                qualified = logs.filtered(
                    lambda l: l.outcome in ("demo_bookee", "vendu", "interesse")
                )
                taux_qual = len(qualified) / contacts * 100.0 if contacts else 0
                total_sec = sum(logs.mapped("duration") or [0])
                hours = max(total_sec / 3600.0, 0.01)
                appels_heure = contacts / hours
                min_qual = kpi_cfg.get("taux_qualification", {}).get("minimum", 15)
                min_aph = kpi_cfg.get("appels_par_heure", {}).get("minimum", 8)
                critique_qual = kpi_cfg.get("taux_qualification", {}).get("critique", 8)
                critique_aph = kpi_cfg.get("appels_par_heure", {}).get("critique", 5)
                sous_seuil = taux_qual < min_qual or appels_heure < min_aph
                critique = taux_qual < critique_qual or appels_heure < critique_aph
                if sous_seuil:
                    self._create_alert_if_new(
                        emp.id,
                        "kpi_sous_seuil",
                        "KPI sous seuil — %s" % emp.name,
                        "Semaine : qualification %.0f%% (min %d%%), "
                        "%.1f appels/h (min %d)."
                        % (taux_qual, min_qual, appels_heure, min_aph),
                        "critique" if critique else "warning",
                    )
                    if critique:
                        weeks = self._count_consecutive_kpi_weeks(emp.id)
                        escalade = SEUILS_KPI["escalade_kpi"]
                        sanction_hint = escalade.get(min(weeks, 4), "alerte_superviseur")
                        self._create_incident_if_new(
                            emp.id,
                            "kpi_sous_seuil",
                            "KPI critique semaine %d : qualification %.0f%%, %.1f appels/h. "
                            "Escalade suggérée : %s."
                            % (weeks, taux_qual, appels_heure, sanction_hint),
                            gravite="grave",
                            impact_paie=False,
                        )

        if Result and Challenge:
            active = Challenge.sudo().search([("statut", "=", "active")])
            min_pct = kpi_cfg.get("taux_qualification", {}).get("minimum", 15)
            for challenge in active:
                for result in challenge.resultat_ids:
                    if result.pourcentage >= min_pct:
                        continue
                    emp = result.employee_id
                    self._create_alert_if_new(
                        emp.id,
                        "kpi_sous_seuil",
                        "KPI challenge sous seuil — %s" % emp.name,
                        "Challenge « %s » : %.0f%% de l'objectif (seuil %d%%)."
                        % (challenge.name, result.pourcentage, min_pct),
                        "warning",
                    )

    @api.model
    def _count_consecutive_kpi_weeks(self, employee_id):
        """Compte les semaines consécutives avec incident/alerte KPI."""
        Alert = self.env["pe.supervisor.alert"].sudo()
        since = fields.Date.today() - datetime.timedelta(weeks=8)
        alerts = Alert.search(
            [
                ("employee_id", "=", employee_id),
                ("type_alerte", "=", "kpi_sous_seuil"),
                ("create_date", ">=", datetime.datetime.combine(since, datetime.time.min)),
            ],
            order="create_date desc",
        )
        if not alerts:
            return 1
        weeks = 0
        today = fields.Date.today()
        for w in range(8):
            week_end = today - datetime.timedelta(weeks=w)
            week_start = week_end - datetime.timedelta(days=7)
            if alerts.filtered(
                lambda a, ws=week_start, we=week_end: a.create_date
                and fields.Datetime.to_datetime(a.create_date).date() >= ws
                and fields.Datetime.to_datetime(a.create_date).date() <= we
            ):
                weeks += 1
            else:
                break
        return max(weeks, 1)

    @api.model
    def get_crm_facture_deduction_pct(self, employee_id, period_start, period_end):
        """Retourne % déduction facture freelance selon taux saisie CRM (optionnel)."""
        seuils = SEUILS_SAISIE_CRM
        if not seuils.get("deduction_facture_freelance"):
            return 0.0
        CallLog = self.env.get("pe.call.log")
        if not CallLog:
            return 0.0
        start_dt = datetime.datetime.combine(period_start, datetime.time.min)
        end_dt = datetime.datetime.combine(period_end, datetime.time.max)
        logs = CallLog.sudo().search(
            [
                ("employee_id", "=", employee_id),
                ("date_call", ">=", start_dt),
                ("date_call", "<=", end_dt),
            ]
        )
        if len(logs) < 5:
            return 0.0
        saisis = sum(1 for log in logs if self._call_has_crm_saisie(log))
        taux = saisis / len(logs) * 100.0
        if taux < seuils["taux_saisie_critique"]:
            return seuils["deduction_facture_critique"]
        if taux < seuils["taux_saisie_minimum"]:
            return seuils["deduction_facture_pc"]
        return 0.0

    @api.model
    def _detect_prescription_alert(self):
        """Alerte à J+20 (10 jours restants avant prescription 30j)."""
        alert_days = get_prescription_alert_days(self.env)
        prescription_days = get_prescription_days(self.env)
        today = fields.Date.today()
        window_start = today - datetime.timedelta(days=alert_days)
        window_end = today - datetime.timedelta(days=alert_days - 1)
        Incident = self.env["pe.disciplinary.incident"].sudo()
        incidents = Incident.search(
            [
                ("statut", "in", ("nouveau", "en_cours")),
                ("procedure_id", "=", False),
            ]
        )
        for inc in incidents:
            inc_date = inc.date_incident.date() if inc.date_incident else today
            if window_start <= inc_date <= window_end:
                jours_restants = prescription_days - alert_days
                self._create_alert_if_new(
                    inc.employee_id.id,
                    "prescription_20j",
                    "Prescription J-%d — %s" % (alert_days, inc.employee_id.name),
                    "Incident %s ouvert depuis %d jours — prescription dans %d jours "
                    "(Art. 58 Code du Travail Maroc)."
                    % (inc.name, alert_days, jours_restants),
                    "critique",
                )

    @api.model
    def run_auto_detection(self):
        _logger.info("PE Disciplinary: début auto-détection (config %s)", "2026-06-maroc")
        try:
            self._detect_missing_logs()
            self._detect_pause_exceeded()
            self._detect_pause_quota()
            self._detect_inactive_sessions()
            self._detect_missing_crm_notes()
            self._detect_kpi_sous_seuil()
            self._detect_prescription_alert()
            self.env["pe.disciplinary.incident"].sudo().cron_check_prescription()
        except Exception:
            _logger.exception("PE Disciplinary auto-détection error")
        _logger.info("PE Disciplinary: fin auto-détection")
        return True
