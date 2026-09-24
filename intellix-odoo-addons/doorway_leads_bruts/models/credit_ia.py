# -*- coding: utf-8 -*-
from odoo import api, fields, models


class DoorwayCreditConfig(models.Model):
    _name = "doorway.credit.config"
    _description = "Configuration commerciale crédits Extracteur"

    name = fields.Char(default="Configuration crédits Extracteur", required=True)
    google_maps_api_key = fields.Char(
        string="Clé Google Maps API",
        help="console.cloud.google.com → Places API (Nearby Search + Details)",
    )
    credit_gmaps_search = fields.Float(
        string="Crédit / recherche Google Maps",
        digits=(16, 4),
        default=0.001,
    )
    credit_gmaps_detail = fields.Float(
        string="Crédit / fiche Google Maps",
        digits=(16, 4),
        default=0.0005,
    )
    credit_scraping_page = fields.Float(
        string="Crédit / page annuaire scrapée",
        digits=(16, 4),
        default=0.0002,
    )
    marge_defaut_pct = fields.Float(string="Marge par défaut (%)", default=40.0)
    marge_premium_pct = fields.Float(string="Marge sources premium (%)", default=60.0)
    prix_credit_vente = fields.Float(string="Prix vente / crédit", digits=(16, 4), default=0.10)
    prix_credit_revient = fields.Float(
        string="Prix revient / crédit", digits=(16, 4), default=0.06
    )
    stripe_public_key = fields.Char()
    stripe_secret_key = fields.Char(groups="doorway_leads_bruts.group_admin_commercial")
    mode_commercial = fields.Boolean(
        string="Mode commercial (afficher €)",
        default=True,
    )
    devise = fields.Selection(
        [
            ("eur", "EUR"),
            ("cad", "CAD"),
            ("mad", "MAD"),
            ("usd", "USD"),
            ("chf", "CHF"),
        ],
        default="eur",
    )
    credit_nettoyage_ia = fields.Float(
        string="Crédit / lead nettoyage Claude",
        digits=(16, 4),
        default=0.005,
    )
    credit_import_odoo = fields.Float(
        string="Crédit / lead import Odoo",
        digits=(16, 4),
        default=0.001,
    )
    tva_pct = fields.Float(string="TVA (%)", default=20.0)
    auto_import_crm_doorway = fields.Boolean(
        string="Import CRM auto (pipeline Marketing Zakaria)",
        default=True,
        help="À la fin d'une extraction, envoyer les leads vers le pipeline Marketing Doorway.",
    )
    crm_assignee_login = fields.Char(
        string="Responsable CRM (login)",
        default="zakaria@agencedoorway.com",
    )

    @api.model
    def get_config(self):
        config = self.search([], limit=1)
        if not config:
            config = self.create({"name": "Configuration crédits Extracteur"})
        return config

    def credits_to_display_price(self, credits, marge_pct=None):
        """Convertit crédits en prix affiché avec marge."""
        self.ensure_one()
        marge = marge_pct if marge_pct is not None else self.marge_defaut_pct
        cout_interne = credits * self.prix_credit_revient
        return round(cout_interne * (1 + marge / 100.0), 4)

    def get_user_balance_credits(self):
        """Solde crédits de l'utilisateur courant via doorway_credits."""
        tenant = self.env["doorway.tenant"].get_tenant_for_company()
        if not tenant:
            return 0.0
        config = self.get_config()
        if config.prix_credit_vente <= 0:
            return tenant.credit_balance
        return round(tenant.credit_balance / config.prix_credit_vente, 4)

    def get_user_balance_money(self):
        tenant = self.env["doorway.tenant"].get_tenant_for_company()
        return tenant.credit_balance if tenant else 0.0
