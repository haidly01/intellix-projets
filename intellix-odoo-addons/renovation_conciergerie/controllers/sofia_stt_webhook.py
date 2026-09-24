# -*- coding: utf-8 -*-
import base64
import json
import logging
import os
import re
import time

import requests

from odoo import http
from odoo.http import request

_logger = logging.getLogger(__name__)
CONF_PATH = "/etc/odoo-server.conf"


def _read_conf(key: str) -> str:
    value = (os.environ.get(key) or "").strip()
    if value:
        return value
    try:
        with open(CONF_PATH, encoding="utf-8") as handle:
            for line in handle:
                line = line.strip()
                if not line or line[0] in "#;":
                    continue
                if "=" not in line:
                    continue
                k, v = line.split("=", 1)
                if k.strip() == key:
                    return v.strip()
    except OSError:
        pass
    return ""


class SofiaSttWebhookController(http.Controller):
    def _check_key(self):
        expected = (
            _read_conf("SOFIA_STT_WEBHOOK_KEY")
            or _read_conf("renovation_conciergerie.sofia_stt_key")
            or "doorway-sofia-stt"
        )
        provided = (
            request.httprequest.headers.get("X-Renov-Stt-Key")
            or request.httprequest.headers.get("X-Api-Key")
            or ""
        )
        return provided == expected

    def _audio_bytes(self, data):
        b64 = (data.get("recording_b64") or "").strip()
        if b64:
            try:
                decoded = base64.b64decode(b64, validate=True)
                if decoded:
                    return decoded
            except Exception:
                _logger.warning("Sofia STT: invalid recording_b64, fallback URL")

        url = (data.get("recording_url") or "").strip()
        if not url:
            return b""
        if url.startswith("file://"):
            local_path = url[7:]
            if local_path.endswith(".mp3"):
                local_path = local_path[:-4] + ".wav"
            if not os.path.isfile(local_path) and os.path.isfile(local_path + ".wav"):
                local_path = local_path + ".wav"
            if os.path.isfile(local_path):
                with open(local_path, "rb") as handle:
                    return handle.read()
            return b""

        if not url.endswith(".mp3"):
            url = url + ".mp3"

        tw_sid = _read_conf("TWILIO_ACCOUNT_SID")
        tw_token = _read_conf("TWILIO_AUTH_TOKEN")
        auth = (tw_sid, tw_token) if "api.twilio.com" in url and tw_sid and tw_token else None
        resp = requests.get(url, auth=auth, timeout=30)
        resp.raise_for_status()
        return resp.content

    @http.route(
        "/api/renov/stt/deepgram",
        type="http",
        auth="none",
        methods=["POST"],
        csrf=False,
    )
    def deepgram_transcribe(self):
        if not self._check_key():
            return request.make_response(
                json.dumps({"error": "unauthorized"}),
                status=401,
                headers=[("Content-Type", "application/json")],
            )

        try:
            raw = request.httprequest.data or b"{}"
            data = json.loads(raw.decode("utf-8") if raw else "{}")
        except json.JSONDecodeError:
            data = {}

        language = (data.get("language") or "es").strip() or "es"
        dg_key = _read_conf("DEEPGRAM_API_KEY")
        if not dg_key:
            return request.make_response(
                json.dumps({"error": "DEEPGRAM_API_KEY missing"}),
                status=500,
                headers=[("Content-Type", "application/json")],
            )

        rec_hint = (
            (data.get("recording_url") or "")
            + (data.get("recording_path") or "")
        ).lower()

        try:
            audio = self._audio_bytes(data)
        except Exception as exc:
            _logger.warning("Sofia STT: audio download failed: %s", exc)
            return request.make_response(
                json.dumps({"error": f"audio_download_failed: {exc}"}),
                status=400,
                headers=[("Content-Type", "application/json")],
            )

        if not audio:
            return request.make_response(
                json.dumps({"transcript": "", "confidence": 0}),
                headers=[("Content-Type", "application/json")],
            )

        content_type = "audio/wav" if (
            rec_hint.endswith(".wav") or (audio[:4] == b"RIFF")
        ) else "audio/mpeg"
        # nova-3 > nova-2 pour le français QC : confiance plus haute sur réponses
        # courtes ("Oui" 0.93->0.995, "Peut-être les 2" 0.97->0.995) et toujours
        # vide (pas d'hallucination) sur le silence. Les variantes -phonecall ne
        # supportent PAS le français (Bad Request), donc on reste sur le tier général.
        dg_url = (
            "https://api.deepgram.com/v1/listen"
            f"?language={language}&model=nova-3&smart_format=true&punctuate=false"
        )
        try:
            _t0 = time.monotonic()
            dg_resp = requests.post(
                dg_url,
                headers={
                    "Authorization": f"Token {dg_key}",
                    "Content-Type": content_type,
                },
                data=audio,
                timeout=45,
            )
            dg_resp.raise_for_status()
            payload = dg_resp.json()
            _stt_ms = round((time.monotonic() - _t0) * 1000.0, 1)
        except Exception as exc:
            _logger.warning("Sofia STT: Deepgram failed: %s", exc)
            return request.make_response(
                json.dumps({"error": f"deepgram_failed: {exc}"}),
                status=502,
                headers=[("Content-Type", "application/json")],
            )

        results = payload.get("results") or {}
        channels = results.get("channels") or [{}]
        alternatives = (channels[0] or {}).get("alternatives") or [{}]
        alt = alternatives[0] or {}
        audio_sec = (
            payload.get("metadata", {}).get("duration")
            or payload.get("results", {}).get("metadata", {}).get("duration")
            or 0.0
        )
        result = {
            "transcript": (alt.get("transcript") or "").strip(),
            "confidence": alt.get("confidence") or 0,
            "stt_ms": _stt_ms,
            "audio_sec": audio_sec,
        }

        # ── Instrumentation Léa-QC (non bloquant) ──
        # On capte la latence STT réelle + les secondes audio Deepgram par tour.
        # Attribution par call_sid (explicite ou extrait du nom de fichier
        # d'enregistrement « <call_sid>_<turn>.wav »). Limité au français (Léa /
        # campagnes QC) pour ne pas polluer avec Sofia ES.
        try:
            if str(language).lower().startswith("fr"):
                self._log_lea_stt_turn(data, result, audio_sec, _stt_ms)
        except Exception as exc:  # pragma: no cover - jamais bloquant
            _logger.warning("Léa STT instrumentation échec: %s", exc)

        return request.make_response(
            json.dumps(result),
            headers=[("Content-Type", "application/json")],
        )

    @staticmethod
    def _parse_sid_turn(data):
        call_sid = (data.get("call_sid") or data.get("uniqueid") or "").strip()
        turn = data.get("turn")
        hint = (data.get("recording_url") or "") + (data.get("recording_path") or "")
        if (not call_sid or turn is None) and hint:
            m = re.search(r"([0-9]{6,}\.[0-9]+|[A-Za-z0-9]{6,})_([0-9]+)\.wav", hint)
            if m:
                call_sid = call_sid or m.group(1)
                turn = m.group(2) if turn is None else turn
        return call_sid, (turn if turn is not None else 0)

    def _log_lea_stt_turn(self, data, result, audio_sec, stt_ms):
        if "lea.qc.turn" not in request.env:
            return
        call_sid, turn = self._parse_sid_turn(data)
        if not call_sid:
            return
        request.env["lea.qc.turn"].sudo().log_stage(
            call_sid,
            turn,
            "stt",
            {
                "stt_model": "nova-3",
                "stt_audio_sec": float(audio_sec or 0.0),
                "stt_ms": float(stt_ms or 0.0),
                "stt_confidence": float(result.get("confidence") or 0.0),
                "prospect_transcript": (result.get("transcript") or "")[:2000],
            },
        )
