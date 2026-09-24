# -*- coding: utf-8 -*-
from odoo import api, fields, models


class PeDepartmentObjective(models.Model):
    _name = "pe.department.objective"
    _description = "Objectif département"
    _order = "sequence, id"

    department_id = fields.Many2one(
        "pe.department", required=True, ondelete="cascade", index=True
    )
    sequence = fields.Integer(default=10)
    name = fields.Char(string="Nom objectif", required=True)
    type_usager = fields.Selection(
        [
            ("tous", "Tous les employés du département"),
            ("prospecteur_vicidial", "Prospecteur VICIdial uniquement"),
            ("prospecteur_social", "Prospecteur réseaux sociaux uniquement"),
            ("closeur", "Agent closeur uniquement"),
            ("gestionnaire", "Gestionnaire uniquement"),
        ],
        required=True,
        default="tous",
    )
    metrique = fields.Selection(
        [
            ("leads_qualifies_jour", "Leads qualifiés / jour"),
            ("leads_qualifies_mois", "Leads qualifiés / mois"),
            ("taux_conversion_pct", "Taux de conversion (%)"),
            ("taux_conversion_ia_pct", "Taux conversion leads IA (%)"),
            ("duree_moyenne_appel_min", "Durée moyenne appel (min)"),
            ("appels_total_jour", "Appels total / jour"),
            ("leads_supplementaires", "Leads supplémentaires générés (upsell)"),
            ("heures_travaillees_jour", "Heures travaillées réelles / jour"),
            ("taux_presence_pct", "Taux présence (%)"),
            ("demos_jour", "Démos bookées / jour"),
            ("score_ia_moy_jour", "Score IA moyen / jour"),
            ("jours_ponctualite_semaine", "Jours ponctualité / semaine"),
        ],
        required=True,
    )
    points_atteint = fields.Integer(
        string="Points gamification si atteint",
        default=50,
    )
    valeur_cible = fields.Float(string="Cible", required=True)
    valeur_minimum = fields.Float(
        string="Minimum acceptable",
        help="En dessous = non-performance.",
    )
    tolerance_chute_pct = fields.Float(string="Tolérance chute (%)")
    periode = fields.Selection(
        [
            ("jour", "Par jour"),
            ("semaine", "Par semaine"),
            ("mois", "Par mois"),
        ],
        default="jour",
    )
    actif = fields.Boolean(default=True)
    notes = fields.Text(string="Notes / explications")

    @api.onchange("valeur_cible", "tolerance_chute_pct")
    def _onchange_valeur_minimum(self):
        for rec in self:
            if rec.valeur_cible and rec.tolerance_chute_pct:
                rec.valeur_minimum = rec.valeur_cible * (
                    1 - rec.tolerance_chute_pct / 100
                )

    def _profile_for_employee(self, employee):
        return self.env["pe.employee.profile"].search(
            [("employee_id", "=", employee.id)], limit=1
        )

    def _applies_to_employee(self, employee):
        profile = self._profile_for_employee(employee)
        role = profile.type_usager_pe or "mixte"
        mapping = {
            "prospecteur_vicidial": ("prospecteur_vicidial", "mixte"),
            "prospecteur_social": ("prospecteur_social", "mixte"),
            "closeur": ("closeur", "mixte"),
            "gestionnaire": ("gestionnaire", "mixte"),
        }
        if self.type_usager == "tous":
            return True
        allowed = mapping.get(self.type_usager, (self.type_usager,))
        return role in allowed

    def evaluer_employe(self, employee, periode_debut, periode_fin):
        self.ensure_one()
        employee = self.env["hr.employee"].browse(employee)
        if isinstance(employee, int):
            employee = self.env["hr.employee"].browse(employee)
        if not self._applies_to_employee(employee):
            return {
                "valeur_reelle": 0.0,
                "valeur_cible": self.valeur_cible,
                "valeur_minimum": self.valeur_minimum,
                "atteint": False,
                "pct_atteinte": 0.0,
                "statut": "na",
            }
        profile = self._profile_for_employee(employee)
        coef = profile.coefficient_objectifs if profile else 1.0
        if not coef or coef <= 0:
            coef = 1.0
        cible = self.valeur_cible * coef
        methode = "_calculer_%s" % self.metrique
        valeur = getattr(self, methode)(employee.id, periode_debut, periode_fin)
        pct = (valeur / cible * 100) if cible else 0
        base_minimum = self.valeur_minimum or (self.valeur_cible * 0.75)
        minimum = base_minimum * coef
        if valeur >= cible:
            statut = "ok"
        elif valeur >= minimum:
            statut = "attention"
        else:
            statut = "critique"
        return {
            "valeur_reelle": valeur,
            "valeur_cible": cible,
            "valeur_minimum": minimum,
            "atteint": valeur >= cible,
            "pct_atteinte": pct,
            "statut": statut,
        }

    def _calculer_leads_qualifies_jour(self, employee_id, debut, fin):
        jours = max((fin - debut).days, 1)
        leads = self.env["crm.lead"].search_count(
            [
                ("user_id.employee_ids", "in", [employee_id]),
                ("stage_id.name", "ilike", "qualif"),
                ("date_closed", ">=", debut),
                ("date_closed", "<=", fin),
            ]
        )
        return leads / jours

    def _calculer_leads_qualifies_mois(self, employee_id, debut, fin):
        return float(
            self.env["crm.lead"].search_count(
                [
                    ("user_id.employee_ids", "in", [employee_id]),
                    ("stage_id.name", "ilike", "qualif"),
                    ("date_closed", ">=", debut),
                    ("date_closed", "<=", fin),
                ]
            )
        )

    def _calculer_taux_conversion_ia_pct(self, employee_id, debut, fin):
        assignments = self.env["pe.agent.assignment"].search(
            [
                ("employee_id", "=", employee_id),
                ("date_attribution", ">=", debut),
                ("date_attribution", "<=", fin),
            ]
        )
        if not assignments:
            return 0.0
        convertis = assignments.filtered(lambda r: r.statut == "converti")
        return len(convertis) / len(assignments) * 100

    def _calculer_leads_supplementaires(self, employee_id, debut, fin):
        return float(
            self.env["pe.prime.upsell.log"].search_count(
                [
                    ("employee_id", "=", employee_id),
                    ("date", ">=", debut),
                    ("date", "<=", fin),
                ]
            )
        )

    def _calculer_heures_travaillees_jour(self, employee_id, debut, fin):
        svc = self.env["pe.presence.service"]
        total = 0.0
        current = debut
        while current <= fin:
            h = svc.calculer_heures_reelles_jour(employee_id, current)
            total += h.get("heures_reelles", 0.0)
            current += __import__("datetime").timedelta(days=1)
        jours = max((fin - debut).days + 1, 1)
        return total / jours

    def _calculer_taux_presence_pct(self, employee_id, debut, fin):
        summaries = self.env["pe.presence.summary"].search(
            [
                ("employee_id", "=", employee_id),
                ("date", ">=", debut),
                ("date", "<=", fin),
            ]
        )
        if not summaries:
            return 0.0
        present = len(summaries.filtered(lambda s: s.statut_jour == "present"))
        return present / len(summaries) * 100

    def _calculer_taux_conversion_pct(self, employee_id, debut, fin):
        profile = self.env["pe.employee.profile"].search(
            [("employee_id", "=", employee_id)], limit=1
        )
        return profile.crm_conversion_rate if profile else 0.0

    def _calculer_appels_total_jour(self, employee_id, debut, fin):
        jours = max((fin - debut).days, 1)
        calls = self.env["pe.coaching.call"].search_count(
            [
                ("employee_id", "=", employee_id),
                ("date_appel", ">=", debut),
                ("date_appel", "<=", fin),
            ]
        )
        return calls / jours

    def _calculer_duree_moyenne_appel_min(self, employee_id, debut, fin):
        calls = self.env["pe.coaching.call"].search(
            [
                ("employee_id", "=", employee_id),
                ("date_appel", ">=", debut),
                ("date_appel", "<=", fin),
            ]
        )
        if not calls:
            return 0.0
        return sum(calls.mapped("duree_secondes")) / len(calls) / 60.0

    def _calculer_demos_jour(self, employee_id, debut, fin):
        jours = max((fin - debut).days, 1)
        demos = self.env["pe.call.log"].search_count(
            [
                ("employee_id", "=", employee_id),
                ("outcome", "=", "demo_bookee"),
                ("date_call", ">=", debut),
                ("date_call", "<=", fin),
            ]
        )
        employee = self.env["hr.employee"].browse(employee_id)
        if employee.user_id:
            demos += self.env["crm.lead"].search_count(
                [
                    ("user_id", "=", employee.user_id.id),
                    ("source_vicidial", "=", True),
                    ("qualification_statut", "=", "rdv"),
                    ("write_date", ">=", debut),
                    ("write_date", "<=", fin),
                ]
            )
        return demos / jours

    def _calculer_score_ia_moy_jour(self, employee_id, debut, fin):
        logs = self.env["pe.call.log"].search(
            [
                ("employee_id", "=", employee_id),
                ("date_call", ">=", debut),
                ("date_call", "<=", fin),
                ("ai_score", ">", 0),
            ]
        )
        if not logs:
            return 0.0
        return sum(logs.mapped("ai_score")) / len(logs)

    def _calculer_jours_ponctualite_semaine(self, employee_id, debut, fin):
        summaries = self.env["pe.presence.summary"].search(
            [
                ("employee_id", "=", employee_id),
                ("date", ">=", debut),
                ("date", "<=", fin),
                ("statut_jour", "=", "present"),
            ]
        )
        return float(len(summaries))
