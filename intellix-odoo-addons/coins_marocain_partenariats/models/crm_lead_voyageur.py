# -*- coding: utf-8 -*-
import logging
import re
from datetime import date, timedelta

from odoo import api, fields, models, _
from odoo.exceptions import UserError
from odoo.osv import expression

_logger = logging.getLogger(__name__)

COL_ID = 0
COL_CREATED = 1
COL_CAMPAIGN = 7
COL_FORM = 9
COL_PLATFORM = 11
COL_EVENT_TYPE = 12
COL_NB_PERSONNES = 13
COL_DATE_ENV = 14
COL_EMAIL = 15
COL_NAME = 16
COL_PHONE = 17

EVENT_TYPE_MAP = {
    "fiançailles-mariage": "mariage",
    "fiancailles-mariage": "mariage",
    "mariage": "mariage",
    "wedding": "mariage",
    "moment_festif_entre_amis/famille": "groupe_amis",
    "moment_festif_entre_amis_famille": "groupe_amis",
    "moment festif entre amis/famille": "groupe_amis",
    "amis": "groupe_amis",
    "famille": "reunion_famille",
    "reunion_famille": "reunion_famille",
    "anniversaire": "anniversaire",
    "birthday": "anniversaire",
}

TAILLE_MAP = {
    "1-10": "1_10",
    "1_10": "1_10",
    "10-20": "10_20",
    "10_20": "10_20",
    "20-30": "20_30",
    "20_30": "20_30",
    "30+": "30_plus",
    "30_plus": "30_plus",
}


class CrmLeadVoyageur(models.Model):
    _inherit = "crm.lead"

    coins_is_voyageur_lead = fields.Boolean(
        string="Lead pipeline voyageurs",
        compute="_compute_coins_pipeline_flags",
        store=True,
    )
    coins_service_demande = fields.Char(string="Service demandé")
    coins_voyageur_budget = fields.Char(string="Budget")
    coins_canal_origine = fields.Selection(
        [
            ("meta", "Meta Ads"),
            ("whatsapp", "WhatsApp"),
            ("site", "Site coinsmarocain.com"),
            ("yasmine", "Yasmine / Agent IA"),
            ("referral", "Parrainage"),
            ("autre", "Autre"),
        ],
        string="Canal d'origine",
        index=True,
    )
    coins_urgence = fields.Boolean(string="Urgence", tracking=True)
    coins_conversation_id = fields.Many2one(
        "coins.yasmine.conversation",
        string="Fil de conversation",
        ondelete="set null",
        copy=False,
    )
    coins_xsell_bienetre = fields.Boolean(string="Bien-être")
    coins_xsell_hebergement = fields.Boolean(string="Hébergement")
    coins_xsell_evenements = fields.Boolean(string="Événements")
    coins_xsell_restaurant = fields.Boolean(string="Restaurant")
    coins_xsell_excursions = fields.Boolean(string="Excursions")
    coins_xsell_transport = fields.Boolean(string="Transport")
    coins_reservation_ids = fields.One2many(
        "coins.reservation",
        "lead_id",
        string="Réservations liées",
    )
    coins_reservation_count = fields.Integer(
        compute="_compute_coins_reservation_count"
    )
    coins_has_coordonnees = fields.Boolean(
        compute="_compute_coins_has_coordonnees",
        store=True,
    )
    coins_kanban_title = fields.Char(compute="_compute_coins_kanban_card")
    coins_kanban_subtitle = fields.Char(compute="_compute_coins_kanban_card")
    coins_kanban_tone = fields.Selection(
        [("hot", "Chaud"), ("won", "Gagné"), ("idle", "Inactif")],
        compute="_compute_coins_kanban_card",
    )
    coins_fiche_initials = fields.Char(compute="_compute_coins_kanban_card")
    coins_kanban_categorie = fields.Char(compute="_compute_coins_kanban_card")
    coins_kanban_commission = fields.Char(compute="_compute_coins_kanban_card")
    coins_kanban_source = fields.Char(compute="_compute_coins_kanban_card")
    coins_kanban_source_kind = fields.Selection(
        [("scrape", "Scraping"), ("manual", "Saisie manuelle")],
        compute="_compute_coins_kanban_card",
    )
    coins_kanban_commercial = fields.Char(compute="_compute_coins_kanban_card")
    coins_voy_taille_groupe = fields.Selection(
        [
            ("1_10", "1-10"),
            ("10_20", "10-20"),
            ("20_30", "20-30"),
            ("30_plus", "30+"),
        ],
        string="Taille du groupe",
        index=True,
    )
    coins_voy_date_event_raw = fields.Char(string="Date événement (texte)")
    coins_voy_coordonnees_incompletes = fields.Boolean(
        string="Coordonnées incomplètes",
        compute="_compute_coins_voy_coordonnees_incompletes",
        store=True,
        index=True,
        help="Email et/ou téléphone manquant — fiche importée quand même.",
    )
    coins_voy_relance_date = fields.Date(
        string="Prochaine relance voyageur",
        index=True,
        tracking=True,
    )
    coins_voy_relance_label = fields.Char(
        compute="_compute_coins_voy_relance_label",
    )
    coins_voy_relance_today = fields.Boolean(
        string="À relancer aujourd'hui",
        compute="_compute_coins_voy_relance_flags",
        search="_search_coins_voy_relance_today",
    )
    coins_voy_relance_week = fields.Boolean(
        string="À relancer cette semaine",
        compute="_compute_coins_voy_relance_flags",
        search="_search_coins_voy_relance_week",
    )
    # Brouillon wizard « Planifier l'événement » — notes internes, pas de conversion.
    coins_evt_style = fields.Selection(
        [
            ("moderne", "Moderne"),
            ("traditionnel", "Traditionnel"),
            ("nature_rural", "Nature-Rural"),
            ("desert", "Désert"),
        ],
        string="Style lieu (brouillon)",
        copy=False,
    )
    coins_evt_note_lieu = fields.Text(string="Lieu pressenti", copy=False)
    coins_evt_note_menu = fields.Text(string="Menu (note)", copy=False)
    coins_evt_note_divert = fields.Text(string="Divertissement (note)", copy=False)
    coins_evt_note_deco = fields.Text(string="Décoration (note)", copy=False)
    coins_evt_note_heberg = fields.Text(string="Hébergement (note)", copy=False)
    coins_evt_resume = fields.Text(
        string="Résumé événement (brouillon)",
        copy=False,
        help="Assemblé par le wizard. Pas envoyé au voyageur.",
    )

    def _coins_selection_label(self, field_name, value):
        if not value:
            return ""
        field = self._fields.get(field_name)
        if not field:
            return value
        return dict(field._description_selection(self.env)).get(value) or ""

    def _coins_clean_kanban_title(self, raw):
        title = (raw or "").strip()
        title = title.lstrip("🔥").strip()
        if title.upper().startswith("HOT"):
            title = title[3:].lstrip(" —–-").strip()
        compact = title.lower().replace("—", "-").replace("–", "-")
        generic = (
            "concierge coins marocain" in compact
            or compact in ("coins marocain", "concierge whatsapp")
            or compact.startswith("concierge whatsapp")
        )
        return title, generic

    def _coins_plain_note(self):
        raw = " ".join(
            p
            for p in (
                self.coins_service_demande,
                self.coins_note,
                self.description,
            )
            if p
        )
        text = re.sub(r"<[^>]+>", " ", raw or "")
        return re.sub(r"\s+", " ", text).strip()

    def _coins_note_excerpt(self, limit=72):
        text = self._coins_plain_note()
        if not text:
            return ""
        match = re.search(
            r"user:\s*(.+?)(?:\s+(?:assistant|yasmine)\s*:|$)",
            text,
            flags=re.I,
        )
        if match:
            text = match.group(1).strip()
        text = re.sub(
            r"TRANSFERT À CHAUD.*?HEURE\.?",
            "",
            text,
            flags=re.I,
        )
        text = re.sub(r"Conversation\s*:\s*", "", text, flags=re.I).strip()
        if len(text) > limit:
            cut = text[:limit].rsplit(" ", 1)[0]
            text = (cut or text[:limit]).rstrip(",;:") + "…"
        return text

    @api.depends(
        "name",
        "contact_name",
        "partner_name",
        "coins_fiche_type",
        "coins_is_voyageur_lead",
        "coins_service_demande",
        "coins_urgence",
        "coins_etablissement",
        "coins_ville",
        "coins_ville_autre",
        "coins_quartier",
        "coins_categorie_etab",
        "coins_type_partenaire",
        "coins_scrape_source",
        "coins_commission_pct",
        "coins_commercial_assigne",
        "coins_agent_ia_id",
        "coins_assignee_display",
        "create_uid",
        "coins_has_coordonnees",
        "coins_note",
        "description",
        "stage_id",
        "stage_id.name",
        "stage_id.is_won",
        "stage_id.fold",
    )
    def _compute_coins_kanban_card(self):
        hot = self._coins_hot_stage()
        for lead in self:
            is_voy = lead.coins_is_voyageur_lead or lead.coins_fiche_type == "voyageur"
            stage_name = lead.stage_id.name or ""
            is_hot = bool(
                is_voy
                and (
                    lead.coins_urgence
                    or (hot and lead.stage_id.id == hot.id)
                    or stage_name == "Transfert à chaud"
                )
            )
            cat_badge = ""
            comm_badge = ""
            source_badge = ""
            source_kind = False
            commercial_badge = ""
            if is_voy:
                raw_title = (
                    lead.contact_name or lead.partner_name or lead.name or ""
                ).strip()
                title, generic = lead._coins_clean_kanban_title(raw_title)
                if generic or not title:
                    title = (
                        (lead.contact_name or "").strip()
                        or (lead.coins_service_demande or "").strip()
                        or "Demande voyageur"
                    )
                    title, _ = lead._coins_clean_kanban_title(title)
                subtitle = (lead.coins_service_demande or "").strip()
                if not subtitle:
                    subtitle = lead._coins_note_excerpt()
                if not lead.coins_has_coordonnees:
                    subtitle = (
                        "Sans téléphone — %s" % subtitle
                        if subtitle
                        else "Sans téléphone — note non suivie"
                    )
                elif is_hot and not subtitle:
                    subtitle = "Rappel : dans l'heure"
                elif generic and subtitle.lower() == title.lower():
                    subtitle = "WhatsApp / concierge"
            else:
                title = (
                    lead.coins_etablissement
                    or lead.partner_name
                    or lead.name
                    or ""
                ).strip()
                cat_badge = lead._coins_kanban_category_label()
                comm_badge = lead._coins_kanban_commission_label()
                source_badge, source_kind = lead._coins_kanban_source_label()
                commercial_badge = (lead.coins_assignee_display or "").strip()
                subtitle = " · ".join(
                    p for p in (cat_badge, comm_badge, source_badge) if p
                )
            if is_hot:
                tone = "hot"
            elif lead.stage_id.is_won:
                tone = "won"
            elif lead.stage_id.fold:
                tone = "idle"
            else:
                tone = False
            lead.coins_kanban_title = title
            lead.coins_kanban_subtitle = subtitle
            lead.coins_kanban_tone = tone
            lead.coins_kanban_categorie = cat_badge
            lead.coins_kanban_commission = comm_badge
            lead.coins_kanban_source = source_badge
            lead.coins_kanban_source_kind = source_kind
            lead.coins_kanban_commercial = commercial_badge
            bits = [p[0] for p in title.replace("—", " ").split() if p[:1].isalpha()]
            lead.coins_fiche_initials = ("".join(bits)[:2] or "?").upper()

    def _coins_kanban_category_label(self):
        """Hébergement / Resto / Spa — combo si les deux champs divergent."""
        self.ensure_one()
        type_short = {
            "hebergement": "Hébergement",
            "restauration": "Resto",
            "spa": "Spa",
            "activite": "Activité",
            "wedding_planner": "Wedding planner",
            "agence_voyage": "Agence de voyage",
            "organisateur_congres": "Congrès",
            "influenceur": "Influenceur",
            "autre": "Autre",
        }
        cat_short = {
            "hebergement": "Hébergement",
            "bien_etre": "Spa",
            "restauration": "Resto",
            "decouverte": "Découverte",
            "privatisation": "Privatisation",
            "evenements": "Événements",
        }
        labels = []
        for value in (
            type_short.get(self.coins_type_partenaire),
            cat_short.get(self.coins_categorie_etab),
        ):
            if value and value not in labels:
                labels.append(value)
        return " / ".join(labels) or "Catégorie à préciser"

    def _coins_kanban_commission_label(self):
        self.ensure_one()
        pct = self.coins_commission_pct or 0.0
        if not pct:
            return "Comm. à préciser"
        if pct != int(pct):
            return "%g %%" % pct
        return "%d %%" % int(pct)

    def _coins_kanban_source_label(self):
        """Origine de la fiche — distincte du commercial assigné."""
        self.ensure_one()
        if self.coins_scrape_source in ("google_places", "pages_jaunes"):
            return "Scraping", "scrape"
        creator = (self.create_uid.name or "").strip()
        first = creator.split()[0] if creator else ""
        if first and first.lower() not in ("odoobot", "system", "__system__"):
            return first, "manual"
        return "Saisie manuelle", "manual"

    def _coins_phone_value(self):
        self.ensure_one()
        partner = self.partner_id
        return (
            (self.coins_whatsapp or "").strip()
            or (self.phone or "").strip()
            or (partner.phone or "").strip()
        )

    @api.depends("coins_whatsapp", "phone", "partner_id.phone")
    def _compute_coins_has_coordonnees(self):
        for lead in self:
            lead.coins_has_coordonnees = bool(lead._coins_phone_value())

    @api.depends(
        "email_from",
        "phone",
        "coins_whatsapp",
        "partner_id.email",
        "partner_id.phone",
    )
    def _compute_coins_voy_coordonnees_incompletes(self):
        for lead in self:
            email = (
                (lead.email_from or "").strip()
                or (lead.partner_id.email or "").strip()
            )
            lead.coins_voy_coordonnees_incompletes = not bool(
                email and lead._coins_phone_value()
            )

    @api.depends("coins_voy_relance_date")
    def _compute_coins_voy_relance_label(self):
        for lead in self:
            if lead.coins_voy_relance_date:
                lead.coins_voy_relance_label = _("Prochaine relance : %s") % (
                    lead.coins_voy_relance_date.strftime("%d/%m")
                )
            else:
                lead.coins_voy_relance_label = ""

    @api.depends("coins_voy_relance_date", "stage_id", "stage_id.is_won", "stage_id.fold")
    def _compute_coins_voy_relance_flags(self):
        today = fields.Date.context_today(self)
        start = today - timedelta(days=today.weekday())
        end = start + timedelta(days=6)
        for lead in self:
            due = lead.coins_voy_relance_date
            closed = bool(lead.stage_id.is_won or lead.stage_id.fold)
            lead.coins_voy_relance_today = bool(due and not closed and due <= today)
            lead.coins_voy_relance_week = bool(
                due and not closed and start <= due <= end
            )

    def _search_coins_voy_relance_today(self, operator, value):
        today = fields.Date.context_today(self)
        wanted = (operator == "=" and value) or (operator == "!=" and not value)
        domain = [
            ("coins_is_voyageur_lead", "=", True),
            ("coins_voy_relance_date", "<=", today),
            ("stage_id.is_won", "=", False),
            ("stage_id.fold", "=", False),
        ]
        return domain if wanted else ["!"] + expression.AND([domain])

    def _search_coins_voy_relance_week(self, operator, value):
        today = fields.Date.context_today(self)
        start = today - timedelta(days=today.weekday())
        end = start + timedelta(days=6)
        wanted = (operator == "=" and value) or (operator == "!=" and not value)
        domain = [
            ("coins_is_voyageur_lead", "=", True),
            ("coins_voy_relance_date", ">=", start),
            ("coins_voy_relance_date", "<=", end),
            ("stage_id.is_won", "=", False),
            ("stage_id.fold", "=", False),
        ]
        return domain if wanted else ["!"] + expression.AND([domain])

    def _coins_voy_business_days_between(self, start, end):
        if hasattr(self, "_reno_business_days_between"):
            return self._reno_business_days_between(start, end)
        if end < start:
            return 0
        days = 0
        cursor = start
        while cursor < end:
            cursor += timedelta(days=1)
            if cursor.weekday() < 5:
                days += 1
        return days

    def _coins_voy_add_business_days(self, start, n):
        cursor = start
        added = 0
        n = max(1, int(n or 1))
        while added < n:
            cursor += timedelta(days=1)
            if cursor.weekday() < 5:
                added += 1
        return cursor

    def _coins_voy_suggest_relance_days(self, event_date=None, today=None):
        today = today or fields.Date.context_today(self)
        event_date = event_date or self.coins_date_souhaitee
        if event_date:
            delta = (event_date - today).days
            if delta <= 14:
                return 1
            if delta <= 35:
                return 2
            if delta <= 60:
                return 3
        return 5

    def _coins_voy_activity_type(self, xmlid, fallback="mail.mail_activity_data_todo"):
        rec = self.env.ref(xmlid, raise_if_not_found=False)
        return rec or self.env.ref(fallback, raise_if_not_found=False)

    def _coins_voy_ensure_relance(self):
        """Activité + date d'échéance sur chaque fiche voyageur (idempotent)."""
        today = fields.Date.context_today(self)
        accuse_type = self._coins_voy_activity_type(
            "coins_marocain_partenariats.mail_activity_voy_envoyer_accuse"
        )
        relance_type = self._coins_voy_activity_type(
            "coins_marocain_partenariats.mail_activity_voy_relance"
        )
        for lead in self:
            if not (
                lead.coins_is_voyageur_lead or lead.coins_fiche_type == "voyageur"
            ):
                continue
            if lead.stage_id.is_won or lead.stage_id.fold:
                continue
            days = lead._coins_voy_suggest_relance_days()
            relance_date = lead.coins_voy_relance_date or lead._coins_voy_add_business_days(
                today, days
            )
            if not lead.coins_voy_relance_date:
                lead.coins_voy_relance_date = relance_date
            user_id = (
                lead.user_id.id
                or lead.coins_commercial_assigne.id
                or self.env.uid
            )
            existing = lead.activity_ids.filtered(
                lambda a: a.activity_type_id in (accuse_type, relance_type)
            )
            if accuse_type and not existing.filtered(
                lambda a: a.activity_type_id == accuse_type
            ):
                lead.activity_schedule(
                    "coins_marocain_partenariats.mail_activity_voy_envoyer_accuse"
                    if self.env.ref(
                        "coins_marocain_partenariats.mail_activity_voy_envoyer_accuse",
                        raise_if_not_found=False,
                    )
                    else "mail.mail_activity_data_todo",
                    date_deadline=today,
                    user_id=user_id,
                    summary=_("Envoyer accusé"),
                    note=_(
                        "Premier contact — accusé + présentation CM événementiel. "
                        "Valider le brouillon avant envoi."
                    ),
                )
            if relance_type and not existing.filtered(
                lambda a: a.activity_type_id == relance_type
            ):
                lead.activity_schedule(
                    "coins_marocain_partenariats.mail_activity_voy_relance"
                    if self.env.ref(
                        "coins_marocain_partenariats.mail_activity_voy_relance",
                        raise_if_not_found=False,
                    )
                    else "mail.mail_activity_data_todo",
                    date_deadline=relance_date,
                    user_id=user_id,
                    summary=_("Relance voyageur"),
                    note=_(
                        "Relance 3–5 jours ouvrables si pas de réponse "
                        "(serrée si date d'événement proche)."
                    ),
                )

    def _coins_voy_template_xmlid(self, kind):
        self.ensure_one()
        event = self.coins_type_evenement or ""
        if event == "mariage":
            tone = "mariage"
        elif event == "anniversaire":
            tone = "anniversaire"
        else:
            tone = "festif"
        return "coins_marocain_partenariats.mail_template_voy_%s_%s" % (kind, tone)

    def action_coins_voy_envoyer_accuse(self):
        self.ensure_one()
        if not (self.email_from or "").strip():
            raise UserError(
                _(
                    "Email manquant — complète la fiche avant d'envoyer l'accusé. "
                    "La fiche reste importée."
                )
            )
        xmlid = self._coins_voy_template_xmlid("accuse")
        template = self.env.ref(xmlid, raise_if_not_found=False)
        if not template:
            raise UserError(_("Modèle introuvable : %s") % xmlid)
        return {
            "type": "ir.actions.act_window",
            "name": _("Envoyer accusé — brouillon à valider"),
            "res_model": "mail.compose.message",
            "view_mode": "form",
            "target": "new",
            "context": {
                "default_model": "crm.lead",
                "default_res_ids": self.ids,
                "default_template_id": template.id,
                "default_use_template": True,
                "default_composition_mode": "comment",
                "default_partner_ids": self.partner_id.ids,
                "mail_post_autofollow": True,
            },
        }

    def action_coins_voy_envoyer_relance(self):
        self.ensure_one()
        if not (self.email_from or "").strip():
            raise UserError(
                _("Email manquant — complète la fiche avant la relance e-mail.")
            )
        xmlid = self._coins_voy_template_xmlid("relance")
        template = self.env.ref(xmlid, raise_if_not_found=False)
        if not template:
            raise UserError(_("Modèle introuvable : %s") % xmlid)
        return {
            "type": "ir.actions.act_window",
            "name": _("Relance — brouillon à valider"),
            "res_model": "mail.compose.message",
            "view_mode": "form",
            "target": "new",
            "context": {
                "default_model": "crm.lead",
                "default_res_ids": self.ids,
                "default_template_id": template.id,
                "default_use_template": True,
                "default_composition_mode": "comment",
                "default_partner_ids": self.partner_id.ids,
                "mail_post_autofollow": True,
            },
        }

    def action_coins_voy_relance_faite(self):
        self.ensure_one()
        today = fields.Date.context_today(self)
        relance_type = self._coins_voy_activity_type(
            "coins_marocain_partenariats.mail_activity_voy_relance"
        )
        accuse_type = self._coins_voy_activity_type(
            "coins_marocain_partenariats.mail_activity_voy_envoyer_accuse"
        )
        done = self.activity_ids.filtered(
            lambda a: a.activity_type_id in (relance_type, accuse_type)
            and a.date_deadline
            and a.date_deadline <= today
        )
        if done:
            done.action_done()
        next_days = max(3, self._coins_voy_suggest_relance_days())
        nxt = self._coins_voy_add_business_days(today, next_days)
        self.coins_voy_relance_date = nxt
        user_id = self.user_id.id or self.env.uid
        self.activity_schedule(
            "coins_marocain_partenariats.mail_activity_voy_relance"
            if relance_type
            and self.env.ref(
                "coins_marocain_partenariats.mail_activity_voy_relance",
                raise_if_not_found=False,
            )
            else "mail.mail_activity_data_todo",
            date_deadline=nxt,
            user_id=user_id,
            summary=_("Relance voyageur"),
            note=_("Prochaine relance après contact."),
        )
        return True

    @api.depends("coins_reservation_ids")
    def _compute_coins_reservation_count(self):
        for lead in self:
            lead.coins_reservation_count = len(lead.coins_reservation_ids)

    def _coins_hot_stage(self):
        return self.env.ref(
            "coins_marocain_partenariats.crm_stage_voy_chaud",
            raise_if_not_found=False,
        )

    def _coins_assert_phone_for_hot(self, vals=None):
        vals = vals or {}
        stage = self.env["crm.stage"]
        if vals.get("stage_id"):
            stage = self.env["crm.stage"].browse(vals["stage_id"])
        hot = self._coins_hot_stage()
        for lead in self:
            target = stage if stage else lead.stage_id
            is_hot = bool((target.name or "") == "Transfert à chaud")
            if not is_hot and not lead.coins_is_voyageur_lead:
                continue
            if not is_hot:
                continue
            phone = vals.get("coins_whatsapp") or vals.get("phone")
            if phone is None:
                phone = lead._coins_phone_value()
            if not (phone or "").strip():
                raise UserError(
                    _(
                        "WhatsApp / téléphone obligatoire avant « Transfert à chaud ». "
                        "L’alerte ne part pas sans coordonnées."
                    )
                )

    def write(self, vals):
        if "stage_id" in vals or vals.get("coins_fiche_type") == "voyageur":
            self._coins_assert_phone_for_hot(vals)
        voy_team = self._coins_voy_team()
        dest_id = False
        if voy_team and "team_id" in vals:
            dest = vals.get("team_id")
            dest_id = dest.id if hasattr(dest, "id") else dest
            try:
                dest_id = int(dest_id or 0)
            except (TypeError, ValueError):
                dest_id = 0
        leaving = vals.get("coins_fiche_type") in ("partenariat", "evenement")
        if voy_team and dest_id and dest_id != voy_team.id and not leaving:
            # Zakaria / Marketing ne doit pas vider le kanban Voyageurs.
            voy = self.filtered(
                lambda l: l.coins_fiche_type == "voyageur" or l.coins_is_voyageur_lead
            )
            if voy and voy == self:
                vals = dict(vals, team_id=voy_team.id)
            elif voy:
                other = self - voy
                res = True
                if other:
                    res = super(CrmLeadVoyageur, other).write(vals)
                voy_vals = dict(vals, team_id=voy_team.id)
                return super(CrmLeadVoyageur, voy).write(voy_vals) and res
        return super().write(vals)

    def action_coins_qualifier(self):
        self.ensure_one()
        stage = self.env.ref(
            "coins_marocain_partenariats.crm_stage_voy_qualifie",
            raise_if_not_found=False,
        )
        if stage:
            self.stage_id = stage.id
        return True

    def action_coins_marquer_transfert_chaud(self):
        self.ensure_one()
        if not self._coins_phone_value():
            raise UserError(
                _(
                    "WhatsApp / téléphone obligatoire avant « Transfert à chaud ». "
                    "L’alerte ne part pas sans coordonnées."
                )
            )
        stage = self._coins_hot_stage()
        vals = {"coins_urgence": True, "coins_fiche_type": "voyageur"}
        if stage:
            vals["stage_id"] = stage.id
        self.write(vals)
        return True

    def action_coins_envoyer_message(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": _("Envoyer un message"),
            "res_model": "mail.compose.message",
            "view_mode": "form",
            "target": "new",
            "context": {
                "default_model": "crm.lead",
                "default_res_ids": self.ids,
                "default_composition_mode": "comment",
                "default_partner_ids": self.partner_id.ids,
            },
        }

    def action_coins_planifier_evenement(self):
        self.ensure_one()
        if self.coins_fiche_type != "voyageur" and not self.coins_is_voyageur_lead:
            raise UserError(
                _("Planifier l'événement est réservé aux fiches voyageur.")
            )
        return {
            "type": "ir.actions.act_window",
            "name": _("Planifier l'événement"),
            "res_model": "coins.planifier.evenement.wizard",
            "view_mode": "form",
            "target": "new",
            "context": {
                "default_lead_id": self.id,
                "dialog_size": "extra-large",
            },
        }

    def action_coins_nouvelle_reservation(self):
        self.ensure_one()
        partner = self.partner_id
        if not partner:
            name = self.contact_name or self.partner_name or self.name
            if not name:
                raise UserError(_("Indique le nom du voyageur avant la réservation."))
            partner = self.env["res.partner"].create(
                {
                    "name": name,
                    "phone": self._coins_phone_value() or False,
                    "email": self.email_from or False,
                }
            )
            self.partner_id = partner.id
        return {
            "type": "ir.actions.act_window",
            "name": _("Nouvelle réservation"),
            "res_model": "coins.reservation",
            "view_mode": "form",
            "target": "current",
            "context": {
                "default_lead_id": self.id,
                "default_traveler_id": partner.id,
                "default_client_nom": partner.name,
                "default_client_telephone": self._coins_phone_value() or False,
                "default_client_email": self.email_from or False,
            },
        }

    def action_open_coins_conversation(self):
        self.ensure_one()
        if not self.coins_conversation_id:
            return True
        return {
            "type": "ir.actions.act_window",
            "res_model": "coins.yasmine.conversation",
            "res_id": self.coins_conversation_id.id,
            "view_mode": "form",
            "target": "current",
        }

    _COINS_INFO_EMAIL = "info@coinsmarocain.com"
    _COINS_SPAM_NEEDLES = (
        "zapier.com",
        "pipedrive.com",
        "brevo.com",
        "semrush",
        "mailchimp",
        "lawfirms1",
        "whitespark",
        "modash",
        "noreply@",
        "no-reply@",
        "newsletter",
    )
    _COINS_PLACE_NEEDLES = (
        "riad",
        "villa",
        "hôtel",
        "hotel",
        "dar ",
        "commission",
        "entente",
        "partenariat",
        "channel manager",
        "shooting",
        "établissement",
        "etablissement",
    )
    _COINS_TRAVELER_NEEDLES = (
        "hammam",
        "excursion",
        "réservation",
        "reservation",
        "voyage",
        "concierge",
        "transfert",
        "whatsapp",
        "ourika",
        "pack",
        "bien-être",
        "bien etre",
        "anniversaire",
        "groupe",
    )

    def _coins_info_mailbox_partner(self):
        Partner = self.env["res.partner"].sudo()
        partner = Partner.search(
            [("email", "=ilike", self._COINS_INFO_EMAIL)], limit=1
        )
        if not partner:
            partner = Partner.create(
                {
                    "name": "Coins Marocain — info",
                    "email": self._COINS_INFO_EMAIL,
                    "company_type": "company",
                }
            )
        return partner

    def _coins_follow_info_mailbox(self):
        mailbox = self._coins_info_mailbox_partner()
        for lead in self:
            if lead.coins_fiche_type != "voyageur" and not lead.coins_is_voyageur_lead:
                continue
            lead.message_subscribe(partner_ids=mailbox.ids)
            if "email_cc" in lead._fields:
                cc = (lead.email_cc or "").lower()
                if self._COINS_INFO_EMAIL not in cc:
                    lead.email_cc = (
                        (lead.email_cc + ", " if lead.email_cc else "")
                        + self._COINS_INFO_EMAIL
                    )

    def _coins_classify_info_email(self, msg_dict):
        blob = " ".join(
            [
                (msg_dict or {}).get("subject") or "",
                (msg_dict or {}).get("from") or "",
                (msg_dict or {}).get("email_from") or "",
                (msg_dict or {}).get("body") or "",
            ]
        ).lower()
        if any(n in blob for n in self._COINS_SPAM_NEEDLES):
            return "spam"
        if any(n in blob for n in self._COINS_PLACE_NEEDLES):
            return "partenariat"
        if any(n in blob for n in self._COINS_TRAVELER_NEEDLES):
            return "voyageur"
        return "voyageur"

    @api.model
    def message_new(self, msg_dict, custom_values=None):
        custom_values = dict(custom_values or {})
        team_cm = self.env.ref(
            "coins_marocain_partenariats.crm_team_coins_marocain",
            raise_if_not_found=False,
        )
        team_voy = self.env.ref(
            "coins_marocain_partenariats.crm_team_coins_voyageurs",
            raise_if_not_found=False,
        )
        if team_cm and custom_values.get("team_id") == team_cm.id:
            kind = self._coins_classify_info_email(msg_dict)
            if kind == "spam":
                reason = self.env["crm.lost.reason"].sudo().search(
                    [("name", "=", "Spam / newsletter / SEO")], limit=1
                )
                custom_values["active"] = False
                if reason:
                    custom_values["lost_reason_id"] = reason.id
            elif kind == "voyageur" and team_voy:
                custom_values["team_id"] = team_voy.id
                custom_values["coins_fiche_type"] = "voyageur"
                custom_values["coins_canal_origine"] = "autre"
                stage = self.env.ref(
                    "coins_marocain_partenariats.crm_stage_voy_nouveau",
                    raise_if_not_found=False,
                )
                if stage:
                    custom_values["stage_id"] = stage.id
            else:
                custom_values["coins_fiche_type"] = "partenariat"
        lead = super().message_new(msg_dict, custom_values)
        if lead.coins_fiche_type == "voyageur" or lead.coins_is_voyageur_lead:
            lead._coins_follow_info_mailbox()
        return lead

    @api.model_create_multi
    def create(self, vals_list):
        leads = super().create(vals_list)
        leads._coins_follow_info_mailbox()
        voy = leads.filtered(
            lambda l: l.coins_is_voyageur_lead or l.coins_fiche_type == "voyageur"
        )
        if voy:
            voy._coins_voy_ensure_relance()
            voy._coins_voy_reassert_team()
        return leads

    def _coins_voy_reassert_team(self):
        """Garde les fiches voyageur sur l'équipe kanban (pas Marketing)."""
        team = self._coins_voy_team()
        if not team:
            return self
        stolen = self.filtered(
            lambda l: (
                l.coins_fiche_type == "voyageur" or l.coins_is_voyageur_lead
            )
            and l.team_id.id != team.id
        )
        if stolen:
            stolen.with_context(mail_notrack=True).write({"team_id": team.id})
        return self

    @api.model
    def _coins_voy_team(self):
        return self.env.ref(
            "coins_marocain_partenariats.crm_team_coins_voyageurs",
            raise_if_not_found=False,
        )

    @api.model
    def _coins_voy_events_team(self):
        return self.env.ref(
            "coins_marocain.crm_team_evenements", raise_if_not_found=False
        )

    @api.model
    def _coins_voy_zakaria_user(self):
        if hasattr(self, "_coins_events_zakaria_user"):
            user = self._coins_events_zakaria_user()
            if user:
                return user
        return self.env["res.users"].sudo().search(
            [
                (
                    "login",
                    "in",
                    ("zakaria@agencedoorway.com", "zakaria@coinsmarocain.com"),
                ),
                ("active", "=", True),
            ],
            limit=1,
        )

    @api.model
    def _coins_voy_map_event_type(self, raw):
        key = (raw or "").strip().lower().replace(" ", "_")
        mapped = EVENT_TYPE_MAP.get(key) or EVENT_TYPE_MAP.get(
            key.replace("’", "'")
        )
        if mapped:
            return mapped
        if hasattr(self, "_coins_map_event_type"):
            return self._coins_map_event_type(raw)
        return "autre"

    @api.model
    def _coins_voy_map_taille(self, raw):
        text = (raw or "").strip().lower().replace(" ", "")
        if text in TAILLE_MAP:
            return TAILLE_MAP[text]
        nums = [int(x) for x in re.findall(r"\d+", text)]
        if not nums:
            return False
        n = max(nums)
        if n >= 30:
            return "30_plus"
        if n >= 20:
            return "20_30"
        if n >= 10:
            return "10_20"
        return "1_10"

    @api.model
    def _coins_voy_parse_event_date(self, raw):
        text = (raw or "").strip()
        if not text:
            return False, True
        months = {
            "january": 1,
            "janvier": 1,
            "february": 2,
            "février": 2,
            "fevrier": 2,
            "march": 3,
            "mars": 3,
            "april": 4,
            "avril": 4,
            "may": 5,
            "mai": 5,
            "june": 6,
            "juin": 6,
            "july": 7,
            "juillet": 7,
            "august": 8,
            "août": 8,
            "aout": 8,
            "september": 9,
            "septembre": 9,
            "october": 10,
            "octobre": 10,
            "november": 11,
            "novembre": 11,
            "december": 12,
            "décembre": 12,
            "decembre": 12,
        }
        m = re.search(r"(\d{1,2})/(\d{1,2})/(\d{4})", text)
        if m:
            d, mo, y = int(m.group(1)), int(m.group(2)), int(m.group(3))
            try:
                return date(y, mo, d), False
            except ValueError:
                return False, True
        low = text.lower()
        year_m = re.search(r"(20\d{2})", low)
        year = int(year_m.group(1)) if year_m else date.today().year
        day_m = re.search(
            r"(\d{1,2})\s+(janvier|février|fevrier|mars|avril|mai|juin|"
            r"juillet|août|aout|septembre|octobre|novembre|décembre|decembre|"
            r"january|february|march|april|may|june|july|august|september|"
            r"october|november|december)",
            low,
        )
        if day_m:
            day = int(day_m.group(1))
            mo = months.get(day_m.group(2))
            if mo:
                try:
                    return date(year, mo, min(day, 28)), True
                except ValueError:
                    return False, True
        for name, mo in months.items():
            if name in low:
                try:
                    return date(year, mo, 1), True
                except ValueError:
                    return False, True
        if hasattr(self, "_coins_parse_date_envisagée"):
            return self._coins_parse_date_envisagée(raw)
        return False, True

    @api.model
    def _coins_voy_norm_phone(self, raw):
        digits = re.sub(r"\D", "", raw or "")
        if digits.startswith("00"):
            digits = digits[2:]
        if digits.startswith("0") and len(digits) == 10:
            digits = "212" + digits[1:]
        return digits

    @api.model
    def _coins_voy_find_duplicate(self, email, phone, team):
        if not team:
            return self.browse()
        Lead = self.sudo()
        base = [
            ("team_id", "=", team.id),
            ("coins_fiche_type", "=", "voyageur"),
        ]
        email_n = (email or "").strip().lower()
        if email_n:
            found = Lead.search(base + [("email_from", "=ilike", email_n)], limit=1)
            if found:
                return found
        phone_n = self._coins_voy_norm_phone(phone)
        if phone_n and len(phone_n) >= 8:
            candidates = Lead.search(
                base
                + [
                    "|",
                    ("phone", "!=", False),
                    ("coins_whatsapp", "!=", False),
                ]
            )
            for lead in candidates:
                for raw in (lead.coins_whatsapp, lead.phone):
                    if self._coins_voy_norm_phone(raw) == phone_n:
                        return lead
        return self.browse()

    @api.model
    def _coins_voy_row_vals(self, row, team, stage_new, stage_incomplet, user):
        if not row or len(row) < 18:
            return None
        lead_key = (row[COL_ID] or "").strip()
        if not lead_key.startswith("l:"):
            return None
        email = (row[COL_EMAIL] if len(row) > COL_EMAIL else "").strip()
        name = (row[COL_NAME] if len(row) > COL_NAME else "").strip()
        phone = (row[COL_PHONE] if len(row) > COL_PHONE else "").strip()
        if not email and not phone and not name:
            return None
        event_raw = row[COL_EVENT_TYPE] if len(row) > COL_EVENT_TYPE else ""
        event_type = self._coins_voy_map_event_type(event_raw)
        taille_raw = row[COL_NB_PERSONNES] if len(row) > COL_NB_PERSONNES else ""
        taille = self._coins_voy_map_taille(taille_raw)
        if hasattr(self, "_coins_parse_nb_personnes"):
            nb = self._coins_parse_nb_personnes(taille_raw)
        else:
            nums = [int(x) for x in re.findall(r"\d+", taille_raw or "")]
            nb = max(nums) if nums else 0
        date_raw = row[COL_DATE_ENV] if len(row) > COL_DATE_ENV else ""
        date_env, flexible = self._coins_voy_parse_event_date(date_raw)
        campaign = row[COL_CAMPAIGN] if len(row) > COL_CAMPAIGN else ""
        form_name = row[COL_FORM] if len(row) > COL_FORM else ""
        platform = row[COL_PLATFORM] if len(row) > COL_PLATFORM else ""
        created = row[COL_CREATED] if len(row) > COL_CREATED else ""
        incomplete = not email or not phone
        stage = stage_incomplet if incomplete and stage_incomplet else stage_new
        lead_name = name or email or phone or lead_key
        desc_lines = [
            "Import Google Sheet — Voyageurs Coins Marocain (%s)" % lead_key,
            "Type d'événement (formulaire) : %s" % event_raw,
            "Taille de groupe : %s" % taille_raw,
            "Date événement (texte) : %s" % date_raw,
        ]
        if flexible and date_raw:
            desc_lines.append("Date normalisée approximative — texte libre conservé.")
        desc_lines.extend(
            [
                "Campagne : %s" % campaign,
                "Formulaire : %s" % form_name,
                "Plateforme : %s" % platform,
                "Créé Meta : %s" % created,
            ]
        )
        if incomplete:
            desc_lines.append(
                "Coordonnées incomplètes : email et/ou téléphone manquant."
            )
        vals = {
            "name": lead_name,
            "contact_name": name or False,
            "email_from": email or False,
            "phone": phone or False,
            "coins_whatsapp": phone or False,
            # crm.lead Odoo 19 n'a plus mobile — téléphone + WhatsApp suffisent.
            "description": "\n".join(desc_lines),
            "type": "opportunity",
            "team_id": team.id,
            "coins_fiche_type": "voyageur",
            "stage_id": stage.id if stage else False,
            "user_id": user.id if user else False,
            "coins_commercial_assigne": user.id if user else False,
            "coins_canal_origine": "meta",
            "coins_xsell_evenements": True,
            "coins_sheet_row_key": lead_key,
            "coins_type_evenement": event_type,
            "coins_nombre_personnes": nb,
            "coins_voy_taille_groupe": taille,
            "coins_date_souhaitee": date_env or False,
            "coins_date_flexible": flexible,
            "coins_voy_date_event_raw": date_raw or False,
            "coins_moyen_recontact": "whatsapp" if phone else "email",
            "coins_service_demande": {
                "mariage": "Fiançailles / mariage",
                "anniversaire": "Anniversaire",
                "groupe_amis": "Moment festif amis / famille",
                "reunion_famille": "Réunion de famille",
            }.get(event_type, event_raw or "Événement"),
        }
        return vals, incomplete

    @api.model
    def _coins_voy_forbidden_team_ids(self):
        ids = []
        for xmlid in (
            "coins_marocain_partenariats.crm_team_coins_marocain",
            "reno_immobilier.crm_team_reno_immobilier",
            "renovation_conciergerie.crm_team_renovation",
            "renovation_conciergerie.crm_team_immobilier",
            "renovation_conciergerie.crm_team_driven",
            "intellix_finance.crm_team_itex",
            "intellix_finance.crm_team_finance",
        ):
            rec = self.env.ref(xmlid, raise_if_not_found=False)
            if rec:
                ids.append(rec.id)
        extra = self.env["crm.team"].sudo().search(
            ["|", ("name", "ilike", "Québec"), ("name", "ilike", "Driven")]
        )
        ids.extend(extra.ids)
        return set(ids)

    @api.model
    def action_sync_coins_voyageurs_google_sheet(self):
        """Importe le sheet Meta vers Voyageurs CM. Ne touche pas hôtels / partenariats."""
        team = self._coins_voy_team()
        if not team:
            return {"ok": False, "error": "crm_team_coins_voyageurs introuvable"}
        stage_new = self.env.ref(
            "coins_marocain_partenariats.crm_stage_voy_nouveau",
            raise_if_not_found=False,
        )
        stage_incomplet = self.env.ref(
            "coins_marocain_partenariats.crm_stage_voy_incomplet",
            raise_if_not_found=False,
        )
        user = self._coins_voy_zakaria_user()
        if hasattr(self, "_coins_ensure_zakaria_on_events_team"):
            self._coins_ensure_zakaria_on_events_team(team, user)
        try:
            if hasattr(self, "_coins_fetch_events_sheet_rows"):
                rows = self._coins_fetch_events_sheet_rows()
            else:
                raise RuntimeError("fetch sheet indisponible")
        except Exception as exc:  # noqa: BLE001
            _logger.exception("coins voyageurs sheet fetch failed")
            return {"ok": False, "error": str(exc)}
        created = migrated = skipped_dup = skipped_row = incomplete_n = 0
        Lead = self.sudo()
        ev_team = self._coins_voy_events_team()
        forbidden_teams = self._coins_voy_forbidden_team_ids()
        for row in rows:
            parsed = self._coins_voy_row_vals(
                row, team, stage_new, stage_incomplet, user
            )
            if not parsed:
                skipped_row += 1
                continue
            vals, incomplete = parsed
            key = vals["coins_sheet_row_key"]
            existing_key = Lead.with_context(active_test=False).search(
                [("coins_sheet_row_key", "=", key)], limit=1
            )
            if existing_key:
                if (
                    existing_key.coins_fiche_type == "voyageur"
                    and existing_key.team_id == team
                ):
                    skipped_dup += 1
                    continue
                # Sheet Meta mal routé vers Événements / team CM : basculer vers voyageurs.
                # Ne pas merger un hôtel / partenariat réel.
                misrouted = existing_key.coins_fiche_type == "evenement" or (
                    ev_team and existing_key.team_id == ev_team
                )
                if misrouted:
                    write_vals = dict(vals)
                    write_vals.pop("type", None)
                    if existing_key.user_id:
                        write_vals.pop("user_id", None)
                        write_vals.pop("coins_commercial_assigne", None)
                    if (existing_key.name or "").startswith("[Événement]"):
                        write_vals["name"] = vals["name"]
                    existing_key.write(write_vals)
                    existing_key._coins_voy_ensure_relance()
                    migrated += 1
                    if incomplete:
                        incomplete_n += 1
                    continue
                skipped_dup += 1
                continue
            dup = self._coins_voy_find_duplicate(
                vals.get("email_from"), vals.get("phone"), team
            )
            if dup:
                skipped_dup += 1
                continue
            lead = Lead.create(vals)
            lead._coins_voy_ensure_relance()
            created += 1
            if incomplete:
                incomplete_n += 1
        if team:
            Lead.search(
                [("coins_fiche_type", "=", "voyageur")]
            )._coins_voy_reassert_team()
        result = {
            "ok": True,
            "created": created,
            "migrated": migrated,
            "imported": created + migrated,
            "incomplete": incomplete_n,
            "duplicates_skipped": skipped_dup,
            "rows_skipped": skipped_row,
            "team_id": team.id,
        }
        _logger.info("coins voyageurs sheet sync: %s", result)
        return result

    @api.model
    def action_sync_coins_events_google_sheet(self):
        """Le sheet événements alimente désormais Voyageurs CM, pas Événements."""
        return self.action_sync_coins_voyageurs_google_sheet()

    @api.model
    def cron_sync_coins_events_google_sheet(self):
        return self.action_sync_coins_voyageurs_google_sheet()
