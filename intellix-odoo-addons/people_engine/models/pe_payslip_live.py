# -*- coding: utf-8 -*-
import datetime

from odoo import api, fields, models


class PePayslipLive(models.Model):
    _name = "pe.payslip.live"
    _description = "Fiche de paie temps réel"
    _order = "mois desc, employee_id"

    employee_id = fields.Many2one("hr.employee", required=True, index=True)
    profile_id = fields.Many2one(
        "pe.employee.profile",
        compute="_compute_profile",
        store=True,
    )
    mois = fields.Char(string="Mois", required=True, index=True)
    date_calcul = fields.Datetime(string="Dernier calcul", readonly=True)
    salaire_base = fields.Float(string="Salaire / honoraire base")
    devise_base = fields.Selection(
        [("MAD", "MAD"), ("EUR", "EUR"), ("CAD", "CAD")],
        default="MAD",
    )
    prime_plateau = fields.Float(string="Prime plateau leads")
    prime_upsell = fields.Float(string="Prime upsell")
    prime_conversion = fields.Float(string="Prime conversion IA")
    prime_presence = fields.Float(string="Bonus présence")
    prime_coaching = fields.Float(string="Bonus coaching validé")
    deduction_absences = fields.Float(string="Déductions absences")
    total_brut = fields.Float(compute="_compute_total", store=True)
    total_net_estime = fields.Float(compute="_compute_total", store=True)
    detail_calcul = fields.Text(string="Détail du calcul", readonly=True)
    leads_confirmes_mois = fields.Integer(string="Leads confirmés ce mois")
    leads_upsell_mois = fields.Integer(string="Leads upsell ce mois")
    taux_conversion_ia_mois = fields.Float(string="Taux conversion IA (%)")
    heures_reelles_mois = fields.Float(string="Heures réelles travaillées")
    jours_absents_mois = fields.Float(string="Jours absents")
    blocs_primes = fields.Integer(string="Blocs primes plateau")

    _employee_mois_unique = models.Constraint(
        "unique(employee_id, mois)",
        "Une seule fiche paie temps réel par employé et par mois.",
    )

    @api.depends("employee_id")
    def _compute_profile(self):
        Profile = self.env["pe.employee.profile"]
        for rec in self:
            rec.profile_id = (
                Profile.search([("employee_id", "=", rec.employee_id.id)], limit=1).id
                if rec.employee_id
                else False
            )

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
        for rec in self:
            rec.total_brut = (
                rec.salaire_base
                + rec.prime_plateau
                + rec.prime_upsell
                + rec.prime_conversion
                + rec.prime_presence
                + rec.prime_coaching
                - rec.deduction_absences
            )
            rec.total_net_estime = rec.total_brut * 0.85

    @api.model
    def recalculer_tous(self):
        today = datetime.date.today()
        mois = today.strftime("%Y-%m")
        debut = today.replace(day=1)
        fin = today
        for emp in self.env["hr.employee"].search([("active", "=", True)]):
            self._recalculer_employe(emp, mois, debut, fin)

    def _recalculer_employe(self, employee, mois, debut, fin):
        payslip = self.search(
            [("employee_id", "=", employee.id), ("mois", "=", mois)],
            limit=1,
        )
        profile = self.env["pe.employee.profile"].search(
            [("employee_id", "=", employee.id)], limit=1
        )
        if not payslip:
            payslip = self.create(
                {
                    "employee_id": employee.id,
                    "mois": mois,
                    "salaire_base": profile.salaire_base if profile else 0.0,
                    "devise_base": profile.devise_remuneration
                    if profile
                    else "MAD",
                }
            )
        dept = self.env["pe.department"].search(
            [("employee_ids", "in", [employee.id])], limit=1
        )
        if not dept and profile and profile.department_pe_id:
            dept = profile.department_pe_id

        details = []
        prime_plateau = prime_upsell = prime_conversion = 0.0
        blocs = 0
        if dept:
            for config in dept.prime_config_ids.filtered("actif"):
                result = config.calculer_prime_employe(employee.id, debut, fin)
                if config.type_prime == "plateau_leads":
                    prime_plateau = result.get("montant", 0.0)
                    blocs = result.get("blocs", 0)
                    details.append("Plateau: %s" % result.get("detail"))
                elif config.type_prime == "upsell_lead":
                    prime_upsell = result.get("montant", 0.0)
                    details.append("Upsell: %s" % result.get("detail"))
                elif config.type_prime == "conversion_ia":
                    prime_conversion = result.get("montant", 0.0)
                    details.append("Conversion IA: %s" % result.get("detail"))

        presence_svc = self.env["pe.presence.service"]
        payroll_svc = self.env["pe.payroll.service"].sudo()
        period = payroll_svc.get_payroll_period()
        heures_total = payroll_svc.calculate_employee_payroll(
            employee.id, period["period_start"], min(fin, period["period_end"])
        ).get("heures_nettes", 0.0)
        if heures_total <= 0:
            heures_total = 0.0
            current = debut
            while current <= fin:
                h = presence_svc.calculer_heures_reelles_jour(employee.id, current)
                heures_total += h.get("heures_reelles", 0.0)
                current += datetime.timedelta(days=1)

        leads_confirmes = self.env["crm.lead"].search_count(
            [
                ("user_id.employee_ids", "in", [employee.id]),
                ("stage_id.name", "ilike", "confirm"),
                ("date_closed", ">=", debut),
                ("date_closed", "<=", fin),
            ]
        )
        upsells = self.env["pe.prime.upsell.log"].search_count(
            [
                ("employee_id", "=", employee.id),
                ("date", ">=", debut),
                ("date", "<=", fin),
                ("valide_par_manager", "=", True),
            ]
        )
        assignments = self.env["pe.agent.assignment"].search(
            [
                ("employee_id", "=", employee.id),
                ("date_attribution", ">=", debut),
                ("date_attribution", "<=", fin),
            ]
        )
        taux_ia = 0.0
        if assignments:
            conv = len(assignments.filtered(lambda r: r.statut == "converti"))
            taux_ia = conv / len(assignments) * 100

        deductions = sum(
            self.env["pe.leave.impact.prime"]
            .search(
                [
                    ("employee_id", "=", employee.id),
                    ("mois", "=", mois),
                ]
            )
            .mapped("prime_deduite")
        )

        payslip.write(
            {
                "salaire_base": profile.salaire_base if profile else payslip.salaire_base,
                "devise_base": profile.devise_remuneration
                if profile
                else payslip.devise_base,
                "prime_plateau": prime_plateau,
                "prime_upsell": prime_upsell,
                "prime_conversion": prime_conversion,
                "heures_reelles_mois": heures_total,
                "leads_confirmes_mois": leads_confirmes,
                "leads_upsell_mois": upsells,
                "taux_conversion_ia_mois": taux_ia,
                "blocs_primes": blocs,
                "deduction_absences": deductions,
                "detail_calcul": "\n".join(details),
                "date_calcul": fields.Datetime.now(),
            }
        )
        return payslip

    @api.model
    def action_open_my_payslip(self):
        """Dashboard employé : fiche paie du mois courant."""
        user = self.env.user
        employee = self.env["hr.employee"].pe_resolve_user_employee()
        if not employee:
            return {"type": "ir.actions.act_window_close"}
        mois = datetime.date.today().strftime("%Y-%m")
        payslip = self.search(
            [("employee_id", "=", employee.id), ("mois", "=", mois)],
            limit=1,
        )
        if not payslip:
            payslip = self._recalculer_employe(
                employee,
                mois,
                datetime.date.today().replace(day=1),
                datetime.date.today(),
            )
        return {
            "type": "ir.actions.act_window",
            "name": "Mon dashboard",
            "res_model": "pe.payslip.live",
            "res_id": payslip.id,
            "view_mode": "form",
            "target": "current",
        }
