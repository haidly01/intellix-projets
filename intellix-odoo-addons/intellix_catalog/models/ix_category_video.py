# -*- coding: utf-8 -*-
from odoo import api, fields, models

PROSPECT_CATEGORIES = [
    ("hotel_hebergement", "Hôtels / Hébergement"),
    ("restauration", "Restauration"),
    ("bien_etre", "Bien-être"),
    ("divertissement_evenementiel", "Divertissement / Événementiel"),
]


class IxCategoryVideo(models.Model):
    _name = "ix.category.video"
    _description = "Vidéo explicative devis (catégorie prospect)"
    _order = "category"

    category = fields.Selection(
        PROSPECT_CATEGORIES,
        string="Catégorie prospect",
        required=True,
    )
    video_url = fields.Char(
        string="Lien vidéo",
        help="HeyGen, Vimeo ou hébergeur propre. Les devis déjà envoyés gardent leur URL figée.",
    )
    updated_at = fields.Datetime(string="Mis à jour", readonly=True)

    _sql_constraints = [
        (
            "ix_category_video_unique",
            "unique(category)",
            "Une seule vidéo par catégorie prospect.",
        )
    ]

    @api.model
    def url_for(self, category):
        if not category:
            return ""
        rec = self.search([("category", "=", category)], limit=1)
        return (rec.video_url or "").strip()

    def write(self, vals):
        vals = dict(vals)
        vals["updated_at"] = fields.Datetime.now()
        return super().write(vals)
