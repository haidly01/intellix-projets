# -*- coding: utf-8 -*-
from odoo import api, fields, models

# Mapping formule (cout_estime) -> prix indicatif par lead (EUR) pour l'estimation
# tarifaire du configurateur. Utilisé en l'absence d'avis Claude chiffré.
COUT_FORMULE_PAR_LEAD = {
    "INTLX-EXT-BRUT": 0.12,
    "INTLX-EXT-VER": 0.18,
    "INTLX-EXT-IA": 0.28,
    "INTLX-EXT-RDV": 0.45,
}


class DoorwaySourceRegistry(models.Model):
    _name = "doorway.source.registry"
    _description = "Registre des sources de leads par pays"
    _order = "pays, type_source, name"

    name = fields.Char(required=True)
    code = fields.Char(required=True, index=True)
    pays = fields.Selection(
        [
            ("maroc", "Maroc"),
            ("france", "France"),
            ("belgique", "Belgique"),
            ("espagne", "Espagne"),
            ("suisse", "Suisse"),
            ("canada", "Canada"),
            ("usa", "États-Unis"),
            ("tunisie", "Tunisie"),
            ("tous", "Tous pays"),
        ],
        required=True,
        default="tous",
    )
    type_source = fields.Selection(
        [
            ("annuaire", "Annuaire"),
            ("classees", "Annonces classées"),
            ("gmaps", "Google Maps"),
            ("linkedin", "LinkedIn"),
            ("jobboard", "Job board"),
            ("autre", "Autre"),
        ],
        required=True,
        default="annuaire",
    )
    url_pattern = fields.Char(
        help="Pattern URL avec {mot_cle} et {region}, ex: https://example.com/search?q={mot_cle}&loc={region}"
    )
    actif = fields.Boolean(default=True)
    premium = fields.Boolean(default=False)
    credit_par_page = fields.Float(digits=(16, 4), default=0.001)
    credit_par_fiche = fields.Float(digits=(16, 4), default=0.0005)
    description = fields.Text()
    logo_url = fields.Char()
    nb_leads_moy = fields.Integer(string="Leads moyens / campagne", default=50)
    taux_tel = fields.Float(string="% avec téléphone", default=0.0)
    taux_email = fields.Float(string="% avec email", default=0.0)
    rating_stars = fields.Integer(
        string="Étoiles",
        default=2,
        help="1-3 étoiles pour affichage UI",
    )

    # --- Champs Configurateur de Campagnes (INTLX-EXT) ---
    secteur = fields.Selection(
        [
            ("assurance", "Assurance"),
            ("renovation", "Rénovation"),
            ("immobilier", "Immobilier"),
            ("telecom", "Télécom"),
            ("centres_appels", "Centres d'appels"),
        ],
        string="Secteur",
        index=True,
        help="Secteur métier ciblé par cette source (configurateur de campagnes).",
    )
    ext_source_id = fields.Char(
        string="Identifiant source (configurateur)",
        help="Identifiant métier de la source tel qu'exposé au configurateur / à Claude.",
    )
    types_leads = fields.Char(
        string="Types de leads",
        help="Liste séparée par des virgules (ex: particuliers,artisans,TPE).",
    )
    filtres_dispo = fields.Char(
        string="Filtres disponibles",
        help="Liste séparée par des virgules (ex: departement,ville,code_postal).",
    )
    cout_estime = fields.Selection(
        [
            ("INTLX-EXT-BRUT", "INTLX-EXT-BRUT — Brut"),
            ("INTLX-EXT-VER", "INTLX-EXT-VER — Vérifié"),
            ("INTLX-EXT-IA", "INTLX-EXT-IA — Qualifié IA"),
            ("INTLX-EXT-RDV", "INTLX-EXT-RDV — RDV"),
        ],
        string="Formule estimée",
        help="Formule de coût indicative associée à la source.",
    )
    qualite = fields.Integer(
        string="Qualité (1-5)",
        default=3,
        help="Indice de qualité 1 à 5 pour le configurateur de campagnes.",
    )
    signal_intention = fields.Char(
        string="Signal d'intention",
        help="Signal d'intention détecté (ex: achat_immobilier, creation_entreprise).",
    )
    gratuit = fields.Boolean(
        string="Source gratuite",
        default=False,
    )

    _code_uniq = models.Constraint("unique(code)", "Le code source doit être unique.")

    @api.model
    def get_sources_for_zone(self, zone):
        """Sources actives pour une zone (inclut 'tous')."""
        if not zone or zone == "autre":
            return self.search([("actif", "=", True), ("pays", "=", "tous")])
        return self.search(
            [
                ("actif", "=", True),
                "|",
                ("pays", "=", zone),
                ("pays", "=", "tous"),
            ],
            order="type_source, premium desc, name",
        )

    def estimate_cost(self, volume_leads):
        """Estime le coût crédits pour cette source et un volume cible."""
        self.ensure_one()
        if not volume_leads:
            return 0.0
        pages = max(1, int(volume_leads / max(self.nb_leads_moy or 1, 1) * 10))
        fiches = volume_leads
        return round(
            pages * self.credit_par_page + fiches * self.credit_par_fiche,
            4,
        )

    def estimate_leads_max(self):
        """Capacité maximale estimée pour cette source."""
        self.ensure_one()
        avg = self.nb_leads_moy or 30
        return int(avg * 1.2)

    def estimate_leads_range(self, volume_target):
        """Retourne (min, max) leads estimés pour cette source."""
        self.ensure_one()
        avg = self.nb_leads_moy or 30
        share = min(volume_target, avg)
        return (int(share * 0.7), int(share * 1.2))

    # ------------------------------------------------------------------
    # Configurateur de Campagnes (INTLX-EXT)
    # ------------------------------------------------------------------
    def _to_configurator_dict(self):
        """Sérialise une source pour le configurateur OWL / pour Claude."""
        self.ensure_one()
        return {
            "id": self.ext_source_id or self.code,
            "registry_id": self.id,
            "code": self.code,
            "label": self.name,
            "description": self.description or "",
            "types_leads": [
                t.strip() for t in (self.types_leads or "").split(",") if t.strip()
            ],
            "filtres_dispo": [
                f.strip() for f in (self.filtres_dispo or "").split(",") if f.strip()
            ],
            "cout_estime": self.cout_estime or "INTLX-EXT-BRUT",
            "qualite": self.qualite or self.rating_stars or 3,
            "signal_intention": self.signal_intention or "",
            "url_pattern": self.url_pattern or "",
            "gratuit": bool(self.gratuit),
            "premium": bool(self.premium),
        }

    @api.model
    def get_configurator_sources(self, pays, secteur):
        """Sources du configurateur pour un couple pays + secteur.

        Ne renvoie que les sources rattachées à un secteur (champ ``secteur``),
        ce qui exclut les sources « scraping » génériques de l'extracteur libre.
        """
        domain = [("actif", "=", True), ("secteur", "=", secteur)]
        if pays:
            domain += ["|", ("pays", "=", pays), ("pays", "=", "tous")]
        sources = self.search(domain, order="qualite desc, premium desc, name")
        return [src._to_configurator_dict() for src in sources]
