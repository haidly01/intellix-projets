# -*- coding: utf-8 -*-
"""Vidéos liées à une fiche bien — carte publique + portail propriétaire.

Une fiche (coins.property) peut avoir des vidéos propriétaire et/ou influenceur.
Seules les vidéos `publiee` alimentent les pins de la page Carte.
"""
from datetime import timedelta

from odoo import api, fields, models


class CoinsFicheVideo(models.Model):
    _name = "coins.fiche_video"
    _description = "Vidéo de fiche (Coins Marocain)"
    _order = "ordre_affichage, id"

    fiche_id = fields.Many2one(
        "coins.property",
        string="Fiche",
        required=True,
        ondelete="cascade",
        index=True,
    )
    source = fields.Selection(
        [
            ("proprietaire", "Propriétaire"),
            ("influenceur", "Influenceur / créateur"),
        ],
        string="Source",
        required=True,
        default="proprietaire",
    )
    uploaded_by = fields.Many2one("res.partner", string="Déposé par")
    video_url = fields.Char(
        string="URL vidéo",
        required=True,
        help="URL publique (MP4, YouTube, Vimeo…) pour l’aperçu carte.",
    )
    titre = fields.Char(string="Titre court")
    date_upload = fields.Datetime(string="Date d’upload", default=fields.Datetime.now)
    statut = fields.Selection(
        [
            ("en_attente", "En attente"),
            ("publiee", "Publiée"),
            ("refusee", "Refusée"),
        ],
        string="Statut",
        default="en_attente",
        required=True,
        index=True,
    )
    ordre_affichage = fields.Integer(string="Ordre", default=10)
    view_ids = fields.One2many(
        "coins.fiche_video.view",
        "video_id",
        string="Vues",
    )
    view_count_7d = fields.Integer(
        string="Vues (7 j)",
        compute="_compute_view_count_7d",
    )

    @api.depends("view_ids.viewed_at")
    def _compute_view_count_7d(self):
        since = fields.Datetime.now() - timedelta(days=7)
        View = self.env["coins.fiche_video.view"]
        for rec in self:
            rec.view_count_7d = View.search_count([
                ("video_id", "=", rec.id),
                ("viewed_at", ">=", since),
            ])
