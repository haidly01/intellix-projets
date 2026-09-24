# -*- coding: utf-8 -*-
import json
import logging
import secrets
import subprocess
import time

import requests

from odoo import _, api, fields, models
from odoo.exceptions import UserError

from odoo.addons.doorway_veille_sociale.services.meta_service import MetaGraphService
from odoo.addons.doorway_veille_sociale.services.reddit_service import RedditService

_logger = logging.getLogger(__name__)


class VeilleConfig(models.Model):
    _name = "doorway.veille.config"
    _description = "Configuration Veille Sociale Doorway"

    name = fields.Char(default="Configuration Veille", required=True)
    actif = fields.Boolean(string="Veille active", default=True)
    marche_quebec = fields.Boolean(string="Marché Québec", default=True)
    marche_france = fields.Boolean(string="Marché France", default=False)

    supabase_url = fields.Char(
        string="URL Supabase",
        default="https://supabase.intellixcrm.com",
    )
    supabase_key = fields.Char(string="Clé Supabase (service_role)")
    anthropic_api_key = fields.Char(string="Clé API Anthropic")
    anthropic_model = fields.Char(
        string="Modèle Claude", default="claude-sonnet-4-6"
    )
    n8n_webhook_url = fields.Char(
        string="URL Webhook n8n (sortant)",
        default="https://n8n.intellixcrm.com/webhook/meta-veille",
        help="Instance n8n self-hosted (workflows veille).",
    )

    webhook_token = fields.Char(
        string="Token Webhook entrant (X-Doorway-Token)", copy=False
    )
    webhook_url_entrant = fields.Char(
        string="URL Webhook à configurer dans n8n",
        compute="_compute_webhook_url_entrant",
    )

    seuil_score_hot = fields.Integer(string="Seuil score Hot", default=8)
    seuil_score_warm = fields.Integer(string="Seuil score Warm", default=4)
    email_alerte_hot = fields.Char(
        string="Email alerte Hot", default="comptabilite@agencedoorway.com"
    )

    auto_lead_actif = fields.Boolean(
        string="Créer lead CRM auto (après acceptation)",
        default=False,
        help="Crée un lead CRM uniquement lorsque vous cliquez « Qualifier (opportunité) » "
        "sur un signal dont le score atteint le seuil. Répondre au signal ne déclenche "
        "jamais de lead automatique.",
    )
    auto_lead_score_min = fields.Integer(
        string="Seuil score auto-lead", default=8,
    )

    refroidissement_actif = fields.Boolean(
        string="Refroidissement automatique",
        default=True,
        help="Les signaux non ignorés passent progressivement de Hot → Warm → Cold "
        "selon leur âge sans action.",
    )
    refroidissement_hot_heures = fields.Integer(
        string="Hot → Warm (heures)",
        default=24,
    )
    refroidissement_warm_heures = fields.Integer(
        string="Warm → Cold (heures)",
        default=72,
    )
    reactivation_auto_actif = fields.Boolean(
        string="Réactivation douce automatique",
        default=False,
        help="Exécute les règles d'automatisation marquées « Exécution automatique » "
        "sur les signaux froids éligibles.",
    )
    instagram_hashtags = fields.Char(
        string="Hashtags Instagram (veille)",
        default="renovationquebec,couvreur,thermopompe,soumissionreno,toiturequebec",
        help="Liste séparée par virgules — utilisée par n8n Phase 3.",
    )

    # Connexions réseaux sociaux (credentials utilisés par n8n — pas d'OAuth direct dans Odoo)
    facebook_actif = fields.Boolean(string="Facebook / Meta connecté", default=False)
    facebook_page_id = fields.Char(string="ID page Facebook")
    instagram_actif = fields.Boolean(string="Instagram connecté", default=False)
    instagram_account_id = fields.Char(string="ID compte Instagram")
    reddit_actif = fields.Boolean(string="Reddit actif", default=False)
    reddit_subreddit = fields.Char(string="Subreddit surveillé", default="renovation+quebec")
    reddit_client_id = fields.Char(string="Reddit — Client ID")
    reddit_client_secret = fields.Char(
        string="Reddit — Client secret",
        groups="doorway_veille_sociale.group_veille_settings,base.group_system",
    )
    reddit_username = fields.Char(string="Reddit — Nom d'utilisateur")
    reddit_password = fields.Char(
        string="Reddit — Mot de passe / app password",
        groups="doorway_veille_sociale.group_veille_settings,base.group_system",
    )
    reddit_refresh_token = fields.Char(
        string="Reddit — Refresh token (recommandé)",
        groups="doorway_veille_sociale.group_veille_settings,base.group_system",
        help="Généré automatiquement via « Obtenir refresh token ».",
    )
    reddit_refresh_token_status = fields.Char(
        string="État refresh token",
        compute="_compute_reddit_refresh_token_status",
        readonly=True,
    )
    reddit_user_agent = fields.Char(
        string="Reddit — User-Agent",
        default="IntellixCRM/1.0 by /u/digital_doorway",
    )
    reddit_oauth_redirect_uri = fields.Char(
        string="Redirect URI OAuth Reddit",
        help="À copier dans l'app Reddit (type web). Laisser vide pour l'URL par défaut Odoo.",
    )
    reddit_last_check = fields.Datetime(string="Dernière vérif. Reddit", readonly=True)
    reddit_status_message = fields.Text(string="Résultat vérif. Reddit", readonly=True)

    google_alerts_actif = fields.Boolean(string="Google Alerts actif", default=False)
    google_alerts_email = fields.Char(
        string="Email Google Alerts",
        help="Boîte qui reçoit les alertes Google (traitée par n8n).",
    )
    google_alerts_mots_cles = fields.Text(
        string="Mots-clés Google Alerts",
        default="rénovation Québec\nthermopompe Québec\nsoumission rénovation",
    )

    meta_access_token = fields.Char(
        string="Token Meta (long-lived)",
        help="Utilisé par n8n et pour la validation Graph API — ne pas partager.",
    )
    meta_facebook_name = fields.Char(string="Nom page Facebook (vérif.)", readonly=True)
    meta_instagram_username = fields.Char(
        string="Compte Instagram (vérif.)", readonly=True
    )
    meta_last_check = fields.Datetime(string="Dernière vérif. Meta", readonly=True)
    meta_status_message = fields.Text(string="Résultat vérif. Meta", readonly=True)
    notes_connexions = fields.Html(string="Notes connexions")

    connexion_meta_ok = fields.Boolean(
        string="Meta OK", compute="_compute_connexion_status"
    )
    connexion_google_ok = fields.Boolean(
        string="Google Alerts OK", compute="_compute_connexion_status"
    )
    connexion_webhook_ok = fields.Boolean(
        string="Webhook configuré", compute="_compute_connexion_status"
    )
    connexion_reddit_ok = fields.Boolean(
        string="Reddit réponse OK", compute="_compute_connexion_status"
    )

    count_hot = fields.Integer(compute="_compute_dashboard_counts")
    count_warm = fields.Integer(compute="_compute_dashboard_counts")
    count_cold = fields.Integer(compute="_compute_dashboard_counts")
    count_total = fields.Integer(compute="_compute_dashboard_counts")
    count_en_attente = fields.Integer(compute="_compute_dashboard_counts")
    count_reactivation = fields.Integer(compute="_compute_dashboard_counts")

    @api.depends("reddit_refresh_token")
    def _compute_reddit_refresh_token_status(self):
        for rec in self:
            token = (rec.reddit_refresh_token or "").strip()
            if not token:
                rec.reddit_refresh_token_status = _("Non configuré")
            elif len(token) < 100:
                rec.reddit_refresh_token_status = _(
                    "Invalide (%s car.) — regénérez via « Obtenir refresh token »"
                ) % len(token)
            else:
                rec.reddit_refresh_token_status = _(
                    "Configuré (%s caractères)"
                ) % len(token)

    @api.depends(
        "facebook_actif",
        "instagram_actif",
        "google_alerts_actif",
        "google_alerts_email",
        "webhook_token",
        "meta_access_token",
        "facebook_page_id",
        "instagram_account_id",
        "reddit_client_id",
        "reddit_client_secret",
        "reddit_username",
        "reddit_password",
        "reddit_refresh_token",
        "reddit_actif",
    )
    def _compute_connexion_status(self):
        svc = RedditService(self.env)
        for rec in self:
            rec.connexion_meta_ok = bool(
                rec.meta_access_token
                and rec.facebook_page_id
                and rec.instagram_account_id
                and (rec.facebook_actif or rec.instagram_actif)
            )
            rec.connexion_google_ok = bool(
                rec.google_alerts_actif and rec.google_alerts_email
            )
            rec.connexion_webhook_ok = bool(rec.webhook_token)
            rec.connexion_reddit_ok = bool(
                rec.reddit_actif and svc.credentials_ok(rec)
            )

    @api.depends_context("uid")
    def _compute_dashboard_counts(self):
        Signal = self.env["doorway.veille.signal"]
        for rec in self:
            base = Signal.search([("statut", "=", "en_attente")])
            rec.count_hot = len(base.filtered(lambda s: s.temperature == "hot"))
            rec.count_warm = len(base.filtered(lambda s: s.temperature == "warm"))
            rec.count_cold = len(base.filtered(lambda s: s.temperature == "cold"))
            rec.count_en_attente = len(base)
            rec.count_reactivation = Signal.search_count(
                [
                    ("statut", "in", ["en_attente", "repondu", "accepte"]),
                    ("reactivation_statut", "in", ["eligible", "planifie"]),
                ]
            )
            rec.count_total = Signal.search_count([])

    @api.depends("webhook_token")
    def _compute_webhook_url_entrant(self):
        base = (
            self.env["ir.config_parameter"].sudo().get_param("web.base.url") or ""
        )
        for rec in self:
            rec.webhook_url_entrant = "%s/doorway/veille/webhook" % (base or "")

    @api.model
    def get_config(self):
        """Renvoie l'enregistrement de configuration unique (le crée si besoin)."""
        cfg = self.sudo().search([], limit=1)
        if not cfg:
            cfg = self.sudo().create({"name": "Configuration Veille"})
        if not cfg.webhook_token:
            cfg.sudo().webhook_token = secrets.token_hex(16)
        cfg.sudo()._sync_source_flags()
        return cfg

    def _sync_source_flags(self):
        """Active les sources lorsque les identifiants requis sont renseignés."""
        for rec in self:
            updates = {}
            token = (rec.meta_access_token or "").strip()
            if token and rec.facebook_page_id and not rec.facebook_actif:
                updates["facebook_actif"] = True
            if token and rec.instagram_account_id and not rec.instagram_actif:
                updates["instagram_actif"] = True
            if (rec.google_alerts_email or "").strip() and not rec.google_alerts_actif:
                updates["google_alerts_actif"] = True
            if updates:
                rec.sudo().write(updates)

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        records.sudo()._sync_source_flags()
        return records

    def write(self, vals):
        res = super().write(vals)
        trigger = {
            "meta_access_token",
            "facebook_page_id",
            "instagram_account_id",
            "google_alerts_email",
        }
        if trigger.intersection(vals.keys()):
            self.sudo()._sync_source_flags()
        return res

    def action_regenerate_token(self):
        self.ensure_one()
        self.webhook_token = secrets.token_hex(16)
        return True

    @api.model
    def action_open_sources(self):
        """Ouvre la fiche connexions (réseaux + Google Alerts)."""
        cfg = self.get_config()
        view = self.env.ref(
            "doorway_veille_sociale.view_veille_config_sources",
            raise_if_not_found=False,
        )
        action = {
            "type": "ir.actions.act_window",
            "name": "Connexions & sources",
            "res_model": "doorway.veille.config",
            "res_id": cfg.id,
            "view_mode": "form",
            "target": "current",
        }
        if view:
            action["views"] = [(view.id, "form")]
            action["view_id"] = view.id
        return action

    @api.model
    def action_open_settings(self):
        cfg = self.get_config()
        view = self.env.ref(
            "doorway_veille_sociale.view_veille_config_form",
            raise_if_not_found=False,
        )
        action = {
            "type": "ir.actions.act_window",
            "name": "Paramètres veille",
            "res_model": "doorway.veille.config",
            "view_mode": "form",
            "res_id": cfg.id,
            "target": "current",
        }
        if view:
            action["views"] = [(view.id, "form")]
            action["view_id"] = view.id
        return action

    @api.model
    def action_open_dashboard(self):
        cfg = self.get_config()
        view = self.env.ref(
            "doorway_veille_sociale.view_veille_config_dashboard",
            raise_if_not_found=False,
        )
        action = {
            "type": "ir.actions.act_window",
            "name": "Tableau de bord veille",
            "res_model": "doorway.veille.config",
            "res_id": cfg.id,
            "view_mode": "form",
            "target": "current",
        }
        if view:
            action["views"] = [(view.id, "form")]
            action["view_id"] = view.id
        return action

    def get_anthropic_credentials(self):
        """Renvoie (api_key, model) avec repli sur la config du module rénovation."""
        self.ensure_one()
        api_key = self.anthropic_api_key
        if not api_key:
            api_key = (
                self.env["ir.config_parameter"]
                .sudo()
                .get_param("renovation_conciergerie.anthropic_api_key", "")
            )
        model = self.anthropic_model or "claude-sonnet-4-6"
        return api_key or "", model

    def action_test_meta_connection(self):
        """Valide token + page Facebook + compte Instagram via Graph API."""
        self.ensure_one()
        if not self.meta_access_token:
            raise UserError(_("Renseignez le token Meta dans Connexions & sources."))
        svc = MetaGraphService(self.env)
        result = svc.validate_config(self)
        self.sudo().write(
            {
                "meta_last_check": fields.Datetime.now(),
                "meta_facebook_name": result.get("facebook_name") or False,
                "meta_instagram_username": result.get("instagram_username") or False,
                "meta_status_message": "\n".join(result.get("messages") or []),
                "facebook_actif": result.get("facebook_ok", False),
                "instagram_actif": result.get("instagram_ok", False),
            }
        )
        ok = result.get("facebook_ok") and result.get("instagram_ok")
        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": _("Meta") if ok else _("Meta — vérification"),
                "message": "\n".join(result.get("messages") or [_("Terminé.")]),
                "type": "success" if ok else "warning",
                "sticky": not ok,
            },
        }

    def action_test_reddit_connection(self):
        """Valide OAuth Reddit pour lecture + réponse aux posts."""
        self.ensure_one()
        svc = RedditService(self.env)
        if not svc.credentials_ok(self):
            raise UserError(
                _(
                    "Renseignez Client ID, secret et refresh token (ou compte Reddit) "
                    "dans Connexions & sources."
                )
            )
        result = svc.validate_config(self)
        self.sudo().write(
            {
                "reddit_last_check": fields.Datetime.now(),
                "reddit_status_message": "\n".join(result.get("messages") or []),
                "reddit_actif": result.get("ok", False),
            }
        )
        ok = result.get("ok")
        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": _("Reddit") if ok else _("Reddit — vérification"),
                "message": "\n".join(result.get("messages") or [_("Terminé.")]),
                "type": "success" if ok else "warning",
                "sticky": not ok,
            },
        }

    def action_connect_reddit_oauth(self):
        """Redirige vers Reddit pour autoriser l'accès (sans mot de passe Odoo)."""
        self.ensure_one()
        svc = RedditService(self.env)
        if not (self.reddit_client_id or "").strip():
            raise UserError(_("Renseignez le Client ID Reddit (app type « web app »)."))
        if not (self.reddit_client_secret or "").strip():
            raise UserError(_("Renseignez le secret Reddit."))
        redirect = svc.get_redirect_uri(self)
        if not redirect.startswith("https://"):
            raise UserError(
                _(
                    "Le redirect URI doit être en HTTPS : %s"
                )
                % redirect
            )
        state = secrets.token_hex(16)
        session = svc.store_oauth_state(state, self.env.uid, self)
        url = svc.build_authorize_url(self, session)
        if not url:
            raise UserError(_("Impossible de construire l'URL OAuth Reddit."))
        return {
            "type": "ir.actions.act_url",
            "url": url,
            "target": "new",
        }

    def action_open_reddit_oauth_link(self):
        """Ouvre le lien Reddit dans un nouvel onglet (même flux que Connecter)."""
        return self.action_connect_reddit_oauth()

    def action_paste_reddit_oauth_code(self):
        """Échange manuel du code si le retour automatique échoue."""
        self.ensure_one()
        svc = RedditService(self.env)
        wizard = self.env["doorway.reddit.oauth.code.wizard"].create(
            {"redirect_uri": svc.get_redirect_uri(self)}
        )
        return {
            "type": "ir.actions.act_window",
            "name": _("Code OAuth Reddit"),
            "res_model": "doorway.reddit.oauth.code.wizard",
            "view_mode": "form",
            "res_id": wizard.id,
            "target": "new",
        }

    def action_obtain_reddit_refresh_token(self):
        """Génère et enregistre un refresh token (app script + mot de passe)."""
        self.ensure_one()
        result = RedditService(self.env).obtain_refresh_token(self)
        if not result.get("ok"):
            raise UserError(result.get("message") or _("Échec OAuth Reddit."))
        sync_msg = self._run_reddit_n8n_sync()
        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": _("Reddit — refresh token"),
                "message": "%s\n%s" % (result.get("message"), sync_msg),
                "type": "success",
                "sticky": False,
            },
        }

    def action_sync_reddit_to_n8n(self):
        """Copie les identifiants Reddit vers /opt/n8n/.env."""
        self.ensure_one()
        msg = self._run_reddit_n8n_sync()
        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": _("Reddit → n8n"),
                "message": msg,
                "type": "success",
                "sticky": False,
            },
        }

    def _run_reddit_n8n_sync(self):
        script = "/opt/n8n/workflows/sync_reddit_from_odoo.sh"
        try:
            proc = subprocess.run(
                [script],
                capture_output=True,
                text=True,
                timeout=60,
                check=False,
            )
            out = (proc.stdout or proc.stderr or "").strip()
            if proc.returncode != 0:
                _logger.warning("Reddit n8n sync failed: %s", out)
                return _("Sync n8n échouée : %s") % (out[:500] or proc.returncode)
            return out or _("Sync n8n terminée.")
        except (OSError, subprocess.TimeoutExpired) as exc:
            _logger.warning("Reddit n8n sync: %s", exc)
            return _("Sync n8n impossible : %s") % exc

    def action_test_webhook(self):
        """Envoie un signal test vers le webhook public Odoo."""
        self.ensure_one()
        if not self.webhook_token:
            raise UserError(_("Générez d'abord le token webhook (Paramètres veille)."))
        url = self.webhook_url_entrant
        if not url:
            raise UserError(_("URL de base Odoo (web.base.url) non configurée."))
        payload = {
            "source": "test_odoo",
            "plateforme": "odoo",
            "titre": "Test connexion webhook veille",
            "texte": "Signal de test envoyé depuis Odoo (Connexions & sources).",
            "auteur": self.env.user.name,
            "url": url,
            "marche": "quebec",
        }
        try:
            response = requests.post(
                url,
                json=payload,
                headers={
                    "Content-Type": "application/json",
                    "X-Doorway-Token": self.webhook_token,
                },
                timeout=30,
            )
            body = response.json() if response.content else {}
        except requests.RequestException as exc:
            raise UserError(_("Échec appel webhook : %s") % exc) from exc
        if response.status_code != 200 or body.get("status") != "ok":
            raise UserError(
                _("Webhook HTTP %(code)s : %(msg)s")
                % {
                    "code": response.status_code,
                    "msg": body.get("message") or response.text[:200],
                }
            )
        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": _("Webhook OK"),
                "message": _("Signal test créé (ID Odoo : %s).") % body.get("signal_id"),
                "type": "success",
            },
        }

    def action_open_reactivation(self):
        return self.env.ref(
            "doorway_veille_sociale.action_veille_signal_reactivation"
        ).read()[0]

    def action_resoudre_urls_signaux(self):
        count = self.env["doorway.veille.signal"].migrate_resoudre_urls()
        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": _("Liens sources"),
                "message": _("%s signaux — URLs ouvrables mises en cache.") % count,
                "type": "success",
            },
        }

    def action_migrer_signaux_reactivation(self):
        """Intègre les signaux existants dans le modèle réactivation douce."""
        count = self.env["doorway.veille.signal"].migrate_signaux_reactivation()
        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": _("Migration réactivation"),
                "message": _("%s signaux intégrés au modèle de réactivation douce.")
                % count,
                "type": "success",
                "sticky": False,
            },
        }

    def action_open_sources_from_dashboard(self):
        return self.env["doorway.veille.config"].action_open_sources()
