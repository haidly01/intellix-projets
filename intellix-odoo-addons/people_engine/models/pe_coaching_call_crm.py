# -*- coding: utf-8 -*-
from odoo import fields, models


class CrmLeadCoachingCalls(models.Model):
    _inherit = "crm.lead"

    coaching_call_ids = fields.One2many(
        "pe.coaching.call", "lead_id", string="Coaching appels"
    )


class PeCoachingCallCrm(models.Model):
    _inherit = "pe.coaching.call"

    qualification_appel = fields.Selection(
        [
            ("non_fait", "Pas encore qualifié"),
            ("qualifie", "Qualifié — lead chaud"),
            ("a_rappeler", "Rappel"),
            ("rdv", "RDV planifié"),
            ("pas_interesse", "Pas intéressé"),
            ("deja_servi", "Déjà servi"),
            ("locataire", "Locataire"),
            ("dnc", "DNC — Ne plus appeler"),
            ("messagerie", "Boîte vocale"),
            ("hors_cible", "Hors cible"),
            ("faux_num", "Faux numéro"),
            ("b2b_valide", "B2B validé pour Karine"),
        ],
        string="Qualification appel",
        index=True,
    )
