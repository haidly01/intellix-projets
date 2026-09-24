# -*- coding: utf-8 -*-
import logging
import secrets

from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError

_logger = logging.getLogger(__name__)

DECO_TYPE_CODES = ("fleuriste", "mobilier", "chapiteau", "decoration_generale")
DECO_THEME_CODES = (
    "oriental_traditionnel",
    "moderne_minimaliste",
    "boheme_nature",
    "nomade_desert",
    "romantique_classique",
    "festif_colore",
)
PHOTOS_MIN_PER_THEME = 3


class CoinsDecoPrestataireType(models.Model):
    _name = "coins.deco.prestataire.type"
    _description = "Type de service prestataire déco"
    _order = "sequence, name"

    name = fields.Char(required=True, translate=True)
    code = fields.Char(required=True, index=True)
    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True)

    _sql_constraints = [
        ("code_uniq", "unique(code)", "Le code de type déco doit être unique."),
    ]


class CoinsDecoPrestataireTheme(models.Model):
    _name = "coins.deco.prestataire.theme"
    _description = "Thème visuel prestataire déco"
    _order = "sequence, name"

    name = fields.Char(required=True, translate=True)
    code = fields.Char(required=True, index=True)
    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True)

    _sql_constraints = [
        ("code_uniq", "unique(code)", "Le code de thème déco doit être unique."),
    ]


class CoinsDecoPrestataire(models.Model):
    _name = "coins.deco.prestataire"
    _description = "Prestataire décoration (Coins Marocain)"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "name"

    name = fields.Char(string="Nom", required=True, tracking=True)
    active = fields.Boolean(default=True)
    street = fields.Char(string="Adresse")
    zone_couverture = fields.Char(
        string="Zone de couverture",
        help="Ex. Marrakech, Ourika, Agafay…",
    )
    contact_name = fields.Char(string="Personne à contacter", tracking=True)
    phone = fields.Char(string="Téléphone / WhatsApp")
    email = fields.Char(string="Email")

    type_ids = fields.Many2many(
        "coins.deco.prestataire.type",
        "coins_deco_prestataire_type_rel",
        "prestataire_id",
        "type_id",
        string="Types de service",
        help="Plusieurs types possibles — pas une catégorie unique.",
    )
    theme_ids = fields.Many2many(
        "coins.deco.prestataire.theme",
        "coins_deco_prestataire_theme_rel",
        "prestataire_id",
        "theme_id",
        string="Thèmes",
    )

    fl_types_arrangements = fields.Text(string="Types d’arrangements")
    fl_prix = fields.Text(string="Prix fleuriste (pièce / forfait)")
    fl_prix_piece = fields.Float(string="Prix à la pièce")
    fl_prix_forfait = fields.Float(string="Prix forfait")
    fl_fleurs_origine = fields.Selection(
        [
            ("locales", "Fleurs locales"),
            ("importees", "Fleurs importées"),
            ("mixte", "Locales et importées"),
        ],
        string="Origine des fleurs",
    )

    mob_inventaire = fields.Text(string="Inventaire mobilier")
    mob_prix = fields.Text(string="Prix mobilier")
    mob_livraison_incluse = fields.Boolean(string="Livraison incluse")

    chap_tailles_disponibles = fields.Text(string="Tailles de chapiteau")
    chap_prix_par_taille = fields.Text(string="Prix par taille")
    chap_delai_montage = fields.Char(string="Délai de montage")
    chap_contraintes_terrain = fields.Text(string="Contraintes de terrain")

    dec_services_inclus = fields.Text(string="Services déco inclus")
    dec_prix = fields.Text(string="Prix déco générale")

    prix_minimum_commande = fields.Float(string="Minimum de commande")
    inclus_prix_base = fields.Text(string="Inclus dans le prix de base")
    delai_reservation_min = fields.Integer(
        string="Délai de réservation mini (jours)",
    )
    commission = fields.Float(
        string="Commission (%)",
        help="Commission Coins Marocain, en pourcentage.",
    )

    photo_ids = fields.One2many(
        "coins.deco.prestataire.photo",
        "prestataire_id",
        string="Photos",
    )
    photo_count = fields.Integer(compute="_compute_photo_count")

    portal_token = fields.Char(
        string="Token portail prestataire déco",
        copy=False,
        index=True,
        help="Lien public /prestataire-deco/[token] — unicité dans cette table seulement.",
    )
    onboarding_status = fields.Selection(
        [
            ("brouillon", "Brouillon"),
            ("lien_envoye", "Lien envoyé"),
            ("en_attente_validation", "En attente de validation"),
            ("publie", "Publié"),
        ],
        string="Statut onboarding",
        default="brouillon",
        copy=False,
        index=True,
        tracking=True,
    )
    portal_url = fields.Char(
        string="URL portail",
        compute="_compute_portal_url",
    )

    lead_ids = fields.One2many(
        "crm.lead",
        "coins_deco_prestataire_id",
        string="Leads CRM",
    )

    notes = fields.Text(string="Notes internes")

    _sql_constraints = [
        (
            "portal_token_uniq",
            "unique(portal_token)",
            "Le token portail déco doit être unique dans cette table.",
        ),
    ]

    _ONBOARDING_CONTENT_FIELDS = {
        "name",
        "street",
        "zone_couverture",
        "contact_name",
        "phone",
        "email",
        "type_ids",
        "theme_ids",
        "fl_types_arrangements",
        "fl_prix",
        "fl_prix_piece",
        "fl_prix_forfait",
        "fl_fleurs_origine",
        "mob_inventaire",
        "mob_prix",
        "mob_livraison_incluse",
        "chap_tailles_disponibles",
        "chap_prix_par_taille",
        "chap_delai_montage",
        "chap_contraintes_terrain",
        "dec_services_inclus",
        "dec_prix",
        "prix_minimum_commande",
        "inclus_prix_base",
        "delai_reservation_min",
        "commission",
        "photo_ids",
    }

    @api.depends("photo_ids")
    def _compute_photo_count(self):
        for rec in self:
            rec.photo_count = len(rec.photo_ids)

    @api.depends("portal_token")
    def _compute_portal_url(self):
        for rec in self:
            rec.portal_url = rec._deco_public_url() if rec.portal_token else ""

    def type_codes_list(self):
        self.ensure_one()
        return [c for c in self.type_ids.mapped("code") if c in DECO_TYPE_CODES]

    def theme_codes_list(self):
        self.ensure_one()
        return [c for c in self.theme_ids.mapped("code") if c in DECO_THEME_CODES]

    def has_type(self, code):
        self.ensure_one()
        return code in self.type_codes_list()

    def photos_for_theme(self, theme):
        self.ensure_one()
        theme_id = theme.id if hasattr(theme, "id") else theme
        return self.photo_ids.filtered(lambda p: p.theme_id.id == theme_id)

    def _photo_count_by_theme(self):
        self.ensure_one()
        counts = {}
        for theme in self.theme_ids:
            counts[theme.code] = len(self.photos_for_theme(theme))
        return counts

    def _missing_theme_photos(self):
        """Thèmes cochés sans le minimum de 3 photos."""
        self.ensure_one()
        missing = []
        for theme in self.theme_ids:
            n = len(self.photos_for_theme(theme))
            if n < PHOTOS_MIN_PER_THEME:
                missing.append((theme, n))
        return missing

    def _can_publish(self):
        self.ensure_one()
        if not self.name:
            return False
        if not (self.street or "").strip() and not (self.zone_couverture or "").strip():
            return False
        if not self.type_ids or not self.theme_ids:
            return False
        return not self._missing_theme_photos()

    def _assert_publish_ready(self):
        self.ensure_one()
        if not (self.street or "").strip() and not (self.zone_couverture or "").strip():
            raise UserError(
                _("Renseignez une adresse et/ou une zone de couverture avant de publier.")
            )
        if not self.type_ids:
            raise UserError(_("Cochez au moins un type de service avant de publier."))
        if not self.theme_ids:
            raise UserError(_("Cochez au moins un thème avant de publier."))
        missing = self._missing_theme_photos()
        if missing:
            lines = [
                _("• %s : %s photo(s) (minimum %s)")
                % (theme.name, n, PHOTOS_MIN_PER_THEME)
                for theme, n in missing
            ]
            raise UserError(
                _("Au moins %s photos par thème coché sont requises :\n%s")
                % (PHOTOS_MIN_PER_THEME, "\n".join(lines))
            )

    def write(self, vals):
        publishing = vals.get("onboarding_status") == "publie"
        if publishing and not self.env.context.get("coins_deco_force_publish"):
            for rec in self:
                rec._assert_publish_ready()
        res = super().write(vals)
        if self.env.context.get("coins_deco_force_publish") or vals.get(
            "onboarding_status"
        ) in ("publie",):
            return res
        touched = self._ONBOARDING_CONTENT_FIELDS.intersection(vals)
        if not touched and not self.env.context.get("coins_deco_portal"):
            return res
        # Only deco portal edits re-queue for validation — not backend/CRM writes.
        if not self.env.context.get("coins_deco_portal"):
            return res
        for rec in self:
            if rec.onboarding_status == "publie":
                super(CoinsDecoPrestataire, rec).write(
                    {"onboarding_status": "en_attente_validation"}
                )
        return res

    def action_publish_onboarding(self):
        """Publication humaine uniquement — jamais automatique."""
        for rec in self:
            rec._assert_publish_ready()
            rec.with_context(coins_deco_force_publish=True).write(
                {"onboarding_status": "publie"}
            )
            rec.message_post(body=_("Fiche déco publiée après validation humaine."))
        return True

    def _ensure_portal_token(self):
        """Crée le token au premier appel — unicité dans coins.deco.prestataire seulement."""
        self.ensure_one()
        if not (self.portal_token or "").strip():
            token = secrets.token_urlsafe(24)
            while self.search_count([("portal_token", "=", token)]):
                token = secrets.token_urlsafe(24)
            super(CoinsDecoPrestataire, self).write({"portal_token": token})
        return self.portal_token

    def _deco_public_url(self):
        self.ensure_one()
        token = (self.portal_token or "").strip()
        if not token:
            return ""
        base = (
            self.env["ir.config_parameter"]
            .sudo()
            .get_param(
                "coins_marocain.partenaire_base_url",
                "https://coinsmarocain.com",
            )
            .rstrip("/")
        )
        return "%s/prestataire-deco/%s" % (base, token)

    @api.model
    def _lookup_by_portal_token(self, token):
        token = (token or "").strip()
        if not token or len(token) < 8:
            return self.browse()
        return self.sudo().search([("portal_token", "=", token)], limit=1)

    def action_open_portal(self):
        self.ensure_one()
        self._ensure_portal_token()
        return {
            "type": "ir.actions.act_url",
            "url": self._deco_public_url(),
            "target": "new",
        }
