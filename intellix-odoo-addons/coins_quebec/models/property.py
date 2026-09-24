# -*- coding: utf-8 -*-
from odoo import _, api, fields, models
from odoo.exceptions import UserError


class CoinsQuebecPropertyCategory(models.Model):
    _name = "coins.quebec.property.category"
    _description = "Catégorie de bien (Coins Québec)"
    _order = "sequence, name"

    name = fields.Char(required=True)
    code = fields.Char(required=True, index=True)
    sequence = fields.Integer(default=10)
    description = fields.Text()
    active = fields.Boolean(default=True)


class CoinsQuebecProperty(models.Model):
    _name = "coins.quebec.property"
    _description = "Bien (Coins Québec)"
    _inherit = ["mail.thread", "mail.activity.mixin", "coins.quebec.cad.mixin"]
    _order = "name"

    name = fields.Char(string="Nom du bien", required=True, tracking=True)
    active = fields.Boolean(default=True)
    property_type = fields.Selection(
        [
            ("gite", "Gîte / maison d'hôte"),
            ("chalet", "Chalet"),
            ("auberge", "Auberge"),
            ("villa", "Villa"),
            ("apartment", "Appartement"),
            ("riad", "Riad"),
            ("pool_hammam", "Spa / détente"),
            ("other", "Autre"),
        ],
        string="Type",
        default="gite",
        required=True,
    )
    state = fields.Selection(
        [
            ("negotiating", "En négociation"),
            ("active", "Actif"),
            ("inactive", "Inactif"),
        ],
        string="Statut",
        default="negotiating",
        required=True,
        tracking=True,
    )
    street = fields.Char(string="Adresse")
    district = fields.Char(string="Quartier")
    city = fields.Char(string="Ville", default="Montréal")
    province = fields.Char(string="Province", default="Québec")
    country_id = fields.Many2one(
        "res.country",
        string="Pays",
        default=lambda self: self.env.ref("base.ca", raise_if_not_found=False),
    )
    category_ids = fields.Many2many(
        "coins.quebec.property.category",
        "coins_quebec_property_category_rel",
        "property_id",
        "category_id",
        string="Catégories",
        help="Découverte, Privatisation, Événements, Bien-être, Hébergement — même structure que Coins Marocain.",
    )
    owner_id = fields.Many2one("res.partner", string="Propriétaire")
    phone = fields.Char()
    email = fields.Char()
    nb_chambres = fields.Integer(string="Chambres")
    location_chambre_unite = fields.Boolean(string="Location à la chambre / suite")
    currency_id = fields.Many2one(
        "res.currency",
        default=lambda self: self._cq_cad().id,
        required=True,
    )
    tarif_nuit = fields.Monetary(string="Tarif / nuit", currency_field="currency_id")
    tarif_privatisation_jour = fields.Monetary(
        string="Tarif privatisation / jour",
        currency_field="currency_id",
    )
    commission_pct = fields.Float(string="Commission (%)", default=15.0)
    notes = fields.Text()
    reservation_ids = fields.One2many(
        "coins.quebec.reservation", "property_id", string="Réservations"
    )
    reservation_count = fields.Integer(compute="_compute_reservation_count")
    is_demo = fields.Boolean(
        string="Bien démo Mon Coin",
        default=False,
        index=True,
        copy=False,
    )

    @api.depends("reservation_ids")
    def _compute_reservation_count(self):
        for rec in self:
            rec.reservation_count = len(rec.reservation_ids)

    def unlink(self):
        blocked = self.filtered(
            lambda r: "gîte test coins québec" in (r.name or "").strip().lower()
            or "gite test coins quebec" in (r.name or "").strip().lower()
        )
        if blocked:
            raise UserError(
                _("Le bien « Gîte test Coins Québec » est protégé et ne peut pas être supprimé.")
            )
        return super().unlink()
