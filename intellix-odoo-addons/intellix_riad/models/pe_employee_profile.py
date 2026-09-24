# -*- coding: utf-8 -*-

from odoo import api, fields, models
from odoo.exceptions import UserError

RIAD_ROLES = [
    ("reception", "Réception"),
    ("menage", "Ménage"),
    ("cuisine", "Cuisine"),
    ("wellness", "Bien-être / beauté"),
    ("restaurant", "Service restaurant"),
]


class PeEmployeeProfileRiad(models.Model):
    _inherit = "pe.employee.profile"

    riad_establishment_id = fields.Many2one(
        "intellix.riad.establishment",
        string="Établissement hébergement",
        ondelete="set null",
        index=True,
    )
    riad_role = fields.Selection(RIAD_ROLES, string="Poste (principal)")
    riad_role_ids = fields.Many2many(
        "intellix.riad.staff.role",
        "intellix_riad_profile_role_rel",
        "profile_id",
        "role_id",
        string="Rôles",
        help="Plusieurs rôles possibles (ex. massage + esthétique + ménage).",
    )
    riad_phone = fields.Char(string="Téléphone")
    riad_hire_date = fields.Date(string="Date d'entrée en poste")
    riad_photo = fields.Image(string="Photo", max_width=512, max_height=512)
    riad_wage = fields.Monetary(
        string="Salaire de base",
        currency_field="riad_wage_currency_id",
        help="Montant transmis dans le rapport mensuel comptable.",
    )
    riad_wage_currency_id = fields.Many2one(
        related="riad_establishment_id.property_id.currency_id",
        readonly=True,
    )
    riad_in_payroll = fields.Boolean(
        string="Inclus dans le rapport mensuel",
        default=True,
    )
    riad_practitioner_id = fields.Many2one(
        "intellix.riad.practitioner",
        string="Fiche prestataire bien-être",
        ondelete="set null",
    )
    riad_expected_start = fields.Float(
        string="Heure d'arrivée prévue",
        default=9.0,
        help="Référence pour calculer les minutes de retard à partir de l'heure saisie par la gérante.",
    )
    riad_late_arrival = fields.Float(
        string="Heure d'arrivée (saisie gérante)",
        store=False,
        help="À remplir avant de pointer un retard. Aucune heure n'est capturée automatiquement.",
    )
    riad_new_employee_name = fields.Char(
        string="Nom (nouvelle fiche)",
        store=False,
        help="Si aucun employé n'existe encore, une fiche hr.employee est créée.",
    )
    riad_today_status = fields.Char(
        string="Statut du jour",
        compute="_compute_riad_today_status",
    )
    company_id = fields.Many2one(
        "res.company",
        string="Société",
        related="riad_establishment_id.company_id",
        store=True,
        readonly=True,
    )
    employee_company_id = fields.Many2one(
        related="employee_id.company_id",
        string="Société employé",
        readonly=True,
    )
    work_email = fields.Char(
        related="employee_id.work_email",
        string="Email professionnel",
        readonly=False,
    )
    work_phone = fields.Char(
        related="employee_id.work_phone",
        string="Téléphone professionnel",
        readonly=False,
    )

    def _sync_riad_summaries_establishment(self):
        Summary = self.env["pe.presence.summary"]
        Log = self.env["pe.presence.log"]
        Absence = self.env["pe.absence.detected"]
        for rec in self:
            if not rec.employee_id:
                continue
            summaries = Summary.search([("employee_id", "=", rec.employee_id.id)])
            if summaries:
                summaries._compute_riad_establishment_id()
            logs = Log.search([("employee_id", "=", rec.employee_id.id)])
            if logs:
                logs._compute_riad_establishment_id()
            absences = Absence.search([("employee_id", "=", rec.employee_id.id)])
            if absences:
                absences._compute_riad_establishment_id()

    def _sync_employee_riad_company(self):
        for rec in self.filtered("employee_id"):
            estab = rec.riad_establishment_id
            vals = {}
            if estab:
                vals["riad_establishment_id"] = estab.id
                if estab.company_id:
                    vals["company_id"] = estab.company_id.id
            if vals:
                rec.employee_id.sudo().write(vals)

    def _sync_primary_role(self):
        for rec in self:
            first = rec.riad_role_ids.sorted("sequence")[:1]
            if first and first.legacy_role:
                rec.riad_role = first.legacy_role

    def riad_role_label(self):
        self.ensure_one()
        names = self.riad_role_ids.sorted("sequence").mapped("name")
        if names:
            return " · ".join(names)
        return dict(self._fields["riad_role"].selection).get(self.riad_role) or "—"

    def _employee_vals_from_riad(self, vals, name=None, establishment=None):
        emp_vals = {}
        if name:
            emp_vals["name"] = name
        if vals.get("riad_phone"):
            emp_vals["mobile_phone"] = vals["riad_phone"]
        if vals.get("work_email"):
            emp_vals["work_email"] = vals["work_email"]
        if vals.get("work_phone"):
            emp_vals["work_phone"] = vals["work_phone"]
        if vals.get("riad_photo") and "image_1920" in self.env["hr.employee"]._fields:
            emp_vals["image_1920"] = vals["riad_photo"]
        estab = establishment
        if not estab and vals.get("riad_establishment_id"):
            estab = self.env["intellix.riad.establishment"].browse(
                vals["riad_establishment_id"]
            )
        if estab and not estab.company_id:
            estab.sudo()._ensure_anna_sweety_company()
            estab.invalidate_recordset(["company_id"])
        if estab:
            emp_vals["riad_establishment_id"] = estab.id
            if estab.company_id:
                emp_vals["company_id"] = estab.company_id.id
        return emp_vals

    def _sync_wellness_practitioner(self):
        Type = self.env["intellix.riad.wellness.type"]
        Pract = self.env["intellix.riad.practitioner"]
        for rec in self:
            if not rec.riad_establishment_id:
                continue
            codes = [
                code
                for code in rec.riad_role_ids.mapped("wellness_type_code")
                if code
            ]
            types = Type.search([("code", "in", codes)]) if codes else Type.browse()
            pract = rec.riad_practitioner_id or Pract.search(
                [("pe_profile_id", "=", rec.id)], limit=1
            )
            name = rec.display_name or rec.employee_id.name or rec.riad_new_employee_name
            if types:
                payload = {
                    "establishment_id": rec.riad_establishment_id.id,
                    "name": name or "Prestataire",
                    "type_ids": [(6, 0, types.ids)],
                    "pe_profile_id": rec.id,
                    "kind": "staff",
                    "active": True,
                }
                if pract:
                    pract.write(payload)
                else:
                    pract = Pract.create(payload)
                rec.riad_practitioner_id = pract.id
            elif pract:
                pract.active = False

    @api.model_create_multi
    def create(self, vals_list):
        Employee = self.env["hr.employee"].sudo()
        for vals in vals_list:
            name = (vals.pop("riad_new_employee_name", None) or "").strip()
            if not vals.get("employee_id") and name:
                employee = Employee.with_context(riad_creating_staff=True).create(
                    self._employee_vals_from_riad(vals, name)
                )
                vals["employee_id"] = employee.id
            elif not vals.get("employee_id") and vals.get("riad_establishment_id"):
                raise UserError(
                    "Indiquez un employé existant ou saisissez un nom pour créer la fiche."
                )
            elif vals.get("employee_id"):
                extra = self._employee_vals_from_riad(vals)
                extra.pop("name", None)
                if extra:
                    Employee.browse(vals["employee_id"]).write(extra)
        records = super().create(vals_list)
        records.filtered("riad_establishment_id")._sync_riad_summaries_establishment()
        records._sync_primary_role()
        records._sync_wellness_practitioner()
        records._sync_employee_riad_company()
        return records

    def write(self, vals):
        name = vals.pop("riad_new_employee_name", None)
        res = super().write(vals)
        if "riad_establishment_id" in vals:
            self._sync_riad_summaries_establishment()
            self._sync_employee_riad_company()
        extra = self._employee_vals_from_riad(vals, (name or "").strip() or None)
        extra.pop("name", None)
        if extra:
            for rec in self.filtered("employee_id"):
                rec.employee_id.sudo().write(extra)
        if "riad_role_ids" in vals:
            self._sync_primary_role()
        if any(
            key in vals
            for key in (
                "riad_role_ids",
                "riad_establishment_id",
                "riad_new_employee_name",
            )
        ):
            self._sync_wellness_practitioner()
        return res

    @api.model
    def riad_migrate_legacy_roles(self):
        Role = self.env["intellix.riad.staff.role"]
        by_legacy = {
            role.legacy_role: role
            for role in Role.search([("legacy_role", "!=", False)])
        }
        orphans = self.search(
            [
                ("riad_establishment_id", "!=", False),
                ("riad_role_ids", "=", False),
                ("riad_role", "!=", False),
            ]
        )
        for rec in orphans:
            role = by_legacy.get(rec.riad_role)
            if role:
                rec.riad_role_ids = [(4, role.id)]
        return True

    def _compute_riad_today_status(self):
        today = fields.Date.context_today(self)
        summaries = self.env["pe.presence.summary"].search(
            [
                ("employee_id", "in", self.mapped("employee_id").ids),
                ("date", "=", today),
            ]
        )
        by_emp = {row.employee_id.id: row for row in summaries}
        for rec in self:
            row = by_emp.get(rec.employee_id.id)
            rec.riad_today_status = row.riad_status_label() if row else "Non pointé"

    def _arrival_from_float(self, value):
        hours = int(value or 0)
        minutes = int(round(((value or 0) % 1) * 60))
        if minutes >= 60:
            hours += 1
            minutes = 0
        return "%02d:%02d" % (hours, minutes)

    def riad_punch(self, kind, arrival=None, note=None, day=None):
        """Pointage manuel par la gérante — la donnée saisie fait foi."""
        self.ensure_one()
        if not self.employee_id:
            raise UserError("Cette fiche n'est pas liée à un employé.")
        if kind == "late" and not arrival and self.riad_late_arrival:
            arrival = self._arrival_from_float(self.riad_late_arrival)
        return self.env["pe.presence.summary"].riad_upsert_punch(
            self.employee_id,
            kind,
            arrival=arrival,
            note=note,
            expected_start=self.riad_expected_start,
            day=day,
        )

    def action_riad_punch_present(self):
        for rec in self:
            rec.riad_punch("present")
        return True

    def action_riad_punch_late(self):
        for rec in self:
            rec.riad_punch("late")
        return True

    def action_riad_punch_leave(self):
        for rec in self:
            rec.riad_punch("leave")
        return True

    def action_riad_punch_illness(self):
        for rec in self:
            rec.riad_punch("illness")
        return True

    def action_riad_punch_unjustified(self):
        for rec in self:
            rec.riad_punch("unjustified")
        return True
