# -*- coding: utf-8 -*-

from datetime import datetime, time, timedelta

import pytz

from odoo import api, fields, models

HIBA_LOGIN = "hiba@agencedoorway.com"
LEILA_LOGIN = "leiladaouadi@gmail.com"
FREELANCE_LOGINS = (HIBA_LOGIN, LEILA_LOGIN)
BASE_MAD = 5000.0
RDV_AVG_TARGET = 5.0
RDV_BONUS_MAD = 1000.0
CA_THRESHOLD_USD = 10000.0
CA_TRANCHE_USD = 5000.0
CA_BONUS_PER_TRANCHE_MAD = 500.0


def _toronto_month_bounds(day=None):
    tz = pytz.timezone("America/Toronto")
    now = day or datetime.now(tz)
    if hasattr(now, "tzinfo") and now.tzinfo is None:
        now = tz.localize(datetime.combine(now, time.min))
    start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    if start.month == 12:
        end = start.replace(year=start.year + 1, month=1)
    else:
        end = start.replace(month=start.month + 1)
    return (
        start.astimezone(pytz.utc).replace(tzinfo=None),
        end.astimezone(pytz.utc).replace(tzinfo=None),
        start.date(),
        end.date(),
    )


class HibaPayrollMixin(models.AbstractModel):
    _name = "hiba.payroll.mixin"
    _description = "Calcul paie freelance Hiba"

    @api.model
    def _hiba_user(self, login=None):
        domain = [("login", "in", FREELANCE_LOGINS), ("active", "=", True)]
        if login:
            domain = [("login", "=", login), ("active", "=", True)]
        return self.env["res.users"].sudo().search(domain, limit=1)

    @api.model
    def _hiba_employee(self, user=None):
        user = user or self._hiba_user()
        if not user:
            return self.env["hr.employee"]
        return self.env["hr.employee"].sudo().search(
            [("user_id", "=", user.id), ("active", "=", True)], limit=1
        )

    @api.model
    def hiba_month_stats(self, day=None, user=None):
        start_dt, end_dt, start_d, end_d = _toronto_month_bounds(day)
        user = user or self._hiba_user()
        employee = self._hiba_employee(user)
        if not employee or not user:
            return {}
        Attendance = self.env["hr.attendance"].sudo()
        atts = Attendance.search(
            [
                ("employee_id", "=", employee.id),
                ("check_in", ">=", start_dt),
                ("check_in", "<", end_dt),
            ]
        )
        hours = sum(atts.mapped("worked_hours"))
        work_days = len({(a.check_in.date() if a.check_in else None) for a in atts} - {None})
        open_att = Attendance.search(
            [("employee_id", "=", employee.id), ("check_out", "=", False)], limit=1
        )
        events = self.env["calendar.event"].sudo().search(
            [
                ("hiba_booked_by", "=", user.id),
                ("hiba_presence", "=", "present"),
                ("start", ">=", start_dt),
                ("start", "<", end_dt),
            ]
        )
        presents = len(events)
        avg = (presents / work_days) if work_days else 0.0
        bonus_rdv = RDV_BONUS_MAD if work_days and avg >= RDV_AVG_TARGET else 0.0

        leads = events.mapped("opportunity_id")
        leads |= self.env["crm.lead"].sudo().search(
            [
                ("user_id", "=", user.id),
                ("hiba_rdv_state", "=", "present"),
                ("hiba_rdv_start", ">=", start_dt),
                ("hiba_rdv_start", "<", end_dt),
            ]
        )
        sales_usd = 0.0
        usd = self.env.ref("base.USD", raise_if_not_found=False)
        for lead in leads:
            amount = lead.expected_revenue or 0.0
            currency = lead.company_currency_id or lead.company_id.currency_id
            if usd and currency and currency != usd:
                try:
                    amount = currency._convert(amount, usd, lead.company_id, start_d)
                except Exception:
                    pass
            sales_usd += amount
        extra = max(sales_usd - CA_THRESHOLD_USD, 0.0)
        tranches = int(extra // CA_TRANCHE_USD) if sales_usd > CA_THRESHOLD_USD else 0
        bonus_ca = tranches * CA_BONUS_PER_TRANCHE_MAD
        total = BASE_MAD + bonus_rdv + bonus_ca
        return {
            "employee_id": employee.id,
            "hours": round(hours, 2),
            "work_days": work_days,
            "checked_in": bool(open_att),
            "check_in": open_att.check_in if open_att else False,
            "rdv_present": presents,
            "rdv_avg": round(avg, 2),
            "bonus_rdv": bonus_rdv,
            "sales_usd": round(sales_usd, 2),
            "bonus_ca": bonus_ca,
            "ca_tranches": tranches,
            "base": BASE_MAD,
            "total": total,
            "currency": "MAD",
            "month": start_d.strftime("%Y-%m"),
        }


class PePayslipLive(models.Model):
    _inherit = "pe.payslip.live"

    def _recalculer_employe(self, employee, mois, debut, fin):
        payslip = super()._recalculer_employe(employee, mois, debut, fin)
        user = employee.user_id
        if not user or user.login not in FREELANCE_LOGINS:
            return payslip
        stats = self.env["hiba.payroll.mixin"].hiba_month_stats(user=user)
        if not stats:
            return payslip
        details = [
            "Freelance %s — forfait %s MAD" % (user.name, int(BASE_MAD)),
            "Heures pointées : %.2f h (%s jours)" % (stats["hours"], stats["work_days"]),
            "RDV présents : %s (moy. %.2f / jour travaillé, cible %s)"
            % (stats["rdv_present"], stats["rdv_avg"], int(RDV_AVG_TARGET)),
            "Bonus RDV : %s MAD" % int(stats["bonus_rdv"]),
            "CA généré : %.0f USD (seuil %.0f, tranche %.0f → %s × %s MAD)"
            % (
                stats["sales_usd"],
                CA_THRESHOLD_USD,
                CA_TRANCHE_USD,
                stats["ca_tranches"],
                int(CA_BONUS_PER_TRANCHE_MAD),
            ),
            "Bonus CA : %s MAD" % int(stats["bonus_ca"]),
            "Total : %s MAD" % int(stats["total"]),
        ]
        payslip.sudo().write(
            {
                "salaire_base": BASE_MAD,
                "devise_base": "MAD",
                "prime_presence": stats["bonus_rdv"],
                "prime_plateau": stats["bonus_ca"],
                "heures_reelles_mois": stats["hours"],
                "detail_calcul": "\n".join(details),
                "date_calcul": fields.Datetime.now(),
            }
        )
        return payslip

    @api.depends(
        "salaire_base",
        "prime_plateau",
        "prime_upsell",
        "prime_conversion",
        "prime_presence",
        "prime_coaching",
        "deduction_absences",
    )
    def _compute_total(self):
        super()._compute_total()
        for rec in self:
            if rec.employee_id.user_id.login == HIBA_LOGIN:
                rec.total_net_estime = rec.total_brut

    @api.model
    def action_open_my_payslip(self):
        if self.env.user.login == HIBA_LOGIN:
            return super(PePayslipLive, self.sudo()).action_open_my_payslip()
        return super().action_open_my_payslip()


class PeEmployeeProfile(models.Model):
    _inherit = "pe.employee.profile"

    def _hiba_minimal_hub_snapshot(self):
        user = self.env.user
        employee = self.env["hr.employee"].sudo().pe_resolve_user_employee(user)
        name = (employee.name if employee else user.name) or ""
        return {
            "employee": {
                "id": employee.id if employee else 0,
                "name": name,
                "first_name": name.split(" ")[0],
                "job": employee.job_id.name if employee and employee.job_id else "",
                "department": (
                    employee.department_id.name
                    if employee and employee.department_id
                    else ""
                ),
                "email": user.email or "",
            },
            "performance": {
                "score_global": 0,
                "percent": 0,
                "band": "",
                "trend": "stable",
            },
            "kpis": {
                "leave_remaining": None,
                "hours_month": None,
                "score_percent": 0,
                "next_eval": None,
            },
            "perf_series": [],
            "dev_plan": {
                "active_paths": 0,
                "progress_pct": 0,
                "coaching_plans": 0,
                "items": [],
            },
            "payroll": {
                "net": None,
                "currency": "MAD",
                "month": "",
                "hours": None,
                "has_payslip": False,
            },
            "legal_docs": [],
            "hr_docs": {
                "enrollments_total": 0,
                "enrollments_done": 0,
                "completion_pct": 0,
                "legal_articles": 0,
            },
        }

    @api.model
    def rh_hub_snapshot(self):
        try:
            data = super().rh_hub_snapshot()
        except Exception:
            # people_engine lit des modeles sans ACL employe, ou tente un create.
            data = self._hiba_minimal_hub_snapshot()
        if data.get("error"):
            return data
        user = self.env.user
        if user.login != HIBA_LOGIN:
            return data
        try:
            stats = self.env["hiba.payroll.mixin"].hiba_month_stats()
        except Exception:
            stats = {}
        if not stats:
            return data
        try:
            Payslip = self.env["pe.payslip.live"].sudo()
            employee = self.env["hr.employee"].sudo().pe_resolve_user_employee(user)
            if employee:
                mois = stats["month"]
                today = fields.Date.context_today(self)
                Payslip._recalculer_employe(
                    employee, mois, today.replace(day=1), today
                )
        except Exception:
            pass
        data["kpis"]["hours_month"] = stats["hours"]
        data["payroll"] = {
            "net": stats["total"],
            "currency": "MAD",
            "month": stats["month"],
            "hours": stats["hours"],
            "has_payslip": True,
            "base": stats["base"],
            "bonus_rdv": stats["bonus_rdv"],
            "bonus_ca": stats["bonus_ca"],
            "rdv_present": stats["rdv_present"],
            "rdv_avg": stats["rdv_avg"],
            "sales_usd": stats["sales_usd"],
            "checked_in": stats["checked_in"],
        }
        data["hiba_clock"] = {
            "checked_in": stats["checked_in"],
            "check_in": stats["check_in"],
        }
        return data

    @api.model
    def action_hiba_toggle_attendance(self):
        employee = self.env["hr.employee"].pe_resolve_user_employee()
        if not employee:
            return {"error": "no_employee"}
        employee.sudo()._attendance_action_change()
        stats = self.env["hiba.payroll.mixin"].hiba_month_stats()
        return {"ok": True, "checked_in": stats.get("checked_in"), "hours": stats.get("hours")}
