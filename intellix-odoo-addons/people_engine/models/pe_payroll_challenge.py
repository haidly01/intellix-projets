# -*- coding: utf-8 -*-
import datetime

from odoo import _, api, fields, models
from odoo.exceptions import UserError


class PePayrollChallenge(models.Model):
    _name = "pe.payroll.challenge"
    _description = "Challenge paie (primes monétaires)"
    _inherit = ["mail.thread"]
    _order = "date_debut desc, id desc"

    name = fields.Char(string="Nom", required=True, tracking=True)
    description = fields.Text(string="Description")
    type_metrique = fields.Selection(
        [
            ("nombre_appels", "Nombre d'appels"),
            ("nombre_contacts", "Nombre de contacts"),
            ("taux_conversion", "Taux de conversion (%)"),
            ("leads_qualifies", "Leads qualifiés"),
            ("heures_loguees", "Heures loguées"),
            ("taches_completees", "Tâches complétées"),
            ("ca_genere", "CA généré"),
        ],
        string="Métrique",
        required=True,
        default="nombre_appels",
    )
    objectif_valeur = fields.Float(string="Objectif", required=True)
    date_debut = fields.Date(string="Date début", required=True, index=True)
    date_fin = fields.Date(string="Date fin", required=True, index=True)
    montant_prime = fields.Float(string="Montant prime", required=True)
    prime_paliers = fields.Boolean(
        string="Prime par paliers",
        default=True,
        help="Palier call center : 50%%→25%%, 75%%→50%%, 100%%→100%%, 120%%+→125%%",
    )
    employee_ids = fields.Many2many(
        "hr.employee",
        "pe_payroll_challenge_employee_rel",
        "challenge_id",
        "employee_id",
        string="Agents",
    )
    department_id = fields.Many2one("hr.department", string="Département")
    department_pe_id = fields.Many2one("pe.department", string="Département PE")
    statut = fields.Selection(
        [
            ("draft", "Brouillon"),
            ("active", "Actif"),
            ("finished", "Terminé"),
            ("closed", "Clôturé paie"),
        ],
        default="draft",
        tracking=True,
    )
    cumul_paie = fields.Boolean(
        string="Inclure en paie",
        default=True,
        help="Somme la prime sur le bulletin de paie à la clôture du challenge.",
    )
    gamification_challenge_id = fields.Many2one(
        "gamification.challenge",
        string="Challenge gamification lié",
        help="Lien optionnel vers un badge gamification (sans dupliquer les objectifs).",
    )
    resultat_ids = fields.One2many(
        "pe.payroll.challenge.result", "challenge_id", string="Résultats"
    )
    result_count = fields.Integer(compute="_compute_result_stats")
    prime_totale_calculee = fields.Float(compute="_compute_result_stats")

    @api.depends("resultat_ids.prime_calculee")
    def _compute_result_stats(self):
        for rec in self:
            rec.result_count = len(rec.resultat_ids)
            rec.prime_totale_calculee = sum(rec.resultat_ids.mapped("prime_calculee"))

    def _get_participant_employees(self):
        self.ensure_one()
        if self.employee_ids:
            return self.employee_ids
        if self.department_pe_id:
            return self.department_pe_id.employee_ids
        if self.department_id:
            return self.env["hr.employee"].search(
                [("department_id", "=", self.department_id.id), ("active", "=", True)]
            )
        return self.env["hr.employee"].search([("active", "=", True)])

    def action_activate(self):
        self.write({"statut": "active"})

    def action_finish(self):
        self.write({"statut": "finished"})
        self.action_recalculate_results()

    def action_recalculate_results(self):
        svc = self.env["pe.payroll.challenge.service"].sudo()
        for challenge in self:
            svc.recalculate_challenge(challenge)
        return True

    def action_open_team_ranking(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": _("Classement — %s") % self.name,
            "res_model": "pe.payroll.challenge.result",
            "view_mode": "list",
            "domain": [("challenge_id", "=", self.id)],
            "context": {"default_challenge_id": self.id},
        }


class PePayrollChallengeResult(models.Model):
    _name = "pe.payroll.challenge.result"
    _description = "Résultat challenge paie par agent"
    _order = "pourcentage desc, prime_calculee desc"

    challenge_id = fields.Many2one(
        "pe.payroll.challenge",
        string="Challenge",
        required=True,
        ondelete="cascade",
        index=True,
    )
    employee_id = fields.Many2one("hr.employee", required=True, index=True)
    valeur_atteinte = fields.Float(string="Valeur atteinte")
    pourcentage = fields.Float(string="Progression (%)")
    palier_atteint = fields.Selection(
        [
            ("aucun", "Aucun (<50%)"),
            ("50", "50%"),
            ("75", "75%"),
            ("100", "100%"),
            ("120_et_plus", "120%+"),
        ],
        string="Palier",
        default="aucun",
    )
    prime_calculee = fields.Float(string="Prime calculée")
    date_calcul = fields.Datetime(string="Dernier calcul", readonly=True)
    inclus_paie_id = fields.Many2one(
        "pe.payroll.bulletin", string="Bulletin paie", readonly=True, index=True
    )
    statut = fields.Selection(
        [
            ("draft", "Brouillon"),
            ("calculated", "Calculé"),
            ("finalized", "Finalisé paie"),
            ("paid", "Payé"),
        ],
        default="draft",
    )
    jours_restants = fields.Integer(
        string="Jours restants", compute="_compute_jours_restants"
    )
    prime_potentielle = fields.Float(
        string="Prime potentielle max", related="challenge_id.montant_prime"
    )
    type_metrique = fields.Selection(related="challenge_id.type_metrique")
    objectif_valeur = fields.Float(related="challenge_id.objectif_valeur")

    _challenge_employee_unique = models.Constraint(
        "unique(challenge_id, employee_id)",
        "Un seul résultat par agent et par challenge.",
    )

    @api.depends("challenge_id.date_fin")
    def _compute_jours_restants(self):
        today = fields.Date.today()
        for rec in self:
            if rec.challenge_id.date_fin:
                rec.jours_restants = max((rec.challenge_id.date_fin - today).days, 0)
            else:
                rec.jours_restants = 0

    def name_get(self):
        return [
            (r.id, "%s — %s" % (r.challenge_id.name, r.employee_id.name))
            for r in self
        ]


class PePayrollBulletinChallengeLine(models.Model):
    _name = "pe.payroll.bulletin.challenge.line"
    _description = "Ligne prime challenge sur bulletin"
    _order = "id"

    bulletin_id = fields.Many2one(
        "pe.payroll.bulletin", required=True, ondelete="cascade", index=True
    )
    result_id = fields.Many2one("pe.payroll.challenge.result", string="Résultat")
    challenge_name = fields.Char(string="Challenge", required=True)
    type_metrique = fields.Char(string="Métrique")
    valeur_atteinte = fields.Float(string="Valeur")
    objectif_valeur = fields.Float(string="Objectif")
    pourcentage = fields.Float(string="%")
    palier_atteint = fields.Char(string="Palier")
    montant = fields.Float(string="Prime")
