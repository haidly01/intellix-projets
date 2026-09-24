# -*- coding: utf-8 -*-
from odoo import _, api, fields, models
from odoo.exceptions import UserError


class HrPayslipMa(models.Model):
    _name = "hr.payslip.ma"
    _description = "Bulletin de paie Maroc"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "period_end desc, employee_id"

    name = fields.Char(
        string="Référence",
        required=True,
        copy=False,
        default=lambda self: self.env["ir.sequence"].next_by_code("hr.payslip.ma")
        or "BUL-MA",
    )
    employee_id = fields.Many2one(
        "hr.employee",
        string="Employé",
        required=True,
        index=True,
        tracking=True,
    )
    company_id = fields.Many2one(
        "res.company",
        string="Société",
        required=True,
        default=lambda self: self.env.company,
        tracking=True,
    )
    contract_id = fields.Many2one(
        "pe.employment.contract",
        string="Contrat IntelliX",
    )
    structure_id = fields.Many2one(
        "hr.payroll.structure.ma",
        string="Structure",
        required=True,
        domain="[('company_id', '=', company_id)]",
    )
    period_start = fields.Date(string="Début période", required=True, index=True)
    period_end = fields.Date(string="Fin période", required=True, index=True)
    period_label = fields.Char(compute="_compute_period_label", store=True)
    state = fields.Selection(
        [
            ("draft", "Brouillon"),
            ("validated", "Validé"),
            ("paid", "Payé"),
            ("cancelled", "Annulé"),
        ],
        default="draft",
        tracking=True,
    )
    gross_salary = fields.Float(string="Salaire brut", tracking=True)
    net_salary = fields.Float(string="Net à payer", tracking=True)
    total_employee_deductions = fields.Float(
        string="Total retenues salariales",
        compute="_compute_totals",
        store=True,
    )
    total_employer_charges = fields.Float(
        string="Total charges patronales",
        compute="_compute_totals",
        store=True,
    )
    line_ids = fields.One2many(
        "hr.payslip.line.ma",
        "payslip_id",
        string="Lignes",
    )
    move_id = fields.Many2one(
        "account.move",
        string="Écriture comptable",
        readonly=True,
        copy=False,
    )
    note = fields.Text(string="Note")
    cnss_number = fields.Char(related="employee_id.x_cnss_number", readonly=True)
    cin_number = fields.Char(related="employee_id.x_cin_number", readonly=True)

    _employee_period_unique = models.Constraint(
        "unique(employee_id, period_start, period_end, company_id)",
        "Un bulletin par employé et par période.",
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

    @api.depends("line_ids.amount", "line_ids.employer_amount", "line_ids.category")
    def _compute_totals(self):
        for rec in self:
            rec.total_employee_deductions = sum(
                rec.line_ids.filtered(
                    lambda l: l.category == "retenue_salariale"
                ).mapped("amount")
            )
            rec.total_employer_charges = sum(
                rec.line_ids.filtered(
                    lambda l: l.category == "charge_patronale"
                ).mapped("employer_amount")
            )

    @api.onchange("employee_id")
    def _onchange_employee_id(self):
        if self.employee_id:
            self.company_id = self.employee_id.company_id
            contract = self.env["pe.employment.contract"].search(
                [
                    ("employee_id", "=", self.employee_id.id),
                    ("statut", "=", "active"),
                ],
                order="date_start desc",
                limit=1,
            )
            if contract:
                self.contract_id = contract
                if contract.salaire_base and not self.gross_salary:
                    self.gross_salary = contract.salaire_base
            structure = self.env["hr.payroll.structure.ma"].search(
                [
                    ("company_id", "=", self.company_id.id),
                    ("active", "=", True),
                ],
                limit=1,
            )
            if structure:
                self.structure_id = structure

    def action_compute(self):
        engine = self.env["payroll.engine.ma"].sudo()
        for rec in self:
            if rec.state != "draft":
                raise UserError(_("Seuls les bulletins brouillon peuvent être recalculés."))
            if not rec.gross_salary:
                raise UserError(_("Indiquez le salaire brut avant le calcul."))
            result = engine.compute_payslip(rec)
            rec.line_ids.unlink()
            rec.write(
                {
                    "line_ids": [(0, 0, line) for line in result["lines"]],
                    "net_salary": result["net_salary"],
                }
            )
        return True

    def action_validate(self):
        for rec in self:
            if rec.state != "draft":
                raise UserError(_("Ce bulletin est déjà validé ou annulé."))
            if not rec.line_ids:
                rec.action_compute()
            rec._create_account_move()
            rec.state = "validated"
        return True

    def action_mark_paid(self):
        self.filtered(lambda p: p.state == "validated").write({"state": "paid"})
        return True

    def action_cancel(self):
        for rec in self:
            if rec.move_id and rec.move_id.state == "posted":
                raise UserError(
                    _("Annulez ou reversez l'écriture comptable %s avant d'annuler le bulletin.")
                    % rec.move_id.name
                )
            if rec.move_id:
                rec.move_id.button_cancel()
            rec.write({"state": "cancelled", "move_id": False})
        return True

    def action_draft(self):
        self.write({"state": "draft"})
        return True

    def action_print_payslip(self):
        self.ensure_one()
        return self.env.ref(
            "intellix_hr_payroll_ma.action_report_hr_payslip_ma"
        ).report_action(self)

    def _create_account_move(self):
        self.ensure_one()
        company = self.company_id
        company._ensure_payroll_ma_accounts()
        journal = company.x_payroll_ma_journal_id
        if not journal:
            raise UserError(_("Journal « Paie MA » introuvable pour %s.") % company.name)

        move_lines = []
        for line in self.line_ids:
            amount = abs(line.amount) + abs(line.employer_amount)
            if amount <= 0:
                continue
            rule = line.rule_id
            if line.category == "gain" and line.code == "BASIC":
                debit_acc = rule.account_debit_id or company.get_payroll_ma_account("61711")
                credit_acc = rule.account_credit_id or company.get_payroll_ma_account("4432")
                move_lines.append(
                    self._prepare_move_line(debit_acc, amount, 0, line.name)
                )
                move_lines.append(
                    self._prepare_move_line(credit_acc, 0, amount, line.name)
                )
            elif line.category == "retenue_salariale" and line.amount:
                debit_acc = rule.account_debit_id or company.get_payroll_ma_account("4432")
                credit_acc = rule.account_credit_id or company.get_payroll_ma_account(
                    "4433" if line.code != "IR" else "4452"
                )
                move_lines.append(
                    self._prepare_move_line(debit_acc, line.amount, 0, line.name)
                )
                move_lines.append(
                    self._prepare_move_line(credit_acc, 0, line.amount, line.name)
                )
            elif line.category == "charge_patronale" and line.employer_amount:
                debit_acc = rule.account_debit_id or company.get_payroll_ma_account("61741")
                credit_acc = rule.account_credit_id or company.get_payroll_ma_account("4433")
                move_lines.append(
                    self._prepare_move_line(
                        debit_acc, line.employer_amount, 0, line.name
                    )
                )
                move_lines.append(
                    self._prepare_move_line(
                        credit_acc, 0, line.employer_amount, line.name
                    )
                )

        if not move_lines:
            return

        move = self.env["account.move"].create(
            {
                "journal_id": journal.id,
                "date": self.period_end,
                "ref": self.name,
                "company_id": company.id,
                "line_ids": move_lines,
            }
        )
        move.action_post()
        self.move_id = move.id

    def _prepare_move_line(self, account, debit, credit, label):
        return (
            0,
            0,
            {
                "name": label,
                "account_id": account.id,
                "debit": debit,
                "credit": credit,
            },
        )

    @api.model
    def create_from_contract(self, contract, period_start=None, period_end=None):
        """Crée un bulletin brouillon depuis un contrat pe.employment.contract."""
        svc = self.env["pe.payroll.service"].sudo()
        period = svc.get_payroll_period(period_end or fields.Date.today())
        start = period_start or period["period_start"]
        end = period_end or period["period_end"]
        company = contract.employee_id.company_id
        structure = self.env["hr.payroll.structure.ma"].search(
            [("company_id", "=", company.id), ("active", "=", True)],
            limit=1,
        )
        if not structure:
            raise UserError(
                _("Aucune structure de paie Maroc pour %s.") % company.name
            )
        existing = self.search(
            [
                ("employee_id", "=", contract.employee_id.id),
                ("period_start", "=", start),
                ("period_end", "=", end),
                ("company_id", "=", company.id),
            ],
            limit=1,
        )
        if existing:
            return existing
        payslip = self.create(
            {
                "employee_id": contract.employee_id.id,
                "company_id": company.id,
                "contract_id": contract.id,
                "structure_id": structure.id,
                "period_start": start,
                "period_end": end,
                "gross_salary": contract.salaire_base,
            }
        )
        payslip.action_compute()
        return payslip
