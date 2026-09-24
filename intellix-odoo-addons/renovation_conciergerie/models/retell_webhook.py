import hashlib
import hmac
import json
import logging
import re
import secrets
import time

from odoo import _, api, models

_logger = logging.getLogger(__name__)

SIGNATURE_PATTERN = re.compile(r"v=(\d+),d=([a-f0-9]+)", re.IGNORECASE)
CREATE_LEAD_EVENTS = frozenset(
    {"call_started", "call_ended", "call_analyzed", "call_inbound"}
)


class RenovationRetellWebhook(models.AbstractModel):
    _name = "renovation.retell.webhook"
    _description = "Webhooks Agents IA (n8n / ElevenLabs) → opportunités CRM"

    PIPELINE_CONFIG = {
        "renovation": {
            "team_xmlid": "renovation_conciergerie.crm_team_renovation",
            "token_key": "renovation_conciergerie.retell_webhook_token",
        },
        "marketing": {
            "team_xmlid": "renovation_conciergerie.crm_team_marketing",
            "token_key": "renovation_conciergerie.marketing_retell_webhook_token",
        },
        "immobilier": {
            "team_xmlid": "renovation_conciergerie.crm_team_immobilier",
            "token_key": "renovation_conciergerie.immobilier_agent_webhook_token",
        },
    }

    @api.model
    def _ensure_retell_webhook_token(self):
        self._ensure_token("renovation_conciergerie.retell_webhook_token")

    @api.model
    def _ensure_marketing_retell_webhook_token(self):
        self._ensure_token("renovation_conciergerie.marketing_retell_webhook_token")

    @api.model
    def _ensure_immobilier_agent_webhook_token(self):
        self._ensure_token("renovation_conciergerie.immobilier_agent_webhook_token")

    @api.model
    def _ensure_token(self, key):
        icp = self.env["ir.config_parameter"].sudo()
        if not icp.get_param(key):
            icp.set_param(key, secrets.token_urlsafe(32))

    @api.model
    def _team_for_pipeline(self, pipeline_key):
        config = self.PIPELINE_CONFIG.get(pipeline_key)
        if not config:
            return self.env["crm.team"]
        return self.env.ref(config["team_xmlid"], raise_if_not_found=False) or self.env[
            "crm.team"
        ]

    @api.model
    def verify_retell_signature(self, raw_body, signature_header):
        """Vérifie X-Retell-Signature avec la clé API Retell (HMAC-SHA256)."""
        api_key = (
            self.env["ir.config_parameter"]
            .sudo()
            .get_param("renovation_conciergerie.retell_api_key")
        )
        if not signature_header:
            return bool(api_key) is False
        if not api_key:
            _logger.warning("Retell webhook: signature reçue mais API key absente.")
            return False

        match = SIGNATURE_PATTERN.search(signature_header or "")
        if not match:
            return False

        timestamp, digest = match.group(1), match.group(2)
        try:
            ts_ms = int(timestamp)
        except ValueError:
            return False
        if abs(int(time.time() * 1000) - ts_ms) > 5 * 60 * 1000:
            return False

        payload = f"{raw_body}{timestamp}".encode("utf-8")
        expected = hmac.new(
            api_key.encode("utf-8"), payload, hashlib.sha256
        ).hexdigest()
        return hmac.compare_digest(expected, digest)

    @api.model
    def _check_optional_token(self, payload, pipeline_key="renovation"):
        config = self.PIPELINE_CONFIG.get(pipeline_key)
        if not config:
            return False
        expected = (
            self.env["ir.config_parameter"].sudo().get_param(config["token_key"])
        )
        if not expected:
            return True
        provided = payload.get("token") or payload.get("webhook_token")
        return provided == expected

    @api.model
    def _normalize_phone(self, phone):
        if not phone:
            return ""
        return re.sub(r"[^\d+]", "", str(phone).strip())

    @api.model
    def _customer_phone_from_call(self, call):
        direction = (call.get("direction") or "inbound").lower()
        from_number = call.get("from_number") or ""
        to_number = call.get("to_number") or ""
        if direction == "outbound":
            return to_number or from_number
        return from_number or to_number

    @api.model
    def _contact_name_from_call(self, call):
        dynamic = call.get("retell_llm_dynamic_variables") or {}
        if not isinstance(dynamic, dict):
            dynamic = {}
        for key in ("customer_name", "contact_name", "name", "caller_name"):
            value = (dynamic.get(key) or "").strip()
            if value:
                return value
        metadata = call.get("metadata") or {}
        if isinstance(metadata, dict):
            for key in ("customer_name", "contact_name", "name"):
                value = (metadata.get(key) or "").strip()
                if value:
                    return value
        return ""

    @api.model
    def _build_lead_description(self, call, event):
        parts = [f"Événement Agent IA: {event or 'n/a'}"]
        volet = (call.get("metadata") or {}).get("volet")
        if volet:
            parts.append(f"Volet: {volet}")
        if call.get("direction"):
            parts.append(f"Direction: {call.get('direction')}")
        if call.get("disconnection_reason"):
            parts.append(f"Fin d'appel: {call.get('disconnection_reason')}")
        if call.get("call_status"):
            parts.append(f"Statut: {call.get('call_status')}")
        transcript = (call.get("transcript") or "").strip()
        if transcript:
            parts.append(f"Transcription:\n{transcript}")
        analysis = call.get("call_analysis")
        if isinstance(analysis, dict) and analysis:
            parts.append(
                "Analyse:\n" + json.dumps(analysis, ensure_ascii=False, indent=2)
            )
        collected = call.get("collected_dynamic_variables")
        if isinstance(collected, dict) and collected:
            parts.append(
                "Variables collectées:\n"
                + json.dumps(collected, ensure_ascii=False, indent=2)
            )
        return "\n\n".join(parts)

    @api.model
    def _find_lead_for_call(self, call, call_id, team):
        Lead = self.env["crm.lead"].sudo()
        metadata = call.get("metadata") or {}
        if isinstance(metadata, dict) and metadata.get("lead_id"):
            lead = Lead.browse(int(metadata["lead_id"])).exists()
            if lead:
                return lead

        if call_id:
            log = self.env["renovation.retell.call.log"].sudo().search(
                [("retell_call_id", "=", call_id)], limit=1
            )
            if log.lead_id:
                return log.lead_id

        phone = self._normalize_phone(self._customer_phone_from_call(call))
        if phone:
            domain = [("phone", "ilike", phone[-10:])]
            if team:
                domain = [("team_id", "=", team.id)] + domain
            lead = Lead.search(domain, order="id desc", limit=1)
            if lead:
                return lead
        return Lead

    @api.model
    def _create_lead_from_retell(self, call, call_id, event, team):
        if not team:
            raise ValueError(_("Pipeline CRM introuvable pour ce webhook."))

        phone = self._customer_phone_from_call(call)
        contact_name = self._contact_name_from_call(call)
        lead_name = contact_name or (
            f"Agent IA — {phone}" if phone else f"Agent IA — {call_id or 'appel'}"
        )

        assignee = team._get_default_assignee()
        lead_vals = {
            "name": lead_name,
            "type": "opportunity",
            "team_id": team.id,
            "lead_provenance": "retell",
            "contact_name": contact_name or False,
            "phone": phone or False,
            "description": self._build_lead_description(call, event),
        }
        if assignee:
            lead_vals["user_id"] = assignee.id
        company = team.company_id or (assignee.company_id if assignee else False)
        if company:
            lead_vals["company_id"] = company.id
        lead = self.env["crm.lead"].sudo().create(lead_vals)
        return lead

    @api.model
    def _ensure_retell_log(self, lead, call, call_id):
        Log = self.env["renovation.retell.call.log"].sudo()
        log = Log.search([("retell_call_id", "=", call_id)], limit=1) if call_id else Log
        vals = {
            "lead_id": lead.id,
            "partner_id": lead.partner_id.id if lead.partner_id else False,
            "phone_number": self._customer_phone_from_call(call),
            "status": call.get("call_status") or call.get("status") or "in_progress",
            "duration_seconds": int(call.get("duration_seconds") or 0),
            "transcript_url": call.get("transcript_url") or False,
            "recording_url": call.get("recording_url") or False,
            "raw_payload": json.dumps(call, ensure_ascii=True),
        }
        if call_id:
            vals["retell_call_id"] = call_id
        if log:
            log.write(vals)
            return log
        if not call_id:
            return Log
        return Log.create(vals)

    @api.model
    def _update_lead_from_call(self, lead, call, event, team):
        vals = {"lead_provenance": "retell"}
        if team and (not lead.team_id or lead.team_id != team):
            vals["team_id"] = team.id
        contact_name = self._contact_name_from_call(call)
        if contact_name and not lead.contact_name:
            vals["contact_name"] = contact_name
        phone = self._customer_phone_from_call(call)
        if phone and not lead.phone:
            vals["phone"] = phone
        description = self._build_lead_description(call, event)
        if description:
            existing = (lead.description or "").strip()
            if not existing or "Événement Agent IA:" in existing or "Événement Retell:" in existing:
                vals["description"] = description
            elif event in ("call_ended", "call_analyzed"):
                vals["description"] = f"{existing}\n\n---\n\n{description}"
        lead.write(vals)
        return lead

    @api.model
    def _parse_payload(self, payload):
        event = payload.get("event")
        # Format n8n / Odoo (remplace Retell)
        if not event and payload.get("source") in ("odoo", "n8n", "elevenlabs"):
            event = payload.get("event_type") or "call_ended"
        if event == "call_inbound":
            inbound = payload.get("call_inbound") or {}
            call = {
                "direction": "inbound",
                "from_number": inbound.get("from_number"),
                "to_number": inbound.get("to_number"),
                "agent_id": inbound.get("agent_id"),
                "metadata": inbound.get("metadata") or {},
                "retell_llm_dynamic_variables": inbound.get("dynamic_variables")
                or {},
            }
            return event, call, None

        call = payload.get("call")
        if isinstance(call, dict):
            if payload.get("volet") and isinstance(call.get("metadata"), dict):
                call["metadata"]["volet"] = payload["volet"]
            elif payload.get("volet"):
                call["metadata"] = {"volet": payload["volet"]}
            return event, call, call.get("call_id") or call.get("id")

        if payload.get("from_number") or payload.get("to_number"):
            call = dict(payload)
            if payload.get("volet"):
                meta = call.get("metadata") if isinstance(call.get("metadata"), dict) else {}
                meta["volet"] = payload["volet"]
                call["metadata"] = meta
            call_id = (
                call.get("call_id") or call.get("id") or payload.get("retell_call_id")
            )
            return event, call, call_id

        call_id = (
            payload.get("call_id") or payload.get("id") or payload.get("retell_call_id")
        )
        return event, payload, call_id

    @api.model
    def process_webhook_payload(self, payload, pipeline_key="renovation"):
        """
        Crée ou met à jour une opportunité (étape Retell) dans le pipeline ciblé.
        Retourne un dict avec éventuellement inbound_response pour call_inbound.
        """
        team = self._team_for_pipeline(pipeline_key)
        event, call, call_id = self._parse_payload(payload)

        if event == "call_inbound":
            lead = self._create_lead_from_retell(call, None, event, team)
            return {
                "lead_id": lead.id,
                "inbound_response": {
                    "call_inbound": {
                        "metadata": {"lead_id": lead.id},
                        "dynamic_variables": {
                            "customer_name": lead.contact_name or lead.name,
                        },
                    }
                },
            }

        if event not in CREATE_LEAD_EVENTS and not call_id:
            return {"status": "ignored", "event": event}

        lead = self._find_lead_for_call(call, call_id, team)
        if not lead or not lead.id:
            if event in CREATE_LEAD_EVENTS:
                lead = self._create_lead_from_retell(call, call_id, event, team)
            else:
                return {"status": "ignored", "event": event, "reason": "no_lead"}
        else:
            lead = self._update_lead_from_call(lead, call, event, team)

        if call_id:
            self._ensure_retell_log(lead, call, call_id)

        return {
            "status": "success",
            "event": event,
            "lead_id": lead.id,
            "team_name": lead.team_id.name,
            "stage_name": lead.stage_id.name,
            "lead_provenance": lead.lead_provenance,
        }
