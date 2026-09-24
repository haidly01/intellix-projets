# -*- coding: utf-8 -*-
import datetime
import logging
from collections import defaultdict

from odoo import api, fields, models

_logger = logging.getLogger(__name__)

MOROCCO_WEEKLY_HOURS = 44.0
OT_TIER1_MAX = 6.0
OT_TIER1_PREMIUM = 0.25
OT_TIER2_PREMIUM = 0.50
MONTHLY_HOURS_MA = 191.33  # 44h × 52 / 12
FREELANCE_HOURS_PER_DAY = 8.0

# Comparaison CDD/CDI vs Freelance :
# | Type     | Document  | Base calc              | Pauses | Primes   | Payment      |
# | CDD/CDI  | Bulletin  | Salary × period        | Yes    | Yes      | 5th M+2      |
# | Freelance| Facture   | Rate × logs or forfait | Yes*   | Optional | J+delay      |
# * Pauses déduites uniquement en facturation horaire.


class PePayrollService(models.AbstractModel):
    _name = "pe.payroll.service"
    _description = "Service calcul paie IntelliX (période 25→24, Maroc 44h)"

    @api.model
    def get_payroll_period(self, ref_date=None):
        """Période de paie : du 25 du mois M au 24 du mois M+1."""
        ref = ref_date or fields.Date.today()
        if isinstance(ref, datetime.datetime):
            ref = ref.date()
        if ref.day >= 25:
            period_start = datetime.date(ref.year, ref.month, 25)
            if ref.month == 12:
                period_end = datetime.date(ref.year + 1, 1, 24)
            else:
                period_end = datetime.date(ref.year, ref.month + 1, 24)
        else:
            if ref.month == 1:
                period_start = datetime.date(ref.year - 1, 12, 25)
            else:
                period_start = datetime.date(ref.year, ref.month - 1, 25)
            period_end = datetime.date(ref.year, ref.month, 24)

        pay_month = period_start.month + 2
        pay_year = period_start.year
        while pay_month > 12:
            pay_month -= 12
            pay_year += 1
        payment_date = datetime.date(pay_year, pay_month, 5)
        label = "%s → %s" % (
            period_start.strftime("%d/%m/%Y"),
            period_end.strftime("%d/%m/%Y"),
        )
        return {
            "period_start": period_start,
            "period_end": period_end,
            "payment_date": payment_date,
            "label": label,
            "code": "%s_%s" % (period_start.strftime("%Y%m"), period_end.strftime("%Y%m")),
        }

    @api.model
    def _week_start(self, day):
        return day - datetime.timedelta(days=day.weekday())

    @api.model
    def get_hours_from_timesheet(self, employee_id, date_start, date_end):
        """Heures depuis account.analytic.line (hr_timesheet)."""
        AnalyticLine = self.env["account.analytic.line"].sudo()
        if "employee_id" not in AnalyticLine._fields:
            return 0.0, []
        lines = AnalyticLine.search(
            [
                ("employee_id", "=", employee_id),
                ("date", ">=", date_start),
                ("date", "<=", date_end),
            ]
        )
        total = sum(lines.mapped("unit_amount"))
        return round(total, 2), lines

    @api.model
    def get_hours_from_presence(self, employee_id, date_start, date_end):
        """Repli : heures depuis pe.presence.summary / service."""
        Summary = self.env["pe.presence.summary"].sudo()
        summaries = Summary.search(
            [
                ("employee_id", "=", employee_id),
                ("date", ">=", date_start),
                ("date", "<=", date_end),
            ]
        )
        if summaries:
            return round(sum(summaries.mapped("heures_reelles")), 2)

        svc = self.env["pe.presence.service"].sudo()
        total = 0.0
        current = date_start
        while current <= date_end:
            h = svc.calculer_heures_reelles_jour(employee_id, current)
            total += h.get("heures_reelles", 0.0)
            current += datetime.timedelta(days=1)
        return round(total, 2)

    @api.model
    def get_hours_from_sessions(self, employee_id, date_start, date_end):
        """Heures nettes depuis sessions VICIdial terminées."""
        Session = self.env.get("doorway.vicidial.agent.session")
        if not Session:
            return 0.0, 0
        employee = self.env["hr.employee"].browse(employee_id)
        if not employee.user_id:
            return 0.0, 0
        debut = datetime.datetime.combine(date_start, datetime.time.min)
        fin = datetime.datetime.combine(date_end, datetime.time.max)
        sessions = Session.sudo().search(
            [
                ("user_id", "=", employee.user_id.id),
                ("date_start", ">=", debut),
                ("date_start", "<=", fin),
                ("state", "=", "ended"),
            ]
        )
        seconds = sum(sessions.mapped("duree_travail_secondes"))
        calls = sum(sessions.mapped("nb_appels"))
        return round(seconds / 3600.0, 2), calls

    @api.model
    def get_pause_deduction_hours(self, employee_id, date_start, date_end):
        """Pauses non déjeuner à déduire (pe.session.pause)."""
        Pause = self.env.get("pe.session.pause")
        if not Pause:
            return 0.0
        pauses = Pause.sudo().search(
            [
                ("employee_id", "=", employee_id),
                ("date_start", ">=", datetime.datetime.combine(date_start, datetime.time.min)),
                ("date_start", "<=", datetime.datetime.combine(date_end, datetime.time.max)),
                ("pause_type", "!=", "dejeuner"),
                ("state", "=", "ended"),
            ]
        )
        seconds = sum(pauses.mapped("duration_seconds"))
        return round(seconds / 3600.0, 2)

    @api.model
    def compute_weekly_overtime(self, employee_id, date_start, date_end, net_hours_by_day):
        """Heures sup Maroc : +25 % (6 h max/sem), +50 % au-delà (base 44 h/sem)."""
        weekly = defaultdict(float)
        for day, hours in net_hours_by_day.items():
            if not hours:
                continue
            ws = self._week_start(day)
            weekly[ws] += hours

        ot_25 = ot_50 = 0.0
        for ws, hours in weekly.items():
            if ws + datetime.timedelta(days=6) < date_start:
                continue
            if ws > date_end:
                continue
            excess = max(hours - MOROCCO_WEEKLY_HOURS, 0.0)
            ot_25 += min(excess, OT_TIER1_MAX)
            ot_50 += max(excess - OT_TIER1_MAX, 0.0)
        return round(ot_25, 2), round(ot_50, 2)

    @api.model
    def _net_hours_by_day(self, employee_id, date_start, date_end, logged_hours):
        """Répartition journalière approximative pour le calcul hebdo des HS."""
        Summary = self.env["pe.presence.summary"].sudo()
        summaries = Summary.search(
            [
                ("employee_id", "=", employee_id),
                ("date", ">=", date_start),
                ("date", "<=", date_end),
            ]
        )
        if summaries:
            return {s.date: s.heures_reelles for s in summaries}

        days = (date_end - date_start).days + 1
        if days <= 0:
            return {}
        per_day = logged_hours / days
        result = {}
        current = date_start
        while current <= date_end:
            result[current] = per_day
            current += datetime.timedelta(days=1)
        return result

    @api.model
    def is_subject_morocco_payroll(self, employee_id, ref_date=None):
        """True si l'employé doit recevoir un bulletin paie Maroc (CDD/CDI)."""
        profile = self.env["pe.employee.profile"].sudo().search(
            [("employee_id", "=", employee_id)], limit=1
        )
        if profile and profile.hors_paie_maroc:
            return False
        if profile and profile.pays_affectation and profile.pays_affectation != "MA":
            return False
        contract = self.get_active_contract(employee_id, ref_date)
        if contract and contract.contract_type == "freelance":
            return False
        return True

    @api.model
    def get_active_contract(self, employee_id, ref_date=None):
        ref = ref_date or fields.Date.today()
        Contract = self.env["pe.employment.contract"].sudo()
        return Contract.search(
            [
                ("employee_id", "=", employee_id),
                ("statut", "=", "active"),
                ("date_start", "<=", ref),
                "|",
                ("date_end", "=", False),
                ("date_end", ">=", ref),
            ],
            order="date_start desc",
            limit=1,
        )

    @api.model
    def calculate_employee_payroll(self, employee_id, period_start, period_end):
        """Calcul complet pour un employé sur une période."""
        employee = self.env["hr.employee"].browse(employee_id)
        contract = self.get_active_contract(employee_id, period_end)
        profile = self.env["pe.employee.profile"].sudo().search(
            [("employee_id", "=", employee_id)], limit=1
        )

        salaire_base = 0.0
        devise = "MAD"
        if contract:
            salaire_base = contract.salaire_base
            devise = contract.devise or "MAD"
        elif profile:
            salaire_base = profile.salaire_base
            devise = profile.devise_remuneration or "MAD"

        logged, _lines = self.get_hours_from_timesheet(
            employee_id, period_start, period_end
        )
        source = "timesheet"
        if logged <= 0:
            logged = self.get_hours_from_presence(employee_id, period_start, period_end)
            source = "presence"
        if logged <= 0:
            logged, _calls = self.get_hours_from_sessions(
                employee_id, period_start, period_end
            )
            source = "vicidial_sessions"

        pause_deduct = self.get_pause_deduction_hours(
            employee_id, period_start, period_end
        )
        net_hours = max(logged - pause_deduct, 0.0)

        _, session_calls = self.get_hours_from_sessions(
            employee_id, period_start, period_end
        )

        by_day = self._net_hours_by_day(
            employee_id, period_start, period_end, net_hours
        )
        heures_sup_25, heures_sup_50 = self.compute_weekly_overtime(
            employee_id, period_start, period_end, by_day
        )

        hourly = salaire_base / MONTHLY_HOURS_MA if salaire_base else 0.0
        weeks = max((period_end - period_start).days + 1, 1) / 7.0
        expected_hours = weeks * MOROCCO_WEEKLY_HOURS
        base_prorata = (
            salaire_base * min(net_hours / expected_hours, 1.0)
            if expected_hours
            else salaire_base
        )
        ot_premium = (
            heures_sup_25 * hourly * OT_TIER1_PREMIUM
            + heures_sup_50 * hourly * OT_TIER2_PREMIUM
        )

        prime_plateau = prime_upsell = prime_conversion = 0.0
        details = [
            "Source heures : %s" % source,
            "Heures loggées : %.2f h" % logged,
            "Pauses déduites (hors déjeuner) : %.2f h" % pause_deduct,
            "Heures nettes : %.2f h" % net_hours,
            "HS +25%% : %.2f h | HS +50%% : %.2f h" % (heures_sup_25, heures_sup_50),
        ]

        dept = self.env["pe.department"].sudo().search(
            [("employee_ids", "in", [employee_id])], limit=1
        )
        if not dept and profile and profile.department_pe_id:
            dept = profile.department_pe_id
        if dept:
            for config in dept.prime_config_ids.filtered("actif"):
                result = config.calculer_prime_employe(
                    employee_id, period_start, period_end
                )
                if config.type_prime == "plateau_leads":
                    prime_plateau = result.get("montant", 0.0)
                    details.append("Plateau: %s" % result.get("detail"))
                elif config.type_prime == "upsell_lead":
                    prime_upsell = result.get("montant", 0.0)
                    details.append("Upsell: %s" % result.get("detail"))
                elif config.type_prime == "conversion_ia":
                    prime_conversion = result.get("montant", 0.0)
                    details.append("Conversion IA: %s" % result.get("detail"))

        prime_performance = self._compute_prime_performance(
            employee_id, period_start, period_end, contract
        )
        if prime_performance:
            details.append("Prime performance KPI : %.2f" % prime_performance)

        deductions = sum(
            self.env["pe.leave.impact.prime"]
            .sudo()
            .search(
                [
                    ("employee_id", "=", employee_id),
                    ("mois", "=", period_start.strftime("%Y-%m")),
                ]
            )
            .mapped("prime_deduite")
        )

        absence_deduction, absence_details = self.appliquer_deduction_absence(
            employee_id, period_start, period_end, salaire_base
        )
        deductions += absence_deduction
        for line in absence_details:
            details.append(line)

        challenge_svc = self.env["pe.payroll.challenge.service"].sudo()
        primes_challenges, challenge_details = challenge_svc.get_challenge_primes_summary(
            employee_id, period_start, period_end
        )
        for line in challenge_details:
            details.append("Challenge: %s" % line)

        montant_brut = (
            base_prorata
            + ot_premium
            + prime_plateau
            + prime_upsell
            + prime_conversion
            + primes_challenges
            + prime_performance
            - deductions
        )
        montant_net = montant_brut * 0.85

        return {
            "employee_id": employee_id,
            "contract_id": contract.id if contract else False,
            "salaire_base": salaire_base,
            "devise": devise,
            "heures_loggees": logged,
            "heures_pause_deductibles": pause_deduct,
            "heures_nettes": net_hours,
            "heures_sup_25": heures_sup_25,
            "heures_sup_50": heures_sup_50,
            "nb_appels": session_calls,
            "prime_plateau": prime_plateau,
            "prime_upsell": prime_upsell,
            "prime_conversion": prime_conversion,
            "primes_challenges": primes_challenges,
            "prime_performance": prime_performance,
            "deduction_absences": deductions,
            "montant_brut": round(montant_brut, 2),
            "montant_net": round(montant_net, 2),
            "detail_calcul": "\n".join(details),
            "hourly_rate": round(hourly, 4),
            "ot_premium": round(ot_premium, 2),
        }

    @api.model
    def calcul_paie_freelance(
        self, employee_id, period_start, period_end, contract=None, date_emission=None
    ):
        """Calcul facture freelance : horaire, journalier ou forfait + primes challenges."""
        contract = contract or self.get_active_contract(employee_id, period_end)
        if not contract or contract.contract_type != "freelance":
            return {"error": "Aucun contrat freelance actif."}

        logged, _lines = self.get_hours_from_timesheet(
            employee_id, period_start, period_end
        )
        source = "timesheet"
        if logged <= 0:
            logged = self.get_hours_from_presence(employee_id, period_start, period_end)
            source = "presence"
        if logged <= 0:
            logged, _calls = self.get_hours_from_sessions(
                employee_id, period_start, period_end
            )
            source = "vicidial_sessions"

        type_fact = contract.type_facturation or "horaire"
        pause_deduct = 0.0
        if type_fact == "horaire":
            pause_deduct = self.get_pause_deduction_hours(
                employee_id, period_start, period_end
            )
        net_hours = max(logged - pause_deduct, 0.0)
        jours_loguees = round(net_hours / FREELANCE_HOURS_PER_DAY, 2)

        taux_applique = 0.0
        montant_ht = 0.0
        alerte_forfait = False
        alerte_heures = net_hours <= 0
        details = [
            "Source heures : %s" % source,
            "Heures loguées : %.2f h" % logged,
        ]
        if type_fact == "horaire":
            details.append("Pauses déduites : %.2f h" % pause_deduct)
            details.append("Heures nettes : %.2f h" % net_hours)
            taux_applique = contract.taux_horaire_freelance
            montant_ht = round(net_hours * taux_applique, 2)
            details.append(
                "Horaire : %.2f h × %.2f = %.2f"
                % (net_hours, taux_applique, montant_ht)
            )
        elif type_fact == "journalier":
            taux_applique = contract.taux_journalier
            montant_ht = round(jours_loguees * taux_applique, 2)
            details.append(
                "Journalier : %.2f j (8h/j) × %.2f = %.2f"
                % (jours_loguees, taux_applique, montant_ht)
            )
        elif type_fact == "forfait":
            taux_applique = contract.montant_forfait
            min_h = contract.heures_forfait_min or 0.0
            if net_hours >= min_h:
                montant_ht = contract.montant_forfait
                details.append(
                    "Forfait : %.2f (min %.2f h atteint, %.2f h loguées)"
                    % (montant_ht, min_h, net_hours)
                )
            else:
                alerte_forfait = True
                details.append(
                    "⚠ Forfait incomplet : %.2f h / %.2f h minimum"
                    % (net_hours, min_h)
                )

        primes_challenges = 0.0
        if contract.challenges_eligible:
            challenge_svc = self.env["pe.payroll.challenge.service"].sudo()
            primes_challenges, challenge_details = (
                challenge_svc.get_challenge_primes_summary(
                    employee_id, period_start, period_end
                )
            )
            for line in challenge_details:
                details.append("Challenge: %s" % line)

        tva = 0.0  # Auto-entrepreneur Maroc : TVA 0 %
        crm_ded_pct = 0.0
        disc_svc = self.env.get("pe.disciplinary.service")
        if disc_svc:
            crm_ded_pct = disc_svc.sudo().get_crm_facture_deduction_pct(
                employee_id, period_start, period_end
            )
        if crm_ded_pct:
            deduction = round(montant_ht * crm_ded_pct / 100.0, 2)
            montant_ht = max(montant_ht - deduction, 0.0)
            details.append(
                "Déduction CRM sous-traitant : -%d%% (%.2f MAD) — taux saisie < seuil"
                % (crm_ded_pct, deduction)
            )
        montant_ttc = round(montant_ht + tva, 2)
        total_a_payer = round(montant_ttc + primes_challenges, 2)

        emission = date_emission or period_end
        if isinstance(emission, datetime.datetime):
            emission = emission.date()
        delai = contract.delai_paiement or 30
        date_echeance = emission + datetime.timedelta(days=delai)

        return {
            "employee_id": employee_id,
            "contract_id": contract.id,
            "heures_loguees": logged,
            "jours_loguees": jours_loguees,
            "type_facturation": type_fact,
            "taux_applique": taux_applique,
            "montant_ht": montant_ht,
            "tva": tva,
            "montant_ttc": montant_ttc,
            "primes_challenges": primes_challenges,
            "total_a_payer": total_a_payer,
            "devise": contract.devise or "MAD",
            "date_emission": emission,
            "date_echeance": date_echeance,
            "ice_freelance": contract.ice_numero,
            "rib_freelance": contract.rib,
            "rc_freelance": contract.rc_numero,
            "detail_calcul": "\n".join(details),
            "alerte_forfait": alerte_forfait,
            "alerte_heures": alerte_heures,
        }

    @api.model
    def get_supervisor_pause_status(self):
        """Dashboard superviseur : agents en pause avec timers."""
        Session = self.env.get("doorway.vicidial.agent.session")
        Pause = self.env.get("pe.session.pause")
        Profile = self.env["pe.employee.profile"].sudo()
        agents = []
        now = fields.Datetime.now()
        for profile in Profile.search([("vicidial_user", "!=", False)]):
            active_pause = False
            pause_seconds = 0
            pause_type = ""
            session_state = "offline"
            if Pause:
                active_pause = Pause.sudo().search(
                    [("employee_id", "=", profile.employee_id.id), ("state", "=", "active")],
                    limit=1,
                )
                if active_pause:
                    pause_type = active_pause.pause_type
                    pause_seconds = int(
                        (now - active_pause.date_start).total_seconds()
                    )
            if Session and profile.user_id:
                session = Session.sudo().search(
                    [
                        ("user_id", "=", profile.user_id.id),
                        ("state", "in", ("active", "paused")),
                    ],
                    limit=1,
                )
                if session:
                    session_state = session.state
            alert = False
            if active_pause:
                limits = {"pausette": 15 * 60, "dejeuner": 60 * 60, "personnelle": 30 * 60}
                limit = limits.get(pause_type, 30 * 60)
                alert = pause_seconds > limit
            agents.append(
                {
                    "profile_id": profile.id,
                    "name": profile.display_name,
                    "cc_status": profile.cc_status,
                    "session_state": session_state,
                    "pause_type": pause_type,
                    "pause_seconds": pause_seconds,
                    "pause_alert": alert,
                }
            )
        return {"agents": agents, "timestamp": fields.Datetime.to_string(now)}

    @api.model
    def appliquer_deduction_absence(self, employee_id, period_start, period_end, salaire_base):
        """Déductions paie pour absences injustifiées confirmées sur la période."""
        Absence = self.env.get("pe.absence.detected")
        if not Absence:
            return 0.0, []
        absences = Absence.sudo().search(
            [
                ("employee_id", "=", employee_id),
                ("date_absence", ">=", period_start),
                ("date_absence", "<=", period_end),
                ("statut", "=", "injustifiee"),
                ("impact_paie", "=", True),
            ]
        )
        if not absences:
            return 0.0, []
        hourly = salaire_base / MONTHLY_HOURS_MA if salaire_base else 0.0
        total = 0.0
        detail_lines = []
        for absence in absences:
            deduction = round(absence.heures_deduites * hourly, 2)
            total += deduction
            detail_lines.append(
                "Absence injustifiée %s : %.2f h → -%.2f MAD"
                % (absence.date_absence.strftime("%d/%m/%Y"), absence.heures_deduites, deduction)
            )
        return round(total, 2), detail_lines

    @api.model
    def _compute_prime_performance(self, employee_id, period_start, period_end, contract):
        """Prime performance conditionnelle selon snapshots KPI (commercial/marketing)."""
        if not contract or not contract.prime_performance_base:
            return 0.0
        Snapshot = self.env.get("pe.kpi.snapshot")
        if not Snapshot:
            return 0.0
        snapshots = Snapshot.sudo().search(
            [
                ("employee_id", "=", employee_id),
                ("periode_debut", ">=", period_start),
                ("periode_fin", "<=", period_end),
            ]
        )
        if not snapshots:
            return 0.0
        statuts = snapshots.mapped("statut_global")
        base = contract.prime_performance_base
        if all(s == "ok" for s in statuts):
            return base
        if statuts.count("ok") >= len(statuts) * 0.75:
            return round(base * 0.5, 2)
        if "critique" in statuts:
            return 0.0
        return 0.0
