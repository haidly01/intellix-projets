# -*- coding: utf-8 -*-
import datetime
import logging

from odoo import api, fields, models

_logger = logging.getLogger(__name__)

PALIER_RULES = [
    (120.0, "120_et_plus", 1.25),
    (100.0, "100", 1.0),
    (75.0, "75", 0.50),
    (50.0, "50", 0.25),
    (0.0, "aucun", 0.0),
]


class PePayrollChallengeService(models.AbstractModel):
    _name = "pe.payroll.challenge.service"
    _description = "Service métriques et primes challenges paie"

    @api.model
    def _period_datetimes(self, date_start, date_end):
        if isinstance(date_start, str):
            date_start = fields.Date.from_string(date_start)
        if isinstance(date_end, str):
            date_end = fields.Date.from_string(date_end)
        start_dt = datetime.datetime.combine(date_start, datetime.time.min)
        end_dt = datetime.datetime.combine(date_end, datetime.time.max)
        return start_dt, end_dt

    @api.model
    def _employee_user(self, employee_id):
        employee = self.env["hr.employee"].browse(employee_id)
        return employee.user_id if employee else False

    @api.model
    def get_metrique(self, employee_id, date_start, date_end, type_metrique):
        """Lit la métrique depuis les logs IntelliX (appels, CRM, timesheet…)."""
        handlers = {
            "nombre_appels": self._metrique_nombre_appels,
            "nombre_contacts": self._metrique_nombre_contacts,
            "taux_conversion": self._metrique_taux_conversion,
            "leads_qualifies": self._metrique_leads_qualifies,
            "heures_loguees": self._metrique_heures_loguees,
            "taches_completees": self._metrique_taches_completees,
            "ca_genere": self._metrique_ca_genere,
        }
        handler = handlers.get(type_metrique)
        if not handler:
            return 0.0
        return round(handler(employee_id, date_start, date_end), 2)

    @api.model
    def _metrique_nombre_appels(self, employee_id, date_start, date_end):
        start_dt, end_dt = self._period_datetimes(date_start, date_end)
        total = 0
        CallLog = self.env.get("pe.call.log")
        if CallLog:
            total += CallLog.sudo().search_count(
                [
                    ("employee_id", "=", employee_id),
                    ("date_call", ">=", start_dt),
                    ("date_call", "<=", end_dt),
                ]
            )
        Session = self.env.get("doorway.vicidial.agent.session")
        user = self._employee_user(employee_id)
        if Session and user:
            sessions = Session.sudo().search(
                [
                    ("user_id", "=", user.id),
                    ("date_start", ">=", start_dt),
                    ("date_start", "<=", end_dt),
                    ("state", "=", "ended"),
                ]
            )
            total += sum(sessions.mapped("nb_appels"))
        return float(total)

    @api.model
    def _metrique_nombre_contacts(self, employee_id, date_start, date_end):
        start_dt, end_dt = self._period_datetimes(date_start, date_end)
        CallLog = self.env.get("pe.call.log")
        if CallLog:
            logs = CallLog.sudo().search(
                [
                    ("employee_id", "=", employee_id),
                    ("date_call", ">=", start_dt),
                    ("date_call", "<=", end_dt),
                ]
            )
            return float(len(logs))
        return self._metrique_nombre_appels(employee_id, date_start, date_end)

    @api.model
    def _metrique_taux_conversion(self, employee_id, date_start, date_end):
        start_dt, end_dt = self._period_datetimes(date_start, date_end)
        CallLog = self.env.get("pe.call.log")
        if CallLog:
            logs = CallLog.sudo().search(
                [
                    ("employee_id", "=", employee_id),
                    ("date_call", ">=", start_dt),
                    ("date_call", "<=", end_dt),
                ]
            )
            if not logs:
                return 0.0
            converted = logs.filtered(
                lambda l: l.outcome in ("demo_bookee", "vendu", "interesse")
            )
            return round(len(converted) / len(logs) * 100.0, 2)
        user = self._employee_user(employee_id)
        if not user:
            return 0.0
        Lead = self.env["crm.lead"].sudo()
        leads = Lead.search_count(
            [
                ("user_id", "=", user.id),
                ("create_date", ">=", start_dt),
                ("create_date", "<=", end_dt),
            ]
        )
        won = Lead.search_count(
            [
                ("user_id", "=", user.id),
                ("create_date", ">=", start_dt),
                ("create_date", "<=", end_dt),
                ("stage_id.is_won", "=", True),
            ]
        )
        return round(won / leads * 100.0, 2) if leads else 0.0

    @api.model
    def _metrique_leads_qualifies(self, employee_id, date_start, date_end):
        user = self._employee_user(employee_id)
        if not user:
            return 0.0
        start_dt, end_dt = self._period_datetimes(date_start, date_end)
        domain = [
            ("user_id", "=", user.id),
            ("create_date", ">=", start_dt),
            ("create_date", "<=", end_dt),
        ]
        Lead = self.env["crm.lead"].sudo()
        if "probability" in Lead._fields:
            domain.append(("probability", ">=", 50))
        return float(Lead.search_count(domain))

    @api.model
    def _metrique_heures_loguees(self, employee_id, date_start, date_end):
        payroll = self.env["pe.payroll.service"].sudo()
        hours, _lines = payroll.get_hours_from_timesheet(
            employee_id, date_start, date_end
        )
        if hours > 0:
            return hours
        return payroll.get_hours_from_presence(employee_id, date_start, date_end)

    @api.model
    def _metrique_taches_completees(self, employee_id, date_start, date_end):
        user = self._employee_user(employee_id)
        if not user:
            return 0.0
        start_dt, end_dt = self._period_datetimes(date_start, date_end)
        Task = self.env["project.task"].sudo()
        domain = [
            ("user_ids", "in", user.id),
            ("write_date", ">=", start_dt),
            ("write_date", "<=", end_dt),
        ]
        tasks = Task.search(domain)
        if "is_closed" in Task._fields:
            return float(len(tasks.filtered(lambda t: t.is_closed)))
        done_stages = self.env["project.task.type"].search([("fold", "=", True)])
        if done_stages:
            return float(
                len(tasks.filtered(lambda t: t.stage_id.id in done_stages.ids))
            )
        return float(len(tasks.filtered(lambda t: t.stage_id.name in ("Done", "Fait"))))

    @api.model
    def _metrique_ca_genere(self, employee_id, date_start, date_end):
        user = self._employee_user(employee_id)
        if not user:
            return 0.0
        start_dt, end_dt = self._period_datetimes(date_start, date_end)
        leads = self.env["crm.lead"].sudo().search(
            [
                ("user_id", "=", user.id),
                ("write_date", ">=", start_dt),
                ("write_date", "<=", end_dt),
                ("stage_id.is_won", "=", True),
            ]
        )
        if "expected_revenue" in leads._fields:
            return sum(leads.mapped("expected_revenue"))
        return float(len(leads))

    @api.model
    def calcul_prime(self, valeur_atteinte, objectif_valeur, montant_prime, prime_paliers):
        """Calcule palier et montant prime."""
        if not objectif_valeur:
            return 0.0, 0.0, "aucun"
        pct = valeur_atteinte / objectif_valeur * 100.0
        if not prime_paliers:
            if pct >= 100.0:
                return round(montant_prime, 2), pct, "100"
            return 0.0, pct, "aucun"
        palier = "aucun"
        factor = 0.0
        for threshold, code, mult in PALIER_RULES:
            if pct >= threshold:
                palier = code
                factor = mult
                break
        return round(montant_prime * factor, 2), pct, palier

    @api.model
    def recalculate_challenge(self, challenge):
        """Recalcule tous les résultats d'un challenge."""
        Result = self.env["pe.payroll.challenge.result"].sudo()
        employees = challenge._get_participant_employees()
        for emp in employees:
            valeur = self.get_metrique(
                emp.id,
                challenge.date_debut,
                challenge.date_fin,
                challenge.type_metrique,
            )
            prime, pct, palier = self.calcul_prime(
                valeur,
                challenge.objectif_valeur,
                challenge.montant_prime,
                challenge.prime_paliers,
            )
            result = Result.search(
                [("challenge_id", "=", challenge.id), ("employee_id", "=", emp.id)],
                limit=1,
            )
            vals = {
                "valeur_atteinte": valeur,
                "pourcentage": round(pct, 1),
                "palier_atteint": palier,
                "prime_calculee": prime,
                "date_calcul": fields.Datetime.now(),
                "statut": "calculated",
            }
            if result:
                if result.statut not in ("finalized", "paid"):
                    result.write(vals)
            else:
                vals.update(
                    {"challenge_id": challenge.id, "employee_id": emp.id}
                )
                Result.create(vals)
        return True

    @api.model
    def cron_recalculate_active_challenges(self):
        """Cron horaire : recalcule les challenges actifs."""
        challenges = self.env["pe.payroll.challenge"].sudo().search(
            [("statut", "in", ("active", "finished"))]
        )
        for challenge in challenges:
            try:
                self.recalculate_challenge(challenge)
            except Exception as exc:  # noqa: BLE001
                _logger.warning(
                    "Challenge %s recalc error: %s", challenge.name, exc
                )
        return True

    @api.model
    def get_employee_active_results(self, employee_id):
        """Dashboard agent : challenges en cours avec progression."""
        today = fields.Date.today()
        results = self.env["pe.payroll.challenge.result"].sudo().search(
            [
                ("employee_id", "=", employee_id),
                ("challenge_id.statut", "=", "active"),
                ("challenge_id.date_debut", "<=", today),
                ("challenge_id.date_fin", ">=", today),
            ]
        )
        data = []
        for res in results:
            data.append(
                {
                    "id": res.id,
                    "name": res.challenge_id.name,
                    "metric": res.type_metrique,
                    "value": res.valeur_atteinte,
                    "target": res.objectif_valeur,
                    "pct": res.pourcentage,
                    "palier": res.palier_atteint,
                    "prime_potential": res.prime_potentielle,
                    "prime_calculee": res.prime_calculee,
                    "days_left": res.jours_restants,
                }
            )
        return data

    @api.model
    def get_team_ranking(self, challenge_id):
        """Dashboard superviseur : classement équipe pour un challenge."""
        results = self.env["pe.payroll.challenge.result"].sudo().search(
            [("challenge_id", "=", challenge_id)],
            order="pourcentage desc, prime_calculee desc",
        )
        ranking = []
        for rank, res in enumerate(results, start=1):
            ranking.append(
                {
                    "rank": rank,
                    "employee": res.employee_id.name,
                    "employee_id": res.employee_id.id,
                    "metric": res.type_metrique,
                    "value": res.valeur_atteinte,
                    "target": res.objectif_valeur,
                    "pct": res.pourcentage,
                    "palier": res.palier_atteint,
                    "prime": res.prime_calculee,
                }
            )
        return ranking

    @api.model
    def finalize_for_payroll(self, employee_id, period_start, period_end, bulletin):
        """Finalise les primes challenge pour un bulletin de paie."""
        Challenge = self.env["pe.payroll.challenge"].sudo()
        Result = self.env["pe.payroll.challenge.result"].sudo()
        Line = self.env["pe.payroll.bulletin.challenge.line"].sudo()

        bulletin.challenge_line_ids.unlink()

        challenges = Challenge.search(
            [
                ("cumul_paie", "=", True),
                ("statut", "in", ("active", "finished")),
                ("date_fin", ">=", period_start),
                ("date_fin", "<=", period_end),
            ]
        )
        total = 0.0
        lines = []
        metric_labels = {
            "nombre_appels": "Appels",
            "nombre_contacts": "Contacts",
            "taux_conversion": "Taux conversion",
            "leads_qualifies": "Leads qualifiés",
            "heures_loguees": "Heures",
            "taches_completees": "Tâches",
            "ca_genere": "CA",
        }

        for challenge in challenges:
            employees = challenge._get_participant_employees()
            if employee_id not in employees.ids:
                continue
            self.recalculate_challenge(challenge)
            result = Result.search(
                [
                    ("challenge_id", "=", challenge.id),
                    ("employee_id", "=", employee_id),
                ],
                limit=1,
            )
            if not result or result.prime_calculee <= 0:
                continue
            if result.statut == "paid" and result.inclus_paie_id:
                continue
            result.write(
                {
                    "inclus_paie_id": bulletin.id,
                    "statut": "finalized",
                }
            )
            total += result.prime_calculee
            lines.append(
                {
                    "bulletin_id": bulletin.id,
                    "result_id": result.id,
                    "challenge_name": challenge.name,
                    "type_metrique": metric_labels.get(
                        challenge.type_metrique, challenge.type_metrique
                    ),
                    "valeur_atteinte": result.valeur_atteinte,
                    "objectif_valeur": challenge.objectif_valeur,
                    "pourcentage": result.pourcentage,
                    "palier_atteint": result.palier_atteint,
                    "montant": result.prime_calculee,
                }
            )
        if lines:
            Line.create(lines)
            for challenge in challenges.filtered(
                lambda c: all(
                    r.statut in ("finalized", "paid")
                    for r in c.resultat_ids
                )
            ):
                challenge.write({"statut": "closed"})
        return round(total, 2), lines

    @api.model
    def get_challenge_primes_summary(self, employee_id, period_start, period_end):
        """Prévisualisation sans finaliser (calcul paie)."""
        Challenge = self.env["pe.payroll.challenge"].sudo()
        total = 0.0
        details = []
        metric_labels = {
            "nombre_appels": "Appels",
            "nombre_contacts": "Contacts",
            "taux_conversion": "Taux conversion",
            "leads_qualifies": "Leads qualifiés",
            "heures_loguees": "Heures",
            "taches_completees": "Tâches",
            "ca_genere": "CA",
        }
        challenges = Challenge.search(
            [
                ("cumul_paie", "=", True),
                ("statut", "in", ("active", "finished")),
                ("date_fin", ">=", period_start),
                ("date_fin", "<=", period_end),
            ]
        )
        for challenge in challenges:
            if employee_id not in challenge._get_participant_employees().ids:
                continue
            valeur = self.get_metrique(
                employee_id,
                challenge.date_debut,
                challenge.date_fin,
                challenge.type_metrique,
            )
            prime, pct, palier = self.calcul_prime(
                valeur,
                challenge.objectif_valeur,
                challenge.montant_prime,
                challenge.prime_paliers,
            )
            if prime > 0:
                total += prime
                details.append(
                    "%s : %.2f (%s, %s%% → palier %s)"
                    % (
                        challenge.name,
                        prime,
                        metric_labels.get(challenge.type_metrique, ""),
                        round(pct, 1),
                        palier,
                    )
                )
        return round(total, 2), details
