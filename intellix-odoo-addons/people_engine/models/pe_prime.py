# -*- coding: utf-8 -*-
from odoo import _, api, fields, models
from odoo.exceptions import UserError


class PeopleEnginePrime(models.Model):
    _name = "pe.prime"
    _description = "Prime de performance People Engine"
    _inherit = ["mail.thread"]
    _order = "create_date desc"

    name = fields.Char(compute="_compute_name", store=True)
    profile_id = fields.Many2one(
        "pe.employee.profile", required=True, ondelete="cascade", index=True
    )
    employee_id = fields.Many2one(related="profile_id.employee_id", store=True)
    rule_id = fields.Many2one("pe.prime.rule", required=True, ondelete="restrict")
    amount_proposed = fields.Float()
    amount_approved = fields.Float()
    currency_id = fields.Many2one(
        "res.currency",
        default=lambda self: self.env.company.currency_id,
    )
    period_start = fields.Date(required=True)
    period_end = fields.Date(required=True)
    trigger_score = fields.Float()
    trigger_details = fields.Text()
    manager_id = fields.Many2one("hr.employee")
    manager_approved = fields.Boolean(default=False)
    manager_date = fields.Datetime()
    manager_comments = fields.Text()
    hr_reviewer_id = fields.Many2one("hr.employee")
    hr_approved = fields.Boolean(default=False)
    hr_date = fields.Datetime()
    hr_comments = fields.Text()
    dg_approver_id = fields.Many2one("hr.employee")
    dg_approved = fields.Boolean(default=False)
    dg_date = fields.Datetime()
    dg_comments = fields.Text()
    dg_amount_override = fields.Float()
    accounting_reviewer_id = fields.Many2one("res.users")
    accounting_approved = fields.Boolean(default=False)
    accounting_date = fields.Datetime()
    move_id = fields.Many2one("account.move", string="Pièce comptable", readonly=True)
    status = fields.Selection(
        [
            ("draft", "Proposée"),
            ("pending_manager", "Manager"),
            ("pending_hr", "RH"),
            ("pending_dg", "DG"),
            ("pending_accounting", "Comptabilité"),
            ("approved", "Approuvée"),
            ("paid", "Versée"),
            ("rejected", "Refusée"),
            ("cancelled", "Annulée"),
        ],
        default="draft",
        tracking=True,
    )
    employee_notified = fields.Boolean(default=False)
    employee_notified_date = fields.Datetime()

    @api.depends("employee_id", "rule_id", "period_end")
    def _compute_name(self):
        for rec in self:
            rec.name = _("Prime %s — %s") % (
                rec.rule_id.name or "",
                rec.employee_id.name or "",
            )

    def action_submit_manager(self):
        self.write({"status": "pending_manager"})

    def action_manager_approve(self):
        for prime in self:
            prime.write(
                {
                    "manager_approved": True,
                    "manager_date": fields.Datetime.now(),
                    "manager_id": self.env.user.employee_id.id,
                    "status": "pending_hr" if prime.rule_id.requires_hr else "pending_dg",
                }
            )

    def action_hr_approve(self):
        if not self.env.user.has_group("people_engine.group_hr"):
            raise UserError(_("Approbation RH requise."))
        for prime in self:
            prime.write(
                {
                    "hr_approved": True,
                    "hr_date": fields.Datetime.now(),
                    "hr_reviewer_id": self.env.user.employee_id.id,
                    "status": "pending_dg",
                }
            )

    def action_dg_approve(self):
        for prime in self:
            amount = prime.dg_amount_override or prime.amount_proposed
            prime.write(
                {
                    "dg_approved": True,
                    "dg_date": fields.Datetime.now(),
                    "amount_approved": amount,
                    "status": "pending_accounting",
                }
            )

    def action_accounting_approve_and_post(self):
        engine = self.env["pe.prime.engine"]
        for prime in self:
            if prime.status != "pending_accounting":
                raise UserError(_("Statut comptabilité requis."))
            engine.create_accounting_entry(prime)
            prime.write(
                {
                    "accounting_reviewer_id": self.env.user.id,
                    "status": "approved",
                }
            )

    def action_reject(self):
        self.write({"status": "rejected"})

    def action_cancel(self):
        self.write({"status": "cancelled"})
