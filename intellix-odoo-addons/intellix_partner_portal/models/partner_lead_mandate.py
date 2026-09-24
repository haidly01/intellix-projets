# -*- coding: utf-8 -*-
from odoo import api, fields, models


STATUS_VALUES = [
    ("nouveau", "Nouveau"),
    ("relance", "En relance"),
    ("rdv", "RDV fixé"),
    ("vendu", "Vendu"),
    ("perdu", "Perdu"),
]


class IntellixPartnerLeadMandate(models.Model):
    _name = "intellix.partner.lead.mandate"
    _description = "Mandat lead partenaire"
    _order = "id desc"

    name = fields.Char(string="Prospect", required=True)
    partner_id = fields.Many2one(
        "res.partner",
        string="Partenaire",
        required=True,
        ondelete="cascade",
        index=True,
    )
    bloc_id = fields.Many2one(
        "intellix.partner.lead.bloc",
        string="Bloc",
        ondelete="set null",
        index=True,
    )
    crm_lead_id = fields.Many2one(
        "crm.lead",
        string="Lead CRM",
        ondelete="set null",
    )
    status = fields.Selection(
        STATUS_VALUES,
        default="nouveau",
        required=True,
        index=True,
    )
    # Assignation à un membre de l'organisation (jamais cross-org : contrôlé
    # côté contrôleur, borné à commercial_partner_id de l'appelant).
    assigned_user_id = fields.Many2one("res.users", string="Assigné à", index=True)
    notes = fields.Text(string="Notes")
    ia_score = fields.Integer(string="Score IA", default=75)
    delivered_date = fields.Datetime(
        string="Date de livraison",
        default=fields.Datetime.now,
    )
    phone = fields.Char(string="Téléphone")
    city = fields.Char(string="Ville")
    project_type = fields.Char(string="Service demandé")
    budget_range = fields.Char(string="Budget")
    timing = fields.Char(string="Timing")
    is_owner_confirmed = fields.Boolean(string="Propriétaire confirmé")
    agent_name = fields.Char(string="Agent IA", default="Léa")
    campaign_name = fields.Char(string="Campagne", default="DW_QCB2C")
    qualification_notes = fields.Text(string="Notes qualification")
    attempt_ids = fields.One2many(
        "intellix.partner.lead.attempt",
        "mandate_id",
        string="Tentatives",
    )
    activity_ids = fields.One2many(
        "intellix.partner.lead.activity",
        "mandate_id",
        string="Activités",
    )
    score_class = fields.Selection(
        [
            ("green", "Élevé"),
            ("orange", "Moyen"),
        ],
        compute="_compute_score_class",
    )
    status_label = fields.Char(compute="_compute_status_label")
    attempt_count = fields.Integer(compute="_compute_attempt_count")

    @api.depends("ia_score")
    def _compute_score_class(self):
        for rec in self:
            rec.score_class = "green" if rec.ia_score >= 80 else "orange"

    @api.depends("status")
    def _compute_status_label(self):
        labels = dict(STATUS_VALUES)
        for rec in self:
            rec.status_label = labels.get(rec.status, rec.status)

    @api.depends("attempt_ids")
    def _compute_attempt_count(self):
        for rec in self:
            rec.attempt_count = len(rec.attempt_ids)
