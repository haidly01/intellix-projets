# -*- coding: utf-8 -*-

from odoo import api, fields, models


class IntellixRiadMenuItem(models.Model):
    _name = "intellix.riad.menu.item"
    _description = "Catalogue soins / restaurant (établissement)"
    _order = "kind, sequence, id"

    name = fields.Char(required=True)
    code = fields.Char(index=True)
    kind = fields.Selection(
        [
            ("wellness", "Soin bien-être / beauté"),
            ("restaurant", "Restaurant / terrasse"),
        ],
        required=True,
        index=True,
    )
    establishment_id = fields.Many2one(
        "intellix.riad.establishment",
        required=True,
        ondelete="cascade",
        index=True,
    )
    company_id = fields.Many2one(
        "res.company",
        string="Société",
        required=True,
        index=True,
        ondelete="restrict",
        help="Catalogue isolé par société. Jamais partagé avec IntelliX / Doorway / Coins.",
    )
    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True)
    description = fields.Text()
    type_id = fields.Many2one(
        "intellix.riad.wellness.type",
        string="Type de soin",
        ondelete="set null",
    )
    category = fields.Selection(
        [
            ("massage", "Massage"),
            ("hammam", "Hammam"),
            ("esthetique", "Esthétique"),
            ("ongles", "Ongles"),
            ("brushing", "Brushing"),
            ("formule", "Formule"),
            ("entree", "Entrée"),
            ("plat", "Plat"),
            ("dessert", "Dessert"),
            ("boisson", "Boisson"),
        ],
        string="Catégorie",
    )
    duration_minutes = fields.Integer(string="Durée (min)")
    currency_id = fields.Many2one(
        "res.currency",
        default=lambda self: self._default_currency(),
    )
    price = fields.Monetary(string="Prix", currency_field="currency_id")
    included_in_half_board = fields.Boolean(
        string="Inclus demi-pension",
        help="Visible comme formule / plat couvert par la demi-pension résidente.",
    )
    space_mode = fields.Selection(
        [
            ("wellness", "Mode transats / tables de massage (journée)"),
            ("restaurant", "Mode restaurant (soir)"),
            ("both", "Les deux modes"),
        ],
        string="Mode d'espace",
        required=True,
        default="restaurant",
    )

    _sql_constraints = [
        (
            "code_estab_uniq",
            "unique(establishment_id, code)",
            "Ce code existe déjà pour cet établissement.",
        ),
    ]

    def _default_currency(self):
        mad = self.env["res.currency"].search([("name", "=", "MAD")], limit=1)
        return mad.id if mad else self.env.company.currency_id.id

    @api.onchange("establishment_id")
    def _onchange_establishment_company(self):
        for rec in self:
            if rec.establishment_id and rec.establishment_id.company_id:
                rec.company_id = rec.establishment_id.company_id

    @api.model_create_multi
    def create(self, vals_list):
        Estab = self.env["intellix.riad.establishment"]
        for vals in vals_list:
            estab = False
            if vals.get("establishment_id"):
                estab = Estab.browse(vals["establishment_id"])
                if estab and not estab.company_id:
                    estab.sudo()._ensure_anna_sweety_company()
                    estab.invalidate_recordset(["company_id"])
            if estab and not vals.get("company_id") and estab.company_id:
                vals["company_id"] = estab.company_id.id
        return super().create(vals_list)

    def duration_label(self):
        self.ensure_one()
        if not self.duration_minutes:
            return ""
        hours, minutes = divmod(int(self.duration_minutes), 60)
        if hours and minutes:
            return "%sh%02d" % (hours, minutes)
        if hours:
            return "%sh" % hours
        return "%s min" % minutes

    def price_label(self):
        self.ensure_one()
        symbol = self.currency_id.symbol or self.currency_id.name or ""
        amount = self.price or 0
        if self.included_in_half_board and self.kind == "restaurant":
            if amount:
                return "Inclus demi-pension · %s %s hors formule" % (
                    int(amount) if amount == int(amount) else amount,
                    symbol,
                )
            return "Inclus demi-pension"
        if amount == int(amount):
            return "%s %s" % (int(amount), symbol)
        return "%s %s" % (amount, symbol)

    def catalog_row(self):
        self.ensure_one()
        return {
            "id": self.id,
            "name": self.name,
            "kind": self.kind,
            "company": self.company_id.name or "",
            "company_id": self.company_id.id,
            "establishment": self.establishment_id.name or "",
            "category": dict(self._fields["category"].selection).get(self.category)
            or "",
            "category_key": self.category or "",
            "type_id": self.type_id.id if self.type_id else False,
            "type_name": self.type_id.name or "",
            "duration": self.duration_label(),
            "duration_minutes": self.duration_minutes or 0,
            "price": self.price or 0,
            "price_label": self.price_label(),
            "included_in_half_board": bool(self.included_in_half_board),
            "space_mode": self.space_mode,
            "space_mode_label": dict(self._fields["space_mode"].selection).get(
                self.space_mode
            )
            or "",
            "description": self.description or "",
        }

    @api.model
    def catalog_for_establishment(self, establishment, kind=None, space_mode=None):
        if not establishment:
            return self.browse()
        domain = [
            ("establishment_id", "=", establishment.id),
            ("active", "=", True),
        ]
        if kind:
            domain.append(("kind", "=", kind))
        items = self.search(domain, order="sequence, id")
        if space_mode and space_mode in ("wellness", "restaurant"):
            items = items.filtered(
                lambda rec: rec.space_mode in (space_mode, "both")
            )
        return items

    @api.model
    def payload_for_establishment(self, establishment, kind=None, space_mode=None):
        return [
            rec.catalog_row()
            for rec in self.catalog_for_establishment(
                establishment, kind=kind, space_mode=space_mode
            )
        ]

    @api.model
    def _seed_anna_sweety_menus(self):
        """Catalogue initial Riad Anna Sweety uniquement. N'écrase pas un menu déjà saisi."""
        estab = (
            self.env["intellix.riad.establishment"]
            .sudo()
            .search([("name", "=", "Riad Anna Sweety")], limit=1)
        )
        if not estab:
            return True
        if not estab.company_id:
            estab.sudo()._ensure_anna_sweety_company()
            estab.invalidate_recordset(["company_id"])
        company = estab.company_id
        if not company:
            return True
        existing = self.sudo().search([("establishment_id", "=", estab.id)])
        if existing:
            orphans = existing.filtered(
                lambda rec: rec.company_id != company
            )
            if orphans:
                orphans.write({"company_id": company.id})
            return True
        Type = self.env["intellix.riad.wellness.type"]
        by_code = {row.code: row for row in Type.search([])}
        mad = self.env["res.currency"].search([("name", "=", "MAD")], limit=1)
        currency = mad or company.currency_id
        rows = [
            {
                "code": "massage_60",
                "kind": "wellness",
                "name": "Massage relaxant",
                "category": "massage",
                "type_id": by_code.get("massage") and by_code["massage"].id,
                "duration_minutes": 60,
                "price": 500,
                "space_mode": "wellness",
                "sequence": 10,
                "description": "Massage à l'huile sur table, terrasse en journée.",
            },
            {
                "code": "massage_90",
                "kind": "wellness",
                "name": "Massage long",
                "category": "massage",
                "type_id": by_code.get("massage") and by_code["massage"].id,
                "duration_minutes": 90,
                "price": 700,
                "space_mode": "wellness",
                "sequence": 20,
            },
            {
                "code": "hammam_45",
                "kind": "wellness",
                "name": "Hammam + gommage",
                "category": "hammam",
                "type_id": by_code.get("hammam") and by_code["hammam"].id,
                "duration_minutes": 45,
                "price": 350,
                "space_mode": "wellness",
                "sequence": 30,
            },
            {
                "code": "manucure",
                "kind": "wellness",
                "name": "Manucure",
                "category": "ongles",
                "type_id": by_code.get("ongles") and by_code["ongles"].id,
                "duration_minutes": 40,
                "price": 200,
                "space_mode": "wellness",
                "sequence": 40,
            },
            {
                "code": "pedicure",
                "kind": "wellness",
                "name": "Pédicure",
                "category": "ongles",
                "type_id": by_code.get("ongles") and by_code["ongles"].id,
                "duration_minutes": 50,
                "price": 250,
                "space_mode": "wellness",
                "sequence": 50,
            },
            {
                "code": "brushing",
                "kind": "wellness",
                "name": "Brushing",
                "category": "brushing",
                "type_id": by_code.get("brushing") and by_code["brushing"].id,
                "duration_minutes": 30,
                "price": 180,
                "space_mode": "wellness",
                "sequence": 60,
            },
            {
                "code": "soin_visage",
                "kind": "wellness",
                "name": "Soin visage",
                "category": "esthetique",
                "type_id": by_code.get("esthetique") and by_code["esthetique"].id,
                "duration_minutes": 45,
                "price": 300,
                "space_mode": "wellness",
                "sequence": 70,
            },
            {
                "code": "dp_diner",
                "kind": "restaurant",
                "name": "Formule demi-pension — dîner",
                "category": "formule",
                "price": 0,
                "included_in_half_board": True,
                "space_mode": "restaurant",
                "sequence": 10,
                "description": "Entrée + plat + dessert pour les résidentes en demi-pension.",
            },
            {
                "code": "salade_marocaine",
                "kind": "restaurant",
                "name": "Salade marocaine",
                "category": "entree",
                "price": 70,
                "included_in_half_board": True,
                "space_mode": "restaurant",
                "sequence": 20,
            },
            {
                "code": "tajine_poulet",
                "kind": "restaurant",
                "name": "Tajine poulet citron olives",
                "category": "plat",
                "price": 140,
                "included_in_half_board": True,
                "space_mode": "restaurant",
                "sequence": 30,
            },
            {
                "code": "tajine_legumes",
                "kind": "restaurant",
                "name": "Tajine de légumes",
                "category": "plat",
                "price": 120,
                "included_in_half_board": True,
                "space_mode": "restaurant",
                "sequence": 40,
            },
            {
                "code": "orange_cannelle",
                "kind": "restaurant",
                "name": "Orange à la cannelle",
                "category": "dessert",
                "price": 40,
                "included_in_half_board": True,
                "space_mode": "restaurant",
                "sequence": 50,
            },
            {
                "code": "the_menthe",
                "kind": "restaurant",
                "name": "Thé à la menthe",
                "category": "boisson",
                "price": 25,
                "space_mode": "both",
                "sequence": 60,
                "description": "Servi en journée sur les transats et au dîner.",
            },
        ]
        for row in rows:
            row.update(
                {
                    "establishment_id": estab.id,
                    "company_id": company.id,
                    "currency_id": currency.id,
                }
            )
        self.sudo().create(rows)
        return True
