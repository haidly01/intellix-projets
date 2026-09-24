# -*- coding: utf-8 -*-
import json
import logging
import re
import secrets

import requests

from odoo import _, api, fields, models

_logger = logging.getLogger(__name__)

ENERGIE_N8N_POSTCALL_URL = "https://n8n.intellixcrm.com/webhook/elevenlabs-energie-postcall"


class RenovationEnergieWebhook(models.AbstractModel):
    _name = "renovation.energie.webhook"
    _description = "Webhooks leads Énergie Pro (3 sites) + mises à jour n8n"

    SITE_TAG_XMLID = {
        "icithermopompe": "renovation_conciergerie.crm_tag_source_icithermopompe",
        "isolationqc": "renovation_conciergerie.crm_tag_source_isolationqc",
        "portesetfenetresqc": "renovation_conciergerie.crm_tag_source_portesfenetresqc",
    }
    PROJET_TAG_XMLID = {
        "thermopompe": "renovation_conciergerie.crm_tag_projet_thermopompe",
        "isolation": "renovation_conciergerie.crm_tag_projet_isolation",
        "portes_fenetres": "renovation_conciergerie.crm_tag_projet_portes_fenetres",
        "multi": "renovation_conciergerie.crm_tag_projet_multi",
    }
    SCORE_TAG_XMLID = {
        "hot": "renovation_conciergerie.crm_tag_energie_hot",
        "warm": "renovation_conciergerie.crm_tag_energie_warm",
        "cold": "renovation_conciergerie.crm_tag_energie_cold",
    }

    @api.model
    def regenerate_energie_webhook_token(self):
        token = secrets.token_urlsafe(32)
        self.env["ir.config_parameter"].sudo().set_param(
            "renovation_conciergerie.energie_webhook_token",
            token,
        )
        return token

    @api.model
    def _ensure_energie_meta_pages_icp(self):
        """Synchronise pages Énergie depuis le mapping Meta global."""
        self.env["renovation.meta.leads.routing"]._ensure_meta_leads_global_map()
        icp = self.env["ir.config_parameter"].sudo()
        if not icp.get_param("renovation_conciergerie.energie_facebook_page_icithermopompe_id"):
            icp.set_param(
                "renovation_conciergerie.energie_facebook_page_icithermopompe_id",
                "962295250303049",
            )

    @api.model
    def _ensure_energie_webhook_token(self):
        icp = self.env["ir.config_parameter"].sudo()
        if not icp.get_param("renovation_conciergerie.energie_webhook_token"):
            icp.set_param(
                "renovation_conciergerie.energie_webhook_token",
                secrets.token_urlsafe(32),
            )

    @api.model
    def _energie_elevenlabs_client(self):
        from odoo.addons.doorway_agents_dashboard.services.elevenlabs_client import (
            BASE,
            ElevenLabsClient,
        )

        return ElevenLabsClient(self.env), BASE

    @api.model
    def _find_energie_postcall_webhook_id(self, client, base_url):
        response = requests.get(
            "%s/workspace/webhooks" % base_url,
            headers=client.headers,
            timeout=30,
        )
        if response.status_code >= 400:
            _logger.warning(
                "Liste webhooks ElevenLabs Énergie: %s %s",
                response.status_code,
                response.text[:300],
            )
            return ""
        for wh in (response.json() or {}).get("webhooks") or []:
            if (wh.get("webhook_url") or "").rstrip("/") == ENERGIE_N8N_POSTCALL_URL:
                return wh.get("webhook_id") or ""
        return ""

    @api.model
    def _create_energie_postcall_webhook(self, client, base_url):
        response = requests.post(
            "%s/workspace/webhooks" % base_url,
            headers=client.headers,
            json={
                "settings": {
                    "name": "Énergie Pro Post-Call n8n",
                    "webhook_url": ENERGIE_N8N_POSTCALL_URL,
                    "auth_type": "hmac",
                    "events": ["transcript"],
                    "transcript_format": "json",
                }
            },
            timeout=30,
        )
        if response.status_code >= 400:
            _logger.warning(
                "Création webhook post-call Énergie: %s %s",
                response.status_code,
                response.text[:400],
            )
            return "", ""
        body = response.json() or {}
        return body.get("webhook_id") or "", body.get("webhook_secret") or ""

    @api.model
    def _ensure_energie_elevenlabs_postcall_webhook(self):
        """Webhook workspace ElevenLabs dédié → n8n elevenlabs-energie-postcall."""
        icp = self.env["ir.config_parameter"].sudo()
        icp.set_param(
            "renovation_conciergerie.energie_n8n_postcall_url",
            ENERGIE_N8N_POSTCALL_URL,
        )
        webhook_id = (
            icp.get_param("renovation_conciergerie.elevenlabs_energie_postcall_webhook_id")
            or ""
        ).strip()
        client, base_url = self._energie_elevenlabs_client()
        if not webhook_id:
            webhook_id = self._find_energie_postcall_webhook_id(client, base_url)
        if not webhook_id:
            webhook_id, webhook_secret = self._create_energie_postcall_webhook(
                client, base_url
            )
            if webhook_secret and not icp.get_param(
                "renovation_conciergerie.elevenlabs_energie_webhook_secret"
            ):
                icp.set_param(
                    "renovation_conciergerie.elevenlabs_energie_webhook_secret",
                    webhook_secret,
                )
        if webhook_id:
            icp.set_param(
                "renovation_conciergerie.elevenlabs_energie_postcall_webhook_id",
                webhook_id,
            )
        return webhook_id

    @api.model
    def assign_energie_postcall_webhook_to_agents(self):
        """Lie le webhook post-call Énergie aux agents ConvAI (override par agent)."""
        webhook_id = self._ensure_energie_elevenlabs_postcall_webhook()
        if not webhook_id:
            return {"updated": 0, "webhook_id": ""}

        icp = self.env["ir.config_parameter"].sudo()
        agent_ids = set()
        for key in (
            "doorway_agents_dashboard.elevenlabs_agent_id_energie",
            "doorway_agents_dashboard.elevenlabs_agent_id_energie_j1",
            "doorway_agents_dashboard.elevenlabs_agent_id_energie_j3",
            "doorway_agents_dashboard.elevenlabs_agent_id_energie_j7",
        ):
            aid = (icp.get_param(key) or "").strip()
            if aid and not aid.startswith("ELEVENLABS"):
                agent_ids.add(aid)

        profiles = self.env["doorway.agent.profile"].sudo().search(
            [("energie_agent_role", "!=", False)]
        )
        for profile in profiles:
            aid = (profile.external_agent_id or "").strip()
            if aid and not aid.startswith("ELEVENLABS"):
                agent_ids.add(aid)

        client, base_url = self._energie_elevenlabs_client()
        payload = {
            "platform_settings": {
                "workspace_overrides": {
                    "webhooks": {
                        "post_call_webhook_id": webhook_id,
                        "events": ["transcript"],
                        "transcript_format": "json",
                    }
                }
            }
        }
        updated = 0
        for agent_id in agent_ids:
            response = requests.patch(
                "%s/convai/agents/%s" % (base_url, agent_id),
                headers=client.headers,
                json=payload,
                timeout=60,
            )
            if response.status_code < 400:
                updated += 1
            else:
                _logger.warning(
                    "PATCH webhook Énergie agent %s: %s",
                    agent_id,
                    response.text[:300],
                )
        return {"updated": updated, "webhook_id": webhook_id}

    @api.model
    def _check_token(self, data):
        expected = (
            self.env["ir.config_parameter"]
            .sudo()
            .get_param("renovation_conciergerie.energie_webhook_token")
        )
        if not expected:
            return True
        provided = (
            data.get("token")
            or data.get("webhook_token")
            or data.get("webhook_secret")
        )
        return provided == expected

    @api.model
    def _normalize_phone_e164(self, phone, default_country="+1"):
        if not phone:
            return ""
        digits = re.sub(r"\D", "", str(phone))
        if len(digits) == 10:
            return f"{default_country}{digits}"
        if len(digits) == 11 and digits.startswith("1"):
            return f"+{digits}"
        if str(phone).strip().startswith("+"):
            return "+" + digits
        return f"{default_country}{digits}" if digits else ""

    @api.model
    def _meta_access_token(self):
        config = self.env["doorway.veille.config"].sudo().search([], limit=1)
        return (config.meta_access_token or "").strip() if config else ""

    @api.model
    def _energie_facebook_page_ids(self):
        raw = (
            self.env["ir.config_parameter"]
            .sudo()
            .get_param("renovation_conciergerie.energie_facebook_page_ids")
            or ""
        )
        return [p.strip() for p in raw.split(",") if p.strip()]

    @api.model
    def _energie_facebook_page_map(self):
        raw = (
            self.env["ir.config_parameter"]
            .sudo()
            .get_param("renovation_conciergerie.energie_facebook_page_map")
            or "{}"
        )
        try:
            data = json.loads(raw)
            return data if isinstance(data, dict) else {}
        except json.JSONDecodeError:
            return {}

    @api.model
    def _site_from_facebook_page_id(self, page_id):
        page_id = (page_id or "").strip()
        if not page_id:
            return ""
        route = self.env["renovation.meta.leads.routing"].resolve_route(
            {"page_id": page_id}
        )
        if route.get("site"):
            return route["site"]
        entry = self._energie_facebook_page_map().get(page_id) or {}
        return (entry.get("site") or "").strip()

    @api.model
    def validate_energie_facebook_pages(self):
        """Vérifie les pages Meta liées à Énergie Pro via Graph API."""
        page_ids = self._energie_facebook_page_ids()
        if not page_ids:
            return {"ok": False, "message": _("Aucune page Facebook Énergie configurée.")}
        token = self._meta_access_token()
        if not token:
            return {
                "ok": False,
                "message": _("Token Meta manquant (Veille sociale → Connexions)."),
            }
        try:
            import requests
        except ImportError:
            return {"ok": False, "message": _("Module requests requis.")}

        icp = self.env["ir.config_parameter"].sudo()
        page_map = dict(self._energie_facebook_page_map())
        pages = []
        errors = []
        for page_id in page_ids:
            response = requests.get(
                "https://graph.facebook.com/v21.0/%s" % page_id,
                params={"fields": "id,name", "access_token": token},
                timeout=25,
            )
            data = response.json()
            if response.status_code >= 400 or data.get("error"):
                err = (data.get("error") or {}).get("message") or _("Erreur Graph API")
                errors.append("%s: %s" % (page_id, err))
                continue
            name = data.get("name") or page_id
            pages.append({"id": data.get("id") or page_id, "name": name})
            entry = page_map.get(page_id) or {}
            entry["name"] = name
            if not entry.get("site"):
                entry["site"] = entry.get("site") or ""
            page_map[page_id] = entry

        icp.set_param(
            "renovation_conciergerie.energie_facebook_page_map",
            json.dumps(page_map, ensure_ascii=False),
        )
        if errors and not pages:
            return {"ok": False, "message": "\n".join(errors)}
        return {
            "ok": True,
            "pages": pages,
            "errors": errors,
        }

    @api.model
    def detect_site_and_projet(self, data):
        page_id = (
            data.get("page_id")
            or data.get("facebook_page_id")
            or data.get("meta_page_id")
            or ""
        ).strip()
        site_from_page = self._site_from_facebook_page_id(page_id)
        raw = " ".join(
            str(data.get(k) or "")
            for k in (
                "source",
                "site",
                "lead_site",
                "page_url",
                "form_name",
                "website",
                "energie_site_source",
            )
        ).lower()
        if "icithermopompe" in raw or "thermopompe" in raw:
            return "icithermopompe", "thermopompe"
        if "isolationqc" in raw or (
            "isolation" in raw and "portes" not in raw and "fenetre" not in raw
        ):
            return "isolationqc", "isolation"
        if "portesetfenetres" in raw or "portes" in raw or "fenetres" in raw:
            return "portesetfenetresqc", "portes_fenetres"
        site = (data.get("energie_site_source") or data.get("site") or "").strip()
        projet = (data.get("energie_projet_type") or data.get("project_type") or "").strip()
        if site in self.SITE_TAG_XMLID:
            if not projet:
                projet = {
                    "icithermopompe": "thermopompe",
                    "isolationqc": "isolation",
                    "portesetfenetresqc": "portes_fenetres",
                }.get(site, "multi")
            return site, projet
        if site_from_page in self.SITE_TAG_XMLID:
            projet = {
                "icithermopompe": "thermopompe",
                "isolationqc": "isolation",
                "portesetfenetresqc": "portes_fenetres",
            }.get(site_from_page, "multi")
            return site_from_page, projet
        return "inconnu", projet or "multi"

    @api.model
    def _tag_ids_from_xmlids(self, xmlids):
        tags = self.env["crm.tag"]
        for xmlid in xmlids:
            tag = self.env.ref(xmlid, raise_if_not_found=False)
            if tag:
                tags |= tag
        return tags.ids

    @api.model
    def _default_energie_agent(self):
        return self.env["doorway.agent.profile"].get_energie_pro_qualification_profile()

    @api.model
    def _relance_agent_ids_from_icp(self):
        icp = self.env["ir.config_parameter"].sudo()
        return {
            "j1": icp.get_param("doorway_agents_dashboard.elevenlabs_agent_id_energie_j1")
            or "",
            "j3": icp.get_param("doorway_agents_dashboard.elevenlabs_agent_id_energie_j3")
            or "",
            "j7": icp.get_param("doorway_agents_dashboard.elevenlabs_agent_id_energie_j7")
            or "",
        }

    @api.model
    def _team_renovation(self):
        # Isolation / portes / ICI → Leads Gestion, plus Réno 92.
        return self.env.ref(
            "reno_immobilier.crm_team_reno_immobilier",
            raise_if_not_found=False,
        ) or self.env.ref(
            "renovation_conciergerie.crm_team_renovation",
            raise_if_not_found=False,
        ) or self.env["crm.team"].search([], limit=1)

    @api.model
    def create_lead_from_webhook(self, data):
        team = self._team_renovation()
        if not team:
            return {"status": "error", "message": _("Équipe CRM introuvable.")}, 500

        meta_page_id = (
            data.get("page_id")
            or data.get("facebook_page_id")
            or data.get("meta_page_id")
            or ""
        ).strip()
        allowed_pages = self._energie_facebook_page_ids()
        site, projet = self.detect_site_and_projet(data)
        first = (data.get("first_name") or "").strip()
        last = (data.get("last_name") or "").strip()
        contact_name = " ".join(p for p in (first, last) if p).strip()
        phone = self._normalize_phone_e164(
            data.get("phone") or data.get("mobile") or data.get("tel")
        )
        email = (data.get("email") or data.get("email_from") or "").strip()
        city = (data.get("lead_city") or data.get("city") or "").strip()

        if not phone and not email:
            return {
                "status": "error",
                "message": _("Téléphone ou courriel requis."),
            }, 400

        labels = {
            "icithermopompe": "Thermopompe",
            "isolationqc": "Isolation",
            "portesetfenetresqc": "Portes & Fenêtres",
            "inconnu": "Énergie",
        }
        lead_name = (
            (data.get("name") or "").strip()
            or (f"{contact_name} — {labels.get(site, 'Énergie')}" if contact_name else "")
            or (f"Énergie Pro — {phone}" if phone else "Énergie Pro")
        )

        chauffage = (data.get("chauffage_actuel") or data.get("current_heating") or "").strip()
        chauffage_map = {
            "mazout": "mazout",
            "oil": "mazout",
            "propane": "propane",
            "electrique": "electrique",
            "électrique": "electrique",
            "gaz": "gaz_naturel",
        }
        chauffage_sel = chauffage_map.get(chauffage.lower(), chauffage or False)

        tag_xmlids = []
        if site in self.SITE_TAG_XMLID:
            tag_xmlids.append(self.SITE_TAG_XMLID[site])
        if projet in self.PROJET_TAG_XMLID:
            tag_xmlids.append(self.PROJET_TAG_XMLID[projet])
        if chauffage_sel == "mazout":
            tag_xmlids.append("renovation_conciergerie.crm_tag_chauffage_mazout")
        elif chauffage_sel == "propane":
            tag_xmlids.append("renovation_conciergerie.crm_tag_chauffage_propane")
        elif chauffage_sel == "electrique":
            tag_xmlids.append("renovation_conciergerie.crm_tag_chauffage_electrique")

        route = self.env["renovation.meta.leads.routing"].resolve_route(
            {**data, "page_id": meta_page_id, "site": site}
        )
        agent = (
            self.env["renovation.meta.leads.routing"].pick_agent_profile(route, data)
            or self._default_energie_agent()
        )
        vals = {
            "name": lead_name,
            "type": "opportunity",
            "team_id": team.id,
            "contact_name": contact_name or False,
            "email_from": email or False,
            "phone": phone or False,
            "city": city or False,
            "energie_site_source": site,
            "energie_projet_type": projet if projet in dict(
                self.PROJET_TAG_XMLID
            ) else "multi",
            "energie_chauffage_actuel": chauffage_sel or False,
            "doorway_call_volet": "qualification",
        }
        if meta_page_id:
            vals["energie_meta_page_id"] = meta_page_id[:64]
        if tag_xmlids:
            vals["tag_ids"] = [(6, 0, self._tag_ids_from_xmlids(tag_xmlids))]
        if agent:
            vals["doorway_agent_profile_id"] = agent.id

        assignee = team._get_default_assignee()
        if assignee:
            vals["user_id"] = assignee.id
        company = team.company_id or (assignee.company_id if assignee else False)
        if company:
            vals["company_id"] = company.id

        vals.update(
            self.env["crm.lead"]._doorway_ai_agent_entry_vals(team=team)
        )
        vals["team_id"] = team.id
        source_labels = {
            "icithermopompe": "ICI Thermopompe",
            "isolationqc": "Isolation QC",
            "portesetfenetresqc": "Portes et Fenêtres QC",
        }
        label = source_labels.get(site)
        if label:
            Source = self.env["utm.source"].sudo()
            src = Source.search([("name", "=", label)], limit=1) or Source.create(
                {"name": label}
            )
            vals["source_id"] = src.id
        if team.company_id:
            vals["company_id"] = team.company_id.id

        lead = self.env["crm.lead"].sudo().create(vals)
        icp = self.env["ir.config_parameter"].sudo()
        payload = {
            "status": "success",
            "lead_id": lead.id,
            "lead_name": lead.name,
            "phone": lead.phone,
            "lead_site": site,
            "project_type": projet,
            "agent_id": agent.external_agent_id if agent else "",
            "agent_profile_id": agent.id if agent else False,
            "from_number": "+15818900456",
            "sip_trunk_sid": "TK36b2a72091465e309606d218a3af145d",
            "transfer_number": "+14389929200",
            "relance_agents": self._relance_agent_ids_from_icp(),
            "elevenlabs_phone_number_id": icp.get_param(
                "doorway_agents_dashboard.elevenlabs_phone_number_id_energie"
            )
            or "",
            "elevenlabs_agent_id_energie": icp.get_param(
                "doorway_agents_dashboard.elevenlabs_agent_id_energie"
            )
            or (agent.external_agent_id if agent else ""),
            "n8n_postcall_webhook_url": ENERGIE_N8N_POSTCALL_URL,
            "energie_facebook_page_ids": allowed_pages,
            "facebook_page_id": meta_page_id,
        }
        warnings = []
        if meta_page_id and allowed_pages and meta_page_id not in allowed_pages:
            warnings.append(
                _("page_id Meta %(got)s non listé pour Énergie Pro (%(ref)s).")
                % {"got": meta_page_id, "ref": ", ".join(allowed_pages)}
            )
        if warnings:
            payload["warnings"] = warnings
        return payload, 200

    @api.model
    def update_lead_from_n8n(self, data):
        lead_id = int(data.get("lead_id") or data.get("odoo_lead_id") or 0)
        if not lead_id:
            return {"status": "error", "message": _("lead_id requis.")}, 400
        lead = self.env["crm.lead"].sudo().browse(lead_id).exists()
        if not lead:
            return {"status": "error", "message": _("Lead introuvable.")}, 404

        vals = {}
        score = (data.get("score") or data.get("energie_ia_score") or "").lower()
        if score in ("hot", "warm", "cold"):
            vals["energie_ia_score"] = score
            tag = self.env.ref(
                self.SCORE_TAG_XMLID.get(score), raise_if_not_found=False
            )
            if tag:
                vals["tag_ids"] = [(4, tag.id)]
        if data.get("score_numeric") is not None:
            vals["energie_ia_score_numeric"] = int(data.get("score_numeric") or 0)
        if data.get("subvention_estimee") is not None:
            vals["energie_subvention_estimee"] = float(
                data.get("subvention_estimee") or 0
            )
        if data.get("programmes_eligibles"):
            vals["energie_programmes_eligibles"] = str(data["programmes_eligibles"])[:255]
        if data.get("transcript") or data.get("energie_call_transcript"):
            vals["energie_call_transcript"] = (
                data.get("transcript") or data.get("energie_call_transcript")
            )
        if data.get("conversation_id"):
            vals["energie_elevenlabs_conv_id"] = str(data["conversation_id"])[:64]
        agent = lead.doorway_agent_profile_id or self._default_energie_agent()
        if data.get("transfer_now"):
            vals["energie_transfer_at"] = fields.Datetime.now()
            vals.update(
                self.env["crm.lead"]._doorway_human_transfer_vals(
                    agent=agent, team=lead.team_id
                )
            )
        elif score == "hot" or data.get("final_status") == "hot":
            vals.update(
                self.env["crm.lead"]._doorway_ia_qualified_vals(team=lead.team_id)
            )
            vals["priority"] = "2"
        if data.get("do_not_call"):
            vals["energie_do_not_call"] = True
        if data.get("increment_call_attempt"):
            vals["energie_total_call_attempts"] = (lead.energie_total_call_attempts or 0) + 1
        if data.get("nurture_active") is not None:
            vals["energie_nurture_active"] = bool(data.get("nurture_active"))

        for field, key in (
            ("energie_chauffage_actuel", "chauffage_actuel"),
            ("energie_type_thermopompe", "type_thermopompe"),
            ("energie_zones_isolation", "zones_isolation"),
            ("energie_nb_ouvertures", "nb_ouvertures"),
        ):
            if data.get(key) is not None:
                vals[field] = data.get(key)

        if vals:
            lead.write(vals)
        return {"status": "success", "lead_id": lead.id}, 200

    @api.model
    def get_lead_context_for_n8n(self, lead_id):
        lead = self.env["crm.lead"].sudo().browse(int(lead_id)).exists()
        if not lead:
            return {"status": "error", "message": _("Lead introuvable.")}, 404
        agent = lead.doorway_agent_profile_id or self._default_energie_agent()
        return {
            "status": "success",
            "lead_id": lead.id,
            "first_name": (lead.contact_name or lead.name or "").split()[0],
            "phone": lead.phone,
            "lead_site": lead.energie_site_source or "inconnu",
            "project_type": lead.energie_projet_type or "multi",
            "current_heating": lead.energie_chauffage_actuel or "",
            "lead_city": lead.city or "",
            "agent_id": agent.external_agent_id if agent else "",
            "relance_agents": self._relance_agent_ids_from_icp(),
        }, 200
