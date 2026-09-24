# -*- coding: utf-8 -*-
"""Audit & optimisation SEO on-page d'une ``website.page``.

Chaque enregistrement reflète l'état SEO d'une page : score, anomalies, et la
proposition d'optimisation générée par Claude. L'application (« APPLY ») écrit
dans les champs SEO natifs d'Odoo (``website_meta_*``) de façon idempotente.
"""
import json
import logging
import re

from odoo import api, fields, models

from ..services import claude_seo, page_auditor

_logger = logging.getLogger(__name__)

# Marqueur d'injection idempotente du JSON-LD dans l'arch de la page.
JSONLD_BEGIN = "<!-- doorway_seo:jsonld:begin -->"
JSONLD_END = "<!-- doorway_seo:jsonld:end -->"


class SeoPageAudit(models.Model):
    _name = "doorway.seo.page.audit"
    _description = "Audit SEO de page — SEO IA"
    _order = "score asc, id desc"
    _rec_name = "page_name"

    page_id = fields.Many2one(
        "website.page", string="Page", required=True, ondelete="cascade", index=True
    )
    website_id = fields.Many2one("website", string="Site web")
    page_name = fields.Char(string="Page")
    url = fields.Char(string="URL")
    target_keyword = fields.Char(string="Mot-clé cible")

    score = fields.Integer(string="Score SEO", default=0)
    state = fields.Selection(
        [
            ("pending", "À auditer"),
            ("audited", "Audité"),
            ("proposed", "Proposition prête"),
            ("optimized", "Optimisé"),
            ("error", "Erreur"),
        ],
        string="État",
        default="pending",
        required=True,
    )

    issues_json = fields.Text(string="Anomalies (JSON)")
    metrics_json = fields.Text(string="Métriques (JSON)")

    current_meta_title = fields.Char(string="Meta title actuel")
    current_meta_description = fields.Text(string="Meta description actuelle")
    current_meta_keywords = fields.Char(string="Mots-clés actuels")

    suggested_meta_title = fields.Char(string="Meta title proposé")
    suggested_meta_description = fields.Text(string="Meta description proposée")
    suggested_keywords = fields.Char(string="Mots-clés proposés")
    suggested_jsonld = fields.Text(string="JSON-LD proposé")
    suggestions = fields.Text(string="Pistes d'amélioration")

    last_error = fields.Text(string="Dernière erreur")
    apply_charged = fields.Boolean(
        string="Application facturée", default=False, copy=False,
        help="Vrai dès qu'un crédit a été consommé pour appliquer cette "
        "optimisation en ligne (évite toute double facturation à la ré-application).",
    )

    _sql_constraints = [
        ("page_uniq", "unique(page_id)", "Un seul audit par page."),
    ]

    # ------------------------------------------------------------------
    def _load(self, field):
        raw = self[field]
        if not raw:
            return None
        try:
            return json.loads(raw)
        except (ValueError, TypeError):
            return None

    def run_audit(self):
        """(Ré)audite la page et met à jour le score / anomalies / métriques."""
        for rec in self:
            page = rec.page_id
            if not page or not page.exists():
                rec.write({"state": "error", "last_error": "Page introuvable."})
                continue
            result = page_auditor.audit_page(page, target_keyword=rec.target_keyword or "")
            new_state = "audited"
            if rec.state in ("proposed", "optimized") and (
                rec.suggested_meta_title or rec.suggested_meta_description
            ):
                new_state = rec.state
            rec.write(
                {
                    "page_name": result["name"],
                    "url": result["url"],
                    "score": result["score"],
                    "issues_json": json.dumps(result["issues"], ensure_ascii=False),
                    "metrics_json": json.dumps(result["metrics"], ensure_ascii=False),
                    "current_meta_title": result["meta_title"],
                    "current_meta_description": result["meta_description"],
                    "current_meta_keywords": result["meta_keywords"],
                    "state": new_state,
                    "last_error": False,
                }
            )
        return True

    def generate_proposal(self, language="fr"):
        """Appelle Claude pour proposer des meta / JSON-LD / pistes."""
        self.ensure_one()
        page = self.page_id
        if not page or not page.exists():
            self.write({"state": "error", "last_error": "Page introuvable."})
            return self.read_dict()
        # On (ré)audite d'abord pour fournir un contexte frais à Claude.
        self.run_audit()
        context = {
            "name": self.page_name,
            "url": self.url,
            "current_meta_title": self.current_meta_title or "",
            "current_meta_description": self.current_meta_description or "",
            "current_meta_keywords": self.current_meta_keywords or "",
            "metrics": self._load("metrics_json") or {},
            "issues": self._load("issues_json") or [],
            "content_excerpt": page_auditor.audit_page(
                page, target_keyword=self.target_keyword or ""
            ).get("content_excerpt", ""),
        }
        data, message = claude_seo.generate_page_seo(
            self.env, context, target_keyword=self.target_keyword or "", language=language
        )
        if data is None:
            self.write({"state": "error", "last_error": message})
            return self.read_dict()
        self.write(
            {
                "suggested_meta_title": data["meta_title"],
                "suggested_meta_description": data["meta_description"],
                "suggested_keywords": ", ".join(data["keywords"]),
                "suggested_jsonld": json.dumps(data["jsonld"], ensure_ascii=False, indent=2)
                if data["jsonld"]
                else "",
                "suggestions": "\n".join("• " + s for s in data["suggestions"]),
                "state": "proposed",
                "last_error": False,
            }
        )
        return self.read_dict()

    def apply_proposal(self, inject_jsonld=True):
        """Écrit la proposition dans les champs SEO natifs (idempotent)."""
        self.ensure_one()
        page = self.page_id
        if not page or not page.exists():
            self.write({"state": "error", "last_error": "Page introuvable."})
            return self.read_dict()
        vals = {}
        if self.suggested_meta_title:
            vals["website_meta_title"] = self.suggested_meta_title
        if self.suggested_meta_description:
            vals["website_meta_description"] = self.suggested_meta_description
        if self.suggested_keywords:
            vals["website_meta_keywords"] = self.suggested_keywords
        try:
            if vals:
                page.write(vals)
        except Exception as exc:  # noqa: BLE001
            _logger.exception("SEO IA : écriture meta échouée")
            self.write({"state": "error", "last_error": "Meta non appliquées : %s" % exc})
            return self.read_dict()

        if inject_jsonld and self.suggested_jsonld:
            self._inject_jsonld(page)

        # Re-audit pour refléter le nouveau score.
        self.run_audit()
        self.write({"state": "optimized", "last_error": False})
        return self.read_dict()

    def _inject_jsonld(self, page):
        """Injecte/remplace un bloc JSON-LD dans l'arch de la page (idempotent)."""
        try:
            jsonld = json.loads(self.suggested_jsonld)
        except (ValueError, TypeError):
            return
        try:
            arch = page.arch or ""
            block = (
                '%s<div class="doorway_seo_jsonld" style="display:none">'
                '<script type="application/ld+json">%s</script></div>%s'
                % (
                    JSONLD_BEGIN,
                    json.dumps(jsonld, ensure_ascii=False),
                    JSONLD_END,
                )
            )
            # Retire un éventuel bloc précédent (idempotence).
            pattern = re.escape(JSONLD_BEGIN) + r".*?" + re.escape(JSONLD_END)
            arch = re.sub(pattern, "", arch, flags=re.DOTALL)
            # Insère juste avant la dernière fermeture </div> ou en fin de wrap.
            if "</div>" in arch:
                idx = arch.rfind("</div>")
                arch = arch[:idx] + block + arch[idx:]
            else:
                arch = arch + block
            page.arch = arch
        except Exception:  # noqa: BLE001
            _logger.info("SEO IA : injection JSON-LD ignorée (non bloquant)")

    # ------------------------------------------------------------------
    def read_dict(self):
        self.ensure_one()
        return {
            "id": self.id,
            "page_id": self.page_id.id,
            "page_name": self.page_name or "",
            "url": self.url or "",
            "target_keyword": self.target_keyword or "",
            "score": self.score,
            "state": self.state,
            "issues": self._load("issues_json") or [],
            "metrics": self._load("metrics_json") or {},
            "current_meta_title": self.current_meta_title or "",
            "current_meta_description": self.current_meta_description or "",
            "current_meta_keywords": self.current_meta_keywords or "",
            "suggested_meta_title": self.suggested_meta_title or "",
            "suggested_meta_description": self.suggested_meta_description or "",
            "suggested_keywords": self.suggested_keywords or "",
            "suggested_jsonld": self.suggested_jsonld or "",
            "suggestions": self.suggestions or "",
            "last_error": self.last_error or "",
            "apply_charged": self.apply_charged,
        }

    @api.model
    def sync_from_website(self, target_keyword=""):
        """Crée/MAJ un audit pour chaque page publiée du site courant.

        Renvoie la liste des dicts d'audit, triés par score croissant.
        """
        website = self.env["website"].get_current_website()
        domain = [("url", "!=", False)]
        if website:
            domain += ["|", ("website_id", "=", website.id), ("website_id", "=", False)]
        pages = self.env["website.page"].search(domain)
        audits = self.env["doorway.seo.page.audit"]
        for page in pages:
            audit = self.search([("page_id", "=", page.id)], limit=1)
            if not audit:
                audit = self.create(
                    {
                        "page_id": page.id,
                        "website_id": page.website_id.id if page.website_id else False,
                        "page_name": page.name or page.url,
                        "url": page.url,
                        "target_keyword": target_keyword or "",
                    }
                )
            elif target_keyword:
                audit.target_keyword = target_keyword
            audits |= audit
        audits.run_audit()
        return [a.read_dict() for a in audits.sorted(key=lambda r: (r.score, -r.id))]
