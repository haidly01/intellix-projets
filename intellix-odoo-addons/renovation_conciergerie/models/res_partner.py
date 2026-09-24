import re

import requests

from odoo import api, fields, models
from odoo.exceptions import UserError


class ResPartner(models.Model):
    _inherit = "res.partner"
    _EUROPE_COUNTRY_CODES = {
        "AL", "AD", "AM", "AT", "AZ", "BA", "BE", "BG", "BY", "CH", "CY", "CZ", "DE",
        "DK", "EE", "ES", "FI", "FO", "FR", "GB", "GE", "GI", "GR", "HR", "HU", "IE",
        "IS", "IT", "LI", "LT", "LU", "LV", "MC", "MD", "ME", "MK", "MT", "NL", "NO",
        "PL", "PT", "RO", "RS", "SE", "SI", "SK", "SM", "TR", "UA", "VA", "XK",
    }

    service_category_ids = fields.Many2many(
        "renovation.service.category",
        "partner_service_category_rel",
        "partner_id",
        "category_id",
        string="Services offerts",
    )
    coverage_mode = fields.Selection(
        [
            ("province", "Par province / région entière"),
            ("city", "Par villes spécifiques"),
            ("radius", "Par rayon (km)"),
            ("postal", "Par codes postaux"),
        ],
        default="province",
        string="Mode de couverture",
    )
    province_ids = fields.Many2many(
        "res.country.state",
        "partner_province_rel",
        "partner_id",
        "state_id",
        string="Provinces desservies",
    )
    city_text = fields.Char(
        string="Villes desservies",
        help="Entrez une ou plusieurs villes, separees par un espace ou une virgule.",
    )
    postal_codes_text = fields.Char(
        string="Codes postaux (saisie rapide)",
        compute="_compute_postal_codes_text",
        inverse="_inverse_postal_codes_text",
        help="Tapez un ou plusieurs codes postaux separes par un espace ou une virgule "
             "(ex: H7T1A1 J7E2B2). Le decoupage est automatique.",
    )

    @staticmethod
    def _parse_postal_codes(text):
        """Decoupe un texte libre en codes postaux canadiens (6 caracteres)."""
        raw = re.sub(r"[^A-Za-z0-9]", "", text or "").upper()
        result = []
        for i in range(0, len(raw), 6):
            chunk = raw[i:i + 6]
            if len(chunk) == 6:
                result.append(chunk[:3] + " " + chunk[3:])
            elif chunk:
                result.append(chunk)
        return result

    @api.depends("postal_code_ids.postal_code")
    def _compute_postal_codes_text(self):
        for partner in self:
            partner.postal_codes_text = " ".join(
                partner.postal_code_ids.mapped("postal_code")
            )

    def _inverse_postal_codes_text(self):
        for partner in self:
            codes = partner._parse_postal_codes(partner.postal_codes_text)
            existing = partner.postal_code_ids.mapped("postal_code")
            if codes == existing:
                continue
            commands = [(5, 0, 0)] + [(0, 0, {"postal_code": c}) for c in codes]
            partner.postal_code_ids = commands
    coverage_radius_km = fields.Float(
        string="Rayon de couverture (km)",
        help="Rayon en km autour de l'adresse du partenaire",
        default=40.0,
    )
    postal_code_ids = fields.One2many(
        "renovation.partner.postal.code",
        "partner_id",
        string="Codes postaux desservis",
    )
    partner_latitude = fields.Float(string="Latitude", digits=(10, 7))
    partner_longitude = fields.Float(string="Longitude", digits=(10, 7))
    package_ids = fields.One2many(
        "renovation.partner.package",
        "partner_id",
        string="Forfaits",
    )
    welcome_email_subject = fields.Char(
        string="Objet email de bienvenue",
        default="Bienvenue chez Soumission Entrepreneurs",
    )
    welcome_email_body = fields.Html(
        string="Message email de bienvenue",
        default=(
            "<p>Bonjour,</p>"
            "<p>Bienvenue chez Soumission Entrepreneurs.</p>"
            "<p>Nous sommes heureux de vous compter parmi nos partenaires.</p>"
            "<p>Cordialement,<br/>L'equipe Soumission Entrepreneurs</p>"
        ),
    )

    def _geocode_address(self):
        """Geolocalise l'adresse via OpenStreetMap Nominatim."""
        for partner in self:
            if partner.coverage_mode != "radius":
                continue
            parts = []
            if partner.street:
                parts.append(partner.street)
            if partner.city:
                parts.append(partner.city)
            if partner.zip:
                parts.append(partner.zip)
            if partner.country_id:
                parts.append(partner.country_id.name)

            if not parts:
                continue

            address = ", ".join(parts)
            try:
                response = requests.get(
                    "https://nominatim.openstreetmap.org/search",
                    params={
                        "q": address,
                        "format": "json",
                        "limit": 1,
                    },
                    headers={"User-Agent": "AgenceDoorway/1.0"},
                    timeout=5,
                )
                data = response.json()
                if data:
                    partner.partner_latitude = float(data[0]["lat"])
                    partner.partner_longitude = float(data[0]["lon"])
            except Exception:
                pass

    @api.onchange("street", "city", "zip", "country_id")
    def _onchange_address_geocode(self):
        """Declenche la geolocalisation quand l'adresse change."""
        self._geocode_address()

    def _compute_active_package(self):
        for partner in self:
            package = self.env["renovation.partner.package"].search(
                [("partner_id", "=", partner.id), ("state", "=", "active")],
                limit=1,
            )
            partner.active_package_id = package

    active_package_id = fields.Many2one(
        "renovation.partner.package",
        string="Forfait actif",
        compute="_compute_active_package",
        store=False,
    )

    def _is_eligible_for_partner_access(self):
        self.ensure_one()
        return bool(
            self.email
            and not self.parent_id
            and (self.service_category_ids or self.package_ids or self.supplier_rank > 0)
        )

    def _ensure_partner_user_access(self):
        """Cree (ou met a jour) le compte utilisateur partenaire."""
        if self.env.context.get("skip_partner_user_auto"):
            return

        group_user = self.env.ref("base.group_user", raise_if_not_found=False)
        group_system = self.env.ref("base.group_system", raise_if_not_found=False)
        partner_group = self.env.ref(
            "renovation_conciergerie.group_renovation_partner", raise_if_not_found=False
        )
        default_company = self._get_default_agence_doorway_company()
        if not group_user or not partner_group:
            return

        Users = self.env["res.users"].sudo().with_context(
            skip_partner_user_auto=True, active_test=False
        )
        for partner in self:
            if not partner._is_eligible_for_partner_access():
                continue

            partner_email = (partner.email or "").strip()
            if not partner_email:
                continue

            user = Users.search([("partner_id", "=", partner.id)], limit=1)
            if not user:
                user = Users.search([("login", "=ilike", partner_email)], limit=1)

            values = {
                "name": partner.name or partner_email,
                "login": partner_email,
                "email": partner_email,
                "partner_id": partner.id,
                "active": True,
                "share": False,
            }
            if default_company:
                values.update(
                    {
                        "company_id": default_company.id,
                        "company_ids": [(6, 0, [default_company.id])],
                    }
                )

            if user:
                # Do not overwrite internal/admin users with partner-only groups.
                if group_system and user.has_group("base.group_system"):
                    continue
                values["group_ids"] = [(4, group_user.id), (4, partner_group.id)]
                user.write(values)
            else:
                values["group_ids"] = [(6, 0, [group_user.id, partner_group.id])]
                Users.create(values)

    @api.model
    def _get_default_agence_doorway_company(self):
        return self.env["res.company"].search([("name", "ilike", "Agence Doorway")], limit=1)

    def _get_default_currency_code_for_country(self, country):
        code = (country.code or "").upper() if country else ""
        if code == "MA":
            return "MAD"
        if code in self._EUROPE_COUNTRY_CODES:
            return "EUR"
        return "CAD"

    def _get_default_currency_code_for_partner(self):
        """Pays du contact, sinon devise de la société de l'utilisateur interne."""
        self.ensure_one()
        if self.country_id:
            return self._get_default_currency_code_for_country(self.country_id)
        user = self.env["res.users"].sudo().search(
            [("partner_id", "=", self.id)], limit=1
        )
        if user and user.company_id.currency_id:
            return user.company_id.currency_id.name
        return "CAD"

    def _default_pricelist_names_for_currency(self, currency_code):
        """Noms officiels — exclut les listes pack (ex. « 500 CAD »)."""
        return [
            f"Prix par defaut {currency_code}",
            f"Par défaut {currency_code}",
            f"Default {currency_code}",
        ]

    def _get_pricelist_for_currency_code(self, currency_code, company=None):
        currency = self.env["res.currency"].with_context(active_test=False).search(
            [("name", "=", currency_code)], limit=1
        )
        if not currency:
            return False
        if not currency.active:
            currency.active = True
        base_domain = [("currency_id", "=", currency.id)]
        if company:
            base_domain = [
                ("currency_id", "=", currency.id),
                "|",
                ("company_id", "=", False),
                ("company_id", "=", company.id),
            ]
        Pricelist = self.env["product.pricelist"]
        for name in self._default_pricelist_names_for_currency(currency_code):
            pricelist = Pricelist.search(
                base_domain + [("name", "=", name)],
                order="company_id desc, sequence asc, id asc",
                limit=1,
            )
            if pricelist:
                return pricelist
        pricelist = Pricelist.search(
            base_domain + [("name", "in", ["Par défaut", "Default"])],
            order="company_id desc, sequence asc, id asc",
            limit=1,
        )
        if pricelist:
            return pricelist
        return Pricelist.create(
            {
                "name": f"Prix par defaut {currency_code}",
                "currency_id": currency.id,
                "company_id": company.id if company else False,
            }
        )

    def _partner_pricelist_company(self, partner):
        user = self.env["res.users"].sudo().search(
            [("partner_id", "=", partner.id)], limit=1
        )
        if user.company_id:
            return user.company_id
        if partner.company_id:
            return partner.company_id
        return self.env.company

    def _apply_default_pricelist_from_country(self):
        for partner in self:
            code = partner._get_default_currency_code_for_partner()
            company = partner._partner_pricelist_company(partner)
            pricelist = partner._get_pricelist_for_currency_code(code, company=company)
            if pricelist:
                partner.property_product_pricelist = pricelist

    def action_send_welcome_email(self):
        self.ensure_one()
        if not self.email:
            raise UserError("Le partenaire doit avoir un email pour envoyer le message de bienvenue.")

        email_from = "info@agencedoorway.com"
        body_html = self.welcome_email_body or "<p>Bonjour,</p><p>Bienvenue.</p>"
        self.env["mail.mail"].sudo().create(
            {
                "subject": self.welcome_email_subject or "Bienvenue chez Soumission Entrepreneurs",
                "email_from": email_from,
                "email_to": self.email,
                "body_html": body_html,
            }
        ).send()
        return True

    @api.model_create_multi
    def create(self, vals_list):
        partners = super().create(vals_list)
        # Currency/pricelist default by country (CAD by default, EUR for Europe, MAD for Morocco).
        partners._apply_default_pricelist_from_country()
        if not self.env.context.get("skip_partner_user_auto"):
            partners._ensure_partner_user_access()
        return partners

    def write(self, vals):
        res = super().write(vals)
        if self.env.context.get("skip_partner_user_auto"):
            return res

        address_fields = {"street", "city", "zip", "country_id"}
        if address_fields & set(vals.keys()):
            self._geocode_address()

        if "country_id" in vals and "property_product_pricelist" not in vals:
            self._apply_default_pricelist_from_country()

        access_fields = {"email", "service_category_ids", "supplier_rank", "parent_id"}
        if access_fields & set(vals.keys()):
            self._ensure_partner_user_access()
        return res
