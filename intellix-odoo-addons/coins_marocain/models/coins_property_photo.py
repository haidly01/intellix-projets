# -*- coding: utf-8 -*-
import re

from odoo import fields, models

# Photos téléphone / brouillon — pas le set retouché à mettre en public.
_DRAFT_PHOTO_RE = re.compile(
    r"whatsapp[-_ ]?image|whatsapp|\bwa[-_]?img\b",
    re.I,
)


class CoinsPropertyPhoto(models.Model):
    _name = "coins.property.photo"
    _description = "Photo de bien (Coins Marocain)"
    _order = "sequence, id"

    property_id = fields.Many2one(
        "coins.property",
        string="Propriété",
        required=True,
        ondelete="cascade",
        index=True,
    )
    room_id = fields.Many2one(
        "coins.property.room",
        string="Chambre",
        ondelete="set null",
        index=True,
        help="Photo propre à une suite. Vide = galerie de l’établissement.",
    )
    image = fields.Image(string="Image", required=True, max_width=1920, max_height=1920)
    sequence = fields.Integer(string="Ordre", default=10)
    legende = fields.Char(string="Légende")
    category_ids = fields.Many2many(
        "coins.property.photo.category",
        "coins_property_photo_category_rel",
        "photo_id",
        "category_id",
        string="Catégories",
        help="Thèmes galerie (plusieurs possibles). Une photo liée à une chambre "
        "est aussi classée Chambres, même sans tag explicite.",
    )

    def public_category_codes(self):
        """Codes publics : tags + Chambres si la photo est assignée à une suite."""
        self.ensure_one()
        codes = [c.code for c in self.category_ids if c.code]
        if self.room_id and "chambres" not in codes:
            codes = ["chambres"] + codes
        return codes

    def _is_draft_after_retouch(self):
        """True si la légende désigne un envoi WhatsApp / photo brute."""
        self.ensure_one()
        return bool(_DRAFT_PHOTO_RE.search(self.legende or ""))
