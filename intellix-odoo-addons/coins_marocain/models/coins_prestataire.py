# -*- coding: utf-8 -*-
from odoo import fields, models


class CoinsPrestataireTag(models.Model):
    _name = "coins.prestataire.tag"
    _description = "Tag spécialité prestataire événements"
    _order = "name"

    name = fields.Char(required=True, translate=True)
    code = fields.Char(
        string="Code",
        help="Identifiant stable pour le filtrage automatique (ex. mariage, piscine).",
        index=True,
    )
    active = fields.Boolean(default=True)

    _sql_constraints = [
        ("code_uniq", "unique(code)", "Le code de tag doit être unique."),
    ]


class CoinsEventActivite(models.Model):
    _name = "coins.event.activite"
    _description = "Activité souhaitée (brief lead événement)"
    _order = "sequence, name"

    name = fields.Char(required=True, translate=True)
    code = fields.Char(required=True, index=True)
    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True)

    _sql_constraints = [
        ("code_uniq", "unique(code)", "Le code d’activité doit être unique."),
    ]


class CoinsPrestataire(models.Model):
    _name = "coins.prestataire"
    _description = "Catalogue prestataire événements (CRM)"
    _order = "category, name"

    name = fields.Char(required=True)
    active = fields.Boolean(default=True)
    category = fields.Selection(
        [
            ("traiteur", "Traiteur"),
            ("fleuriste", "Fleuriste"),
            ("dj", "DJ"),
            ("photographe", "Photographe"),
            ("videaste", "Vidéaste"),
            ("excursion", "Excursion"),
            ("spa", "Spa"),
            ("transport", "Transport"),
            ("lieu", "Lieu"),
        ],
        string="Catégorie",
        required=True,
        index=True,
    )
    zone_couverture = fields.Char(
        string="Zone de couverture",
        help="Ex. Marrakech, Ourika, Agafay…",
    )
    specialite_tag_ids = fields.Many2many(
        "coins.prestataire.tag",
        "coins_prestataire_tag_rel",
        "prestataire_id",
        "tag_id",
        string="Spécialités / tags",
    )
    partner_id = fields.Many2one("res.partner", string="Contact", ondelete="set null")
    notes = fields.Text(string="Notes")
    disponibilite = fields.Selection(
        [
            ("disponible", "Disponible"),
            ("limite", "Disponibilité limitée"),
            ("indisponible", "Indisponible"),
        ],
        string="Disponibilité",
        default="disponible",
    )
