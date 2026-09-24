# -*- coding: utf-8 -*-
import json
import logging

from odoo import fields, http
from odoo.http import request

from odoo.addons.doorway_agents_dashboard.services.config_loader import get_secret

_logger = logging.getLogger(__name__)


class AgentWebhookController(http.Controller):
    def _webhook_key(self):
        return get_secret(
            request.env,
            "DOORWAY_AGENTS_WEBHOOK_KEY",
            "doorway_agents_dashboard.webhook_token",
        )

    def _check_key(self):
        expected = self._webhook_key()
        provided = request.httprequest.headers.get("X-Doorway-Key")
        if not provided:
            provided = request.httprequest.headers.get("X-Doorway-Token")
        if not provided:
            provided = request.params.get("token")
        return expected and provided == expected

    def _json_body(self):
        raw = request.httprequest.get_data(as_text=True) or ""
        if not raw:
            return {}
        try:
            return json.loads(raw)
        except (TypeError, ValueError):
            _logger.warning("Webhook JSON invalide")
            return {}

    def _unauthorized(self):
        return request.make_response(
            json.dumps({"error": "unauthorized"}),
            headers=[("Content-Type", "application/json")],
            status=401,
        )

    def _ok(self):
        return request.make_response(
            json.dumps({"status": "ok"}),
            headers=[("Content-Type", "application/json")],
        )

    def _agent_context(self, test_call):
        agent = test_call.agent_id
        parts = [agent.name or ""]
        if agent.pipeline:
            parts.append("pipeline=%s" % agent.pipeline)
        if agent.agent_type:
            parts.append("type=%s" % agent.agent_type)
        if test_call.scenario_hint:
            parts.append("scénario=%s" % test_call.scenario_hint)
        return " | ".join(p for p in parts if p)

    def _apply_analysis(self, test_call, transcript, duration, analysis, recording_url=""):
        forces = analysis.get("forces") or []
        faiblesses = analysis.get("faiblesses") or []
        recommandations = analysis.get("recommandations") or []
        if isinstance(forces, str):
            forces = [forces]
        if isinstance(faiblesses, str):
            faiblesses = [faiblesses]
        if isinstance(recommandations, str):
            recommandations = [recommandations]
        total = sum(
            float(analysis.get(k) or 0)
            for k in (
                "score_fluidite",
                "score_pertinence",
                "score_conversion",
                "score_tone",
            )
        )
        test_call.sudo().write(
            {
                "state": "done",
                "transcript": transcript,
                "duration_seconds": duration,
                "recording_url": recording_url,
                "score_fluidite": analysis.get("score_fluidite", 0),
                "score_pertinence": analysis.get("score_pertinence", 0),
                "score_conversion": analysis.get("score_conversion", 0),
                "score_tone": analysis.get("score_tone", 0),
                "forces": "\n".join(forces),
                "faiblesses": "\n".join(faiblesses),
                "recommandations": "\n".join(recommandations),
                "analyse_ia": (
                    "Score global %s/100 — Fluidité %s, Pertinence %s, "
                    "Conversion %s, Ton %s."
                )
                % (
                    total,
                    analysis.get("score_fluidite", 0),
                    analysis.get("score_pertinence", 0),
                    analysis.get("score_conversion", 0),
                    analysis.get("score_tone", 0),
                ),
            }
        )
        test_call.agent_id.sudo().write(
            {
                "last_test_date": fields.Datetime.now(),
                "last_test_score": test_call.score_global,
                "total_test_calls": test_call.agent_id.total_test_calls + 1,
            }
        )
        try:
            from odoo.addons.doorway_agents_dashboard.services.google_sheets_service import (
                GoogleSheetsService,
            )

            GoogleSheetsService(request.env).export_test_call(
                test_call, recording_url=recording_url
            )
        except Exception as exc:  # noqa: BLE001
            _logger.warning("Google Sheet export webhook: %s", exc)

    def _handle_elevenlabs(self, data):
        call_id = (
            data.get("call_id")
            or data.get("conversation_id")
            or data.get("id")
        )
        transcript = data.get("transcript", "")
        if isinstance(transcript, list):
            transcript = "\n".join(str(t) for t in transcript)
        duration = int(data.get("duration") or data.get("duration_seconds") or 0)
        recording_url = (
            data.get("recording_url")
            or data.get("audio_url")
            or data.get("RecordingUrl")
            or ""
        )
        test_call = (
            request.env["doorway.agent.test.call"]
            .sudo()
            .search([("external_call_id", "=", call_id)], limit=1)
        )
        if not test_call:
            return
        if not transcript and call_id:
            try:
                from odoo.addons.doorway_agents_dashboard.services.elevenlabs_client import (
                    ElevenLabsClient,
                )

                client = ElevenLabsClient(request.env)
                call_data = client.get_call_transcript(call_id)
                transcript = ElevenLabsClient.extract_transcript(call_data)
                duration = duration or int(call_data.get("duration_seconds") or 0)
                if not recording_url:
                    recording_url = ElevenLabsClient.extract_recording_url(call_data)
            except Exception as exc:  # noqa: BLE001
                _logger.warning("ElevenLabs transcript fallback: %s", exc)
        from odoo.addons.doorway_agents_dashboard.services.call_analyzer import (
            _api_key,
            analyze_call,
        )

        analysis = analyze_call(
            transcript,
            self._agent_context(test_call),
            api_key=_api_key(request.env),
        )
        self._apply_analysis(
            test_call, transcript, duration, analysis, recording_url=recording_url
        )

    def _handle_n8n(self, data):
        call_id = data.get("call_id") or data.get("id")
        transcript_obj = data.get("transcript", [])
        if isinstance(transcript_obj, str):
            transcript = transcript_obj
        else:
            transcript = "\n".join(
                "%s: %s" % (t.get("role", ""), t.get("content", ""))
                for t in (transcript_obj or [])
            )
        duration = int((data.get("duration_ms") or 0) / 1000)
        test_call = (
            request.env["doorway.agent.test.call"]
            .sudo()
            .search([("external_call_id", "=", call_id)], limit=1)
        )
        if not test_call:
            return
        if not transcript and call_id:
            try:
                from odoo.addons.doorway_agents_dashboard.services.n8n_client import (
                    N8NClient,
                )

                call_data = N8NClient(request.env).fetch_call(call_id)
                transcript = N8NClient.extract_transcript(call_data)
                duration = duration or int(call_data.get("duration_seconds") or 0)
            except Exception as exc:  # noqa: BLE001
                _logger.warning("n8n transcript fallback: %s", exc)
        from odoo.addons.doorway_agents_dashboard.services.call_analyzer import (
            _api_key,
            analyze_call,
        )

        analysis = analyze_call(
            transcript,
            self._agent_context(test_call),
            api_key=_api_key(request.env),
        )
        recording_url = data.get("recording_url") or data.get("audio_url") or ""
        self._apply_analysis(
            test_call, transcript, duration, analysis, recording_url=recording_url
        )

    @http.route(
        "/api/agents/webhook/elevenlabs",
        auth="public",
        methods=["POST"],
        csrf=False,
    )
    def webhook_elevenlabs(self, **kwargs):
        """Reçoit fin d'appel ElevenLabs + transcription."""
        if not self._check_key():
            return self._unauthorized()
        data = self._json_body() or dict(kwargs)
        try:
            self._handle_elevenlabs(data)
        except Exception as exc:  # noqa: BLE001
            _logger.exception("Webhook ElevenLabs")
            return request.make_response(
                json.dumps({"error": str(exc)}),
                headers=[("Content-Type", "application/json")],
                status=500,
            )
        return self._ok()

    @http.route(
        "/api/agents/webhook/n8n",
        auth="public",
        methods=["POST"],
        csrf=False,
    )
    def webhook_n8n(self, **kwargs):
        """Reçoit fin d'appel n8n + analyse."""
        if not self._check_key():
            return self._unauthorized()
        data = self._json_body() or dict(kwargs)
        try:
            self._handle_n8n(data)
        except Exception as exc:  # noqa: BLE001
            _logger.exception("Webhook n8n")
            return request.make_response(
                json.dumps({"error": str(exc)}),
                headers=[("Content-Type", "application/json")],
                status=500,
            )
        return self._ok()

    # Rétrocompatibilité anciennes URLs
    @http.route(
        "/doorway/agents/webhook/elevenlabs",
        auth="public",
        methods=["POST"],
        csrf=False,
    )
    def webhook_elevenlabs_legacy(self, **kwargs):
        return self.webhook_elevenlabs(**kwargs)

    @http.route(
        "/doorway/agents/webhook/n8n",
        auth="public",
        methods=["POST"],
        csrf=False,
    )
    def webhook_n8n_legacy(self, **kwargs):
        return self.webhook_n8n(**kwargs)

    # Rétrocompatibilité ancienne URL Retell -> n8n
    @http.route(
        "/api/agents/webhook/retell",
        auth="public",
        methods=["POST"],
        csrf=False,
    )
    def webhook_retell_compat(self, **kwargs):
        return self.webhook_n8n(**kwargs)

    @http.route(
        "/doorway/agents/webhook/retell",
        auth="public",
        methods=["POST"],
        csrf=False,
    )
    def webhook_retell_legacy_compat(self, **kwargs):
        return self.webhook_n8n(**kwargs)
