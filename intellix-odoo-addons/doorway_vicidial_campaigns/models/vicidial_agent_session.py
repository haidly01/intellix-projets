# -*- coding: utf-8 -*-
import datetime
import logging
import re
from datetime import timedelta

from odoo import _, api, fields, models
from odoo.exceptions import UserError
from odoo.tools import plaintext2html

_logger = logging.getLogger(__name__)

# Agents France B2C — une seule campagne / poste WebRTC fixe
_LEILA_VICIDIAL_LOGIN = "leiladaouadi"
_ZAKARIA_VICIDIAL_LOGIN = "zakaria"
_FRB2C_ONLY_CAMPAIGN = "DW_FRB2C"
_LEILA_ONLY_CAMPAIGN = _FRB2C_ONLY_CAMPAIGN


class VicidialAgentSession(models.Model):
    _name = "doorway.vicidial.agent.session"
    _description = "Session de travail agent VICIdial"
    _order = "date_start desc"

    user_id = fields.Many2one("res.users", required=True, index=True)
    agent_user_id = fields.Many2one("doorway.campaign.agent.user", string="Agent VICIdial")
    employee_id = fields.Many2one(
        "hr.employee",
        related="user_id.employee_id",
        store=True,
        readonly=True,
    )
    campaign_id = fields.Many2one("doorway.campaign", string="Campagne", index=True)
    vicidial_user = fields.Char(string="Login VICIdial")
    vicidial_session_name = fields.Char(string="Session VICIdial (heartbeat)")
    vicidial_campaign_id = fields.Char(related="campaign_id.vicidial_campaign_id")

    state = fields.Selection(
        [
            ("draft", "Brouillon"),
            ("active", "En cours"),
            ("paused", "En pause"),
            ("ended", "Terminée"),
        ],
        default="draft",
        required=True,
        index=True,
    )
    date_start = fields.Datetime(string="Début session")
    date_end = fields.Datetime(string="Fin session")
    last_pause_start = fields.Datetime(string="Début pause")
    total_pause_seconds = fields.Integer(default=0)

    nb_appels = fields.Integer(string="Appels", default=0)
    nb_qualifies = fields.Integer(string="Qualifiés", default=0)
    nb_rappels = fields.Integer(string="Rappels planifiés", default=0)
    outbound_group_alias_id = fields.Char(string="Alias CID sortant")
    duree_travail_secondes = fields.Integer(
        string="Durée travail (s)", compute="_compute_duree", store=True
    )

    @api.depends("date_start", "date_end", "total_pause_seconds", "state")
    def _compute_duree(self):
        now = fields.Datetime.now()
        for rec in self:
            if not rec.date_start:
                rec.duree_travail_secondes = 0
                continue
            end = rec.date_end or (now if rec.state in ("active", "paused") else now)
            total = int((end - rec.date_start).total_seconds())
            rec.duree_travail_secondes = max(total - (rec.total_pause_seconds or 0), 0)

    @api.model
    def _get_agent_users(self, user=None):
        user = (user or self.env.user).sudo()
        return self.env["doorway.campaign.agent.user"].search(
            [("user_id", "=", user.id), ("active", "=", True)],
            order="id asc",
        )

    @api.model
    def _get_agent_user(self, user=None, campaign=None):
        agents = self._get_agent_users(user)
        if campaign:
            matched = agents & campaign.human_agent_ids
            if matched:
                return matched[0]
        return agents[:1]

    @api.model
    def _is_leila_agent(self, user=None):
        user = (user or self.env.user).sudo()
        return any(
            a.vicidial_user == _LEILA_VICIDIAL_LOGIN
            for a in self._get_agent_users(user)
        )

    @api.model
    def _is_zakaria_agent(self, user=None):
        user = (user or self.env.user).sudo()
        return any(
            a.vicidial_user == _ZAKARIA_VICIDIAL_LOGIN
            for a in self._get_agent_users(user)
        )

    @api.model
    def _is_frb2c_only_agent(self, user=None):
        # Leila moved to France B2B (DW_FRB2B): assignment-driven access, no FRB2C lock.
        return self._is_zakaria_agent(user)

    @api.model
    def _frb2c_only_campaign_domain(self):
        return [
            ("vicidial_campaign_id", "=", _FRB2C_ONLY_CAMPAIGN),
            ("state", "in", ("ready", "active")),
            ("campaign_mode", "in", ("human_agent", "mixed")),
        ]

    @api.model
    def get_available_campaigns(self, user=None):
        user = (user or self.env.user).sudo()
        if self._is_frb2c_only_agent(user):
            return self.env["doorway.campaign"].search(
                self._frb2c_only_campaign_domain(),
                order="name asc",
            )
        domain = [
            ("state", "in", ("ready", "active")),
            ("campaign_mode", "in", ("human_agent", "mixed")),
        ]
        agents = self._get_agent_users(user)
        if agents:
            assigned = self.env["doorway.campaign"].search(
                domain + [("human_agent_ids", "in", agents.ids)],
                order="name asc",
            )
            if assigned:
                return assigned
        return self.env["doorway.campaign"].search(domain, order="name asc")

    @api.model
    def get_active_session(self, user=None):
        user = (user or self.env.user).sudo()
        return self.search(
            [("user_id", "=", user.id), ("state", "in", ("active", "paused"))],
            limit=1,
            order="date_start desc",
        )

    @api.model
    def _end_open_sessions(self, user=None):
        """Clôture toutes les sessions actives/pause (évite les doublons bloquants)."""
        user = (user or self.env.user).sudo()
        open_sessions = self.search(
            [("user_id", "=", user.id), ("state", "in", ("active", "paused"))],
            order="date_start asc",
        )
        for session in open_sessions:
            session.action_end_session()
        return len(open_sessions)

    @api.model
    def _default_outbound_group_alias_for_campaign(self, campaign):
        """Alias CID par défaut selon la campagne (QC / FR / B2B Twilio)."""
        vicidial_cid = ((campaign.vicidial_campaign_id if campaign else "") or "").upper()
        if not vicidial_cid:
            return ""
        if vicidial_cid == "DW_FRB2B":
            return "TWILIO_FR_CLI"
        if "QC" in vicidial_cid or vicidial_cid == "DW_QCB2C":
            return "DOOR_QC_CLI"
        if "FR" in vicidial_cid or vicidial_cid == "DW_FRB2C":
            return "DOOR_FR_CLI"
        return ""

    @api.model
    def get_workstation_data(self, light=False):
        user = self.env.user
        agent = self._get_agent_user(user)
        session = self.get_active_session(user)
        campaigns = self.get_available_campaigns(user)
        callbacks = self._get_callbacks(user)
        icp = self.env["ir.config_parameter"].sudo()
        from odoo.addons.doorway_vicidial_campaigns.services.vicidial_service import (
            VicidialService,
        )

        svc = VicidialService(self.env)
        agent_url = "%s/vicidial.php" % svc._agent_portal_base()
        vicidial_live = {}
        pause_alert = {}
        auto_pause_recovered = False
        vicidial_login = ""
        phone_extension = ""
        if session and session.vicidial_user:
            vicidial_login = session.vicidial_user
        elif agent:
            vicidial_login = agent.vicidial_user
        if vicidial_login:
            phone_extension = svc.get_agent_phone_extension(vicidial_login)
        webphone_registered = False
        vicidial_live = {}
        if vicidial_login:
            vicidial_live = svc.get_agent_live_status(vicidial_login)
            webphone_registered = svc.get_webphone_call_ready(
                vicidial_login, vicidial_live.get("conf_exten")
            )
            needs_vicidial_sync = (
                session
                and session.state == "active"
                and session.campaign_id.vicidial_campaign_id
                and (
                    not light
                    or not vicidial_live.get("logged_in")
                    or (vicidial_live.get("status") or "").upper() != "READY"
                )
            )
            if needs_vicidial_sync:
                sync = svc.sync_agent_ready_for_session(
                    vicidial_login,
                    session.campaign_id.vicidial_campaign_id,
                    session_name=session.vicidial_session_name,
                )
                pause_alert = sync.get("pause_alert") or {}
                auto_pause_recovered = bool(sync.get("auto_pause_recovered"))
                synced_name = (sync.get("session_name") or "").strip()
                if synced_name and synced_name != (session.vicidial_session_name or ""):
                    session.sudo().write({"vicidial_session_name": synced_name})
                vicidial_live = svc.get_agent_live_status(vicidial_login)
                webphone_registered = svc.get_webphone_call_ready(
                    vicidial_login, vicidial_live.get("conf_exten")
                )
            elif session and session.state == "active":
                pause_alert = svc.get_agent_pause_alert(
                    vicidial_login, odoo_session_active=True
                )
        return {
            "agent": {
                "id": agent.id if agent else False,
                "vicidial_user": agent.vicidial_user if agent else "",
                "full_name": agent.full_name if agent else user.name,
                "phone_extension": phone_extension,
            },
            "vicidial_live": vicidial_live,
            "webphone_registered": webphone_registered,
            "pause_alert": pause_alert,
            "auto_pause_recovered": auto_pause_recovered,
            "session": session._to_client_dict(vicidial_live) if session else False,
            "campaigns": [
                {
                    "id": c.id,
                    "name": c.name,
                    "vicidial_campaign_id": c.vicidial_campaign_id or "",
                    "state": c.state,
                    "hopper_count": (
                        svc.get_hopper_count(c.vicidial_campaign_id)
                        if c.vicidial_campaign_id
                        else 0
                    ),
                    "manual_dial": (
                        (
                            c.campaign_mode in ("human_agent", "mixed")
                            and (c.auto_dial_mode or "") not in ("progressive", "predictive")
                        )
                        or svc.is_manual_dial_campaign(
                            c.vicidial_campaign_id, c.auto_dial_mode
                        )
                    ),
                }
                for c in campaigns
            ],
            "callbacks": callbacks,
            "cid_aliases": svc.get_outbound_cid_aliases(
                (session.campaign_id.vicidial_campaign_id if session and session.campaign_id else "")
                or (campaigns[0].vicidial_campaign_id if campaigns else "")
            ),
            "vicidial_agent_url": agent_url,
            "phone": self._phone_config(agent),
            "stats_today": self._get_stats_today(user),
            "coaching": self.get_coaching_summary() if not light else {},
            "recent_calls": self.get_recent_calls(),
            "messaging": self._messaging_caps(),
            "qualification_options": self.env["crm.lead"].get_workstation_qualification_options(),
        }

    @api.model
    def _phone_config(self, agent):
        """Webphone ViciPhone intégré dans Odoo (micro navigateur)."""
        if not agent:
            return {"mode": "missing"}
        return {
            "mode": "webphone",
            "message": _(
                "Cliquez « Démarrer » puis autorisez le micro du navigateur. "
                "Le téléphone WebRTC se connecte automatiquement."
            ),
        }

    def _to_client_dict(self, vicidial_live=None):
        self.ensure_one()
        from odoo.addons.doorway_vicidial_campaigns.services.vicidial_service import (
            VicidialService,
        )

        svc = VicidialService(self.env)
        live = vicidial_live
        if live is None and self.vicidial_user:
            live = svc.get_agent_live_status(self.vicidial_user)
        live = live or {}
        return {
            "id": self.id,
            "state": self.state,
            "campaign_id": self.campaign_id.id,
            "campaign_name": self.campaign_id.name,
            "vicidial_campaign_id": self.vicidial_campaign_id or "",
            "date_start": fields.Datetime.to_string(self.date_start)
            if self.date_start
            else False,
            "nb_appels": self.nb_appels,
            "nb_qualifies": self.nb_qualifies,
            "nb_rappels": self.nb_rappels,
            "duree_travail_secondes": self.duree_travail_secondes,
            "vicidial_status": live.get("status") or "",
            "vicidial_ready": bool(live.get("ready")),
            "vicidial_webphone_url": self._webphone_url_for_session(live),
            "manual_dial": (
                (
                    self.campaign_id.campaign_mode in ("human_agent", "mixed")
                    and (self.campaign_id.auto_dial_mode or "") not in ("progressive", "predictive")
                )
                or svc.is_manual_dial_campaign(
                    self.campaign_id.vicidial_campaign_id,
                    self.campaign_id.auto_dial_mode,
                )
            ),
            "outbound_group_alias_id": self.outbound_group_alias_id or "",
            "manual_dial_hint": self._manual_dial_hint(),
        }

    def _manual_dial_hint(self):
        self.ensure_one()
        country = self.campaign_id._phone_import_country()
        if country == "CA":
            return _("Ex. 5145551234 ou 4385551234 (sans +1)")
        if country in ("ES", "ESP", "SPAIN"):
            return _("Ex. 612345678 (sans +34)")
        return _("Ex. 0478820581 ou 0612345678 (sans +33). Test audio WebRTC : 86028999")

    def _webphone_url_for_session(self, vicidial_live=None):
        self.ensure_one()
        if not self.vicidial_user or self.state not in ("active", "paused"):
            return ""
        from odoo.addons.doorway_vicidial_campaigns.services.vicidial_service import (
            VicidialService,
        )

        live = vicidial_live or {}
        return VicidialService(self.env).build_webphone_embed_url(
            self.vicidial_user,
            self.campaign_id.vicidial_campaign_id,
            conf_exten=live.get("conf_exten"),
        )

    @api.model
    def _get_callbacks(self, user):
        Activity = self.env["mail.activity"].sudo()
        today = fields.Date.today()
        end = today + timedelta(days=7)
        activities = Activity.search(
            [
                ("user_id", "=", user.id),
                ("res_model", "=", "crm.lead"),
                ("date_deadline", ">=", today),
                ("date_deadline", "<=", end),
            ],
            order="date_deadline asc",
            limit=50,
        )
        callbacks = []
        for act in activities:
            lead = self.env["crm.lead"].browse(act.res_id)
            callbacks.append(
                {
                    "id": act.id,
                    "date": fields.Date.to_string(act.date_deadline),
                    "summary": act.summary or _("Rappel"),
                    "lead_id": lead.id if lead else False,
                    "lead_name": lead.name if lead else "",
                    "phone": lead.phone if lead else "",
                }
            )
        if "calendar.event" in self.env:
            events = self.env["calendar.event"].sudo().search(
                [
                    ("user_id", "=", user.id),
                    ("start", ">=", fields.Datetime.now()),
                    ("name", "ilike", "rappel"),
                ],
                order="start asc",
                limit=30,
            )
            for ev in events:
                callbacks.append(
                    {
                        "id": "cal-%s" % ev.id,
                        "date": fields.Datetime.to_string(ev.start),
                        "summary": ev.name,
                        "lead_id": False,
                        "lead_name": "",
                        "phone": "",
                        "calendar_event_id": ev.id,
                    }
                )
        return callbacks

    @api.model
    def _get_stats_today(self, user):
        today = fields.Date.today()
        debut = datetime.datetime.combine(today, datetime.time.min)
        sessions = self.search(
            [
                ("user_id", "=", user.id),
                ("date_start", ">=", debut),
            ]
        )
        syncs = self.env["doorway.vicidial.call.sync"].sudo().search_count(
            [
                ("user_id", "=", user.id),
                ("date_debut", ">=", debut),
            ]
        )
        return {
            "sessions": len(sessions),
            "duree_totale": sum(sessions.mapped("duree_travail_secondes")),
            "appels": syncs,
            "qualifies": sum(sessions.mapped("nb_qualifies")),
        }

    # ------------------------------------------------------------------
    # Hub d'appels — liste des appels récents, fiche CRM, notes,
    # activités et envoi SMS / WhatsApp (réutilise doorway_messaging).
    # ------------------------------------------------------------------

    _AVATAR_PALETTE = [
        "#6366f1", "#8b5cf6", "#0ea5e9", "#14b8a6",
        "#f59e0b", "#ec4899", "#10b981", "#f43f5e",
    ]
    _ODOO_TAG_COLORS = {
        0: "#94a3b8", 1: "#ef4444", 2: "#f59e0b", 3: "#eab308",
        4: "#06b6d4", 5: "#a855f7", 6: "#ec4899", 7: "#14b8a6",
        8: "#3b82f6", 9: "#f43f5e", 10: "#22c55e", 11: "#8b5cf6",
    }

    @api.model
    def _initials(self, name):
        parts = [p for p in re.split(r"\s+", (name or "").strip()) if p]
        if not parts:
            return "?"
        if len(parts) == 1:
            return parts[0][:2].upper()
        return (parts[0][0] + parts[-1][0]).upper()

    @api.model
    def _avatar_color(self, key):
        key = key or "?"
        idx = sum(ord(c) for c in key) % len(self._AVATAR_PALETTE)
        return self._AVATAR_PALETTE[idx]

    @api.model
    def _tag_color(self, color_index):
        return self._ODOO_TAG_COLORS.get(int(color_index or 0), "#14b8a6")

    @api.model
    def _relative_time_fr(self, dt):
        if not dt:
            return ""
        now = fields.Datetime.now()
        secs = int((now - dt).total_seconds())
        if secs < 0:
            secs = 0
        if secs < 60:
            return _("à l'instant")
        mins = secs // 60
        if mins < 60:
            return _("il y a %s min") % mins
        hours = mins // 60
        if hours < 24:
            return _("il y a %s h") % hours
        days = hours // 24
        if days == 1:
            return _("Hier")
        if days < 7:
            return _("il y a %s j") % days
        return fields.Datetime.to_string(dt)[:10]

    @api.model
    def get_recent_calls(self, kind="all", search=None, limit=60):
        """Appels récents de l'agent connecté (source : sync VICIdial temps réel)."""
        user = self.env.user
        Sync = self.env["doorway.vicidial.call.sync"].sudo()
        syncs = Sync.search(
            [("user_id", "=", user.id)], order="date_debut desc", limit=300
        )
        search_norm = (search or "").strip().lower()
        entries = []
        for s in syncs:
            connected = (s.duree_secondes or 0) > 0 or s.statut_vicidial == "INCALL"
            is_active = s.statut_vicidial == "INCALL" and not s.date_fin
            missed = (not connected) and s.statut_vicidial == "HUNG_UP"
            # Les appels du poste sont émis vers le prospect (sortant). Un
            # appel sans temps de parole est traité comme « manqué ».
            direction = "sortant"
            status = "manque" if missed else direction
            name = (
                s.lead_name
                or (s.lead_id.name if s.lead_id else "")
                or s.phone
                or _("Inconnu")
            )
            if search_norm:
                haystack = "%s %s" % (name or "", s.phone or "")
                if search_norm not in haystack.lower():
                    continue
            if kind == "entrants" and direction != "entrant":
                continue
            if kind == "manques" and status != "manque":
                continue
            entries.append(
                {
                    "id": s.id,
                    "name": name,
                    "phone": s.phone or "",
                    "direction": direction,
                    "status": status,
                    "missed": missed,
                    "active": is_active,
                    "initials": self._initials(name),
                    "color": self._avatar_color(name or s.phone),
                    "rel_time": self._relative_time_fr(s.date_debut),
                    "lead_id": s.lead_id.id if s.lead_id else False,
                    "duration": s.duree_secondes or 0,
                }
            )
            if len(entries) >= limit:
                break
        return entries

    @api.model
    def _phone_search_tails(self, phone):
        """Suffixes téléphone pour recherche CRM / VICIdial (10 chiffres NA, 9 FR/QC)."""
        digits = re.sub(r"\D", "", phone or "")
        if not digits:
            return []
        # Artefact Odoo Léa B2B : préfixe 033 + 9 chiffres (ex. 033472800610 → 472800610).
        if digits.startswith("033") and len(digits) >= 12:
            core = digits[3:]
            if len(core) == 9:
                digits = core
        tails = []
        if len(digits) >= 10:
            tails.append(digits[-10:])
        if len(digits) >= 9:
            nine = digits[-9:]
            if nine not in tails:
                tails.append(nine)
        if not tails:
            tails.append(digits)
        return tails

    @api.model
    def _model_phone_fields(self, model):
        """Champs téléphone disponibles (Odoo 19 : pas de res.partner.mobile ici)."""
        names = []
        for fname in ("phone", "mobile", "mobile_phone"):
            if fname in model._fields:
                names.append(fname)
        return names or ["phone"]

    @api.model
    def _phone_match_domain(self, phone, model=None):
        """Domaine ORM res.partner / crm.lead pour un numéro composé."""
        model = model or self.env["res.partner"].sudo()
        tails = self._phone_search_tails(phone)
        if not tails:
            return []
        fields = self._model_phone_fields(model)
        leaves = []
        for tail in tails:
            for fname in fields:
                leaves.append((fname, "ilike", tail))
        if len(leaves) == 1:
            return leaves
        return ["|"] * (len(leaves) - 1) + leaves

    @api.model
    def _search_best_phone_record(self, model, phone):
        """Meilleur enregistrement pour un numéro (évite société si contact perso existe)."""
        dom = self._phone_match_domain(phone, model)
        if not dom:
            return model.browse()
        records = model.search(dom, order="write_date desc", limit=20)
        if not records:
            return model.browse()
        if len(records) == 1:
            return records
        digits = "".join(c for c in (phone or "") if c.isdigit())
        exact = records.filtered(
            lambda r: digits
            and digits[-10:] in "".join(c for c in (r.phone or "") if c.isdigit())
        )
        if exact:
            records = exact
        if model._name == "res.partner":
            persons = records.filtered(lambda p: not p.is_company)
            if persons:
                return persons[0]
        return records[0]

    @api.model
    def _resolve_contact_records(self, phone=None, lead_id=None, partner_id=None):
        Partner = self.env["res.partner"].sudo()
        Lead = self.env["crm.lead"].sudo()
        partner = Partner.browse()
        lead = Lead.browse()
        if partner_id:
            partner = Partner.browse(int(partner_id)).exists()
        if lead_id:
            lead = Lead.browse(int(lead_id)).exists()
        if lead and not partner and lead.partner_id:
            partner = lead.partner_id
        if not partner and phone:
            partner = self._search_best_phone_record(Partner, phone)
        if not lead and phone:
            lead = self._search_best_phone_record(Lead, phone)
        if not lead and partner:
            lead = Lead.search(
                [("partner_id", "=", partner.id)], order="write_date desc", limit=1
            )
        return partner, lead

    @api.model
    def get_contact_fiche(self, phone=None, lead_id=None, partner_id=None):
        partner, lead = self._resolve_contact_records(phone, lead_id, partner_id)
        if not partner and not lead:
            return {
                "found": False,
                "name": (phone or "").strip() or _("Contact inconnu"),
                "phone": (phone or "").strip(),
                "initials": self._initials(phone or "?"),
                "color": self._avatar_color(phone or "?"),
                "tags": [],
            }
        name = (
            (partner.name if partner else "")
            or (lead.contact_name if lead else "")
            or (lead.name if lead else "")
            or (phone or "").strip()
            or _("Contact")
        )
        role = (partner.function if partner else "") or (
            lead.function if lead and "function" in lead._fields else ""
        )
        company = ""
        if partner:
            company = (
                (partner.parent_id.name if partner.parent_id else "")
                or partner.commercial_company_name
                or partner.company_name
                or ""
            )
        if not company and lead:
            company = lead.partner_name or ""
        email = (partner.email if partner else "") or (lead.email_from if lead else "")
        phone_val = (
            (partner.phone if partner else "")
            or (lead.phone if lead else "")
            or (phone or "").strip()
        )
        mobile = ""
        if partner:
            for fname in self._model_phone_fields(partner):
                if fname != "phone" and partner[fname]:
                    mobile = partner[fname]
                    break
        if not mobile and lead:
            for fname in self._model_phone_fields(lead):
                if fname != "phone" and lead[fname]:
                    mobile = lead[fname]
                    break
        tags = []
        if partner:
            for cat in partner.category_id[:6]:
                tags.append({"name": cat.name, "color": self._tag_color(cat.color)})
        if lead:
            for tag in lead.tag_ids[:6]:
                tags.append({"name": tag.name, "color": self._tag_color(tag.color)})
            if lead.stage_id:
                tags.append({"name": lead.stage_id.name, "color": "#6366f1"})
        if partner and partner.active or (lead and lead.active):
            tags.append({"name": _("Actif"), "color": "#22c55e"})
        last_interaction = self._last_interaction(partner, lead)
        qual_statut = ""
        qual_label = ""
        if lead:
            qual_statut = lead.qualification_statut or "non_fait"
            qual_label = lead._qualification_label(qual_statut)
        return {
            "found": True,
            "partner_id": partner.id if partner else False,
            "lead_id": lead.id if lead else False,
            "name": name,
            "role": role or "",
            "company": company or "",
            "email": email or "",
            "phone": phone_val or "",
            "mobile": mobile or "",
            "initials": self._initials(name),
            "color": self._avatar_color(name),
            "tags": tags[:8],
            "last_interaction": last_interaction,
            "qualification_statut": qual_statut,
            "qualification_label": qual_label,
        }

    @api.model
    def _last_interaction(self, partner, lead):
        record = lead or partner
        if not record:
            return ""
        msg = self.env["mail.message"].sudo().search(
            [("model", "=", record._name), ("res_id", "=", record.id)],
            order="date desc",
            limit=1,
        )
        if msg and msg.date:
            label = _("Message") if msg.message_type != "comment" else _("Note")
            return "%s · %s" % (self._relative_time_fr(msg.date), label)
        ref_dt = record.write_date
        if ref_dt:
            return self._relative_time_fr(ref_dt)
        return ""

    @api.model
    def workstation_open_contact(self, lead_id=None, partner_id=None):
        if lead_id:
            return {
                "type": "ir.actions.act_window",
                "res_model": "crm.lead",
                "res_id": int(lead_id),
                "view_mode": "form",
                "views": [[False, "form"]],
                "target": "current",
            }
        if partner_id:
            return {
                "type": "ir.actions.act_window",
                "res_model": "res.partner",
                "res_id": int(partner_id),
                "view_mode": "form",
                "views": [[False, "form"]],
                "target": "current",
            }
        return {}

    @api.model
    def workstation_save_note(self, note, lead_id=None, partner_id=None):
        body = (note or "").strip()
        if not body:
            return {"ok": False, "error": "empty"}
        record = None
        if lead_id:
            record = self.env["crm.lead"].browse(int(lead_id)).exists()
        if not record and partner_id:
            record = self.env["res.partner"].browse(int(partner_id)).exists()
        if not record:
            return {"ok": False, "error": "no_target"}
        record.message_post(
            body=plaintext2html(body), subject=_("Note d'appel")
        )
        return {"ok": True}

    @api.model
    def _activity_type_ref(self, kind):
        xmlid = (
            "mail.mail_activity_data_call"
            if kind == "followup"
            else "mail.mail_activity_data_todo"
        )
        act_type = self.env.ref(xmlid, raise_if_not_found=False)
        if not act_type:
            act_type = self.env["mail.activity.type"].sudo().search([], limit=1)
        return act_type

    @api.model
    def workstation_create_activity(
        self,
        kind="task",
        lead_id=None,
        partner_id=None,
        summary=None,
        note=None,
        date_deadline=None,
    ):
        record = None
        if lead_id:
            record = self.env["crm.lead"].browse(int(lead_id)).exists()
        if not record and partner_id:
            record = self.env["res.partner"].browse(int(partner_id)).exists()
        if not record:
            return {"ok": False, "error": "no_target"}
        act_type = self._activity_type_ref(kind)
        if not act_type:
            return {"ok": False, "error": "no_activity_type"}
        model = self.env["ir.model"]._get(record._name)
        if date_deadline:
            deadline = fields.Date.to_date(date_deadline)
        else:
            deadline = fields.Date.today() + timedelta(
                days=2 if kind == "followup" else 1
            )
        default_summary = (
            _("Programmer un suivi") if kind == "followup" else _("Tâche d'appel")
        )
        activity = self.env["mail.activity"].create(
            {
                "res_model_id": model.id,
                "res_id": record.id,
                "activity_type_id": act_type.id,
                "user_id": self.env.user.id,
                "summary": (summary or "").strip() or default_summary,
                "note": plaintext2html(note) if note else False,
                "date_deadline": deadline,
            }
        )
        return {"ok": True, "activity_id": activity.id}

    @api.model
    def workstation_apply_qualification(
        self, statut, lead_id=None, partner_id=None, note=None
    ):
        """Qualification rapide depuis le panneau contact du poste d'appels."""
        _partner, lead = self._resolve_contact_records(None, lead_id, partner_id)
        if not lead:
            return {"ok": False, "error": "no_lead"}
        had_note = bool((note or "").strip())
        lead.apply_workstation_qualification(statut, note=note)
        agent_login = ""
        session = self.get_active_session(self.env.user)
        if session and session.vicidial_user:
            agent_login = session.vicidial_user
        vic = self._vicidial_svc()
        vic_sync = vic.sync_qualification_to_vicidial(
            lead, statut, agent_login=agent_login
        )
        if statut not in lead.WORKSTATION_CALL_OUTCOME_ONLY:
            lead._record_session_qualification()
        return {
            "ok": True,
            "qualification_statut": lead.qualification_statut,
            "qualification_label": lead._qualification_label(),
            "vicidial_sync": vic_sync,
            "note_saved": had_note,
        }

    @api.model
    def _messaging_caps(self):
        caps = {"installed": False, "sms": False, "whatsapp": False}
        if "doorway.message.log" not in self.env:
            return caps
        caps["installed"] = True
        try:
            from odoo.addons.doorway_messaging.services.sms_service import SmsService
            from odoo.addons.doorway_messaging.services.whatsapp_service import (
                WhatsAppService,
            )

            caps["sms"] = bool(SmsService(self.env).is_available())
            caps["whatsapp"] = bool(WhatsAppService(self.env).is_available())
        except Exception:  # noqa: BLE001
            _logger.warning("doorway_messaging indisponible pour le poste d'appels")
        return caps

    @api.model
    def _log_workstation_message(self, canal, number, body, res, lead_id, partner_id):
        if "doorway.message.log" not in self.env:
            return
        try:
            self.env["doorway.message.log"].sudo().create(
                {
                    "canal": canal,
                    "destinataire": number,
                    "lead_id": int(lead_id) if lead_id else False,
                    "partner_id": int(partner_id) if partner_id else False,
                    "statut": "envoye" if res.get("success") else "erreur",
                    "date_envoi": fields.Datetime.now(),
                    "message_id": res.get("sid") or False,
                    "erreur_msg": res.get("error") or False,
                    "corps_envoye": body or "",
                }
            )
        except Exception:  # noqa: BLE001
            _logger.exception("Log message poste d'appels (%s) impossible", canal)

    @api.model
    def workstation_send_message(
        self, channel, phone, body=None, lead_id=None, partner_id=None
    ):
        caps = self._messaging_caps()
        if not caps["installed"]:
            return {"ok": False, "error": "module_absent"}
        number = (phone or "").strip()
        if not number:
            return {"ok": False, "error": "no_phone"}
        body = (body or "").strip()
        channel = (channel or "").lower()
        if channel == "sms":
            if not caps["sms"]:
                return {"ok": False, "error": "sms_unavailable"}
            from odoo.addons.doorway_messaging.services.sms_service import SmsService

            res = SmsService(self.env).send_sms(number, body=body)
            canal = "sms"
        elif channel == "whatsapp":
            if not caps["whatsapp"]:
                return {"ok": False, "error": "wa_unavailable"}
            from odoo.addons.doorway_messaging.services.whatsapp_service import (
                WhatsAppService,
            )

            res = WhatsAppService(self.env).send_whatsapp(number, body=body)
            canal = "whatsapp"
        else:
            return {"ok": False, "error": "bad_channel"}
        self._log_workstation_message(canal, number, body, res, lead_id, partner_id)
        if res.get("success"):
            return {"ok": True, "sid": res.get("sid") or ""}
        return {"ok": False, "error": res.get("error") or "send_failed"}

    def _resolve_employee(self):
        employee = self.user_id.employee_id
        if employee:
            return employee
        Profile = self.env.get("pe.employee.profile")
        if not Profile:
            return self.env["hr.employee"]
        profile = Profile.sudo().search(
            [("employee_id.user_id", "=", self.user_id.id)], limit=1
        )
        if not profile and self.vicidial_user:
            profile = Profile.sudo().search(
                [
                    "|",
                    ("vicidial_user", "=", self.vicidial_user),
                    ("vicidial_agent_id", "=", self.vicidial_user),
                ],
                limit=1,
            )
        return profile.employee_id if profile else self.env["hr.employee"]

    def _log_presence(self, statut, note=""):
        employee = self._resolve_employee()
        if not employee:
            return
        PeLog = self.env.get("pe.presence.log")
        if not PeLog:
            return
        PeLog.sudo().create(
            {
                "employee_id": employee.id,
                "statut": statut,
                "source": "odoo",
                "vicidial_agent_id": self.vicidial_user,
                "note": note,
            }
        )

    def _activate_vicidial_session(self, agent, campaign, user=None):
        from odoo.addons.doorway_vicidial_campaigns.services.vicidial_service import (
            VicidialService,
        )

        svc = VicidialService(self.env)
        svc.ensure_webrtc_viciphone()
        svc.ensure_agent_webphone(
            agent.vicidial_user,
            agent.full_name or (user.name if user else agent.vicidial_user),
        )
        # Ne pas reload PJSIP / kick conf au démarrage — casse l'enregistrement WebRTC en cours.
        list_id = campaign.vicidial_list_id or "1010"
        allows_manual = (
            (
                campaign.campaign_mode in ("human_agent", "mixed")
                and (campaign.auto_dial_mode or "") not in ("progressive", "predictive")
            )
            or svc.is_manual_dial_campaign(
                campaign.vicidial_campaign_id, campaign.auto_dial_mode
            )
        )
        if allows_manual:
            hopper_count = svc.get_hopper_count(campaign.vicidial_campaign_id)
        else:
            hopper_count = svc.reload_campaign_hopper(campaign, list_id=list_id)
            if hopper_count <= 0:
                raise UserError(
                    _(
                        "Aucun prospect prêt à appeler pour cette campagne "
                        "(hopper vide, liste %s)."
                    )
                    % list_id
                )
        ready_info = svc.activate_agent_ready(
            agent.vicidial_user,
            campaign.vicidial_campaign_id,
            mobile_callback=False,
        )
        if not ready_info.get("ok"):
            raise UserError(
                _("Impossible de passer l'agent en READY VICIdial : %s")
                % (ready_info.get("message") or _("erreur inconnue"))
            )
        webphone_url = svc.build_webphone_embed_url(
            agent.vicidial_user,
            campaign.vicidial_campaign_id,
            conf_exten=ready_info.get("conf_exten"),
        )
        _logger.info(
            "Session %s — hopper %s=%s, READY=%s, webphone=%s",
            agent.vicidial_user,
            campaign.vicidial_campaign_id,
            hopper_count,
            ready_info,
            bool(webphone_url),
        )
        return {
            "vicidial_live": svc.get_agent_live_status(agent.vicidial_user),
            "webphone_url": webphone_url,
            "conf_exten": ready_info.get("conf_exten"),
            "session_name": ready_info.get("session_name") or "",
        }

    @api.model
    def action_start_session(self, campaign_id, callback_phone=None):
        user = self.env.user
        campaign = self.env["doorway.campaign"].browse(campaign_id).exists()
        if not campaign:
            raise UserError(_("Campagne introuvable."))
        if self._is_frb2c_only_agent(user):
            if campaign.vicidial_campaign_id != _FRB2C_ONLY_CAMPAIGN:
                raise UserError(
                    _("Votre poste est réservé à la campagne France B2C — RénoFacile.")
                )
        agent = self._get_agent_user(user, campaign=campaign)
        if not agent:
            raise UserError(
                _("Aucun agent d'appels configuré pour votre compte Odoo.")
            )
        self._end_open_sessions(user)
        vicidial_live = {}
        webphone_url = ""
        activated = {}
        if campaign.campaign_mode in ("human_agent", "mixed") and campaign.vicidial_campaign_id:
            activated = self._activate_vicidial_session(agent, campaign, user=user)
            vicidial_live = activated["vicidial_live"]
            webphone_url = activated.get("webphone_url") or ""

        session = self.create(
            {
                "user_id": user.id,
                "agent_user_id": agent.id,
                "campaign_id": campaign.id,
                "vicidial_user": agent.vicidial_user,
                "vicidial_session_name": activated.get("session_name") or "",
                "outbound_group_alias_id": self._default_outbound_group_alias_for_campaign(
                    campaign
                ),
                "state": "active",
                "date_start": fields.Datetime.now(),
            }
        )
        session._log_presence(
            "actif",
            _("Session démarrée — %s") % campaign.name,
        )
        payload = session._to_client_dict(vicidial_live)
        if webphone_url:
            payload["vicidial_webphone_url"] = webphone_url
        return payload

    def _vicidial_svc(self):
        from odoo.addons.doorway_vicidial_campaigns.services.vicidial_service import (
            VicidialService,
        )

        return VicidialService(self.env)

    def action_pause_session(self):
        self.ensure_one()
        if self.state != "active":
            raise UserError(_("La session n'est pas active."))
        if self.vicidial_user:
            self._vicidial_svc().set_agent_paused(self.vicidial_user)
        self.write(
            {
                "state": "paused",
                "last_pause_start": fields.Datetime.now(),
            }
        )
        self._log_presence("en_pause", _("Pause session — %s") % self.campaign_id.name)
        return self._to_client_dict()

    def action_resume_session(self):
        self.ensure_one()
        if self.state != "paused":
            raise UserError(_("La session n'est pas en pause."))
        extra_pause = 0
        if self.last_pause_start:
            extra_pause = int(
                (fields.Datetime.now() - self.last_pause_start).total_seconds()
            )
        resume_vals = {
            "state": "active",
            "total_pause_seconds": self.total_pause_seconds + extra_pause,
            "last_pause_start": False,
        }
        if self.vicidial_user and self.campaign_id.vicidial_campaign_id:
            agent = self.agent_user_id
            if agent:
                activated = self._activate_vicidial_session(
                    agent, self.campaign_id, user=self.user_id
                )
                if activated.get("session_name"):
                    resume_vals["vicidial_session_name"] = activated["session_name"]
        self.write(resume_vals)
        self._log_presence(
            "actif", _("Reprise session — %s") % self.campaign_id.name
        )
        return self._to_client_dict()

    def action_set_outbound_group_alias(self, group_alias_id=None):
        """Persiste la préférence d'alias CID sortant pour la session active."""
        self.ensure_one()
        alias = (group_alias_id if group_alias_id is not None else "").strip()
        self.sudo().write({"outbound_group_alias_id": alias or False})
        return {"ok": True, "outbound_group_alias_id": alias}

    def action_dial_next(self, group_alias_id=None):
        self.ensure_one()
        if self.state != "active":
            raise UserError(_("La session n'est pas active."))
        if not self.vicidial_user or not self.campaign_id.vicidial_campaign_id:
            raise UserError(_("Campagne VICIdial non configurée."))
        alias = (
            (group_alias_id if group_alias_id is not None else self.outbound_group_alias_id)
            or ""
        ).strip()
        if group_alias_id is not None:
            self.sudo().write({"outbound_group_alias_id": alias or False})
        svc = self._vicidial_svc()
        live = svc.get_agent_live_status(self.vicidial_user)
        if not live.get("ready"):
            # Auto-récupération : un process VICIdial peut repasser l'agent en
            # PAUSE (random_id=10) entre deux heartbeats. On le repasse READY
            # puis on revérifie avant d'échouer (évite « pas ready » alors que
            # l'agent est connecté).
            svc.sync_agent_ready_for_session(
                self.vicidial_user,
                self.campaign_id.vicidial_campaign_id,
                self.vicidial_session_name,
            )
            live = svc.get_agent_live_status(self.vicidial_user)
        if not live.get("ready"):
            raise UserError(
                _("VICIdial n'est pas READY — patientez ou actualisez la page.")
            )
        if not self.vicidial_session_name or not live.get("conf_exten"):
            raise UserError(
                _("Session VICIdial incomplète — terminez et redémarrez la session.")
            )
        result = svc.dial_manual_next_call(
            self.vicidial_user,
            self.vicidial_session_name,
            self.campaign_id.vicidial_campaign_id,
            live.get("conf_exten"),
            group_alias_id=alias or None,
        )
        if not result.get("ok"):
            raise UserError(result.get("message") or _("Impossible de lancer l'appel."))
        return result

    def action_manual_dial(self, raw_phone, group_alias_id=None):
        """Compose manuellement un numéro saisi ou collé par l'agent."""
        self.ensure_one()
        if self.state != "active":
            raise UserError(_("La session n'est pas active."))
        if not self.vicidial_user or not self.campaign_id.vicidial_campaign_id:
            raise UserError(_("Campagne VICIdial non configurée."))
        alias = (
            (group_alias_id if group_alias_id is not None else self.outbound_group_alias_id)
            or ""
        ).strip()
        if group_alias_id is not None:
            self.sudo().write({"outbound_group_alias_id": alias or False})
        svc = self._vicidial_svc()
        country = self.campaign_id._phone_import_country()
        phone_number, phone_code = svc.normalize_manual_dial_phone(raw_phone, country)
        if not phone_number:
            hint = self._manual_dial_hint()
            raise UserError(
                _("Numéro invalide. %(hint)s", hint=hint)
            )
        live = svc.get_agent_live_status(self.vicidial_user)
        if not live.get("ready"):
            # Auto-récupération : un process VICIdial peut repasser l'agent en
            # PAUSE (random_id=10) entre deux heartbeats. On le repasse READY
            # puis on revérifie avant d'échouer (évite « pas ready » alors que
            # l'agent est connecté).
            svc.sync_agent_ready_for_session(
                self.vicidial_user,
                self.campaign_id.vicidial_campaign_id,
                self.vicidial_session_name,
            )
            live = svc.get_agent_live_status(self.vicidial_user)
        if not live.get("ready"):
            raise UserError(
                _("VICIdial n'est pas READY — patientez ou actualisez la page.")
            )
        if not self.vicidial_session_name or not live.get("conf_exten"):
            raise UserError(
                _("Session VICIdial incomplète — terminez et redémarrez la session.")
            )
        list_id = svc.get_campaign_manual_dial_list_id(
            self.campaign_id.vicidial_campaign_id
        )
        session_name = svc.resolve_vicidial_session_name(
            self.vicidial_user, self.vicidial_session_name
        )
        if session_name != (self.vicidial_session_name or ""):
            self.sudo().write({"vicidial_session_name": session_name})
        join = svc.ensure_webphone_in_conference(
            self.vicidial_user, live.get("conf_exten")
        )
        if not join.get("ok"):
            raise UserError(
                _(
                    "Micro WebRTC hors conférence agent — attendez « Connecté » "
                    "sur le téléphone intégré puis réessayez."
                )
            )
        result = svc.dial_manual_number(
            self.vicidial_user,
            session_name,
            self.campaign_id.vicidial_campaign_id,
            live.get("conf_exten"),
            phone_number,
            phone_code=phone_code,
            list_id=list_id,
            country=self.campaign_id._phone_import_country(),
            group_alias_id=alias or None,
        )
        if not result.get("ok"):
            raise UserError(result.get("message") or _("Impossible de composer ce numéro."))
        resolved = (result.get("session_name") or "").strip()
        if resolved and resolved != session_name:
            self.sudo().write({"vicidial_session_name": resolved})
        self.env["doorway.vicidial.call.sync"].sudo().register_manual_outbound(
            self.user_id,
            self.vicidial_user,
            self.campaign_id,
            phone_number,
            lead_id=result.get("lead_id"),
        )
        return result

    def action_hangup_call(self):
        """Raccroche l appel client VICIdial (composition manuelle poste Odoo)."""
        self.ensure_one()
        if self.state != "active":
            raise UserError(_("La session n'est pas active."))
        if not self.vicidial_user:
            raise UserError(_("Agent VICIdial non configuré."))
        svc = self._vicidial_svc()
        live = svc.get_agent_live_status(self.vicidial_user)
        session_name = svc.resolve_vicidial_session_name(
            self.vicidial_user, self.vicidial_session_name
        )
        result = svc.hangup_agent_call(
            self.vicidial_user,
            session_name=session_name,
            campaign_id=self.campaign_id.vicidial_campaign_id,
            conf_exten=live.get("conf_exten"),
        )
        if not result.get("ok") and not result.get("skipped"):
            raise UserError(result.get("message") or _("Impossible de raccrocher."))
        return result

    def action_end_session(self):
        self.ensure_one()
        if self.state == "ended":
            return self._to_client_dict()
        if self.vicidial_user:
            self._vicidial_svc().deactivate_agent(self.vicidial_user)
        extra_pause = 0
        if self.state == "paused" and self.last_pause_start:
            extra_pause = int(
                (fields.Datetime.now() - self.last_pause_start).total_seconds()
            )
        self.write(
            {
                "state": "ended",
                "date_end": fields.Datetime.now(),
                "total_pause_seconds": self.total_pause_seconds + extra_pause,
                "last_pause_start": False,
            }
        )
        self._log_presence(
            "deconnecte",
            _("Fin session — %s (%s appels)") % (self.campaign_id.name, self.nb_appels),
        )
        self._update_presence_summary()
        return self._to_client_dict()

    def record_call_event(self, qualification_faite=False, is_rappel=False):
        self.ensure_one()
        vals = {"nb_appels": self.nb_appels + 1}
        if qualification_faite:
            vals["nb_qualifies"] = self.nb_qualifies + 1
        if is_rappel:
            vals["nb_rappels"] = self.nb_rappels + 1
        self.write(vals)

    def _update_presence_summary(self):
        employee = self._resolve_employee()
        if not employee:
            return
        Summary = self.env.get("pe.presence.summary")
        if not Summary:
            return
        today = fields.Date.today()
        summary = Summary.sudo().search(
            [("employee_id", "=", employee.id), ("date", "=", today)],
            limit=1,
        )
        sessions = self.search(
            [
                ("user_id", "=", self.user_id.id),
                ("date_start", ">=", datetime.datetime.combine(today, datetime.time.min)),
                ("state", "=", "ended"),
            ]
        )
        nb_appels = self.env["doorway.vicidial.call.sync"].sudo().search_count(
            [
                ("user_id", "=", self.user_id.id),
                ("date_debut", ">=", datetime.datetime.combine(today, datetime.time.min)),
            ]
        )
        vals = {
            "nb_appels_vicidial": nb_appels,
            "nb_leads_generes": sum(sessions.mapped("nb_qualifies")),
            "heure_debut": min(sessions.mapped("date_start")) if sessions else self.date_start,
            "heure_fin": self.date_end,
        }
        if summary:
            summary.write(vals)
        else:
            Summary.create({"employee_id": employee.id, "date": today, **vals})

    @api.model
    def cron_maintain_webrtc_pjsip(self):
        """Retire le wizard 86019 recréé par VICIdial (endpoint dans pjsip_custom_webrtc.conf)."""
        from odoo.addons.doorway_vicidial_campaigns.services.vicidial_service import (
            VicidialService,
        )

        svc = VicidialService(self.env)
        svc._ensure_pjsip_custom_webrtc_only()
        svc._reload_asterisk_sip_stack()
