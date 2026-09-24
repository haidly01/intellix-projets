# -*- coding: utf-8 -*-
import json
import logging
from datetime import datetime, timedelta

import requests

from odoo import _, api, fields, models
from odoo.exceptions import UserError

from odoo.addons.doorway_veille_sociale.services.meta_service import MetaGraphService
from odoo.addons.doorway_veille_sociale.services.reddit_service import RedditService
from odoo.addons.doorway_veille_sociale.services.url_resolver import VeilleUrlResolver

_logger = logging.getLogger(__name__)

REQUEST_TIMEOUT = 30


class VeilleSignal(models.Model):
    _name = "doorway.veille.signal"
    _description = "Signal de veille sociale"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "score_final desc, date_detection desc"
    _rec_name = "titre"

    # Identité du signal
    signal_id_externe = fields.Char(
        string="ID externe (Supabase)", index=True, copy=False, tracking=True
    )
    source = fields.Selection(
        [
            ("reddit", "Reddit"),
            ("google_alerts", "Google Alerts"),
            ("instagram", "Instagram"),
            ("facebook", "Facebook"),
            ("facebook_manuel", "Facebook (manuel)"),
            ("autre", "Autre"),
        ],
        string="Source",
        default="autre",
        tracking=True,
    )
    plateforme = fields.Char(string="Plateforme")
    auteur = fields.Char(string="Auteur")
    titre = fields.Char(string="Titre")
    texte = fields.Text(string="Texte")
    url = fields.Char(string="URL")
    url_editeur = fields.Char(
        string="Site éditeur",
        help="URL du média d'origine (extrait du flux RSS Google Alerts).",
    )
    url_resolue = fields.Char(
        string="URL ouverte",
        copy=False,
        help="Lien résolu mis en cache pour l'ouverture navigateur.",
    )
    url_enrichie = fields.Char(
        string="URL enrichie (Reddit)",
        copy=False,
        help="Permalink Reddit trouvé pour une home de subreddit — n'écrase pas url_resolue.",
    )
    categorie_lead = fields.Char(string="Catégorie lead")
    reponse_publique = fields.Text(string="Réponse publique")
    message_prive = fields.Text(string="Message privé")
    canal_soumission = fields.Char(
        string="Soumis par",
        help="Leila / Martin / Zakaria (capture Facebook manuelle). Pas une colonne Supabase.",
    )
    external_object_id = fields.Char(
        string="ID post / média (Meta)",
        index=True,
        copy=False,
        help="Identifiant Graph API du post Facebook ou média Instagram.",
    )
    external_comment_id = fields.Char(
        string="ID commentaire (Meta)",
        index=True,
        copy=False,
        help="Commentaire auquel répondre via l'API Meta.",
    )
    conversation_synced_at = fields.Datetime(string="Conversation sync.", copy=False)
    conversation_message_ids = fields.One2many(
        "doorway.veille.conversation.message",
        "signal_id",
        string="Conversation",
    )
    conversation_message_count = fields.Integer(compute="_compute_conversation_message_count")
    can_reply_api = fields.Boolean(compute="_compute_can_reply_api")
    reply_api_source = fields.Selection(
        [("meta", "Meta"), ("reddit", "Reddit"), ("none", "Aucune")],
        compute="_compute_can_reply_api",
    )
    reply_channel_hint = fields.Char(compute="_compute_can_reply_api")

    # Scoring
    pre_score = fields.Integer(string="Pré-score")
    score_final = fields.Integer(string="Score final", tracking=True)
    score_intention = fields.Integer(string="Score d'intention (0-10)")
    temperature = fields.Selection(
        [("hot", "🔥 Hot"), ("warm", "🌡 Warm"), ("cold", "❄ Cold")],
        string="Température",
        default="cold",
        tracking=True,
    )
    resume = fields.Char(string="Résumé IA")
    type_projet = fields.Char(string="Type de projet")
    marche = fields.Selection(
        [("quebec", "Québec"), ("france", "France"), ("autre", "Autre")],
        string="Marché",
        default="quebec",
    )
    action_suggeree = fields.Char(string="Action suggérée")

    # Statut de traitement
    statut = fields.Selection(
        [
            ("en_attente", "En attente"),
            ("repondu", "Répondu"),
            ("accepte", "Accepté"),
            ("ignore", "Ignoré"),
            ("cree_odoo", "Lead créé"),
        ],
        string="Statut",
        default="en_attente",
        tracking=True,
    )
    odoo_lead_id = fields.Many2one("crm.lead", string="Lead CRM", copy=False)
    task_id = fields.Many2one("project.task", string="Tâche planifiée", copy=False)
    date_refroidi = fields.Datetime(
        string="Refroidi le",
        copy=False,
        help="Date à laquelle le signal est passé en froid (sans être ignoré).",
    )
    reactivation_statut = fields.Selection(
        [
            ("none", "—"),
            ("eligible", "Éligible réactivation"),
            ("planifie", "Planifié"),
            ("effectue", "Réactivation effectuée"),
        ],
        string="Réactivation",
        default="none",
        tracking=True,
    )
    reactivation_automation_id = fields.Many2one(
        "doorway.veille.reactivation.automation",
        string="Automatisation",
        copy=False,
    )
    reactivation_planifiee = fields.Datetime(string="Réactivation planifiée", copy=False)
    reactivation_derniere_action = fields.Selection(
        [
            ("none", "—"),
            ("like", "Like / Upvote"),
            ("reponse_douce", "Réponse douce"),
            ("tache", "Tâche"),
            ("notification", "Notification"),
        ],
        string="Dernière action douce",
        default="none",
        copy=False,
    )
    date_post = fields.Datetime(string="Date de publication")
    date_detection = fields.Datetime(string="Date de détection", default=fields.Datetime.now)
    age_minutes = fields.Integer(string="Âge (min)", compute="_compute_age_minutes")

    _signal_id_externe_uniq = models.Constraint(
        "unique(signal_id_externe)",
        "Un signal avec cet ID externe existe déjà.",
    )

    @api.depends("date_detection")
    def _compute_age_minutes(self):
        now = fields.Datetime.now()
        for rec in self:
            if rec.date_detection:
                delta = now - rec.date_detection
                rec.age_minutes = int(delta.total_seconds() // 60)
            else:
                rec.age_minutes = 0

    @api.depends("conversation_message_ids")
    def _compute_conversation_message_count(self):
        for rec in self:
            rec.conversation_message_count = len(rec.conversation_message_ids)

    @api.depends("source", "external_object_id", "external_comment_id", "signal_id_externe", "url")
    def _compute_can_reply_api(self):
        cfg = self.env["doorway.veille.config"].get_config()
        token_ok = bool((cfg.meta_access_token or "").strip())
        reddit_ok = RedditService(self.env).credentials_ok(cfg)
        for rec in self:
            rec.reply_api_source = "none"
            rec.can_reply_api = False
            if rec.source in ("facebook", "instagram") and token_ok and rec._get_external_object_id():
                rec.can_reply_api = True
                rec.reply_api_source = "meta"
                rec.reply_channel_hint = _(
                    "Réponse directe via Meta Graph API (%s)"
                ) % (rec.source.capitalize())
            elif rec.source == "reddit" and rec.url and reddit_ok:
                rec.can_reply_api = True
                rec.reply_api_source = "reddit"
                rec.reply_channel_hint = _(
                    "Réponse directe sur Reddit via OAuth (compte configuré)."
                )
            elif rec.source == "reddit" and rec.url:
                rec.reply_channel_hint = _(
                    "Lecture Reddit OK — pour répondre en direct, configurez OAuth Reddit "
                    "dans Veille → Connexions & sources."
                )
            elif rec.source == "google_alerts":
                rec.reply_channel_hint = _(
                    "Alerte presse Google — article détecté, pas de commentaires à lire ici. "
                    "Ouvrez l'article, répondez sur le site ou vos réseaux, "
                    "puis « Marquer répondu (manuel) »."
                )
            elif rec.url:
                rec.reply_channel_hint = _("Réponse via le lien source (pas d'API).")
            else:
                rec.reply_channel_hint = _("Configurez Meta, Reddit ou ajoutez une URL au signal.")

    # ------------------------------------------------------------------
    # Actions utilisateur
    # ------------------------------------------------------------------
    def action_repondre(self):
        """Ouvre l'assistant Répondre (conversation + réponse Meta)."""
        self.ensure_one()
        try:
            self.action_sync_conversation()
        except UserError:
            if self.texte and not self.conversation_message_ids:
                self._upsert_conversation_messages(
                    [
                        {
                            "author_name": self.auteur or _("Auteur"),
                            "body": self.texte,
                            "direction": "inbound",
                            "platform": self.source,
                        }
                    ]
                )
        return {
            "type": "ir.actions.act_window",
            "name": _("Répondre au signal"),
            "res_model": "doorway.repondre.signal.wizard",
            "view_mode": "form",
            "target": "new",
            "context": {"default_signal_id": self.id},
        }

    def _get_external_object_id(self):
        self.ensure_one()
        if self.external_object_id:
            return self.external_object_id
        ext = self.signal_id_externe or ""
        if ext.startswith("meta_"):
            return ext[5:]
        return False

    def _get_reply_target_id(self):
        """ID du commentaire ou post Meta auquel répondre."""
        self.ensure_one()
        if self.external_comment_id:
            return self.external_comment_id
        inbound = self.conversation_message_ids.filtered(
            lambda m: m.direction == "inbound" and m.external_id
        )
        if inbound:
            return inbound[-1].external_id
        return self._get_external_object_id()

    def _has_reply_target(self):
        self.ensure_one()
        if self.source == "reddit":
            return bool(self._get_reddit_reply_thing_id())
        if self.source in ("facebook", "instagram"):
            return bool(self._get_reply_target_id())
        return False

    def _ensure_conversation_for_reply(self):
        """Synchronise le fil avant une réponse API si possible."""
        self.ensure_one()
        if self.source not in ("facebook", "instagram", "reddit"):
            return
        if self._has_reply_target() and self.conversation_message_ids:
            return
        try:
            self.action_sync_conversation()
        except UserError:
            pass

    def _send_reactivation_reply(self, message_text):
        """Réponse douce : API si possible, sinon enregistrement manuel."""
        self.ensure_one()
        text = (message_text or "").strip()
        if not text:
            raise UserError(_("Message de réponse douce vide."))

        self._ensure_conversation_for_reply()
        if self.can_reply_api and self._has_reply_target():
            try:
                self.action_send_reply(text)
                return {"ok": True, "manual": False}
            except UserError:
                _logger.info(
                    "Réactivation API échouée signal %s — bascule manuelle.",
                    self.id,
                )

        self.env["doorway.veille.conversation.message"].sudo().create(
            {
                "signal_id": self.id,
                "direction": "outbound",
                "author_name": self.env.user.name,
                "body": text,
                "posted_at": fields.Datetime.now(),
                "platform": self.source,
            }
        )
        body = _(
            "<p><b>Réactivation douce (manuelle)</b></p>"
            "<p>%s</p>"
        ) % text
        if self.url:
            open_url = self._get_open_url()
            body += '<p><a href="%s" target="_blank">Ouvrir la source pour publier</a></p>' % (
                open_url
            )
        self.message_post(body=body, subtype_xmlid="mail.mt_note")
        return {"ok": True, "manual": True}

    def _send_reactivation_like(self):
        """Like / upvote : API si possible, sinon note manuelle."""
        self.ensure_one()
        cfg = self.env["doorway.veille.config"].get_config()
        self._ensure_conversation_for_reply()
        result = {"ok": False}
        try:
            if self.source == "reddit" and self.url:
                result = RedditService(self.env).vote_up(cfg, self)
            elif self.source in ("facebook", "instagram") and self._get_external_object_id():
                result = MetaGraphService(self.env).like_object(cfg, self)
        except Exception:  # noqa: BLE001
            result = {"ok": False}
        if result.get("ok"):
            return result
        body = _("<p><b>Like / upvote (manuel)</b></p>")
        if self.url:
            open_url = self._get_open_url()
            body += '<p><a href="%s" target="_blank">Ouvrir la source pour liker</a></p>' % (
                open_url
            )
        self.message_post(body=body, subtype_xmlid="mail.mt_note")
        return {"ok": True, "manual": True}

    def _parse_posted_at(self, value):
        if not value:
            return False
        try:
            if isinstance(value, (int, float)) or (
                isinstance(value, str) and str(value).isdigit()
            ):
                from datetime import datetime

                return datetime.utcfromtimestamp(int(value)).strftime("%Y-%m-%d %H:%M:%S")
            txt = str(value).replace("Z", "").replace("T", " ")
            return txt[:19]
        except Exception:  # noqa: BLE001
            return False

    def _upsert_conversation_messages(self, messages, platform=None):
        Message = self.env["doorway.veille.conversation.message"].sudo()
        for rec in self:
            for item in messages:
                ext_id = item.get("external_id")
                domain = [("signal_id", "=", rec.id)]
                if ext_id:
                    domain.append(("external_id", "=", ext_id))
                else:
                    domain.extend(
                        [
                            ("author_name", "=", item.get("author_name")),
                            ("body", "=", item.get("body")),
                        ]
                    )
                existing = Message.search(domain, limit=1)
                vals = {
                    "signal_id": rec.id,
                    "direction": item.get("direction") or "inbound",
                    "author_name": item.get("author_name"),
                    "body": item.get("body"),
                    "external_id": ext_id,
                    "posted_at": rec._parse_posted_at(item.get("posted_at")),
                    "platform": item.get("platform") or platform or rec.source,
                }
                if existing:
                    existing.write(vals)
                else:
                    Message.create(vals)
            if not rec.external_comment_id:
                inbound = rec.conversation_message_ids.filtered(
                    lambda m: m.direction == "inbound" and m.external_id
                )
                if inbound:
                    rec.external_comment_id = inbound[0].external_id
            rec.conversation_synced_at = fields.Datetime.now()

    def _get_reddit_reply_thing_id(self):
        """ID Reddit (t1_/t3_) auquel répondre."""
        self.ensure_one()
        if self.external_comment_id:
            return RedditService.to_thing_id(self.external_comment_id, kind="t1")
        inbound = self.conversation_message_ids.filtered(
            lambda m: m.direction == "inbound" and m.external_id
        )
        if inbound:
            last = inbound[-1]
            kind = "t3" if last == inbound[0] else "t1"
            return RedditService.to_thing_id(last.external_id, kind=kind)
        post_id = RedditService.extract_post_id(self.url)
        return RedditService.to_thing_id(post_id, kind="t3") if post_id else False

    def action_sync_conversation(self):
        """Charge le fil de conversation (Meta ou Reddit)."""
        self.ensure_one()
        rec = self
        messages = []

        if rec.source in ("facebook", "instagram"):
            cfg = self.env["doorway.veille.config"].get_config()
            service = MetaGraphService(self.env)
            result = service.fetch_conversation(cfg, rec)
            messages = result.get("messages") or []
            if not result.get("ok") and not messages:
                if rec.texte:
                    messages = [
                        {
                            "author_name": rec.auteur or _("Auteur"),
                            "body": rec.texte,
                            "direction": "inbound",
                            "platform": rec.source,
                        }
                    ]
                    rec.message_post(
                        body=_(
                            "<p><b>Conversation Meta partielle</b></p>"
                            "<p>%s</p>"
                        )
                        % (result.get("message") or _("Sync Meta impossible.")),
                        subtype_xmlid="mail.mt_note",
                    )
                else:
                    raise UserError(
                        result.get("message") or _("Sync conversation impossible.")
                    )
        elif rec.source == "reddit" and rec.url:
            cfg = self.env["doorway.veille.config"].get_config()
            service = RedditService(self.env)
            result = service.fetch_thread(cfg, rec)
            messages = result.get("messages") or []
            if not messages and rec.texte:
                messages = [
                    {
                        "author_name": rec.auteur or _("Auteur"),
                        "body": rec.texte,
                        "direction": "inbound",
                        "platform": "reddit",
                    }
                ]
            elif not messages:
                raise UserError(
                    result.get("message")
                    or _("Impossible de charger le fil Reddit (OAuth recommandé).")
                )
        elif rec.source == "google_alerts":
            body_parts = []
            if rec.titre:
                body_parts.append(rec.titre)
            if rec.texte and (rec.texte or "").strip() != (rec.titre or "").strip():
                body_parts.append(rec.texte)
            messages = [
                {
                    "author_name": rec.auteur or _("Google Alerts"),
                    "body": "\n\n".join(body_parts) or rec.titre or _("Alerte presse"),
                    "direction": "inbound",
                    "platform": "google_alerts",
                }
            ]
        else:
            if rec.texte:
                messages = [
                    {
                        "author_name": rec.auteur or _("Auteur"),
                        "body": rec.texte,
                        "direction": "inbound",
                        "platform": rec.source,
                    }
                ]
            else:
                raise UserError(
                    _(
                        "Pas de fil disponible : source non Meta ou URL manquante. "
                        "Ouvrez le lien externe pour voir la conversation."
                    )
                )

        rec._upsert_conversation_messages(messages)
        if rec.texte and not rec.conversation_message_ids:
            rec._upsert_conversation_messages(
                [
                    {
                        "author_name": rec.auteur or _("Auteur"),
                        "body": rec.texte,
                        "direction": "inbound",
                        "platform": rec.source,
                    }
                ]
            )
        return True

    def _fetch_reddit_thread(self):
        """Lit les commentaires Reddit publics (sans OAuth)."""
        self.ensure_one()
        url = (self.url or "").split("?")[0].rstrip("/")
        if "reddit.com" not in url:
            return []
        json_url = url if url.endswith(".json") else url + ".json"
        try:
            response = requests.get(
                json_url,
                headers={"User-Agent": "IntellixCRM/1.0"},
                timeout=REQUEST_TIMEOUT,
            )
            if response.status_code != 200:
                return []
            data = response.json()
        except Exception as error:  # noqa: BLE001
            _logger.warning("Reddit thread fetch: %s", error)
            return []

        messages = []
        try:
            post_listing = data[0]["data"]["children"][0]["data"]
            messages.append(
                {
                    "author_name": post_listing.get("author") or "reddit",
                    "body": post_listing.get("title", "") + "\n" + (post_listing.get("selftext") or ""),
                    "direction": "inbound",
                    "platform": "reddit",
                    "external_id": post_listing.get("id"),
                }
            )
            comments = data[1]["data"]["children"] if len(data) > 1 else []
            for child in comments[:40]:
                c = child.get("data") or {}
                if not c.get("body"):
                    continue
                messages.append(
                    {
                        "author_name": c.get("author") or "reddit",
                        "body": c.get("body") or "",
                        "direction": "inbound",
                        "platform": "reddit",
                        "external_id": c.get("id"),
                        "posted_at": c.get("created_utc"),
                    }
                )
        except (KeyError, IndexError, TypeError):
            return messages
        return messages

    def action_send_reply(self, message_text):
        """Publie une réponse via Meta Graph API ou Reddit OAuth."""
        self.ensure_one()
        self._ensure_conversation_for_reply()
        if not self.can_reply_api:
            raise UserError(
                self.reply_channel_hint
                or _("Réponse API non disponible pour ce signal.")
            )
        if not self._has_reply_target():
            raise UserError(
                _(
                    "Impossible de déterminer la cible (post ou commentaire). "
                    "Vérifiez l'URL du signal ou configurez l'ID Meta / Reddit OAuth."
                )
            )
        cfg = self.env["doorway.veille.config"].get_config()
        if self.source == "reddit":
            result = RedditService(self.env).send_reply(cfg, self, message_text)
        else:
            service = MetaGraphService(self.env)
            result = service.send_reply(cfg, self, message_text)
        if not result.get("ok"):
            raise UserError(result.get("message") or _("Échec envoi de la réponse."))

        self.env["doorway.veille.conversation.message"].sudo().create(
            {
                "signal_id": self.id,
                "direction": "outbound",
                "author_name": self.env.user.name,
                "body": message_text,
                "external_id": result.get("external_id"),
                "posted_at": fields.Datetime.now(),
                "platform": self.source,
            }
        )
        self.action_marquer_repondu()
        self.message_post(
            body=_("<p><b>Réponse publiée</b> (%s)</p><p>%s</p>")
            % (self.source, message_text),
            subtype_xmlid="mail.mt_note",
        )
        if self.odoo_lead_id:
            self.odoo_lead_id.message_post(
                body=_("<p><b>Veille — réponse publiée</b></p><p>%s</p>") % message_text,
                subtype_xmlid="mail.mt_note",
            )
        return True

    def action_creer_lead(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": _("Créer un lead CRM"),
            "res_model": "doorway.create.lead.wizard",
            "view_mode": "form",
            "target": "new",
            "context": {"default_signal_id": self.id},
        }

    def action_ignorer(self):
        """Marque le signal ignoré (triage — sans créer d'opportunité CRM)."""
        for rec in self:
            rec.statut = "ignore"
            rec._push_status_to_supabase("ignore")
            rec.message_post(
                body=_("Signal ignoré par %s.") % self.env.user.name,
                subtype_xmlid="mail.mt_note",
            )
        return True

    def action_marquer_repondu(self):
        """Marque le signal comme traité (réponse) sans créer de lead CRM."""
        for rec in self:
            if rec.statut in ("cree_odoo", "ignore"):
                continue
            if rec.statut != "repondu":
                rec.statut = "repondu"
                rec._push_status_to_supabase("repondu")
        return True

    def action_accepter(self):
        """Qualifie le signal (opportunité) — peut déclencher l'auto-lead si configuré."""
        for rec in self:
            if rec.statut in ("en_attente", "repondu"):
                rec.statut = "accepte"
                rec._push_status_to_supabase("accepte")
        self.auto_create_lead_if_hot()
        return True

    def action_planifier_reponse(self):
        self.ensure_one()
        project = self.env["doorway.community.post"].get_community_project()
        task = self.env["project.task"].create(
            {
                "name": _("Réponse : %s") % (self.resume or self.titre or self.url or self.id),
                "project_id": project.id,
                "description": self._build_task_description(),
            }
        )
        self.task_id = task.id
        return {
            "type": "ir.actions.act_window",
            "name": _("Tâche planifiée"),
            "res_model": "project.task",
            "view_mode": "form",
            "res_id": task.id,
            "target": "current",
        }

    def _build_task_description(self):
        self.ensure_one()
        parts = []
        if self.resume:
            parts.append("<p><b>Résumé :</b> %s</p>" % self.resume)
        if self.action_suggeree:
            parts.append("<p><b>Action suggérée :</b> %s</p>" % self.action_suggeree)
        if self.texte:
            parts.append("<p><b>Texte original :</b><br/>%s</p>" % (self.texte or ""))
        if self.url:
            open_url = self._get_open_url()
            parts.append(
                '<p><a href="%s" target="_blank">Voir la source</a></p>' % open_url
            )
        return "".join(parts)

    def _get_open_url(self, cache=True):
        """Résout l'URL à ouvrir (Google News → article ou recherche éditeur)."""
        self.ensure_one()
        if self.url_resolue:
            return self.url_resolue
        resolved = VeilleUrlResolver(self.env).resolve(self)
        if not resolved:
            resolved = self.url
        if cache and resolved and resolved != self.url:
            self.sudo().write({"url_resolue": resolved})
        return resolved

    def action_open_url(self):
        self.ensure_one()
        if not self.url and not self.titre:
            raise UserError(_("Aucune URL pour ce signal."))
        open_url = self._get_open_url()
        if not open_url:
            raise UserError(_("Impossible de construire un lien pour ce signal."))
        return {"type": "ir.actions.act_url", "url": open_url, "target": "new"}

    def action_open_lead(self):
        self.ensure_one()
        if not self.odoo_lead_id:
            raise UserError(_("Aucun lead CRM lié à ce signal."))
        return {
            "type": "ir.actions.act_window",
            "name": _("Lead CRM"),
            "res_model": "crm.lead",
            "view_mode": "form",
            "res_id": self.odoo_lead_id.id,
            "target": "current",
        }

    # ------------------------------------------------------------------
    # Synchronisation Supabase
    # ------------------------------------------------------------------
    @api.model
    def _supabase_headers(self, cfg):
        return {
            "apikey": cfg.supabase_key or "",
            "Authorization": "Bearer %s" % (cfg.supabase_key or ""),
            "Content-Type": "application/json",
        }

    @api.model
    def _map_supabase_row(self, row):
        """Convertit une ligne Supabase en valeurs Odoo (défensif)."""
        def g(*keys):
            for k in keys:
                if k in row and row[k] not in (None, ""):
                    return row[k]
            return False

        def to_dt(value):
            if not value:
                return False
            try:
                txt = str(value).replace("Z", "").replace("T", " ")
                return txt[:19]
            except Exception:  # noqa: BLE001
                return False

        temperature = (g("temperature") or "").lower() or False
        if temperature not in ("hot", "warm", "cold"):
            temperature = "cold"
        source = (g("source") or "").lower() or "autre"
        _aliases = {
            "facebook_meta": "facebook",
            "instagram_meta": "instagram",
            "instagram_hashtag": "instagram",
        }
        source = _aliases.get(source, source)
        if source not in (
            "reddit",
            "google_alerts",
            "instagram",
            "facebook",
            "facebook_manuel",
            "autre",
        ):
            source = "autre"
        plateforme = g("plateforme", "platform") or source
        marche = (g("marche", "market") or "").lower() or "autre"
        if marche not in ("quebec", "france", "autre"):
            marche = "autre"

        def to_int(value):
            try:
                return int(float(value))
            except (TypeError, ValueError):
                return 0

        ext_raw = g("signal_id_externe", "id", "signal_id", "uuid")
        object_id = g("external_object_id", "meta_object_id", "post_id", "media_id")
        comment_id = g("external_comment_id", "meta_comment_id", "comment_id")
        if not object_id and ext_raw and str(ext_raw).startswith("meta_"):
            object_id = str(ext_raw)[5:]
        vals = {
            "signal_id_externe": str(ext_raw) if ext_raw else False,
            "external_object_id": str(object_id) if object_id else False,
            "external_comment_id": str(comment_id) if comment_id else False,
            "source": source,
            "plateforme": plateforme,
            "auteur": g("auteur", "author") or False,
            "titre": g("titre", "title") or False,
            "texte": (g("texte", "text", "content") or "")[:6000] or False,
            "url": g("url", "link") or False,
            "url_editeur": g("url_editeur", "publisher_url", "source_url") or False,
            "url_enrichie": g("url_enrichie") or False,
            "categorie_lead": g("categorie_lead") or False,
            "reponse_publique": g("reponse_publique") or False,
            "message_prive": g("message_prive") or False,
            "canal_soumission": g("canal_soumission", "auteur") or False,
            "pre_score": to_int(g("pre_score")),
            "score_final": to_int(g("score_final", "score")),
            "score_intention": to_int(g("score_intention")),
            "temperature": temperature,
            "resume": (g("resume", "summary") or "")[:100] or False,
            "type_projet": g("type_projet", "project_type") or False,
            "marche": marche,
            "action_suggeree": g("action_suggeree", "suggested_action") or False,
            "statut": (g("statut", "status") or "en_attente").lower(),
            "date_post": to_dt(g("date_post", "post_date", "created_at")),
            "date_detection": to_dt(g("date_detection", "detected_at")) or fields.Datetime.now(),
        }
        if vals.get("url"):
            from odoo.addons.doorway_veille_sociale.services.url_helpers import (
                unwrap_google_url_redirect,
            )

            vals["url"] = unwrap_google_url_redirect(vals["url"]) or vals["url"]
        if not vals.get("url_editeur") and vals.get("titre"):
            pub_url = VeilleUrlResolver.extract_publisher_url(vals["titre"])
            if pub_url:
                vals["url_editeur"] = pub_url
        return vals

    @api.model
    def upsert_from_payload(self, payload):
        """Crée ou met à jour un signal depuis un dict (webhook ou sync)."""
        vals = self._map_supabase_row(payload)
        from odoo.addons.doorway_veille_sociale.services.media_exclude import (
            is_media_source,
            tag_branche_from_queries,
        )
        if is_media_source(vals) or is_media_source(payload):
            vals["statut"] = "ignore"
            vals["resume"] = ((vals.get("resume") or "") or "Média / presse — exclu de la file.")[:100]
        tagged = (
            payload.get("query_branche")
            or tag_branche_from_queries(payload)
            or tag_branche_from_queries(vals)
        )
        if tagged and vals.get("plateforme") in (False, None, "", "reddit", "google_alerts", "autre"):
            vals["plateforme"] = tagged
        if vals.get("statut") not in (
            "en_attente",
            "repondu",
            "accepte",
            "ignore",
            "cree_odoo",
        ):
            vals["statut"] = "en_attente"
        ext_id = vals.get("signal_id_externe")
        if not ext_id:
            vals.pop("signal_id_externe", None)
        existing = False
        if ext_id:
            existing = self.sudo().search(
                [("signal_id_externe", "=", ext_id)], limit=1
            )
        if existing:
            # Ne pas écraser un statut local plus avancé.
            if existing.statut in ("cree_odoo", "ignore", "accepte", "repondu"):
                vals.pop("statut", None)
            existing.sudo().write(vals)
            existing._maybe_enrich_reddit()
            existing._push_to_supabase()
            return existing
        signal = self.sudo().create(vals)
        signal._maybe_enrich_reddit()
        signal._push_to_supabase()
        return signal

    @api.model
    def sync_from_supabase(self):
        """Cron : tire les signaux 'en_attente' depuis Supabase."""
        cfg = self.env["doorway.veille.config"].get_config()
        if not cfg.actif:
            _logger.info("Veille désactivée — sync ignorée.")
            return 0
        if not cfg.supabase_url or not cfg.supabase_key:
            _logger.warning("Supabase non configuré — sync ignorée.")
            return 0
        url = "%s/rest/v1/veille_signals" % cfg.supabase_url.rstrip("/")
        params = {
            "statut": "eq.en_attente",
            "order": "created_at.desc",
            "limit": "50",
        }
        count = 0
        try:
            response = requests.get(
                url,
                headers=self._supabase_headers(cfg),
                params=params,
                timeout=REQUEST_TIMEOUT,
            )
            if response.status_code != 200:
                _logger.warning(
                    "Sync Supabase: HTTP %s — %s",
                    response.status_code,
                    response.text[:300],
                )
                return 0
            rows = response.json() or []
            for row in rows:
                try:
                    self.upsert_from_payload(row)
                    count += 1
                except Exception:  # noqa: BLE001
                    _logger.exception("Sync Supabase: échec d'un signal")
            _logger.info("Sync Supabase: %s signaux traités.", count)
            self._score_pending_signals_batch()
        except Exception as error:  # noqa: BLE001
            _logger.warning("Sync Supabase impossible: %s", error)
            return 0
        return count

    def _maybe_enrich_reddit(self):
        """Discussions Google Alerts → permalink Reddit, sans écraser url_resolue."""
        for rec in self:
            try:
                from odoo.addons.doorway_veille_sociale.services.reddit_enrich import (
                    enrich_signal,
                )

                enrich_signal(rec)
            except Exception as err:  # noqa: BLE001
                _logger.info("reddit enrich skip %s: %s", rec.id, err)

    @api.model
    def _score_pending_signals_batch(self, limit=20):
        """Score par batch les signaux sans score final (économie API)."""
        pending = self.sudo().search(
            [
                ("statut", "=", "en_attente"),
                ("score_intention", "=", 0),
            ],
            limit=limit,
            order="date_detection desc",
        )
        if not pending:
            return 0
        try:
            from odoo.addons.doorway_veille_sociale.services.scoring_service import (
                VeilleScoringService,
            )

            return VeilleScoringService(self.env).apply_scores_to_records(pending)
        except ImportError:
            _logger.warning("doorway_agents_ia requis pour le scoring batch.")
            return 0

    def _push_status_to_supabase(self, statut):
        """Répercute le statut local vers Supabase (best-effort)."""
        self.ensure_one()
        if not self.signal_id_externe:
            return False
        cfg = self.env["doorway.veille.config"].get_config()
        if not cfg.supabase_url or not cfg.supabase_key:
            return False
        url = "%s/rest/v1/veille_signals" % cfg.supabase_url.rstrip("/")
        try:
            headers = self._supabase_headers(cfg)
            headers["Prefer"] = "return=minimal"
            requests.patch(
                url,
                headers=headers,
                params={"id": "eq.%s" % self.signal_id_externe},
                data=json.dumps({"statut": statut, "updated_at": fields.Datetime.now()}),
                timeout=REQUEST_TIMEOUT,
            )
        except Exception as error:  # noqa: BLE001
            _logger.warning("Push statut Supabase impossible: %s", error)
            return False
        return True

    def _to_supabase_row(self):
        """Convertit un signal Odoo en ligne Supabase."""
        self.ensure_one()
        ext = self.signal_id_externe or "odoo_%s" % self.id
        row = {
            "id": ext,
            "source": self.source or "autre",
            "plateforme": self.plateforme or self.source or "autre",
            "titre": self.titre or None,
            "texte": (self.texte or "")[:6000] or None,
            "url": self.url or None,
            "url_enrichie": self.url_enrichie or None,
            "categorie_lead": self.categorie_lead or None,
            "reponse_publique": self.reponse_publique or None,
            "message_prive": self.message_prive or None,
            "auteur": self.auteur or self.canal_soumission or None,
            "pre_score": self.pre_score or 0,
            "score_final": self.score_final or 0,
            "score_intention": self.score_intention or 0,
            "temperature": self.temperature or "cold",
            "resume": self.resume or None,
            "type_projet": self.type_projet or None,
            "marche": self.marche or "quebec",
            "action_suggeree": self.action_suggeree or None,
            "statut": self.statut or "en_attente",
        }
        if self.date_post:
            row["date_post"] = str(self.date_post)
        if self.date_detection:
            row["date_detection"] = str(self.date_detection)
        return row

    def _push_to_supabase(self):
        """Archive le signal dans Supabase (upsert)."""
        cfg = self.env["doorway.veille.config"].get_config()
        if not cfg.supabase_url or not cfg.supabase_key:
            return False
        for rec in self:
            row = rec._to_supabase_row()
            if not row.get("id"):
                continue
            url = "%s/rest/v1/veille_signals" % cfg.supabase_url.rstrip("/")
            try:
                headers = rec._supabase_headers(cfg)
                headers["Prefer"] = "resolution=merge-duplicates,return=minimal"
                response = requests.post(
                    url,
                    headers=headers,
                    data=json.dumps(row),
                    timeout=REQUEST_TIMEOUT,
                )
                if response.status_code not in (200, 201, 204):
                    _logger.warning(
                        "Push Supabase HTTP %s: %s",
                        response.status_code,
                        response.text[:300],
                    )
                    return False
            except Exception as error:  # noqa: BLE001
                _logger.warning("Push Supabase impossible: %s", error)
                return False
        return True

    def _create_crm_lead(self, pipeline_type="renovation", assign_user=None, name=None, notes=None, priorite=None):
        """Crée un lead CRM depuis le signal (logique partagée wizard / auto)."""
        self.ensure_one()
        signal = self
        if signal.statut == "cree_odoo" and signal.odoo_lead_id:
            return signal.odoo_lead_id

        PIPELINE_TEAM_XMLIDS = {
            "renovation": "renovation_conciergerie.crm_team_renovation",
            "driven": "renovation_conciergerie.crm_team_driven",
            "marketing": "renovation_conciergerie.crm_team_marketing",
        }
        STAGE_VEILLE_NAME = "Nouveau lead — Veille sociale"
        STAGE_FALLBACK_NAME = "Réseaux Sociaux"

        xmlid = PIPELINE_TEAM_XMLIDS.get(pipeline_type, PIPELINE_TEAM_XMLIDS["renovation"])
        team = self.env.ref(xmlid, raise_if_not_found=False)
        if not team:
            team = self.env["crm.team"].search([], limit=1)
        if not team:
            raise UserError(_("Aucune équipe CRM disponible."))

        Stage = self.env["crm.stage"].sudo()
        stage = False
        for name in (STAGE_VEILLE_NAME, STAGE_FALLBACK_NAME):
            stage = Stage.search([("name", "=", name), ("team_ids", "in", team.id)], limit=1)
            if stage:
                break
        if not stage:
            stage = Stage.search([("team_ids", "in", team.id)], order="sequence", limit=1)

        nom = name or signal.auteur or signal.titre or _("Prospect veille")
        if priorite is None:
            priorite = "3" if signal.temperature == "hot" else "2" if signal.temperature == "warm" else "0"
        notes_parts = []
        if notes:
            notes_parts.append(notes)
        elif signal.resume:
            notes_parts.append(signal.resume)
        if not notes and signal.action_suggeree:
            notes_parts.append(signal.action_suggeree)

        lead_vals = {
            "name": nom,
            "type": "opportunity",
            "team_id": team.id,
            "stage_id": stage.id if stage else False,
            "priority": priorite,
            "description": "\n".join(notes_parts) or False,
            "user_id": (assign_user or self.env.user).id,
        }
        if signal.type_projet:
            if "x_type_projet" in self.env["crm.lead"]._fields:
                lead_vals["x_type_projet"] = signal.type_projet

        lead = self.env["crm.lead"].create(lead_vals)
        body_parts = ["<p><b>Lead créé depuis la veille sociale</b></p>"]
        if signal.resume:
            body_parts.append("<p><b>Résumé IA :</b> %s</p>" % signal.resume)
        if signal.texte:
            body_parts.append("<p><b>Texte original :</b><br/>%s</p>" % (signal.texte or ""))
        if signal.url:
            body_parts.append('<p><a href="%s" target="_blank">Source</a></p>' % signal.url)
        if signal.plateforme or signal.source:
            body_parts.append(
                "<p><b>Source :</b> %s / %s</p>"
                % (signal.plateforme or "", signal.source or "")
            )
        from markupsafe import Markup
        lead.message_post(body=Markup("".join(body_parts)), message_type="comment")

        signal.write({"statut": "cree_odoo", "odoo_lead_id": lead.id})
        signal._push_status_to_supabase("cree_odoo")
        return lead

    def auto_create_lead_if_hot(self):
        """Crée un lead si configuré, score >= seuil et signal accepté (post-triage)."""
        cfg = self.env["doorway.veille.config"].get_config()
        if not cfg.auto_lead_actif:
            return self.env["crm.lead"]
        created = self.env["crm.lead"]
        min_score = cfg.auto_lead_score_min or cfg.seuil_score_hot or 8
        for rec in self.filtered(
            lambda s: s.statut == "accepte"
            and not s.odoo_lead_id
            and (s.score_final or s.pre_score or 0) >= min_score
        ):
            try:
                created |= rec._create_crm_lead()
            except Exception:  # noqa: BLE001
                _logger.exception("Auto-lead veille: échec signal %s", rec.id)
        return created

    # ------------------------------------------------------------------
    # Refroidissement & réactivation douce
    # ------------------------------------------------------------------
    def _age_heures(self):
        self.ensure_one()
        if not self.date_detection:
            return 0
        delta = fields.Datetime.now() - self.date_detection
        return delta.total_seconds() / 3600.0

    def _apply_refroidissement_vals(self, cfg, now=None):
        """Calcule température et éligibilité réactivation selon l'âge."""
        self.ensure_one()
        now = now or fields.Datetime.now()
        hot_h = cfg.refroidissement_hot_heures or 24
        warm_h = cfg.refroidissement_warm_heures or 72
        age_h = self._age_heures()
        vals = {}
        if age_h >= warm_h:
            if self.temperature != "cold":
                vals["temperature"] = "cold"
            if not self.date_refroidi:
                vals["date_refroidi"] = now
            if self.reactivation_statut in (False, "none"):
                vals["reactivation_statut"] = "eligible"
        elif age_h >= hot_h and self.temperature == "hot":
            vals["temperature"] = "warm"
        return vals

    @api.model
    def cron_refroidir_signaux(self):
        """Cron : refroidit les signaux non ignorés sans action."""
        cfg = self.env["doorway.veille.config"].get_config()
        if not cfg.refroidissement_actif:
            return 0
        now = fields.Datetime.now()
        candidates = self.search(
            [("statut", "in", ["en_attente", "repondu", "accepte"])]
        )
        updated = 0
        for rec in candidates:
            vals = rec._apply_refroidissement_vals(cfg, now=now)
            if vals:
                rec.write(vals)
                updated += 1
        return updated

    @api.model
    def _ensure_default_reactivation_automations(self):
        """Crée les règles par défaut si absentes."""
        Automation = self.env["doorway.veille.reactivation.automation"].sudo()
        defaults = [
            {
                "name": "Réponse douce — Reddit",
                "action_type": "reponse_douce",
                "source_filtre": "reddit",
                "delay_jours": 3,
            },
            {
                "name": "Like / Upvote — Reddit",
                "action_type": "like",
                "source_filtre": "reddit",
                "delay_jours": 1,
            },
            {
                "name": "Réponse douce — Meta (FB/IG)",
                "action_type": "reponse_douce",
                "source_filtre": "facebook",
                "delay_jours": 3,
            },
            {
                "name": "Like — Meta (FB/IG)",
                "action_type": "like",
                "source_filtre": "facebook",
                "delay_jours": 1,
            },
            {
                "name": "Tâche de suivi — signal froid",
                "action_type": "tache",
                "source_filtre": "all",
                "delay_jours": 7,
                "tache_nom": "Réactivation douce — relire le signal veille",
            },
        ]
        for spec in defaults:
            if not Automation.search([("name", "=", spec["name"])], limit=1):
                Automation.create(spec)
        return Automation.search([])

    @api.model
    def _default_automation_for_signal(self, signal, automations):
        """Choisit une règle par défaut selon la source."""
        if signal.source == "reddit":
            return automations.filtered(
                lambda a: a.source_filtre == "reddit"
                and a.action_type == "reponse_douce"
            )[:1]
        if signal.source in ("facebook", "instagram"):
            return automations.filtered(
                lambda a: a.source_filtre == "facebook"
                and a.action_type == "reponse_douce"
            )[:1]
        return automations.filtered(
            lambda a: a.source_filtre == "all" and a.action_type == "tache"
        )[:1]

    @api.model
    def migrate_signaux_reactivation(self):
        """Migration : intègre les signaux existants dans le modèle réactivation."""
        cfg = self.env["doorway.veille.config"].get_config()
        automations = self._ensure_default_reactivation_automations()
        now = fields.Datetime.now()

        candidates = self.search(
            [("statut", "in", ["en_attente", "repondu", "accepte"])]
        )
        migrated = 0
        for rec in candidates:
            vals = rec._apply_refroidissement_vals(cfg, now=now)
            if rec.reactivation_statut in (False, "none"):
                vals["reactivation_statut"] = "eligible"
            if not rec.date_refroidi:
                vals.setdefault("date_refroidi", now)
            if not rec.reactivation_automation_id:
                auto = self._default_automation_for_signal(rec, automations)
                if auto:
                    vals["reactivation_automation_id"] = auto.id
            rec.write(vals)
            migrated += 1
        _logger.info(
            "Veille réactivation : %s signaux migrés sur %s candidats.",
            migrated,
            len(candidates),
        )
        return migrated

    def action_reactivation_douce(self):
        """Ouvre l'assistant de réactivation douce."""
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": _("Réactivation douce"),
            "res_model": "doorway.reactivation.douce.wizard",
            "view_mode": "form",
            "target": "new",
            "context": {"default_signal_id": self.id},
        }

    def action_assigner_automatisation(self):
        """Assigne la règle par défaut et marque éligible."""
        self.ensure_one()
        automations = self._ensure_default_reactivation_automations()
        auto = self._default_automation_for_signal(self, automations)
        vals = {"reactivation_statut": "eligible"}
        if auto:
            vals["reactivation_automation_id"] = auto.id
        if self.temperature != "cold":
            vals.update(
                self._apply_refroidissement_vals(
                    self.env["doorway.veille.config"].get_config()
                )
            )
        self.write(vals)
        return True

    def _executer_reactivation(self, automation, message_override=None):
        """Exécute une action de réactivation douce."""
        self.ensure_one()
        action = automation.action_type
        cfg = self.env["doorway.veille.config"].get_config()

        if action == "like":
            result = self._send_reactivation_like()
            if result.get("manual"):
                self.message_post(
                    body=_("Like enregistré — effectuez-le manuellement sur la plateforme."),
                    subtype_xmlid="mail.mt_note",
                )
        elif action == "reponse_douce":
            text = (message_override or automation.message_modele or "").strip()
            result = self._send_reactivation_reply(text)
            if result.get("manual"):
                self.message_post(
                    body=_(
                        "Réponse enregistrée dans Odoo — publiez-la manuellement "
                        "sur la plateforme via le lien source."
                    ),
                    subtype_xmlid="mail.mt_note",
                )
        elif action == "tache":
            self.action_planifier_reponse()
            result = {"ok": True}
        elif action == "notification":
            user = automation.notify_user_id or self.env.user
            self.activity_schedule(
                "mail.mail_activity_data_todo",
                user_id=user.id,
                summary=_("Réactivation douce — signal veille"),
                note=self.resume or self.titre or self.url or "",
            )
            result = {"ok": True}
        else:
            raise UserError(_("Type d'action inconnu."))

        if action not in ("reponse_douce", "like") and not result.get("ok"):
            raise UserError(result.get("message") or _("Échec réactivation."))

        self.write(
            {
                "reactivation_statut": "effectue",
                "reactivation_derniere_action": action,
                "reactivation_automation_id": automation.id,
            }
        )
        self.message_post(
            body=_("<p><b>Réactivation douce</b> — %s</p>") % automation.name,
            subtype_xmlid="mail.mt_note",
        )
        return True

    @api.model
    def cron_reactivation_planifiee(self):
        """Exécute les réactivations planifiées manuellement (date échue)."""
        now = fields.Datetime.now()
        executed = 0
        planned = self.search(
            [
                ("reactivation_statut", "=", "planifie"),
                ("reactivation_planifiee", "<=", now),
                ("statut", "in", ["en_attente", "repondu", "accepte"]),
            ]
        )
        for sig in planned:
            automation = sig.reactivation_automation_id
            if not automation:
                continue
            try:
                sig._executer_reactivation(automation)
                executed += 1
            except Exception:  # noqa: BLE001
                _logger.exception(
                    "Réactivation planifiée échouée signal %s", sig.id
                )
        return executed

    @api.model
    def cron_reactivation_douce(self):
        """Cron : planifiées + automatisations marquées auto."""
        executed = self.cron_reactivation_planifiee()
        cfg = self.env["doorway.veille.config"].get_config()
        if not cfg.reactivation_auto_actif:
            return executed
        from datetime import timedelta

        Automation = self.env["doorway.veille.reactivation.automation"]
        rules = Automation.search([("active", "=", True), ("auto_executer", "=", True)])
        if not rules:
            return executed

        now = fields.Datetime.now()
        for rule in rules:
            deadline = now - timedelta(days=rule.delay_jours or 0)
            domain = [
                ("reactivation_statut", "=", "eligible"),
                ("temperature", "=", "cold"),
                ("statut", "in", ["en_attente", "repondu", "accepte"]),
                ("date_refroidi", "<=", deadline),
            ]
            if rule.source_filtre != "all":
                domain.append(("source", "=", rule.source_filtre))
            for sig in self.search(domain):
                if not rule._match_signal(sig):
                    continue
                try:
                    sig._executer_reactivation(rule)
                    executed += 1
                except Exception:  # noqa: BLE001
                    _logger.exception(
                        "Réactivation auto échouée signal %s règle %s",
                        sig.id,
                        rule.id,
                    )
        return executed

    @api.model
    def cron_resoudre_urls(self):
        """Met en cache les URLs ouvrables pour les signaux sans url_resolue."""
        pending = self.search(
            [
                ("url_resolue", "=", False),
                "|",
                ("url", "!=", False),
                ("titre", "!=", False),
            ],
            limit=100,
        )
        count = 0
        for rec in pending:
            try:
                resolved = rec._get_open_url(cache=True)
                if resolved:
                    count += 1
            except Exception:  # noqa: BLE001
                _logger.exception("Résolution URL signal %s", rec.id)
        return count

    @api.model
    def migrate_resoudre_urls(self):
        """Backfill url_editeur + url_resolue sur tous les signaux."""
        signals = self.search([])
        updated = 0
        for rec in signals:
            vals = {}
            if not rec.url_editeur and rec.titre:
                pub = VeilleUrlResolver.extract_publisher_url(rec.titre)
                if pub:
                    vals["url_editeur"] = pub
            if vals:
                rec.write(vals)
            try:
                rec._get_open_url(cache=True)
                updated += 1
            except Exception:  # noqa: BLE001
                pass
        return updated

    # ------------------------------------------------------------------
    # Alerte Hot
    # ------------------------------------------------------------------
    def _notify_hot(self):
        """Envoie un email d'alerte pour les signaux 'hot'."""
        cfg = self.env["doorway.veille.config"].get_config()
        email = cfg.email_alerte_hot
        if not email:
            return False
        for rec in self.filtered(lambda s: s.temperature == "hot"):
            subject = _("🔥 Signal HOT détecté : %s") % (rec.resume or rec.titre or "")
            body = rec._build_task_description() or "<p>Nouveau signal hot.</p>"
            try:
                self.env["mail.mail"].sudo().create(
                    {
                        "subject": subject,
                        "body_html": body,
                        "email_to": email,
                        "auto_delete": True,
                    }
                ).send()
            except Exception:  # noqa: BLE001
                _logger.exception("Alerte hot: envoi email impossible")
        return True

    @api.model
    def collect_tagged_queries(self):
        """Collecte Reddit taguée Coins Marocain / Coins Québec."""
        from odoo.addons.doorway_veille_sociale.services.query_collect import (
            collect_tagged_payloads,
        )
        from odoo.addons.doorway_veille_sociale.services.reddit_service import (
            RedditService,
        )
        cfg = self.env["doorway.veille.config"].get_config()
        svc = RedditService(self.env)
        headers = None
        oauth = False
        try:
            token = svc._access_token(cfg)
            if token:
                headers = svc._auth_headers(cfg, token)
                oauth = True
        except Exception:
            _logger.warning("collect_tagged_queries: OAuth Reddit indisponible, essai public")
        count = 0
        for payload in collect_tagged_payloads(headers=headers, oauth=oauth):
            try:
                self.upsert_from_payload(payload)
                count += 1
            except Exception:
                _logger.exception("collect_tagged_queries: échec d un signal")
        return count
