# -*- coding: utf-8 -*-
import re
import secrets

from odoo import _, api, fields, models

UPLOAD_URL = "https://soumissionentrepreneurs.com/"


class RenovationHaidlyWebhook(models.AbstractModel):
    _name = "renovation.haidly.webhook"
    _description = "Webhooks leads Haidly — SoumissionEntrepreneurs.com"

    PROJET_TAG_XMLID = {
        "cuisine": "renovation_conciergerie.crm_tag_reno_cuisine",
        "salle_de_bain": "renovation_conciergerie.crm_tag_reno_salle_de_bain",
        "sous_sol": "renovation_conciergerie.crm_tag_reno_sous_sol",
        "agrandissement": "renovation_conciergerie.crm_tag_reno_agrandissement",
        "exterieur": "renovation_conciergerie.crm_tag_reno_exterieure",
        "patio": "renovation_conciergerie.crm_tag_reno_patio_terrasse",
        "pergola": "renovation_conciergerie.crm_tag_reno_pergola",
        "pool_house": "renovation_conciergerie.crm_tag_reno_pool_house",
        "pieux": "renovation_conciergerie.crm_tag_reno_pieux",
        "multi": "renovation_conciergerie.crm_tag_reno_multi_projets",
    }
    SCORE_TAG_XMLID = {
        "hot": "renovation_conciergerie.crm_tag_haidly_hot",
        "warm": "renovation_conciergerie.crm_tag_haidly_warm",
        "cold": "renovation_conciergerie.crm_tag_haidly_cold",
    }
    SUBVENTION_TAG_XMLID = {
        "renoclimat": "renovation_conciergerie.crm_tag_eligible_renoclimat",
        "cirhm": "renovation_conciergerie.crm_tag_eligible_cirhm",
        "ciad": "renovation_conciergerie.crm_tag_eligible_ciad",
        "tps_tvq": "renovation_conciergerie.crm_tag_eligible_tps_tvq",
        "renoregion": "renovation_conciergerie.crm_tag_eligible_renoregion",
    }
    STAGE_XMLID = {
        "Qualifié": "renovation_conciergerie.crm_stage_renovation_immo_qualified",
        "Qualifié (IA)": "renovation_conciergerie.crm_stage_renovation_immo_qualified",
    }

    @api.model
    def regenerate_haidly_webhook_token(self):
        token = secrets.token_urlsafe(32)
        self.env["ir.config_parameter"].sudo().set_param(
            "renovation_conciergerie.haidly_webhook_token",
            token,
        )
        return token

    HAIDLY_N8N_POSTCALL_URL = "https://n8n.intellixcrm.com/webhook/haidly-postcall"

    @api.model
    def _ensure_haidly_elevenlabs_postcall_webhook(self):
        """Webhook post-call ElevenLabs → n8n haidly-postcall."""
        icp = self.env["ir.config_parameter"].sudo()
        icp.set_param(
            "renovation_conciergerie.haidly_n8n_postcall_url",
            self.HAIDLY_N8N_POSTCALL_URL,
        )
        return self.env["renovation.elevenlabs.postcall"].ensure_webhook(
            self.HAIDLY_N8N_POSTCALL_URL,
            "Haidly Post-Call n8n",
            "renovation_conciergerie.elevenlabs_haidly_postcall_webhook_id",
            "renovation_conciergerie.elevenlabs_haidly_webhook_secret",
        )

    @api.model
    def assign_haidly_postcall_webhook_to_agents(self):
        bridge = self.env["renovation.elevenlabs.postcall"]
        webhook_id = self._ensure_haidly_elevenlabs_postcall_webhook()
        agent_ids = bridge.collect_agent_ids(
            icp_keys=(
                "doorway_agents_dashboard.elevenlabs_agent_id_haidly",
                "doorway_agents_dashboard.elevenlabs_agent_id_haidly_j1",
                "doorway_agents_dashboard.elevenlabs_agent_id_haidly_j3",
                "doorway_agents_dashboard.elevenlabs_agent_id_haidly_j7",
                "doorway_agents_dashboard.elevenlabs_agent_id_haidly_j14",
            ),
            profile_domain=[("haidly_agent_role", "!=", False)],
        )
        updated = bridge.assign_webhook_to_agent_ids(webhook_id, agent_ids)
        return {"updated": updated, "webhook_id": webhook_id}

    @api.model
    def _ensure_haidly_webhook_token(self):
        icp = self.env["ir.config_parameter"].sudo()
        if not icp.get_param("renovation_conciergerie.haidly_webhook_token"):
            icp.set_param(
                "renovation_conciergerie.haidly_webhook_token",
                secrets.token_urlsafe(32),
            )

    @api.model
    def _check_token(self, data):
        expected = (
            self.env["ir.config_parameter"]
            .sudo()
            .get_param("renovation_conciergerie.haidly_webhook_token")
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
    def detect_project_type(self, data):
        raw = " ".join(
            str(data.get(k) or "")
            for k in (
                "project_type",
                "reno_types",
                "project",
                "service",
                "form_name",
                "message",
                "comments",
            )
        ).lower()
        mapping = (
            ("salle_de_bain", ("salle de bain", "sdb", "bain", "douche")),
            ("cuisine", ("cuisine", "kitchen")),
            ("sous_sol", ("sous-sol", "sous sol", "basement")),
            ("agrandissement", ("agrandissement", "extension", "étage")),
            ("patio", ("patio", "terrasse", "deck")),
            ("pergola", ("pergola",)),
            ("pool_house", ("pool house", "cabanon piscine")),
            ("pieux", ("pieux", "pieu viss")),
            ("exterieur", ("extérieur", "exterieur", "façade", "toiture", "fenêtre")),
        )
        for key, needles in mapping:
            if any(n in raw for n in needles):
                return key
        explicit = (data.get("project_type") or data.get("reno_project_type") or "").strip()
        if explicit in self.PROJET_TAG_XMLID:
            return explicit
        return "multi"

    @api.model
    def _tag_ids_from_xmlids(self, xmlids):
        tags = self.env["crm.tag"]
        for xmlid in xmlids:
            tag = self.env.ref(xmlid, raise_if_not_found=False)
            if tag:
                tags |= tag
        return tags.ids

    @api.model
    def _default_haidly_agent(self):
        return self.env["doorway.agent.profile"].get_haidly_qualification_profile()

    @api.model
    def _relance_agent_ids_from_icp(self):
        icp = self.env["ir.config_parameter"].sudo()
        return {
            "j1": icp.get_param("doorway_agents_dashboard.elevenlabs_agent_id_haidly_j1")
            or "",
            "j3": icp.get_param("doorway_agents_dashboard.elevenlabs_agent_id_haidly_j3")
            or "",
            "j7": icp.get_param("doorway_agents_dashboard.elevenlabs_agent_id_haidly_j7")
            or "",
            "j14": icp.get_param("doorway_agents_dashboard.elevenlabs_agent_id_haidly_j14")
            or "",
        }

    @api.model
    def _team_renovation(self):
        return self.env.ref(
            "renovation_conciergerie.crm_team_renovation",
            raise_if_not_found=False,
        ) or self.env["crm.team"].search([], limit=1)

    @api.model
    def create_lead_from_webhook(self, data):
        team = self._team_renovation()
        if not team:
            return {"status": "error", "message": _("Équipe CRM introuvable.")}, 500

        meta = self.env["crm.lead"]._doorway_parse_meta_contact(data)
        contact_name = meta.get("contact_name") or ""
        phone = self._normalize_phone_e164(meta.get("source_phone") or "")
        email = meta.get("source_email") or ""
        city = meta.get("source_ville") or ""
        projet = self.detect_project_type(data)

        if not phone and not email:
            return {
                "status": "error",
                "message": _("Téléphone ou courriel requis."),
            }, 400

        labels = {
            "cuisine": "Cuisine",
            "salle_de_bain": "Salle de bain",
            "sous_sol": "Sous-sol",
            "agrandissement": "Agrandissement",
            "exterieur": "Réno extérieure",
            "patio": "Patio / Terrasse",
            "pergola": "Pergola",
            "pool_house": "Pool house",
            "pieux": "Pieux vissés",
            "multi": "Rénovation",
        }
        lead_name = (
            (data.get("name") or "").strip()
            or (
                f"{contact_name} — {labels.get(projet, 'Rénovation')}"
                if contact_name
                else ""
            )
            or (f"SoumissionEntrepreneurs — {phone}" if phone else "SoumissionEntrepreneurs")
        )

        tag_xmlids = [
            "renovation_conciergerie.crm_tag_source_soumissionentrepreneurs",
            "renovation_conciergerie.crm_tag_plans_3d_offerts",
        ]
        if projet in self.PROJET_TAG_XMLID:
            tag_xmlids.append(self.PROJET_TAG_XMLID[projet])

        meta_page_id = (
            data.get("page_id")
            or data.get("facebook_page_id")
            or data.get("meta_page_id")
            or ""
        ).strip()
        meta_form_id = (
            self.env["renovation.meta.leads.routing"]
            ._normalize_meta_form_id(
                data.get("form_id")
                or data.get("leadgen_form_id")
                or data.get("formId")
                or ""
            )
        )
        route = self.env["renovation.meta.leads.routing"].resolve_route(
            {**data, "page_id": meta_page_id, "site": "soumissionentrepreneurs"}
        )
        agent = (
            self.env["renovation.meta.leads.routing"].pick_agent_profile(route, data)
            or self._default_haidly_agent()
        )
        budget_raw = (data.get("budget_range") or data.get("reno_budget") or "").strip()
        budget_map = {
            "<10": "moins_10k",
            "moins_10": "moins_10k",
            "10_25": "10_25k",
            "25_50": "25_50k",
            "50_100": "50_100k",
            "100": "100k_plus",
        }
        valid_budgets = {
            "moins_10k",
            "10_25k",
            "25_50k",
            "50_100k",
            "100k_plus",
            "inconnu",
        }
        budget_sel = budget_map.get(budget_raw)
        if not budget_sel and budget_raw in valid_budgets:
            budget_sel = budget_raw

        vals = {
            "name": lead_name,
            "type": "opportunity",
            "team_id": team.id,
            "source_prenom": meta.get("source_prenom") or False,
            "source_nom": meta.get("source_nom") or False,
            "source_email": email or False,
            "source_phone": phone or False,
            "source_ville": city or False,
            "contact_name": contact_name or False,
            "email_from": email or False,
            "phone": phone or False,
            "city": city or False,
            "reno_project_type": projet,
            "reno_types": (data.get("reno_types") or projet).strip()[:255],
            "reno_budget": budget_sel or False,
            "reno_property_type": data.get("property_type")
            or data.get("reno_property_type")
            or False,
            "haidly_source": (
                data.get("source")
                or ("meta_lead_ads" if meta_form_id else "soumissionentrepreneurs")
            ).strip()[:64],
            "doorway_call_volet": "qualification",
            "reno_plans_3d_offerts": True,
        }
        if meta_form_id or meta_page_id:
            desc_bits = [
                "Lead Meta Ads — Haidly Reno",
                f"ID page Meta: {meta_page_id}" if meta_page_id else "",
                f"ID formulaire Meta: {meta_form_id}" if meta_form_id else "",
            ]
            vals["description"] = "\n".join(p for p in desc_bits if p)
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

        if self.env["crm.lead"]._doorway_is_test_lead_vals(vals):
            return {
                "status": "ignored",
                "message": _("Lead de test ignoré en production."),
            }, 200

        lead = self.env["crm.lead"].sudo().create(vals)
        icp = self.env["ir.config_parameter"].sudo()
        payload = {
            "status": "success",
            "lead_id": lead.id,
            "lead_name": lead.name,
            "phone": lead.phone,
            "project_type": projet,
            "city": city,
            "upload_url": UPLOAD_URL,
            "agent_id": agent.external_agent_id if agent else "",
            "agent_profile_id": agent.id if agent else False,
            "from_number": "+15817058118",
            "sip_trunk_sid": "TK3d6c7ea376c52bca4e8e81c3b10db400",
            "transfer_number": "+14389929200",
            "relance_agents": self._relance_agent_ids_from_icp(),
            "elevenlabs_phone_number_id": icp.get_param(
                "doorway_agents_dashboard.elevenlabs_phone_number_id_haidly"
            )
            or "",
            "elevenlabs_agent_id_haidly": icp.get_param(
                "doorway_agents_dashboard.elevenlabs_agent_id_haidly"
            )
            or (agent.external_agent_id if agent else ""),
            "n8n_postcall_webhook_url": "https://n8n.intellixcrm.com/webhook/haidly-postcall",
        }
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
        score = (data.get("score") or data.get("haidly_ia_score") or "").lower()
        if score in ("hot", "warm", "cold"):
            vals["haidly_ia_score"] = score
            tag = self.env.ref(
                self.SCORE_TAG_XMLID.get(score), raise_if_not_found=False
            )
            if tag:
                vals.setdefault("tag_ids", [])
                vals["tag_ids"].append((4, tag.id))
        if data.get("score_numeric") is not None:
            vals["haidly_ia_score_numeric"] = int(data.get("score_numeric") or 0)
        if data.get("subvention_estimee") is not None:
            vals["reno_subvention_estimee"] = float(data.get("subvention_estimee") or 0)
        if data.get("subventions_applicables"):
            vals["reno_subventions_applicables"] = str(
                data["subventions_applicables"]
            )[:255]
            for key in self.SUBVENTION_TAG_XMLID:
                if key in str(data["subventions_applicables"]).lower():
                    tag = self.env.ref(
                        self.SUBVENTION_TAG_XMLID[key], raise_if_not_found=False
                    )
                    if tag:
                        vals.setdefault("tag_ids", [])
                        vals["tag_ids"].append((4, tag.id))
        if data.get("transcript") or data.get("haidly_call_transcript"):
            vals["haidly_call_transcript"] = (
                data.get("transcript") or data.get("haidly_call_transcript")
            )
        if data.get("conversation_id"):
            vals["haidly_elevenlabs_conv_id"] = str(data["conversation_id"])[:64]
        agent = lead.doorway_agent_profile_id or self._default_haidly_agent()
        if data.get("transfer_now"):
            vals["haidly_transfer_at"] = fields.Datetime.now()
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
            vals["haidly_do_not_call"] = True
        if data.get("increment_call_attempt"):
            vals["haidly_total_call_attempts"] = (
                lead.haidly_total_call_attempts or 0
            ) + 1
        if data.get("nurture_active") is not None:
            vals["haidly_nurture_active"] = bool(data.get("nurture_active"))
        if data.get("photos_uploaded"):
            vals["reno_photos_uploadees"] = True
            tag = self.env.ref(
                "renovation_conciergerie.crm_tag_photos_uploadees",
                raise_if_not_found=False,
            )
            if tag:
                vals.setdefault("tag_ids", [])
                vals["tag_ids"].append((4, tag.id))
        if data.get("upload_link_sent"):
            vals["reno_lien_photos_envoye"] = True
        if data.get("summary"):
            lead.message_post(
                body=_("Résumé appel Haidly: %s") % str(data["summary"])[:2000],
                message_type="comment",
            )

        odoo_stage = data.get("odoo_stage") or ""
        stage_xmlid = self.STAGE_XMLID.get(odoo_stage)
        if stage_xmlid and not data.get("transfer_now"):
            stage = self.env.ref(stage_xmlid, raise_if_not_found=False)
            if stage:
                vals["stage_id"] = stage.id

        for field, key in (
            ("reno_budget", "budget_range"),
            ("reno_delai", "delai"),
            ("reno_style", "style"),
            ("reno_property_type", "property_type"),
            ("reno_project_type", "project_type"),
            ("reno_projet_multigenerationnel", "multigenerational"),
            ("reno_aine_present", "senior_accessibility"),
        ):
            if data.get(key) is not None:
                vals[field] = data.get(key)

        if vals:
            lead.write(vals)
        lead._doorway_register_ia_call(data)
        return {"status": "success", "lead_id": lead.id}, 200

    @api.model
    def get_lead_context_for_n8n(self, lead_id):
        lead = self.env["crm.lead"].sudo().browse(int(lead_id)).exists()
        if not lead:
            return {"status": "error", "message": _("Lead introuvable.")}, 404
        agent = lead.doorway_agent_profile_id or self._default_haidly_agent()
        name = (lead.contact_name or lead.name or "").strip()
        first = name.split()[0] if name else ""
        return {
            "status": "success",
            "lead_id": lead.id,
            "first_name": first,
            "lead_name": first,
            "phone": lead.phone,
            "project_type": lead.reno_project_type or "multi",
            "city": lead.city or "",
            "budget_range": lead.reno_budget or "",
            "property_type": lead.reno_property_type or "",
            "upload_url": UPLOAD_URL,
            "agent_id": agent.external_agent_id if agent else "",
            "relance_agents": self._relance_agent_ids_from_icp(),
            "n8n_postcall_webhook_url": "https://n8n.intellixcrm.com/webhook/haidly-postcall",
            "haidly_total_call_attempts": lead.haidly_total_call_attempts or 0,
            "haidly_do_not_call": bool(lead.haidly_do_not_call),
        }, 200
