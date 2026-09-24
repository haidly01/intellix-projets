# -*- coding: utf-8 -*-
"""Citations / annuaires (SEO local).

- ``doorway.seo.nap`` : fiche NAP maîtresse (Name / Address / Phone + extras).
- ``doorway.seo.directory`` : annuaire (liste pré-remplie QC + France).
- ``doorway.seo.citation`` : soumission d'une NAP dans un annuaire (statut +
  contenu généré par Claude, cohérent NAP).
"""
import json
import logging

from odoo import api, fields, models

from ..services import claude_seo

_logger = logging.getLogger(__name__)


class SeoNap(models.Model):
    _name = "doorway.seo.nap"
    _description = "Fiche NAP (SEO local) — SEO IA"
    _order = "id desc"

    name = fields.Char(string="Nom de l'entreprise", required=True)
    address = fields.Char(string="Adresse")
    city = fields.Char(string="Ville")
    postal_code = fields.Char(string="Code postal")
    country = fields.Char(string="Pays / région", default="Québec, Canada")
    phone = fields.Char(string="Téléphone")
    email = fields.Char(string="Email")
    website_url = fields.Char(string="Site web")
    hours = fields.Char(string="Horaires")
    categories = fields.Char(string="Catégories")
    description = fields.Text(string="Description")

    def to_dict(self):
        self.ensure_one()
        return {
            "id": self.id,
            "name": self.name or "",
            "address": self.address or "",
            "city": self.city or "",
            "postal_code": self.postal_code or "",
            "country": self.country or "",
            "phone": self.phone or "",
            "email": self.email or "",
            "website_url": self.website_url or "",
            "hours": self.hours or "",
            "categories": self.categories or "",
            "description": self.description or "",
        }

    @api.model
    def get_or_create_default(self):
        nap = self.search([], limit=1)
        if not nap:
            company = self.env.company
            nap = self.create(
                {
                    "name": company.name or "Mon entreprise",
                    "address": company.street or "",
                    "city": company.city or "",
                    "postal_code": company.zip or "",
                    "phone": company.phone or "",
                    "email": company.email or "",
                    "website_url": company.website or "",
                }
            )
        return nap


class SeoDirectory(models.Model):
    _name = "doorway.seo.directory"
    _description = "Annuaire / citation (SEO local) — SEO IA"
    _order = "sequence, name"

    name = fields.Char(string="Annuaire", required=True)
    url = fields.Char(string="URL de soumission")
    region = fields.Selection(
        [
            ("global", "International"),
            ("qc", "Québec / Canada"),
            ("fr", "France"),
        ],
        string="Zone",
        default="global",
        required=True,
    )
    category = fields.Selection(
        [
            ("general", "Généraliste / incontournable"),
            ("local", "Local / régional"),
            ("sector", "Sectoriel"),
        ],
        string="Catégorie",
        default="general",
    )
    format_hint = fields.Char(string="Format attendu (indice)")
    is_priority = fields.Boolean(string="Prioritaire")
    sequence = fields.Integer(string="Séquence", default=10)
    active = fields.Boolean(string="Actif", default=True)

    def to_dict(self):
        self.ensure_one()
        return {
            "id": self.id,
            "name": self.name,
            "url": self.url or "",
            "region": self.region,
            "category": self.category,
            "format_hint": self.format_hint or "",
            "is_priority": self.is_priority,
        }


class SeoCitation(models.Model):
    _name = "doorway.seo.citation"
    _description = "Soumission de citation — SEO IA"
    _order = "id desc"
    _rec_name = "directory_id"

    nap_id = fields.Many2one("doorway.seo.nap", string="Fiche NAP", ondelete="cascade")
    directory_id = fields.Many2one(
        "doorway.seo.directory", string="Annuaire", required=True, ondelete="cascade"
    )
    status = fields.Selection(
        [
            ("a_soumettre", "À soumettre"),
            ("soumis", "Soumis"),
            ("en_ligne", "En ligne / vérifié"),
            ("a_corriger", "À corriger"),
        ],
        string="Statut",
        default="a_soumettre",
        required=True,
    )
    business_description = fields.Text(string="Description (soumission)")
    short_description = fields.Char(string="Description courte")
    categories = fields.Char(string="Catégories proposées")
    keywords = fields.Char(string="Mots-clés")
    tagline = fields.Char(string="Accroche")
    notes = fields.Text(string="Notes de soumission")
    last_error = fields.Text(string="Dernière erreur")

    _sql_constraints = [
        (
            "nap_directory_uniq",
            "unique(nap_id, directory_id)",
            "Une seule citation par couple (NAP, annuaire).",
        ),
    ]

    def generate_content(self, language="fr"):
        self.ensure_one()
        nap = self.nap_id or self.env["doorway.seo.nap"].get_or_create_default()
        directory = self.directory_id
        data, message = claude_seo.generate_citation_content(
            self.env, nap.to_dict(), directory.to_dict(), language=language
        )
        if data is None:
            self.write({"last_error": message})
            return self.read_dict()
        self.write(
            {
                "business_description": data["business_description"],
                "short_description": data["short_description"],
                "categories": ", ".join(data["categories"]),
                "keywords": ", ".join(data["keywords"]),
                "tagline": data["tagline"],
                "notes": data["notes"],
                "last_error": False,
            }
        )
        return self.read_dict()

    def set_status(self, status):
        valid = dict(self._fields["status"].selection)
        if status in valid:
            self.write({"status": status})
        return self.read_dict()

    def read_dict(self):
        self.ensure_one()
        return {
            "id": self.id,
            "directory_id": self.directory_id.id,
            "directory": self.directory_id.to_dict(),
            "status": self.status,
            "business_description": self.business_description or "",
            "short_description": self.short_description or "",
            "categories": self.categories or "",
            "keywords": self.keywords or "",
            "tagline": self.tagline or "",
            "notes": self.notes or "",
            "last_error": self.last_error or "",
        }
