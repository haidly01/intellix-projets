# -*- coding: utf-8 -*-
import logging
import secrets
from datetime import timedelta

from odoo import _, api, fields, models
from odoo.exceptions import ValidationError

_logger = logging.getLogger(__name__)


class CoinsProperty(models.Model):
    _name = "coins.property"
    _description = "Bien (Coins Marocain)"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "name"

    name = fields.Char(string="Nom du bien", required=True, tracking=True)
    active = fields.Boolean(default=True)
    property_type = fields.Selection(
        [
            ("riad", "Riad"),
            ("maison_hotes", "Maison d'hôtes"),
            ("apartment", "Appartement"),
            ("villa", "Villa"),
            ("pool_hammam", "Piscine / Hammam (location directe)"),
            ("other", "Autre"),
        ],
        string="Type",
        default="riad",
        required=True,
    )
    state = fields.Selection(
        [
            ("negotiating", "En négociation"),
            ("active", "Actif"),
            ("inactive", "Inactif"),
        ],
        string="Statut",
        default="negotiating",
        required=True,
        tracking=True,
    )

    district = fields.Char(string="Quartier")
    city = fields.Char(string="Ville", default="Marrakech")
    street = fields.Char(string="Adresse")

    # Carte publique (Google Maps) — optionnel, saisi manuellement si absent
    latitude = fields.Float(string="Latitude", digits=(10, 7))
    longitude = fields.Float(string="Longitude", digits=(10, 7))
    map_zone = fields.Selection(
        [
            ("marrakech_centre", "Marrakech centre"),
            ("palmeraie", "Palmeraie"),
            ("agafay", "Agafay"),
            ("autre", "Autre (rayon 30 min)"),
        ],
        string="Zone carte",
    )
    map_pillar = fields.Selection(
        [
            ("villas_riads", "Villas & Riads / Hébergement"),
            ("bien_etre", "Bien-être"),
            ("route_gourmande", "Route gourmande"),
            ("plein_air", "Plein air & sport"),
            ("experiences", "Expériences"),
            ("evenements", "Événements"),
        ],
        string="Thème carte",
        help="Thème filtrable sur la page Carte (esprit Mon Coin).",
    )
    category_ids = fields.Many2many(
        "coins.property.category",
        "coins_property_category_rel",
        "property_id",
        "category_id",
        string="Catégories",
        help="Un lieu peut cumuler plusieurs catégories. "
        "Découverte = carte publique + adresse exacte.",
    )
    category_codes = fields.Char(
        string="Codes catégories",
        compute="_compute_category_codes",
        store=True,
        index=True,
    )
    # Compatibilité domaines historiques — synchronisé depuis Découverte.
    niveau_visibilite = fields.Selection(
        [
            ("public", "Public (carte)"),
            ("privatisation", "Privatisation (hors carte)"),
        ],
        string="Visibilité carte (sync)",
        default="public",
        required=True,
        index=True,
        help="Synchronisé avec la catégorie Découverte (public = sur carte).",
    )
    location_chambre_unite = fields.Boolean(
        string="Location chambre / suite à l’unité",
        default=False,
        help="Capacité réservable à la chambre/suite. Requis si catégorie Hébergement.",
    )
    nb_suites = fields.Integer(
        string="Nombre de suites",
        help="Suites du domaine (informatif si pas de location à l’unité).",
    )
    terrain_hectares = fields.Float(
        string="Terrain (hectares)",
        digits=(16, 2),
    )
    tarif_privatisation_jour = fields.Float(
        string="Tarif privatisation / jour (€)",
        help="Tarif indicatif pour privatisation complète (pas à la chambre).",
    )
    # Entonnoir événement — saisie manuelle uniquement (jamais déduit).
    style_evenement = fields.Selection(
        [
            ("moderne", "Moderne"),
            ("traditionnel", "Traditionnel"),
            ("nature_rural", "Nature / rural"),
            ("desert", "Désert"),
            ("non_classe", "Non classé"),
        ],
        string="Style événement",
        default="non_classe",
        required=True,
        help="Ne jamais deviner automatiquement. non_classe = masqué au client.",
    )
    budget_tier = fields.Selection(
        [
            ("tres_economique", "Très économique"),
            ("economique", "Économique"),
            ("moyen", "Moyen"),
            ("eleve", "Élevé"),
        ],
        string="Gamme de budget",
    )
    capacite_evenement_jour = fields.Integer(
        string="Capacité événement (jour)",
        help="Personnes le jour (peut différer de la capacité nuit).",
    )
    gestion_disponibilite_actuelle = fields.Selection(
        [
            ("calendrier_papier", "Calendrier papier"),
            ("whatsapp", "WhatsApp"),
            ("autre_systeme", "Autre système"),
            ("non_geree", "Non gérée"),
        ],
        string="Gestion disponibilité actuelle",
    )
    politique_annulation = fields.Text(string="Politique d’annulation")
    menu_options = fields.Text(
        string="Options menu",
        help="Une ligne par option : nom + prix. Ex. Menu groupe 45 €.",
    )
    divertissement_options = fields.Text(
        string="Options divertissement",
        help="Une ligne par option : nom + prix.",
    )
    decoration_options = fields.Text(
        string="Options décoration",
        help="Une ligne par option : nom + prix.",
    )
    autres_services = fields.Char(
        string="Autres services",
        help="Codes séparés par virgule : transport, bien_etre, activites, autre.",
    )
    prix_privatisation_jour_soir = fields.Float(
        string="Privatisation jour + soir (€)",
        help="Tarif indicatif jour + soir — EUR fixe, comme le tarif / jour.",
    )
    inclus_prix_base = fields.Text(string="Inclus dans le prix de base")
    supplement_prix_base = fields.Text(string="Suppléments au prix de base")

    def autres_services_list(self):
        self.ensure_one()
        allowed = {"transport", "bien_etre", "activites", "autre"}
        return [
            x.strip()
            for x in (self.autres_services or "").split(",")
            if x.strip() in allowed
        ]

    def event_extras_filled(self):
        """True si au moins un extra événement a une valeur (hors style)."""
        self.ensure_one()
        if (self.menu_options or "").strip():
            return True
        if (self.divertissement_options or "").strip():
            return True
        if (self.decoration_options or "").strip():
            return True
        if self.autres_services_list():
            return True
        if (self.inclus_prix_base or "").strip():
            return True
        if (self.supplement_prix_base or "").strip():
            return True
        if (self.politique_annulation or "").strip():
            return True
        if self.capacite_evenement_jour:
            return True
        if self.gestion_disponibilite_actuelle:
            return True
        return False

    def public_event_summary(self):
        """Payload public /lieux — non_classe et extras vides → show False."""
        self.ensure_one()
        style = self.style_evenement or "non_classe"
        extras = {}
        if (self.menu_options or "").strip():
            extras["menu_options"] = self.menu_options.strip()
        if (self.divertissement_options or "").strip():
            extras["divertissement_options"] = self.divertissement_options.strip()
        if (self.decoration_options or "").strip():
            extras["decoration_options"] = self.decoration_options.strip()
        services = self.autres_services_list()
        if services:
            extras["autres_services"] = services
        if (self.inclus_prix_base or "").strip():
            extras["inclus_prix_base"] = self.inclus_prix_base.strip()
        if (self.supplement_prix_base or "").strip():
            extras["supplement_prix_base"] = self.supplement_prix_base.strip()
        if (self.politique_annulation or "").strip():
            extras["politique_annulation"] = self.politique_annulation.strip()
        if self.capacite_evenement_jour:
            extras["capacite_evenement_jour"] = int(self.capacite_evenement_jour)
        if self.gestion_disponibilite_actuelle:
            extras["gestion_disponibilite_actuelle"] = (
                self.gestion_disponibilite_actuelle
            )
        show = style != "non_classe" and self.event_extras_filled()
        labels = dict(self._fields["style_evenement"].selection)
        budget_labels = dict(self._fields["budget_tier"].selection)
        gestion_labels = dict(self._fields["gestion_disponibilite_actuelle"].selection)
        service_labels = {
            "transport": "Transport",
            "bien_etre": "Bien-être",
            "activites": "Activités",
            "autre": "Autre",
        }
        prix = float(self.prix_privatisation_jour_soir or 0)
        return {
            "style_evenement": "" if style == "non_classe" else style,
            "style_evenement_label": labels.get(style, "") if style != "non_classe" else "",
            "budget_tier": self.budget_tier or "",
            "budget_tier_label": budget_labels.get(self.budget_tier, "")
            if self.budget_tier
            else "",
            "prix_privatisation_jour_soir": prix if prix else 0,
            "extras": extras,
            "extras_labels": {
                "autres_services": [service_labels.get(c, c) for c in services],
                "gestion_disponibilite_actuelle": gestion_labels.get(
                    self.gestion_disponibilite_actuelle or "", ""
                ),
            },
            "show": show,
        }
    recommande_par_radio = fields.Boolean(
        string="Coup de cœur radio",
        default=False,
        help="Badge « Coup de cœur radio » sur la carte (priorité max).",
    )
    nom_radio = fields.Char(
        string="Nom de la radio",
        help="Affiché avec le badge radio si renseigné.",
    )
    fiche_video_ids = fields.One2many(
        "coins.fiche_video",
        "fiche_id",
        string="Vidéos fiche",
    )
    portal_token = fields.Char(
        string="Token portail partenaire",
        copy=False,
        index=True,
        help="Lien public /partenaire/[token] — usage propriétaire.",
    )
    portal_preview_token = fields.Char(
        string="Token aperçu interne (Karine)",
        copy=False,
        index=True,
        help="Lien de test / validation interne — distinct du token propriétaire. "
        "Même vue, pas envoyé aux partenaires.",
    )
    onboarding_kind = fields.Selection(
        [
            ("restaurant", "Restaurant"),
            ("spa", "Spa / bien-être"),
            ("hebergement", "Hébergement"),
        ],
        string="Type d'onboarding",
        copy=False,
    )
    onboarding_status = fields.Selection(
        [
            ("brouillon", "Brouillon"),
            ("lien_envoye", "Lien envoyé"),
            ("en_attente_validation", "En attente de validation"),
            ("publiee", "Publiée"),
            ("correction", "À corriger"),
        ],
        string="Statut onboarding",
        default="brouillon",
        copy=False,
        index=True,
    )
    onboarding_contact_name = fields.Char(string="Contact onboarding")
    onboarding_phone = fields.Char(string="Téléphone onboarding")
    onboarding_email = fields.Char(string="Email onboarding")

    # ——— Route gourmande (lieux restauration / tables) ———
    rg_cuisine = fields.Selection(
        [
            ("marocaine_traditionnelle", "Marocaine traditionnelle"),
            ("fusion", "Fusion"),
            ("mediterraneenne", "Méditerranéenne"),
            ("internationale", "Internationale"),
            ("street_food", "Street food gastronomique"),
        ],
        string="Type de cuisine",
        help="Route gourmande — extensible via le code source.",
    )
    rg_cadre = fields.Char(
        string="Cadre",
        help="Codes séparés par virgule : rooftop, terrasse_exterieure, "
        "jardin, salle_interieure, salle_privee.",
    )
    rg_alcool = fields.Selection(
        [
            ("licence_complete", "Licence complète"),
            ("sans_alcool", "Sans alcool"),
            ("sur_demande", "Sur demande"),
        ],
        string="Alcool",
    )
    rg_animations = fields.Char(
        string="Animations",
        help="Codes séparés par virgule : musique_live, dj, danse_orientale, "
        "lounge, aucune.",
    )
    rg_capacite_couverts = fields.Integer(string="Capacité (couverts)")
    rg_capacite_groupe_max = fields.Integer(string="Groupe max")
    rg_privatisation_possible = fields.Boolean(
        string="Privatisation possible",
        default=False,
    )
    rg_ambiance = fields.Selection(
        [
            ("romantique", "Romantique"),
            ("festif", "Festif"),
            ("familial", "Familial"),
            ("chic", "Chic / formel"),
        ],
        string="Ambiance",
    )
    rg_vue = fields.Selection(
        [
            ("panoramique_medina", "Panoramique médina"),
            ("jardin", "Jardin"),
            ("aucune", "Aucune vue particulière"),
        ],
        string="Vue",
    )
    rg_fourchette_prix = fields.Selection(
        [
            ("accessible", "Accessible"),
            ("milieu", "Milieu de gamme"),
            ("premium", "Premium"),
            ("sur_devis", "Sur devis"),
        ],
        string="Fourchette de prix",
        help="Pas de prix exact public — cohérent avec la politique devis / à partir de.",
    )

    def rg_cadre_list(self):
        self.ensure_one()
        return [x.strip() for x in (self.rg_cadre or "").split(",") if x.strip()]

    def rg_animations_list(self):
        self.ensure_one()
        return [x.strip() for x in (self.rg_animations or "").split(",") if x.strip()]

    # ——— Route bien-être (villa événementielle / hammam spécialisé) ———
    be_type_lieu = fields.Selection(
        [
            ("villa_evenementiel", "Villa/riad événementiel"),
            ("hammam_specialise", "Hammam spécialisé"),
        ],
        string="Type de lieu bien-être",
        help="Villa/riad = salle bien-être + Zen Traitements. "
        "Hammam = lieu indépendant sans hébergement.",
    )
    be_services = fields.Char(
        string="Services offerts",
        help="Codes séparés par virgule : massage, hammam_traditionnel, "
        "soin_visage, henna, brushing, soins_beaute.",
    )
    be_mixte = fields.Selection(
        [
            ("mixte", "Mixte"),
            ("creneaux_separes", "Créneaux séparés hommes-femmes"),
            ("non_mixte", "Non-mixte"),
        ],
        string="Mixte / non-mixte",
    )
    be_capacite_simultanee = fields.Integer(
        string="Capacité simultanée",
        help="Nombre de soins en même temps (ex. massage duo).",
    )
    be_prestataire_libre = fields.Char(
        string="Prestataire (hammam)",
        help="Hammams spécialisés uniquement. "
        "Villas/riads : utiliser le partenaire Zen Traitements.",
    )
    be_cadre = fields.Char(
        string="Cadre (hammam)",
        help="Codes : spa_interieur, jardin, terrasse — hammams spécialisés.",
    )
    be_ambiance = fields.Selection(
        [
            ("calme", "Calme / méditatif"),
            ("luxe", "Luxe premium"),
            ("convivial", "Convivial"),
        ],
        string="Ambiance (hammam)",
    )
    be_duree_moyenne = fields.Char(
        string="Durée moyenne",
        help="Ex. 90 min — hammams spécialisés.",
    )
    be_fourchette_prix = fields.Selection(
        [
            ("accessible", "Accessible"),
            ("milieu", "Milieu de gamme"),
            ("premium", "Premium"),
            ("sur_devis", "Sur devis"),
        ],
        string="Fourchette de prix (hammam)",
    )

    def be_services_list(self):
        self.ensure_one()
        return [x.strip() for x in (self.be_services or "").split(",") if x.strip()]

    def be_cadre_list(self):
        self.ensure_one()
        return [x.strip() for x in (self.be_cadre or "").split(",") if x.strip()]

    def be_prestataire_label(self):
        self.ensure_one()
        if self.be_type_lieu == "villa_evenementiel":
            return (self.detente_partner_id.name if self.detente_partner_id else "") or (
                "Zen Traitements"
            )
        return self.be_prestataire_libre or ""

    def has_category(self, code):
        self.ensure_one()
        return code in (self.category_ids.mapped("code") or [])

    def onboarding_kinds_list(self):
        """Catégories du formulaire public. Compat : une seule onboarding_kind."""
        self.ensure_one()
        kinds = []
        if self.has_category("route_gourmande"):
            kinds.append("restaurant")
        if self.has_category("bien_etre"):
            kinds.append("spa")
        if self.has_category("hebergement"):
            kinds.append("hebergement")
        if kinds:
            return kinds
        if self.onboarding_kind in ("restaurant", "spa", "hebergement"):
            return [self.onboarding_kind]
        return ["hebergement"]

    def _apply_onboarding_kinds(self, kinds):
        """Étend category_ids — ne remplace pas Découverte ni les autres piliers."""
        self.ensure_one()
        allowed = [k for k in (kinds or []) if k in ("restaurant", "spa", "hebergement")]
        xmlids = {
            "restaurant": "coins_marocain.cat_route_gourmande",
            "spa": "coins_marocain.cat_bien_etre",
            "hebergement": "coins_marocain.cat_hebergement",
        }
        commands = []
        for kind, xmlid in xmlids.items():
            cat = self.env.ref(xmlid, raise_if_not_found=False)
            if not cat:
                continue
            if kind in allowed:
                commands.append((4, cat.id))
            elif cat in self.category_ids:
                commands.append((3, cat.id))
        vals = {}
        if commands:
            vals["category_ids"] = commands
        if "hebergement" in allowed:
            vals["location_chambre_unite"] = True
        if allowed:
            vals["onboarding_kind"] = (
                "hebergement" if "hebergement" in allowed else allowed[0]
            )
        if vals:
            self.with_context(coins_partner_portal=True).write(vals)

    def is_carte_public(self):
        """Adresse exacte / pin carte : uniquement catégorie Découverte."""
        self.ensure_one()
        return self.has_category("decouverte")

    @api.depends("category_ids", "category_ids.code")
    def _compute_category_codes(self):
        for rec in self:
            codes = sorted(c for c in rec.category_ids.mapped("code") if c)
            rec.category_codes = ",".join(codes)

    def _sync_niveau_from_categories(self):
        for rec in self:
            desired = "public" if rec.has_category("decouverte") else "privatisation"
            if rec.niveau_visibilite != desired:
                super(CoinsProperty, rec).write({"niveau_visibilite": desired})

    @api.onchange("category_ids")
    def _onchange_category_ids(self):
        for rec in self:
            rec.niveau_visibilite = (
                "public" if rec.has_category("decouverte") else "privatisation"
            )
            if rec.has_category("hebergement"):
                rec.location_chambre_unite = True
            elif rec.location_chambre_unite and not rec.has_category("hebergement"):
                rec.location_chambre_unite = False

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        records._sync_niveau_from_categories()
        return records

    _ONBOARDING_CONTENT_FIELDS = {
        "name",
        "street",
        "district",
        "city",
        "description",
        "narrative",
        "nb_suites",
        "capacity",
        "price_per_night",
        "rg_cuisine",
        "rg_cadre",
        "rg_alcool",
        "rg_animations",
        "rg_capacite_couverts",
        "rg_privatisation_possible",
        "rg_ambiance",
        "rg_vue",
        "rg_fourchette_prix",
        "be_type_lieu",
        "be_services",
        "be_mixte",
        "be_capacite_simultanee",
        "be_prestataire_libre",
        "onboarding_contact_name",
        "onboarding_phone",
        "onboarding_email",
        "room_ids",
        "photo_ids",
        "fiche_video_ids",
        "category_ids",
    }

    def write(self, vals):
        res = super().write(vals)
        if "category_ids" in vals:
            self._sync_niveau_from_categories()
        if self.env.context.get("coins_force_publish") or vals.get(
            "onboarding_status"
        ) in ("publiee", "correction"):
            return res
        # Only partner-portal content edits re-queue for human validation.
        # Backend / shell / CRM / photo imports must NOT silently unpublish
        # live fiches (that was emptying coinsmarocain.com/lieux/*).
        if not self.env.context.get("coins_partner_portal"):
            return res
        touched = self._ONBOARDING_CONTENT_FIELDS.intersection(vals)
        if not touched:
            return res
        for rec in self:
            if rec.onboarding_status == "publiee":
                super(CoinsProperty, rec).write(
                    {"onboarding_status": "en_attente_validation"}
                )
                rec.message_post(
                    body=_(
                        "Fiche repassée en attente de validation après "
                        "modification partenaire (portail)."
                    )
                )
        return res

    @api.model
    def _domain_exclude_unpublished_onboarding(self, prefix=""):
        """Masque les fiches en file d'onboarding — pas les lieux déjà en ligne."""
        field = ("%s.onboarding_status" % prefix) if prefix else "onboarding_status"
        return [
            "|",
            (field, "=", False),
            (
                field,
                "not in",
                ("lien_envoye", "en_attente_validation", "correction"),
            ),
        ]

    def _is_publicly_listed(self):
        self.ensure_one()
        return self.onboarding_status not in (
            "lien_envoye",
            "en_attente_validation",
            "correction",
        )

    def action_publish_onboarding(self):
        """Publication humaine uniquement — jamais automatique."""
        for rec in self:
            kinds = rec.onboarding_kinds_list()
            rec._apply_onboarding_kinds(kinds)
            vals = {"onboarding_status": "publiee", "state": "active"}
            if "hebergement" in kinds or rec.room_ids.filtered("active"):
                vals["location_chambre_unite"] = True
            rec.with_context(coins_force_publish=True).write(vals)
            rec._sync_onboarding_to_hebergement()
            rec.message_post(body=_("Fiche publiée après validation humaine."))
        return True

    def _sync_onboarding_to_hebergement(self):
        """Chaque coins.property.room reste l'unité réservable — on lie l'établissement."""
        self.ensure_one()
        kinds = self.onboarding_kinds_list()
        if "hebergement" not in kinds and not self.room_ids.filtered("active"):
            return
        if "intellix.riad.establishment" in self.env:
            Estab = self.env["intellix.riad.establishment"].sudo()
            if not Estab.search([("property_id", "=", self.id)], limit=1):
                Estab.create({"property_id": self.id})
        self._sync_rooms_to_channex()

    def _sync_rooms_to_channex(self):
        """Un mapping room_type par chambre, sans toucher aux mappings twin/double existants."""
        self.ensure_one()
        Mapping = self.env["coins.channex.mapping"].sudo()
        prop_map = Mapping.search(
            [("kind", "=", "property"), ("property_id", "=", self.id)],
            limit=1,
        )
        if not prop_map:
            return
        try:
            from odoo.addons.coins_marocain.services.channex_service import (
                ChannexNotConfigured,
                ChannexService,
            )
        except ImportError:
            return
        svc = ChannexService(self.env)
        if not svc.ready:
            return
        for room in self.room_ids.filtered("active"):
            existing = Mapping.search(
                [
                    ("kind", "=", "room_type"),
                    "|",
                    ("room_id", "=", room.id),
                    ("local_id", "=", room.id),
                ],
                limit=1,
            )
            if existing:
                if not existing.room_id:
                    existing.room_id = room.id
                continue
            try:
                body = svc.create_room_type(
                    prop_map.channex_id,
                    room.name,
                    occ_adults=room.sleeps or 2,
                )
            except ChannexNotConfigured:
                return
            except Exception:
                _logger.exception("Channex room_type chambre %s", room.id)
                continue
            node = (body or {}).get("data") if isinstance(body, dict) else {}
            uuid = (node or {}).get("id") or (node or {}).get("attributes", {}).get("id")
            if not uuid:
                continue
            Mapping.create(
                {
                    "kind": "room_type",
                    "local_id": room.id,
                    "channex_id": uuid,
                    "property_id": self.id,
                    "room_id": room.id,
                    "note": room.name,
                }
            )

    def action_request_onboarding_correction(self):
        self.write({"onboarding_status": "correction"})
        for rec in self:
            rec.message_post(body=_("Fiche renvoyée au partenaire — à corriger."))
        return True

    def _notify_karine_onboarding_submission(self):
        self.ensure_one()
        email = (
            self.env["ir.config_parameter"]
            .sudo()
            .get_param(
                "coins_marocain.karine_email",
                self.env["ir.config_parameter"]
                .sudo()
                .get_param(
                    "coins_marocain.booking_notify_email",
                    "karine@agencedoorway.com",
                ),
            )
        )
        if not email:
            return
        base = (
            self.env["ir.config_parameter"]
            .sudo()
            .get_param("web.base.url", "https://intellixcrm.com")
            .rstrip("/")
        )
        kind_labels = dict(self._fields["onboarding_kind"].selection or [])
        labels = {
            "restaurant": "Resto",
            "spa": "Spa / Bien-être",
            "hebergement": "Hébergement",
        }
        kinds = self.onboarding_kinds_list()
        kind = ", ".join(labels.get(k, k) for k in kinds) or (
            kind_labels.get(self.onboarding_kind) or self.onboarding_kind or "—"
        )
        link = "%s/web#id=%s&model=coins.property&view_type=form" % (base, self.id)
        body = (
            "<p>Nouvelle fiche partenaire à valider.</p>"
            "<p><strong>Établissement :</strong> %s<br/>"
            "<strong>Catégories :</strong> %s</p>"
            "<p><a href=\"%s\">Ouvrir la fiche pour validation</a></p>"
        ) % (self.name or "—", kind, link)
        mail = self.env["mail.mail"].sudo().create(
            {
                "subject": "Validation partenaire — %s (%s)" % (self.name or "fiche", kind),
                "body_html": body,
                "email_to": email,
                "email_from": "Coins Marocain <zakaria@coinsmarocain.com>",
                "auto_delete": False,
            }
        )
        mail.send()

    @api.constrains("category_ids", "location_chambre_unite")
    def _check_hebergement_capability(self):
        for rec in self:
            if rec.has_category("hebergement") and not rec.location_chambre_unite:
                raise ValidationError(
                    _(
                        "La catégorie Hébergement exige la capacité "
                        "« Location chambre / suite à l’unité » pour %s."
                    )
                    % (rec.name or _("ce lieu"))
                )
            if rec.location_chambre_unite and not rec.has_category("hebergement"):
                raise ValidationError(
                    _(
                        "La location à l’unité est cochée sans catégorie Hébergement "
                        "pour %s. Ajoutez Hébergement ou décochez la capacité."
                    )
                    % (rec.name or _("ce lieu"))
                )

    def carte_badge_for_video(self, video, trending_fiche_ids=None):
        """Un seul badge par pin — priorité radio > influenceur > tendance."""
        self.ensure_one()
        if not self.is_carte_public():
            return None
        if self.recommande_par_radio:
            detail = (self.nom_radio or "").strip()
            return {
                "type": "radio",
                "label": "Coup de cœur radio",
                "detail": detail,
            }
        if video and video.source == "influenceur":
            creator = (
                video.uploaded_by.name
                if video.uploaded_by
                else ""
            ).strip() or "un créateur"
            return {
                "type": "influenceur",
                "label": "Recommandé par %s" % creator,
                "detail": creator,
            }
        trending = set(trending_fiche_ids or [])
        if self.id in trending:
            return {
                "type": "tendance",
                "label": "Tendance cette semaine",
                "detail": "",
            }
        return None

    owner_id = fields.Many2one(
        "res.partner",
        string="Propriétaire",
        tracking=True,
    )
    management_commission = fields.Float(
        string="Commission de gestion (%)",
        default=10.0,
        help="Pourcentage prélevé sur le prix proprio (défaut 10 %).",
    )

    # Lien partenaire détente (piscine/hammam location directe — une seule source)
    detente_partner_id = fields.Many2one(
        "coins.detente_partner",
        string="Partenaire détente",
        ondelete="set null",
        help="Fiche partenaire détente d'origine (évite la duplication).",
    )
    direct_rental_price_base = fields.Monetary(
        string="Prix proprio (base)",
        currency_field="currency_id",
        help="Prix de base du propriétaire avant commission.",
    )
    direct_rental_markup_fixed = fields.Monetary(
        string="Markup client",
        currency_field="currency_id",
        default=50.0,
        help="Supplément fixe ajouté au prix client (défaut 50 MAD).",
    )
    direct_rental_owner_payout = fields.Monetary(
        string="Versé au proprio",
        currency_field="currency_id",
        compute="_compute_direct_rental_economics",
        store=True,
    )
    direct_rental_margin = fields.Monetary(
        string="Marge Coins",
        currency_field="currency_id",
        compute="_compute_direct_rental_economics",
        store=True,
    )

    # Narration + standard visuel (pilier "esthétique visuelle")
    narrative = fields.Html(
        string="Pourquoi ce bien",
        help="Récit / storytelling du bien — pas un simple listing de specs.",
    )
    description = fields.Html(
        string="Descriptif",
        help="Descriptif éditable pour la plateforme Coins Marocain "
        "(indépendant du texte Airbnb).",
    )
    image_1920 = fields.Image(string="Photo principale", max_width=1920, max_height=1920)

    capacity = fields.Integer(string="Capacité (personnes)")
    amenities = fields.Text(string="Équipements")

    # Chambres + offres daypass / repas (checkout site)
    room_ids = fields.One2many(
        "coins.property.room",
        "property_id",
        string="Chambres",
    )
    daypass_piscine = fields.Boolean(
        string="Daypass piscine proposé",
        help="Propose un accès daypass piscine en complément du séjour.",
    )
    daypass_price = fields.Monetary(
        string="Prix daypass (CAD)",
        currency_field="currency_id",
    )
    daypass_capacity_day = fields.Integer(
        string="Places daypass / jour",
        default=10,
        help="Capacité max de daypass pour une journée donnée.",
    )
    meal_breakfast_available = fields.Boolean(string="Petit-déjeuner proposé")
    meal_lunch_available = fields.Boolean(string="Déjeuner proposé")
    meal_dinner_available = fields.Boolean(string="Dîner proposé")
    meal_breakfast_price = fields.Monetary(
        string="Prix petit-déj. (CAD)", currency_field="currency_id"
    )
    meal_lunch_price = fields.Monetary(
        string="Prix déjeuner (CAD)", currency_field="currency_id"
    )
    meal_dinner_price = fields.Monetary(
        string="Prix dîner (CAD)", currency_field="currency_id"
    )
    ops_slot_ids = fields.One2many(
        "coins.property.ops.slot",
        "property_id",
        string="Agenda ops",
    )
    ops_slot_count = fields.Integer(
        string="Nb créneaux ops",
        compute="_compute_ops_slot_count",
    )

    # Airbnb — sync agenda partenaires inscrits uniquement (jamais affiché au public)
    airbnb_listing_url = fields.Char(
        string="Lien annonce Airbnb (interne)",
        help="Référence interne. Non publié sur le site. "
        "La fiche publique ne propose jamais « Voir sur Airbnb ».",
    )
    airbnb_ical_export_url = fields.Char(
        string="URL iCal export Airbnb",
        help="Uniquement pour partenaires inscrits qui synchronisent leur agenda. "
        "Availability → Sync calendars → Export (.ics). "
        "Sans iCal : créer les disponibilités / blocages manuellement dans Odoo. "
        "Ne jamais utiliser le champ Import côté Airbnb.",
    )
    airbnb_ical_last_sync = fields.Datetime(
        string="Dernière sync Airbnb",
        readonly=True,
        copy=False,
    )
    horizon_dispo_jours = fields.Integer(
        string="Horizon disponibilités (jours)",
        default=365,
        help="Fenêtre aujourd'hui → +N jours pour le calcul des périodes libres.",
    )

    photo_ids = fields.One2many(
        "coins.property.photo",
        "property_id",
        string="Galerie photos",
    )
    blocage_ids = fields.One2many(
        "coins.property.blocage",
        "property_id",
        string="Blocages (technique)",
    )
    disponibilite_ids = fields.One2many(
        "coins.property.disponibilite",
        "property_id",
        string="Périodes disponibles",
    )
    disponibilite_count = fields.Integer(
        string="Nb périodes libres",
        compute="_compute_disponibilite_count",
    )

    currency_id = fields.Many2one(
        "res.currency",
        string="Devise",
        default=lambda self: self.env.company.currency_id.id,
    )
    price_per_night = fields.Monetary(
        string="Prix / nuit (CAD)",
        currency_field="currency_id",
        help="Prix de référence en CAD pour la réservation en ligne "
        "(recopié manuellement depuis Airbnb). Requis pour afficher « Réserver ».",
    )
    frais_service_pct = fields.Float(
        string="Frais de service (%)",
        default=0.0,
        help="Marge de service Coins visible séparément. 0 = aucun frais "
        "(à renseigner avec Karine — pas de valeur métier inventée).",
    )
    online_booking = fields.Boolean(
        string="Réservation en ligne",
        compute="_compute_online_booking",
    )

    reservation_ids = fields.One2many(
        "coins.reservation",
        "property_id",
        string="Réservations",
    )
    reservation_count = fields.Integer(
        string="Nb réservations",
        compute="_compute_reservation_count",
    )

    @api.depends(
        "direct_rental_price_base",
        "direct_rental_markup_fixed",
        "management_commission",
        "property_type",
    )
    def _compute_direct_rental_economics(self):
        for rec in self:
            if rec.property_type != "pool_hammam":
                rec.direct_rental_owner_payout = 0.0
                rec.direct_rental_margin = 0.0
                continue
            base = rec.direct_rental_price_base or 0.0
            markup = rec.direct_rental_markup_fixed or 0.0
            pct = (rec.management_commission or 0.0) / 100.0
            client = base + markup
            owner = base - (base * pct)
            rec.direct_rental_owner_payout = owner
            rec.direct_rental_margin = client - owner

    @api.onchange(
        "direct_rental_price_base",
        "direct_rental_markup_fixed",
        "property_type",
    )
    def _onchange_direct_rental_price(self):
        for rec in self:
            if rec.property_type == "pool_hammam":
                base = rec.direct_rental_price_base or 0.0
                markup = rec.direct_rental_markup_fixed or 0.0
                rec.price_per_night = base + markup

    @api.onchange("detente_partner_id")
    def _onchange_detente_partner(self):
        for rec in self:
            p = rec.detente_partner_id
            if not p:
                continue
            rec.property_type = "pool_hammam"
            rec.name = rec.name or p.name
            rec.district = p.neighborhood or rec.district
            if p.partner_id:
                rec.owner_id = p.partner_id
            rec.direct_rental_price_base = p.direct_rental_price_base
            rec.direct_rental_markup_fixed = p.direct_rental_markup_fixed or 50.0
            rec.management_commission = p.direct_rental_commission_percent or 10.0
            rec.price_per_night = p.direct_rental_client_price or (
                (p.direct_rental_price_base or 0.0)
                + (p.direct_rental_markup_fixed or 50.0)
            )

    @api.depends("price_per_night", "state", "active")
    def _compute_online_booking(self):
        for rec in self:
            rec.online_booking = bool(
                rec.active
                and rec.state == "active"
                and (rec.price_per_night or 0.0) > 0
            )

    @api.depends("reservation_ids")
    def _compute_reservation_count(self):
        for rec in self:
            rec.reservation_count = len(rec.reservation_ids)

    @api.depends("disponibilite_ids")
    def _compute_disponibilite_count(self):
        for rec in self:
            rec.disponibilite_count = len(rec.disponibilite_ids)

    @api.depends("ops_slot_ids")
    def _compute_ops_slot_count(self):
        for rec in self:
            rec.ops_slot_count = len(rec.ops_slot_ids)

    def action_view_ops_slots(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": _("Agenda ops"),
            "res_model": "coins.property.ops.slot",
            "view_mode": "calendar,list,form",
            "domain": [("property_id", "=", self.id)],
            "context": {"default_property_id": self.id},
        }

    def action_view_reservations(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": _("Réservations"),
            "res_model": "coins.reservation",
            "view_mode": "list,form",
            "domain": [("property_id", "=", self.id)],
            "context": {"default_property_id": self.id},
        }

    def action_view_disponibilites(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": _("Disponibilités"),
            "res_model": "coins.property.disponibilite",
            "view_mode": "calendar,list,form",
            "domain": [("property_id", "=", self.id)],
            "context": {"default_property_id": self.id},
        }

    def action_open_detente_partner(self):
        self.ensure_one()
        if not self.detente_partner_id:
            return False
        return {
            "type": "ir.actions.act_window",
            "name": _("Partenaire détente"),
            "res_model": "coins.detente_partner",
            "res_id": self.detente_partner_id.id,
            "view_mode": "form",
            "target": "current",
        }

    # ------------------------------------------------------------------
    # Disponibilités (complément des blocages confirmés)
    # ------------------------------------------------------------------

    @staticmethod
    def _merge_intervals(intervals):
        """Fusionne des intervalles [start, end] inclusifs qui se chevauchent ou se touchent."""
        if not intervals:
            return []
        ordered = sorted(intervals, key=lambda x: (x[0], x[1]))
        merged = [list(ordered[0])]
        for start, end in ordered[1:]:
            last = merged[-1]
            # se touchent si start == last_end + 1 jour
            if start <= last[1] + timedelta(days=1):
                if end > last[1]:
                    last[1] = end
            else:
                merged.append([start, end])
        return [(a, b) for a, b in merged]

    @staticmethod
    def _complement_intervals(window_start, window_end, blocked):
        """Complément des blocages fusionnés dans [window_start, window_end] inclusif."""
        if window_end < window_start:
            return []
        merged = CoinsProperty._merge_intervals(blocked)
        free = []
        cursor = window_start
        for b_start, b_end in merged:
            # clip blocage à la fenêtre
            s = max(b_start, window_start)
            e = min(b_end, window_end)
            if e < s:
                continue
            if cursor < s:
                free.append((cursor, s - timedelta(days=1)))
            cursor = max(cursor, e + timedelta(days=1))
        if cursor <= window_end:
            free.append((cursor, window_end))
        return free

    def _recalculer_disponibilites(self):
        """Vide et repeuple coins.property.disponibilite pour chaque propriété."""
        Dispo = self.env["coins.property.disponibilite"].sudo()
        Blocage = self.env["coins.property.blocage"].sudo()
        today = fields.Date.context_today(self)
        for prop in self:
            horizon = prop.horizon_dispo_jours or 365
            window_end = today + timedelta(days=horizon)
            blocages = Blocage.search(
                [
                    ("property_id", "=", prop.id),
                    ("statut", "=", "confirme"),
                    ("date_debut", "<=", window_end),
                    ("date_fin", ">=", today),
                ]
            )
            blocked = []
            for b in blocages:
                s = max(b.date_debut, today)
                e = min(b.date_fin, window_end)
                if e >= s:
                    blocked.append((s, e))
            free = self._complement_intervals(today, window_end, blocked)
            existing = Dispo.search([("property_id", "=", prop.id)])
            existing.unlink()
            if free:
                Dispo.create(
                    [
                        {
                            "property_id": prop.id,
                            "date_debut": start,
                            "date_fin": end,
                        }
                        for start, end in free
                    ]
                )

    def est_disponible(self, date_debut, date_fin):
        """True si [date_debut, date_fin] est entièrement couvert par les disponibilités."""
        self.ensure_one()
        if not date_debut or not date_fin or date_fin < date_debut:
            return False
        dispos = self.disponibilite_ids.sorted("date_debut")
        if not dispos:
            return False
        # fusionner les périodes libres adjacentes puis vérifier couverture
        intervals = [(d.date_debut, d.date_fin) for d in dispos]
        merged = self._merge_intervals(intervals)
        cursor = date_debut
        for start, end in merged:
            if end < cursor:
                continue
            if start > cursor:
                return False
            # start <= cursor <= end
            if end >= date_fin:
                return True
            cursor = end + timedelta(days=1)
        return False

    def _ensure_portal_token(self):
        """Crée le token au premier appel — pas de modèle parallèle."""
        self.ensure_one()
        if not (self.portal_token or "").strip():
            token = secrets.token_urlsafe(24)
            while self.search_count(
                [
                    "|",
                    ("portal_token", "=", token),
                    ("portal_preview_token", "=", token),
                ]
            ):
                token = secrets.token_urlsafe(24)
            super(CoinsProperty, self).write({"portal_token": token})
        return self.portal_token

    def _ensure_portal_preview_token(self):
        """Token d'aperçu interne (Karine) — jamais le même que le token propriétaire."""
        self.ensure_one()
        if not (self.portal_preview_token or "").strip():
            token = secrets.token_urlsafe(24)
            while self.search_count(
                [
                    "|",
                    "|",
                    ("portal_token", "=", token),
                    ("portal_preview_token", "=", token),
                    ("id", "!=", self.id),
                ]
            ) or token == (self.portal_token or "").strip():
                token = secrets.token_urlsafe(24)
            super(CoinsProperty, self).write({"portal_preview_token": token})
        return self.portal_preview_token

    def _partner_public_url(self):
        self.ensure_one()
        self._ensure_portal_token()
        base = (
            self.env["ir.config_parameter"]
            .sudo()
            .get_param(
                "coins_marocain.partenaire_base_url",
                "https://coinsmarocain.com",
            )
            .rstrip("/")
        )
        return "%s/partenaire/%s" % (base, self.portal_token)

    def _partner_preview_url(self):
        """URL d'aperçu Karine — même portail, token distinct."""
        self.ensure_one()
        self._ensure_portal_preview_token()
        base = (
            self.env["ir.config_parameter"]
            .sudo()
            .get_param(
                "coins_marocain.partenaire_base_url",
                "https://coinsmarocain.com",
            )
            .rstrip("/")
        )
        return "%s/partenaire/%s" % (base, self.portal_preview_token)

    @api.model
    def _lookup_by_portal_token(self, token):
        token = (token or "").strip()
        # token_urlsafe(24) ≈ 32 chars ; refuse les jetons courts / trivialement devinables
        if not token or len(token) < 20:
            return self.browse()
        return self.sudo().search(
            [
                "|",
                ("portal_token", "=", token),
                ("portal_preview_token", "=", token),
            ],
            limit=1,
        )

# --- reconstructed stubs ---

    def action_sync_airbnb_ical(self):
        """Stub reconstruit — logique métier à restaurer."""
        return True
