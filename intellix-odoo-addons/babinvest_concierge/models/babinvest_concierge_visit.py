# -*- coding: utf-8 -*-

import secrets

from odoo import api, fields, models

# Personas pour qui le transport aéroport/hôtel est coché par défaut à la
# création d'une visite physique (brief section 1, transport_required).
TRANSPORT_DEFAULT_PERSONAS = {"retraite_etranger", "mre"}


class BabinvestConciergeVisit(models.Model):
    _name = "babinvest.concierge.visit"
    _description = "Visite projet — conciergerie Bab Invest"
    _inherit = ["mail.activity.mixin"]
    _order = "scheduled_date desc"

    lead_id = fields.Many2one(
        "babinvest.concierge.lead", string="Lead", required=True, ondelete="cascade", index=True
    )
    project_id = fields.Many2one("babinvest.project", string="Projet visité", required=True)
    scheduled_date = fields.Datetime(string="Date prévue", required=True)
    mode = fields.Selection(
        [("physique", "Physique"), ("visio", "Visioconférence")],
        default="physique",
        required=True,
    )
    visio_link = fields.Char(
        string="Lien visio",
        help="Généré automatiquement à la création si la visite est en visioconférence "
        "(en attendant le branchement API Google Meet/Zoom, un lien de secours unique "
        "est généré — à remplacer manuellement une fois l'intégration faite).",
    )
    status = fields.Selection(
        [
            ("planifiee", "Planifiée"),
            ("confirmee", "Confirmée"),
            ("effectuee", "Effectuée"),
            ("no_show", "No-show"),
        ],
        default="planifiee",
        required=True,
    )
    notes_objections = fields.Text(string="Notes / objections relevées")

    # --- Transport (brief section 1, sous-modèle visit) ---
    transport_required = fields.Boolean(
        string="Transport requis",
        help="Coché automatiquement pour les personas retraité à l'étranger / MRE lors de "
        "la sélection du lead ; modifiable manuellement pour toute visite physique.",
    )
    transport_mode = fields.Selection(
        [
            ("aeroport_villa", "Aéroport → villa/projet"),
            ("hotel_villa", "Hôtel → villa/projet"),
            ("autre", "Autre"),
        ],
        string="Type de transport",
    )
    pickup_location = fields.Char(string="Lieu de prise en charge")
    pickup_datetime = fields.Datetime(string="Date/heure de prise en charge")
    transport_provider = fields.Char(string="Chauffeur / société assignée")
    transport_notes = fields.Text(
        string="Notes transport",
        help="Numéro de vol, nombre de passagers, besoins particuliers.",
    )
    transport_status = fields.Selection(
        [
            ("a_organiser", "À organiser"),
            ("confirme", "Confirmé"),
            ("effectue", "Effectué"),
        ],
        default="a_organiser",
        string="Statut transport",
    )

    @api.onchange("lead_id")
    def _onchange_lead_id_transport(self):
        for visit in self:
            if visit.lead_id.persona in TRANSPORT_DEFAULT_PERSONAS:
                visit.transport_required = True

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get("mode") == "visio" and not vals.get("visio_link"):
                vals["visio_link"] = "https://meet.intellix.internal/babinvest-" + secrets.token_urlsafe(8)
            if "transport_required" not in vals and vals.get("lead_id"):
                lead = self.env["babinvest.concierge.lead"].browse(vals["lead_id"])
                if lead.persona in TRANSPORT_DEFAULT_PERSONAS:
                    vals["transport_required"] = True
        return super().create(vals_list)
