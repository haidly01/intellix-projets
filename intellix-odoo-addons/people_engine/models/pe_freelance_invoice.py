# -*- coding: utf-8 -*-
import datetime
import re

from odoo import api, fields, models


class PeFreelanceInvoice(models.Model):
    _name = "pe.freelance.invoice"
    _description = "Facture freelance IntelliX (période 25→24)"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "period_start desc, employee_id"

    name = fields.Char(
        string="Référence",
        required=True,
        copy=False,
        readonly=True,
        default="New",
    )
    employee_id = fields.Many2one("hr.employee", required=True, index=True, tracking=True)
    contrat_id = fields.Many2one(
        "pe.employment.contract",
        string="Contrat",
        domain=[("contract_type", "=", "freelance")],
    )
    period_start = fields.Date(string="Début période", required=True, index=True)
    period_end = fields.Date(string="Fin période", required=True, index=True)
    period_label = fields.Char(compute="_compute_period_label", store=True)
    heures_loguees = fields.Float(string="Heures loguées")
    jours_loguees = fields.Float(string="Jours logués")
    type_facturation = fields.Selection(
        [
            ("horaire", "Horaire"),
            ("journalier", "Journalier"),
            ("forfait", "Forfait"),
        ],
        string="Type facturation",
    )
    taux_applique = fields.Float(string="Taux appliqué")
    montant_ht = fields.Float(string="Montant HT")
    tva = fields.Float(string="TVA", default=0.0)
    montant_ttc = fields.Float(string="Montant TTC")
    primes_challenges = fields.Float(string="Primes challenges")
    total_a_payer = fields.Float(string="Total à payer")
    devise = fields.Selection(
        [("MAD", "MAD"), ("EUR", "EUR"), ("USD", "USD"), ("CAD", "CAD")],
        default="MAD",
    )
    date_emission = fields.Date(string="Date émission", tracking=True)
    date_echeance = fields.Date(string="Date échéance", tracking=True)
    statut = fields.Selection(
        [
            ("brouillon", "Brouillon"),
            ("emise", "Émise"),
            ("payee", "Payée"),
            ("en_retard", "En retard"),
        ],
        default="brouillon",
        tracking=True,
        index=True,
    )
    date_paiement_reel = fields.Date(string="Date paiement réel")
    ice_freelance = fields.Char(string="ICE freelance")
    rib_freelance = fields.Char(string="RIB freelance")
    rc_freelance = fields.Char(string="RC freelance")
    detail_calcul = fields.Text(string="Détail calcul", readonly=True)
    alerte_forfait = fields.Boolean(string="Forfait incomplet", readonly=True)
    alerte_heures = fields.Boolean(string="Heures non loguées", readonly=True)
    date_calcul = fields.Datetime(string="Dernier calcul", readonly=True)

    _employee_period_unique = models.Constraint(
        "unique(employee_id, period_start, period_end)",
        "Une facture par freelance et par période.",
    )

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

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get("name", "New") == "New":
                employee = self.env["hr.employee"].browse(vals.get("employee_id"))
                period_end = vals.get("period_end")
                if isinstance(period_end, str):
                    period_end = fields.Date.from_string(period_end)
                vals["name"] = self._build_reference(employee, period_end)
        return super().create(vals_list)

    @api.model
    def _build_reference(self, employee, period_end):
        slug = re.sub(r"[^A-Z0-9]", "", (employee.name or "FREELANCE").upper())[:12]
        slug = slug or "FREELANCE"
        yyyymm = period_end.strftime("%Y%m") if period_end else fields.Date.today().strftime("%Y%m")
        base = "FACT-%s-%s" % (slug, yyyymm)
        existing = self.search_count([("name", "=", base)])
        if existing:
            seq = self.env["ir.sequence"].next_by_code("pe.freelance.invoice") or "001"
            return "%s-%s" % (base, seq)
        return base

    def action_calculate(self):
        svc = self.env["pe.payroll.service"].sudo()
        for rec in self:
            result = svc.calcul_paie_freelance(
                rec.employee_id.id,
                rec.period_start,
                rec.period_end,
                contract=rec.contrat_id,
            )
            rec.write(
                {
                    "contrat_id": result.get("contract_id"),
                    "heures_loguees": result.get("heures_loguees"),
                    "jours_loguees": result.get("jours_loguees"),
                    "type_facturation": result.get("type_facturation"),
                    "taux_applique": result.get("taux_applique"),
                    "montant_ht": result.get("montant_ht"),
                    "tva": result.get("tva"),
                    "montant_ttc": result.get("montant_ttc"),
                    "primes_challenges": result.get("primes_challenges"),
                    "total_a_payer": result.get("total_a_payer"),
                    "devise": result.get("devise"),
                    "date_emission": result.get("date_emission"),
                    "date_echeance": result.get("date_echeance"),
                    "ice_freelance": result.get("ice_freelance"),
                    "rib_freelance": result.get("rib_freelance"),
                    "rc_freelance": result.get("rc_freelance"),
                    "detail_calcul": result.get("detail_calcul"),
                    "alerte_forfait": result.get("alerte_forfait"),
                    "alerte_heures": result.get("alerte_heures"),
                    "date_calcul": fields.Datetime.now(),
                    "statut": "brouillon",
                }
            )

    def action_issue(self):
        for rec in self:
            if not rec.date_emission:
                rec.date_emission = fields.Date.today()
            if not rec.date_echeance and rec.contrat_id:
                rec.date_echeance = rec.date_emission + datetime.timedelta(
                    days=rec.contrat_id.delai_paiement or 30
                )
            rec.statut = "emise"

    def action_mark_paid(self):
        self.write(
            {
                "statut": "payee",
                "date_paiement_reel": fields.Date.today(),
            }
        )

    def action_print_invoice(self):
        self.ensure_one()
        return self.env.ref(
            "people_engine.action_report_pe_freelance_invoice"
        ).report_action(self)

    @api.model
    def generer_factures_periode_courante(self):
        """Cron : génère/recalcule les factures freelance de la période en cours."""
        svc = self.env["pe.payroll.service"].sudo()
        Contract = self.env["pe.employment.contract"].sudo()
        period = svc.get_payroll_period()
        contracts = Contract.search(
            [
                ("contract_type", "=", "freelance"),
                ("statut", "=", "active"),
                ("date_start", "<=", period["period_end"]),
                "|",
                ("date_end", "=", False),
                ("date_end", ">=", period["period_start"]),
            ]
        )
        for contract in contracts:
            invoice = self.search(
                [
                    ("employee_id", "=", contract.employee_id.id),
                    ("period_start", "=", period["period_start"]),
                    ("period_end", "=", period["period_end"]),
                ],
                limit=1,
            )
            if not invoice:
                invoice = self.create(
                    {
                        "employee_id": contract.employee_id.id,
                        "contrat_id": contract.id,
                        "period_start": period["period_start"],
                        "period_end": period["period_end"],
                    }
                )
            invoice.action_calculate()
        return True

    @api.model
    def cron_check_freelance_alerts(self):
        """Alertes : factures en retard, heures non loguées, forfait incomplet."""
        today = fields.Date.today()
        overdue = self.search(
            [
                ("statut", "in", ("emise", "en_retard")),
                ("date_echeance", "<", today),
            ]
        )
        for inv in overdue:
            if inv.statut != "en_retard":
                inv.statut = "en_retard"
            inv.message_post(
                body="⚠️ Facture en retard — échéance %s dépassée."
                % inv.date_echeance
            )

        svc = self.env["pe.payroll.service"].sudo()
        period = svc.get_payroll_period()
        if today == period["period_end"]:
            zero_hours = self.search(
                [
                    ("period_start", "=", period["period_start"]),
                    ("period_end", "=", period["period_end"]),
                    ("heures_loguees", "<=", 0),
                    ("statut", "=", "brouillon"),
                ]
            )
            for inv in zero_hours:
                inv.alerte_heures = True
                inv.message_post(
                    body="⚠️ Fin de période : aucune heure loguée pour cette facture."
                )

        forfait_incomplete = self.search(
            [
                ("alerte_forfait", "=", True),
                ("statut", "=", "brouillon"),
            ]
        )
        for inv in forfait_incomplete:
            inv.message_post(
                body="⚠️ Forfait incomplet : heures minimum non atteintes avant facturation."
            )
        return True

    @api.model
    def action_open_current_period(self):
        svc = self.env["pe.payroll.service"].sudo()
        period = svc.get_payroll_period()
        return {
            "type": "ir.actions.act_window",
            "name": "Factures freelance — %s" % period["label"],
            "res_model": "pe.freelance.invoice",
            "view_mode": "list,form",
            "domain": [
                ("period_start", "=", period["period_start"]),
                ("period_end", "=", period["period_end"]),
            ],
            "context": {
                "default_period_start": period["period_start"],
                "default_period_end": period["period_end"],
            },
        }

    @api.model
    def get_payroll_document_type(self, employee_id, ref_date=None):
        """CDD/CDI → bulletin ; freelance → facture."""
        svc = self.env["pe.payroll.service"].sudo()
        contract = svc.get_active_contract(employee_id, ref_date)
        if contract and contract.contract_type == "freelance":
            return "freelance_invoice"
        return "payroll_bulletin"
