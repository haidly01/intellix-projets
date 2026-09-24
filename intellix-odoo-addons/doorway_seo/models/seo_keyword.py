# -*- coding: utf-8 -*-
"""Recherche de mots-clés + suivi de positionnement (rank tracking).

GRATUIT (analyse) : ces modèles ne consomment AUCUN crédit. Le code est
néanmoins structuré pour pouvoir être métré plus tard si souhaité (un seul
point d'entrée par action : ``research`` côté idées, ``run_rank_check`` côté
suivi — il suffirait d'y ajouter une consommation ``doorway.credit.api``).

Tout dépend de Bright Data SERP de façon OPTIONNELLE : sans configuration, la
recherche d'idées Claude fonctionne toujours et le suivi affiche un état clair
« configurer Bright Data SERP » au lieu de planter.
"""
import json
import logging

from odoo import api, fields, models

from ..services import brightdata_client, serp_analyzer

_logger = logging.getLogger(__name__)


class SeoKeywordIdea(models.Model):
    _name = "doorway.seo.keyword.idea"
    _description = "Idée de mot-clé — SEO IA"
    _order = "id asc"

    workspace_id = fields.Many2one(
        "doorway.seo.workspace", string="Espace SEO", ondelete="cascade", index=True
    )
    keyword = fields.Char(string="Mot-clé", required=True)
    intent = fields.Selection(
        [
            ("informational", "Informationnel"),
            ("commercial", "Commercial"),
            ("transactional", "Transactionnel"),
            ("navigational", "Navigationnel"),
            ("local", "Local"),
        ],
        string="Intention",
        default="informational",
    )
    group = fields.Char(string="Thème")
    rationale = fields.Text(string="Pertinence")
    source = fields.Char(string="Source", default="claude")

    volume_value = fields.Integer(string="Volume (si fournisseur)")
    volume_label = fields.Char(string="Volume", default="estimé")
    volume_source = fields.Char(string="Source volume", default="estimate")
    cpc = fields.Float(string="CPC (si fournisseur)")
    competition = fields.Char(string="Concurrence (Ads)")

    difficulty = fields.Integer(string="Difficulté (KD)")
    difficulty_label = fields.Char(string="Difficulté", default="N/A")
    top_domains = fields.Char(string="Domaines en tête (SERP)")

    saved = fields.Boolean(string="Suivi activé", default=False)

    def read_dict(self):
        self.ensure_one()
        return {
            "id": self.id,
            "keyword": self.keyword,
            "intent": self.intent,
            "group": self.group or "",
            "rationale": self.rationale or "",
            "volume_value": self.volume_value or None,
            "volume_label": self.volume_label or "estimé",
            "volume_source": self.volume_source or "estimate",
            "cpc": round(self.cpc, 2) if self.cpc else None,
            "competition": self.competition or "",
            "difficulty": self.difficulty or None,
            "difficulty_label": self.difficulty_label or "N/A",
            "top_domains": self.top_domains or "",
            "saved": self.saved,
        }


class SeoTrackedKeyword(models.Model):
    _name = "doorway.seo.tracked.keyword"
    _description = "Mot-clé suivi (positionnement) — SEO IA"
    _order = "current_position asc, id desc"

    workspace_id = fields.Many2one(
        "doorway.seo.workspace", string="Espace SEO", ondelete="cascade", index=True
    )
    keyword = fields.Char(string="Mot-clé", required=True)
    target_url = fields.Char(
        string="URL / domaine ciblé",
        help="Domaine ou URL dont on suit la position. À défaut, le site web de "
        "l'espace SEO est utilisé.",
    )
    location = fields.Char(string="Localisation", help="Ville / région ajoutée à la requête.")
    country_code = fields.Char(string="Pays (gl)", default="ca")
    language = fields.Char(string="Langue (hl)", default="fr")
    device = fields.Selection(
        [("desktop", "Ordinateur"), ("mobile", "Mobile")],
        string="Appareil",
        default="desktop",
    )
    active = fields.Boolean(string="Actif", default=True)

    current_position = fields.Integer(string="Position actuelle", default=0)
    previous_position = fields.Integer(string="Position précédente", default=0)
    best_position = fields.Integer(string="Meilleure position", default=0)
    last_url = fields.Char(string="URL classée")
    last_features_json = fields.Text(string="Fonctionnalités SERP (JSON)")
    last_checked = fields.Datetime(string="Dernier contrôle")
    last_error = fields.Text(string="Dernière erreur")

    snapshot_ids = fields.One2many(
        "doorway.seo.rank.snapshot", "keyword_id", string="Historique"
    )

    # ------------------------------------------------------------------
    def _effective_domain(self):
        self.ensure_one()
        target = (self.target_url or "").strip()
        if not target and self.workspace_id:
            target = (self.workspace_id.website_url or "").strip()
        return serp_analyzer.normalize_domain(target)

    def _query_text(self):
        self.ensure_one()
        kw = (self.keyword or "").strip()
        loc = (self.location or "").strip()
        return ("%s %s" % (kw, loc)).strip() if loc else kw

    def run_rank_check(self):
        """Interroge le SERP, trouve la meilleure position, ajoute un snapshot.

        Dégrade proprement : si Bright Data n'est pas configuré ou échoue, on
        enregistre ``last_error`` et on n'altère pas l'historique. Ne lève jamais.
        """
        Snapshot = self.env["doorway.seo.rank.snapshot"]
        for rec in self:
            domain = rec._effective_domain()
            if not domain:
                rec.last_error = "Aucun domaine cible (renseignez l'URL/domaine ou le site de l'espace)."
                continue
            if not brightdata_client.is_available(self.env):
                rec.last_error = (
                    "Bright Data SERP non configuré : suivi en direct indisponible."
                )
                continue
            serp, msg = brightdata_client.serp_full(
                self.env,
                rec._query_text(),
                country=(rec.country_code or "ca"),
                lang=(rec.language or "fr"),
                num=100,
            )
            if serp is None:
                rec.last_error = msg
                continue
            rank = serp_analyzer.find_rank(serp, domain)
            position = int(rank.get("position") or 0)
            features = rank.get("features") or serp.get("features") or []
            features_json = json.dumps(features, ensure_ascii=False)

            Snapshot.create(
                {
                    "keyword_id": rec.id,
                    "position": position,
                    "found": bool(rank.get("found")),
                    "ranking_url": rank.get("url") or "",
                    "serp_features_json": features_json,
                }
            )
            vals = {
                "previous_position": rec.current_position,
                "current_position": position,
                "last_url": rank.get("url") or "",
                "last_features_json": features_json,
                "last_checked": fields.Datetime.now(),
                "last_error": False,
            }
            if position:
                if not rec.best_position or position < rec.best_position:
                    vals["best_position"] = position
            rec.write(vals)
        return True

    # ------------------------------------------------------------------
    def read_dict(self):
        self.ensure_one()
        history = [
            {
                "date": fields.Datetime.to_string(s.check_date) if s.check_date else "",
                "position": s.position or 0,
                "found": s.found,
            }
            for s in self.snapshot_ids.sorted(key=lambda r: (r.check_date or fields.Datetime.now(), r.id))
        ]
        delta = 0
        delta_dir = "flat"
        if self.current_position and self.previous_position:
            # Position plus basse = meilleure → amélioration si current < previous.
            delta = self.previous_position - self.current_position
            if delta > 0:
                delta_dir = "up"
            elif delta < 0:
                delta_dir = "down"
        elif self.current_position and not self.previous_position:
            delta_dir = "new"
        try:
            features = json.loads(self.last_features_json) if self.last_features_json else []
        except (ValueError, TypeError):
            features = []
        return {
            "id": self.id,
            "keyword": self.keyword,
            "target_url": self.target_url or "",
            "location": self.location or "",
            "country_code": self.country_code or "ca",
            "language": self.language or "fr",
            "device": self.device,
            "active": self.active,
            "current_position": self.current_position or 0,
            "previous_position": self.previous_position or 0,
            "best_position": self.best_position or 0,
            "delta": delta,
            "delta_dir": delta_dir,
            "last_url": self.last_url or "",
            "last_checked": fields.Datetime.to_string(self.last_checked) if self.last_checked else "",
            "last_error": self.last_error or "",
            "features": features,
            "history": history,
        }

    # ------------------------------------------------------------------
    @api.model
    def cron_refresh_all(self):
        """Action planifiée (ir.cron) : rafraîchit tous les mots-clés actifs.

        Dégrade proprement si Bright Data n'est pas configuré (ne fait rien,
        ne plante pas). Commit par enregistrement pour préserver l'historique
        déjà écrit en cas d'incident.
        """
        if not brightdata_client.is_available(self.env):
            _logger.info("SEO rank cron : Bright Data SERP non configuré, ignoré.")
            return True
        records = self.search([("active", "=", True)])
        for rec in records:
            try:
                rec.run_rank_check()
                self.env.cr.commit()
            except Exception:  # noqa: BLE001
                _logger.exception("SEO rank cron : échec mot-clé %s", rec.id)
                self.env.cr.rollback()
        return True


class SeoRankSnapshot(models.Model):
    _name = "doorway.seo.rank.snapshot"
    _description = "Relevé de position daté — SEO IA"
    _order = "check_date desc, id desc"
    _rec_name = "keyword_id"

    keyword_id = fields.Many2one(
        "doorway.seo.tracked.keyword",
        string="Mot-clé suivi",
        required=True,
        ondelete="cascade",
        index=True,
    )
    check_date = fields.Datetime(string="Date du relevé", default=fields.Datetime.now)
    position = fields.Integer(
        string="Position", default=0, help="0 = hors du top 100."
    )
    found = fields.Boolean(string="Présent dans le top 100", default=False)
    ranking_url = fields.Char(string="URL classée")
    serp_features_json = fields.Text(string="Fonctionnalités SERP (JSON)")
