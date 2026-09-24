# -*- coding: utf-8 -*-
"""
Service de détection et envoi des félicitations RH.

V1 : cron Odoo quotidien (voir data/pe_celebration_cron.xml).
V2 (optionnel) : remplacer ou compléter par un workflow n8n quotidien qui appelle
  env['pe.celebration.service'].sudo().trigger_celebration(...) via XML-RPC/JSON-RPC
  pour chaque match détecté côté n8n — évite la duplication en conservant pe.celebration.log.
"""
import logging
from datetime import date

from odoo import _, api, fields, models

from odoo.addons.people_engine.services.document_placeholder_service import (
    DocumentPlaceholderService,
)

_logger = logging.getLogger(__name__)

ANNIVERSARY_TYPE_BY_YEARS = {
    1: "anniversary_1y",
    3: "anniversary_3y",
    5: "anniversary_5y",
}


class PeCelebrationService(models.AbstractModel):
    _name = "pe.celebration.service"
    _description = "Détection et envoi des félicitations RH"

    @api.model
    def _config_param(self, key, default=""):
        return (
            self.env["ir.config_parameter"]
            .sudo()
            .get_param(key, default)
        )

    @api.model
    def _config_bool(self, key, default=True):
        value = self._config_param(key, "True" if default else "False")
        return str(value).lower() in ("1", "true", "yes", "on")

    @api.model
    def _is_occasion_enabled(self, occasion_type):
        key = "people_engine.celebration.enabled.%s" % occasion_type
        return self._config_bool(key, default=True)

    @api.model
    def _exclude_honoree_from_email(self):
        return self._config_bool(
            "people_engine.celebration.exclude_honoree_email",
            default=True,
        )

    @api.model
    def _get_profile(self, employee):
        return self.env["pe.employee.profile"].sudo().search(
            [("employee_id", "=", employee.id)],
            limit=1,
        )

    @api.model
    def _get_joining_date(self, employee):
        profile = self._get_profile(employee)
        if profile and profile.active_contract_id and profile.active_contract_id.date_start:
            return profile.active_contract_id.date_start
        if profile:
            contract = self.env["pe.employment.contract"].sudo().search(
                [
                    ("profile_id", "=", profile.id),
                    ("statut", "=", "active"),
                ],
                order="date_start asc",
                limit=1,
            )
            if contract and contract.date_start:
                return contract.date_start
        return employee.date_start or getattr(employee, "contract_date_start", False)

    @api.model
    def _employee_lang(self, employee):
        user = employee.user_id
        if user and user.lang:
            return user.lang
        return "fr_FR"

    @api.model
    def _active_employees(self):
        Employee = self.env["hr.employee"].sudo()
        employees = Employee.search([("active", "=", True)])
        return employees.filtered(
            lambda e: not e.celebration_opt_out
            and (
                not self._get_profile(e)
                or self._get_profile(e).pe_status
                in ("active", "monitoring", "coaching")
            )
        )

    @api.model
    def _years_of_service(self, joining_date, today):
        if not joining_date:
            return 0
        years = today.year - joining_date.year
        if (today.month, today.day) < (joining_date.month, joining_date.day):
            years -= 1
        return max(years, 0)

    @api.model
    def _detect_matches(self, employee, today=None):
        today = today or fields.Date.context_today(self)
        matches = []

        if employee.birthday and (
            employee.birthday.month == today.month
            and employee.birthday.day == today.day
        ):
            matches.append(
                {
                    "occasion_type": "birthday",
                    "occasion_date": today,
                    "detail": "",
                    "anniversary_years": 0,
                }
            )

        joining_date = self._get_joining_date(employee)
        if joining_date and joining_date.month == today.month and joining_date.day == today.day:
            years = self._years_of_service(joining_date, today)
            if years >= 10:
                matches.append(
                    {
                        "occasion_type": "anniversary_10y",
                        "occasion_date": today,
                        "detail": "",
                        "anniversary_years": years,
                    }
                )
            elif years in ANNIVERSARY_TYPE_BY_YEARS:
                matches.append(
                    {
                        "occasion_type": ANNIVERSARY_TYPE_BY_YEARS[years],
                        "occasion_date": today,
                        "detail": "",
                        "anniversary_years": years,
                    }
                )
            elif years > 0:
                other_template = self.env["pe.celebration.template"].sudo().search(
                    [
                        ("occasion_type", "=", "anniversary_other"),
                        ("anniversary_years", "=", years),
                        ("active", "=", True),
                    ],
                    limit=1,
                )
                if other_template:
                    matches.append(
                        {
                            "occasion_type": "anniversary_other",
                            "occasion_date": today,
                            "detail": "",
                            "anniversary_years": years,
                        }
                    )

        milestone = employee.last_performance_milestone
        if milestone:
            if isinstance(milestone, str):
                milestone = fields.Date.to_date(milestone)
            if milestone == today:
                matches.append(
                    {
                        "occasion_type": "performance",
                        "occasion_date": today,
                        "detail": employee.last_performance_detail or "",
                        "anniversary_years": 0,
                    }
                )

        if employee.last_promotion_date == today:
            matches.append(
                {
                    "occasion_type": "promotion",
                    "occasion_date": today,
                    "detail": "",
                    "anniversary_years": 0,
                }
            )

        return matches

    @api.model
    def _already_sent(self, employee, occasion_type, occasion_date):
        if occasion_type == "praise":
            return False
        Log = self.env["pe.celebration.log"].sudo()
        return bool(
            Log.search_count(
                [
                    ("employee_id", "=", employee.id),
                    ("occasion_type", "=", occasion_type),
                    ("occasion_year", "=", occasion_date.year),
                ]
            )
        )

    @api.model
    def _get_template(self, occasion_type, lang, anniversary_years=0):
        Template = self.env["pe.celebration.template"].sudo()
        domain = [
            ("occasion_type", "=", occasion_type),
            ("active", "=", True),
            ("lang", "=", lang),
        ]
        if occasion_type == "anniversary_other" and anniversary_years:
            domain.append(("anniversary_years", "=", anniversary_years))
        template = Template.search(domain, limit=1)
        if not template and lang != "fr_FR":
            domain = [d for d in domain if d[0] != "lang"] + [("lang", "=", "fr_FR")]
            template = Template.search(domain, limit=1)
        return template

    @api.model
    def _build_extra_values(self, employee, profile, occasion_date, detail="", anniversary_years=0):
        joining_date = self._get_joining_date(employee)
        years = anniversary_years or self._years_of_service(joining_date, occasion_date)
        manager_name = ""
        if employee.parent_id:
            manager_name = employee.parent_id.name or ""
        department_name = ""
        if employee.department_id:
            department_name = employee.department_id.name
        elif profile and profile.department_id:
            department_name = profile.department_id.name

        placeholder = DocumentPlaceholderService(self.env)
        return {
            "equipe": department_name,
            "anciennete": str(years),
            "manager": manager_name,
            "date_evenement": placeholder.format_fr_date(occasion_date),
            "detail": detail or "",
        }

    @api.model
    def _render_content(self, content, profile, occasion_date, extra_values):
        if not content:
            return ""
        placeholder = DocumentPlaceholderService(self.env)
        rendered = placeholder.render(content, profile, letter_date=occasion_date)
        for key, value in extra_values.items():
            rendered = rendered.replace("{{%s}}" % key, value or "")
            rendered = rendered.replace("{{ %s }}" % key, value or "")
        return rendered

    @api.model
    def _get_team_partner_ids(self, employee, exclude_honoree=True):
        partners = self.env["res.partner"]
        if employee.department_id:
            teammates = self.env["hr.employee"].sudo().search(
                [
                    ("department_id", "=", employee.department_id.id),
                    ("active", "=", True),
                ]
            )
            if exclude_honoree and self._exclude_honoree_from_email():
                teammates = teammates.filtered(lambda e: e.id != employee.id)
            partners = teammates.mapped("user_id.partner_id").filtered(lambda p: p)
        elif employee.parent_id and employee.parent_id.user_id:
            partners = employee.parent_id.user_id.partner_id
        return partners

    @api.model
    def _get_team_emails(self, employee, exclude_honoree=True):
        partners = self._get_team_partner_ids(employee, exclude_honoree=exclude_honoree)
        emails = []
        for partner in partners:
            email = partner.email
            if email and email not in emails:
                emails.append(email)
        if not emails and employee.parent_id:
            manager_email = (
                employee.parent_id.work_email
                or employee.parent_id.private_email
                or (
                    employee.parent_id.user_id.partner_id.email
                    if employee.parent_id.user_id
                    else False
                )
            )
            if manager_email:
                emails.append(manager_email)
        return emails

    @api.model
    def _send_team_email(self, employee, subject, body_html, emails):
        if not emails:
            _logger.info(
                "Celebration: no team emails for employee %s", employee.name
            )
            return False
        try:
            self.env["mail.mail"].sudo().create(
                {
                    "subject": subject,
                    "body_html": body_html,
                    "email_to": ",".join(emails),
                    "auto_delete": True,
                }
            ).send()
            return True
        except Exception as exc:  # noqa: BLE001
            _logger.warning(
                "Celebration email failed for %s: %s", employee.name, exc
            )
            return False

    @api.model
    def _post_notification(self, profile, employee, message, partner_ids):
        if not message:
            return False
        body = "<p>%s</p>" % message
        partners = partner_ids or self._get_team_partner_ids(employee).ids
        try:
            if profile:
                profile.message_post(
                    body=body,
                    partner_ids=partners,
                    message_type="notification",
                    subtype_xmlid="mail.mt_comment",
                )
            elif employee.user_id:
                employee.user_id.partner_id.message_post(
                    body=body,
                    partner_ids=partners,
                    message_type="notification",
                    subtype_xmlid="mail.mt_comment",
                )
            return True
        except Exception as exc:  # noqa: BLE001
            _logger.warning(
                "Celebration notification failed for %s: %s",
                employee.name,
                exc,
            )
            return False

    @api.model
    def trigger_celebration(
        self,
        employee,
        occasion_type,
        occasion_date=None,
        detail="",
        template=None,
        anniversary_years=0,
        force=False,
    ):
        """Point d'entrée unique (cron, wizard manuel, ou futur n8n)."""
        employee = employee if hasattr(employee, "id") else self.env["hr.employee"].browse(employee)
        employee.ensure_one()
        occasion_date = occasion_date or fields.Date.context_today(self)

        if employee.celebration_opt_out and occasion_type != "custom":
            return False

        if not force and self._already_sent(employee, occasion_type, occasion_date):
            return False

        if not self._is_occasion_enabled(occasion_type) and not force:
            return False

        profile = self._get_profile(employee)
        if not profile:
            profile = self.env["pe.employee.profile"].sudo().create(
                {"employee_id": employee.id}
            )

        lang = self._employee_lang(employee)
        template = template or self._get_template(
            occasion_type, lang, anniversary_years=anniversary_years
        )
        if not template:
            _logger.warning(
                "Celebration: no template for %s / %s", occasion_type, lang
            )
            return False

        extra = self._build_extra_values(
            employee,
            profile,
            occasion_date,
            detail=detail,
            anniversary_years=anniversary_years,
        )
        subject = self._render_content(
            template.email_subject, profile, occasion_date, extra
        )
        body_html = self._render_content(
            template.email_body, profile, occasion_date, extra
        )
        notification = self._render_content(
            template.notification_message, profile, occasion_date, extra
        )

        emails = self._get_team_emails(employee)
        email_sent = self._send_team_email(employee, subject, body_html, emails)
        partners = self._get_team_partner_ids(employee)
        notification_sent = self._post_notification(
            profile, employee, notification, partners.ids
        )

        self.env["pe.celebration.log"].sudo().create(
            {
                "employee_id": employee.id,
                "profile_id": profile.id,
                "occasion_type": occasion_type,
                "occasion_date": occasion_date,
                "template_id": template.id,
                "detail": detail,
                "email_sent": email_sent,
                "notification_sent": notification_sent,
                "sent_at": fields.Datetime.now(),
            }
        )
        return True

    @api.model
    def cron_daily_celebrations(self):
        today = fields.Date.context_today(self)
        processed = 0
        for employee in self._active_employees():
            for match in self._detect_matches(employee, today):
                occasion_type = match["occasion_type"]
                if not self._is_occasion_enabled(occasion_type):
                    continue
                if self._already_sent(employee, occasion_type, match["occasion_date"]):
                    continue
                if self.trigger_celebration(
                    employee,
                    occasion_type,
                    occasion_date=match["occasion_date"],
                    detail=match.get("detail") or "",
                    anniversary_years=match.get("anniversary_years") or 0,
                ):
                    processed += 1
        _logger.info("PE celebrations cron: %s message(s) sent on %s", processed, today)
        return processed

    @api.model
    def _build_praise_chatter_body(self, sender_name, occasion_date, subject, message_html):
        placeholder = DocumentPlaceholderService(self.env)
        date_str = placeholder.format_fr_date(occasion_date)
        title = subject or _("Félicitations")
        return (
            '<div style="padding:12px 16px;border-left:4px solid #28a745;'
            'background:#f8fff9;border-radius:4px;">'
            '<h3 style="margin:0 0 8px;color:#28a745;">🎉 %s</h3>'
            '<p style="margin:0 0 12px;color:#666;font-size:13px;">'
            "%s <strong>%s</strong> — %s"
            "</p>%s</div>"
        ) % (
            title,
            _("Envoyé par"),
            sender_name,
            date_str,
            message_html or "",
        )

    @api.model
    def _get_employee_email(self, employee):
        if employee.work_email:
            return employee.work_email
        if employee.private_email:
            return employee.private_email
        if employee.user_id and employee.user_id.partner_id.email:
            return employee.user_id.partner_id.email
        return False

    @api.model
    def send_on_demand_praise(
        self,
        employee,
        message_html,
        profile=None,
        subject=None,
        template=None,
        occasion_date=None,
        send_employee_email=False,
        send_team_email=False,
        force=False,
    ):
        """Félicitation libre depuis le profil RH (message personnalisé)."""
        from odoo.tools.mail import html2plaintext

        employee = (
            employee
            if hasattr(employee, "id")
            else self.env["hr.employee"].browse(employee)
        )
        employee.ensure_one()
        occasion_date = occasion_date or fields.Date.context_today(self)
        message_html = (message_html or "").strip()
        if not message_html:
            return False

        profile = profile or self._get_profile(employee)
        if not profile:
            profile = self.env["pe.employee.profile"].sudo().create(
                {"employee_id": employee.id}
            )

        sender_name = self.env.user.name or _("RH")
        chatter_body = self._build_praise_chatter_body(
            sender_name,
            occasion_date,
            subject,
            message_html,
        )
        partner_ids = []
        if employee.user_id:
            partner_ids.append(employee.user_id.partner_id.id)

        notification_sent = False
        try:
            profile.message_post(
                body=chatter_body,
                subject=subject or _("Félicitations"),
                message_type="comment",
                subtype_xmlid="mail.mt_note",
                partner_ids=partner_ids,
            )
            notification_sent = True
        except Exception as exc:  # noqa: BLE001
            _logger.warning(
                "On-demand praise chatter failed for %s: %s",
                employee.name,
                exc,
            )

        email_subject = subject or _("Félicitations — %s") % employee.name
        email_sent = False
        if send_employee_email:
            employee_email = self._get_employee_email(employee)
            if employee_email:
                email_sent = self._send_team_email(
                    employee,
                    email_subject,
                    chatter_body,
                    [employee_email],
                )

        if send_team_email:
            team_emails = self._get_team_emails(employee)
            if team_emails:
                email_sent = (
                    self._send_team_email(
                        employee,
                        email_subject,
                        chatter_body,
                        team_emails,
                    )
                    or email_sent
                )

        self.env["pe.celebration.log"].sudo().create(
            {
                "employee_id": employee.id,
                "profile_id": profile.id,
                "occasion_type": "praise",
                "occasion_date": occasion_date,
                "template_id": template.id if template else False,
                "detail": html2plaintext(message_html)[:500],
                "email_sent": email_sent,
                "notification_sent": notification_sent,
                "sent_at": fields.Datetime.now(),
            }
        )
        return True
