# -*- coding: utf-8 -*-
from odoo import api, fields, models


class PeopleEngineLevel(models.Model):
    _name = "pe.level"
    _description = "Niveau employé People Engine"
    _order = "points_required asc"

    name = fields.Char(required=True)
    level_number = fields.Integer(required=True)
    icon = fields.Char(default="⭐")
    color = fields.Char(default="#4F6EF7")
    points_required = fields.Integer(required=True)
    perks = fields.Text(string="Avantages")
    reward_ids = fields.Many2many("pe.reward", string="Récompenses automatiques")

    _level_number_unique = models.Constraint(
        "unique(level_number)", "Le numéro de niveau doit être unique."
    )


class PeopleEngineEmployeeLevel(models.Model):
    _name = "pe.employee.level"
    _description = "Niveau actuel employé PE"
    _rec_name = "profile_id"

    profile_id = fields.Many2one(
        "pe.employee.profile",
        required=True,
        ondelete="cascade",
        index=True,
    )
    level_id = fields.Many2one("pe.level", string="Niveau actuel")
    total_points = fields.Integer(default=0)
    points_to_next = fields.Integer(compute="_compute_points_to_next")
    point_history_ids = fields.One2many(
        "pe.point.transaction", "employee_level_id"
    )

    _profile_unique = models.Constraint(
        "unique(profile_id)", "Un seul enregistrement de niveau par profil."
    )

    @api.depends("total_points", "level_id")
    def _compute_points_to_next(self):
        Level = self.env["pe.level"]
        for rec in self:
            next_level = Level.search(
                [("points_required", ">", rec.total_points)],
                order="points_required asc",
                limit=1,
            )
            rec.points_to_next = (
                (next_level.points_required - rec.total_points) if next_level else 0
            )


class PeopleEnginePointTransaction(models.Model):
    _name = "pe.point.transaction"
    _description = "Transaction de points PE"
    _order = "date desc"

    employee_level_id = fields.Many2one(
        "pe.employee.level", required=True, ondelete="cascade", index=True
    )
    profile_id = fields.Many2one(
        related="employee_level_id.profile_id", store=True, readonly=True
    )
    points = fields.Integer(required=True)
    source = fields.Selection(
        [
            ("badge", "Badge obtenu"),
            ("objective", "Objectif complété"),
            ("evaluation", "Évaluation positive"),
            ("challenge", "Défi d'équipe gagné"),
            ("training", "Formation complétée"),
            ("quiz_certification", "Certification quiz"),
            ("manual", "Attribution manuelle RH"),
            ("call_center", "Call Center"),
        ],
        required=True,
    )
    reference_id = fields.Integer()
    description = fields.Char()
    date = fields.Datetime(default=fields.Datetime.now, required=True)
