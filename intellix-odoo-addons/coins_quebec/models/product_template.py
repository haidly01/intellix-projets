# -*- coding: utf-8 -*-
from odoo import api, fields, models

MC_CODES = (
    "MC_FICHE",
    "MC_SETUP_500",
    "MC_SETUP_BOUTIQUE_1000",
    "MC_PALIER_CONNEXION",
    "MC_PALIER_MESURE",
    "MC_PALIER_COMPLET",
    "MC_ITEX_50",
    "MC_ARGENT_MESURE",
    "MC_ARGENT_COMPLET",
)

PAID_PALIER_CODES = (
    "MC_PALIER_CONNEXION",
    "MC_PALIER_MESURE",
    "MC_PALIER_COMPLET",
)

SETUP_500_CODE = "MC_SETUP_500"
SETUP_BOUTIQUE_CODE = "MC_SETUP_BOUTIQUE_1000"

# Split ITEX + argent : 2 lignes de devis, pas un 2e wallet.
# ITEX existant = crm.lead team 112 + payment.transaction (adhésion),
# pas un solde de crédits pour facturer Ventes.
SPLIT_MAP = {
    "MC_PALIER_MESURE": ("MC_ITEX_50", "MC_ARGENT_MESURE"),
    "MC_PALIER_COMPLET": ("MC_ITEX_50", "MC_ARGENT_COMPLET"),
}


class ProductTemplate(models.Model):
    _inherit = "product.template"

    mon_coin_kind = fields.Selection(
        [
            ("fiche", "Ma fiche"),
            ("setup_500", "Frais démarrage 500$ (sans boutique)"),
            ("setup_boutique", "Frais démarrage Boutique 1000$ (à la place du 500$)"),
            ("palier_connexion", "Palier Connexion"),
            ("palier_mesure", "Palier Mesure"),
            ("palier_complet", "Palier Complet"),
            ("itex_part", "Part ITEX 50$"),
            ("cash_part", "Part argent"),
        ],
        string="Rôle Mon Coin",
        copy=False,
        help="Catalogue Mon Coin Commerces. Le 1000$ Boutique remplace le 500$, "
        "il ne s’ajoute pas.",
    )
    mon_coin_recurrence = fields.Selection(
        [
            ("none", "One-shot / non récurrent"),
            ("monthly", "Abonnement mensuel"),
        ],
        string="Récurrence Mon Coin",
        default="none",
        help="sale_subscription n’est pas installé (Enterprise). "
        "Les paliers sont mensuels au catalogue ; la facture récurrente reste manuelle.",
    )
    mon_coin_itex_amount = fields.Monetary(
        string="Part ITEX (CAD)",
        currency_field="currency_id",
        help="Montant à régler en ITEX (troc existant). Pas un nouveau wallet.",
    )
    mon_coin_cash_amount = fields.Monetary(
        string="Part argent (CAD)",
        currency_field="currency_id",
    )
    mon_coin_itex_split_required = fields.Boolean(
        string="Split ITEX + argent obligatoire",
        help="Si coché, le devis doit porter 2 lignes (part ITEX + part argent), "
        "jamais une seule ligne au prix plein.",
    )
    mon_coin_fee_trigger = fields.Selection(
        [
            ("none", "Aucun"),
            ("first_paid_no_boutique", "1re souscription palier payant, sans boutique"),
            ("boutique_activation", "Activation Boutique (à la place du 500$)"),
        ],
        string="Déclencheur frais",
        default="none",
        help="500$ et 1000$ sont exclusifs : un seul one-shot selon le parcours.",
    )

    @api.model
    def _cq_doorway_company(self):
        cad = self.env.ref("base.CAD", raise_if_not_found=False)
        domain = [("name", "ilike", "Agence Doorway")]
        if cad:
            domain.append(("currency_id", "=", cad.id))
        return self.env["res.company"].sudo().search(domain, limit=1)

    @api.model
    def _cq_bind_mon_coin_products(self):
        """Société QC + taxes vente CAD. Idempotent, appelé à chaque -u."""
        company = self._cq_doorway_company()
        products = self.sudo().search([("default_code", "in", MC_CODES)])
        if not products:
            return
        vals = {}
        if company:
            vals["company_id"] = company.id
            tax = company.account_sale_tax_id
            if tax:
                vals["taxes_id"] = [(6, 0, tax.ids)]
        if vals:
            products.write(vals)
