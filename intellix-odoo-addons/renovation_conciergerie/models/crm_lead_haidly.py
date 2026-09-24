# -*- coding: utf-8 -*-
from odoo import fields, models


class CrmLeadHaidly(models.Model):
    _inherit = "crm.lead"

    reno_types = fields.Char(
        string="Types de rénovation",
        help="Liste séparée par virgules (cuisine, salle_de_bain, patio, etc.)",
    )
    reno_budget = fields.Selection(
        [
            ("moins_10k", "< 10 000 $"),
            ("10_25k", "10 000 - 25 000 $"),
            ("25_50k", "25 000 - 50 000 $"),
            ("50_100k", "50 000 - 100 000 $"),
            ("100k_plus", "100 000 $+"),
            ("inconnu", "Non mentionné"),
        ],
        string="Budget estimé",
        tracking=True,
    )
    reno_delai = fields.Selection(
        [
            ("urgent", "Urgent (< 1 mois)"),
            ("3_mois", "1-3 mois"),
            ("6_mois", "3-6 mois"),
            ("1_an", "6-12 mois"),
            ("plus_1_an", "> 1 an"),
            ("indefini", "À définir"),
        ],
        string="Délai travaux",
        tracking=True,
    )
    reno_style = fields.Char(string="Style design mentionné")
    reno_property_type = fields.Selection(
        [
            ("maison", "Maison unifamiliale"),
            ("condo", "Condo"),
            ("duplex", "Duplex/Triplex"),
            ("cottage", "Chalet/Cottage"),
        ],
        string="Type de propriété",
    )
    reno_project_type = fields.Selection(
        [
            ("cuisine", "Cuisine"),
            ("salle_de_bain", "Salle de bain"),
            ("sous_sol", "Sous-sol"),
            ("agrandissement", "Agrandissement"),
            ("exterieur", "Réno extérieure"),
            ("patio", "Patio / Terrasse"),
            ("pergola", "Pergola"),
            ("pool_house", "Pool house"),
            ("pieux", "Pieux vissés"),
            ("multi", "Multi-projets"),
        ],
        string="Type de projet (Haidly)",
        tracking=True,
    )
    reno_plans_3d_offerts = fields.Boolean(string="Plans 3D offerts")
    reno_photos_uploadees = fields.Boolean(string="Photos uploadées")
    reno_lien_photos_envoye = fields.Boolean(string="Lien upload envoyé")
    reno_subventions_applicables = fields.Char(string="Subventions identifiées")
    reno_subvention_estimee = fields.Float(string="Subvention estimée ($)")
    reno_projet_multigenerationnel = fields.Boolean(string="Projet multigénérationnel")
    reno_aine_present = fields.Boolean(string="Aîné / accessibilité")
    haidly_ia_score = fields.Selection(
        [("hot", "Hot"), ("warm", "Warm"), ("cold", "Cold")],
        string="Score Haidly",
        tracking=True,
    )
    haidly_ia_score_numeric = fields.Integer(string="Score Haidly /100", tracking=True)
    haidly_elevenlabs_conv_id = fields.Char(
        string="ElevenLabs Conv ID (Haidly)", index=True
    )
    haidly_call_transcript = fields.Text(string="Transcript appel Haidly")
    haidly_transfer_at = fields.Datetime(string="Transfert humain le")
    haidly_nurture_active = fields.Boolean(
        string="Séquence nurture Haidly active", default=False
    )
    haidly_total_call_attempts = fields.Integer(
        string="Tentatives d'appel Haidly", default=0
    )
    haidly_do_not_call = fields.Boolean(string="Ne plus appeler (Haidly DNC)")
    haidly_source = fields.Char(
        string="Source lead Haidly",
        default="soumissionentrepreneurs",
        index=True,
    )
