# -*- coding: utf-8 -*-
from datetime import timedelta

from odoo import _, api, fields, models
from odoo.exceptions import ValidationError

from odoo.addons.intellix_hr_dossier.utils.num_helpers import amount_to_words_fr

_MEDICAL_FIELDS = frozenset({
    "x_blood_type",
    "x_medical_conditions",
    "x_last_medical_visit_date",
    "x_next_medical_visit_date",
})


class HrEmployee(models.Model):
    _inherit = "hr.employee"

    # --- 2.1 Identité & état civil ---
    x_cin_number = fields.Char(
        string="Numéro CIN",
        groups="hr.group_hr_user",
        tracking=True,
    )
    x_cin_expiry_date = fields.Date(
        string="Date d'expiration CIN",
        groups="hr.group_hr_user",
        tracking=True,
    )
    x_birth_place = fields.Char(
        string="Lieu de naissance",
        groups="hr.group_hr_user",
        tracking=True,
    )

    # --- 2.2 Résidence ---
    x_residence_neighborhood = fields.Char(
        string="Quartier / secteur",
        groups="hr.group_hr_user",
        tracking=True,
    )
    x_emergency_contact_name = fields.Char(
        string="Contact d'urgence — Nom",
        groups="hr.group_hr_user",
        tracking=True,
    )
    x_emergency_contact_relation = fields.Char(
        string="Contact d'urgence — Lien",
        groups="hr.group_hr_user",
        tracking=True,
    )
    x_emergency_contact_phone = fields.Char(
        string="Contact d'urgence — Téléphone",
        groups="hr.group_hr_user",
        tracking=True,
    )

    # --- 2.3 CNSS ---
    x_cnss_number = fields.Char(
        string="N° CNSS",
        groups="hr.group_hr_user",
        tracking=True,
    )
    x_cnss_affiliation_date = fields.Date(
        string="Date d'affiliation CNSS",
        groups="hr.group_hr_user",
        tracking=True,
    )
    x_mutuelle_provider = fields.Char(
        string="Mutuelle",
        groups="hr.group_hr_user",
        tracking=True,
    )
    x_mutuelle_contract_number = fields.Char(
        string="N° contrat mutuelle",
        groups="hr.group_hr_user",
        tracking=True,
    )
    x_cimr_number = fields.Char(
        string="N° CIMR",
        groups="hr.group_hr_user",
        tracking=True,
    )
    x_cimr_rate = fields.Float(
        string="Taux CIMR salarié (%)",
        groups="hr.group_hr_user",
        tracking=True,
        help="Taux de cotisation CIMR part salariale (indicatif, configurable par employé).",
    )
    x_cimr_employer_rate = fields.Float(
        string="Taux CIMR employeur (%)",
        groups="hr.group_hr_user",
        tracking=True,
        help="Taux de cotisation CIMR part patronale (optionnel).",
    )

    # --- 2.4 Medical (restricted) ---
    x_blood_type = fields.Selection(
        selection=[
            ("A+", "A+"),
            ("A-", "A-"),
            ("B+", "B+"),
            ("B-", "B-"),
            ("AB+", "AB+"),
            ("AB-", "AB-"),
            ("O+", "O+"),
            ("O-", "O-"),
        ],
        string="Groupe sanguin",
        groups="intellix_hr_dossier.group_medical_data",
        tracking=True,
    )
    x_medical_conditions = fields.Text(
        string="Antécédents / conditions médicales",
        groups="intellix_hr_dossier.group_medical_data",
        tracking=True,
    )
    x_last_medical_visit_date = fields.Date(
        string="Dernière visite médicale",
        groups="intellix_hr_dossier.group_medical_data",
        tracking=True,
    )
    x_next_medical_visit_date = fields.Date(
        string="Prochaine visite médicale",
        groups="intellix_hr_dossier.group_medical_data",
        tracking=True,
    )

    internship_ids = fields.One2many(
        "hr.internship",
        "employee_id",
        string="Stages",
        groups="hr.group_hr_user",
    )
    internship_count = fields.Integer(
        compute="_compute_internship_count",
        groups="hr.group_hr_user",
    )

    @api.depends("internship_ids")
    def _compute_internship_count(self):
        for emp in self:
            emp.internship_count = len(emp.internship_ids)

    @api.constrains("x_cnss_number")
    def _check_cnss_number(self):
        for emp in self:
            if not emp.x_cnss_number:
                continue
            digits = emp.x_cnss_number.replace(" ", "")
            if not digits.isdigit() or len(digits) not in (8, 9):
                raise ValidationError(
                    _("Le numéro CNSS doit comporter 8 ou 9 chiffres.")
                )

    def _has_medical_access(self):
        return self.env.user.has_group(
            "intellix_hr_dossier.group_medical_data"
        )

    @api.model
    def fields_get(self, allfields=None, attributes=None):
        res = super().fields_get(allfields=allfields, attributes=attributes)
        if not self._has_medical_access():
            for fname in _MEDICAL_FIELDS:
                res.pop(fname, None)
        return res

    def read(self, fields=None, load="_classic_read"):
        if fields is None:
            return super().read(fields=fields, load=load)
        if not self._has_medical_access():
            fields = [f for f in fields if f not in _MEDICAL_FIELDS]
            if not fields:
                return [{} for _ in self]
        return super().read(fields=fields, load=load)

    def _get_attestation_company(self):
        self.ensure_one()
        return self.company_id or self.env.company

    def _get_attestation_signatory(self, wizard=None):
        company = self._get_attestation_company()
        name = (wizard and wizard.signatory_name) or company.x_hr_signatory_name
        title = (wizard and wizard.signatory_title) or company.x_hr_signatory_title
        city = (wizard and wizard.city) or company.x_attestation_city or company.city
        return {"name": name or "", "title": title or "", "city": city or ""}

    def _get_current_wage(self):
        self.ensure_one()
        wage = self.wage or self.contract_wage or 0.0
        return wage

    def get_wage_in_words(self):
        self.ensure_one()
        currency = self.currency_id.name if self.currency_id else "MAD"
        return amount_to_words_fr(self._get_current_wage(), currency)

    def _get_active_internship(self, internship_id=None):
        self.ensure_one()
        Internship = self.env["hr.internship"]
        if internship_id:
            internship = Internship.browse(internship_id)
            if internship.employee_id == self:
                return internship
        return Internship.search(
            [("employee_id", "=", self.id), ("active", "=", True)],
            order="date_start desc",
            limit=1,
        )

    def action_open_internships(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": _("Stages"),
            "res_model": "hr.internship",
            "view_mode": "list,form",
            "domain": [("employee_id", "=", self.id)],
            "context": {"default_employee_id": self.id},
        }

    def action_open_attestation_wizard(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": _("Attestation / certificat"),
            "res_model": "intellix_hr_dossier.attestation.wizard",
            "view_mode": "form",
            "target": "new",
            "context": {"default_employee_id": self.id},
        }

    @api.model
    def _cron_notify_cin_expiry(self):
        """Alerte hebdomadaire : CIN expirant dans les 90 prochains jours."""
        today = fields.Date.context_today(self)
        deadline = today + timedelta(days=90)
        employees = self.search([
            ("x_cin_expiry_date", "!=", False),
            ("x_cin_expiry_date", "<=", deadline),
            ("x_cin_expiry_date", ">=", today),
            ("active", "=", True),
        ])
        if not employees:
            return
        hr_users = self.env.ref("hr.group_hr_user").users.filtered(
            lambda u: u.active
        )
        for emp in employees:
            days_left = (emp.x_cin_expiry_date - today).days
            body = _(
                "La CIN de %(name)s (n° %(cin)s) expire le %(date)s "
                "(%(days)s jours restants).",
                name=emp.name,
                cin=emp.x_cin_number or "—",
                date=emp.x_cin_expiry_date,
                days=days_left,
            )
            emp.message_post(body=body, message_type="notification")
            if emp.user_id:
                emp.user_id.partner_id.message_post(
                    body=_(
                        "Votre CIN expire le %(date)s. "
                        "Merci de transmettre le renouvellement aux RH.",
                        date=emp.x_cin_expiry_date,
                    ),
                    message_type="notification",
                )
            for user in hr_users:
                if user.partner_id:
                    user.partner_id.message_post(
                        body=body,
                        message_type="notification",
                    )
