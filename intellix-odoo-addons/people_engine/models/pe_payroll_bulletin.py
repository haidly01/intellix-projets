# -*- coding: utf-8 -*-
import datetime

from odoo import api, fields, models


class PePayrollBulletin(models.Model):
    _name = "pe.payroll.bulletin"
    _description = "Bulletin de paie IntelliX (période 25→24)"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "period_start desc, employee_id"

    name = fields.Char(
        string="Référence",
        required=True,
        copy=False,
        default=lambda self: self.env["ir.sequence"].next_by_code("pe.payroll.bulletin")
        or "BULLETIN",
    )
    employee_id = fields.Many2one("hr.employee", required=True, index=True)
    contract_id = fields.Many2one("pe.employment.contract", string="Contrat")
    period_start = fields.Date(string="Début période", required=True, index=True)
    period_end = fields.Date(string="Fin période", required=True, index=True)
    period_label = fields.Char(string="Période", compute="_compute_period_label", store=True)
    payment_date = fields.Date(string="Date paiement (5 du mois)")
    state = fields.Selection(
        [
            ("draft", "Brouillon"),
            ("calculated", "Calculé"),
            ("validated", "Validé"),
            ("paid", "Payé"),
        ],
        default="draft",
        tracking=True,
    )
    salaire_base = fields.Float(string="Salaire de base")
    devise = fields.Selection(
        [("MAD", "MAD"), ("EUR", "EUR"), ("CAD", "CAD")],
        default="MAD",
    )
    heures_loggees = fields.Float(string="Heures loggées")
    heures_pause_deductibles = fields.Float(string="Pauses déduites")
    heures_nettes = fields.Float(string="Heures nettes")
    heures_sup_25 = fields.Float(string="HS +25 %")
    heures_sup_50 = fields.Float(string="HS +50 %")
    nb_appels = fields.Integer(string="Appels")
    prime_plateau = fields.Float()
    prime_upsell = fields.Float()
    prime_conversion = fields.Float()
    primes_challenges = fields.Float(string="Primes challenges")
    prime_performance = fields.Float(string="Prime performance KPI")
    challenge_line_ids = fields.One2many(
        "pe.payroll.bulletin.challenge.line",
        "bulletin_id",
        string="Détail challenges",
        readonly=True,
    )
    deductions_disciplinaires = fields.Float(
        string="Déductions disciplinaires",
        compute="_compute_deductions_disciplinaires",
        store=True,
    )
    heures_non_reconnues = fields.Float(
        string="Heures non reconnues",
        compute="_compute_deductions_disciplinaires",
        store=True,
    )
    deduction_line_ids = fields.One2many(
        "pe.payroll.bulletin.deduction.line",
        "bulletin_id",
        string="Détail déductions disciplinaires",
        readonly=True,
    )
    deduction_absences = fields.Float(string="Déductions")
    montant_brut = fields.Float(string="Brut")
    montant_net = fields.Float(string="Net estimé")
    detail_calcul = fields.Text(string="Détail calcul", readonly=True)
    date_calcul = fields.Datetime(string="Dernier calcul", readonly=True)
    payslip_live_id = fields.Many2one("pe.payslip.live", string="Fiche temps réel liée")

    @api.depends("period_start", "period_end")
    def _compute_period_label(self):
        for rec in self:
            if rec.period_start and rec.period_end:
                rec.period_label = "%s → %s" % (
                    rec.period_start.strftime("%d/%m/%Y"),
                    rec.period_end.strftime("%d/%m/%Y"),
                )
            else:
                rec.period_label = ""

    @api.depends("deduction_line_ids.montant", "deduction_line_ids.heures")
    def _compute_deductions_disciplinaires(self):
        for rec in self:
            lines = rec.deduction_line_ids
            rec.deductions_disciplinaires = sum(lines.mapped("montant"))
            rec.heures_non_reconnues = sum(lines.mapped("heures"))

    _employee_period_unique = models.Constraint(
        "unique(employee_id, period_start, period_end)",
        "Un bulletin par employé et par période.",
    )

    def action_calculate(self):
        svc = self.env["pe.payroll.service"].sudo()
        challenge_svc = self.env["pe.payroll.challenge.service"].sudo()
        for rec in self:
            result = svc.calculate_employee_payroll(
                rec.employee_id.id, rec.period_start, rec.period_end
            )
            primes_challenges, _lines = challenge_svc.finalize_for_payroll(
                rec.employee_id.id,
                rec.period_start,
                rec.period_end,
                rec,
            )
            montant_brut = (
                result.get("montant_brut", 0.0)
                - result.get("primes_challenges", 0.0)
                + primes_challenges
                - rec.deductions_disciplinaires
            )
            detail = result.get("detail_calcul", "")
            if primes_challenges:
                detail += "\nPrimes challenges : %.2f" % primes_challenges
            if rec.deductions_disciplinaires:
                detail += "\nDéductions disciplinaires : %.2f" % rec.deductions_disciplinaires
            rec.write(
                {
                    "contract_id": result.get("contract_id"),
                    "salaire_base": result.get("salaire_base"),
                    "devise": result.get("devise"),
                    "heures_loggees": result.get("heures_loggees"),
                    "heures_pause_deductibles": result.get("heures_pause_deductibles"),
                    "heures_nettes": result.get("heures_nettes"),
                    "heures_sup_25": result.get("heures_sup_25"),
                    "heures_sup_50": result.get("heures_sup_50"),
                    "nb_appels": result.get("nb_appels"),
                    "prime_plateau": result.get("prime_plateau"),
                    "prime_upsell": result.get("prime_upsell"),
                    "prime_conversion": result.get("prime_conversion"),
                    "primes_challenges": primes_challenges,
                    "prime_performance": result.get("prime_performance", 0.0),
                    "deduction_absences": result.get("deduction_absences"),
                    "montant_brut": round(montant_brut, 2),
                    "montant_net": round(montant_brut * 0.85, 2),
                    "detail_calcul": detail,
                    "date_calcul": fields.Datetime.now(),
                    "state": "calculated",
                }
            )

    def action_validate(self):
        self.write({"state": "validated"})

    def action_mark_paid(self):
        self.write({"state": "paid"})

    @api.model
    def generer_bulletins_periode_courante(self):
        """Cron : génère/recalcule les bulletins de la période en cours."""
        svc = self.env["pe.payroll.service"].sudo()
        period = svc.get_payroll_period()
        employees = self.env["hr.employee"].search([("active", "=", True)])
        for emp in employees:
            if not svc.is_subject_morocco_payroll(emp.id, period["period_end"]):
                continue
            bulletin = self.search(
                [
                    ("employee_id", "=", emp.id),
                    ("period_start", "=", period["period_start"]),
                    ("period_end", "=", period["period_end"]),
                ],
                limit=1,
            )
            if not bulletin:
                bulletin = self.create(
                    {
                        "employee_id": emp.id,
                        "period_start": period["period_start"],
                        "period_end": period["period_end"],
                        "payment_date": period["payment_date"],
                    }
                )
            bulletin.action_calculate()
        return True

    @api.model
    def action_open_current_period(self):
        """Action menu : bulletins période courante."""
        svc = self.env["pe.payroll.service"].sudo()
        period = svc.get_payroll_period()
        return {
            "type": "ir.actions.act_window",
            "name": "Bulletins — %s" % period["label"],
            "res_model": "pe.payroll.bulletin",
            "view_mode": "list,form",
            "domain": [
                ("period_start", "=", period["period_start"]),
                ("period_end", "=", period["period_end"]),
            ],
            "context": {
                "default_period_start": period["period_start"],
                "default_period_end": period["period_end"],
                "default_payment_date": period["payment_date"],
            },
        }

    def action_print_bulletin(self):
        self.ensure_one()
        return self.env.ref(
            "people_engine.action_report_pe_payroll_bulletin"
        ).report_action(self)
