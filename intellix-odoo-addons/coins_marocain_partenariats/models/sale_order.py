# -*- coding: utf-8 -*-
from odoo import api, fields, models, _
from odoo.exceptions import UserError

DIGITAL_COMM_CODES = {"CM_DIGITAL_COMM", "CQ_DIGITAL_COMM"}
DIGITAL_FIXE_CODES = {"CM_DIGITAL_FIXE", "CQ_DIGITAL_FIXE"}
VISIBILITE_CODES = {"CM_VISIBILITE", "CQ_VISIBILITE"}
SHOOTING_CODES = {
    "CM_SOCIAL_SHOOTING",
    "CM_SHOOTING_SEUL",
    "CQ_SOCIAL_SHOOTING",
    "CQ_SHOOTING_SEUL",
}
CHANNEX_CODES = {"CM_CHANNEX", "CQ_CHANNEX"}
PACK_EXTRA_CODES = DIGITAL_COMM_CODES | DIGITAL_FIXE_CODES | SHOOTING_CODES | CHANNEX_CODES


class SaleOrder(models.Model):
    _inherit = "sale.order"

    partner_id = fields.Many2one(
        domain=lambda self: self._coins_devis_partner_domain()
    )

    @api.model
    def _coins_restrict_devis_partners(self):
        user = self.env.user
        if user.has_group(
            "coins_marocain_partenariats.group_devis_own_contacts"
        ) or user.has_group("coins_marocain_partenariats.group_devis_workspace"):
            return True
        if user.has_group("sales_team.group_sale_manager") or user.has_group(
            "base.group_system"
        ):
            return False
        return bool(
            user.has_group("sales_team.group_sale_salesman")
            or user.has_group("sales_team.group_sale_salesman_all_leads")
            or user.has_group(
                "renovation_conciergerie.group_doorway_pipeline_assigned"
            )
        )

    @api.model
    def _coins_devis_partner_domain(self):
        if not self._coins_restrict_devis_partners():
            return []
        uid = self.env.user.id
        return [
            "|",
            "|",
            "|",
            "|",
            "|",
            ("create_uid", "=", uid),
            ("user_id", "=", uid),
            ("id", "=", self.env.user.partner_id.id),
            ("parent_id.user_id", "=", uid),
            ("opportunity_ids.user_id", "=", uid),
            ("sale_order_ids.user_id", "=", uid),
        ]

    coins_entente_id = fields.Many2one(
        "coins.entente",
        string="Entente Coins",
        copy=False,
        ondelete="set null",
    )

    def _coins_quote_is_quebec(self):
        self.ensure_one()
        code = getattr(self, "ix_template_code", "") or ""
        if code.startswith("coins_quebec"):
            return True
        if getattr(self, "ix_entity", "") == "agence_doorway":
            return True
        return any(
            (c or "").startswith("CQ_")
            for c in self.order_line.mapped("product_id.default_code")
        )

    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        template_id = res.get("sale_order_template_id") or self.env.context.get(
            "default_sale_order_template_id"
        )
        if not template_id:
            return res
        template = self.env["sale.order.template"].browse(template_id)
        code = getattr(template, "ix_template_code", "") or ""
        curr = getattr(template, "currency_id", False)
        curr_name = curr.name if curr else ""
        if code.startswith("coins_quebec"):
            if "ix_entity" in fields_list or "ix_entity" in res:
                res["ix_entity"] = "agence_doorway"
            if "ix_client_type" in fields_list or "ix_client_type" in res:
                res["ix_client_type"] = "international"
        elif curr_name == "MAD" or code == "coins_visibilite":
            if "ix_entity" in fields_list or "ix_entity" in res:
                res["ix_entity"] = "digital_doorway"
            if "ix_client_type" in fields_list or "ix_client_type" in res:
                res["ix_client_type"] = "local"
            pl = self.env["product.pricelist"].sudo().search(
                [("name", "=", "IX-MAD")], limit=1
            )
            if pl and ("pricelist_id" in fields_list or "pricelist_id" in res):
                res["pricelist_id"] = pl.id
        return res

    def _coins_apply_template_currency(self):
        """Force MAD/DH on the Coins Marocain visibilité template (never CAD/EUR)."""
        for order in self:
            tmpl = order.sale_order_template_id
            if not tmpl:
                continue
            code = getattr(tmpl, "ix_template_code", "") or ""
            curr = getattr(tmpl, "currency_id", False)
            curr_name = curr.name if curr else ""
            if curr_name != "MAD" and code != "coins_visibilite":
                continue
            order.ix_entity = "digital_doorway"
            order.ix_client_type = "local"
            if hasattr(order, "_ix_pricelist_for_entity"):
                pl = order._ix_pricelist_for_entity()
                if pl:
                    order.pricelist_id = pl
            if hasattr(order, "_apply_ix_entity_prices"):
                order._apply_ix_entity_prices()

    @api.model_create_multi
    def create(self, vals_list):
        orders = super().create(vals_list)
        orders._coins_apply_template_currency()
        return orders

    @api.onchange("sale_order_template_id", "partner_id")
    def _onchange_coins_template_currency(self):
        self._coins_apply_template_currency()

    def _coins_selected_lines(self):
        """Lignes réellement retenues : qty > 0. Les options Odoo 19 restent à 0 tant qu'on ne les active pas."""
        self.ensure_one()
        return self.order_line.filtered(
            lambda line: line.product_id
            and not line.display_type
            and line.product_uom_qty > 0
        )

    def _coins_selected_codes(self):
        return set(
            code
            for code in self._coins_selected_lines().mapped("product_id.default_code")
            if code
        )

    def _coins_drop_digital_conflict(self):
        """FIXE et COMM ne cohabitent pas : si le forfait est choisi, on retire le 10 %."""
        for order in self:
            codes = order._coins_selected_codes()
            if codes & DIGITAL_COMM_CODES and codes & DIGITAL_FIXE_CODES:
                comm = order._coins_selected_lines().filtered(
                    lambda line: line.product_id.default_code in DIGITAL_COMM_CODES
                )
                comm.unlink()

    @api.onchange("order_line")
    def _onchange_coins_digital_exclusive(self):
        self._coins_drop_digital_conflict()

    def _coins_commission_snapshot(self):
        self.ensure_one()
        parts = []
        pct = 0.0
        for line in self._coins_selected_lines():
            tmpl = line.product_id.product_tmpl_id
            code = line.product_id.default_code or ""
            if tmpl.coins_commission_pct:
                if code in VISIBILITE_CODES or not pct:
                    pct = tmpl.coins_commission_pct
                parts.append(
                    "%s %s %%"
                    % (tmpl.name.split("]")[-1].strip() or code, int(tmpl.coins_commission_pct))
                )
            elif code == "CQ_DIGITAL_FIXE":
                parts.append("Digitalisation 199 $ CAD/mois")
            elif code == "CM_DIGITAL_FIXE":
                parts.append("Digitalisation 1 500 DH/mois")
        return pct, " + ".join(parts) if parts else ""

    def _coins_quote_is_visibilite_only(self):
        """Devis visibilité 15 % seule — pas de Channex, shooting ni digitalisation."""
        self.ensure_one()
        code = getattr(self, "ix_template_code", "") or ""
        if not code and self.sale_order_template_id:
            code = getattr(self.sale_order_template_id, "ix_template_code", "") or ""
        if code in ("coins_digitalisation", "coins_presence_complete") or code.startswith(
            "coins_quebec"
        ):
            return False
        codes = self._coins_selected_codes()
        if codes & PACK_EXTRA_CODES:
            return False
        if codes & VISIBILITE_CODES:
            return True
        return code == "coins_visibilite"

    def _coins_sync_entente_from_quote(self):
        Lead = self.env["crm.lead"]
        Entente = self.env["coins.entente"]
        for order in self:
            lead = order.opportunity_id
            if not lead:
                lead = Lead.search(
                    [("coins_sale_order_id", "=", order.id)], limit=1
                )
            if not lead or not lead.coins_is_partner_lead:
                continue
            codes = order._coins_selected_codes()
            if codes & DIGITAL_COMM_CODES and codes & DIGITAL_FIXE_CODES:
                raise UserError(
                    _(
                        "Digitalisation : choisissez 10 % des réservations "
                        "ou le forfait mensuel, pas les deux."
                    )
                )
            pct, modele = order._coins_commission_snapshot()
            lead.sudo().write(
                {
                    "coins_sale_order_id": order.id,
                    "coins_commission_pct": pct or lead.coins_commission_pct,
                    "coins_commission_modele": modele or lead.coins_commission_modele,
                }
            )
            quebec = order._coins_quote_is_quebec()
            if not quebec and hasattr(lead, "_coins_is_quebec_market"):
                quebec = bool(lead._coins_is_quebec_market())
            vals = {
                "type_partenaire": lead.coins_type_partenaire or "hebergement",
                "partenaire_nom": lead.contact_name or lead.partner_name or lead.name,
                "etablissement": lead.coins_etablissement or lead.partner_name or lead.name,
                "contact_partenaire": lead.email_from or lead.coins_whatsapp or lead.phone,
                "pourcentage_commission": pct or lead.coins_commission_pct,
                "shooting_souhaite": lead.coins_interet_shooting
                or bool(codes & SHOOTING_CODES),
                "partner_id": lead.partner_id.id,
                "notes": modele or "",
                "type_remuneration": "commission" if pct else "forfait",
            }
            if quebec:
                vals["notes"] = ((modele or "") + " — Coins Québec CAD").strip(" —")
            visib = (not quebec) and order._coins_quote_is_visibilite_only()
            if visib:
                vals["shooting_souhaite"] = False
            entente = order.coins_entente_id or lead.coins_entente_id
            if entente:
                if not entente.date_signature:
                    if visib:
                        vals["clauses_html"] = entente._coins_render_visibilite_cm(vals)
                    elif quebec:
                        vals["clauses_html"] = entente._coins_default_clauses_html_from_vals(
                            vals
                        )
                    entente.sudo().write(vals)
            else:
                if visib:
                    vals["clauses_html"] = Entente._coins_render_visibilite_cm(vals)
                elif quebec:
                    vals["clauses_html"] = Entente._coins_default_clauses_html_from_vals(
                        vals
                    )
                entente = Entente.sudo().create(vals)
            order.sudo().write({"coins_entente_id": entente.id})
            lead.sudo().write({"coins_entente_id": entente.id})
            if not entente.signature_id and not entente.date_signature:
                entente.sudo()._coins_prepare_signature()

    def action_confirm(self):
        self._coins_drop_digital_conflict()
        res = super().action_confirm()
        self._coins_sync_entente_from_quote()
        return res


class SaleOrderTemplate(models.Model):
    _inherit = "sale.order.template"

    currency_id = fields.Many2one(
        "res.currency",
        string="Devise",
        help="Devise forcée à la création d'un devis depuis ce modèle (MAD/DH pour Coins Marocain).",
    )

    @api.depends(
        "sale_order_template_line_ids",
        "sale_order_template_line_ids.product_id",
        "name",
    )
    def _compute_ix_display_info(self):
        super()._compute_ix_display_info()
        for template in self:
            code = getattr(template, "ix_template_code", "") or ""
            if code.startswith("coins_quebec"):
                template.ix_category_label = "Coins Québec"
            elif code.startswith("coins_"):
                template.ix_category_label = "Coins Marocain"
