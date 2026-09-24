# -*- coding: utf-8 -*-
"""Routage global Meta Lead Ads : page_id / form_id → pipeline, n8n, agent IA."""
from __future__ import annotations

import json
import logging
import secrets

from odoo import _, api, models

_logger = logging.getLogger(__name__)

# Pages / sites connus dans le projet (compléter les page_id manquants dans Paramètres Odoo).
DEFAULT_META_LEADS_GLOBAL_MAP = {
    "version": 1,
    "n8n_webhook_base": "https://n8n.intellixcrm.com/webhook",
    "pages": {
        "964640820063787": {
            "name": "Maison Recherchée",
            "pipeline": "immo",
            "lead_ads": True,
            "form_ids": [
                "1826191751704113",
                "1697837451292893",
                "1016997697520697",
                "1959964661340863",
            ],
            "n8n_webhook": "meta-immo-lead",
            "odoo_create": "immo/meta-lead",
            "webhook_token_icp": "renovation_conciergerie.meta_immo_webhook_token",
            "webhook_header": "X-Immo-Webhook-Token",
            "agent_resolver": "immo_j0",
            "agent_assignment": "default",
            "agent_profile_xmlids": [
                "doorway_agents_dashboard.agent_maison_recherchee",
            ],
        },
        "962295250303049": {
            "name": "ICI Thermopompe",
            "pipeline": "energie",
            "site": "icithermopompe",
            "projet": "thermopompe",
            "lead_ads": True,
            "form_ids": ["1912811406106600"],
            "n8n_webhook": "energie-lead",
            "odoo_create": "energie/lead",
            "webhook_token_icp": "renovation_conciergerie.energie_webhook_token",
            "webhook_header": "X-Energie-Webhook-Token",
            "agent_resolver": "energie_j0",
            "agent_assignment": "default",
            "agent_profile_xmlids": [
                "doorway_agents_dashboard.agent_energie_pro",
            ],
        },
        "1004010452788312": {
            "name": "Énergie Pro",
            "pipeline": "energie",
            "site": "energie_pro",
            "projet": "multi",
            "lead_ads": True,
            "n8n_webhook": "energie-lead",
            "odoo_create": "energie/lead",
            "webhook_token_icp": "renovation_conciergerie.energie_webhook_token",
            "webhook_header": "X-Energie-Webhook-Token",
            "agent_resolver": "energie_j0",
            "agent_assignment": "round_robin",
            "agent_profile_xmlids": [
                "doorway_agents_dashboard.agent_energie_pro",
            ],
        },
        "499982889862307": {
            "name": "Agence Doorway",
            "pipeline": "marketing",
            "lead_ads": True,
            "skip_orchestrator": False,
            "direct_odoo_create": True,
            "form_ids": ["1002390528799358"],
            "odoo_create": "marketing/meta-lead",
            "webhook_token_icp": "renovation_conciergerie.marketing_meta_webhook_token",
            "webhook_header": "X-Marketing-Meta-Webhook-Token",
            "assign_user_login": "zakaria@agencedoorway.com",
            "notes": "Digital Doorway — Zakaria, colonne Nouveau, sans agent IA",
        },
        "574384345749047": {
            "name": "Haidly Reno",
            "pipeline": "haidly",
            "site": "soumissionentrepreneurs",
            "lead_ads": True,
            "skip_orchestrator": False,
            "form_ids": ["1177919251120913"],
            "n8n_webhook": "haidly-lead",
            "odoo_create": "haidly/lead",
            "webhook_token_icp": "renovation_conciergerie.haidly_webhook_token",
            "webhook_header": "X-Haidly-Webhook-Token",
            "agent_resolver": "haidly_j0",
            "agent_assignment": "default",
            "agent_profile_xmlids": [
                "doorway_agents_dashboard.agent_haidly",
            ],
        },
    },
    "sites_fallback": {
        "icithermopompe": {
            "pipeline": "energie",
            "site": "icithermopompe",
            "projet": "thermopompe",
            "n8n_webhook": "energie-lead",
            "odoo_create": "energie/lead",
            "webhook_token_icp": "renovation_conciergerie.energie_webhook_token",
            "webhook_header": "X-Energie-Webhook-Token",
            "agent_resolver": "energie_j0",
            "agent_assignment": "round_robin",
            "agent_profile_xmlids": [
                "doorway_agents_dashboard.agent_energie_pro",
            ],
        },
        "isolationqc": {
            "pipeline": "energie",
            "site": "isolationqc",
            "projet": "isolation",
            "n8n_webhook": "energie-lead",
            "odoo_create": "energie/lead",
            "webhook_token_icp": "renovation_conciergerie.energie_webhook_token",
            "webhook_header": "X-Energie-Webhook-Token",
            "agent_resolver": "energie_j0",
            "agent_assignment": "round_robin",
            "agent_profile_xmlids": [
                "doorway_agents_dashboard.agent_energie_pro",
            ],
            "page_id_pending": True,
            "notes": "Renseigner page_id Meta dans le mapping global",
        },
        "portesetfenetresqc": {
            "pipeline": "energie",
            "site": "portesetfenetresqc",
            "projet": "portes_fenetres",
            "n8n_webhook": "energie-lead",
            "odoo_create": "energie/lead",
            "webhook_token_icp": "renovation_conciergerie.energie_webhook_token",
            "webhook_header": "X-Energie-Webhook-Token",
            "agent_resolver": "energie_j0",
            "agent_assignment": "round_robin",
            "agent_profile_xmlids": [
                "doorway_agents_dashboard.agent_energie_pro",
            ],
            "page_id_pending": True,
        },
        "soumissionentrepreneurs": {
            "pipeline": "haidly",
            "site": "soumissionentrepreneurs",
            "n8n_webhook": "haidly-lead",
            "odoo_create": "haidly/lead",
            "webhook_token_icp": "renovation_conciergerie.haidly_webhook_token",
            "webhook_header": "X-Haidly-Webhook-Token",
            "agent_resolver": "haidly_j0",
            "agent_assignment": "default",
            "agent_profile_xmlids": [
                "doorway_agents_dashboard.agent_haidly",
            ],
            "notes": "Formulaire web — pas Meta page_id",
        },
    },
    "forms": {
        "1016997697520697": {
            "name": "Maison Recherchée — 7 mai",
            "page_id": "964640820063787",
            "pipeline": "immo",
            "n8n_webhook": "meta-immo-lead",
            "odoo_create": "immo/meta-lead",
            "webhook_token_icp": "renovation_conciergerie.meta_immo_webhook_token",
            "webhook_header": "X-Immo-Webhook-Token",
            "agent_resolver": "immo_j0",
            "agent_assignment": "default",
            "agent_profile_xmlids": [
                "doorway_agents_dashboard.agent_maison_recherchee",
            ],
        },
        "1826191751704113": {
            "name": "Maison Recherchée — Immobilier-19 août",
            "page_id": "964640820063787",
            "pipeline": "immo",
            "n8n_webhook": "meta-immo-lead",
            "odoo_create": "immo/meta-lead",
            "webhook_token_icp": "renovation_conciergerie.meta_immo_webhook_token",
            "webhook_header": "X-Immo-Webhook-Token",
            "agent_resolver": "immo_j0",
            "agent_assignment": "default",
            "agent_profile_xmlids": [
                "doorway_agents_dashboard.agent_maison_recherchee",
            ],
        },
        "1697837451292893": {
            "name": "Maison Recherchée — Immobilier",
            "page_id": "964640820063787",
            "pipeline": "immo",
            "n8n_webhook": "meta-immo-lead",
            "odoo_create": "immo/meta-lead",
            "webhook_token_icp": "renovation_conciergerie.meta_immo_webhook_token",
            "webhook_header": "X-Immo-Webhook-Token",
            "agent_resolver": "immo_j0",
            "agent_assignment": "default",
            "agent_profile_xmlids": [
                "doorway_agents_dashboard.agent_maison_recherchee",
            ],
        },
        "1959964661340863": {
            "name": "Maison Recherchée — 19 mai",
            "page_id": "964640820063787",
            "pipeline": "immo",
            "n8n_webhook": "meta-immo-lead",
            "odoo_create": "immo/meta-lead",
            "webhook_token_icp": "renovation_conciergerie.meta_immo_webhook_token",
            "webhook_header": "X-Immo-Webhook-Token",
            "agent_resolver": "immo_j0",
            "agent_assignment": "default",
            "agent_profile_xmlids": [
                "doorway_agents_dashboard.agent_maison_recherchee",
            ],
        },
        "1912811406106600": {
            "name": "ICI Thermopompe — Lead Ads",
            "page_id": "962295250303049",
            "pipeline": "energie",
            "site": "icithermopompe",
            "projet": "thermopompe",
            "n8n_webhook": "energie-lead",
            "odoo_create": "energie/lead",
            "webhook_token_icp": "renovation_conciergerie.energie_webhook_token",
            "webhook_header": "X-Energie-Webhook-Token",
            "agent_resolver": "energie_j0",
            "agent_assignment": "default",
            "agent_profile_xmlids": [
                "doorway_agents_dashboard.agent_energie_pro",
            ],
        },
        "1177919251120913": {
            "name": "Haidly Reno — Lead Ads",
            "page_id": "574384345749047",
            "pipeline": "haidly",
            "site": "soumissionentrepreneurs",
            "n8n_webhook": "haidly-lead",
            "odoo_create": "haidly/lead",
            "webhook_token_icp": "renovation_conciergerie.haidly_webhook_token",
            "webhook_header": "X-Haidly-Webhook-Token",
            "agent_resolver": "haidly_j0",
            "agent_assignment": "default",
            "agent_profile_xmlids": [
                "doorway_agents_dashboard.agent_haidly",
            ],
        },
        "1002390528799358": {
            "name": "Agence Doorway — Lead Ads Marketing",
            "page_id": "499982889862307",
            "pipeline": "marketing",
            "direct_odoo_create": True,
            "odoo_create": "marketing/meta-lead",
            "webhook_token_icp": "renovation_conciergerie.marketing_meta_webhook_token",
            "webhook_header": "X-Marketing-Meta-Webhook-Token",
            "assign_user_login": "zakaria@agencedoorway.com",
        },
    },
}


class RenovationMetaLeadsRouting(models.AbstractModel):
    _name = "renovation.meta.leads.routing"
    _description = "Mapping global Meta Lead Ads → pipelines Doorway"

    @api.model
    def _icp(self):
        return self.env["ir.config_parameter"].sudo()

    @api.model
    def get_global_map(self):
        raw = self._icp().get_param("renovation_conciergerie.meta_leads_global_page_map")
        if not raw:
            return dict(DEFAULT_META_LEADS_GLOBAL_MAP)
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            _logger.warning("meta_leads_global_page_map JSON invalide, défaut utilisé")
            return dict(DEFAULT_META_LEADS_GLOBAL_MAP)
        base = dict(DEFAULT_META_LEADS_GLOBAL_MAP)
        for key in ("version", "n8n_webhook_base", "pages", "sites_fallback", "forms"):
            if key in data:
                if key in ("pages", "sites_fallback", "forms") and isinstance(data[key], dict):
                    base[key] = {**base.get(key, {}), **data[key]}
                else:
                    base[key] = data[key]
        return base

    @api.model
    def _ensure_meta_leads_global_map(self):
        icp = self._icp()
        raw = icp.get_param("renovation_conciergerie.meta_leads_global_page_map")
        if not raw:
            icp.set_param(
                "renovation_conciergerie.meta_leads_global_page_map",
                json.dumps(DEFAULT_META_LEADS_GLOBAL_MAP, ensure_ascii=False, indent=2),
            )
        else:
            try:
                data = json.loads(raw)
            except json.JSONDecodeError:
                data = dict(DEFAULT_META_LEADS_GLOBAL_MAP)
            data = self._merge_default_forms_into_map(data)
            data = self._merge_default_pages_into_map(data)
            icp.set_param(
                "renovation_conciergerie.meta_leads_global_page_map",
                json.dumps(data, ensure_ascii=False, indent=2),
            )
        if not icp.get_param("renovation_conciergerie.meta_leads_hub_webhook_url"):
            icp.set_param(
                "renovation_conciergerie.meta_leads_hub_webhook_url",
                "https://n8n.intellixcrm.com/webhook/meta-leads-hub",
            )
        if not icp.get_param("renovation_conciergerie.meta_leads_routing_token"):
            icp.set_param(
                "renovation_conciergerie.meta_leads_routing_token",
                secrets.token_urlsafe(32),
            )
        self.env["renovation.meta.marketing.webhook"]._ensure_marketing_meta_webhook_token()
        # Sync legacy energie map depuis le global
        gmap = self.get_global_map()
        energie_pages = {
            pid: {
                "site": cfg.get("site") or "",
                "name": cfg.get("name") or pid,
            }
            for pid, cfg in (gmap.get("pages") or {}).items()
            if cfg.get("pipeline") == "energie" and cfg.get("lead_ads", True)
        }
        if energie_pages:
            icp.set_param(
                "renovation_conciergerie.energie_facebook_page_map",
                json.dumps(energie_pages, ensure_ascii=False),
            )
            icp.set_param(
                "renovation_conciergerie.energie_facebook_page_ids",
                ",".join(sorted(energie_pages.keys())),
            )

    @api.model
    def _page_entry(self, page_id):
        page_id = (page_id or "").strip()
        gmap = self.get_global_map()
        if page_id:
            entry = (gmap.get("pages") or {}).get(page_id)
            if entry:
                return dict(entry, page_id=page_id)
        return None

    @api.model
    def _site_entry(self, site):
        site = (site or "").strip().lower()
        if not site:
            return None
        gmap = self.get_global_map()
        entry = (gmap.get("sites_fallback") or {}).get(site)
        return dict(entry) if entry else None

    @api.model
    def _normalize_meta_form_id(self, form_id):
        form_id = (form_id or "").strip()
        if form_id.lower().startswith("f:"):
            form_id = form_id[2:].strip()
        return form_id

    @api.model
    def _form_override(self, form_id):
        form_id = self._normalize_meta_form_id(form_id)
        if not form_id:
            return {}
        forms = self.get_global_map().get("forms") or {}
        entry = forms.get(form_id)
        if entry:
            return dict(entry)
        return {}

    @api.model
    def _merge_default_forms_into_map(self, data):
        """Fusionne les formulaires Meta canoniques (page_id, pipeline, agents)."""
        merged = dict(data or {})
        forms = dict(merged.get("forms") or {})
        for fid, cfg in (DEFAULT_META_LEADS_GLOBAL_MAP.get("forms") or {}).items():
            forms[fid] = {**forms.get(fid, {}), **cfg}
        merged["forms"] = forms
        return merged

    @api.model
    def _merge_default_pages_into_map(self, data):
        """Synchronise les pages Meta canoniques (ex. Haidly Reno Lead Ads)."""
        merged = dict(data or {})
        pages = dict(merged.get("pages") or {})
        for pid, cfg in (DEFAULT_META_LEADS_GLOBAL_MAP.get("pages") or {}).items():
            page = {**pages.get(pid, {}), **cfg}
            if cfg.get("lead_ads"):
                page.pop("skip_orchestrator", None)
            stored_ids = [
                str(x).strip()
                for x in (pages.get(pid, {}).get("form_ids") or [])
                if str(x).strip()
            ]
            default_ids = [
                str(x).strip()
                for x in (cfg.get("form_ids") or [])
                if str(x).strip()
            ]
            seen = []
            for fid in default_ids + stored_ids:
                if fid not in seen:
                    seen.append(fid)
            if seen:
                page["form_ids"] = seen
            pages[pid] = page
        merged["pages"] = pages
        return merged

    @api.model
    def link_meta_form(self, page_id, form_id, form_name=""):
        """Lie un Instant Form à sa page (ICP + forms). Évite le 7 mai figé."""
        page_id = (page_id or "").strip()
        form_id = self._normalize_meta_form_id(form_id)
        if not page_id or not form_id:
            return False
        icp = self._icp()
        raw = icp.get_param("renovation_conciergerie.meta_leads_global_page_map")
        try:
            data = json.loads(raw) if raw else dict(DEFAULT_META_LEADS_GLOBAL_MAP)
        except json.JSONDecodeError:
            data = dict(DEFAULT_META_LEADS_GLOBAL_MAP)
        pages = dict(data.get("pages") or {})
        page = dict(pages.get(page_id) or self._page_entry(page_id) or {})
        if not page.get("pipeline") and not page.get("name"):
            return False
        ids = [str(x).strip() for x in (page.get("form_ids") or []) if str(x).strip()]
        changed = False
        if form_id not in ids:
            ids.append(form_id)
            page["form_ids"] = ids
            pages[page_id] = page
            data["pages"] = pages
            changed = True
        forms = dict(data.get("forms") or {})
        if form_id not in forms:
            forms[form_id] = {
                "name": form_name or ("%s — %s" % (page.get("name") or page_id, form_id)),
                "page_id": page_id,
                "pipeline": page.get("pipeline") or "immo",
                "n8n_webhook": page.get("n8n_webhook"),
                "odoo_create": page.get("odoo_create"),
                "webhook_token_icp": page.get("webhook_token_icp"),
                "webhook_header": page.get("webhook_header"),
                "agent_resolver": page.get("agent_resolver"),
                "agent_assignment": page.get("agent_assignment"),
                "agent_profile_xmlids": list(page.get("agent_profile_xmlids") or []),
            }
            data["forms"] = forms
            changed = True
        elif form_name and not (forms.get(form_id) or {}).get("name"):
            forms[form_id] = {**forms[form_id], "name": form_name}
            data["forms"] = forms
            changed = True
        if changed:
            icp.set_param(
                "renovation_conciergerie.meta_leads_global_page_map",
                json.dumps(data, ensure_ascii=False, indent=2),
            )
            _logger.info(
                "Meta form linked page=%s form=%s name=%s",
                page_id,
                form_id,
                form_name or "",
            )
        return changed

    @api.model
    def detect_site_from_payload(self, data):
        """Heuristique sites Énergie (comme energie_webhook.detect_site_and_projet)."""
        from odoo.addons.renovation_conciergerie.models.energie_webhook import (
            RenovationEnergieWebhook,
        )

        site, _projet = self.env[
            "renovation.energie.webhook"
        ].detect_site_and_projet(data)
        return site

    @api.model
    def resolve_route(self, data):
        """Retourne la route n8n/Odoo pour un lead Meta (page_id, form_id, champs form)."""
        data = data or {}
        page_id = (
            data.get("page_id")
            or data.get("facebook_page_id")
            or data.get("meta_page_id")
            or ""
        ).strip()
        form_id = self._normalize_meta_form_id(
            data.get("form_id")
            or data.get("leadgen_form_id")
            or data.get("formId")
            or ""
        )

        entry = self._page_entry(page_id)
        form_ov = self._form_override(form_id)
        if not entry and form_ov:
            entry = dict(form_ov)
            if form_ov.get("page_id"):
                page_id = page_id or form_ov["page_id"]
                entry["page_id"] = form_ov["page_id"]
        site = (data.get("site") or data.get("energie_site_source") or "").strip().lower()
        if not entry and site:
            entry = self._site_entry(site)
            if entry:
                entry = dict(entry, page_id=page_id or "", site=site)
        if not entry and not page_id:
            site = site or self.detect_site_from_payload(data)
            if site:
                entry = self._site_entry(site)
                if entry:
                    entry = dict(entry, page_id="", site=site)

        if entry and form_ov:
            entry = {**entry, **form_ov}

        gmap = self.get_global_map()
        base_url = (
            self._icp().get_param("renovation_conciergerie.meta_leads_hub_webhook_url")
            or gmap.get("n8n_webhook_base")
            or "https://n8n.intellixcrm.com/webhook/meta-leads-hub"
        )
        n8n_root = base_url.rsplit("/webhook/", 1)[0] + "/webhook"

        if not entry:
            return {
                "status": "unknown",
                "pipeline": "unknown",
                "page_id": page_id,
                "form_id": form_id,
                "skip_orchestrator": True,
                "message": _(
                    "page_id %(pid)s non mappé — ajoutez-le dans Paramètres → Mapping Meta global."
                )
                % {"pid": page_id or "(vide)"},
                "n8n_webhook": None,
                "n8n_webhook_url": None,
            }

        pipeline = entry.get("pipeline") or "unknown"
        skip = bool(entry.get("skip_orchestrator")) or pipeline in (
            "veille",
            "unknown",
        )
        if pipeline == "marketing" and entry.get("direct_odoo_create"):
            skip = False
        wh = entry.get("n8n_webhook")
        return {
            "status": "ok",
            "pipeline": pipeline,
            "page_id": page_id or entry.get("page_id") or "",
            "form_id": form_id,
            "page_name": entry.get("name") or "",
            "site": entry.get("site") or site or "",
            "projet": entry.get("projet") or "",
            "skip_orchestrator": skip,
            "direct_odoo_create": bool(entry.get("direct_odoo_create")),
            "n8n_webhook": wh,
            "n8n_webhook_url": f"{n8n_root}/{wh}" if wh else None,
            "odoo_create": entry.get("odoo_create"),
            "webhook_token_icp": entry.get("webhook_token_icp"),
            "webhook_header": entry.get("webhook_header"),
            "assign_user_login": entry.get("assign_user_login") or "",
            "agent_assignment": entry.get("agent_assignment") or "default",
            "agent_resolver": entry.get("agent_resolver"),
            "notes": entry.get("notes") or "",
        }

    @api.model
    def _profiles_from_xmlids(self, xmlids):
        Profile = self.env["doorway.agent.profile"].sudo()
        profiles = Profile
        for xmlid in xmlids or []:
            rec = self.env.ref(xmlid, raise_if_not_found=False)
            if rec and rec.status == "active":
                profiles |= rec
        return profiles

    @api.model
    def _default_profile_for_resolver(self, resolver):
        Profile = self.env["doorway.agent.profile"].sudo()
        if resolver == "immo_j0":
            return Profile.get_maison_immo_qualification_profile()
        if resolver == "energie_j0":
            return Profile.get_energie_pro_qualification_profile()
        if resolver == "haidly_j0":
            return Profile.get_haidly_qualification_profile()
        return Profile.browse()

    @api.model
    def pick_agent_profile(self, route, data=None):
        """Choisit l'agent IA J+0 (round-robin si plusieurs profils sur même form/page)."""
        data = data or {}
        page_id = (route.get("page_id") or data.get("page_id") or "").strip()
        form_id = (route.get("form_id") or data.get("form_id") or "").strip()
        entry = self._page_entry(page_id) or {}
        form_ov = self._form_override(form_id)
        cfg = {**entry, **form_ov}
        assignment = (
            form_ov.get("agent_assignment")
            or route.get("agent_assignment")
            or cfg.get("agent_assignment")
            or "default"
        )
        xmlids = (
            form_ov.get("agent_profile_xmlids")
            or cfg.get("agent_profile_xmlids")
            or []
        )
        resolver = (
            form_ov.get("agent_resolver")
            or route.get("agent_resolver")
            or cfg.get("agent_resolver")
        )

        pool = self._profiles_from_xmlids(xmlids)
        if not pool and resolver:
            default = self._default_profile_for_resolver(resolver)
            if default:
                pool = default

        if not pool:
            return self.env["doorway.agent.profile"].browse()

        if assignment != "round_robin" or len(pool) <= 1:
            return pool[:1]

        rr_key = f"renovation_conciergerie.meta_leads_rr_{form_id or page_id or 'default'}"
        icp = self._icp()
        idx = int(icp.get_param(rr_key) or 0) % len(pool)
        icp.set_param(rr_key, str(idx + 1))
        return pool[idx]

    @api.model
    def list_pages_summary(self):
        """Liste pour UI / doc."""
        gmap = self.get_global_map()
        rows = []
        for page_id, cfg in sorted((gmap.get("pages") or {}).items()):
            rows.append(
                {
                    "page_id": page_id,
                    "name": cfg.get("name"),
                    "pipeline": cfg.get("pipeline"),
                    "n8n_webhook": cfg.get("n8n_webhook"),
                    "site": cfg.get("site") or "",
                    "lead_ads": cfg.get("lead_ads", True),
                }
            )
        for site, cfg in sorted((gmap.get("sites_fallback") or {}).items()):
            rows.append(
                {
                    "page_id": cfg.get("page_id") or _("(à renseigner)"),
                    "name": cfg.get("name") or site,
                    "pipeline": cfg.get("pipeline"),
                    "n8n_webhook": cfg.get("n8n_webhook"),
                    "site": site,
                    "lead_ads": True,
                    "pending_page_id": bool(cfg.get("page_id_pending")),
                }
            )
        return rows
