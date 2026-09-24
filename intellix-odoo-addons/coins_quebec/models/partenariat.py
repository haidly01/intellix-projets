# -*- coding: utf-8 -*-
import os

import pytz
from markupsafe import Markup, escape

from odoo import _, api, fields, models
from odoo.exceptions import UserError

CQ_CANADA_TZ = "America/Toronto"


def cq_format_canada_short(dt):
    """UTC naïf → jj/mm/aaaa HHhMM (Toronto)."""
    if not dt:
        return False
    tz = pytz.timezone(CQ_CANADA_TZ)
    if getattr(dt, "tzinfo", None):
        local = dt.astimezone(tz)
    else:
        local = pytz.UTC.localize(dt).astimezone(tz)
    return local.strftime("%d/%m/%Y %Hh%M")


def cq_click_to_call_action(env, phone, lead_id=None):
    """Ouvre le poste VICIdial avec le numéro — même flux pour tout le monde."""
    phone = (phone or "").strip()
    if not phone:
        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": _("Téléphone"),
                "message": _("Aucun numéro renseigné sur cette fiche."),
                "type": "warning",
                "sticky": False,
            },
        }
    return {
        "type": "ir.actions.client",
        "tag": "vicidial_workstation_action",
        "params": {
            "doorway_vicidial_dial_phone": phone,
            "doorway_vicidial_lead_id": lead_id or 0,
        },
    }
from odoo.modules.module import get_module_path

CQ_REGIONS = [
    ("montreal", "Montréal"),
    ("quebec", "Québec"),
    ("laurentides", "Laurentides"),
    ("estrie", "Estrie"),
    ("outaouais", "Outaouais"),
    ("monteregie", "Montérégie"),
    ("sorel", "Sorel"),
    ("autre", "Ailleurs au Québec"),
]

# Kanban partenariat (Karine Barmaki) : Nouveau → Contacté → En RDV → Suivis → Entente.
# Gagné / Perdu restent après Entente (données conservées, colonnes repliées côté CRM).
# L'ordre kanban = group_expand + sequence, pas ORDER BY clé SQL.
CQ_PIPELINE_STAGES = [
    ("nouveau", "Nouveau"),
    ("contacte", "Contacté"),
    ("en_rdv", "En RDV"),
    ("suivi", "Suivis"),
    ("entente", "Entente"),
    ("gagne", "Gagné"),
    ("perdu", "Perdu"),
]
CQ_STAGES_CLOSED = ("gagne", "perdu")
CQ_PIPELINE_OBSOLETE = (
    "attribue",
    "relance",
    "signe",
    "qualifie",
    "reserve",
)


def cq_group_expand_stage(records, stages, domain, order=None):
    """Colonnes kanban = sequence ir.model.fields.selection (ignore order SQL)."""
    del stages, domain, order
    Selection = records.env["ir.model.fields.selection"].sudo()
    field = records.env["ir.model.fields"].sudo().search(
        [("model", "=", records._name), ("name", "=", "stage")], limit=1
    )
    if field:
        recs = Selection.search([("field_id", "=", field.id)], order="sequence, id")
        values = [r.value for r in recs if r.value in dict(CQ_PIPELINE_STAGES)]
        if values:
            return values
    return [value for value, _label in CQ_PIPELINE_STAGES]

CQ_TYPES_PARTENAIRE = [
    ("hebergement", "Hôtel / hébergement"),
    ("resto", "Restaurant / Gourmand"),
    ("spa", "Spa / bien-être"),
    ("activite", "Activité"),
    ("evenement", "Événement"),
    ("traiteur", "Traiteur"),
    ("fleuriste", "Fleuriste"),
    ("dj", "DJ / animation"),
    ("mobilier", "Location mobilier"),
    ("autre", "Autre"),
]

# Pastille calendrier Martin (user 10) — mauve, pas Michel.
CQ_MARTIN_CALENDAR_COLOR = 10

# Calendrier RDV : Martin uniquement (décision Karine Barmaki).
# Pas de répartition auto par région.
CQ_MARTIN_LOGIN = "martin@agencedoorway.com"

# Sous-zones Laurentides (recrutement Michel) — région = laurentides.
CQ_LAURENTIDES_ZONES = [
    ("mont_tremblant", "Mont-Tremblant"),
    ("saint_sauveur", "Saint-Sauveur"),
    ("corridor_spas", "Corridor spas (Sainte-Adèle / Sainte-Agathe / Val-David)"),
    ("saint_jerome_sud", "Saint-Jérôme / sud Laurentides"),
    ("labelle_nord", "Labelle / Tremblant nord"),
    ("autre", "Autre zone"),
]


class CoinsQuebecPartenariat(models.Model):
    _name = "coins.quebec.partenariat"
    _description = "Fiche partenariat (Coins Québec)"
    _inherit = ["mail.thread", "mail.activity.mixin", "coins.quebec.assignee.mixin"]
    _order = "id desc"
    _rec_name = "name"
    _rec_names_search = [
        "name",
        "contact_name",
        "contact_firstname",
        "contact_lastname",
        "email",
        "phone",
        "city",
    ]

    name = fields.Char(string="Établissement", required=True, tracking=True)
    contact_name = fields.Char(string="Contact")
    phone = fields.Char(string="Téléphone")
    email = fields.Char(string="Email")
    type_partenaire = fields.Selection(
        CQ_TYPES_PARTENAIRE,
        string="Type de partenaire",
        default="hebergement",
        required=True,
        index=True,
    )
    region = fields.Selection(
        CQ_REGIONS,
        string="Région",
        default="montreal",
        required=True,
        index=True,
    )
    city = fields.Char(string="Ville")
    street = fields.Char(string="Adresse")
    zone = fields.Selection(
        CQ_LAURENTIDES_ZONES,
        string="Zone Laurentides",
        index=True,
    )
    place_id = fields.Char(string="Google Place ID", index=True, copy=False)
    google_rating = fields.Float(string="Note Google", digits=(2, 1))
    google_maps_url = fields.Char(string="Lien Google Maps")
    partner_lat = fields.Float(string="Latitude", digits=(10, 7))
    partner_lng = fields.Float(string="Longitude", digits=(10, 7))
    source = fields.Selection(
        [
            ("google", "Google Places"),
            ("pages_jaunes", "Pages Jaunes Canada"),
            ("mixte", "Google + Pages Jaunes"),
            ("manuel", "Manuel"),
        ],
        string="Source",
        default="manuel",
        index=True,
    )
    phone_source = fields.Selection(
        [
            ("google", "Google"),
            ("pages_jaunes", "Pages Jaunes Canada"),
            ("manquant", "Manquant"),
            ("manuel", "Manuel"),
        ],
        string="Source téléphone",
    )
    stage = fields.Selection(
        CQ_PIPELINE_STAGES,
        string="Étape",
        default="nouveau",
        required=True,
        tracking=True,
        index=True,
        group_expand="_group_expand_stage",
    )
    notes = fields.Text(string="Notes")
    active = fields.Boolean(default=True)
    property_id = fields.Many2one(
        "coins.quebec.property",
        string="Bien lié",
        ondelete="set null",
    )
    user_id = fields.Many2one(
        "res.users",
        string="Commercial (suivi)",
        default=lambda self: self._cq_martin_user() or self.env.user,
        tracking=True,
        help="Utilisateur humain pour activités / mail. "
        "L'assignation métier est coins_commercial_assigne ou coins_agent_ia_id. "
        "Défaut Martin ; les réunions vont toujours sur son calendrier.",
    )
    cq_rdv_event_id = fields.Many2one(
        "calendar.event",
        string="Réunion planifiée",
        copy=False,
        ondelete="set null",
    )
    cq_meeting_display_label = fields.Char(
        compute="_compute_cq_meeting_display",
    )
    cq_meeting_display_date = fields.Char(
        compute="_compute_cq_meeting_display",
    )
    cq_rdv_booked_display = fields.Char(
        compute="_compute_cq_meeting_display",
        string="RDV pris le",
        help="Date et heure où le rendez-vous a été booké, en heure du Canada.",
    )
    fiche_lien = fields.Char(
        string="Lien fiche partenaire",
        help="URL portail Mon Coin : https://intellixcrm.com/mon-coin/login",
    )
    is_demo = fields.Boolean(
        string="Fiche démo Mon Coin",
        default=False,
        index=True,
        copy=False,
        help="Isolée : les écritures démo ne touchent jamais une fiche réelle.",
    )

    _sql_constraints = [
        (
            "cq_partenariat_place_id_uniq",
            "unique(place_id)",
            "Ce Place ID Google est déjà dans le pipeline Coins Québec.",
        ),
    ]

    @api.model
    def _cq_martin_user(self):
        Users = self.env["res.users"].sudo()
        martin = Users.search([("login", "=", CQ_MARTIN_LOGIN)], limit=1)
        if martin:
            return martin
        fallback = Users.browse(10).exists()
        if (
            fallback
            and "martin" in (fallback.name or "").lower()
            and "michel" not in (fallback.name or "").lower()
        ):
            return fallback
        return Users.browse()

    @api.model
    def _cq_ensure_martin_calendar_color(self):
        """Pastille calendrier Martin = mauve (color 10). Ne touche pas Michel."""
        martin = self._cq_martin_user()
        if not martin or not martin.partner_id:
            return martin
        partner = martin.partner_id
        if partner.color != CQ_MARTIN_CALENDAR_COLOR:
            partner.sudo().write({"color": CQ_MARTIN_CALENDAR_COLOR})
        return martin

    @api.model
    def _register_hook(self):
        super()._register_hook()
        try:
            self._cq_ensure_martin_calendar_color()
        except Exception:
            pass
        try:
            self._cq_sync_upcoming_rdv_stages()
        except Exception:
            pass

    @api.model
    def _group_expand_stage(self, stages, domain, order=None):
        return cq_group_expand_stage(self, stages, domain, order)

    CQ_STAGES_MOVE_TO_RDV = ("nouveau", "contacte", "suivi") + CQ_PIPELINE_OBSOLETE

    _CQ_RDV_SKIP_MARKERS = (
        "[call]",
        "[to-do]",
        "[relance",
        "rappel",
        "import —",
        "import -",
    )

    @api.model
    def _cq_is_real_rdv_event(self, event):
        """Vrai rendez-vous (wizard / calendrier / IntelliX), pas rappel ni Call."""
        if not event or not event.exists() or not event.active:
            return False
        name = (event.name or "").strip().lower()
        if not name:
            return False
        if any(marker in name for marker in self._CQ_RDV_SKIP_MARKERS):
            return False
        if (
            name.startswith("[meeting]")
            and "rdv " not in name
            and "coins québec" not in name
        ):
            return False
        if name.startswith("rdv ") or "rdv " in name:
            return True
        description = (event.description or "").lower()
        if "coins québec" in name or "réunion partenariat" in description:
            return True
        if event.res_model == "coins.quebec.partenariat" and event.res_id:
            return True
        return False

    @api.model
    def _cq_find_for_booking(self, email=None, phone=None):
        """Retrouve une fiche CQ par email, sinon téléphone (10 derniers chiffres)."""
        Part = self.sudo()
        email = (email or "").strip()
        if email:
            rec = Part.search(
                [("email", "=ilike", email), ("active", "=", True)],
                limit=1,
            )
            if rec:
                return rec
        digits = "".join(ch for ch in (phone or "") if ch.isdigit())
        if digits and len(digits) >= 10:
            tail = digits[-10:]
            for rec in Part.search(
                [("phone", "!=", False), ("active", "=", True)]
            ):
                rec_digits = "".join(ch for ch in (rec.phone or "") if ch.isdigit())
                if rec_digits and rec_digits[-10:] == tail:
                    return rec
        return Part.browse()

    def _cq_mark_en_rdv_from_event(self, event=None):
        """Colonne En RDV + pointeur RDV. N'ouvre pas Entente / Gagné / Perdu."""
        now = fields.Datetime.now()
        for rec in self:
            if rec.stage in CQ_STAGES_CLOSED or rec.stage == "entente":
                continue
            vals = {}
            if event and event.exists():
                current = rec.cq_rdv_event_id
                replace = False
                if not current:
                    replace = True
                elif event.start and event.start >= now:
                    if (
                        not current.start
                        or current.start < now
                        or current.id == event.id
                    ):
                        replace = True
                if replace and current.id != event.id:
                    vals["cq_rdv_event_id"] = event.id
            if rec.stage in self.CQ_STAGES_MOVE_TO_RDV:
                vals["stage"] = "en_rdv"
            if vals:
                rec.with_context(cq_skip_rdv_stage=True).write(vals)

    @api.model
    def _cq_sync_upcoming_rdv_stages(self):
        """En RDV = vrai RDV à venir. 716 Légende (mail, pas de RDV) → Suivis."""
        Part = self.sudo().with_context(active_test=False)
        now = fields.Datetime.now()
        upcoming_ids = set()
        with_event = Part.search(
            [
                ("cq_rdv_event_id", "!=", False),
                ("cq_rdv_event_id.start", ">=", now),
                ("cq_rdv_event_id.active", "=", True),
                ("stage", "not in", list(CQ_STAGES_CLOSED) + ["entente"]),
            ]
        )
        for rec in with_event:
            if self._cq_is_real_rdv_event(rec.cq_rdv_event_id):
                upcoming_ids.add(rec.id)
        events = self.env["calendar.event"].sudo().search(
            [
                ("start", ">=", now),
                ("active", "=", True),
                ("res_model", "=", "coins.quebec.partenariat"),
                ("res_id", ">", 0),
            ]
        )
        for event in events:
            if not self._cq_is_real_rdv_event(event):
                continue
            rec = Part.browse(event.res_id)
            if rec.exists() and rec.stage not in CQ_STAGES_CLOSED + ("entente",):
                upcoming_ids.add(rec.id)
                if rec.cq_rdv_event_id != event and event.start and event.start >= now:
                    rec.with_context(cq_skip_rdv_stage=True).write(
                        {"cq_rdv_event_id": event.id}
                    )
        if upcoming_ids:
            to_rdv = Part.browse(list(upcoming_ids)).filtered(
                lambda r: r.stage != "en_rdv"
                and r.stage in self.CQ_STAGES_MOVE_TO_RDV
            )
            if to_rdv:
                to_rdv.write({"stage": "en_rdv"})
        # Restaurant Légende : suivi mail, aucun RDV → Suivis (pas En RDV).
        legende = Part.browse(716).exists()
        if (
            legende
            and "légende" in (legende.name or "").lower()
            and legende.id not in upcoming_ids
            and legende.stage not in CQ_STAGES_CLOSED + ("suivi", "entente", "en_rdv")
        ):
            legende.write({"stage": "suivi"})

    @api.depends(
        "cq_rdv_event_id",
        "cq_rdv_event_id.start",
        "cq_rdv_event_id.create_date",
        "cq_rdv_event_id.active",
    )
    def _compute_cq_meeting_display(self):
        for rec in self:
            event = rec.cq_rdv_event_id
            if event and event.active and event.start:
                rec.cq_meeting_display_label = _("Prochaine réunion")
                rec.cq_meeting_display_date = cq_format_canada_short(event.start)
                booked = cq_format_canada_short(event.create_date)
                rec.cq_rdv_booked_display = (
                    _("Pris le %s") % booked if booked else False
                )
            else:
                rec.cq_meeting_display_label = _("Aucune réunion")
                rec.cq_meeting_display_date = False
                rec.cq_rdv_booked_display = False

    @api.model_create_multi
    def create(self, vals_list):
        martin = self._cq_martin_user()
        martin_id = martin.id if martin else self.env.uid
        for vals in vals_list:
            if not vals.get("user_id"):
                vals["user_id"] = martin_id
            if not vals.get("coins_agent_ia_id") and not vals.get(
                "coins_commercial_assigne"
            ):
                if vals.get("assignee_kind") != "ia":
                    vals["coins_commercial_assigne"] = vals.get("user_id") or martin_id
        return super().create(vals_list)

    def unlink(self):
        from .mon_coin_demo import _name_is_protected_real

        blocked = self.filtered(lambda r: _name_is_protected_real(r.name))
        if blocked:
            raise UserError(
                _(
                    "Ces fiches sont protégées et ne peuvent pas être "
                    "supprimées : %s. Archivez-les si besoin."
                )
                % ", ".join(blocked.mapped("name"))
            )
        return super().unlink()

    def write(self, vals):
        if self.env.context.get("mon_coin_demo"):
            real = self.filtered(lambda r: not r.is_demo)
            if real:
                raise UserError(
                    _("Mode démo : écriture interdite sur une fiche réelle (%s).")
                    % ", ".join(real.mapped("name"))
                )
        if vals.get("is_demo"):
            protected = self.filtered(
                lambda r: (r.name or "").strip().lower()
                in (
                    "atelier du pin",
                    "gîte test coins québec",
                    "gite test coins quebec",
                )
                or "atelier du pin" in (r.name or "").strip().lower()
            )
            if protected:
                raise UserError(
                    _("Impossible de marquer démo une fiche réelle : %s")
                    % ", ".join(protected.mapped("name"))
                )
        res = super().write(vals)
        if vals.get("coins_commercial_assigne") and not vals.get("coins_agent_ia_id"):
            for rec in self.filtered("coins_commercial_assigne"):
                if rec.user_id != rec.coins_commercial_assigne:
                    super(CoinsQuebecPartenariat, rec).write(
                        {"user_id": rec.coins_commercial_assigne.id}
                    )
        if (
            vals.get("cq_rdv_event_id")
            and "stage" not in vals
            and not self.env.context.get("cq_skip_rdv_stage")
        ):
            to_move = self.filtered(
                lambda r: r.stage in self.CQ_STAGES_MOVE_TO_RDV
            )
            if to_move:
                super(CoinsQuebecPartenariat, to_move).write({"stage": "en_rdv"})
        return res

    def _find_scrape_duplicate(self, name, phone, place_id):
        """Dédup name + phone + place_id (fiches CQ seulement)."""
        if place_id:
            rec = self.search([("place_id", "=", place_id)], limit=1)
            if rec:
                return rec
        digits = "".join(ch for ch in (phone or "") if ch.isdigit())
        if digits and len(digits) >= 7:
            for rec in self.search([("phone", "!=", False)]):
                rec_digits = "".join(ch for ch in (rec.phone or "") if ch.isdigit())
                if rec_digits and rec_digits[-10:] == digits[-10:]:
                    if (rec.name or "").strip().lower() == (name or "").strip().lower():
                        return rec
        if name:
            rec = self.search(
                [("name", "=ilike", name.strip()), ("region", "=", "laurentides")],
                limit=1,
            )
            if rec:
                return rec
        return self.browse()

    # HTML prospection (Karine Barmaki, 29 août 2026) — PAS le suivi rencontre.
    # Envoi individuel via compositeur Odoo — pas de blast Listmonk.
    CQ_PROSPECT_HTML = {
        "resto": ("email_restaurant.html", "restaurant"),
        "hebergement": ("email_hotel.html", "hotel"),
        "spa": ("email_spa.html", "spa"),
        "activite": ("email_divertissement.html", "divertissement"),
        "evenement": ("email_hotel.html", "hotel"),
        "traiteur": ("email_restaurant.html", "restaurant"),
        "fleuriste": ("email_divertissement.html", "divertissement"),
        "dj": ("email_divertissement.html", "divertissement"),
        "mobilier": ("email_divertissement.html", "divertissement"),
        "autre": ("email_hotel.html", "hotel"),
    }
    # Canada live : 72 resto, 74 hôtel, 75 spa, 76 activité.
    CQ_PROSPECT_TEMPLATE = {
        "resto": ("coins_quebec.mail_template_cq_prospection", 72),
        "hebergement": ("coins_quebec.mail_template_cq_prospection_hotel", 74),
        "spa": ("coins_quebec.mail_template_cq_prospection_spa", 75),
        "activite": ("coins_quebec.mail_template_cq_prospection_divertissement", 76),
    }

    def _cq_followup_mail_ref(self):
        """Modèle post-rencontre selon type_partenaire.

        Mapping (clés existantes, pas de migration) :
        - hebergement → hôtel (15 %)
        - spa → spa (15 %)
        - resto → restaurant (10 %)
        - activite → divertissement (10 %)
        - evenement / autre / vide → hôtel (défaut documenté)
        """
        self.ensure_one()
        mapping = {
            "hebergement": (
                "coins_quebec.mail_template_cq_suite_rencontre",
                "Suite à notre rencontre",
            ),
            "spa": (
                "coins_quebec.mail_template_cq_suite_rencontre_spa",
                "Suivi rencontre (spa",
            ),
            "resto": (
                "coins_quebec.mail_template_cq_suite_rencontre_restaurant",
                "Suivi rencontre (restaurant)",
            ),
            "activite": (
                "coins_quebec.mail_template_cq_suite_rencontre_divertissement",
                "Suivi rencontre (divertissement)",
            ),
        }
        return mapping.get(
            self.type_partenaire or "hebergement",
            (
                "coins_quebec.mail_template_cq_suite_rencontre",
                "Suite à notre rencontre",
            ),
        )

    def _cq_prospect_html_path(self):
        self.ensure_one()
        filename, _utm = self.CQ_PROSPECT_HTML.get(
            self.type_partenaire or "hebergement",
            self.CQ_PROSPECT_HTML["hebergement"],
        )
        addon = os.path.join(
            get_module_path("coins_quebec"), "data", "emails", filename
        )
        if os.path.isfile(addon):
            return addon
        raise UserError(
            _("Fichier HTML de prospection introuvable : %s") % filename
        )

    def _cq_followup_video_urls(self):
        slug = {
            "resto": "restaurant",
            "hebergement": "hotel",
            "spa": "spa",
            "activite": "divertissement",
        }.get(self.type_partenaire or "hebergement", "hotel")
        base = "https://coinsquebec.com/assets/video/prospection-%s" % slug
        return "%s.html" % base, "%s-email.jpg" % base

    def _cq_fiche_cta_url(self):
        return (self.fiche_lien or "").strip() or "https://coinsquebec.com/commercants"

    def _cq_followup_html_path(self):
        addon = os.path.join(
            get_module_path("coins_quebec"),
            "data",
            "emails",
            "email_suite_rencontre.html",
        )
        if os.path.isfile(addon):
            return addon
        raise UserError(_("Fichier HTML de suivi rencontre introuvable."))

    def _cq_render_followup_html(self):
        """Couleurs CQ + vignette vidéo + CTA fiche (Karine Barmaki)."""
        self.ensure_one()
        html = open(self._cq_followup_html_path(), encoding="utf-8").read()
        contact = ((self.contact_name or "").strip().split() or [""])[0] or ""
        etab = (self.name or "").strip() or "votre établissement"
        ville = (self.city or "").strip() or "votre ville"
        video_href, video_img = self._cq_followup_video_urls()
        visib = (
            10
            if (self.type_partenaire or "")
            in ("resto", "activite", "traiteur", "fleuriste", "dj", "mobilier")
            else 15
        )
        digital = (
            "Gestion réservations, personnel / présence, pricing dynamique — "
            "<strong>10 % des réservations ou 199 $ CAD/mois</strong>."
        )
        sender = (self.env.user.name or "").strip() or "Karine Barmaki"
        html = html.replace("{{CONTACT}}", str(escape(contact)))
        html = html.replace("{{ETABLISSEMENT}}", str(escape(etab)))
        html = html.replace("{{VILLE}}", str(escape(ville)))
        html = html.replace("{{VIDEO_HREF}}", str(escape(video_href)))
        html = html.replace("{{VIDEO_IMG}}", str(escape(video_img)))
        html = html.replace("{{FICHE_URL}}", str(escape(self._cq_fiche_cta_url())))
        html = html.replace("{{VISIB_PCT}}", str(visib))
        html = html.replace("{{DIGITAL_LINE}}", digital)
        html = html.replace("{{SENDER}}", str(escape(sender)))
        return html

    def _cq_render_prospect_html(self):
        """Remplit CONTACT / ETABLISSEMENT / VILLE. Laisse {{VIDEO_URL_*}} tel quel."""
        self.ensure_one()
        html = open(self._cq_prospect_html_path(), encoding="utf-8").read()
        contact = ((self.contact_name or "").strip().split() or [""])[0]
        etab = (self.name or "").strip() or "votre établissement"
        ville = (self.city or "").strip() or "votre ville"
        html = html.replace("{{CONTACT}}", str(escape(contact)))
        html = html.replace("{{ETABLISSEMENT}}", str(escape(etab)))
        html = html.replace("{{VILLE}}", str(escape(ville)))
        _fname, utm_content = self.CQ_PROSPECT_HTML.get(
            self.type_partenaire or "hebergement",
            self.CQ_PROSPECT_HTML["hebergement"],
        )
        base_martin = "https://intellixcrm.com/intellix/rdv/martin"
        if "utm_campaign=coins_quebec" not in html:
            martin = (
                base_martin
                + "?utm_source=email&utm_medium=prospection"
                + "&utm_campaign=coins_quebec&utm_content=%s" % utm_content
            )
            html = html.replace(base_martin, martin)
        return html

    def _cq_prospect_mail_template(self):
        """Modèle prospection selon type_partenaire — pas de choix manuel."""
        self.ensure_one()
        xmlid, fallback_id = self.CQ_PROSPECT_TEMPLATE.get(
            self.type_partenaire or "hebergement",
            self.CQ_PROSPECT_TEMPLATE["hebergement"],
        )
        template = self.env.ref(xmlid, raise_if_not_found=False)
        if template:
            return template
        template = self.env["mail.template"].sudo().browse(fallback_id)
        if template.exists() and template.model == "coins.quebec.partenariat":
            return template
        template = self.env["mail.template"].sudo().search(
            [
                ("model", "=", "coins.quebec.partenariat"),
                ("name", "ilike", "Prospection"),
            ],
            limit=1,
        )
        if not template:
            raise UserError(
                _("Modèle introuvable : Prospection Coins Québec.")
            )
        return template

    def action_send_cq_followup_email(self):
        """Ouvre le compositeur (brouillon) — n'envoie pas automatiquement.

        Corps = data/emails/email_suite_rencontre.html : couleurs CQ,
        vignette vidéo, CTA OUVRIR MA FICHE.
        """
        self.ensure_one()
        xmlid, name_ilike = self._cq_followup_mail_ref()
        template = self.env.ref(xmlid, raise_if_not_found=False)
        if not template:
            template = self.env["mail.template"].sudo().search(
                [
                    ("model", "=", "coins.quebec.partenariat"),
                    ("name", "ilike", name_ilike),
                ],
                limit=1,
            )
        if not template:
            raise UserError(
                _("Modèle introuvable : Suite à notre rencontre (Coins Québec).")
            )
        ctx = {
            "default_model": "coins.quebec.partenariat",
            "default_res_ids": self.ids,
            "default_template_id": template.id,
            "default_use_template": True,
            "default_composition_mode": "comment",
            "mail_post_autofollow": True,
            "active_model": "coins.quebec.partenariat",
            "active_ids": self.ids,
            "active_id": self.id,
        }
        try:
            rendered = self._cq_render_followup_html()
        except (OSError, UserError):
            rendered = ""
        if rendered:
            ctx.update(
                {
                    "default_subject": (
                        "Suite à notre rencontre — %s sur Coins Québec"
                        % ((self.name or "").strip() or "votre établissement")
                    ),
                    "default_body": Markup(rendered),
                }
            )
        return {
            "type": "ir.actions.act_window",
            "name": _("Envoyer suivi rencontre"),
            "res_model": "mail.compose.message",
            "view_mode": "form",
            "target": "new",
            "context": ctx,
        }

    def action_send_cq_prospect_email(self):
        """Ouvre le compositeur (brouillon) — n'envoie pas automatiquement.

        Modèle 72/74/75/76 selon type_partenaire. Corps = data/emails/.
        """
        self.ensure_one()
        if not (self.email or "").strip():
            raise UserError(
                _("Indiquez l'email du contact avant d'ouvrir le courriel.")
            )
        template = self._cq_prospect_mail_template()
        ctx = {
            "default_model": "coins.quebec.partenariat",
            "default_res_ids": self.ids,
            "default_template_id": template.id,
            "default_use_template": True,
            "default_composition_mode": "comment",
            "mail_post_autofollow": True,
        }
        body = template.body_html or ""
        stub = (
            "Voir data/emails" in body
            or "BROUILLON" in body
            or len(body) < 200
        )
        if stub:
            try:
                rendered = self._cq_render_prospect_html()
            except (OSError, UserError):
                rendered = ""
            if rendered:
                subject = (
                    "Coins Québec — visibilité vidéo pour %s"
                    % ((self.name or "").strip() or "votre établissement")
                )
                ctx.update({
                    "default_subject": subject,
                    "default_body": Markup(rendered),
                })
        return {
            "type": "ir.actions.act_window",
            "name": _("Envoyer courriel prospection"),
            "res_model": "mail.compose.message",
            "view_mode": "form",
            "target": "new",
            "context": ctx,
        }

    def action_cq_phone_call(self):
        self.ensure_one()
        return cq_click_to_call_action(self.env, self.phone)

    def action_cq_book_rdv(self):
        """Wizard créneaux Martin — ne touche pas hiba.book.martin.wizard."""
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": _("Planifier une réunion (Martin)"),
            "res_model": "coins.quebec.book.rdv.wizard",
            "view_mode": "form",
            "target": "new",
            "context": {"default_partenariat_id": self.id},
        }

    def action_cq_meeting_stat(self):
        """Même geste que crm.lead Réno : Aucune réunion → booker, sinon ouvrir."""
        self.ensure_one()
        event = self.cq_rdv_event_id
        if event and event.active:
            return {
                "type": "ir.actions.act_window",
                "name": _("Réunion"),
                "res_model": "calendar.event",
                "view_mode": "form",
                "res_id": event.id,
                "target": "current",
            }
        return self.action_cq_book_rdv()
