# -*- coding: utf-8 -*-
from odoo import _, api, fields, models


class SaleOrderTemplate(models.Model):
    _inherit = "sale.order.template"

    ix_tax_mode = fields.Selection(
        [
            ("company_default", "TVA société du devis"),
            ("with_tax", "Forcer TVA applicable"),
            ("no_tax", "Hors taxes"),
        ],
        string="Mode taxes",
        default="with_tax",
        help="Appliqué lors de la création d'un devis depuis ce modèle.",
    )
    ix_line_count = fields.Integer(
        string="Lignes produits",
        compute="_compute_ix_display_info",
    )
    ix_product_summary = fields.Char(
        string="Aperçu produits",
        compute="_compute_ix_display_info",
    )
    ix_category_label = fields.Char(
        string="Catégorie",
        compute="_compute_ix_display_info",
    )
    ix_template_code = fields.Char(string="Code modèle")

    @api.depends("sale_order_template_line_ids", "sale_order_template_line_ids.product_id", "name")
    def _compute_ix_display_info(self):
        for template in self:
            product_lines = template.sale_order_template_line_ids.filtered(
                lambda line: not line.display_type and line.product_id
            )
            template.ix_line_count = len(product_lines)
            names = product_lines.mapped("product_id.display_name")
            if len(names) > 2:
                template.ix_product_summary = f"{names[0]}, {names[1]}… (+{len(names) - 2})"
            else:
                template.ix_product_summary = ", ".join(names) or _("Aucun produit")

            name_lower = (template.name or "").lower()
            if "présence" in name_lower or "presence" in name_lower:
                template.ix_category_label = "Présence digitale"
            elif "croissance" in name_lower:
                template.ix_category_label = "Croissance IA"
            elif "starter" in name_lower:
                template.ix_category_label = "Starter"
            else:
                template.ix_category_label = "Intellix"

    def action_ix_create_quotation(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": _("Nouveau devis"),
            "res_model": "sale.order",
            "view_mode": "form",
            "target": "current",
            "context": {
                "default_sale_order_template_id": self.id,
            },
        }
