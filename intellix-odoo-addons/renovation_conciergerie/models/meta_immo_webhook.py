# -*- coding: utf-8 -*-
import json
import re
import secrets
import unicodedata

from odoo import _, api, fields, models
from odoo.exceptions import ValidationError

_TRUE_META = frozenset({"oui", "yes", "true", "1", "o", "y"})
_FALSE_META = frozenset({"non", "no", "false", "0", "n"})


IMMO_N8N_POSTCALL_URL = "https://n8n.intellixcrm.com/webhook/elevenlabs-immo-postcall"


class RenovationMetaImmoWebhook(models.AbstractModel):
    _name = "renovation.meta.immo.webhook"
    _description = "Webhooks Meta Ads + mises à jour n8n — qualification immobilier"

    SCORE_STAGE_XMLID = {
        "hot": "renovation_conciergerie.crm_stage_renovation_immo_qualified",
        "warm": "renovation_conciergerie.crm_stage_renovation_immo_development",
        "cold": "renovation_conciergerie.crm_stage_renovation_immo_unqualified",
    }
    SCORE_TAG_XMLID = {
        "hot": "renovation_conciergerie.crm_tag_score_hot",
        "warm": "renovation_conciergerie.crm_tag_score_warm",
        "cold": "renovation_conciergerie.crm_tag_score_cold",
    }

    @api.model
    def regenerate_meta_immo_webhook_token(self):
        token = secrets.token_urlsafe(32)
        self.env["ir.config_parameter"].sudo().set_param(
            "renovation_conciergerie.meta_immo_webhook_token",
            token,
        )
        return token

    @api.model
    def _ensure_meta_immo_elevenlabs_postcall_webhook(self):
        icp = self.env["ir.config_parameter"].sudo()
        icp.set_param(
            "doorway_agents_dashboard.maison_immo_n8n_postcall_url",
            IMMO_N8N_POSTCALL_URL,
        )
        return self.env["renovation.elevenlabs.postcall"].ensure_webhook(
            IMMO_N8N_POSTCALL_URL,
            "Immo Meta Post-Call n8n",
            "renovation_conciergerie.elevenlabs_immo_postcall_webhook_id",
            "renovation_conciergerie.elevenlabs_immo_webhook_secret",
        )

    @api.model
    def assign_meta_immo_postcall_webhook_to_agents(self):
        bridge = self.env["renovation.elevenlabs.postcall"]
        webhook_id = self._ensure_meta_immo_elevenlabs_postcall_webhook()
        agent_ids = bridge.collect_agent_ids(
            icp_keys=(
                "doorway_agents_dashboard.elevenlabs_agent_id_immo",
                "doorway_agents_dashboard.elevenlabs_agent_id_relance_j1",
                "doorway_agents_dashboard.elevenlabs_agent_id_relance_j3",
                "doorway_agents_dashboard.elevenlabs_agent_id_relance_j7",
                "doorway_agents_dashboard.elevenlabs_agent_id_relance_j14",
            ),
            profile_domain=[("immo_agent_role", "!=", False)],
        )
        updated = bridge.assign_webhook_to_agent_ids(webhook_id, agent_ids)
        return {"updated": updated, "webhook_id": webhook_id}

    @api.model
    def _ensure_meta_immo_webhook_token(self):
        icp = self.env["ir.config_parameter"].sudo()
        if not icp.get_param("renovation_conciergerie.meta_immo_webhook_token"):
            icp.set_param(
                "renovation_conciergerie.meta_immo_webhook_token",
                secrets.token_urlsafe(32),
            )

    @api.model
    def _check_token(self, data):
        expected = (
            self.env["ir.config_parameter"]
            .sudo()
            .get_param("renovation_conciergerie.meta_immo_webhook_token")
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
    def _team_for_meta_immo(self):
        team_xmlid = (
            self.env["ir.config_parameter"]
            .sudo()
            .get_param(
                "renovation_conciergerie.meta_immo_team_xmlid",
                "reno_immobilier.crm_team_reno_immobilier",
            )
        )
        return self.env.ref(team_xmlid, raise_if_not_found=False) or self.env.ref(
            "reno_immobilier.crm_team_reno_immobilier", raise_if_not_found=False
        ) or self.env["crm.team"]

    @api.model
    def _tag_ids_from_xmlids(self, xmlids):
        tags = self.env["crm.tag"]
        for xmlid in xmlids:
            tag = self.env.ref(xmlid, raise_if_not_found=False)
            if tag:
                tags |= tag
        return tags.ids

    @api.model
    def _relance_agent_ids_from_icp(self):
        icp = self.env["ir.config_parameter"].sudo()
        return {
            "j1": icp.get_param("doorway_agents_dashboard.elevenlabs_agent_id_relance_j1") or "",
            "j3": icp.get_param("doorway_agents_dashboard.elevenlabs_agent_id_relance_j3") or "",
            "j7": icp.get_param("doorway_agents_dashboard.elevenlabs_agent_id_relance_j7") or "",
            "j14": icp.get_param("doorway_agents_dashboard.elevenlabs_agent_id_relance_j14") or "",
        }

    @api.model
    def get_elevenlabs_agent_for_relance(self, relance_number):
        """relance_number: 1=J+1, 2=J+3, 3=J+7, 4=J+14."""
        mapping = {1: "j1", 2: "j3", 3: "j7", 4: "j14"}
        key = mapping.get(int(relance_number or 0))
        if not key:
            return ""
        return self._relance_agent_ids_from_icp().get(key) or ""

    @api.model
    def _default_maison_agent(self):
        """Agent qualification J+0 (rôle immo_agent_role, pas le nom affiché)."""
        return self.env["doorway.agent.profile"].get_maison_immo_qualification_profile()

    @api.model
    def _cleanup_immo_test_leads(self):
        """Supprime les leads créés lors des tests Meta (noms / meta_lead_id connus)."""
        Lead = self.env["crm.lead"].sudo()
        domain = [
            "|",
            "|",
            ("immo_meta_lead_id", "in", ("test-validation-001", "val-002")),
            ("name", "ilike", "Validation Meta"),
            ("name", "ilike", "Val2 Meta"),
        ]
        test_leads = Lead.search(domain)
        if test_leads:
            test_leads.unlink()

    @api.model
    def _meta_immo_reference_ad_id(self):
        return (
            self.env["ir.config_parameter"]
            .sudo()
            .get_param("renovation_conciergerie.meta_immo_reference_ad_id")
            or ""
        ).strip()

    @api.model
    def _meta_immo_facebook_page_id(self):
        return (
            self.env["ir.config_parameter"]
            .sudo()
            .get_param("renovation_conciergerie.meta_immo_facebook_page_id")
            or ""
        ).strip()

    @api.model
    def _meta_access_token(self):
        """Token Graph API (Veille sociale — même app Meta)."""
        config = self.env["doorway.veille.config"].sudo().search([], limit=1)
        return (config.meta_access_token or "").strip() if config else ""

    @api.model
    def validate_meta_immo_facebook_page(self):
        """Vérifie la page Maison Recherchée via Graph API."""
        page_id = self._meta_immo_facebook_page_id()
        token = self._meta_access_token()
        if not page_id:
            return {"ok": False, "message": _("ID page Facebook immo non configuré.")}
        if not token:
            return {
                "ok": False,
                "message": _("Token Meta manquant (Veille sociale → Connexions)."),
            }
        try:
            import requests
        except ImportError:
            return {"ok": False, "message": _("Module requests requis.")}

        response = requests.get(
            "https://graph.facebook.com/v21.0/%s" % page_id,
            params={
                "fields": (
                    "id,name,instagram_business_account{id,username},"
                    "connected_instagram_account{id,username}"
                ),
                "access_token": token,
            },
            timeout=25,
        )
        data = response.json()
        if response.status_code >= 400 or data.get("error"):
            err = data.get("error") or {}
            return {
                "ok": False,
                "message": err.get("message") or _("Erreur Graph API."),
            }
        ig = data.get("instagram_business_account") or data.get(
            "connected_instagram_account"
        ) or {}
        icp = self.env["ir.config_parameter"].sudo()
        icp.set_param(
            "renovation_conciergerie.meta_immo_facebook_page_name",
            data.get("name") or "Maison Recherchée",
        )
        return {
            "ok": True,
            "page_id": data.get("id") or page_id,
            "page_name": data.get("name") or "",
            "instagram_id": ig.get("id") or "",
            "instagram_username": ig.get("username") or "",
        }

    @api.model
    def _stage_new(self, team):
        stage = self.env.ref(
            "renovation_conciergerie.crm_stage_renovation_new",
            raise_if_not_found=False,
        )
        if stage and team in stage.team_ids:
            return stage
        return self.env["crm.stage"].search(
            [("team_ids", "in", team.ids)], order="sequence", limit=1
        )

    @staticmethod
    def _norm_meta_value(value):
        text = unicodedata.normalize("NFD", str(value or "").strip().lower())
        text = "".join(ch for ch in text if unicodedata.category(ch) != "Mn")
        return text.replace("_", " ").strip()

    @classmethod
    def _coerce_meta_bool(cls, value):
        if value is None or value is False or value == "":
            return None
        if value is True:
            return True
        token = cls._norm_meta_value(value).replace(" ", "")
        if token in _TRUE_META:
            return True
        if token in _FALSE_META:
            return False
        return None

    @classmethod
    def _pretty_meta_value(cls, value):
        return str(value or "").replace("_", " ").strip()

    @api.model
    def _fill_immo_vals_from_mapped(self, mapped, vals, mapped_keys):
        """Mappe les clés Graph/webhook vers les champs crm.lead. Ne réécrit pas le bonus."""
        property_type = mapped.get("property_type")
        if property_type:
            vals["immo_property_type"] = self._pretty_meta_value(property_type)
            mapped_keys.append("property_type")
        timeline = mapped.get("selling_timeline")
        if timeline:
            vals["immo_selling_timeline"] = self._pretty_meta_value(timeline)
            mapped_keys.append("selling_timeline")
        estimated = mapped.get("estimated_value")
        if estimated:
            vals["immo_estimated_value"] = self._pretty_meta_value(estimated)
            mapped_keys.append("estimated_value")
        owner = self._coerce_meta_bool(mapped.get("is_owner"))
        if owner is not None:
            vals["immo_is_owner_confirmed"] = owner
            mapped_keys.append("is_owner")
        other_agents = self._coerce_meta_bool(mapped.get("other_agents"))
        if other_agents is not None:
            vals["immo_other_agents"] = other_agents
            mapped_keys.append("other_agents")
        return vals

    @api.model
    def _format_raw_meta_answers(self, rows):
        lines = []
        for row in rows or []:
            name = (row.get("name") or "").strip()
            values = [str(v) for v in (row.get("values") or []) if v]
            if name:
                lines.append("%s: %s" % (name, ", ".join(values) if values else ""))
        return lines

    @api.model
    def _ensure_immo_mapped_payload(self, data):
        data = dict(data or {})
        needed = (
            "property_type",
            "selling_timeline",
            "estimated_value",
            "is_owner",
            "other_agents",
        )
        if any(data.get(key) for key in needed) and data.get("_raw_field_data"):
            return data
        leadgen = self.env["renovation.meta.leadgen.webhook"]
        lid = (
            data.get("meta_lead_id")
            or data.get("leadgen_id")
            or data.get("id")
            or ""
        )
        if not lid:
            return data
        graph = leadgen._fetch_lead_from_graph(lid)
        extra = {}
        leadgen._map_field_data((graph or {}).get("field_data"), extra)
        for key, value in extra.items():
            if value and not data.get(key):
                data[key] = value
        if (graph or {}).get("field_data") and not data.get("_raw_field_data"):
            data["_raw_field_data"] = graph.get("field_data")
        return data

    @api.model
    def enrich_lead_from_meta_graph(self, lead):
        """Rattrapage additif d'un lead existant. N'écrase pas description."""
        lead.ensure_one()
        lid = (lead.immo_meta_lead_id or "").strip()
        if not lid:
            return {"ok": False, "reason": "no_meta_lead_id"}
        leadgen = self.env["renovation.meta.leadgen.webhook"]
        graph = leadgen._fetch_lead_from_graph(lid)
        if not graph or graph.get("error"):
            return {
                "ok": False,
                "reason": "graph_empty",
                "error": (graph or {}).get("error") or {},
            }
        mapped = {}
        leadgen._map_field_data(graph.get("field_data"), mapped)
        vals = {}
        mapped_keys = []
        self._fill_immo_vals_from_mapped(mapped, vals, mapped_keys)
        vals["immo_meta_mapped_keys"] = ",".join(mapped_keys) or False
        lead.sudo().write(vals)
        return {
            "ok": True,
            "mapped_keys": mapped_keys,
            "graph_form_id": graph.get("form_id"),
            "graph_created_time": graph.get("created_time"),
        }

    @api.model
    def create_lead_from_meta(self, data):
        team = self._team_for_meta_immo()
        if not team:
            return {"status": "error", "message": _("Équipe CRM introuvable.")}, 500

        data = self._ensure_immo_mapped_payload(data)
        meta = self.env["crm.lead"]._doorway_parse_meta_contact(data)
        contact_name = meta.get("contact_name") or ""
        phone = self._normalize_phone_e164(meta.get("source_phone") or "")
        email = meta.get("source_email") or ""
        city = meta.get("source_ville") or ""
        address = (
            data.get("full_address")
            or data.get("street")
            or data.get("address")
            or ""
        ).strip()
        timeline = (data.get("selling_timeline") or "").strip()
        mortgage = (data.get("current_mortgage") or "").strip()
        estimated = (data.get("estimated_value") or "").strip()

        if not phone and not email:
            return {
                "status": "error",
                "message": _("Téléphone ou courriel requis."),
            }, 400

        meta_lead_id = (
            data.get("meta_lead_id") or data.get("leadgen_id") or data.get("id") or ""
        ).strip()
        if meta_lead_id:
            self.env.cr.execute(
                "SELECT id FROM crm_lead WHERE immo_meta_lead_id = %s LIMIT 1",
                (meta_lead_id[:64],),
            )
            row = self.env.cr.fetchone()
            if row:
                lead = self.env["crm.lead"].sudo().browse(row[0])
                return {
                    "status": "exists",
                    "lead_id": lead.id,
                    "lead_name": lead.name,
                    "message": _("Lead Meta déjà présent."),
                }, 200

        lead_name = (
            (data.get("name") or "").strip()
            or (f"{contact_name} — Éval. marchande" if contact_name else "")
            or (f"Meta Ads — {phone}" if phone else "Meta Ads — Immobilier")
        )

        meta_ad_id = (data.get("ad_id") or data.get("adgroup_id") or "").strip()
        meta_form_id = (data.get("form_id") or data.get("leadgen_form_id") or "").strip()
        raw_answers = self._format_raw_meta_answers(
            data.get("_raw_field_data") or data.get("field_data")
        )
        desc_parts = [
            "Lead Meta Ads — Formulaire évaluation marchande",
            f"ID publicité Meta: {meta_ad_id}" if meta_ad_id else "",
            f"ID formulaire Meta: {meta_form_id}" if meta_form_id else "",
            f"Adresse: {address}" if address else "",
            f"Délai vente: {timeline}" if timeline else "",
            f"Valeur estimée (form): {estimated}" if estimated else "",
            f"Hypothèque: {mortgage}" if mortgage else "",
        ]
        if raw_answers:
            desc_parts.append("Réponses brutes Meta:")
            desc_parts.extend(raw_answers)
        tag_xmlids = [
            "renovation_conciergerie.crm_tag_immo_eval_marchande",
            "renovation_conciergerie.crm_tag_meta_ads_immo",
        ]
        tag_ids = self._tag_ids_from_xmlids(tag_xmlids)

        assignee = team._get_default_assignee()
        route = self.env["renovation.meta.leads.routing"].resolve_route(data)
        agent = (
            self.env["renovation.meta.leads.routing"].pick_agent_profile(route, data)
            or self._default_maison_agent()
        )
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
            "street": address or False,
            "description": "\n".join(p for p in desc_parts if p),
            "immo_selling_timeline": timeline or False,
            "immo_estimated_value": estimated or False,
            "immo_meta_mapped_keys": False,
            "immo_meta_lead_id": (
                data.get("meta_lead_id")
                or data.get("leadgen_id")
                or data.get("id")
                or ""
            )[:64]
            or False,
            "immo_meta_ad_id": meta_ad_id[:64] if meta_ad_id else False,
            "immo_meta_form_id": meta_form_id[:64] if meta_form_id else False,
            "doorway_call_volet": "qualification",
        }
        if tag_ids:
            vals["tag_ids"] = [(6, 0, tag_ids)]
        if assignee:
            vals["user_id"] = assignee.id
        if agent:
            vals["doorway_agent_profile_id"] = agent.id
        company = team.company_id or (assignee.company_id if assignee else False)
        if company:
            vals["company_id"] = company.id

        vals.update(
            self.env["crm.lead"]._doorway_ai_agent_entry_vals(team=team)
        )
        # Instant Forms MR → Leads Gestion, pas Immobilier 93 / Réno 92 / Driven.
        vals["team_id"] = team.id
        vals["lead_provenance"] = "social"
        Source = self.env["utm.source"].sudo()
        mr = Source.search([("name", "=", "Maison Recherchée")], limit=1) or Source.create(
            {"name": "Maison Recherchée"}
        )
        vals["source_id"] = mr.id
        if team.company_id:
            vals["company_id"] = team.company_id.id
        nouveau = self.env.ref(
            "reno_immobilier.crm_stage_nouveau", raise_if_not_found=False
        )
        if nouveau:
            vals["stage_id"] = nouveau.id
        if "reno_immo_lead" in self.env["crm.lead"]._fields:
            vals["reno_immo_lead"] = True

        mapped_keys = []
        self._fill_immo_vals_from_mapped(data, vals, mapped_keys)
        vals["immo_meta_mapped_keys"] = ",".join(mapped_keys) or False

        if self.env["crm.lead"]._doorway_is_test_lead_vals(vals):
            return {
                "status": "ignored",
                "message": _("Lead de test ignoré en production."),
            }, 200

        try:
            lead = self.env["crm.lead"].sudo().create(vals)
        except ValidationError as err:
            existing = self.env["crm.lead"].sudo().browse()
            if email:
                existing = self.env["crm.lead"].sudo().search(
                    [("email_from", "=ilike", email), ("active", "=", True)],
                    limit=1,
                )
            if not existing and phone:
                existing = self.env["crm.lead"].sudo().search(
                    [("phone", "ilike", phone[-10:]), ("active", "=", True)],
                    limit=1,
                )
            if existing:
                if meta_lead_id and not existing.immo_meta_lead_id:
                    existing.write({"immo_meta_lead_id": meta_lead_id[:64]})
                return {
                    "status": "exists",
                    "lead_id": existing.id,
                    "lead_name": existing.name,
                    "message": str(err),
                }, 200
            return {"status": "error", "message": str(err)}, 400
        ref_ad = self._meta_immo_reference_ad_id()
        warnings = []
        if ref_ad and meta_ad_id and meta_ad_id != ref_ad:
            warnings.append(
                _("ad_id Meta (%(got)s) ≠ pub de référence (%(ref)s).")
                % {"got": meta_ad_id, "ref": ref_ad}
            )
        if not agent:
            warnings.append(_("Aucun agent J+0 qualification actif (immo_agent_role)."))
        payload = {
            "status": "success",
            "lead_id": lead.id,
            "lead_name": lead.name,
            "phone": lead.phone,
            "team_id": team.id,
            "team_name": team.name,
            "stage_id": lead.stage_id.id,
            "stage_name": lead.stage_id.name,
            "agent_id": agent.external_agent_id if agent else "",
            "agent_profile_id": agent.id if agent else False,
            "volet": "qualification",
            "from_number": "+14387905970",
            "sip_trunk_sid": "TK4005d66df6aefef66f0a63a711491166",
            "transfer_number": "+14389929200",
            "relance_agents": self._relance_agent_ids_from_icp(),
            "elevenlabs_phone_number_id": (
                self.env["ir.config_parameter"]
                .sudo()
                .get_param("doorway_agents_dashboard.elevenlabs_phone_number_id")
                or ""
            ),
            "elevenlabs_agent_id_immo": (
                self.env["ir.config_parameter"]
                .sudo()
                .get_param("doorway_agents_dashboard.elevenlabs_agent_id_immo")
                or (agent.external_agent_id if agent else "")
            ),
            "immo_agent_role": agent.immo_agent_role if agent else "",
            "meta_immo_facebook_page_id": self._meta_immo_facebook_page_id(),
        }
        if warnings:
            payload["warnings"] = warnings
        return payload, 200

    @api.model
    def _parse_transcript(self, data):
        transcript = data.get("transcript") or data.get("immo_call_transcript")
        if isinstance(transcript, list):
            lines = []
            for item in transcript:
                if isinstance(item, dict):
                    role = item.get("role") or item.get("speaker") or ""
                    text = item.get("message") or item.get("content") or ""
                    lines.append(f"{role}: {text}".strip(": "))
                else:
                    lines.append(str(item))
            return "\n".join(lines)
        return transcript or ""

    @api.model
    def update_lead_from_n8n(self, data):
        lead_id = data.get("lead_id") or data.get("odoo_lead_id")
        if not lead_id:
            return {"status": "error", "message": _("lead_id requis.")}, 400
        lead = self.env["crm.lead"].sudo().browse(int(lead_id))
        if not lead.exists():
            return {"status": "error", "message": _("Lead introuvable.")}, 404

        score = (data.get("score") or data.get("immo_ia_score") or "").lower()
        collection = data.get("data_collection") or {}
        if isinstance(collection, dict):
            timeline = collection.get("selling_timeline") or lead.immo_selling_timeline
            estimated = collection.get("estimated_value") or lead.immo_estimated_value
            motivation = collection.get("motivation") or ""
            is_owner = collection.get("is_owner")
            other_agents = collection.get("other_agents")
        else:
            timeline = lead.immo_selling_timeline
            estimated = lead.immo_estimated_value
            motivation = ""
            is_owner = None
            other_agents = None

        if data.get("do_not_call") is not None:
            vals_extra = {"immo_do_not_call": bool(data.get("do_not_call"))}
        else:
            vals_extra = {}
        if data.get("explicit_refusal") is not None:
            vals_extra["immo_explicit_refusal"] = bool(data.get("explicit_refusal"))
        if data.get("relance_number") is not None:
            vals_extra["immo_relance_number"] = int(data.get("relance_number") or 0)
        if data.get("total_call_attempts") is not None:
            vals_extra["immo_total_call_attempts"] = int(data.get("total_call_attempts") or 0)
        if data.get("increment_call_attempt"):
            vals_extra["immo_total_call_attempts"] = (lead.immo_total_call_attempts or 0) + 1
            vals_extra["immo_last_call_at"] = fields.Datetime.now()
        final_status = (data.get("final_status") or "").lower()
        tag_xmlids = []
        if final_status == "not_interested":
            tag_xmlids.append("renovation_conciergerie.crm_tag_cold_ferme")
            vals_extra["immo_do_not_call"] = True
        elif final_status == "postponed":
            tag_xmlids.append("renovation_conciergerie.crm_tag_nurture_passif")
        elif final_status == "no_answer":
            tag_xmlids.append("renovation_conciergerie.crm_tag_pas_repondu")

        vals = {
            "immo_ia_score": score or lead.immo_ia_score,
            "immo_ia_score_numeric": int(
                data.get("score_numeric") or data.get("immo_ia_score_numeric") or 0
            )
            or lead.immo_ia_score_numeric,
            "elevenlabs_conversation_id": (
                data.get("conversation_id")
                or data.get("elevenlabs_conversation_id")
                or lead.elevenlabs_conversation_id
            ),
            "immo_call_transcript": self._parse_transcript(data)
            or lead.immo_call_transcript,
            "immo_selling_timeline": timeline,
            "immo_estimated_value": estimated,
        }
        if is_owner is not None:
            vals["immo_is_owner_confirmed"] = bool(is_owner)
        if other_agents is not None:
            vals["immo_other_agents"] = bool(other_agents)

        summary = (data.get("summary") or "").strip()
        next_action = (data.get("next_action") or "").strip()
        desc_add = []
        if summary:
            desc_add.append(f"Résumé IA: {summary}")
        if next_action:
            desc_add.append(f"Prochaine action: {next_action}")
        if motivation:
            desc_add.append(f"Motivation: {motivation}")
        if desc_add:
            base = (lead.description or "").strip()
            vals["description"] = (
                base + "\n\n---\n\n" + "\n".join(desc_add) if base else "\n".join(desc_add)
            )

        agent = lead.doorway_agent_profile_id or self._default_maison_agent()
        if data.get("transfer_now"):
            vals["immo_transfer_at"] = fields.Datetime.now()
            vals.update(
                self.env["crm.lead"]._doorway_human_transfer_vals(
                    agent=agent, team=lead.team_id
                )
            )
            vals["priority"] = "2"
        elif score == "hot":
            vals.update(
                self.env["crm.lead"]._doorway_ia_qualified_vals(team=lead.team_id)
            )
            hot_tag = self.env.ref(
                self.SCORE_TAG_XMLID.get("hot"), raise_if_not_found=False
            )
            if hot_tag:
                vals["tag_ids"] = [(4, hot_tag.id)]
            vals["priority"] = "2"
        elif score in ("warm", "cold"):
            score_tag = self.env.ref(
                self.SCORE_TAG_XMLID.get(score), raise_if_not_found=False
            )
            if score_tag:
                vals["tag_ids"] = [(4, score_tag.id)]
            vals["priority"] = "1" if score == "warm" else "0"

        if data.get("nurture_step") is not None:
            vals["immo_nurture_step"] = int(data.get("nurture_step"))

        vals.update(vals_extra)
        if tag_xmlids:
            extra_tags = self._tag_ids_from_xmlids(tag_xmlids)
            if extra_tags:
                vals.setdefault("tag_ids", [])
                for tid in extra_tags:
                    vals["tag_ids"].append((4, tid))

        prob = data.get("probability") or data.get("score_numeric")
        if prob not in (None, ""):
            try:
                vals["probability"] = float(prob)
            except (TypeError, ValueError):
                pass

        if data.get("start_nurture"):
            vals["immo_nurture_active"] = True
            vals["immo_nurture_started_at"] = fields.Datetime.now()
        if data.get("stop_nurture") or data.get("archive_nurture"):
            vals["immo_nurture_active"] = False
            if data.get("archive_nurture"):
                tag_ids = self._tag_ids_from_xmlids(
                    ["renovation_conciergerie.crm_tag_nurture_passif"]
                )
                if tag_ids:
                    vals.setdefault("tag_ids", [])
                    for tid in tag_ids:
                        vals["tag_ids"].append((4, tid))

        lead.write(vals)
        lead._doorway_register_ia_call(data)
        return {
            "status": "success",
            "lead_id": lead.id,
            "stage_name": lead.stage_id.name,
            "immo_ia_score": lead.immo_ia_score,
            "transfer_at": fields.Datetime.to_string(lead.immo_transfer_at)
            if lead.immo_transfer_at
            else False,
            "immo_nurture_active": lead.immo_nurture_active,
        }, 200

    @api.model
    def get_lead_context_for_n8n(self, lead_id):
        """Contexte lead pour workflows n8n (post-call, relances)."""
        lead = self.env["crm.lead"].sudo().browse(int(lead_id))
        if not lead.exists():
            return {"status": "error", "message": _("Lead introuvable.")}, 404
        agent = lead.doorway_agent_profile_id or self._default_maison_agent()
        first = (lead.contact_name or lead.name or "").strip().split()
        relance = self._relance_agent_ids_from_icp()
        icp = self.env["ir.config_parameter"].sudo()
        return {
            "status": "success",
            "lead_id": lead.id,
            "first_name": first[0] if first else "",
            "last_name": " ".join(first[1:]) if len(first) > 1 else "",
            "phone": lead.phone or getattr(lead, "mobile", None) or "",
            "email": lead.email_from or "",
            "full_address": lead.street or "",
            "property_address": lead.street or "",
            "selling_timeline": lead.immo_selling_timeline or "",
            "immo_ia_score": lead.immo_ia_score or "",
            "immo_nurture_step": lead.immo_nurture_step or 0,
            "immo_nurture_active": lead.immo_nurture_active,
            "immo_total_call_attempts": lead.immo_total_call_attempts or 0,
            "immo_do_not_call": lead.immo_do_not_call,
            "immo_explicit_refusal": lead.immo_explicit_refusal,
            "immo_days_since_request": lead.immo_days_since_request,
            "days_since_request": lead.immo_days_since_request,
            "agent_id": agent.external_agent_id if agent else "",
            "relance_agents": relance,
            "elevenlabs_phone_number_id": icp.get_param(
                "doorway_agents_dashboard.elevenlabs_phone_number_id"
            )
            or "",
            "from_number": "+14387905970",
            "transfer_number": "+14389929200",
            "neighborhood": (lead.street or "").split(",")[0].strip(),
            "season": "printemps",
            "market_days": "45",
        }, 200
