# -*- coding: utf-8 -*-
from odoo import _, fields, models
from odoo.exceptions import UserError

from .product_template import SETUP_500_CODE, SETUP_BOUTIQUE_CODE, SPLIT_MAP

PALIER_CODES = {
    "fiche": "MC_FICHE",
    "connexion": "MC_PALIER_CONNEXION",
    "mesure": "MC_PALIER_MESURE",
    "complet": "MC_PALIER_COMPLET",
}

PAID_PALIERS = ("connexion", "mesure", "complet")


class CoinsQuebecPartenariatCatalog(models.Model):
    _inherit = "coins.quebec.partenariat"

    mon_coin_palier = fields.Selection(
        [
            ("none", "Aucun"),
            ("fiche", "Ma fiche (0$)"),
            ("connexion", "Connexion (50$/mois)"),
            ("mesure", "Mesure (150$/mois)"),
            ("complet", "Complet (250$/mois)"),
        ],
        string="Palier Mon Coin",
        default="none",
        tracking=True,
        copy=False,
    )
    mon_coin_startup_fee_kind = fields.Selection(
        [
            ("none", "Aucun"),
            ("clover_500", "500$ — paliers sans boutique"),
            ("boutique_1000", "1000$ — parcours Boutique (à la place du 500$)"),
        ],
        string="Frais de démarrage retenu",
        default="none",
        tracking=True,
        copy=False,
        help="Exclusif : 1000$ Boutique remplace le 500$, jamais les deux.",
    )
    mon_coin_startup_fee_invoiced = fields.Boolean(
        string="Frais de démarrage déjà facturé",
        default=False,
        copy=False,
        tracking=True,
    )
    mon_coin_boutique_activated = fields.Boolean(
        string="Boutique en ligne activée",
        default=False,
        copy=False,
        tracking=True,
        help="Seuil produits actifs / canaux marketplace. "
        "Le palier Complet sans canal activé ne déclenche pas le 1000$.",
    )
    mon_coin_sale_order_ids = fields.One2many(
        "sale.order", "cq_partenariat_id", string="Devis / commandes Mon Coin"
    )

    def _cq_product_by_code(self, code):
        tmpl = self.env["product.template"].sudo().search(
            [("default_code", "=", code)], limit=1
        )
        return tmpl.product_variant_id if tmpl else self.env["product.product"]

    def _cq_startup_fee_product(self, boutique_path=False):
        """Un seul one-shot. 1000$ Boutique remplace le 500$ ; jamais les deux.

        Manuel encore : le bouton « Créer le devis palier » ajoute la ligne.
        L’activation portail Boutique n’auto-facture pas encore.
        """
        self.ensure_one()
        if self.mon_coin_startup_fee_invoiced or self.mon_coin_startup_fee_kind != "none":
            return self.env["product.product"]
        if boutique_path:
            return self._cq_product_by_code(SETUP_BOUTIQUE_CODE)
        return self._cq_product_by_code(SETUP_500_CODE)

    def action_activate_boutique(self):
        """Marque l’activation Boutique. Ne facture pas le 1000$ par-dessus un 500$."""
        for rec in self:
            rec.mon_coin_boutique_activated = True
            if rec.mon_coin_startup_fee_kind == "clover_500" or rec.mon_coin_startup_fee_invoiced:
                rec.message_post(
                    body=_(
                        "Boutique activée. Frais 1000$ non ajouté : un frais de "
                        "démarrage a déjà été retenu (le 1000$ remplace le 500$, "
                        "il ne s’ajoute pas)."
                    )
                )
            elif rec.mon_coin_startup_fee_kind == "none":
                rec.message_post(
                    body=_(
                        "Boutique activée (canaux). Le one-shot à facturer est "
                        "1000$ CAD — à la place du 500$, pas en plus. "
                        "Utiliser « Créer le devis palier »."
                    )
                )
        return True

    def action_create_palier_quotation(self):
        """Devis brouillon : palier + un seul frais (500$ OU 1000$, jamais les deux)."""
        self.ensure_one()
        if self.mon_coin_palier in (False, "none"):
            raise UserError(_("Choisissez d’abord un palier Mon Coin."))
        partner = self.partner_id
        if not partner:
            raise UserError(_("Liez une fiche contact (partenaire) avant le devis."))
        company = self.env["product.template"]._cq_doorway_company()
        code = PALIER_CODES.get(self.mon_coin_palier)
        palier_prod = self._cq_product_by_code(code) if code else self.env["product.product"]
        if not palier_prod:
            raise UserError(_("Produit palier introuvable (%s).") % code)

        boutique_path = bool(self.mon_coin_boutique_activated)
        fee = self.env["product.product"]
        if self.mon_coin_palier in PAID_PALIERS:
            fee = self._cq_startup_fee_product(boutique_path=boutique_path)

        Order = self.env["sale.order"].sudo()
        order = Order.create(
            {
                "partner_id": partner.id,
                "company_id": company.id if company else self.env.company.id,
                "cq_partenariat_id": self.id,
            }
        )
        Line = self.env["sale.order.line"].sudo()
        split = SPLIT_MAP.get(code)
        if split:
            itex = self._cq_product_by_code(split[0])
            cash = self._cq_product_by_code(split[1])
            if itex:
                Line.with_context(cq_skip_mon_coin_split=True).create(
                    {
                        "order_id": order.id,
                        "product_id": itex.id,
                        "product_uom_qty": 1.0,
                        "mon_coin_pay_kind": "itex",
                    }
                )
            if cash:
                Line.with_context(cq_skip_mon_coin_split=True).create(
                    {
                        "order_id": order.id,
                        "product_id": cash.id,
                        "product_uom_qty": 1.0,
                        "mon_coin_pay_kind": "cash",
                    }
                )
        else:
            Line.with_context(cq_skip_mon_coin_split=True).create(
                {
                    "order_id": order.id,
                    "product_id": palier_prod.id,
                    "product_uom_qty": 1.0,
                    "mon_coin_pay_kind": "either"
                    if self.mon_coin_palier == "connexion"
                    else False,
                }
            )
        if fee:
            Line.with_context(cq_skip_mon_coin_split=True).create(
                {
                    "order_id": order.id,
                    "product_id": fee.id,
                    "product_uom_qty": 1.0,
                }
            )
            if fee.default_code == SETUP_BOUTIQUE_CODE:
                self.mon_coin_startup_fee_kind = "boutique_1000"
            elif fee.default_code == SETUP_500_CODE:
                self.mon_coin_startup_fee_kind = "clover_500"
        order._cq_dedupe_startup_fees()
        return {
            "type": "ir.actions.act_window",
            "name": _("Devis Mon Coin"),
            "res_model": "sale.order",
            "res_id": order.id,
            "view_mode": "form",
            "target": "current",
        }
