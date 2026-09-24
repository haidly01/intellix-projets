# -*- coding: utf-8 -*-
"""
Webhook universel Africa-Con / VICIdial → doorway.call.log
Reçoit les événements fin d'appel de tous les agents IA (Sofia FR, Sofia ES,
Léa QC, Alex, et futurs agents) via n8n après chaque appel Africa-Con.

Endpoint : POST /api/vicidial/webhook/call-ended
Header   : X-Doorway-Key: <DOORWAY_AGENTS_WEBHOOK_KEY>
"""
import json
import logging

from odoo import fields, http
from odoo.http import request

_logger = logging.getLogger(__name__)


class VicidialCallWebhook(http.Controller):

    def _check_key(self):
        expected = (
            request.env["ir.config_parameter"]
            .sudo()
            .get_param("doorway.agents_webhook_key", "")
        ) or "b9059f3e01007b701c73c0877f8d2338e5cad541112305d87012ac6712b377ca"
        provided = (
            request.httprequest.headers.get("X-Doorway-Key")
            or request.httprequest.headers.get("X-Api-Key")
            or ""
        )
        return provided == expected

    def _json_body(self):
        try:
            raw = request.httprequest.data or b"{}"
            return json.loads(raw.decode("utf-8"))
        except Exception:
            return {}

    @http.route(
        [
            "/api/vicidial/webhook/call-ended",
            "/api/vicidial/webhook/call_ended",
        ],
        type="http",
        auth="public",
        methods=["POST"],
        csrf=False,
    )
    def call_ended(self, **kwargs):
        """
        Reçoit fin d'appel Africa-Con/VICIdial depuis n8n.
        Corps JSON attendu :
          - call_sid / uniqueid       : identifiant unique appel
          - campaign_id               : ex. DW_QCB2C
          - agent_id                  : ex. lea_qc
          - phone_number / telephone  : numéro appelé
          - duration_sec / duration   : durée en secondes
          - amd_result                : human / machine / unknown
          - disposition               : VENTE / INTERET / RAPPEL / REFUS / REPONDEUR
          - transcript                : texte transcription
          - recording_url / recording_path : URL ou chemin local du recording
          - partner_id / lead_id      : ID CRM Odoo (optionnel)
          - statut / etat_final       : statut qualification (optionnel)
        """
        if not self._check_key():
            return request.make_response(
                json.dumps({"error": "unauthorized"}),
                status=401,
                headers=[("Content-Type", "application/json")],
            )

        data = self._json_body() or dict(kwargs)

        try:
            result = self._handle_call_ended(data)
            return request.make_response(
                json.dumps(result),
                headers=[("Content-Type", "application/json")],
            )
        except Exception as exc:
            _logger.exception("VicidialCallWebhook.call_ended error: %s", exc)
            return request.make_response(
                json.dumps({"error": str(exc)}),
                status=500,
                headers=[("Content-Type", "application/json")],
            )

    def _handle_call_ended(self, data):
        env = request.env

        # ── Identifiants ──
        call_sid = (
            data.get("call_sid")
            or data.get("uniqueid")
            or data.get("id")
            or ""
        ).strip()
        campaign_key = (
            data.get("campaign_id")
            or data.get("campaign")
            or ""
        ).strip().upper()
        agent_name = (
            data.get("agent_id")
            or data.get("agent_name")
            or ""
        ).strip()
        phone = (
            data.get("phone_number")
            or data.get("telephone")
            or data.get("to")
            or data.get("from")
            or ""
        ).strip()

        # ── Durée ──
        duration = int(
            data.get("duration_sec")
            or data.get("duration")
            or data.get("duree_sec")
            or 0
        )

        # ── AMD ──
        amd_raw = (data.get("amd_result") or "").lower()
        amd_map = {
            "human": "human",
            "machine": "amd_hangup",
            "answering_machine": "amd_hangup",
            "voicemail": "answering_machine",
            "no_answer": "no_answer",
            "busy": "busy",
            "invalid": "invalid",
            "repondeur": "amd_hangup",
        }
        amd_result = amd_map.get(amd_raw, "human" if amd_raw == "" else "human")

        # Ignorer les répondeurs sauf si on veut les logger
        if amd_raw in ("machine", "answering_machine", "repondeur", "fax"):
            _logger.info(
                "VicidialWebhook: répondeur ignoré — %s %s", call_sid, phone
            )
            return {"ok": True, "skipped": True, "reason": "answering_machine"}

        # ── Disposition ──
        statut_raw = (
            data.get("disposition")
            or data.get("statut")
            or data.get("etat_final")
            or ""
        ).upper()
        disp_map = {
            "VENTE": "VENTE",
            "QUALIFIE": "VENTE",
            "LEAD_GAGNANT": "VENTE",
            "HOT": "VENTE",
            "INTERET": "INTERET",
            "WARM": "INTERET",
            "RAPPEL": "RAPPEL",
            "COLD": "RAPPEL",
            "REFUS": "REFUS",
            "NON_QUALIFIE": "REFUS",
            "PAS_INTERESSE": "REFUS",
            "REPONDEUR": "REPONDEUR",
            "INVALIDE": "INVALIDE",
        }
        disposition = disp_map.get(statut_raw, "RAPPEL")

        # ── Transcript ──
        transcript_raw = data.get("transcript") or data.get("transcripcion") or ""
        if isinstance(transcript_raw, list):
            transcript = "\n".join(
                "%s: %s" % (t.get("role", ""), t.get("content", ""))
                for t in transcript_raw
            )
        else:
            transcript = str(transcript_raw)

        # ── Recording URL ──
        recording_url = (
            data.get("recording_url")
            or data.get("recording_path")
            or data.get("audio_url")
            or ""
        ).strip()
        # Convertir chemin local en file:// si nécessaire
        if recording_url and recording_url.startswith("/"):
            recording_url = "file://" + recording_url

        # ── Identification campagnes IA vs humaines ──
        IA_CAMPAIGNS = {
            'DW_FRB2C','DW_FRB2B','DW_QCB2C','DW_QCB2B','DW_LEAFR',
            'SOFIA_ES','SOFIAES','DW_ESREN',
            'RENOFACILE','DW_FB2CP','DW_FB2BM','DW_FB2BF',
            'LEA_FR','LEA_QC','SOUMISSION_QC',
            'CQMTG01','INBOUND_QC','DW_DRIVN','INBOUND_DRIVEN',
            'ITEXQC01','GARQC01',
        }
        is_ia_agent = campaign_key in IA_CAMPAIGNS

        # ── Campagne Odoo ──
        Campaign = env["doorway.campaign"].sudo()
        campaign = Campaign.search(
            [("vicidial_campaign_id", "=", campaign_key)], limit=1
        )
        if not campaign and campaign_key:
            campaign = Campaign.search(
                [("vicidial_campaign_id", "ilike", campaign_key)], limit=1
            )
        if not campaign and campaign_key not in ("CQMTG01", "INBOUND_QC", "ITEXQC01", "GARQC01"):
            _logger.warning(
                "VicidialWebhook: campagne Odoo absente pour %s — pas de fallback Sales/Rénovation",
                campaign_key,
            )

        if campaign_key in ("CQMTG01", "INBOUND_QC"):
            from odoo.addons.doorway_vicidial_campaigns.services.campaign_crm_router import (
                CampaignCrmRouter,
            )
            routed = CampaignCrmRouter(env).route_rosalie(data)
            _logger.info("VicidialWebhook CQMTG01 routed: %s", routed)
            if not campaign:
                return {"ok": bool(routed.get("ok")), "cq": routed}

        if campaign_key in ("ITEXQC01", "GARQC01"):
            from odoo.addons.doorway_vicidial_campaigns.services.campaign_crm_router import (
                CampaignCrmRouter,
            )
            routed = CampaignCrmRouter(env).route(data)
            _logger.info("VicidialWebhook ITEXQC01 routed: %s", routed)
            if not campaign:
                return {"ok": bool(routed.get("ok")), "itex": routed}

        if not campaign:
            _logger.warning(
                "VicidialWebhook: aucune campagne trouvée pour %s", campaign_key
            )
            return {"ok": False, "error": "no_campaign"}

        # ── Lead CRM ──
        lead_id_raw = data.get("lead_id") or data.get("partner_id") or 0
        lead = None
        if lead_id_raw:
            try:
                lead = env["crm.lead"].sudo().browse(int(lead_id_raw))
                if not lead.exists():
                    lead = None
            except Exception:
                lead = None

        # Chercher par téléphone si pas de lead_id
        if not lead and phone:
            lead = (
                env["crm.lead"]
                .sudo()
                .search(
                    [
                        "|",
                        ("phone", "=", phone),
                        ("phone", "=", phone),
                        ("active", "=", True),
                    ],
                    limit=1,
                    order="create_date desc",
                )
            )

        # ── Créer ou mettre à jour call log ──
        CallLog = env["doorway.call.log"].sudo()
        existing = False
        if call_sid:
            existing = CallLog.search(
                [("vicidial_call_id", "=", call_sid)], limit=1
            )

        vals = {
            "campaign_id": campaign.id,
            "phone_number": phone,
            "call_date": fields.Datetime.now(),
            "duration": duration,
            "amd_result": amd_result,
            "disposition": disposition,
            "agent_name": agent_name or campaign_key,
            "vicidial_call_id": call_sid or False,
            "recording_url": recording_url or False,
            "lead_id": lead.id if lead else False,
        }

        if existing:
            existing.write(vals)
            log = existing
            action = "updated"
        else:
            log = CallLog.create(vals)
            action = "created"

        # ── Appliquer politique de rétention ──
        try:
            log._apply_recording_retention_policy()
        except Exception as exc:
            _logger.warning("Retention policy error: %s", exc)

        # ── Coaching Claude si transcript ──
        if transcript and duration > 15:
            try:
                from odoo.addons.doorway_vicidial_campaigns.services.vicidial_service import (
                    VicidialService,
                )
                VicidialService(env)._enrich_call_log_recording(log.id, {
                    "transcript": transcript,
                })
            except Exception as exc:
                _logger.warning("Coaching enrichment error: %s", exc)

        _logger.info(
            "VicidialWebhook: call log %s (%s) — %s %s %ss",
            log.id, action, campaign_key, agent_name, duration,
        )

        # Sauvegarder transcript pour scoring par cron
        transcript_text = data.get("transcript", "")
        if transcript_text and len(transcript_text.strip()) >= 50:
            log.sudo().write({
                "transcript": transcript_text,
                "coaching_status": "pending",
                "is_ia_agent": is_ia_agent,
            })
        return {
            "ok": True,
            "action": action,
            "call_log_id": log.id,
            "campaign": campaign_key,
            "agent": agent_name,
            "duration": duration,
            "disposition": disposition,
            "lead_id": lead.id if lead else None,
        }


def _score_call_with_claude(call_log_id, transcript, is_ia_agent, env):
    """Appel Claude API pour scorer le transcript post-call"""
    import requests as req
    import json as json_lib

    if not transcript or len(transcript.strip()) < 50:
        env['doorway.call.log'].browse(call_log_id).sudo().write({
            'coaching_status': 'skipped',
        })
        return

    api_key = os.environ.get('ANTHROPIC_API_KEY', '')
    if not api_key:
        return

    if is_ia_agent:
        system_prompt = """Tu es un expert en qualification de leads pour call center.
Analyse cette conversation entre un agent IA et un prospect.
Retourne UNIQUEMENT un JSON valide sans markdown avec cette structure exacte:
{
  "score_global": <0-100>,
  "dimensions": {
    "accroche": {"score": <0-10>, "commentaire": "<texte>"},
    "qualification": {"score": <0-20>, "commentaire": "<texte>"},
    "gestion_objections": {"score": <0-20>, "commentaire": "<texte>"},
    "closing": {"score": <0-20>, "commentaire": "<texte>"},
    "fluidite": {"score": <0-30>, "commentaire": "<texte>"}
  },
  "points_forts": ["<point1>", "<point2>"],
  "axes_amelioration": ["<axe1>", "<axe2>"],
  "recommandation": "<texte court>"
}"""
    else:
        system_prompt = """Tu es un coach expert pour agents de call center humains.
Analyse cette conversation et évalue la performance de l'agent humain.
Retourne UNIQUEMENT un JSON valide sans markdown avec cette structure exacte:
{
  "score_global": <0-100>,
  "dimensions": {
    "accroche": {"score": <0-10>, "commentaire": "<texte>"},
    "qualification": {"score": <0-20>, "commentaire": "<texte>"},
    "gestion_objections": {"score": <0-20>, "commentaire": "<texte>"},
    "closing": {"score": <0-20>, "commentaire": "<texte>"},
    "ton_empathie": {"score": <0-30>, "commentaire": "<texte>"}
  },
  "points_forts": ["<point1>", "<point2>"],
  "axes_amelioration": ["<axe1>", "<axe2>"],
  "suggestion_superviseur": "<texte>",
  "recommandation_formation": "<texte>"
}"""

    try:
        resp = req.post(
            'https://api.anthropic.com/v1/messages',
            headers={
                'x-api-key': api_key,
                'anthropic-version': '2023-06-01',
                'content-type': 'application/json',
            },
            json={
                'model': 'claude-sonnet-4-6',
                'max_tokens': 1000,
                'system': system_prompt,
                'messages': [{'role': 'user', 'content': f'Transcript:\n{transcript[:3000]}'}],
            },
            timeout=30,
        )
        if resp.status_code == 200:
            content = resp.json()['content'][0]['text'].strip()
            # Nettoyer markdown si présent
            content = content.replace('```json', '').replace('```', '').strip()
            scoring = json_lib.loads(content)
            env['doorway.call.log'].browse(call_log_id).sudo().write({
                'coaching_score': scoring.get('score_global', 0),
                'coaching_json': json_lib.dumps(scoring),
                'coaching_status': 'done',
            })
        else:
            env['doorway.call.log'].browse(call_log_id).sudo().write({
                'coaching_status': 'error',
            })
    except Exception as e:
        _logger.error('Claude scoring error call_log %s: %s', call_log_id, e)
        try:
            env['doorway.call.log'].browse(call_log_id).sudo().write({
                'coaching_status': 'error',
            })
        except Exception:
            pass
