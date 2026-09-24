# -*- coding: utf-8 -*-
from odoo import api, fields, models
from odoo.fields import Command

from . import ix_terms
from .ix_category_video import PROSPECT_CATEGORIES

IX_CATALOG_VERSION = "19.0.2.2.0"


class SaleOrder(models.Model):
    _inherit = "sale.order"

    ix_tax_mode = fields.Selection(
        [
            ("company_default", "TVA société du devis"),
            ("with_tax", "Forcer TVA applicable"),
            ("no_tax", "Hors taxes"),
        ],
        string="Mode taxes",
        default="with_tax",
    )
    ix_client_type = fields.Selection(
        [
            ("local", "Local (Maroc)"),
            ("international", "International (US/CA)"),
        ],
        string="Type de client",
        default="local",
    )
    ix_entity = fields.Selection(
        [
            ("digital_doorway", "Digital Doorway (dh)"),
            ("agence_doorway", "Agence Doorway ($CAD)"),
        ],
        string="Entité / devise",
        default="digital_doorway",
        help="Par défaut : local → Digital Doorway, international → Agence Doorway. Forçage possible.",
    )
    ix_template_code = fields.Char(string="Modèle utilisé")
    ix_prospect_category = fields.Selection(
        PROSPECT_CATEGORIES,
        string="Secteur prospect",
        help="Détermine la vidéo explicative jointe au devis.",
    )
    ix_video_url = fields.Char(
        string="Vidéo explicative",
        help="Résolue depuis la table catégorie → vidéo. Figée à l'envoi.",
    )
    ix_prices_locked = fields.Boolean(
        string="Prix figés",
        copy=False,
        help="Activé à l'envoi : le catalogue peut changer, ce devis ne bouge plus.",
    )
    ix_catalog_version = fields.Char(string="Version catalogue", copy=False)
    ix_terms_snapshot = fields.Html(string="Clauses figées", sanitize=False, copy=False)
    ix_terms_html = fields.Html(
        string="Clauses d'entente",
        compute="_compute_ix_terms_html",
        sanitize=False,
    )

    def _compute_ix_terms_html(self):
        for order in self:
            if order.ix_prices_locked and order.ix_terms_snapshot:
                order.ix_terms_html = order.ix_terms_snapshot
            elif order.ix_entity == "agence_doorway":
                order.ix_terms_html = ix_terms.TERMS_AGENCE_DOORWAY
            else:
                order.ix_terms_html = ix_terms.TERMS_DIGITAL_DOORWAY

    @api.onchange("ix_prospect_category")
    def _onchange_ix_prospect_category(self):
        if self.ix_prices_locked:
            return
        self.ix_video_url = self.env["ix.category.video"].url_for(
            self.ix_prospect_category
        )

    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        template_id = (
            res.get("sale_order_template_id")
            or self.env.context.get("default_sale_order_template_id")
        )
        if not template_id:
            return res

        template = self.env["sale.order.template"].browse(template_id)
        if not template.exists():
            return res

        res["sale_order_template_id"] = template.id
        if template.number_of_days and "validity_date" in fields_list:
            res["validity_date"] = fields.Date.add(
                fields.Date.today(), days=template.number_of_days
            )
        if template.note and "note" in fields_list:
            res["note"] = template.note
        if hasattr(template, "ix_tax_mode") and "ix_tax_mode" in fields_list:
            res["ix_tax_mode"] = template.ix_tax_mode
        if hasattr(template, "ix_template_code") and "ix_template_code" in fields_list:
            res["ix_template_code"] = template.ix_template_code
        if "order_line" in fields_list and not res.get("order_line"):
            line_cmds = [
                Command.create(line._prepare_order_line_values())
                for line in template.sale_order_template_line_ids
            ]
            if len(line_cmds) >= 2:
                line_cmds[1][2]["sequence"] = -99
            res["order_line"] = line_cmds
        return res

    @api.onchange("ix_client_type")
    def _onchange_ix_client_type(self):
        if self.ix_client_type == "international":
            self.ix_entity = "agence_doorway"
        elif self.ix_client_type == "local":
            self.ix_entity = "digital_doorway"
        self._apply_ix_entity()

    @api.onchange("ix_entity")
    def _onchange_ix_entity(self):
        self._apply_ix_entity()

    @api.onchange("sale_order_template_id")
    def _onchange_sale_order_template_id_ix(self):
        if self.sale_order_template_id and hasattr(
            self.sale_order_template_id, "ix_tax_mode"
        ):
            self.ix_tax_mode = self.sale_order_template_id.ix_tax_mode
        if self.sale_order_template_id and getattr(
            self.sale_order_template_id, "ix_template_code", False
        ):
            self.ix_template_code = self.sale_order_template_id.ix_template_code
        self._apply_ix_tax_mode()
        self._apply_ix_entity_prices()

    @api.onchange("ix_tax_mode")
    def _onchange_ix_tax_mode(self):
        self._apply_ix_tax_mode()

    def _ix_company_for_entity(self):
        self.ensure_one()
        Company = self.env["res.company"].sudo()
        if self.ix_entity == "agence_doorway":
            return Company.search([("name", "ilike", "Agence Doorway")], limit=1)
        return Company.search([("name", "ilike", "Digital Doorway")], limit=1)

    def _ix_pricelist_for_entity(self):
        self.ensure_one()
        Pricelist = self.env["product.pricelist"].sudo()
        code = "IX-CAD" if self.ix_entity == "agence_doorway" else "IX-MAD"
        return Pricelist.search([("name", "=", code)], limit=1)

    def _ix_fiscal_position_for_entity(self):
        self.ensure_one()
        company = self.company_id or self._ix_company_for_entity()
        if not company:
            return self.env["account.fiscal.position"]
        Fiscal = self.env["account.fiscal.position"].sudo()
        if self.ix_entity == "agence_doorway":
            return Fiscal.search(
                [
                    ("company_id", "=", company.id),
                    ("active", "=", True),
                    "|",
                    ("name", "ilike", "Québec"),
                    ("name", "ilike", "Quebec"),
                ],
                limit=1,
            )
        return Fiscal.search(
            [
                ("company_id", "=", company.id),
                ("is_domestic", "=", True),
                ("active", "=", True),
            ],
            limit=1,
        )

    def _ix_sale_taxes(self):
        """TVA 20 % (Digital Doorway) ou groupe TPS+TVQ (Agence Doorway)."""
        self.ensure_one()
        company = self.company_id or self._ix_company_for_entity()
        if not company:
            return self.env["account.tax"]
        tax = company.sudo().account_sale_tax_id
        if tax and tax.type_tax_use == "sale":
            return tax
        return self.env["account.tax"].sudo().search(
            [
                ("company_id", "=", company.id),
                ("type_tax_use", "=", "sale"),
                ("active", "=", True),
            ],
            limit=1,
        )

    def _apply_ix_entity(self):
        for order in self:
            if order.ix_prices_locked:
                continue
            company = order._ix_company_for_entity()
            if company and order.company_id != company:
                order.company_id = company
            pricelist = order._ix_pricelist_for_entity()
            if pricelist:
                order.pricelist_id = pricelist
            fpos = order._ix_fiscal_position_for_entity()
            if fpos:
                order.fiscal_position_id = fpos
            order._apply_ix_entity_prices()
            order._apply_ix_tax_mode()

    def _ix_lock_quote(self):
        for order in self:
            if order.ix_prices_locked:
                continue
            if not order.ix_video_url and order.ix_prospect_category:
                order.ix_video_url = self.env["ix.category.video"].url_for(
                    order.ix_prospect_category
                )
            live_terms = (
                ix_terms.TERMS_AGENCE_DOORWAY
                if order.ix_entity == "agence_doorway"
                else ix_terms.TERMS_DIGITAL_DOORWAY
            )
            order.write(
                {
                    "ix_prices_locked": True,
                    "ix_catalog_version": IX_CATALOG_VERSION,
                    "ix_terms_snapshot": live_terms,
                }
            )

    def write(self, vals):
        res = super().write(vals)
        if vals.get("state") in ("sent", "sale"):
            self._ix_lock_quote()
        return res

    def action_quotation_send(self):
        self._ix_lock_quote()
        return super().action_quotation_send()

    def _apply_ix_entity_prices(self):
        for order in self:
            if order.ix_prices_locked:
                continue
            cad = order.ix_entity == "agence_doorway"
            for line in order.order_line.filtered(lambda l: l.product_id and not l.display_type):
                tmpl = line.product_id.product_tmpl_id
                if tmpl.ix_quote_only:
                    line.price_unit = 0.0
                    continue
                if cad:
                    line.price_unit = tmpl.ix_price_cad or 0.0
                else:
                    line.price_unit = tmpl.ix_price_mad or tmpl.list_price or 0.0

    def _apply_ix_tax_mode(self):
        for order in self:
            if order.ix_prices_locked or not order.order_line:
                continue
            if order.ix_tax_mode == "no_tax":
                order.order_line.write({"tax_ids": [(5, 0, 0)]})
                continue
            taxes = order._ix_sale_taxes()
            for line in order.order_line.filtered(
                lambda l: l.product_id and not l.display_type
            ):
                if line.product_id.product_tmpl_id.ix_quote_only:
                    line.tax_ids = [(5, 0, 0)]
                    continue
                line.tax_ids = taxes
