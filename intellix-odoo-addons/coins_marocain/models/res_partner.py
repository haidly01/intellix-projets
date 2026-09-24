# -*- coding: utf-8 -*-
"""Extension contact (res.partner) — Carnet + qualification terrain Zakaria.

Le contact client sous-jacent au Carnet (`coins.carnet.partner_id`) est bien
`res.partner`. On enrichit cette fiche ; on ne crée pas de modèle contact dédié
et on ne modifie pas `coins.carnet` (badges / paliers / anti-gaming).

HOOKS FUTURS (ne pas implémenter ici) :
- Rappels offre avant coins_date_anniversaire_contact / coins_date_anniversaire_proche
- Filtrage envois promo : coins_interet_ids + coins_consentement_promo_whatsapp
  (jamais envoyer si consentement non coché)
- Alerte si coins_date_depart approche sans réservation confirmée
"""
from odoo import fields, models


class ResPartner(models.Model):
    _inherit = "res.partner"

    # --- Existant Carnet / voyageur ---
    coins_is_traveler = fields.Boolean(string="Voyageur Coins")
    coins_preferences = fields.Text(string="Préférences voyage")
    coins_reservation_count = fields.Integer(
        string="Nb réservations",
        compute="_compute_coins_reservation_count",
    )

    # --- Qualification : identification ---
    # Décision brief : préfixe coins_ (convention module, évite collisions).
    coins_local_ou_voyageur = fields.Selection(
        [
            ("resident", "Résident"),
            ("expatrie", "Expatrié"),
            ("touriste", "Touriste"),
        ],
        string="Local ou voyageur",
        tracking=True,
    )
    coins_pays_origine = fields.Char(
        string="Pays d'origine",
        help="Visible uniquement pour les touristes.",
    )
    coins_date_arrivee = fields.Date(
        string="Date d'arrivée",
        help="Visible uniquement pour les touristes.",
    )
    coins_date_depart = fields.Date(
        string="Date de départ",
        help="Visible uniquement pour les touristes. "
        "HOOK FUTUR : alerte si départ proche sans réservation confirmée.",
    )

    # --- Consentement (défaut = non — ne jamais présumer) ---
    coins_consentement_promo_whatsapp = fields.Boolean(
        string="Consentement promo WhatsApp",
        default=False,
        tracking=True,
        help="HOOK FUTUR : filtrer les envois promo — jamais envoyer si non coché.",
    )

    # --- Profil voyage ---
    # Décision brief (tranches provisoires, à valider avec Karine) :
    # < 500 / 500-1500 / 1500-3000 / 3000+ DH
    coins_budget_approximatif = fields.Selection(
        [
            ("lt_500", "< 500 DH"),
            ("500_1500", "500 – 1 500 DH"),
            ("1500_3000", "1 500 – 3 000 DH"),
            ("gt_3000", "3 000 DH +"),
        ],
        string="Budget approximatif",
    )
    # Décision brief : Many2many (extensible) via coins.partner.interest
    coins_interet_ids = fields.Many2many(
        "coins.partner.interest",
        "coins_partner_interest_rel",
        "partner_id",
        "interest_id",
        string="Intérêts",
        help="HOOK FUTUR : filtrage des offres / envois promo par intérêts.",
    )
    coins_type_groupe = fields.Selection(
        [
            ("solo", "Solo"),
            ("couple", "Couple"),
            ("famille", "Famille"),
            ("amis", "Amis"),
            ("corporate", "Corporate"),
        ],
        string="Type de groupe",
    )
    coins_taille_groupe_habituelle = fields.Integer(
        string="Taille de groupe habituelle",
    )

    # --- Occasions (upsell) — Date Odoo (jour/mois utilisés pour rappels ; année ignorée) ---
    coins_date_anniversaire_contact = fields.Date(
        string="Anniversaire contact",
        help="Jour/mois suffisent pour les rappels. "
        "HOOK FUTUR : offre automatique avant cette date.",
    )
    coins_nom_proche = fields.Char(
        string="Nom / lien du proche",
        help='Ex. "conjoint", "meilleure amie".',
    )
    coins_date_anniversaire_proche = fields.Date(
        string="Anniversaire proche",
        help="HOOK FUTUR : offre automatique avant cette date.",
    )
    coins_date_anniversaire_mariage = fields.Date(
        string="Anniversaire de mariage",
    )
    coins_autre_occasion_recurrente = fields.Char(
        string="Autre occasion récurrente",
        help='Ex. "voyage annuel à Marrakech en mars".',
    )

    # --- Notes terrain ---
    coins_source_connaissance = fields.Selection(
        [
            ("bouche_a_oreille", "Bouche à oreille"),
            ("reseau", "Réseau"),
            ("radio", "Radio"),
            ("rencontre_directe", "Rencontre directe"),
            ("formulaire_site", "Formulaire site"),
            ("autre", "Autre"),
        ],
        string="Source de connaissance",
    )
    coins_notes_terrain = fields.Text(
        string="Notes terrain",
        help="Observations de qualification (Zakaria / agents).",
    )

    def _compute_coins_reservation_count(self):
        Reservation = self.env["coins.reservation"]
        for rec in self:
            rec.coins_reservation_count = Reservation.search_count(
                [("traveler_id", "=", rec.id)]
            )

    def action_view_coins_reservations(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": "Réservations",
            "res_model": "coins.reservation",
            "view_mode": "list,form",
            "domain": [("traveler_id", "=", self.id)],
            "context": {"default_traveler_id": self.id},
        }
