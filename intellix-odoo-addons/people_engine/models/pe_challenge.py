# -*- coding: utf-8 -*-
from odoo import _, api, fields, models
from odoo.exceptions import UserError


class PeopleEngineChallenge(models.Model):
    _name = "pe.challenge"
    _description = "Défi d'équipe People Engine"
    _inherit = ["mail.thread"]
    _order = "date_start desc"

    name = fields.Char(required=True, tracking=True)
    description = fields.Text()
    challenge_type = fields.Selection(
        [
            ("individual", "Individuel"),
            ("team", "Équipe vs équipe"),
            ("collective", "Objectif collectif"),
        ],
        default="individual",
        required=True,
    )
    metric = fields.Selection(
        [
            ("crm_conversion", "Taux de conversion CRM"),
            ("crm_revenue", "Revenus générés"),
            ("tasks_ontime", "Tâches livrées à temps"),
            ("ia_quality", "Score qualité appels"),
            ("score_global", "Score People Engine global"),
            ("appels", "Appels / jour"),
            ("demos", "Démos bookées"),
            ("ventes", "Ventes conclues"),
            ("score_ia", "Score IA moyen"),
            ("presence", "Présence / assiduité"),
        ],
        required=True,
    )
    reward_badge_id = fields.Many2one("pe.badge", string="Badge récompense")
    department_pe_id = fields.Many2one("pe.department", string="Département PE")
    target_value = fields.Float(required=True)
    date_start = fields.Date(required=True)
    date_end = fields.Date(required=True)
    participant_ids = fields.Many2many("pe.employee.profile", string="Participants")
    department_ids = fields.Many2many("hr.department", string="Départements")
    winner_reward_id = fields.Many2one("pe.reward")
    winner_points = fields.Integer(default=50)
    participation_points = fields.Integer(default=10)
    status = fields.Selection(
        [
            ("draft", "Brouillon"),
            ("active", "En cours"),
            ("finished", "Terminé"),
            ("awarded", "Récompenses attribuées"),
        ],
        default="draft",
        tracking=True,
    )
    created_by_id = fields.Many2one("hr.employee", required=True)
    approved_by_id = fields.Many2one("hr.employee", string="Approuvé par")

    def action_activate(self):
        if not self.approved_by_id:
            raise UserError(_("Un responsable doit approuver le défi avant activation."))
        self.write({"status": "active"})

    def action_finish_and_award(self):
        engine = self.env["pe.gamification.engine"]
        for challenge in self:
            engine.award_challenge_winners(challenge)
            challenge.write({"status": "awarded"})
