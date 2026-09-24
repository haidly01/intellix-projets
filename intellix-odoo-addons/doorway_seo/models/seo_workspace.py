# -*- coding: utf-8 -*-
"""Espace de travail SEO — orchestrateur appelé par le client OWL.

Centralise le brief, le chat, et l'accès aux trois capacités (on-page,
backlinks white-hat, citations). Toutes les méthodes échouent proprement et
renvoient un payload exploitable par l'UI.
"""
import json
import logging
import re

from odoo import api, fields, models

from ..services import (
    brightdata_client,
    claude_seo,
    config_loader,
    dataforseo_client,
    keyword_volume,
    serp_analyzer,
)

_logger = logging.getLogger(__name__)

WELCOME_MESSAGE = (
    "Bonjour ! Je suis Léa, votre assistante SEO. Je peux (1) auditer et "
    "optimiser les pages de votre site, (2) trouver des opportunités de "
    "backlinks LÉGITIMES (white-hat) et préparer vos emails d'approche, et "
    "(3) gérer vos citations dans les annuaires (SEO local QC + France). "
    "Renseignez votre activité et votre zone à gauche, puis demandez-moi par "
    "exemple : « optimise toutes les pages pour rénovation cuisine Montréal »."
)

WHITE_HAT_NOTICE = (
    "⚠️ Approche 100% WHITE-HAT : pas de fermes de liens, pas de spam de "
    "commentaires/forums, pas de PBN, aucun envoi ni dépôt de lien automatique. "
    "Uniquement de la prospection légitime et des annuaires pertinents."
)


class SeoWorkspace(models.Model):
    _name = "doorway.seo.workspace"
    _description = "Espace de travail SEO — SEO IA"
    _order = "id desc"

    name = fields.Char(string="Projet SEO", required=True, default="Espace SEO")
    language = fields.Char(string="Langue", default="fr")
    business_name = fields.Char(string="Nom de l'entreprise")
    niche = fields.Char(string="Activité / niche")
    geo = fields.Char(string="Zone géographique")
    website_url = fields.Char(string="Site web")
    description = fields.Text(string="Description de l'activité")
    target_keyword = fields.Char(string="Mot-clé cible principal")

    nap_id = fields.Many2one("doorway.seo.nap", string="Fiche NAP")
    backlink_ids = fields.One2many(
        "doorway.seo.backlink.target", "workspace_id", string="Cibles de backlinks"
    )
    message_ids = fields.One2many(
        "doorway.seo.chat.message", "workspace_id", string="Conversation"
    )

    # Recherche de mots-clés + suivi de positionnement (GRATUIT, sans crédit).
    keyword_seed = fields.Char(string="Amorce de recherche de mots-clés")
    keyword_research_json = fields.Text(string="Signaux de recherche (JSON)")
    keyword_idea_ids = fields.One2many(
        "doorway.seo.keyword.idea", "workspace_id", string="Idées de mots-clés"
    )
    tracked_keyword_ids = fields.One2many(
        "doorway.seo.tracked.keyword", "workspace_id", string="Mots-clés suivis"
    )

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    def _add_message(self, role, content):
        if not content:
            return
        self.env["doorway.seo.chat.message"].create(
            {"workspace_id": self.id, "role": role, "content": content}
        )

    def _brief_dict(self):
        self.ensure_one()
        return {
            "business_name": self.business_name or "",
            "niche": self.niche or "",
            "geo": self.geo or "",
            "description": self.description or "",
            "language": self.language or "fr",
            "website_url": self.website_url or "",
            "target_keyword": self.target_keyword or "",
        }

    def _sitemap_info(self):
        website = self.env["website"].get_current_website()
        base = ""
        if website:
            try:
                base = website._get_http_domain() or ""
            except Exception:  # noqa: BLE001
                base = website.domain or ""
        base = (base or "").rstrip("/")
        return {
            "sitemap_url": (base + "/sitemap.xml") if base else "/sitemap.xml",
            "robots_url": (base + "/robots.txt") if base else "/robots.txt",
            "note": (
                "Odoo génère automatiquement /sitemap.xml et /robots.txt. Vérifiez "
                "que les pages importantes sont indexées (case « Indexée ») et que "
                "robots.txt n'exclut pas de sections utiles."
            ),
        }

    # ------------------------------------------------------------------
    # Payload UI
    # ------------------------------------------------------------------
    def get_payload(self):
        self.ensure_one()
        nap = self.nap_id or self.env["doorway.seo.nap"].get_or_create_default()
        if not self.nap_id:
            self.nap_id = nap.id
        audits = self.env["doorway.seo.page.audit"].search([])
        citations = self.env["doorway.seo.citation"].search([("nap_id", "=", nap.id)])
        directories = self.env["doorway.seo.directory"].search([])
        cited_dir_ids = citations.mapped("directory_id").ids
        credit_api = self.env["doorway.credit.api"]
        return {
            "id": self.id,
            "name": self.name,
            "credit_balance": credit_api.get_balance(self.env.company),
            "apply_cost": credit_api.get_cost("doorway_credits.cost_seo_publish", 1.0),
            "language": self.language,
            "business_name": self.business_name or "",
            "niche": self.niche or "",
            "geo": self.geo or "",
            "website_url": self.website_url or "",
            "description": self.description or "",
            "target_keyword": self.target_keyword or "",
            "claude_available": claude_seo.is_available(self.env),
            "brightdata_available": config_loader.brightdata_available(self.env),
            "white_hat_notice": WHITE_HAT_NOTICE,
            "nap": nap.to_dict(),
            "pages": [a.read_dict() for a in audits.sorted(key=lambda r: (r.score, -r.id))],
            "backlinks": [b.read_dict() for b in self.backlink_ids],
            "directories": [d.to_dict() for d in directories],
            "citations": [c.read_dict() for c in citations],
            "uncited_directories": [
                d.to_dict() for d in directories if d.id not in cited_dir_ids
            ],
            "messages": [m.to_dict() for m in self.message_ids],
            "sitemap": self._sitemap_info(),
            # --- Mots-clés & suivi (panneaux GRATUITS, aucun crédit) ---
            "serp_available": config_loader.brightdata_available(self.env),
            "keyword_volume_available": config_loader.keyword_volume_available(self.env),
            "volume_provider": config_loader.get_volume_provider_name(self.env),
            "keyword_seed": self.keyword_seed or "",
            "keyword_research": self._load_keyword_research(),
            "keyword_ideas": [i.read_dict() for i in self.keyword_idea_ids],
            "tracked_keywords": [t.read_dict() for t in self.tracked_keyword_ids],
        }

    def _load_keyword_research(self):
        if not self.keyword_research_json:
            return {}
        try:
            data = json.loads(self.keyword_research_json)
            return data if isinstance(data, dict) else {}
        except (ValueError, TypeError):
            return {}

    # ------------------------------------------------------------------
    # Sessions
    # ------------------------------------------------------------------
    @api.model
    def get_or_create_session(self):
        ws = self.search([("create_uid", "=", self.env.uid)], limit=1)
        if not ws:
            ws = self.create({"name": "Espace SEO"})
            ws._add_message("assistant", WELCOME_MESSAGE)
        return ws.get_payload()

    @api.model
    def create_session(self):
        ws = self.create({"name": "Espace SEO"})
        ws._add_message("assistant", WELCOME_MESSAGE)
        return ws.get_payload()

    def update_brief(self, vals):
        self.ensure_one()
        allowed = {
            "name", "language", "business_name", "niche", "geo",
            "website_url", "description", "target_keyword",
        }
        clean = {k: v for k, v in (vals or {}).items() if k in allowed}
        if clean:
            self.write(clean)
        return self.get_payload()

    def update_nap(self, vals):
        self.ensure_one()
        nap = self.nap_id or self.env["doorway.seo.nap"].get_or_create_default()
        if not self.nap_id:
            self.nap_id = nap.id
        allowed = {
            "name", "address", "city", "postal_code", "country", "phone",
            "email", "website_url", "hours", "categories", "description",
        }
        clean = {k: v for k, v in (vals or {}).items() if k in allowed}
        if clean:
            nap.write(clean)
        return self.get_payload()

    def post_message(self, body):
        self.ensure_one()
        body = (body or "").strip()
        if body:
            self._add_message("user", body)
            self._add_message(
                "assistant",
                "C'est noté ✦ Utilisez les actions du tableau de bord, ou "
                "demandez-moi « audite le site », « optimise pour <mot-clé> », "
                "« trouve des backlinks » ou « prépare les citations ».",
            )
        return self.get_payload()

    # ------------------------------------------------------------------
    # Chat router (intentions simples + robustes)
    # ------------------------------------------------------------------
    @staticmethod
    def _extract_keyword(text):
        for pat in (r"«\s*(.+?)\s*»", r"\"(.+?)\"", r"'(.+?)'"):
            m = re.search(pat, text)
            if m:
                return m.group(1).strip()
        m = re.search(r"\bpour\s+(.+)$", text, flags=re.IGNORECASE)
        if m:
            return m.group(1).strip().rstrip(".!?")
        return ""

    def run_chat(self, instruction):
        """Route une instruction en langage naturel vers une action."""
        self.ensure_one()
        instruction = (instruction or "").strip()
        if not instruction:
            return self.get_payload()
        self._add_message("user", instruction)
        low = instruction.lower()
        keyword = self._extract_keyword(instruction)

        if any(w in low for w in ("backlink", "lien entrant", "netlinking")):
            self._add_message("assistant", "Je recherche des opportunités de backlinks légitimes…")
            self.generate_backlinks()
            return self._reply_payload("J'ai proposé des cibles de backlinks white-hat (onglet Backlinks).")

        if any(w in low for w in ("citation", "annuaire", "directory", "nap")):
            self.seed_citations(priority_only=True)
            return self._reply_payload(
                "J'ai préparé les citations pour les annuaires prioritaires (onglet Citations)."
            )

        if any(w in low for w in ("position", "positionnement", "classement", "rank", "suivi")):
            self.refresh_all_tracked()
            return self._reply_payload(
                "J'ai rafraîchi le suivi de positionnement (onglet Suivi)."
            )

        if any(w in low for w in ("mot-clé", "mot-cle", "mots-cl", "keyword", "idées de mots")):
            self.research_keywords(seed=keyword or None)
            return self.get_payload()

        if any(w in low for w in ("optimis", "améliore", "ameliore", "meta")):
            if keyword:
                self.write({"target_keyword": keyword})
            self.audit_pages(target_keyword=self.target_keyword or "")
            self.optimize_all()
            kw = (" pour « %s »" % keyword) if keyword else ""
            return self._reply_payload(
                "J'ai audité puis généré des propositions d'optimisation%s. "
                "Vérifiez et cliquez sur « Appliquer » par page." % kw
            )

        if any(w in low for w in ("audit", "analyse", "score")):
            self.audit_pages(target_keyword=keyword or self.target_keyword or "")
            return self._reply_payload("Audit du site terminé (onglet Pages).")

        # Pas d'intention claire : on enregistre simplement.
        return self._reply_payload(
            "Dites-moi quoi faire : « audite le site », « optimise pour <mot-clé> », "
            "« trouve des backlinks » ou « prépare les citations »."
        )

    def _reply_payload(self, message):
        self._add_message("assistant", message)
        return self.get_payload()

    # ------------------------------------------------------------------
    # Capacité A — On-page
    # ------------------------------------------------------------------
    def audit_pages(self, target_keyword=""):
        self.ensure_one()
        if target_keyword:
            self.target_keyword = target_keyword
        self.env["doorway.seo.page.audit"].sync_from_website(
            target_keyword=self.target_keyword or ""
        )
        return self.get_payload()

    def optimize_page(self, audit_id):
        self.ensure_one()
        audit = self.env["doorway.seo.page.audit"].browse(int(audit_id))
        if audit.exists():
            audit.generate_proposal(language=self.language or "fr")
        return self.get_payload()

    def optimize_all(self):
        self.ensure_one()
        audits = self.env["doorway.seo.page.audit"].search([])
        for audit in audits:
            audit.generate_proposal(language=self.language or "fr")
        return self.get_payload()

    def apply_page(self, audit_id, inject_jsonld=True):
        """PAYANT : applique l'optimisation SEO sur la page EN LIGNE.

        Audit + génération de proposition restent gratuits ; seule l'écriture
        des meta/JSON-LD sur la page live consomme un crédit. Idempotent par
        page (ré-appliquer la même page ne refacture pas). Solde insuffisant →
        paywall, rien n'est appliqué.
        """
        self.ensure_one()
        audit = self.env["doorway.seo.page.audit"].browse(int(audit_id))
        if not audit.exists():
            return self.get_payload()

        credit_api = self.env["doorway.credit.api"]
        cost = credit_api.get_cost("doorway_credits.cost_seo_publish", 1.0)
        company = self.env.company
        idem = "seo_publish:audit:%s" % audit.id
        already = bool(audit.apply_charged) or bool(
            self.env["doorway.credit.transaction"]
            .sudo()
            .search([("idempotency_key", "=", idem)], limit=1)
        )

        # GATE : si pas encore payé et solde insuffisant → paywall, rien appliqué.
        if not already and not credit_api.has_credits(company, cost):
            payload = self.get_payload()
            payload["paywall"] = credit_api.action_open_paywall(
                company,
                required=cost,
                service="seo_publish",
                message="Solde insuffisant pour appliquer le SEO sur la page en ligne.",
            )
            self._add_message(
                "assistant",
                "🔒 Solde de crédits insuffisant pour appliquer le SEO en ligne. "
                "L'audit et les propositions restent gratuits ; achetez un pack pour "
                "publier les optimisations.",
            )
            return payload

        # Application effective (écrit les meta/JSON-LD sur la page live).
        audit.apply_proposal(inject_jsonld=bool(inject_jsonld))

        # CONSOMMATION : une seule fois par page appliquée avec succès.
        if audit.state == "optimized" and not already:
            res = credit_api.consume(
                company,
                cost,
                "Application SEO page « %s »" % (audit.page_name or audit.id),
                ref="audit:%s" % audit.id,
                service="seo_publish",
                idempotency_key=idem,
            )
            if res.get("success"):
                audit.apply_charged = True
        return self.get_payload()

    def set_page_keyword(self, audit_id, keyword):
        self.ensure_one()
        audit = self.env["doorway.seo.page.audit"].browse(int(audit_id))
        if audit.exists():
            audit.write({"target_keyword": (keyword or "").strip()})
            audit.run_audit()
        return self.get_payload()

    # ------------------------------------------------------------------
    # Capacité B — Backlinks (white-hat)
    # ------------------------------------------------------------------
    def generate_backlinks(self):
        self.ensure_one()
        serp_context = None
        if config_loader.brightdata_available(self.env):
            query = " ".join(x for x in [self.niche, self.geo] if x) or (self.business_name or "")
            if query:
                results, _msg = brightdata_client.serp_search(self.env, query, country="ca")
                if results:
                    serp_context = results
        targets, message = claude_seo.generate_backlink_targets(
            self.env, self._brief_dict(), serp_context=serp_context
        )
        if targets is None:
            self._add_message("assistant", "⚠️ " + message)
            return self.get_payload()
        for t in targets:
            self.env["doorway.seo.backlink.target"].create(
                {
                    "workspace_id": self.id,
                    "name": t["name"],
                    "target_type": t["type"],
                    "url": t["url"],
                    "approach": t["approach"],
                    "rationale": t["rationale"],
                }
            )
        return self.get_payload()

    def generate_outreach(self, target_id):
        self.ensure_one()
        target = self.env["doorway.seo.backlink.target"].browse(int(target_id))
        if target.exists():
            target.generate_outreach()
        return self.get_payload()

    def set_backlink_status(self, target_id, status):
        self.ensure_one()
        target = self.env["doorway.seo.backlink.target"].browse(int(target_id))
        if target.exists():
            target.set_status(status)
        return self.get_payload()

    # ------------------------------------------------------------------
    # Capacité C — Citations
    # ------------------------------------------------------------------
    def seed_citations(self, priority_only=False):
        """Crée les enregistrements de citation manquants pour les annuaires."""
        self.ensure_one()
        nap = self.nap_id or self.env["doorway.seo.nap"].get_or_create_default()
        if not self.nap_id:
            self.nap_id = nap.id
        domain = []
        if priority_only:
            domain = [("is_priority", "=", True)]
        directories = self.env["doorway.seo.directory"].search(domain)
        Citation = self.env["doorway.seo.citation"]
        for directory in directories:
            exists = Citation.search(
                [("nap_id", "=", nap.id), ("directory_id", "=", directory.id)], limit=1
            )
            if not exists:
                Citation.create({"nap_id": nap.id, "directory_id": directory.id})
        return self.get_payload()

    def generate_citation(self, citation_id):
        self.ensure_one()
        citation = self.env["doorway.seo.citation"].browse(int(citation_id))
        if citation.exists():
            citation.generate_content(language=self.language or "fr")
        return self.get_payload()

    def add_citation(self, directory_id):
        self.ensure_one()
        nap = self.nap_id or self.env["doorway.seo.nap"].get_or_create_default()
        if not self.nap_id:
            self.nap_id = nap.id
        directory = self.env["doorway.seo.directory"].browse(int(directory_id))
        if directory.exists():
            exists = self.env["doorway.seo.citation"].search(
                [("nap_id", "=", nap.id), ("directory_id", "=", directory.id)], limit=1
            )
            if not exists:
                self.env["doorway.seo.citation"].create(
                    {"nap_id": nap.id, "directory_id": directory.id}
                )
        return self.get_payload()

    def set_citation_status(self, citation_id, status):
        self.ensure_one()
        citation = self.env["doorway.seo.citation"].browse(int(citation_id))
        if citation.exists():
            citation.set_status(status)
        return self.get_payload()

    # ------------------------------------------------------------------
    # Capacité D — Recherche de mots-clés (GRATUIT, aucun crédit)
    # ------------------------------------------------------------------
    # NOTE METRAGE : si l'on souhaitait facturer un jour la recherche de
    # mots-clés ou le suivi, ce serait le point d'entrée unique à instrumenter
    # (cf. apply_page pour le pattern doorway.credit.api). Laissé GRATUIT ici.
    def research_keywords(self, seed=None, geo=None, language=None):
        self.ensure_one()
        seed = (seed or self.keyword_seed or self.target_keyword or "").strip()
        upd = {"keyword_seed": seed}
        if geo:
            upd["geo"] = geo
        if language:
            upd["language"] = language
        self.write(upd)
        if not seed:
            return self._reply_payload("Indiquez un mot-clé ou un sujet à explorer.")

        geo = self.geo or ""
        language = self.language or "fr"

        # Signaux SERP réels (optionnels) : recherches associées, PAA, autocomplete.
        panel = {
            "seed": seed,
            "related": [],
            "paa": [],
            "autocomplete": [],
            "top_domains": [],
            "difficulty": None,
            "difficulty_label": "N/A",
            "serp_used": False,
            "note": "",
        }
        serp_context = None
        if config_loader.brightdata_available(self.env):
            query = ("%s %s" % (seed, geo)).strip() if geo else seed
            serp, _msg = brightdata_client.serp_full(self.env, query, lang=language)
            if serp:
                signals = serp_analyzer.extract_signals(serp)
                panel.update(
                    {
                        "related": signals["related"],
                        "paa": signals["paa"],
                        "top_domains": signals["top_domains"],
                        "difficulty": signals["difficulty"],
                        "difficulty_label": signals["difficulty_label"],
                        "serp_used": True,
                    }
                )
            ac, _acmsg = brightdata_client.autocomplete(self.env, seed, lang=language)
            if ac:
                panel["autocomplete"] = ac[:10]
                panel["serp_used"] = True
            serp_context = {
                "related": panel["related"],
                "people_also_ask": panel["paa"],
                "autocomplete": panel["autocomplete"],
            }
        else:
            panel["note"] = (
                "Bright Data SERP non configuré : idées générées par l'IA sans "
                "enrichissement SERP (recherches associées / PAA indisponibles)."
            )

        ideas, message = claude_seo.generate_keyword_ideas(
            self.env, seed, geo=geo, language=language, serp_context=serp_context
        )
        if ideas is None:
            self.write({"keyword_research_json": json.dumps(panel, ensure_ascii=False)})
            return self._reply_payload("⚠️ " + message)

        # Dédoublonnage + enrichissement par les idées RÉELLES DataForSEO.
        merged = []
        seen = set()
        for it in ideas:
            key = it["keyword"].lower()
            if key not in seen:
                seen.add(key)
                merged.append(dict(it, source="claude"))
        if config_loader.dataforseo_available(self.env):
            kfk, _kmsg = dataforseo_client.keywords_for_keywords(
                self.env, seed, geo=geo, language=language, limit=20
            )
            for extra in kfk or []:
                key = (extra.get("keyword") or "").lower()
                if key and key not in seen:
                    seen.add(key)
                    merged.append(
                        {
                            "keyword": extra["keyword"],
                            "intent": "commercial",
                            "group": "DataForSEO",
                            "rationale": "Mot-clé associé réel (DataForSEO).",
                            "source": "dataforseo",
                        }
                    )

        # Métriques réelles (volume + CPC + concurrence + difficulté) ; sinon « estimé ».
        metrics = keyword_volume.lookup(
            self.env, [i["keyword"] for i in merged], geo=geo, language=language
        )
        self.keyword_idea_ids.unlink()
        Idea = self.env["doorway.seo.keyword.idea"]
        for it in merged:
            m = metrics.get(it["keyword"]) or {}
            Idea.create(
                {
                    "workspace_id": self.id,
                    "keyword": it["keyword"],
                    "intent": it["intent"],
                    "group": it.get("group") or "",
                    "rationale": it.get("rationale") or "",
                    "source": it.get("source") or "claude",
                    "volume_value": m.get("volume") or 0,
                    "volume_label": m.get("label") or "estimé",
                    "volume_source": m.get("source") or "estimate",
                    "cpc": m.get("cpc") or 0.0,
                    "competition": m.get("competition") or "",
                    "difficulty": m.get("difficulty") or 0,
                    "difficulty_label": m.get("difficulty_label") or "N/A",
                }
            )
        panel["volume_provider"] = config_loader.get_volume_provider_name(self.env)
        panel["volume_available"] = config_loader.keyword_volume_available(self.env)
        self.write({"keyword_research_json": json.dumps(panel, ensure_ascii=False)})
        return self._reply_payload(
            "J'ai proposé %d mots-clés pour « %s » (onglet Mots-clés)." % (len(merged), seed)
        )

    def analyze_keyword_idea(self, idea_id):
        """Analyse SERP d'UNE idée : domaines en tête (Bright Data) + difficulté.

        La difficulté DataForSEO (KD) prime ; le proxy SERP n'est utilisé que si
        aucune difficulté réelle n'est déjà disponible.
        """
        self.ensure_one()
        idea = self.env["doorway.seo.keyword.idea"].browse(int(idea_id))
        if not idea.exists():
            return self.get_payload()
        if not config_loader.brightdata_available(self.env):
            return self.get_payload()
        query = ("%s %s" % (idea.keyword, self.geo)).strip() if self.geo else idea.keyword
        serp, _msg = brightdata_client.serp_full(self.env, query, lang=self.language or "fr")
        if serp:
            signals = serp_analyzer.extract_signals(serp)
            vals = {"top_domains": ", ".join(signals["top_domains"][:6])}
            # Ne pas écraser une difficulté réelle (DataForSEO) par le proxy SERP.
            if not idea.difficulty and signals.get("difficulty"):
                vals["difficulty"] = signals["difficulty"]
                vals["difficulty_label"] = signals["difficulty_label"] + " (SERP)"
            idea.write(vals)
        return self.get_payload()

    def save_keywords(self, idea_ids):
        """Promeut des idées en mots-clés SUIVIS (rank tracking)."""
        self.ensure_one()
        ideas = self.env["doorway.seo.keyword.idea"].browse(
            [int(i) for i in (idea_ids or []) if i]
        )
        Tracked = self.env["doorway.seo.tracked.keyword"]
        for idea in ideas:
            if not idea.exists():
                continue
            exists = Tracked.search(
                [("workspace_id", "=", self.id), ("keyword", "=", idea.keyword)], limit=1
            )
            if not exists:
                Tracked.create(
                    {
                        "workspace_id": self.id,
                        "keyword": idea.keyword,
                        "target_url": self.website_url or "",
                        "location": self.geo or "",
                        "language": self.language or "fr",
                    }
                )
            idea.saved = True
        return self.get_payload()

    # ------------------------------------------------------------------
    # Capacité E — Suivi de positionnement (GRATUIT, aucun crédit)
    # ------------------------------------------------------------------
    def add_tracked_keyword(self, vals):
        self.ensure_one()
        vals = vals or {}
        keyword = (vals.get("keyword") or "").strip()
        if not keyword:
            return self.get_payload()
        self.env["doorway.seo.tracked.keyword"].create(
            {
                "workspace_id": self.id,
                "keyword": keyword,
                "target_url": (vals.get("target_url") or self.website_url or "").strip(),
                "location": (vals.get("location") or self.geo or "").strip(),
                "country_code": (vals.get("country_code") or "ca").strip() or "ca",
                "language": (vals.get("language") or self.language or "fr").strip() or "fr",
                "device": vals.get("device") if vals.get("device") in ("desktop", "mobile") else "desktop",
            }
        )
        return self.get_payload()

    def set_tracked_keyword(self, tracked_id, vals):
        self.ensure_one()
        rec = self.env["doorway.seo.tracked.keyword"].browse(int(tracked_id))
        if not rec.exists():
            return self.get_payload()
        allowed = {"keyword", "target_url", "location", "country_code", "language", "device", "active"}
        clean = {k: v for k, v in (vals or {}).items() if k in allowed}
        if clean:
            rec.write(clean)
        return self.get_payload()

    def delete_tracked_keyword(self, tracked_id):
        self.ensure_one()
        rec = self.env["doorway.seo.tracked.keyword"].browse(int(tracked_id))
        if rec.exists():
            rec.unlink()
        return self.get_payload()

    def refresh_tracked_keyword(self, tracked_id):
        self.ensure_one()
        rec = self.env["doorway.seo.tracked.keyword"].browse(int(tracked_id))
        if rec.exists():
            rec.run_rank_check()
        return self.get_payload()

    def refresh_all_tracked(self):
        self.ensure_one()
        self.tracked_keyword_ids.run_rank_check()
        return self.get_payload()
