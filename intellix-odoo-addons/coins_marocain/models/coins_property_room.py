# -*- coding: utf-8 -*-
from odoo import _, api, fields, models
from odoo.exceptions import ValidationError

from .room_public_copy import is_internal_draft, public_room_description


class CoinsPropertyRoom(models.Model):
    _name = "coins.property.room"
    _description = "Chambre d'un bien (Coins Marocain)"
    _order = "sequence, id"

    property_id = fields.Many2one(
        "coins.property",
        string="Bien",
        required=True,
        ondelete="cascade",
        index=True,
    )
    name = fields.Char(string="Nom de la chambre", required=True)
    sleeps = fields.Integer(
        string="Couchages",
        required=True,
        default=2,
        help="Nombre de personnes pouvant dormir dans cette chambre.",
    )
    description = fields.Text(string="Description")
    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True)

    def _reject_draft_description(self, vals):
        if "description" not in vals:
            return vals
        raw = vals.get("description") or ""
        if is_internal_draft(raw):
            raise ValidationError(
                _(
                    "Cette description de chambre contient une notice interne "
                    "(brouillon). Elle ne peut pas être publiée. Écrivez un "
                    "texte court pour le voyageur, ou laissez le champ vide."
                )
            )
        vals = dict(vals)
        vals["description"] = public_room_description(raw) or False
        return vals

    @api.model_create_multi
    def create(self, vals_list):
        cleaned = [self._reject_draft_description(vals) for vals in vals_list]
        return super().create(cleaned)

    def write(self, vals):
        vals = self._reject_draft_description(vals)
        return super().write(vals)

    @api.constrains("description")
    def _check_public_room_description(self):
        for rec in self:
            if is_internal_draft(rec.description or ""):
                raise ValidationError(
                    _(
                        "Chambre « %s » : description interne, non publiable."
                    )
                    % (rec.name or rec.id)
                )
