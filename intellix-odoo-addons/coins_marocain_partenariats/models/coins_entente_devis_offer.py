# -*- coding: utf-8 -*-
import re

from markupsafe import escape

from odoo import models


class CoinsEntente(models.Model):
    _inherit = "coins.entente"

    def _coins_related_sale_order(self):
        self.ensure_one()
        return self.env["sale.order"].sudo().search(
            [("coins_entente_id", "=", self.id)], limit=1
        )

    def _coins_devis_line_title_desc(self, line):
        raw = (line.name or "").strip()
        parts = raw.split("\n", 1)
        title = parts[0].strip()
        desc = parts[1].strip() if len(parts) > 1 else ""
        code = (line.product_id.default_code or "").strip()
        if code:
            title = re.sub(
                r"^(\[%s\]\s*)+" % re.escape(code), "", title, flags=re.I
            ).strip()
        if not title:
            title = (line.product_id.name or "").strip()
            if code:
                title = re.sub(
                    r"^\[%s\]\s*" % re.escape(code), "", title, flags=re.I
                ).strip()
        return title, desc

    def _coins_format_dh(self, amount):
        return ("%0.2f" % (amount or 0.0)).replace(".", ",") + "&nbsp;DH"

    def _coins_devis_offer_html(self):
        """Lignes retenues du devis (qty > 0), telles qu'envoyées — pas les options à 0."""
        self.ensure_one()
        order = self._coins_related_sale_order()
        if not order or not hasattr(order, "_coins_selected_lines"):
            return ""
        lines = order._coins_selected_lines().sorted(lambda l: (l.sequence, l.id))
        if not lines:
            return ""
        blocks = []
        for line in lines:
            title, desc = self._coins_devis_line_title_desc(line)
            price_bits = ["%s HT" % self._coins_format_dh(line.price_subtotal)]
            if line.price_tax:
                tax = line.tax_ids[:1]
                if tax and tax.amount:
                    tax_label = "TVA %s&nbsp;%%" % (
                        int(tax.amount) if float(tax.amount).is_integer() else tax.amount
                    )
                else:
                    tax_label = "TVA"
                price_bits.append(
                    "%s %s" % (self._coins_format_dh(line.price_tax), tax_label)
                )
                price_bits.append("%s TTC" % self._coins_format_dh(line.price_total))
            price = " · ".join(str(b) for b in price_bits)
            desc_html = ""
            if desc:
                desc_html = (
                    '<div style="font-size:13px;color:#5C4D38;line-height:1.65;'
                    'margin-top:6px;white-space:pre-wrap;">%s</div>'
                    % escape(desc)
                )
            blocks.append(
                '<div style="margin:0 0 16px;padding:0 0 16px;'
                'border-bottom:1px solid #E4D6B0;">'
                '<div style="font-family:\'Cormorant Garamond\',Georgia,serif;'
                'font-weight:600;font-size:16.5px;color:#3A2E1F;">%s</div>'
                '<div style="font-size:12px;color:#8A6A2F;margin-top:4px;">%s</div>'
                "%s</div>"
                % (escape(title), price, desc_html)
            )
        if not blocks:
            return ""
        if blocks:
            blocks[-1] = blocks[-1].replace(
                "border-bottom:1px solid #E4D6B0;", "border-bottom:none;"
            )
        ref = escape(order.name or "")
        return (
            '<div data-coins-devis-offer="1" style="background:#F8F2E4;'
            'border:1px solid #E4D6B0;border-radius:8px;padding:22px 24px;'
            'margin:0 0 22px;">'
            '<div style="font-size:10.5px;letter-spacing:.15em;text-transform:uppercase;'
            'color:#C9A227;margin-bottom:14px;font-weight:600;">'
            "Offre — devis %s</div>%s</div>"
            % (ref, "".join(blocks))
        )

    def _get_signature_html(self):
        html = super()._get_signature_html()
        offer = self._coins_devis_offer_html()
        if offer and "data-coins-devis-offer" not in (html or ""):
            return offer + (html or "")
        return html
