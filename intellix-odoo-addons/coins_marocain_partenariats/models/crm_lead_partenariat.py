# -*- coding: utf-8 -*-
import os
import re
from urllib.parse import quote

from markupsafe import Markup, escape

from odoo import api, fields, models, _
from odoo.exceptions import UserError
from odoo.modules.module import get_module_path


class CrmLead(models.Model):
    _inherit = ["crm.lead", "coins.assignee.mixin"]
    # Barre de recherche / many2one : nom, établissement, contact, email, tel.
    _rec_names_search = [
        "name",
        "contact_name",
        "partner_name",
        "email_from",
        "phone",
        "coins_etablissement",
        "coins_whatsapp",
    ]

    coins_fiche_type = fields.Selection(
        [
            ("partenariat", "Partenariat établissement"),
            ("evenement", "Événement / voyageur"),
            ("voyageur", "Concierge / voyageur"),
        ],
        string="Type de fiche Coins",
        default="partenariat",
        tracking=True,
        index=True,
    )
    coins_is_event_lead = fields.Boolean(
        string="Lead pipeline Événements",
        compute="_compute_coins_pipeline_flags",
        store=True,
    )
    coins_is_partner_lead = fields.Boolean(
        string="Lead pipeline Coins Marocain",
        compute="_compute_coins_pipeline_flags",
        store=True,
    )
    coins_show_partner_assign = fields.Boolean(
        string="Afficher assignation partenaire",
        compute="_compute_coins_show_partner_assign",
        help="CM / CQ, ou lead Réno Immobilier / Immobilier / Leads Gestion. "
        "Ne pas se fier à team_id not in (…) : cassé en OWL pour les many2one.",
    )

    coins_type_partenaire = fields.Selection(
        [
            ("hebergement", "Hôtel / Riad / Villa"),
            ("restauration", "Restaurant"),
            ("spa", "Spa / bien-être"),
            ("activite", "Activité / excursion"),
            ("wedding_planner", "Wedding planner"),
            ("agence_voyage", "Agence de voyage"),
            ("organisateur_congres", "Organisateur congrès"),
            ("influenceur", "Influenceur"),
            ("autre", "Autre"),
        ],
        string="Type de partenaire",
        tracking=True,
        index=True,
    )
    coins_ville = fields.Selection(
        [
            ("marrakech", "Marrakech"),
            ("casablanca", "Casablanca"),
            ("agadir", "Agadir"),
            ("fes", "Fès"),
            ("rabat", "Rabat"),
            ("tanger", "Tanger"),
            ("essaouira", "Essaouira"),
            ("autre", "Autre"),
        ],
        string="Ville",
        tracking=True,
        index=True,
    )
    coins_ville_autre = fields.Char(string="Ville (précision)")
    coins_quartier = fields.Char(string="Quartier / zone")
    coins_etablissement = fields.Char(string="Établissement", tracking=True)
    coins_contact_role = fields.Selection(
        [
            ("proprio", "Propriétaire"),
            ("gerant", "Gérant"),
            ("marketing", "Marketing"),
            ("reception", "Réception"),
            ("autre", "Autre"),
        ],
        string="Rôle du contact",
        tracking=True,
    )
    coins_whatsapp = fields.Char(string="WhatsApp")
    coins_instagram = fields.Char(string="Instagram")
    coins_site_web = fields.Char(string="Site web")

    canal_traitement = fields.Selection(
        [
            ("autonome", "Autonome (Offre 1)"),
            ("accompagne", "Accompagné (Offre 2/3)"),
        ],
        string="Canal de traitement",
        tracking=True,
        index=True,
        help="Autonome vs Accompagné — champ unique, ne pas dupliquer.",
    )
    coins_date_appel = fields.Date(string="Date appel composé", tracking=True)
    coins_appel_compose = fields.Boolean(string="Appel composé", tracking=True)
    coins_date_conversation = fields.Date(
        string="Date conversation complétée",
        tracking=True,
    )
    coins_conversation_completee = fields.Boolean(
        string="Conversation complétée",
        tracking=True,
    )
    coins_interet_confirme = fields.Boolean(
        string="Intérêt confirmé",
        tracking=True,
        index=True,
    )
    coins_date_visite = fields.Date(string="Date de visite planifiée", tracking=True)
    coins_date_visite_realisee = fields.Date(
        string="Date de visite réalisée",
        tracking=True,
    )
    coins_visite_realisee = fields.Boolean(
        string="Visite réalisée",
        compute="_compute_coins_visite_realisee",
        store=True,
    )
    coins_notes_visite = fields.Text(string="Notes de visite")
    coins_date_derniere_relance = fields.Date(
        string="Dernière relance",
        tracking=True,
    )
    coins_date_prochaine_relance = fields.Date(
        string="Prochaine relance",
        tracking=True,
        index=True,
    )
    coins_relance_canal = fields.Selection(
        [
            ("whatsapp", "WhatsApp"),
            ("appel", "Appel"),
            ("email", "Email"),
            ("visite", "Visite"),
        ],
        string="Canal de relance",
        default="whatsapp",
    )
    coins_nb_relances = fields.Integer(string="Nb relances", default=0)
    coins_relance_notes = fields.Text(string="Notes de relance")

    coins_interet_carte = fields.Boolean(string="Intéressé carte / fiche")
    coins_interet_channel_manager = fields.Boolean(string="Intéressé channel manager")
    coins_interet_shooting = fields.Boolean(string="Shooting photo/vidéo à planifier")
    coins_commission_pct = fields.Float(string="Commission (%)", digits=(16, 2))
    coins_commission_suggeree = fields.Float(
        string="Commission suggérée (%)",
        compute="_compute_coins_commission_suggeree",
    )
    coins_commission_modele = fields.Char(string="Modèle de commission")
    coins_sale_order_id = fields.Many2one(
        "sale.order",
        string="Devis partenaire",
        copy=False,
    )
    coins_entente_id = fields.Many2one(
        "coins.entente",
        string="Entente",
        copy=False,
        tracking=True,
    )
    coins_categorie_etab = fields.Selection(
        [
            ("decouverte", "Découverte"),
            ("privatisation", "Privatisation"),
            ("evenements", "Événements"),
            ("hebergement", "Hébergement"),
            ("bien_etre", "Bien-être"),
        ],
        string="Catégorie établissement",
        tracking=True,
        index=True,
    )
    coins_tarif = fields.Char(string="Tarif")
    coins_entente_statut = fields.Selection(
        related="coins_entente_id.statut_entente",
        string="Statut entente",
    )
    coins_xsell_site_web = fields.Boolean(string="Site web")
    coins_xsell_reseaux = fields.Boolean(string="Réseaux sociaux")
    coins_shoot_pack = fields.Selection(
        [
            ("pro_2000", "Pack Pro — 2 000 DH"),
            ("premium_3500", "Pack Premium — 3 500 DH"),
        ],
        string="Pack shoot Maroc",
    )
    coins_note = fields.Text(string="Note")
    coins_property_id = fields.Many2one(
        "coins.property",
        string="Fiche lieu",
        copy=False,
        help="Lien tokenisé /partenaire/[token] — même modèle que les biens / vidéos.",
    )
    coins_partner_lien = fields.Char(
        string="Lien partenaire",
        compute="_compute_coins_partner_lien",
    )
    coins_onboarding_status = fields.Selection(
        related="coins_property_id.onboarding_status",
        string="Statut fiche",
    )
    coins_scrape_zone = fields.Selection(
        [
            ("medina_nord", "Médina Nord / Bab Doukala"),
            ("medina_centre", "Médina Centre"),
            ("medina_sud", "Médina Sud / Kasbah"),
            ("hivernage_gueliz", "Hivernage / Guéliz"),
            ("peripherie", "Périphérie"),
        ],
        string="Zone scrape",
        index=True,
        copy=False,
    )
    coins_scrape_source = fields.Selection(
        [
            ("google_places", "Google Places"),
            ("pages_jaunes", "Pages Jaunes (complément tél.)"),
            ("manuel", "Manuel"),
        ],
        string="Source scrape",
        index=True,
        copy=False,
    )
    coins_google_place_id = fields.Char(
        string="Google Place ID",
        index=True,
        copy=False,
    )

    @api.depends("coins_date_visite_realisee")
    def _compute_coins_visite_realisee(self):
        for lead in self:
            lead.coins_visite_realisee = bool(lead.coins_date_visite_realisee)

    @api.depends("coins_categorie_etab", "coins_type_partenaire")
    def _compute_coins_commission_suggeree(self):
        for lead in self:
            cat = lead.coins_categorie_etab or lead.coins_type_partenaire
            if cat in ("hebergement",):
                lead.coins_commission_suggeree = 12.5
            elif cat in ("activite", "decouverte", "privatisation"):
                lead.coins_commission_suggeree = 30.0
            else:
                lead.coins_commission_suggeree = 15.0

    @api.onchange("coins_categorie_etab", "coins_type_partenaire")
    def _onchange_coins_suggest_commission(self):
        if not self.coins_commission_pct:
            self.coins_commission_pct = self.coins_commission_suggeree
        if not self.coins_commission_modele:
            cat = self.coins_categorie_etab or self.coins_type_partenaire
            if cat in ("hebergement",):
                self.coins_commission_modele = "Hébergement 10–15 %"
            elif cat in ("activite", "decouverte", "privatisation"):
                self.coins_commission_modele = "Activités 25–35 %"
            else:
                self.coins_commission_modele = "Commission générale Maroc 15 %"

    @api.onchange("contact_name", "coins_etablissement", "coins_fiche_type")
    def _onchange_coins_sync_name(self):
        title = (
            self.contact_name
            if self.coins_fiche_type == "voyageur"
            else (self.coins_etablissement or self.contact_name)
        )
        if title and (not self.name or self.name in ("Nouveau", "/")):
            self.name = title

    @api.depends("team_id", "coins_fiche_type")
    def _compute_coins_pipeline_flags(self):
        team_cm = self.env.ref(
            "coins_marocain_partenariats.crm_team_coins_marocain",
            raise_if_not_found=False,
        )
        team_cq = self._coins_quebec_team()
        team_ev = self.env.ref(
            "coins_marocain.crm_team_evenements",
            raise_if_not_found=False,
        )
        team_voy = self.env.ref(
            "coins_marocain_partenariats.crm_team_coins_voyageurs",
            raise_if_not_found=False,
        )
        cm_id = team_cm.id if team_cm else False
        cq_id = team_cq.id if team_cq else False
        ev_id = team_ev.id if team_ev else False
        voy_id = team_voy.id if team_voy else False
        for lead in self:
            is_event = lead.coins_fiche_type == "evenement" or (
                ev_id and lead.team_id.id == ev_id
            )
            is_voy = lead.coins_fiche_type == "voyageur" or (
                voy_id and lead.team_id.id == voy_id
            )
            lead.coins_is_event_lead = bool(is_event)
            if "coins_is_voyageur_lead" in lead._fields:
                lead.coins_is_voyageur_lead = bool(is_voy and not is_event)
            # Team CM/CQ only — coins_fiche_type default is "partenariat" on ALL
            # crm.lead, which leaked the notebook Partenariat onto Réno / ITEX.
            lead.coins_is_partner_lead = bool(
                not is_event
                and not is_voy
                and (
                    (cm_id and lead.team_id.id == cm_id)
                    or (cq_id and lead.team_id.id == cq_id)
                )
            )

    @api.depends("coins_is_partner_lead", "team_id")
    def _compute_coins_show_partner_assign(self):
        reno_ids = set()
        if "reno_immo_lead" in self._fields and hasattr(
            self, "_reno_immo_team_ids"
        ):
            reno_ids = set(self._reno_immo_team_ids())
        else:
            for xmlid in (
                "reno_immobilier.crm_team_reno_immobilier",
                "renovation_conciergerie.crm_team_renovation",
                "renovation_conciergerie.crm_team_immobilier",
            ):
                team = self.env.ref(xmlid, raise_if_not_found=False)
                if team:
                    reno_ids.add(team.id)
        for lead in self:
            is_reno = bool(lead.team_id.id in reno_ids)
            if "reno_immo_lead" in lead._fields:
                is_reno = is_reno or bool(lead.reno_immo_lead)
            lead.coins_show_partner_assign = bool(
                lead.coins_is_partner_lead or is_reno
            )

    @api.model_create_multi
    def create(self, vals_list):
        team_cm = self.env.ref(
            "coins_marocain_partenariats.crm_team_coins_marocain",
            raise_if_not_found=False,
        )
        team_cq = self._coins_quebec_team()
        team_voy = self.env.ref(
            "coins_marocain_partenariats.crm_team_coins_voyageurs",
            raise_if_not_found=False,
        )
        for vals in vals_list:
            if team_voy and vals.get("team_id") == team_voy.id:
                vals.setdefault("coins_fiche_type", "voyageur")
                vals.setdefault("type", "opportunity")
            elif team_cm and vals.get("team_id") == team_cm.id:
                vals.setdefault("coins_fiche_type", "partenariat")
                vals.setdefault("type", "opportunity")
                if not vals.get("coins_commercial_assigne") and not vals.get(
                    "coins_agent_ia_id"
                ):
                    if vals.get("assignee_kind") != "ia":
                        vals["coins_commercial_assigne"] = (
                            vals.get("user_id") or self.env.uid
                        )
                if not vals.get("coins_scrape_source"):
                    vals["coins_scrape_source"] = "manuel"
                global_new = self.env.ref("crm.stage_lead1", raise_if_not_found=False)
                cm_new = self.env.ref(
                    "coins_marocain_partenariats.crm_stage_cm_nouveau",
                    raise_if_not_found=False,
                )
                if cm_new and (
                    not vals.get("stage_id")
                    or (global_new and vals.get("stage_id") == global_new.id)
                ):
                    vals["stage_id"] = cm_new.id
                if not vals.get("coins_commission_pct"):
                    cat = vals.get("coins_categorie_etab") or vals.get(
                        "coins_type_partenaire"
                    )
                    vals["coins_commission_pct"] = 12.5 if cat == "hebergement" else 15.0
            elif team_cq and vals.get("team_id") == team_cq.id:
                vals.setdefault("coins_fiche_type", "partenariat")
                vals.setdefault("type", "opportunity")
            if not vals.get("name"):
                vals["name"] = (
                    vals.get("coins_etablissement")
                    or vals.get("contact_name")
                    or vals.get("partner_name")
                    or "Nouveau"
                )
        return super().create(vals_list)

    def write(self, vals):
        res = super().write(vals)
        if "coins_date_prochaine_relance" in vals:
            for lead in self:
                if lead.coins_date_prochaine_relance:
                    super(CrmLead, lead).write(
                        {"date_deadline": lead.coins_date_prochaine_relance}
                    )
        return res

    def action_coins_relance_faite(self):
        self.ensure_one()
        self.write(
            {
                "coins_date_derniere_relance": fields.Date.context_today(self),
                "coins_nb_relances": (self.coins_nb_relances or 0) + 1,
            }
        )
        return True

    def _coins_partner_email(self):
        """Email visible sur la fiche : lead, contact lié ou fiche partenaire."""
        self.ensure_one()
        candidates = [self.email_from]
        if self.partner_id:
            candidates.append(self.partner_id.email)
        if self.coins_property_id:
            candidates.append(self.coins_property_id.onboarding_email)
        for raw in candidates:
            if (raw or "").strip():
                return raw.strip()
        return ""

    def _coins_partner_display_name(self):
        """Nom utilisable : contact, établissement ou titre de fiche."""
        self.ensure_one()
        candidates = [
            self.contact_name,
            self.partner_name,
            self.partner_id.name if self.partner_id else "",
            self.coins_etablissement,
            self.name,
        ]
        for raw in candidates:
            val = (raw or "").strip()
            if val and val not in ("Nouveau", "/"):
                return val
        return ""

    def _coins_zakaria_outgoing(self):
        """Boîte SMTP réelle — pas zakaria@coinsmarocain.com (aucun serveur)."""
        server = self.env["ir.mail_server"].sudo().search(
            [("from_filter", "=", "zakaria@agencedoorway.com")],
            limit=1,
        )
        return {
            "email_from": "Zakaria — Coins Marocain <zakaria@agencedoorway.com>",
            "mail_server_id": server.id if server else False,
        }

    def _action_send_coins_mail_template(self, xmlid, name_ilike, wizard_name):
        self.ensure_one()
        email = self._coins_partner_email()
        name = self._coins_partner_display_name()
        if not email:
            raise UserError(
                _("Impossible d'envoyer — ajoutez l'email du contact sur la fiche.")
            )
        if not name:
            raise UserError(
                _("Impossible d'envoyer — indiquez le nom du contact ou de l'établissement.")
            )
        backfill = {}
        if not (self.email_from or "").strip():
            backfill["email_from"] = email
        if not (self.contact_name or "").strip():
            backfill["contact_name"] = name
        if backfill:
            self.write(backfill)
        partner = self._coins_ensure_partner()
        outgoing = self._coins_zakaria_outgoing()
        template = self.env.ref(xmlid, raise_if_not_found=False)
        if not template:
            template = self.env["mail.template"].sudo().search(
                [("model", "=", "crm.lead"), ("name", "ilike", name_ilike)],
                limit=1,
            )
        if not template:
            raise UserError(_("Modèle introuvable : %s") % wizard_name)
        return {
            "type": "ir.actions.act_window",
            "name": wizard_name,
            "res_model": "mail.compose.message",
            "view_mode": "form",
            "target": "new",
            "context": {
                "default_model": "crm.lead",
                "default_res_ids": self.ids,
                "default_template_id": template.id,
                "default_use_template": True,
                "default_composition_mode": "comment",
                "default_partner_ids": partner.ids,
                "default_email_from": outgoing["email_from"],
                "default_mail_server_id": outgoing["mail_server_id"],
                "mail_post_autofollow": True,
            },
        }

    def action_send_coins_hotel_email(self):
        """Ouvre le composer avec l'email prospection hôtels + vidéo."""
        return self._action_send_coins_mail_template(
            "coins_marocain_partenariats.mail_template_zakaria_channel_manager",
            "Prospection hôtels",
            _("Email prospection hôtels — Channel Manager"),
        )

    def _coins_followup_mail_ref(self):
        """Modèle post-rencontre selon la catégorie (hôtel, resto, spa, activité)."""
        self.ensure_one()
        kind = self.coins_type_partenaire or self.coins_categorie_etab
        mapping = {
            "restauration": (
                "coins_marocain_partenariats.mail_template_zakaria_suite_rencontre_restaurant",
                "Suivi rencontre (restaurant)",
            ),
            "spa": (
                "coins_marocain_partenariats.mail_template_zakaria_suite_rencontre_spa",
                "Suivi rencontre (spa",
            ),
            "bien_etre": (
                "coins_marocain_partenariats.mail_template_zakaria_suite_rencontre_spa",
                "Suivi rencontre (spa",
            ),
            "activite": (
                "coins_marocain_partenariats.mail_template_zakaria_suite_rencontre_activite",
                "Suivi rencontre (activité)",
            ),
            "decouverte": (
                "coins_marocain_partenariats.mail_template_zakaria_suite_rencontre_activite",
                "Suivi rencontre (activité)",
            ),
        }
        return mapping.get(
            kind,
            (
                "coins_marocain_partenariats.mail_template_zakaria_suite_rencontre",
                "Suite à notre rencontre",
            ),
        )

    def action_send_coins_followup_email(self):
        """Ouvre le composer avec le modèle post-rencontre (Zakaria)."""
        self._coins_ensure_partner_property()
        xmlid, name_ilike = self._coins_followup_mail_ref()
        return self._action_send_coins_mail_template(
            xmlid,
            name_ilike,
            _("Envoyer suivi rencontre"),
        )

    def _cm_intro_contact_firstname(self):
        self.ensure_one()
        raw = (self.contact_name or "").strip()
        first = (raw.split() or [""])[0]
        low = raw.lower()
        if (
            not first
            or "test" in low
            or low in ("zakaria", "karine")
            or first.lower() in ("riad", "hotel", "hôtel", "dar", "villa")
        ):
            return "Madame, Monsieur"
        return first

    def _cm_intro_etablissement(self):
        self.ensure_one()
        prop = self.coins_property_id
        return (
            (prop.name if prop else "")
            or (self.coins_etablissement or "")
            or (self.partner_name or "")
            or (self.name or "")
            or "votre établissement"
        ).strip()

    def _cm_entente_public_url(self):
        """Lien de signature électronique / devis — jamais une pièce jointe."""
        self.ensure_one()
        entente = self.coins_entente_id
        if entente:
            sig = entente.signature_id
            if sig and hasattr(sig, "get_sign_url"):
                return sig.get_sign_url()
            token = (entente.token_signature or "").strip()
            if token:
                return "https://intellixcrm.com/sign/contract/%s" % token
        order = self.coins_sale_order_id
        if order:
            order._portal_ensure_token()
            path = order.get_portal_url() or ""
            if path.startswith("http"):
                return path
            return "https://intellixcrm.com%s" % path
        lien = (self.coins_partner_lien or "").strip()
        if lien:
            return lien
        return "https://coinsmarocain.com/partenaire"

    def _cm_intro_pillar_html(self, title, body, last=False):
        margin = "0" if last else "0 0 16px"
        return (
            '<div style="margin:%s;">'
            '<div style="font-family:\'Cormorant Garamond\',Georgia,serif;'
            'font-weight:600;font-size:16.5px;color:#3A2E1F;">%s</div>'
            '<div style="font-size:13px;color:#5C4D38;line-height:1.6;margin-top:4px;">%s</div>'
            "</div>"
        ) % (margin, title, body)

    def _cm_intro_offer_blocks(self):
        """Trois volets — montants = produits / devis visibilité, pas d'invention."""
        self.ensure_one()
        kind = self.coins_type_partenaire or self.coins_categorie_etab or "hebergement"
        if kind in ("hebergement", "riad", "villa", "hotel", "apartment"):
            visib = (
                "Présence sur la carte Coins Marocain. "
                "Commission de <strong>15&nbsp;%</strong> uniquement sur les "
                "réservations réelles via la plateforme — aucun forfait à la signature."
            )
            digital = (
                "Channel Manager Channex, connecté à plus de 200 plateformes "
                "(Booking, Airbnb, Expedia et autres) — "
                "<strong>750&nbsp;DH HT</strong>. "
                "Un seul calendrier, sans double réservation. "
                "Module hébergement IntelliX inclus."
            )
        elif kind in ("restauration",):
            visib = (
                "Présence sur la carte Coins Marocain. "
                "Commission de <strong>15&nbsp;%</strong> sur les réservations "
                "via la plateforme — aucun frais fixe."
            )
            digital = (
                "Gestion des réservations, personnel / présence, pricing dynamique — "
                "<strong>10&nbsp;% des réservations ou 1&nbsp;500&nbsp;DH/mois</strong>."
            )
        elif kind in ("spa", "bien_etre"):
            visib = (
                "Présence sur la carte Coins Marocain. "
                "Commission de <strong>15&nbsp;%</strong> sur les réservations "
                "via la plateforme — aucun frais fixe."
            )
            digital = (
                "Réservations en ligne, cross-selling de soins, présence employé — "
                "<strong>10&nbsp;% ou 1&nbsp;500&nbsp;DH/mois</strong>."
            )
        else:
            visib = (
                "Présence sur la carte Coins Marocain. "
                "Commission de <strong>15&nbsp;%</strong> sur les réservations "
                "via la plateforme — aucun frais fixe."
            )
            digital = (
                "Calendrier, réservations directes, connexion au site — "
                "<strong>10&nbsp;% ou 1&nbsp;500&nbsp;DH/mois</strong>."
            )
        marketing = (
            "Site internet, réseaux sociaux et shooting photo/vidéo avec "
            "l'agence Doorway — seulement si vous voulez aller plus loin."
        )
        return {
            "visibility": self._cm_intro_pillar_html(
                "Visibilité Coins Marocain", visib
            ),
            "digital": self._cm_intro_pillar_html(
                "Channel Manager / digitalisation", digital
            ),
            "marketing": self._cm_intro_pillar_html(
                "Marketing (optionnel)", marketing, last=True
            ),
        }

    def _cm_intro_html_path(self):
        path = os.path.join(
            get_module_path("coins_marocain_partenariats"),
            "data",
            "emails",
            "email_introduction_entente.html",
        )
        if not os.path.isfile(path):
            raise UserError(_("Fichier HTML du courrier de bonjour introuvable."))
        return path

    def _cm_render_intro_entente_html(self):
        """Courrier de bonjour — présentation de l'entente (modèle réutilisable)."""
        self.ensure_one()
        html = open(self._cm_intro_html_path(), encoding="utf-8").read()
        contact = self._cm_intro_contact_firstname()
        etab = self._cm_intro_etablissement()
        sender = "Zakaria"
        blocks = self._cm_intro_offer_blocks()
        html = html.replace("{{CONTACT}}", str(escape(contact)))
        html = html.replace("{{ETABLISSEMENT}}", str(escape(etab)))
        html = html.replace("{{SENDER}}", str(escape(sender)))
        html = html.replace("{{ENTENTE_URL}}", str(escape(self._cm_entente_public_url())))
        html = html.replace("{{VISIBILITY_BLOCK}}", blocks["visibility"])
        html = html.replace("{{DIGITAL_BLOCK}}", blocks["digital"])
        html = html.replace("{{MARKETING_BLOCK}}", blocks["marketing"])
        return html

    def _cm_intro_subject(self):
        self.ensure_one()
        etab = self._cm_intro_etablissement()
        return _("Coins Marocain × %s — présentation de l'entente de partenariat") % etab

    def action_send_coins_intro_entente(self):
        """Ouvre le compositeur (brouillon) — n'envoie pas automatiquement."""
        self.ensure_one()
        email = self._coins_partner_email()
        if not email:
            raise UserError(
                _("Impossible d'envoyer — ajoutez l'email du contact sur la fiche.")
            )
        template = self.env.ref(
            "coins_marocain_partenariats.mail_template_cm_intro_entente",
            raise_if_not_found=False,
        )
        if not template:
            template = self.env["mail.template"].sudo().search(
                [
                    ("model", "=", "crm.lead"),
                    ("name", "ilike", "courrier de bonjour"),
                ],
                limit=1,
            )
        partner = self._coins_ensure_partner()
        outgoing = self._coins_zakaria_outgoing()
        ctx = {
            "default_model": "crm.lead",
            "default_res_ids": self.ids,
            "default_composition_mode": "comment",
            "default_partner_ids": partner.ids,
            "default_email_from": outgoing["email_from"],
            "default_mail_server_id": outgoing["mail_server_id"],
            "mail_post_autofollow": True,
            "active_model": "crm.lead",
            "active_ids": self.ids,
            "active_id": self.id,
        }
        if template:
            ctx.update(
                {
                    "default_template_id": template.id,
                    "default_use_template": True,
                }
            )
        try:
            rendered = self._cm_render_intro_entente_html()
        except (OSError, UserError):
            rendered = ""
        if rendered:
            ctx.update(
                {
                    "default_subject": self._cm_intro_subject(),
                    "default_body": Markup(rendered),
                }
            )
        return {
            "type": "ir.actions.act_window",
            "name": _("Courrier de bonjour"),
            "res_model": "mail.compose.message",
            "view_mode": "form",
            "target": "new",
            "context": ctx,
        }


    CM_PROSPECT_VIDEO = (
        "https://coinsmarocain.com/assets/video/prospection-hotels-riads.html"
    )
    CM_PROSPECT_POSTER = (
        "https://coinsmarocain.com/assets/video/prospection-hotels-riads.jpg"
    )
    CM_BOOKING_URL = "https://intellixcrm.com/intellix/rdv/zakaria"

    def _cm_followup_video(self):
        """URL + poster email-safe (page HTML, YouTube/Vimeo thumbnail)."""
        self.ensure_one()
        videos = self.coins_property_id.fiche_video_ids.filtered(
            lambda v: v.statut == "publiee" and (v.video_url or "").strip()
        )
        url = (
            (videos[:1].video_url or "").strip()
            if videos
            else self.CM_PROSPECT_VIDEO
        )
        if (url or "").rstrip("/").endswith("prospection-hotels-riads.mp4"):
            url = self.CM_PROSPECT_VIDEO
        poster = self.CM_PROSPECT_POSTER
        yt = re.search(
            r"(?:youtube\.com/watch\?v=|youtu\.be/|youtube\.com/embed/)([\w-]{6,})",
            url or "",
        )
        if yt:
            poster = "https://img.youtube.com/vi/%s/hqdefault.jpg" % yt.group(1)
        vm = re.search(r"vimeo\.com/(?:video/)?(\d+)", url or "")
        if vm:
            poster = "https://vumbnail.com/%s.jpg" % vm.group(1)
        return {"url": url, "poster": poster}

    def _cm_followup_confirm_url(self):
        """Fiche partenaire tokenisée, sinon mailto Karine Barmaki."""
        self.ensure_one()
        lien = (self.coins_partner_lien or "").strip()
        if lien:
            return lien
        etab = self.coins_etablissement or self.name or "Coins Marocain"
        return "mailto:karine@agencedoorway.com?subject=%s" % quote(
            "Confirmation partenariat — %s" % etab
        )

    def _cm_followup_booking_url(self):
        return (
            self.env["ir.config_parameter"]
            .sudo()
            .get_param(
                "doorway_agents_dashboard.booking_demo_url",
                self.CM_BOOKING_URL,
            )
            or self.CM_BOOKING_URL
        )

    @api.depends("coins_property_id", "coins_property_id.portal_token")
    def _compute_coins_partner_lien(self):
        base = (
            self.env["ir.config_parameter"]
            .sudo()
            .get_param(
                "coins_marocain.partenaire_base_url",
                "https://coinsmarocain.com",
            )
            .rstrip("/")
        )
        for lead in self:
            token = ""
            if lead.coins_property_id:
                token = (lead.coins_property_id.portal_token or "").strip()
            lead.coins_partner_lien = (
                "%s/partenaire/%s" % (base, token) if token else "%s/partenaire" % base
            )

    def _coins_onboarding_kind(self):
        self.ensure_one()
        cat = self.coins_categorie_etab or self.coins_type_partenaire
        if cat in ("restauration",):
            return "restaurant"
        if cat in ("spa", "bien_etre"):
            return "spa"
        return "hebergement"

    def _coins_category_commands_for_kind(self, kind):
        code = {
            "restaurant": "route_gourmande",
            "spa": "bien_etre",
            "hebergement": "hebergement",
        }.get(kind or "hebergement", "hebergement")
        cat = self.env["coins.property.category"].sudo().search(
            [("code", "=", code)], limit=1
        )
        return [(4, cat.id)] if cat else []

    def _coins_property_type(self, kind):
        return {
            "restaurant": "other",
            "spa": "pool_hammam",
            "hebergement": "riad",
        }.get(kind, "riad")

    def _coins_ville_label(self):
        self.ensure_one()
        labels = dict(self._fields["coins_ville"].selection or [])
        if self.coins_ville == "autre":
            return (self.coins_ville_autre or "").strip() or "Marrakech"
        return labels.get(self.coins_ville) or "Marrakech"

    def _coins_ensure_partner_property(self):
        """Trouve ou crée le coins.property, génère le token au premier clic."""
        self.ensure_one()
        name = (
            self.coins_etablissement
            or self.name
            or self.contact_name
            or self.partner_name
            or ""
        ).strip()
        if not name:
            raise UserError(_("Indiquez l’établissement avant d’envoyer le lien."))
        prop = self.coins_property_id
        if not prop:
            Property = self.env["coins.property"].sudo()
            prop = Property.search([("name", "=ilike", name)], limit=1)
            if not prop:
                kind = self._coins_onboarding_kind()
                create_vals = {
                    "name": name,
                    "state": "negotiating",
                    "property_type": self._coins_property_type(kind),
                    "onboarding_kind": kind,
                    "onboarding_status": "brouillon",
                    "city": self._coins_ville_label(),
                    "district": (self.coins_quartier or "").strip() or False,
                    "owner_id": self.partner_id.id or False,
                    "onboarding_contact_name": (
                        self.contact_name or self.partner_name or ""
                    ).strip()
                    or False,
                    "onboarding_phone": (
                        self.coins_whatsapp or self.phone or ""
                    ).strip()
                    or False,
                    "onboarding_email": (self.email_from or "").strip() or False,
                    "location_chambre_unite": kind == "hebergement",
                }
                cat_cmds = self._coins_category_commands_for_kind(kind)
                if cat_cmds:
                    create_vals["category_ids"] = cat_cmds
                prop = Property.create(create_vals)
            self.coins_property_id = prop.id
        prop._ensure_portal_token()
        return prop

    def _coins_wa_digits(self):
        self.ensure_one()
        raw = (self.coins_whatsapp or self.phone or "").strip()
        digits = re.sub(r"\D", "", raw)
        if digits.startswith("00"):
            digits = digits[2:]
        if digits.startswith("0") and len(digits) == 10:
            digits = "212" + digits[1:]
        return digits

    def _coins_partner_invite_text(self):
        self.ensure_one()
        prop = self._coins_ensure_partner_property()
        lien = prop._partner_public_url()
        prenom = (self.contact_name or "").strip() or "bonjour"
        lieu = prop.name
        return (
            "Bonjour %s,\n\n"
            "Coins Marocain vous invite à compléter la fiche de %s. "
            "Voici votre lien personnel — ne le transmettez pas :\n%s\n\n"
            "À bientôt,\nZakaria — Coins Marocain"
        ) % (prenom, lieu, lien)

    def action_coins_envoyer_lien_whatsapp(self):
        self.ensure_one()
        digits = self._coins_wa_digits()
        if not digits:
            raise UserError(
                _("Renseignez le téléphone ou WhatsApp sur la fiche avant d’envoyer.")
            )
        prop = self._coins_ensure_partner_property()
        text = self._coins_partner_invite_text()
        wa = "https://wa.me/%s?text=%s" % (digits, quote(text))
        prop.write({"onboarding_status": "lien_envoye"})
        self.message_post(
            body=_("Lien partenaire ouvert dans WhatsApp : %s") % prop._partner_public_url()
        )
        return {
            "type": "ir.actions.act_url",
            "url": wa,
            "target": "new",
        }

    def action_coins_envoyer_lien_email(self):
        self.ensure_one()
        email = (self.email_from or "").strip()
        if not email:
            raise UserError(_("Renseignez l’email sur la fiche avant d’envoyer."))
        prop = self._coins_ensure_partner_property()
        template = self.env.ref(
            "coins_marocain_partenariats.mail_template_lien_partenaire_onboarding",
            raise_if_not_found=False,
        )
        if not template:
            raise UserError(_("Modèle d’email du lien partenaire introuvable."))
        outgoing = self._coins_zakaria_outgoing()
        email_values = {
            "email_to": email,
            "auto_delete": False,
            "email_from": outgoing["email_from"],
        }
        if outgoing.get("mail_server_id"):
            email_values["mail_server_id"] = outgoing["mail_server_id"]
        template.send_mail(
            self.id,
            force_send=True,
            raise_exception=True,
            email_values=email_values,
        )
        prop.write({"onboarding_status": "lien_envoye"})
        self.message_post(
            body=_("Lien partenaire envoyé par email à %s — %s")
            % (email, prop._partner_public_url())
        )
        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": _("Lien envoyé"),
                "message": _("Email envoyé à %s") % email,
                "type": "success",
                "sticky": False,
            },
        }

    def action_coins_creer_entente(self):
        self.ensure_one()
        if self.coins_entente_id:
            return {
                "type": "ir.actions.act_window",
                "res_model": "coins.entente",
                "res_id": self.coins_entente_id.id,
                "view_mode": "form",
                "target": "current",
            }
        quote = self.coins_sale_order_id
        if quote and quote.state in ("draft", "sent"):
            return {
                "type": "ir.actions.act_window",
                "res_model": "sale.order",
                "res_id": quote.id,
                "view_mode": "form",
                "target": "current",
            }
        if quote and quote.state == "sale":
            quote._coins_sync_entente_from_quote()
            if self.coins_entente_id:
                return {
                    "type": "ir.actions.act_window",
                    "res_model": "coins.entente",
                    "res_id": self.coins_entente_id.id,
                    "view_mode": "form",
                    "target": "current",
                }
        if not (self.coins_etablissement or self.partner_name or self.name):
            raise UserError(_("Indique l’établissement avant de créer l’entente."))
        return {
            "type": "ir.actions.act_window",
            "name": _("Choisir le modèle de devis"),
            "res_model": "coins.devis.entente.wizard",
            "view_mode": "form",
            "target": "new",
            "context": {
                "default_lead_id": self.id,
                "default_template_id": self._coins_recommended_template_id(),
            },
        }

    @api.model
    def _coins_quebec_team(self):
        for xmlid in (
            "coins_quebec.crm_team_cq_partenariats",
            "doorway_hiba_qualif.crm_team_coins_quebec",
        ):
            team = self.env.ref(xmlid, raise_if_not_found=False)
            if team:
                return team
        return self.env["crm.team"].search(
            ["|", ("name", "ilike", "Coins Québec"), ("name", "ilike", "Coins Quebec")],
            limit=1,
        )

    def _coins_is_quebec_market(self):
        self.ensure_one()
        name = (self.team_id.name or "").lower()
        if "québec" in name or "quebec" in name:
            return True
        team_cq = self._coins_quebec_team()
        return bool(team_cq and self.team_id == team_cq)

    def _coins_recommended_template_id(self):
        self.ensure_one()
        Template = self.env["sale.order.template"]
        quebec = self._coins_is_quebec_market()
        if self.coins_xsell_site_web or self.coins_xsell_reseaux:
            code = (
                "coins_quebec_presence_complete" if quebec else "coins_presence_complete"
            )
        elif self.coins_interet_channel_manager:
            code = "coins_quebec_digitalisation" if quebec else "coins_digitalisation"
        else:
            code = "coins_quebec_visibilite" if quebec else "coins_visibilite"
        tmpl = Template.search([("ix_template_code", "=", code)], limit=1)
        return tmpl.id or False

    def _coins_ensure_partner(self):
        self.ensure_one()
        email = self._coins_partner_email()
        name = self._coins_partner_display_name() or _("Partenaire")
        if self.partner_id:
            vals = {}
            if email and not (self.partner_id.email or "").strip():
                vals["email"] = email
            if not self.partner_id.user_id:
                vals["user_id"] = self.user_id.id or self.env.user.id
            if vals:
                self.partner_id.sudo().write(vals)
            return self.partner_id
        partner = self.env["res.partner"].sudo().create(
            {
                "name": name,
                "email": email or False,
                "phone": self.phone or self.coins_whatsapp or False,
                "user_id": self.user_id.id or self.env.user.id,
            }
        )
        self.partner_id = partner.id
        return partner

    @api.model
    def _coins_align_partnership_stages(self):
        """Étapes opérationnelles distinctes — ne pas fusionner les colonnes."""
        team = self.env.ref(
            "coins_marocain_partenariats.crm_team_coins_marocain",
            raise_if_not_found=False,
        )
        if not team:
            return True

        def stage(xmlid):
            return self.env.ref(
                "coins_marocain_partenariats.%s" % xmlid,
                raise_if_not_found=False,
            )

        specs = (
            ("crm_stage_cm_nouveau", "Nouveau", 10, False, False),
            ("crm_stage_cm_contacte", "Contacté", 20, False, False),
            ("crm_stage_cm_visite", "Attribué", 30, False, False),
            ("crm_stage_cm_relance", "Relance", 40, False, False),
            ("crm_stage_cm_signe", "Gagné", 50, False, True),
            ("crm_stage_cm_perdu", "Perdu", 60, True, False),
        )
        for xid, name, seq, fold, won in specs:
            rec = stage(xid)
            if rec:
                rec.write({
                    "name": name,
                    "sequence": seq,
                    "fold": fold,
                    "is_won": won,
                    "team_ids": [(4, team.id)],
                })
        leftover = stage("crm_stage_cm_voyageurs")
        if leftover:
            leftover.write({"team_ids": [(3, team.id)], "fold": True})
        leftover_entente = stage("crm_stage_cm_entente")
        if leftover_entente:
            leftover_entente.write({"team_ids": [(3, team.id)], "fold": True})
        self._coins_align_voyageur_stages()
        self._coins_merge_global_nouveau(team, stage("crm_stage_cm_nouveau"))
        self._coins_exclude_shop_scrape(team)
        self._coins_backfill_partnership_defaults(team)
        self._coins_put_voyageurs_on_their_team()
        self._coins_split_grouped_card_scan()
        self._coins_unify_existing_to_contacte()
        from odoo.addons.coins_marocain_partenariats.hooks import (
            setup_coins_pipeline_users,
            setup_zakaria_coins_pipeline,
        )
        setup_zakaria_coins_pipeline(self.env)
        setup_coins_pipeline_users(self.env)
        self._coins_put_voyageurs_on_their_team()
        return True

    @api.model
    def _coins_align_voyageur_stages(self):
        """Colonnes Voyageurs = Nouveau → Contacté → Attribué → Relance → Gagné."""
        voy_team = self.env.ref(
            "coins_marocain_partenariats.crm_team_coins_voyageurs",
            raise_if_not_found=False,
        )
        if not voy_team:
            return True

        def stage(xmlid):
            return self.env.ref(
                "coins_marocain_partenariats.%s" % xmlid,
                raise_if_not_found=False,
            )

        relance = stage("crm_stage_voy_relance")
        if not relance:
            relance = self.env["crm.stage"].sudo().create(
                {
                    "name": "Relance",
                    "sequence": 40,
                    "fold": False,
                    "is_won": False,
                    "team_ids": [(4, voy_team.id)],
                }
            )
            self.env["ir.model.data"].sudo().create(
                {
                    "module": "coins_marocain_partenariats",
                    "name": "crm_stage_voy_relance",
                    "model": "crm.stage",
                    "res_id": relance.id,
                    "noupdate": True,
                }
            )
        specs = (
            ("crm_stage_voy_nouveau", "Nouveau", 10, False, False),
            ("crm_stage_voy_qualifie", "Contacté", 20, False, False),
            ("crm_stage_voy_chaud", "Attribué", 30, False, False),
            ("crm_stage_voy_relance", "Relance", 40, False, False),
            ("crm_stage_voy_reserve", "Gagné", 50, False, True),
            ("crm_stage_voy_perdu", "Perdu", 60, True, False),
        )
        for xid, name, seq, fold, won in specs:
            rec = stage(xid)
            if rec:
                rec.write(
                    {
                        "name": name,
                        "sequence": seq,
                        "fold": fold,
                        "is_won": won,
                        "team_ids": [(4, voy_team.id)],
                    }
                )
        incomplet = stage("crm_stage_voy_incomplet")
        if incomplet:
            incomplet.write({"team_ids": [(3, voy_team.id)], "fold": True})
        return True

    @api.model
    def _coins_unify_existing_to_contacte(self):
        """Une fois : fiches déjà dans le pipeline → Contacté (sauf Gagné / Perdu)."""
        icp = self.env["ir.config_parameter"].sudo()
        param = "coins_marocain_partenariats.pipeline_5col_contacte_20260829"
        if icp.get_param(param):
            return True
        Lead = self.sudo()
        team = self.env.ref(
            "coins_marocain_partenariats.crm_team_coins_marocain",
            raise_if_not_found=False,
        )
        voy_team = self.env.ref(
            "coins_marocain_partenariats.crm_team_coins_voyageurs",
            raise_if_not_found=False,
        )
        cm_contacte = self.env.ref(
            "coins_marocain_partenariats.crm_stage_cm_contacte",
            raise_if_not_found=False,
        )
        cm_won = self.env.ref(
            "coins_marocain_partenariats.crm_stage_cm_signe",
            raise_if_not_found=False,
        )
        cm_lost = self.env.ref(
            "coins_marocain_partenariats.crm_stage_cm_perdu",
            raise_if_not_found=False,
        )
        if team and cm_contacte:
            skip = [s.id for s in (cm_won, cm_lost) if s]
            domain = [
                ("team_id", "=", team.id),
                ("coins_fiche_type", "=", "partenariat"),
                ("active", "=", True),
            ]
            if skip:
                domain.append(("stage_id", "not in", skip))
            recs = Lead.search(domain)
            if recs:
                recs.write({"stage_id": cm_contacte.id})
        voy_contacte = self.env.ref(
            "coins_marocain_partenariats.crm_stage_voy_qualifie",
            raise_if_not_found=False,
        )
        voy_won = self.env.ref(
            "coins_marocain_partenariats.crm_stage_voy_reserve",
            raise_if_not_found=False,
        )
        voy_lost = self.env.ref(
            "coins_marocain_partenariats.crm_stage_voy_perdu",
            raise_if_not_found=False,
        )
        voy_incomplet = self.env.ref(
            "coins_marocain_partenariats.crm_stage_voy_incomplet",
            raise_if_not_found=False,
        )
        if voy_team and voy_contacte:
            skip = [s.id for s in (voy_won, voy_lost, voy_incomplet) if s]
            domain = [
                ("team_id", "=", voy_team.id),
                ("coins_fiche_type", "=", "voyageur"),
                ("active", "=", True),
            ]
            if skip:
                domain.append(("stage_id", "not in", skip))
            recs = Lead.search(domain)
            if recs:
                recs.write({"stage_id": voy_contacte.id})
        icp.set_param(param, "1")
        return True

    @api.model
    def _coins_merge_global_nouveau(self, team, cm_new):
        """Les deux « Nouveau » ont le même sens : fusionner vers l'étape CM."""
        global_new = self.env.ref("crm.stage_lead1", raise_if_not_found=False)
        if not team or not cm_new or not global_new or global_new == cm_new:
            return True
        extras = self.sudo().with_context(active_test=False).search(
            [
                ("team_id", "=", team.id),
                ("coins_fiche_type", "=", "partenariat"),
                ("stage_id", "=", global_new.id),
            ]
        )
        if extras:
            extras.write({"stage_id": cm_new.id})
        return True

    @api.model
    def _coins_exclude_shop_scrape(self, team):
        """para universal shop : Places l'a mis en spa, ce n'est pas un partenaire."""
        if not team:
            return True
        shop = self.sudo().with_context(active_test=False).search(
            [
                ("team_id", "=", team.id),
                ("coins_fiche_type", "=", "partenariat"),
                "|",
                ("name", "=ilike", "para universal shop"),
                ("coins_etablissement", "=ilike", "para universal shop"),
            ],
            limit=1,
        )
        if not shop:
            return True
        note = (
            "Hors pipeline partenariats : commerce / parapharmacie. "
            "Google Places l’a renvoyé dans une recherche spa/massage "
            "(Médina Nord / Bab Doukala). Pas un hôtel, resto ni spa."
        )
        # SQL : type=lead déclenche une réaffectation reno vers l'équipe Rénovation.
        self.env.cr.execute(
            """
            UPDATE crm_lead SET
                team_id = %s,
                type = 'opportunity',
                active = false,
                coins_type_partenaire = 'autre',
                coins_categorie_etab = NULL,
                coins_commission_pct = 0
            WHERE id = %s
            """,
            [team.id, shop.id],
        )
        shop.invalidate_recordset()
        if note not in (shop.coins_note or ""):
            shop.coins_note = (
                ((shop.coins_note + "\n") if shop.coins_note else "") + note
            )
            shop.message_post(body=note)
        return True

    @api.model
    def _coins_backfill_partnership_defaults(self, team):
        if not team:
            return True
        Lead = self.sudo()
        manuals = Lead.search(
            [
                ("team_id", "=", team.id),
                ("coins_fiche_type", "=", "partenariat"),
                ("coins_scrape_source", "=", False),
            ]
        )
        if manuals:
            manuals.write({"coins_scrape_source": "manuel"})
        empty_comm = Lead.search(
            [
                ("team_id", "=", team.id),
                ("coins_fiche_type", "=", "partenariat"),
                ("type", "=", "opportunity"),
                ("active", "=", True),
                ("coins_commission_pct", "in", (False, 0, 0.0)),
            ]
        )
        for lead in empty_comm:
            cat = lead.coins_categorie_etab or lead.coins_type_partenaire
            lead.coins_commission_pct = 12.5 if cat == "hebergement" else 15.0
        return True

    @api.model
    def _coins_kanban_team_id(self, domain=None):
        """Équipe du kanban : contexte action, coins_pipeline, ou domaine."""
        pipeline = self.env.context.get("coins_pipeline")
        if pipeline == "partenariat":
            team = self.env.ref(
                "coins_marocain_partenariats.crm_team_coins_marocain",
                raise_if_not_found=False,
            )
            if team:
                return team.id
        if pipeline == "voyageur":
            team = self.env.ref(
                "coins_marocain_partenariats.crm_team_coins_voyageurs",
                raise_if_not_found=False,
            )
            if team:
                return team.id
        raw = self.env.context.get("default_team_id") or self.env.context.get(
            "renovation_active_pipeline_team_id"
        )
        try:
            if raw:
                return int(raw)
        except (TypeError, ValueError):
            pass
        for leaf in domain or []:
            if not isinstance(leaf, (list, tuple)) or len(leaf) < 3:
                continue
            if leaf[0] != "team_id":
                continue
            if leaf[1] == "=" and leaf[2]:
                try:
                    return int(leaf[2])
                except (TypeError, ValueError):
                    return leaf[2]
            if leaf[1] == "in" and len(leaf[2] or []) == 1:
                try:
                    return int(leaf[2][0])
                except (TypeError, ValueError):
                    return leaf[2][0]
        return False

    @api.model
    def _read_group_stage_ids(self, stages, domain):
        """Colonnes CM/voyageurs = étapes de l'équipe (renommées incluses).

        Un « Nouveau » global CRM ou une étape hors équipe casse le drag :
        la carte ne peut pas changer de stage_id.
        """
        team = self.env.ref(
            "coins_marocain_partenariats.crm_team_coins_marocain",
            raise_if_not_found=False,
        )
        team_voy = self.env.ref(
            "coins_marocain_partenariats.crm_team_coins_voyageurs",
            raise_if_not_found=False,
        )
        ctx_team = self._coins_kanban_team_id(domain)
        for dedicated_team in (team, team_voy):
            if dedicated_team and ctx_team == dedicated_team.id:
                dedicated = self.env["crm.stage"].search(
                    [("team_ids", "in", dedicated_team.id)],
                    order="sequence, id",
                )
                if dedicated:
                    return dedicated
        return super()._read_group_stage_ids(stages, domain)

    @api.model
    def _coins_put_voyageurs_on_their_team(self):
        voy_team = self.env.ref(
            "coins_marocain_partenariats.crm_team_coins_voyageurs",
            raise_if_not_found=False,
        )
        voy_new = self.env.ref(
            "coins_marocain_partenariats.crm_stage_voy_nouveau",
            raise_if_not_found=False,
        )
        voy_hot = self.env.ref(
            "coins_marocain_partenariats.crm_stage_voy_chaud",
            raise_if_not_found=False,
        )
        if not voy_team:
            return True
        leads = self.sudo().search(
            [
                ("coins_fiche_type", "=", "voyageur"),
                ("team_id", "!=", voy_team.id),
            ]
        )
        voy_stage_ids = self.env["crm.stage"].sudo().search(
            [("team_ids", "in", voy_team.id)]
        ).ids
        for lead in leads:
            vals = {"team_id": voy_team.id}
            if lead.stage_id.id not in voy_stage_ids:
                phone = (
                    (lead.coins_whatsapp or "").strip()
                    or (lead.phone or "").strip()
                )
                if (
                    phone
                    and voy_hot
                    and (lead.coins_urgence or "HOT" in (lead.name or ""))
                ):
                    vals["stage_id"] = voy_hot.id
                elif voy_new:
                    vals["stage_id"] = voy_new.id
            try:
                lead.write(vals)
            except Exception:
                lead.with_context(mail_notrack=True).sudo().write(
                    {"team_id": voy_team.id}
                )
        return True

    @api.model
    def _coins_split_grouped_card_scan(self):
        """Sépare le scan carte multi-restaurants sans supprimer la fiche d'origine."""
        Lead = self.sudo()
        parent = Lead.search(
            [("name", "ilike", "Café de France, Le Rôti")],
            limit=1,
        )
        if not parent:
            return True
        places = (
            "Café de France",
            "Le Rôti d'Or",
            "Le Marrakchi",
            "Le Salama",
            "La Maison Toubkal",
            "KENNARIA",
        )
        created = []
        for place in places:
            exists = Lead.search(
                [
                    ("id", "!=", parent.id),
                    ("team_id", "=", parent.team_id.id),
                    "|",
                    ("coins_etablissement", "=", place),
                    ("name", "=", place),
                ],
                limit=1,
            )
            if exists:
                continue
            try:
                child = Lead.create(
                    {
                        "name": place,
                        "coins_etablissement": place,
                        "coins_fiche_type": "partenariat",
                        "type": "opportunity",
                        "team_id": parent.team_id.id,
                        "stage_id": parent.stage_id.id,
                        "user_id": parent.user_id.id,
                        "phone": parent.phone,
                        "coins_whatsapp": parent.coins_whatsapp,
                        "coins_ville": parent.coins_ville or "marrakech",
                        "description": (
                            "Séparée de la fiche groupée (scan carte de visite #%s). "
                            "La fiche d'origine est conservée — e-mail du scan : %s."
                        )
                        % (parent.id, parent.email_from or "—"),
                    }
                )
            except Exception:
                continue
            created.append(child.name)
        note = (
            "Scan carte de visite : plusieurs restaurants dans une seule fiche. "
            "Fiche d'origine conservée (historique). "
        )
        if created:
            note += "Fiches séparées : %s." % ", ".join(created)
        else:
            note += "Les fiches individuelles existent déjà."
        if parent.coins_note and "Scan carte de visite" in (parent.coins_note or ""):
            return True
        parent.coins_note = ((parent.coins_note + "\n") if parent.coins_note else "") + note
        parent.message_post(body=note)
        creator = Lead.search(
            [("name", "ilike", "Content Creator Collaboration")],
            limit=1,
        )
        if creator and "Collaboration influenceur" not in (creator.coins_note or ""):
            creator.coins_note = (
                (creator.coins_note + "\n" if creator.coins_note else "")
                + "Collaboration influenceur (Ivana Pejanovic) — une seule fiche, pas un établissement à scinder."
            )
        return True
