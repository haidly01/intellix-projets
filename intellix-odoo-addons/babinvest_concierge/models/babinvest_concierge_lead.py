# -*- coding: utf-8 -*-

from datetime import timedelta

from odoo import api, fields, models

# Budget médian par persona (à calibrer avec les vraies données de vente —
# valeurs de départ raisonnables en MAD pour Marrakech, phase 1).
PERSONA_MEDIAN_BUDGET = {
    "locatif_pur": 800000,
    "residence_secondaire": 1500000,
    "retraite_etranger": 1200000,
    "mre": 1000000,
    "investisseur_multi_lots": 3500000,
}

# Urgence déclarée -> poids (bornes fixées par le brief : immédiat 1.0, long terme 0.25).
HORIZON_URGENCY = {
    "immediat": 1.0,
    "court_terme": 0.75,
    "moyen_terme": 0.5,
    "long_terme": 0.25,
}

# Délai (jours depuis last_contact_date, ou depuis la visite selon l'étape) avant
# la prochaine relance — reprend le premier seuil de la cadence de la section 3
# du brief. n8n gère le détail des relances successives (J+3/J+7/J+14, etc.) en
# se basant sur cette date d'ancrage + l'historique dans concierge.interaction ;
# Odoo n'a pas besoin de dupliquer toute la machine à états ici.
STAGE_FOLLOWUP_DELAY_DAYS = {
    "babinvest_concierge.stage_nouveau_lead": 0,  # <2h : immédiat
    "babinvest_concierge.stage_qualification": 3,
    "babinvest_concierge.stage_visite_effectuee": 2,
}


class BabinvestConciergeLead(models.Model):
    _name = "babinvest.concierge.lead"
    _description = "Lead conciergerie Bab Invest"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "score desc, id desc"

    name = fields.Char(string="Nom complet", required=True, tracking=True)
    phone = fields.Char(string="Téléphone")
    email = fields.Char(string="Email")
    whatsapp = fields.Char(string="WhatsApp")
    city = fields.Char(string="Ville de résidence")

    source_id = fields.Many2one("utm.source", string="Source")
    persona = fields.Selection(
        [
            ("locatif_pur", "Locatif pur"),
            ("residence_secondaire", "Résidence secondaire"),
            ("retraite_etranger", "Retraite à l'étranger"),
            ("mre", "MRE (Marocain résident à l'étranger)"),
            ("investisseur_multi_lots", "Investisseur multi-lots"),
        ],
        string="Persona",
        tracking=True,
    )
    market_id = fields.Many2one("babinvest.market", string="Marché", tracking=True)
    project_ids = fields.Many2many("babinvest.project", string="Projet(s) d'intérêt")

    budget_declared = fields.Monetary(string="Budget déclaré")
    currency_id = fields.Many2one(
        "res.currency", default=lambda self: self.env.company.currency_id
    )
    financing_mode = fields.Selection(
        [("cash", "Cash"), ("credit", "Crédit"), ("mixte", "Mixte")],
        string="Mode de financement",
    )
    purchase_horizon = fields.Selection(
        [
            ("immediat", "Immédiat (<1 mois)"),
            ("court_terme", "Court terme (1-3 mois)"),
            ("moyen_terme", "Moyen terme (3-6 mois)"),
            ("long_terme", "Long terme (>6 mois)"),
        ],
        string="Horizon d'achat",
        tracking=True,
    )

    stage_id = fields.Many2one(
        "babinvest.concierge.stage",
        string="Étape",
        group_expand="_read_group_stage_ids",
        tracking=True,
        default=lambda self: self.env.ref(
            "babinvest_concierge.stage_nouveau_lead", raise_if_not_found=False
        ),
    )
    is_won = fields.Boolean(related="stage_id.is_won", store=True)
    is_lost = fields.Boolean(related="stage_id.is_lost", store=True)

    score = fields.Integer(compute="_compute_score", store=True, string="Score")
    assigned_to = fields.Many2one("res.users", string="Assigné à", tracking=True)
    lost_reason_id = fields.Many2one("crm.lost.reason", string="Motif de perte")

    last_contact_date = fields.Datetime(string="Dernier contact")
    reservation_deadline = fields.Date(
        string="Échéance compromis",
        help="Date convenue pour la signature du compromis après réservation (arrhes). "
        "Sert d'ancrage à la relance J-3 de la section 3 du brief.",
    )
    next_followup_date = fields.Datetime(
        compute="_compute_next_followup_date", store=True, string="Prochaine relance"
    )

    visit_ids = fields.One2many("babinvest.concierge.visit", "lead_id", string="Visites")
    interaction_ids = fields.One2many(
        "babinvest.concierge.interaction", "lead_id", string="Interactions"
    )

    @api.model
    def _read_group_stage_ids(self, stages, domain):
        return stages.search([], order="sequence")

    @api.depends(
        "budget_declared",
        "persona",
        "purchase_horizon",
        "interaction_ids.sent_date",
        "interaction_ids.response_date",
        "interaction_ids.response_received",
    )
    def _compute_score(self):
        for lead in self:
            median = PERSONA_MEDIAN_BUDGET.get(lead.persona)
            budget_norm = min(lead.budget_declared / median, 1.0) if median and lead.budget_declared else 0.0
            urgency = HORIZON_URGENCY.get(lead.purchase_horizon, 0.0)
            reactivity = lead._compute_reactivity()
            weighted = (budget_norm * 0.4) + (urgency * 0.35) + (reactivity * 0.25)
            lead.score = round(weighted * 100)

    def _compute_reactivity(self):
        self.ensure_one()
        answered = self.interaction_ids.filtered(
            lambda i: i.response_received and i.sent_date and i.response_date
        )
        if not answered:
            return 0.0
        delays_hours = [
            (i.response_date - i.sent_date).total_seconds() / 3600.0 for i in answered
        ]
        avg_hours = sum(delays_hours) / len(delays_hours)
        # Réponse quasi immédiate -> 1.0 ; 72h ou plus -> 0.0, dégradé linéaire entre les deux.
        return max(0.0, min(1.0, 1 - (avg_hours / 72.0)))

    @api.depends(
        "stage_id",
        "last_contact_date",
        "reservation_deadline",
        "visit_ids.status",
        "visit_ids.scheduled_date",
    )
    def _compute_next_followup_date(self):
        for lead in self:
            stage_xmlid = lead.stage_id._get_external_ids().get(lead.stage_id.id)
            stage_xmlid = stage_xmlid[0] if stage_xmlid else None
            next_date = False

            if stage_xmlid == "babinvest_concierge.stage_visite_planifiee":
                upcoming = lead.visit_ids.filtered(
                    lambda v: v.status in ("planifiee", "confirmee") and v.scheduled_date
                ).sorted("scheduled_date")
                if upcoming:
                    next_date = upcoming[0].scheduled_date - timedelta(days=1)
            elif stage_xmlid == "babinvest_concierge.stage_reservation" and lead.reservation_deadline:
                next_date = fields.Datetime.to_datetime(lead.reservation_deadline) - timedelta(days=3)
            elif stage_xmlid in STAGE_FOLLOWUP_DELAY_DAYS and lead.last_contact_date:
                next_date = lead.last_contact_date + timedelta(
                    days=STAGE_FOLLOWUP_DELAY_DAYS[stage_xmlid]
                )

            lead.next_followup_date = next_date
