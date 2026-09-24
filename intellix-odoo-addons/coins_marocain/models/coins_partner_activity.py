# -*- coding: utf-8 -*-
from odoo import fields, models


class CoinsPartnerActivity(models.Model):
    _name = "coins.partner_activity"
    _description = "Partenaire activité / resto (Coins Marocain)"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "name"

    name = fields.Char(string="Nom", required=True, tracking=True)
    active = fields.Boolean(default=True)
    category = fields.Selection(
        [
            ("resto", "Restaurant"),
            ("hebergement", "Hébergement"),
            ("quad", "Quad"),
            ("montgolfiere", "Montgolfière"),
            ("hammam", "Hammam / Spa"),
            ("other", "Autre"),
        ],
        string="Catégorie",
        default="resto",
        required=True,
    )
    relation_type = fields.Selection(
        [
            ("direct", "Partenaire direct (négocié)"),
            ("viator", "Affilié Viator"),
            ("libre_service", "Inscription libre-service (carte)"),
        ],
        string="Type de relation",
        default="direct",
        required=True,
        help="Les activités Viator sont importées en lecture seule ; "
        "les partenariats directs sont pilotés dans Odoo. "
        "Libre-service = file d’attente portail propriétaire.",
    )
    state = fields.Selection(
        [
            ("en_attente", "En attente"),
            ("prospected", "Prospecté"),
            ("discussing", "En discussion"),
            ("signed", "Signé"),
        ],
        string="Statut négociation",
        default="prospected",
        required=True,
        tracking=True,
    )
    contact_name = fields.Char(string="Nom du contact")
    partner_id = fields.Many2one("res.partner", string="Contact")
    phone = fields.Char(string="Téléphone")
    email = fields.Char(string="Email")
    currency_id = fields.Many2one(
        "res.currency",
        string="Devise",
        default=lambda self: self.env.company.currency_id.id,
    )
    negotiated_rate = fields.Monetary(
        string="Tarif négocié",
        currency_field="currency_id",
    )
    commission_pct = fields.Float(string="Commission (%)")
    viator_ref = fields.Char(
        string="Réf. Viator",
        help="Identifiant produit côté catalogue Viator (si affilié).",
    )
    notes = fields.Text(
        string="Notes / script de négociation",
        help="Traçabilité de la négociation (approche évidence-first).",
    )
    signup_channel = fields.Selection(
        [
            ("manual", "Saisie interne"),
            ("site_partenaires", "Page Partenaires"),
            ("carte", "Page Carte"),
        ],
        string="Canal d’inscription",
        default="manual",
    )
    description = fields.Text(
        string="Description du lieu",
        help="Présentation fournie à l’inscription (libre-service).",
    )
    image_1920 = fields.Image(
        string="Photo principale",
        max_width=1920,
        max_height=1920,
    )
    video_url = fields.Char(
        string="URL vidéo",
        help="Lien YouTube / Vimeo / MP4 fourni à l’inscription (optionnel).",
    )
