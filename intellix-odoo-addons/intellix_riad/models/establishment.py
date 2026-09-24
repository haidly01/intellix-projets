# -*- coding: utf-8 -*-

import logging
from calendar import monthrange
from datetime import date, timedelta

from odoo import _, api, fields, models
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)

MONTHS_FR = [
    "",
    "janvier",
    "février",
    "mars",
    "avril",
    "mai",
    "juin",
    "juillet",
    "août",
    "septembre",
    "octobre",
    "novembre",
    "décembre",
]


class IntellixRiadEstablishment(models.Model):
    _name = "intellix.riad.establishment"
    _description = "Établissement Module Hébergement"
    _inherit = ["mail.thread", "mail.activity.mixin"]

    property_id = fields.Many2one(
        "coins.property",
        string="Bien",
        required=True,
        ondelete="cascade",
        tracking=True,
    )
    name = fields.Char(
        related="property_id.name",
        store=True,
        readonly=True,
    )
    company_id = fields.Many2one(
        "res.company",
        string="Société",
        help="Société Odoo de cet établissement. Le personnel créé ici "
        "est rattaché uniquement à cette société — jamais aux sociétés "
        "IntelliX / Coins / Doorway.",
    )
    active = fields.Boolean(default=True)
    user_ids = fields.Many2many(
        "res.users",
        "intellix_riad_user_estab_rel",
        "establishment_id",
        "user_id",
        string="Utilisateurs autorisés",
    )
    social_account_id = fields.Many2one(
        "doorway.social.account",
        string="Compte réseaux sociaux",
        ondelete="set null",
    )
    social_account_ids = fields.Many2many(
        "doorway.social.account",
        "intellix_riad_estab_social_rel",
        "establishment_id",
        "account_id",
        string="Comptes réseaux (Hébergement)",
    )
    social_pipeline_id = fields.Many2one(
        "crm.team",
        string="Marque sociale Hébergement",
        ondelete="set null",
        help="Équipe CRM dédiée à cet établissement — ne pas réutiliser les pipelines Coins.",
    )
    tiktok_handle = fields.Char(
        string="Identifiant TikTok",
        help="Sans @. Configuré par établissement, jamais en dur dans le code.",
    )
    terrace_enabled = fields.Boolean(
        string="Terrasse jour / nuit",
        default=True,
        help="Désactiver pour les maisons d'hôtes sans mode terrasse "
        "(bien-être le jour / restaurant le soir).",
    )
    terrace_wellness_start = fields.Float(string="Terrasse bien-être dès", default=10.0)
    terrace_wellness_end = fields.Float(string="Terrasse bien-être jusqu'à", default=17.0)
    terrace_restaurant_start = fields.Float(string="Terrasse restaurant dès", default=18.0)
    terrace_restaurant_end = fields.Float(string="Terrasse restaurant jusqu'à", default=23.0)
    terrace_wellness_label = fields.Char(
        string="Libellé bien-être",
        default="Transats & massage",
    )
    terrace_restaurant_label = fields.Char(
        string="Libellé restaurant",
        default="Restaurant",
    )
    space_mode_ids = fields.One2many(
        "intellix.riad.space.mode",
        "establishment_id",
        string="Modes d'espace",
    )
    table_ids = fields.One2many(
        "intellix.riad.table",
        "establishment_id",
        string="Tables",
    )
    practitioner_ids = fields.One2many(
        "intellix.riad.practitioner",
        "establishment_id",
        string="Prestataires",
    )
    wellness_slot_ids = fields.One2many(
        "intellix.riad.wellness.slot",
        "establishment_id",
        string="Créneaux bien-être",
    )
    event_ids = fields.One2many(
        "intellix.riad.event",
        "establishment_id",
        string="Événements",
    )
    payment_brand = fields.Selection(
        [
            ("coins_quebec", "Coins Québec (CAD)"),
            ("coins_marocain", "Coins Marocain (DH)"),
        ],
        string="Marque / devise paiement",
        compute="_compute_payment_brand",
        store=True,
        readonly=False,
    )
    payment_provider_id = fields.Many2one(
        "payment.provider",
        string="Passerelle de paiement",
        ondelete="set null",
        help="Authorize.net (CAD) ou ChariBaaS / Pay10 (DH). "
        "Clés stockées sur payment.provider, jamais en clair ici.",
    )
    compatible_provider_ids = fields.Many2many(
        "payment.provider",
        compute="_compute_compatible_providers",
    )
    payment_provider_state = fields.Selection(
        related="payment_provider_id.state",
        string="État passerelle",
    )

    @api.depends(
        "company_id",
        "company_id.currency_id",
        "property_id",
        "property_id.currency_id",
    )
    def _compute_payment_brand(self):
        for rec in self:
            curr = (
                rec.property_id.currency_id.name
                or rec.company_id.currency_id.name
                or ""
            ).upper()
            rec.payment_brand = (
                "coins_quebec" if curr == "CAD" else "coins_marocain"
            )

    @api.depends("payment_brand")
    def _compute_compatible_providers(self):
        Provider = self.env["payment.provider"].sudo()
        for rec in self:
            if rec.payment_brand == "coins_quebec":
                codes = ("authorize",)
            else:
                codes = ("charibaas", "pay10")
            rec.compatible_provider_ids = Provider.search([("code", "in", codes)])

    @api.constrains("payment_provider_id", "payment_brand")
    def _check_payment_provider_brand(self):
        for rec in self:
            if not rec.payment_provider_id:
                continue
            allowed = rec.compatible_provider_ids
            if allowed and rec.payment_provider_id not in allowed:
                raise UserError(
                    _(
                        "Cette passerelle n’est pas compatible avec %s."
                    )
                    % dict(rec._fields["payment_brand"].selection).get(
                        rec.payment_brand, rec.payment_brand
                    )
                )

    def action_open_payment_provider(self):
        self.ensure_one()
        if not self.payment_provider_id:
            raise UserError(_("Choisissez ou créez une passerelle d’abord."))
        return {
            "type": "ir.actions.act_window",
            "res_model": "payment.provider",
            "res_id": self.payment_provider_id.id,
            "view_mode": "form",
            "target": "current",
        }

    def action_ensure_test_payment_provider(self):
        """Crée une passerelle test propre à l’établissement, sans clé globale."""
        self.ensure_one()
        Provider = self.env["payment.provider"].sudo()
        if "payment.provider" not in self.env:
            raise UserError(_("Le module de paiement Odoo n’est pas installé."))
        wanted = "authorize" if self.payment_brand == "coins_quebec" else "charibaas"
        codes = [c[0] for c in (Provider._fields["code"].selection or []) if c]
        if wanted not in codes:
            fallback = self.compatible_provider_ids[:1]
            if fallback:
                self.payment_provider_id = fallback.id
                return self.action_open_payment_provider()
            raise UserError(
                _(
                    "Aucune passerelle compatible n’est installée pour %s. "
                    "Installez Authorize.net (Odoo 19) pour le CAD."
                )
                % (self.payment_brand or "")
            )
        name = "Paiement %s — %s" % (self.name or self.id, wanted)
        existing = Provider.search(
            [
                ("name", "=", name),
                ("company_id", "=", self.company_id.id or self.env.company.id),
            ],
            limit=1,
        )
        if existing:
            self.payment_provider_id = existing.id
            return self.action_open_payment_provider()
        vals = {
            "name": name,
            "code": wanted,
            "state": "test",
            "company_id": self.company_id.id or self.env.company.id,
        }
        provider = Provider.create(vals)
        self.payment_provider_id = provider.id
        return self.action_open_payment_provider()

    payroll_accountant_name = fields.Char(string="Comptable — nom")
    payroll_accountant_email = fields.Char(
        string="Comptable — email",
        help="Destinataire du rapport mensuel de présences. Configurable par établissement.",
    )
    payroll_report_day = fields.Integer(
        string="Jour d'envoi du rapport",
        default=1,
        help="Jour du mois (1–28) où le rapport du mois précédent est envoyé.",
    )
    payroll_last_sent_month = fields.Char(
        string="Dernier rapport envoyé",
        readonly=True,
        help="Clé AAAA-MM du dernier mois compilé, pour éviter un double envoi.",
    )
    tourist_tax_rate = fields.Float(
        string="Taxe de séjour (DH / personne / nuit)",
        digits=(16, 2),
        help="Montant facturé au client (formule : taux × personnes × nuits). "
        "Si TPT + communale sont renseignés, ce champ doit égaler leur somme. "
        "Configurable par établissement, jamais en dur.",
    )
    tourist_tax_commune = fields.Char(
        string="Commune de référence",
        help="Commune dont l’arrêté justifie le taux (texte libre — "
        "ex. « Commune Urbaine de Marrakech », « Tameslouht »).",
    )
    tourist_tax_pending_confirmation = fields.Boolean(
        string="Taux à confirmer",
        default=False,
        help="Coché tant que le barème n’a pas été vérifié auprès de la commune. "
        "N’empêche pas la saisie, signale un taux provisoire.",
    )
    tourist_tax_tpt_amount = fields.Float(
        string="Dont TPT (DH / pers. / nuit)",
        digits=(16, 2),
        help="Optionnel — Taxe de Promotion Touristique. "
        "Informational : le calcul client utilise uniquement le taux total.",
    )
    tourist_tax_communal_amount = fields.Float(
        string="Dont taxe communale (DH / pers. / nuit)",
        digits=(16, 2),
        help="Optionnel — part communale. "
        "Informational : le calcul client utilise uniquement le taux total.",
    )
    tourist_tax_owner_rate = fields.Float(
        string="Proposition proprio — taux (DH)",
        digits=(16, 2),
        help="Saisie portail propriétaire. N’alimente le taux actif qu’après validation Karine.",
    )
    tourist_tax_owner_commune = fields.Char(string="Proposition proprio — commune")
    tourist_tax_owner_tpt = fields.Float(
        string="Proposition proprio — TPT",
        digits=(16, 2),
    )
    tourist_tax_owner_communal = fields.Float(
        string="Proposition proprio — communale",
        digits=(16, 2),
    )
    tourist_tax_awaiting_karine = fields.Boolean(
        string="Taxe : soumise — en attente validation Karine",
        default=False,
        help="True après saisie portail propriétaire. "
        "Le taux actif (collecte / bordereau) ne change pas tant que non validé.",
    )
    tourist_tax_owner_submitted_at = fields.Datetime(
        string="Proposition taxe reçue le",
        readonly=True,
    )
    tourist_tax_currency_id = fields.Many2one(
        "res.currency",
        string="Devise taxe de séjour",
        default=lambda self: self.env["res.currency"].search(
            [("name", "=", "MAD")], limit=1
        ).id,
    )
    tax_report_name = fields.Char(string="Déclarations taxe — nom")
    tax_report_email = fields.Char(
        string="Déclarations taxe — email",
        help="Destinataire du rapport trimestriel. Si vide, on utilise l'e-mail paie.",
    )
    tax_last_sent_quarter = fields.Char(
        string="Dernier trimestre taxe envoyé",
        readonly=True,
        help="Clé AAAA-Qn pour éviter un double envoi.",
    )
    tax_bordereau_template_id = fields.Many2one(
        "intellix.riad.tax.bordereau.template",
        string="Modèle de bordereau (commune)",
        help="Chaque commune a son propre imprimé. Marrakech est un modèle, pas le seul.",
    )
    tax_operator_name = fields.Char(string="Exploitant — nom / raison sociale")
    tax_operator_address = fields.Char(string="Exploitant — adresse / siège")
    tax_operator_cin = fields.Char(string="Exploitant — CIN / immatriculation")
    tax_operator_phone = fields.Char(string="Exploitant — téléphone")
    tax_operator_fax = fields.Char(string="Exploitant — fax")
    tax_operator_nature = fields.Selection(
        [
            ("proprietaire", "Propriétaire"),
            ("directeur", "Directeur"),
            ("gerant", "Gérant"),
        ],
        string="Nature de l'exploitant",
        default="gerant",
    )
    tax_report_generate_day = fields.Integer(
        string="Jour de génération du bordereau",
        default=5,
        help="Jour du mois suivant le trimestre (1–20). Le document part assez tôt pour un dépôt avant l'échéance.",
    )
    tax_bordereau_ids = fields.One2many(
        "intellix.riad.tax.bordereau",
        "establishment_id",
        string="Bordereaux taxe de séjour",
    )
    police_fiche_ids = fields.One2many(
        "intellix.riad.police.fiche",
        "establishment_id",
        string="Fiches de police",
    )
    experience_agent_enabled = fields.Boolean(
        string="Créateur d'Expérience actif",
        default=True,
        help="Un seul agent : bien-être et messages voyageurs. Pas un second bot.",
    )
    experience_use_claude = fields.Boolean(
        string="Reformuler via Claude (sans ajouter de faits)",
        default=True,
    )
    experience_checkin_hour = fields.Float(string="Heure de check-in", default=14.0)
    experience_checkout_hour = fields.Float(string="Heure de check-out", default=11.0)
    experience_neighborhood = fields.Char(
        string="Quartier / situation",
        default="Kasbah, médina de Marrakech",
    )
    experience_howto = fields.Text(string="Comment se rendre au riad")
    experience_facts = fields.Text(
        string="Autres infos pratiques (script)",
        help="L'agent ne sort jamais de ce script + calendrier + tarifs + bien-être.",
    )
    experience_wifi = fields.Text(
        string="Wi‑Fi (réseau / mot de passe)",
        help="Bibliothèque portail — isolée à cet établissement uniquement.",
    )
    experience_house_rules = fields.Text(string="Règlement intérieur")
    experience_useful_contacts = fields.Text(
        string="Contacts utiles",
        help="Gardien, taxi, urgence locale, etc.",
    )
    experience_local_tips = fields.Text(
        string="Recommandations locales",
        help="Restaurants, activités, quartiers — propres à ce lieu.",
    )
    ota_booking_status = fields.Selection(
        [
            ("not_connected", "Non connecté"),
            ("pending", "En attente"),
            ("connected", "Connecté"),
        ],
        string="Booking.com (Channex)",
        default="not_connected",
        tracking=True,
    )
    ota_airbnb_status = fields.Selection(
        [
            ("not_connected", "Non connecté"),
            ("pending", "En attente"),
            ("connected", "Connecté"),
        ],
        string="Airbnb (Channex)",
        default="not_connected",
        tracking=True,
    )
    ota_expedia_status = fields.Selection(
        [
            ("not_connected", "Non connecté"),
            ("pending", "En attente"),
            ("connected", "Connecté"),
        ],
        string="Expedia (Channex)",
        default="not_connected",
        tracking=True,
    )
    ota_agoda_status = fields.Selection(
        [
            ("not_connected", "Non connecté"),
            ("pending", "En attente"),
            ("connected", "Connecté"),
        ],
        string="Agoda (Channex)",
        default="not_connected",
        tracking=True,
    )
    ota_vrbo_status = fields.Selection(
        [
            ("not_connected", "Non connecté"),
            ("pending", "En attente"),
            ("connected", "Connecté"),
        ],
        string="VRBO (Channex)",
        default="not_connected",
        tracking=True,
    )
    ota_feratel_status = fields.Selection(
        [
            ("not_connected", "Non connecté"),
            ("pending", "En attente"),
            ("connected", "Connecté"),
        ],
        string="Feratel (Channex)",
        default="not_connected",
        tracking=True,
    )
    ota_inntopia_status = fields.Selection(
        [
            ("not_connected", "Non connecté"),
            ("pending", "En attente"),
            ("connected", "Connecté"),
        ],
        string="Inntopia (Channex)",
        default="not_connected",
        tracking=True,
    )
    ota_hrs_status = fields.Selection(
        [
            ("not_connected", "Non connecté"),
            ("pending", "En attente"),
            ("connected", "Connecté"),
        ],
        string="HRS (Channex)",
        default="not_connected",
        tracking=True,
    )
    ota_smith_status = fields.Selection(
        [
            ("not_connected", "Non connecté"),
            ("pending", "En attente"),
            ("connected", "Connecté"),
        ],
        string="Mr & Mrs Smith (Channex)",
        default="not_connected",
        tracking=True,
    )
    ota_instant_status = fields.Selection(
        [
            ("not_connected", "Non connecté"),
            ("pending", "En attente"),
            ("connected", "Connecté"),
        ],
        string="Instant Booking Page (Channex)",
        default="not_connected",
        tracking=True,
    )
    ota_trip_status = fields.Selection(
        [
            ("not_connected", "Non connecté"),
            ("pending", "En attente"),
            ("connected", "Connecté"),
        ],
        string="Trip.com / Ctrip (Channex)",
        default="not_connected",
        tracking=True,
    )
    ota_google_status = fields.Selection(
        [
            ("not_connected", "Non connecté"),
            ("pending", "En attente"),
            ("connected", "Connecté"),
        ],
        string="Google Hotel / Vacation Rental Ads (Channex)",
        default="not_connected",
        tracking=True,
    )
    ota_status_synced_at = fields.Datetime(
        string="Dernière synchro statuts OTA",
        readonly=True,
    )
    whatsapp_e164 = fields.Char(
        string="WhatsApp Business (E.164)",
        help="Numéro dédié à CET établissement (pas le numéro Yasmine partagé). "
        "Ex. 2126XXXXXXXX",
        copy=False,
        index=True,
    )
    whatsapp_phone_number_id = fields.Char(
        string="Meta Phone Number ID",
        help="ID Meta Cloud API pour ce numéro — un par lieu.",
        copy=False,
    )
    whatsapp_waba_id = fields.Char(
        string="WhatsApp Business Account ID",
        copy=False,
    )
    whatsapp_provision_status = fields.Selection(
        [
            ("not_started", "Non démarré"),
            ("meta_pending", "Demande Meta en cours"),
            ("number_ready", "Numéro prêt — webhook à brancher"),
            ("live", "Live"),
        ],
        string="Statut provisionnement WhatsApp",
        default="not_started",
        copy=False,
        tracking=True,
    )
    whatsapp_display_name = fields.Char(
        string="Nom affiché WhatsApp",
        help="Ex. « Casa Ysabella — Coins Marocain »",
        copy=False,
    )
    experience_n8n_webhook = fields.Char(
        string="Webhook n8n (escalades)",
        help="Optionnel. Même pattern que doorway_messaging / Léa — pas une nouvelle infra.",
    )
    experience_review_enabled = fields.Boolean(
        string="Message d'avis après départ",
        default=True,
    )
    experience_review_delay_hours = fields.Integer(
        string="Délai après le départ (heures)",
        default=2,
        help="Premier message : 2 h après l'heure de check-out.",
    )
    google_review_url = fields.Char(
        string="Lien avis Google Business",
        help="Uniquement pour les séjours hors Booking/Airbnb.",
    )
    facebook_review_url = fields.Char(
        string="Lien avis / recommandation Facebook",
        help="Uniquement pour les séjours hors Booking/Airbnb.",
    )
    experience_review_template = fields.Text(
        string="Ancien texte avis (non envoyé)",
        help="Conservé pour historique. Les messages partent des deux templates routés.",
    )
    experience_thread_ids = fields.One2many(
        "intellix.riad.experience.thread",
        "establishment_id",
        string="Tours Créateur d'Expérience",
    )
    listed_on_coins_marocain = fields.Boolean(
        string="Listé comme lieu partenaire (Coins Marocain)",
        default=True,
        help="Apparait dans le catalogue partenaires Coins pour événements / "
        "privatisations. Le calendrier y est en lecture seule.",
    )
    coins_partner_activity_id = fields.Many2one(
        "coins.partner_activity",
        string="Fiche partenaire Coins Marocain",
        ondelete="set null",
        help="Listing uniquement. Les dossiers événement Coins restent à part.",
    )
    creator_compensation = fields.Selection(
        [
            ("experience", "Expérience offerte"),
            ("commission", "Commission"),
            ("experience_commission", "Séjour offert + commission"),
        ],
        string="Compensation créateurs (Coins Québec)",
        default="experience_commission",
        help="Même structure que l'entente Coins Marocain déjà validée. "
        "Le versement se fait dans le système créateurs existant.",
    )
    creator_commission_pct = fields.Float(
        string="Commission créateurs (%)",
        default=5.0,
        help="5 % sur les réservations générées, en plus du séjour offert.",
    )
    creator_payout_webhook = fields.Char(
        string="Webhook / export versement créateurs",
        help="n8n ou endpoint du système de versement Coins Québec déjà en place. "
        "Pas de nouveau moteur de commission ici.",
    )

    _sql_constraints = [
        (
            "property_uniq",
            "unique(property_id)",
            "Un bien ne peut être lié qu'à un seul établissement Riad.",
        ),
    ]

    def _float_hhmm(self, value):
        hours = int(value or 0)
        minutes = int(round(((value or 0) - hours) * 60))
        if minutes >= 60:
            hours += 1
            minutes = 0
        return "%02d:%02d" % (hours, minutes)

    def _float_hour_label(self, value):
        hours = int(value or 0)
        minutes = int(round(((value or 0) - hours) * 60))
        if minutes:
            return "%sh%02d" % (hours, minutes)
        return "%sh" % hours

    def terrace_for_date(self, day):
        self.ensure_one()
        Mode = self.env["intellix.riad.space.mode"]
        override = Mode.search(
            [
                ("establishment_id", "=", self.id),
                ("date", "=", day),
            ],
            limit=1,
        )
        if override:
            return override
        template = Mode.search(
            [
                ("establishment_id", "=", self.id),
                ("is_template", "=", True),
                ("weekday", "=", str(day.weekday())),
            ],
            limit=1,
        )
        return template

    def current_space_mode(self, hour=None):
        """wellness (transats) / restaurant / closed selon l'heure du jour."""
        self.ensure_one()
        if hour is None:
            now = fields.Datetime.context_timestamp(self, fields.Datetime.now())
            hour = now.hour + now.minute / 60.0
        today = fields.Date.context_today(self)
        mode = self.terrace_for_date(today)
        w_end = mode.wellness_end if mode else self.terrace_wellness_end
        r_start = mode.restaurant_start if mode else self.terrace_restaurant_start
        r_end = mode.restaurant_end if mode else self.terrace_restaurant_end
        w_end = w_end or 17.0
        r_start = r_start or 18.0
        r_end = r_end or 23.0
        if hour < w_end:
            return "wellness"
        if r_start <= hour < r_end:
            return "restaurant"
        return "closed"

    def terrace_payload(self, day):
        self.ensure_one()
        if not self.terrace_enabled:
            return {"enabled": False}
        mode = self.terrace_for_date(day)
        w_start = mode.wellness_start if mode else self.terrace_wellness_start
        w_end = mode.wellness_end if mode else self.terrace_wellness_end
        r_start = mode.restaurant_start if mode else self.terrace_restaurant_start
        r_end = mode.restaurant_end if mode else self.terrace_restaurant_end
        w_label = (
            mode.wellness_label
            if mode and mode.wellness_label
            else self.terrace_wellness_label
        )
        r_label = (
            mode.restaurant_label
            if mode and mode.restaurant_label
            else self.terrace_restaurant_label
        )
        w_span = max((w_end or 0) - (w_start or 0), 0.5)
        r_span = max((r_end or 0) - (r_start or 0), 0.5)
        return {
            "enabled": True,
            "badge": "Bien-être jusqu'à %s" % self._float_hour_label(w_end),
            "wellness_label": "%s – %s · %s"
            % (self._float_hour_label(w_start), self._float_hour_label(w_end), w_label or ""),
            "restaurant_label": "%s – %s · %s"
            % (self._float_hour_label(r_start), self._float_hour_label(r_end), r_label or ""),
            "flex_wellness": int(round(w_span * 10)),
            "flex_restaurant": int(round(r_span * 10)),
            "captions": [
                self._float_hhmm(w_start),
                self._float_hhmm(w_end),
                self._float_hhmm(r_end),
            ],
        }

    @api.model
    def seed_from_icp(self, icp_key, rooms, terrace=None, tiktok_handle=False):
        """Generic seed: resolve property via ICP, never by hardcoded name."""
        icp = self.env["ir.config_parameter"].sudo()
        raw_id = (icp.get_param(icp_key) or "").strip()
        if not raw_id.isdigit():
            return False
        prop = self.env["coins.property"].browse(int(raw_id))
        if not prop.exists():
            return False
        estab = self.search([("property_id", "=", prop.id)], limit=1)
        vals = {}
        if terrace:
            vals.update(
                {
                    "terrace_wellness_start": terrace.get("wellness_start", 10.0),
                    "terrace_wellness_end": terrace.get("wellness_end", 17.0),
                    "terrace_restaurant_start": terrace.get("restaurant_start", 18.0),
                    "terrace_restaurant_end": terrace.get("restaurant_end", 23.0),
                    "terrace_wellness_label": terrace.get(
                        "wellness_label", "Transats & massage"
                    ),
                    "terrace_restaurant_label": terrace.get(
                        "restaurant_label", "Restaurant"
                    ),
                }
            )
        if tiktok_handle:
            vals["tiktok_handle"] = tiktok_handle
        if estab:
            if vals:
                estab.write(vals)
        else:
            create_vals = {"property_id": prop.id}
            create_vals.update(vals)
            estab = self.create(create_vals)
        for row in rooms or []:
            sequence = row.get("sequence")
            room = prop.room_ids.filtered(lambda r, seq=sequence: r.sequence == seq)
            if not room:
                continue
            room_vals = {}
            if row.get("name"):
                room_vals["name"] = row["name"]
            if row.get("emplacement"):
                room_vals["emplacement"] = row["emplacement"]
            if row.get("price_per_night") is not None:
                room_vals["price_per_night"] = row["price_per_night"]
            if "breakfast_included" in row:
                room_vals["breakfast_included"] = bool(row["breakfast_included"])
            elif "price_per_night" in row:
                room_vals["breakfast_included"] = True
            if room_vals:
                room[:1].write(room_vals)
        if not estab.space_mode_ids.filtered("is_template"):
            Mode = self.env["intellix.riad.space.mode"]
            for weekday in range(7):
                Mode.create(
                    {
                        "establishment_id": estab.id,
                        "is_template": True,
                        "weekday": str(weekday),
                        "wellness_start": estab.terrace_wellness_start,
                        "wellness_end": estab.terrace_wellness_end,
                        "restaurant_start": estab.terrace_restaurant_start,
                        "restaurant_end": estab.terrace_restaurant_end,
                    }
                )
        return estab.id

    def action_open_riad_availability_readonly(self):
        self.ensure_one()
        from .cross_promo import _riad_readonly_calendar_action

        return _riad_readonly_calendar_action(
            self.env, self.property_id.id, self.name
        )

    @api.model
    def seed_coins_partner_listing(self, icp_key):
        """Anna Sweety (ou tout établissement ICP) comme lieu partenaire Coins."""
        icp = self.env["ir.config_parameter"].sudo()
        raw_id = (icp.get_param(icp_key) or "").strip()
        if not raw_id.isdigit():
            return False
        estab = self.search([("property_id", "=", int(raw_id))], limit=1)
        if not estab:
            return False
        if not estab.creator_commission_pct:
            estab.creator_commission_pct = 5.0
        if not estab.creator_compensation:
            estab.creator_compensation = "experience_commission"
        estab.listed_on_coins_marocain = True
        if "riad_listed_as_event_venue" in estab.property_id._fields:
            estab.property_id.riad_listed_as_event_venue = True
        Activity = self.env["coins.partner_activity"]
        existing = estab.coins_partner_activity_id
        if not existing:
            existing = Activity.search(
                [("riad_establishment_id", "=", estab.id)], limit=1
            )
        if not existing:
            existing = Activity.search(
                [
                    ("name", "=", estab.name),
                    ("category", "=", "hebergement"),
                ],
                limit=1,
            )
        description = (
            "Lieu partenaire événements / privatisations. "
            "Calendrier de disponibilité en lecture seule depuis Coins Marocain. "
            "La réservation et le blocage chambres restent dans Module Hébergement."
        )
        vals = {
            "name": estab.name or estab.property_id.name,
            "category": "hebergement",
            "relation_type": "direct",
            "state": "signed",
            "signup_channel": "manual",
            "riad_establishment_id": estab.id,
            "commission_pct": estab.creator_commission_pct or 5.0,
            "description": description,
        }
        if existing:
            existing.write(vals)
        else:
            existing = Activity.create(vals)
        estab.coins_partner_activity_id = existing.id
        return existing.id

    def _riad_staff_profiles(self):
        self.ensure_one()
        return self.env["pe.employee.profile"].search(
            [
                ("riad_establishment_id", "=", self.id),
                ("pe_status", "!=", "inactive"),
            ],
            order="riad_role, display_name",
        )

    def _riad_payroll_profiles(self):
        return self._riad_staff_profiles().filtered("riad_in_payroll")

    def compile_payroll_rows(self, year, month):
        self.ensure_one()
        start = date(int(year), int(month), 1)
        last = monthrange(int(year), int(month))[1]
        end = date(int(year), int(month), last)
        profiles = self._riad_payroll_profiles()
        summaries = self.env["pe.presence.summary"].search(
            [
                ("employee_id", "in", profiles.mapped("employee_id").ids),
                ("date", ">=", start),
                ("date", "<=", end),
            ]
        )
        by_emp = {}
        for row in summaries:
            by_emp[row.employee_id.id] = by_emp.get(
                row.employee_id.id, self.env["pe.presence.summary"]
            ) | row
        compiled = []
        for profile in profiles:
            rows = by_emp.get(profile.employee_id.id, self.env["pe.presence.summary"])
            worked = rows.filtered(lambda r: r.statut_jour in ("present", "partiel"))
            late = worked.filtered(lambda r: (r.minutes_late or 0) > 0)
            absences = rows.filtered(lambda r: r.statut_jour == "absent")
            compiled.append(
                {
                    "name": profile.display_name or profile.employee_id.name,
                    "role": profile.riad_role_label(),
                    "wage": profile.riad_wage or 0.0,
                    "days_worked": len(worked),
                    "days_partial": len(worked.filtered(lambda r: r.statut_jour == "partiel")),
                    "absences_planned": len(
                        absences.filtered(lambda r: r.absence_kind in ("planned", "illness"))
                    ),
                    "absences_unplanned": len(
                        absences.filtered(
                            lambda r: r.absence_kind in ("unplanned", "unjustified")
                            or not r.absence_kind
                        )
                    ),
                    "leave_days": len(rows.filtered(lambda r: r.statut_jour == "conge")),
                    "late_count": len(late),
                    "late_minutes": sum(late.mapped("minutes_late")),
                }
            )
        return compiled

    def _payroll_report_html(self, year, month, rows):
        self.ensure_one()
        period = "%s %s" % (MONTHS_FR[int(month)], year)
        title = "Présences / absences — %s — %s" % (self.name or "Établissement", period)
        lines = [
            "<html><body style='font-family:Georgia,serif;color:#241A12;'>",
            "<h2 style='color:#0E4632;'>%s</h2>" % title,
            "<p>Compilation automatique pour le calcul de paie. "
            "Jours travaillés = présents + partiels. "
            "Les retards sont cumulés en minutes.</p>",
            "<table border='1' cellpadding='6' cellspacing='0' style='border-collapse:collapse;font-size:13px;'>",
            "<tr style='background:#FBF7EF;'>"
            "<th>Employé</th><th>Poste</th><th>Salaire de base</th>"
            "<th>Jours travaillés</th>"
            "<th>Dont partiels</th><th>Absences planifiées</th>"
            "<th>Absences non planifiées</th><th>Congés</th>"
            "<th>Retards (nb)</th><th>Retards (min)</th></tr>",
        ]
        if not rows:
            lines.append(
                "<tr><td colspan='10'>Aucun employé inclus dans le rapport pour cet établissement.</td></tr>"
            )
        def _esc(text):
            return (
                (text or "")
                .replace("&", "&amp;")
                .replace("<", "&lt;")
                .replace(">", "&gt;")
            )

        for row in rows:
            lines.append(
                "<tr>"
                "<td>%s</td><td>%s</td><td>%s</td><td>%s</td><td>%s</td>"
                "<td>%s</td><td>%s</td><td>%s</td><td>%s</td><td>%s</td>"
                "</tr>"
                % (
                    _esc(row["name"]),
                    _esc(row["role"]),
                    row.get("wage") or "—",
                    row["days_worked"],
                    row["days_partial"],
                    row["absences_planned"],
                    row["absences_unplanned"],
                    row["leave_days"],
                    row["late_count"],
                    row["late_minutes"],
                )
            )
        lines.append("</table>")
        lines.append(
            "<p style='color:#9C9280;font-size:12px;'>Module Hébergement IntelliX · "
            "données people_engine · établissement #%s</p>" % self.id
        )
        lines.append("</body></html>")
        return title, "".join(lines)

    def action_send_payroll_report(self, year=None, month=None):
        self.ensure_one()
        today = fields.Date.context_today(self)
        if not year or not month:
            first = today.replace(day=1)
            previous = first - timedelta(days=1)
            year, month = previous.year, previous.month
        if not self.payroll_accountant_email:
            raise UserError(
                "Configurez l'email du comptable sur cet établissement avant l'envoi."
            )
        rows = self.compile_payroll_rows(year, month)
        subject, body = self._payroll_report_html(year, month, rows)
        from odoo.addons.doorway_messaging.services.email_service import EmailService

        result = EmailService(self.env).send_email(
            self.payroll_accountant_email,
            subject,
            body,
            recipient_name=self.payroll_accountant_name or "",
        )
        if not result.get("success"):
            raise UserError(result.get("error") or "Échec d'envoi du rapport de paie.")
        self.payroll_last_sent_month = "%04d-%02d" % (int(year), int(month))
        start = date(int(year), int(month), 1)
        last = monthrange(int(year), int(month))[1]
        end = date(int(year), int(month), last)
        summaries = self.env["pe.presence.summary"].search(
            [
                ("riad_establishment_id", "=", self.id),
                ("date", ">=", start),
                ("date", "<=", end),
                ("riad_punch", "=", True),
            ]
        )
        if summaries:
            summaries.with_context(riad_skip_correction_log=True).write(
                {"riad_locked": True}
            )
        self.message_post(
            body="Rapport de présences %s envoyé à %s."
            % (self.payroll_last_sent_month, self.payroll_accountant_email)
        )
        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": "Rapport envoyé",
                "message": "Le rapport a été envoyé à %s." % self.payroll_accountant_email,
                "type": "success",
                "sticky": False,
            },
        }

    def action_send_last_month_payroll_report(self):
        return self.action_send_payroll_report()

    @api.model
    def _ensure_anna_sweety_company(self):
        """Crée/lie la société Riad Anna Sweety. Ne touche aucun employé hors riad."""
        Company = self.env["res.company"].sudo()
        company = Company.search([("name", "=", "Riad Anna Sweety")], limit=1)
        if not company:
            mad = self.env.ref("base.MAD", raise_if_not_found=False)
            company = Company.create(
                {
                    "name": "Riad Anna Sweety",
                    "currency_id": mad.id if mad else self.env.company.currency_id.id,
                }
            )
        estab = self.sudo().search([("name", "=", "Riad Anna Sweety")], limit=1)
        if estab and estab.company_id != company:
            estab.company_id = company.id
        profiles = self.env["pe.employee.profile"].sudo().search(
            [
                ("riad_establishment_id", "!=", False),
                ("employee_id", "!=", False),
            ]
        )
        for profile in profiles:
            employee = profile.employee_id.sudo()
            target = profile.riad_establishment_id.company_id or company
            if target and employee.company_id != target:
                employee.write({"company_id": target.id})
        return True

    @api.model
    def cron_send_payroll_reports(self):
        today = fields.Date.context_today(self)
        first = today.replace(day=1)
        previous = first - timedelta(days=1)
        key = "%04d-%02d" % (previous.year, previous.month)
        establishments = self.search([("payroll_accountant_email", "!=", False)])
        for estab in establishments:
            send_day = min(max(estab.payroll_report_day or 1, 1), 28)
            if today.day != send_day:
                continue
            if estab.payroll_last_sent_month == key:
                continue
            estab.action_send_payroll_report(previous.year, previous.month)

    @api.model
    def set_tourist_tax_from_icp(self, icp_key, rate):
        """Configure le taux d'un établissement déjà lié à une propriété (ICP)."""
        icp = self.env["ir.config_parameter"].sudo()
        raw_id = (icp.get_param(icp_key) or "").strip()
        if not raw_id.isdigit():
            return False
        estab = self.search([("property_id", "=", int(raw_id))], limit=1)
        if not estab:
            return False
        vals = {}
        if not estab.tourist_tax_rate:
            mad = self.env["res.currency"].search([("name", "=", "MAD")], limit=1)
            vals["tourist_tax_rate"] = float(rate or 0)
            vals["tourist_tax_currency_id"] = mad.id if mad else False
            if not estab.tourist_tax_commune:
                vals["tourist_tax_commune"] = "Commune Urbaine de Marrakech"
        if not estab.tax_bordereau_template_id:
            template = self.env.ref(
                "intellix_riad.tax_bordereau_tpl_marrakech", raise_if_not_found=False
            )
            if template:
                vals["tax_bordereau_template_id"] = template.id
        if not estab.tax_operator_name:
            vals["tax_operator_name"] = estab.name
        if vals:
            estab.write(vals)
        return estab.id

    def action_apply_owner_tourist_tax_proposal(self):
        """Karine / Coins : copie la proposition portail vers le taux actif."""
        self.ensure_one()
        if not self.tourist_tax_awaiting_karine and not self.tourist_tax_owner_rate:
            raise UserError(_("Aucune proposition propriétaire à valider."))
        rate = self.tourist_tax_owner_rate or 0.0
        vals = {
            "tourist_tax_rate": rate,
            "tourist_tax_commune": self.tourist_tax_owner_commune
            or self.tourist_tax_commune,
            "tourist_tax_tpt_amount": self.tourist_tax_owner_tpt or 0.0,
            "tourist_tax_communal_amount": self.tourist_tax_owner_communal or 0.0,
            "tourist_tax_pending_confirmation": False,
            "tourist_tax_awaiting_karine": False,
        }
        self.write(vals)
        self.message_post(
            body=_(
                "Proposition taxe propriétaire validée : %(rate)s MAD/pers/nuit — %(commune)s."
            )
            % {"rate": rate, "commune": vals["tourist_tax_commune"] or "—"}
        )
        return True

    def apply_portal_tourist_tax_proposal(self, rate, commune, tpt=0.0, communal=0.0):
        """Portail propriétaire : stocke une proposition sans toucher au taux actif."""
        self.ensure_one()
        self.write(
            {
                "tourist_tax_owner_rate": float(rate or 0),
                "tourist_tax_owner_commune": (commune or "").strip() or False,
                "tourist_tax_owner_tpt": float(tpt or 0),
                "tourist_tax_owner_communal": float(communal or 0),
                "tourist_tax_awaiting_karine": True,
                "tourist_tax_owner_submitted_at": fields.Datetime.now(),
            }
        )
        self.message_post(
            body=_(
                "Proposition taxe reçue via le portail propriétaire : "
                "%(rate)s MAD/pers/nuit (%(commune)s). "
                "<b>En attente de validation Karine</b> — taux actif inchangé "
                "(%(active)s MAD)."
            )
            % {
                "rate": rate or 0,
                "commune": commune or "—",
                "active": self.tourist_tax_rate or 0,
            }
        )
        return True

    def apply_portal_pace_comps(self, names):
        """Remplace/complète le comp-set (max 10) depuis le portail — isolation par établissement."""
        self.ensure_one()
        from html import unescape

        Comp = self.env["intellix.riad.comp.riad"].sudo()
        cleaned = []
        for raw in names or []:
            name = unescape((raw or "").strip())
            if name and name not in cleaned:
                cleaned.append(name[:120])
            if len(cleaned) >= 10:
                break
        existing = Comp.search(
            [("establishment_id", "=", self.id)], order="sequence, id"
        )
        # Update in place by index, archive extras, create missing
        for idx, name in enumerate(cleaned):
            seq = (idx + 1) * 10
            if idx < len(existing):
                existing[idx].write(
                    {
                        "name": name,
                        "booking_label": name,
                        "sequence": seq,
                        "active": True,
                        "notes": "Saisi via portail propriétaire (Pace/Booking Analytics).",
                        "source_kind": "booking_analytics",
                    }
                )
            else:
                Comp.create(
                    {
                        "name": name,
                        "booking_label": name,
                        "establishment_id": self.id,
                        "sequence": seq,
                        "active": True,
                        "notes": "Saisi via portail propriétaire (Pace/Booking Analytics).",
                        "source_kind": "booking_analytics",
                    }
                )
        if len(existing) > len(cleaned):
            existing[len(cleaned) :].write({"active": False})
        self.message_post(
            body=_("Comp-set Pace mis à jour via le portail (%s nom(s)).")
            % len(cleaned)
        )
        return True

    def apply_portal_guest_library(self, vals):
        """Portail : bibliothèque voyageurs propre à cet établissement uniquement."""
        self.ensure_one()
        allowed = {
            "experience_wifi",
            "experience_house_rules",
            "experience_useful_contacts",
            "experience_local_tips",
            "experience_howto",
            "experience_facts",
            "experience_neighborhood",
        }
        clean = {}
        for key, raw in (vals or {}).items():
            if key not in allowed:
                continue
            text = (raw or "").strip()
            clean[key] = text or False
        if "experience_checkin_hour" in (vals or {}):
            try:
                clean["experience_checkin_hour"] = float(
                    str(vals.get("experience_checkin_hour") or "14").replace(",", ".")
                )
            except (TypeError, ValueError):
                pass
        if "experience_checkout_hour" in (vals or {}):
            try:
                clean["experience_checkout_hour"] = float(
                    str(vals.get("experience_checkout_hour") or "11").replace(",", ".")
                )
            except (TypeError, ValueError):
                pass
        if clean:
            clean["experience_agent_enabled"] = True
            self.write(clean)
            self.message_post(
                body=_("Bibliothèque voyageurs mise à jour via le portail propriétaire.")
            )
        return True

    def portal_message_threads(self, limit=40):
        """Conversations visibles dans l'onglet Messages — isolées à cet établissement."""
        self.ensure_one()
        Thread = self.env["intellix.riad.experience.thread"].sudo()
        return Thread.search(
            [
                ("establishment_id", "=", self.id),
                ("channel", "in", ("whatsapp", "booking", "airbnb", "other")),
            ],
            order="inbound_at desc, id desc",
            limit=limit,
        )

    def portal_ota_rows(self):
        """Statuts connexion + disponibilité messagerie auto (honnête)."""
        self.ensure_one()
        # Channex Messages API : Booking / Airbnb / Expedia seulement — pas encore
        # branchée dans Coins (ARI + résas uniquement). Agoda : hors Messages.
        rows = [
            {
                "code": "booking",
                "label": "Booking.com",
                "guide_url": "https://docs.channex.io/channel-mapping-guides/booking.com",
                "status": self.ota_booking_status or "not_connected",
                "status_label": dict(self._fields["ota_booking_status"].selection).get(
                    self.ota_booking_status or "not_connected"
                ),
                "messaging": "unavailable",
                "messaging_label": _(
                    "Auto-réponse non disponible — API Messages Channex pas encore "
                    "branchée (connexion ARI possible via le guide)."
                ),
                "owner_note": _(
                    "La connexion se fait depuis VOTRE extranet Booking (2FA sur "
                    "votre téléphone). Personne d’autre ne peut le faire à votre place."
                ),
            },
            {
                "code": "airbnb",
                "label": "Airbnb",
                "guide_url": "https://docs.channex.io/channel-mapping-guides/airbnb",
                "status": self.ota_airbnb_status or "not_connected",
                "status_label": dict(self._fields["ota_airbnb_status"].selection).get(
                    self.ota_airbnb_status or "not_connected"
                ),
                "messaging": "unavailable",
                "messaging_label": _(
                    "Auto-réponse non disponible — API Messages Channex pas encore "
                    "branchée."
                ),
                "owner_note": _(
                    "Airbnb n’accepte qu’un seul channel manager actif. "
                    "Déconnectez tout autre outil avant de connecter Channex."
                ),
            },
            {
                "code": "expedia",
                "label": "Expedia",
                "guide_url": "https://docs.channex.io/channel-mapping-guides/expedia",
                "status": self.ota_expedia_status or "not_connected",
                "status_label": dict(self._fields["ota_expedia_status"].selection).get(
                    self.ota_expedia_status or "not_connected"
                ),
                "messaging": "unavailable",
                "messaging_label": _(
                    "Auto-réponse non disponible — API Messages Channex pas encore "
                    "branchée (EPS Affiliate Network : messagerie souvent absente)."
                ),
                "owner_note": _(
                    "Suivez le guide officiel depuis votre compte Expedia / EPS."
                ),
            },
            {
                "code": "agoda",
                "label": "Agoda",
                "guide_url": "https://docs.channex.io/channel-mapping-guides/agoda",
                "status": self.ota_agoda_status or "not_connected",
                "status_label": dict(self._fields["ota_agoda_status"].selection).get(
                    self.ota_agoda_status or "not_connected"
                ),
                "messaging": "unsupported",
                "messaging_label": _(
                    "Auto-réponse non disponible sur cette plateforme — "
                    "Channex Messages ne couvre pas Agoda."
                ),
                "owner_note": _(
                    "Vous pouvez connecter Agoda pour les disponibilités/tarifs ; "
                    "pas de chat invité automatisé via Channex."
                ),
            },
            {
                "code": "vrbo",
                "label": "VRBO",
                "guide_url": "https://docs.channex.io/channel-mapping-guides/vrbo",
                "status": self.ota_vrbo_status or "not_connected",
                "status_label": dict(self._fields["ota_vrbo_status"].selection).get(
                    self.ota_vrbo_status or "not_connected"
                ),
                "messaging": "unavailable",
                "messaging_label": _(
                    "Auto-réponse non disponible — API Messages Channex pas encore "
                    "branchée."
                ),
                "owner_note": _(
                    "Compte VRBO / HomeAway requis. Authentifiez-vous dans Channex "
                    "(SMS 2FA possible), mappez chambres/tarifs, puis activez."
                ),
            },
            {
                "code": "feratel",
                "label": "Feratel",
                "guide_url": "https://docs.channex.io/channel-mapping-guides/feratel",
                "status": self.ota_feratel_status or "not_connected",
                "status_label": dict(self._fields["ota_feratel_status"].selection).get(
                    self.ota_feratel_status or "not_connected"
                ),
                "messaging": "unavailable",
                "messaging_label": _(
                    "Auto-réponse non disponible — API Messages Channex pas encore "
                    "branchée."
                ),
                "owner_note": _(
                    "Contrat direct Feratel + Hotel ID requis. Demandez à Feratel "
                    "d’autoriser Channex avant de créer le canal."
                ),
            },
            {
                "code": "inntopia",
                "label": "Inntopia",
                "guide_url": "https://docs.channex.io/channel-mapping-guides/inntopia",
                "status": self.ota_inntopia_status or "not_connected",
                "status_label": dict(self._fields["ota_inntopia_status"].selection).get(
                    self.ota_inntopia_status or "not_connected"
                ),
                "messaging": "unavailable",
                "messaging_label": _(
                    "Auto-réponse non disponible — API Messages Channex pas encore "
                    "branchée."
                ),
                "owner_note": _(
                    "Contrat Inntopia + Hotel ID + codes cross-référence Channex "
                    "dans l’extranet Inntopia avant connexion."
                ),
            },
            {
                "code": "hrs",
                "label": "HRS",
                "guide_url": "https://docs.channex.io/channel-mapping-guides/hrs",
                "status": self.ota_hrs_status or "not_connected",
                "status_label": dict(self._fields["ota_hrs_status"].selection).get(
                    self.ota_hrs_status or "not_connected"
                ),
                "messaging": "unavailable",
                "messaging_label": _(
                    "Auto-réponse non disponible — API Messages Channex pas encore "
                    "branchée."
                ),
                "owner_note": _(
                    "Contrat HRS + Hotel ID. Demandez à HRS de connecter le bien "
                    "à Channex (1 tarif par chambre recommandé)."
                ),
            },
            {
                "code": "smith",
                "label": "Mr & Mrs Smith",
                "guide_url": "https://docs.channex.io/channel-mapping-guides/smith",
                "status": self.ota_smith_status or "not_connected",
                "status_label": dict(self._fields["ota_smith_status"].selection).get(
                    self.ota_smith_status or "not_connected"
                ),
                "messaging": "unavailable",
                "messaging_label": _(
                    "Auto-réponse non disponible — API Messages Channex pas encore "
                    "branchée."
                ),
                "owner_note": _(
                    "Contrat Mr & Mrs Smith + Hotel ID. Demandez-leur d’activer "
                    "le channel manager Channex."
                ),
            },
            {
                "code": "trip",
                "label": "Trip.com / Ctrip",
                "guide_url": "https://docs.channex.io/channel-mapping-guides/ctrip-trip.com",
                "status": self.ota_trip_status or "not_connected",
                "status_label": dict(self._fields["ota_trip_status"].selection).get(
                    self.ota_trip_status or "not_connected"
                ),
                "messaging": "unavailable",
                "messaging_label": _(
                    "Auto-réponse non disponible — API Messages Channex pas encore "
                    "branchée."
                ),
                "owner_note": _(
                    "Dans Trip.com eBooking : Connectivity Settings → choisir Channex, "
                    "puis créer le canal Ctrip dans Channex avec votre Hotel ID."
                ),
            },
            {
                "code": "google",
                "label": "Google Hotel / Vacation Rental Ads",
                "guide_url": "https://docs.channex.io/google/google-hotel-ads",
                "status": self.ota_google_status or "not_connected",
                "status_label": dict(self._fields["ota_google_status"].selection).get(
                    self.ota_google_status or "not_connected"
                ),
                "messaging": "unsupported",
                "messaging_label": _(
                    "Pas de messagerie invité — Google Ads / free listing uniquement."
                ),
                "owner_note": _(
                    "Complétez d’abord la fiche Channex (adresse, photos, politiques). "
                    "Canal « Google Hotel Search ». Vacation Rentals : "
                    "https://docs.channex.io/google/google-hotel-ads-1 — 1 room type "
                    "si type Vacation Rental."
                ),
            },
            {
                "code": "instant",
                "label": "Instant Booking Page",
                "guide_url": "https://docs.channex.io/channel-mapping-guides/instant-booking-page",
                "status": self.ota_instant_status or "not_connected",
                "status_label": dict(self._fields["ota_instant_status"].selection).get(
                    self.ota_instant_status or "not_connected"
                ),
                "messaging": "unavailable",
                "messaging_label": _(
                    "Moteur de réservation Channex (page directe) — pas de messagerie OTA."
                ),
                "owner_note": _(
                    "Gratuit via Channex. Remplir le contenu propriété (adresse, "
                    "photos, politiques, équipements) avant d’activer le canal."
                ),
            },
            {
                "code": "whatsapp",
                "label": "WhatsApp",
                "guide_url": False,
                "status": {
                    "live": "connected",
                    "number_ready": "pending",
                    "meta_pending": "pending",
                }.get(self.whatsapp_provision_status or "not_started", "not_connected"),
                "status_label": dict(
                    self._fields["whatsapp_provision_status"].selection
                ).get(self.whatsapp_provision_status or "not_started"),
                "messaging": "available" if self.whatsapp_provision_status == "live" else "pending",
                "messaging_label": (
                    _(
                        "Disponible — numéro dédié %(num)s. Conversations visibles "
                        "dans l’onglet Messages de ce lieu uniquement."
                    )
                    % {"num": self.whatsapp_e164 or "—"}
                    if self.whatsapp_provision_status == "live"
                    else _(
                        "En attente de provisionnement — un numéro WhatsApp Business "
                        "dédié par lieu (pas le numéro Yasmine). Voir procédure Coins."
                    )
                ),
                "owner_note": _(
                    "Chaque lieu a son propre numéro Business. Vous voyez uniquement "
                    "les conversations de cet établissement dans Messages."
                ),
            },
        ]
        return rows

    def apply_portal_ota_pending(self, codes):
        """Propriétaire signale avoir lancé la connexion OTA → En attente."""
        self.ensure_one()
        mapping = {
            "booking": "ota_booking_status",
            "airbnb": "ota_airbnb_status",
            "expedia": "ota_expedia_status",
            "agoda": "ota_agoda_status",
            "vrbo": "ota_vrbo_status",
            "feratel": "ota_feratel_status",
            "inntopia": "ota_inntopia_status",
            "hrs": "ota_hrs_status",
            "smith": "ota_smith_status",
            "trip": "ota_trip_status",
            "google": "ota_google_status",
            "instant": "ota_instant_status",
        }
        vals = {}
        for code in codes or []:
            field = mapping.get(code)
            if not field:
                continue
            current = self[field]
            if current != "connected":
                vals[field] = "pending"
        if vals:
            self.write(vals)
        return True

    def action_refresh_ota_statuses_from_channex(self):
        """Back-office : lit GET /channels pour ce bien Channex."""
        from odoo.addons.coins_marocain.services.channex_service import (
            ChannexNotConfigured,
            ChannexService,
        )

        for estab in self:
            prop = estab.property_id
            if not prop:
                continue
            mapping = self.env["coins.channex.mapping"].sudo().search(
                [("property_id", "=", prop.id), ("kind", "=", "property")], limit=1
            )
            if not mapping:
                continue
            try:
                svc = ChannexService(self.env)
                channels = svc.list_channels(mapping.channex_id) or []
            except ChannexNotConfigured:
                continue
            except Exception:  # noqa: BLE001
                _logger.exception(
                    "refresh OTA statuses estab=%s", estab.id
                )
                continue
            by_code = {
                "BookingCom": "ota_booking_status",
                "Booking": "ota_booking_status",
                "BDC": "ota_booking_status",
                "Airbnb": "ota_airbnb_status",
                "ABB": "ota_airbnb_status",
                "Expedia": "ota_expedia_status",
                "EXP": "ota_expedia_status",
                "Agoda": "ota_agoda_status",
                "AGO": "ota_agoda_status",
                "VRBO": "ota_vrbo_status",
                "VRB": "ota_vrbo_status",
                "HomeAway": "ota_vrbo_status",
                "Feratel": "ota_feratel_status",
                "FER": "ota_feratel_status",
                "Inntopia": "ota_inntopia_status",
                "INN": "ota_inntopia_status",
                "ITP": "ota_inntopia_status",
                "HRS": "ota_hrs_status",
                "MrAndMrsSmith": "ota_smith_status",
                "MrAndMrsSmiths": "ota_smith_status",
                "MMS": "ota_smith_status",
                "Smith": "ota_smith_status",
                "Ctrip": "ota_trip_status",
                "TripCom": "ota_trip_status",
                "Trip": "ota_trip_status",
                "CTR": "ota_trip_status",
                "Google": "ota_google_status",
                "GoogleHotelSearch": "ota_google_status",
                "GoogleHotelAds": "ota_google_status",
                "GHS": "ota_google_status",
                "InstantBookingPage": "ota_instant_status",
                "OSA": "ota_instant_status",
                "BookingEngine": "ota_instant_status",
            }
            found = {f: "not_connected" for f in set(by_code.values())}
            for node in channels:
                attrs = (node or {}).get("attributes") or node or {}
                code = (
                    attrs.get("channel")
                    or attrs.get("channel_code")
                    or (node or {}).get("type")
                    or ""
                )
                field = by_code.get(str(code))
                if not field:
                    # fuzzy
                    low = str(code).lower()
                    if "booking" in low and "engine" not in low and "instant" not in low:
                        field = "ota_booking_status"
                    elif "airbnb" in low:
                        field = "ota_airbnb_status"
                    elif "expedia" in low:
                        field = "ota_expedia_status"
                    elif "agoda" in low:
                        field = "ota_agoda_status"
                    elif "vrbo" in low or "homeaway" in low or low == "vrb":
                        field = "ota_vrbo_status"
                    elif "feratel" in low or low == "fer":
                        field = "ota_feratel_status"
                    elif "inntopia" in low:
                        field = "ota_inntopia_status"
                    elif low == "hrs":
                        field = "ota_hrs_status"
                    elif "smith" in low or low == "mms":
                        field = "ota_smith_status"
                    elif "ctrip" in low or "trip.com" in low or low in ("trip", "ctr"):
                        field = "ota_trip_status"
                    elif "google" in low or low == "ghs":
                        field = "ota_google_status"
                    elif "instant" in low or low == "osa" or "bookingengine" in low:
                        field = "ota_instant_status"
                if not field:
                    continue
                active = attrs.get("is_active")
                if active is True or str(attrs.get("status") or "").lower() in (
                    "active",
                    "connected",
                    "live",
                ):
                    found[field] = "connected"
                elif found[field] != "connected":
                    found[field] = "pending"
            found["ota_status_synced_at"] = fields.Datetime.now()
            estab.write(found)
        return True

    def _tax_report_recipient(self):
        self.ensure_one()
        email = self.tax_report_email or self.payroll_accountant_email
        name = self.tax_report_name or self.payroll_accountant_name or ""
        return email, name

    def _quarter_bounds(self, year, quarter):
        quarter = int(quarter)
        start_month = (quarter - 1) * 3 + 1
        start = date(int(year), start_month, 1)
        end_month = start_month + 2
        end = date(int(year), end_month, monthrange(int(year), end_month)[1])
        return start, end

    def _previous_quarter(self, day=None):
        day = day or fields.Date.context_today(self)
        quarter = (day.month - 1) // 3 + 1
        if quarter == 1:
            return day.year - 1, 4
        return day.year, quarter - 1

    def _quarter_due_date(self, year, quarter):
        year, quarter = int(year), int(quarter)
        if quarter == 1:
            return date(year, 4, 30)
        if quarter == 2:
            return date(year, 7, 31)
        if quarter == 3:
            return date(year, 10, 31)
        return date(year + 1, 1, 31)

    def compile_tourist_tax_rows(self, year, quarter):
        self.ensure_one()
        start, end = self._quarter_bounds(year, quarter)
        reservations = self.env["coins.reservation"].search(
            [
                ("property_id", "=", self.property_id.id),
                ("state", "in", ("confirmed", "in_progress", "done")),
                ("check_in", "<=", end),
                ("check_out", ">", start),
                ("riad_privatisation_id", "=", False),
            ],
            order="check_in, id",
        )
        rows = []
        total_tax = 0.0
        total_room = 0.0
        for resa in reservations:
            tax = resa.riad_tourist_tax_amount or 0.0
            room = resa.amount_property or 0.0
            total_tax += tax
            total_room += room
            rows.append(
                {
                    "name": resa.name or "",
                    "guest": resa.client_nom or resa.traveler_id.name or "",
                    "check_in": resa.check_in,
                    "check_out": resa.check_out,
                    "guests": resa.riad_taxable_guests or resa.voyageurs or 0,
                    "nights": resa.nights or 0,
                    "rate": resa.riad_tourist_tax_rate or self.tourist_tax_rate or 0,
                    "tax": tax,
                    "room": room,
                    "room_currency": resa.currency_id.symbol or "",
                }
            )
        return {
            "start": start,
            "end": end,
            "rows": rows,
            "total_tax": total_tax,
            "total_room": total_room,
            "rate": self.tourist_tax_rate or 0,
        }

    def _ensure_tax_template(self):
        self.ensure_one()
        if self.tax_bordereau_template_id:
            return self.tax_bordereau_template_id
        raise UserError(
            _(
                "Choisissez le modèle de bordereau de la commune sur cet établissement. "
                "Chaque commune a son propre imprimé."
            )
        )

    def get_or_create_tax_bordereau(self, year, quarter):
        self.ensure_one()
        template = self._ensure_tax_template()
        Bordereau = self.env["intellix.riad.tax.bordereau"]
        rec = Bordereau.search(
            [
                ("establishment_id", "=", self.id),
                ("year", "=", int(year)),
                ("quarter", "=", str(int(quarter))),
            ],
            limit=1,
        )
        if not rec:
            rec = Bordereau.create(
                {
                    "establishment_id": self.id,
                    "template_id": template.id,
                    "year": int(year),
                    "quarter": str(int(quarter)),
                }
            )
        rec._refresh_from_stays()
        return rec

    def _tourist_tax_notice_html(self, bordereau):
        self.ensure_one()
        title = bordereau.name
        body = (
            "<html><body style='font-family:Georgia,serif;color:#241A12;'>"
            "<h2 style='color:#0E4632;'>%s</h2>"
            "<p>%s</p>"
            "<p><b>%s</b> : %s<br/>"
            "<b>%s</b> : %s<br/>"
            "<b>%s</b> : %.2f %s</p>"
            "<p>%s</p>"
            "</body></html>"
        ) % (
            title,
            _(
                "Le bordereau officiel de taxe de séjour est prêt à imprimer "
                "et à déposer à la recette communale. "
                "Ce message ne remplace pas le document papier."
            ),
            _("Nombre de clients"),
            bordereau.guests_count,
            _("Nombre de nuitées"),
            bordereau.nights_count,
            _("Montant total dû"),
            bordereau.amount_due or 0,
            bordereau.currency_id.symbol or "DH",
            _(
                "Imprimez le bordereau depuis Module Hébergement → "
                "Bordereaux taxe de séjour. "
                "Les fiches de police (DGSN) sont un flux distinct."
            ),
        )
        return title, body

    def action_send_tourist_tax_report(self, year=None, quarter=None):
        self.ensure_one()
        if not year or not quarter:
            year, quarter = self._previous_quarter()
        bordereau = self.get_or_create_tax_bordereau(year, quarter)
        email, name = self._tax_report_recipient()
        if email:
            from odoo.addons.doorway_messaging.services.email_service import EmailService

            subject, body = self._tourist_tax_notice_html(bordereau)
            result = EmailService(self.env).send_email(
                email, subject, body, recipient_name=name
            )
            if not result.get("success"):
                raise UserError(
                    result.get("error") or _("Échec d'envoi de l'avis de bordereau.")
                )
            bordereau.action_mark_sent()
        self.tax_last_sent_quarter = "%04d-Q%s" % (int(year), int(quarter))
        self.message_post(
            body=_("Bordereau taxe de séjour %s généré.") % self.tax_last_sent_quarter
        )
        return {
            "type": "ir.actions.act_window",
            "name": bordereau.name,
            "res_model": "intellix.riad.tax.bordereau",
            "res_id": bordereau.id,
            "view_mode": "form",
            "target": "current",
        }

    def action_send_last_quarter_tourist_tax_report(self):
        return self.action_send_tourist_tax_report()

    def action_print_last_quarter_tax_bordereau(self):
        self.ensure_one()
        year, quarter = self._previous_quarter()
        bordereau = self.get_or_create_tax_bordereau(year, quarter)
        return bordereau.action_print()

    @api.model
    def cron_send_tourist_tax_reports(self):
        """Génère le bordereau en début de mois suivant, avant l'échéance de fin de mois."""
        today = fields.Date.context_today(self)
        year, quarter = self._previous_quarter(today)
        due = self._quarter_due_date(year, quarter)
        month_after = date(due.year, due.month, 1)
        if today < month_after or today > due:
            return True
        key = "%04d-Q%s" % (year, quarter)
        for estab in self.search([("tax_bordereau_template_id", "!=", False)]):
            generate_day = min(max(estab.tax_report_generate_day or 5, 1), 20)
            if today.day < generate_day:
                continue
            if estab.tax_last_sent_quarter == key:
                continue
            try:
                estab.action_send_tourist_tax_report(year, quarter)
            except Exception:
                _logger.exception(
                    "Bordereau taxe de séjour %s — établissement %s",
                    key,
                    estab.id,
                )
        return True

    @api.model
    def cron_send_experience_review_invites(self):
        return self.env["intellix.riad.experience.agent"].cron_send_review_invites()

    def _review_now_local(self):
        return fields.Datetime.context_timestamp(self, fields.Datetime.now())

    def _review_first_due(self, resa):
        """Premier message : check-out + délai (2 h par défaut)."""
        if not resa.check_out:
            return False
        delay = max(self.experience_review_delay_hours or 2, 0)
        checkout_h = self.experience_checkout_hour or 11.0
        target_h = checkout_h + delay
        extra_days = int(target_h // 24)
        target_h = target_h % 24
        due_date = resa.check_out + timedelta(days=extra_days)
        now = self._review_now_local()
        today = now.date()
        now_h = now.hour + now.minute / 60.0
        if today > due_date:
            return True
        return today == due_date and now_h >= target_h

    def _review_guest_first(self, resa):
        name = ""
        if hasattr(resa, "_guest_contact"):
            _email, _phone, name = resa._guest_contact()
        else:
            name = resa.client_nom or ""
        name = (name or "").strip()
        return name.split()[0] if name else ""

    def _review_stay_bits(self, resa):
        check_in = resa.check_in.strftime("%d/%m/%Y") if resa.check_in else "—"
        check_out = resa.check_out.strftime("%d/%m/%Y") if resa.check_out else "—"
        nights = resa.nights or 0
        return check_in, check_out, nights

    def _review_message_ota(self, resa):
        """Remerciement seul — Booking/Airbnb, aucun lien d'avis."""
        first = self._review_guest_first(resa) or _("vous")
        house = self.name or ""
        check_in, check_out, nights = self._review_stay_bits(resa)
        text = _(
            "Bonjour %s,\n\n"
            "Votre séjour au %s s'est achevé — %s nuit(s), du %s au %s. "
            "Merci de nous avoir fait confiance.\n\n"
            "On garde un bon souvenir de votre passage. Belle route, "
            "et à une prochaine fois à Marrakech.\n\n"
            "%s"
        ) % (first, house, nights, check_in, check_out, house)
        html = "<p>%s</p>" % text.replace("\n\n", "</p><p>").replace("\n", "<br/>")
        return text, html

    def _review_message_direct(self, resa, followup=False, google=None, facebook=None):
        """Remerciement + Google Business + Facebook — canaux sans avis intégré."""
        first = self._review_guest_first(resa) or _("vous")
        house = self.name or ""
        check_in, check_out, nights = self._review_stay_bits(resa)
        google = (google if google is not None else self.google_review_url or "").strip()
        facebook = (
            facebook if facebook is not None else self.facebook_review_url or ""
        ).strip()
        links_txt = []
        links_html = []
        if google:
            links_txt.append("Google : %s" % google)
            links_html.append(
                "<a href='%s' style='color:#145C42;'>Laisser un mot sur Google</a>"
                % google
            )
        if facebook:
            links_txt.append("Facebook : %s" % facebook)
            links_html.append(
                "<a href='%s' style='color:#145C42;'>Un mot sur Facebook</a>"
                % facebook
            )
        links_block = "\n".join(links_txt)
        links_html_block = " · ".join(links_html)
        if followup:
            text = _(
                "Bonjour %s,\n\n"
                "Juste un mot, sans insister : si votre séjour au %s "
                "(du %s au %s) vous a laissé un bon souvenir, Google et Facebook "
                "sont les deux endroits où un petit mot aide d'autres voyageurs "
                "à nous trouver — uniquement si cela vous dit.\n\n"
                "%s\n\n"
                "Merci encore,\n%s"
            ) % (first, house, check_in, check_out, links_block, house)
        else:
            text = _(
                "Bonjour %s,\n\n"
                "Votre séjour au %s s'est achevé — %s nuit(s), du %s au %s. "
                "Merci de nous avoir choisis.\n\n"
                "Si le riad vous a laissé un bon souvenir, un mot sur Google "
                "ou Facebook aide d'autres voyageurs à nous trouver — "
                "les deux sont là, à vous de voir :\n\n"
                "%s\n\n"
                "À très bientôt,\n%s"
            ) % (first, house, nights, check_in, check_out, links_block, house)
        html = "<p>%s</p>" % text.replace("\n\n", "</p><p>").replace("\n", "<br/>")
        if links_html_block:
            html = html.replace(links_block.replace("\n", "<br/>"), links_html_block)
        return text, html

    def preview_review_templates(self, reservation=None):
        """Les deux templates (avec / sans liens) pour contrôle."""
        self.ensure_one()
        if reservation:
            resa = reservation
        else:
            today = fields.Date.context_today(self)
            resa = type(
                "PreviewResa",
                (),
                {
                    "check_in": today - timedelta(days=3),
                    "check_out": today,
                    "nights": 3,
                    "client_nom": "Karine Barmaki",
                    "_guest_contact": lambda self: (
                        "",
                        "",
                        "Karine Barmaki",
                    ),
                },
            )()
        google = (self.google_review_url or "").strip() or (
            "https://g.page/r/riad-anna-sweety/review"
        )
        facebook = (self.facebook_review_url or "").strip() or (
            "https://www.facebook.com/riadannasweety/reviews"
        )
        ota_txt, ota_html = self._review_message_ota(resa)
        dir_txt, dir_html = self._review_message_direct(
            resa, google=google, facebook=facebook
        )
        fol_txt, fol_html = self._review_message_direct(
            resa, followup=True, google=google, facebook=facebook
        )
        return {
            "ota_thanks": {"text": ota_txt, "html": ota_html},
            "direct_ask": {"text": dir_txt, "html": dir_html},
            "direct_followup": {"text": fol_txt, "html": fol_html},
        }

    @api.model
    def _align_review_delay_hours(self, hours=2):
        stale = self.search([("experience_review_delay_hours", "in", (0, 24))])
        if stale:
            stale.write({"experience_review_delay_hours": int(hours or 2)})
        return True

    def _dispatch_review_message(self, resa, subject, text, html):
        from odoo.addons.doorway_messaging.services.email_service import EmailService

        email, phone, name = (
            resa._guest_contact()
            if hasattr(resa, "_guest_contact")
            else ("", "", "")
        )
        sent = False
        if email:
            wrapped = (
                "<html><body style='font-family:Georgia,serif;color:#241A12;"
                "background:#FBF7EF;padding:20px;'>%s</body></html>"
            ) % html
            result = EmailService(self.env).send_email(
                email, subject, wrapped, recipient_name=name or ""
            )
            sent = bool(result.get("success"))
        if phone:
            try:
                from odoo.addons.doorway_messaging.services.whatsapp_service import (
                    WhatsAppService,
                )

                wa = WhatsAppService(self.env).send_whatsapp(
                    to_number=phone, body=text
                )
                sent = sent or bool(wa.get("success"))
            except Exception:
                _logger.exception("Avis WhatsApp réservation %s", resa.id)
        resa.message_post(body=subject)
        return sent

    def _send_due_review_invites(self, today=None):
        self.ensure_one()
        today = today or fields.Date.context_today(self)
        Res = self.env["coins.reservation"]
        first = Res.search(
            [
                ("property_id", "=", self.property_id.id),
                ("state", "in", ("confirmed", "in_progress", "done")),
                ("riad_review_asked", "=", False),
                ("riad_privatisation_id", "=", False),
                ("check_out", "<=", today),
                ("check_out", ">=", today - timedelta(days=8)),
            ]
        )
        follow = Res.search(
            [
                ("property_id", "=", self.property_id.id),
                ("state", "in", ("confirmed", "in_progress", "done")),
                ("riad_review_asked", "=", True),
                ("riad_review_ota_thanks", "=", False),
                ("riad_review_followup_sent", "=", False),
                ("riad_privatisation_id", "=", False),
                ("check_out", "<=", today - timedelta(days=5)),
                ("check_out", ">=", today - timedelta(days=12)),
            ]
        )
        house = self.name or ""
        for resa in first:
            if not self._review_first_due(resa):
                continue
            skip_links = resa._riad_skip_google_facebook_review()
            if skip_links:
                text, html = self._review_message_ota(resa)
                subject = _("Merci pour votre séjour — %s") % house
            else:
                text, html = self._review_message_direct(resa)
                subject = _("Après votre séjour — %s") % house
            self._dispatch_review_message(resa, subject, text, html)
            resa.write(
                {
                    "riad_review_asked": True,
                    "riad_review_ota_thanks": skip_links,
                }
            )
        for resa in follow:
            if resa._riad_skip_google_facebook_review() or resa.riad_review_ota_thanks:
                continue
            text, html = self._review_message_direct(resa, followup=True)
            subject = _("Un mot, si le cœur vous en dit — %s") % house
            self._dispatch_review_message(resa, subject, text, html)
            resa.riad_review_followup_sent = True
        return True

