# -*- coding: utf-8 -*-
"""
Léa-QC — Endpoints instrumentés TTS (ElevenLabs) & LLM (Claude).

But : mesurer en conditions RÉELLES, avec cache DÉSACTIVÉ (baseline), les unités
et latences exactes de chaque réponse vocale de Léa :
  - TTS : caractères synthétisés, modèle, time-to-first-byte, total, + cacheabilité
          (ligne scriptée ? déjà vue ? → projection d'économies par cache).
  - LLM : tokens entrée/sortie, time-to-first-token, total (si Claude par tour).

Ces endpoints sont des SEAMS prêts à l'emploi. Pour capter le TTS live aujourd'hui,
la boucle (env n8n STORAGE_BUCKET_URL ou audio_url renvoyé) doit pointer vers :
    GET  https://intellixcrm.com/lea-tts/<cle>.mp3   (clip scripté, synthèse live)
    POST https://intellixcrm.com/api/renov/tts/elevenlabs  (texte libre)
Le STT et le télécom sont, eux, déjà mesurés via l'endpoint STT existant.

⚠️  CACHE TTS = DÉSACTIVÉ (TTS_CACHE_ENABLED=False) pour le baseline. Le code de
    cache est laissé en place, isolé et commenté, pour être activé APRÈS la mesure.
"""
import json
import logging
import os
import time

import requests

from odoo import http
from odoo.http import request

_logger = logging.getLogger(__name__)
CONF_PATH = "/etc/odoo-server.conf"

# ───────────────────────────────────────────────────────────────────────────
# SEAM CACHE TTS — INACTIF pendant le baseline. NE PAS activer avant d'avoir
# mesuré le coût/latence TTS réels + le % cacheable. Pour activer ensuite :
#   1. TTS_CACHE_ENABLED = True
#   2. servir le fichier depuis TTS_CACHE_DIR si présent (voir _cache_lookup).
# Tant que c'est False, CHAQUE requête TTS déclenche une synthèse ElevenLabs
# fraîche (= vraie mesure du coût/latence de référence).
TTS_CACHE_ENABLED = False
TTS_CACHE_DIR = "/var/cache/lea-tts"
# ───────────────────────────────────────────────────────────────────────────


def _read_conf(key, default=""):
    val = (os.environ.get(key) or "").strip()
    if val:
        return val
    try:
        with open(CONF_PATH, encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line or line[0] in "#;" or "=" not in line:
                    continue
                k, v = line.split("=", 1)
                if k.strip() == key:
                    return v.strip()
    except OSError:
        pass
    return default


def _check_key():
    expected = _read_conf("SOFIA_STT_WEBHOOK_KEY", "doorway-sofia-stt")
    provided = (
        request.httprequest.headers.get("X-Renov-Stt-Key")
        or request.httprequest.headers.get("X-Api-Key")
        or request.params.get("key")
        or ""
    )
    return provided == expected


def _json_resp(payload, status=200):
    return request.make_response(
        json.dumps(payload),
        status=status,
        headers=[("Content-Type", "application/json")],
    )


def _cache_lookup(_key):
    """SEAM cache (inactif). Retourne un chemin fichier si le cache est activé."""
    if not TTS_CACHE_ENABLED:
        return None
    # path = os.path.join(TTS_CACHE_DIR, "%s.mp3" % _key)
    # return path if os.path.isfile(path) else None
    return None


class LeaQcInstrumentedController(http.Controller):

    # ── TTS scripté (clip fixe) : GET transparent pour la boucle existante ──
    @http.route(
        "/lea-tts/<string:clip>",
        type="http",
        auth="none",
        methods=["GET"],
        csrf=False,
    )
    def tts_scripted_clip(self, clip, **kw):
        """Sert un clip Léa par sa clé (ex: lea_ouverture.mp3) en synthèse LIVE.

        Permet de capter le TTS réel sans toucher l'AGI : il suffit que la boucle
        pointe STORAGE_BUCKET_URL vers https://intellixcrm.com/lea-tts.
        """
        key = (clip or "").rsplit(".", 1)[0]
        call_sid = kw.get("call_sid") or kw.get("uniqueid") or ""
        turn = kw.get("turn") or 0
        line = (
            request.env["lea.qc.scripted.line"]
            .sudo()
            .search([("key", "=", key)], limit=1)
        )
        if not line:
            return _json_resp({"error": "unknown_clip", "clip": key}, status=404)
        audio, metrics = self._synthesize(
            line.text, voice_id=line.voice_id, scripted_key=key
        )
        self._log_tts_turn(call_sid, turn, line.text, metrics, scripted=True)
        if audio is None:
            return _json_resp({"error": metrics.get("error", "tts_failed")}, status=502)
        return request.make_response(
            audio, headers=[("Content-Type", "audio/mpeg"), ("Cache-Control", "no-store")]
        )

    # ── TTS texte libre (dynamique) : POST instrumenté ──
    @http.route(
        "/api/renov/tts/elevenlabs",
        type="http",
        auth="none",
        methods=["POST"],
        csrf=False,
    )
    def tts_elevenlabs(self, **kw):
        if not _check_key():
            return _json_resp({"error": "unauthorized"}, status=401)
        try:
            data = json.loads((request.httprequest.data or b"{}").decode("utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError):
            data = {}
        text = (data.get("text") or "").strip()
        if not text:
            return _json_resp({"error": "text_required"}, status=400)
        call_sid = data.get("call_sid") or ""
        turn = data.get("turn") or 0
        scripted_key = data.get("scripted_key") or ""
        audio, metrics = self._synthesize(
            text,
            voice_id=data.get("voice_id"),
            model_id=data.get("model_id"),
            scripted_key=scripted_key,
        )
        self._log_tts_turn(
            call_sid, turn, text, metrics, scripted=bool(scripted_key)
        )
        if audio is None:
            return _json_resp({"error": metrics.get("error", "tts_failed")}, status=502)
        return request.make_response(
            audio, headers=[("Content-Type", "audio/mpeg"), ("Cache-Control", "no-store")]
        )

    def _synthesize(self, text, voice_id=None, model_id=None, scripted_key=""):
        """Synthèse ElevenLabs en streaming pour mesurer TTFB + total. Cache OFF."""
        metrics = {"chars": len(text), "model": "", "ttfb_ms": 0.0, "total_ms": 0.0}
        api_key = _read_conf("ELEVENLABS_API_KEY")
        voice = voice_id or _read_conf("ELEVENLABS_VOICE_ID")
        model = model_id or "eleven_multilingual_v2"
        metrics["model"] = model
        if not api_key or not voice:
            metrics["error"] = "elevenlabs_key_or_voice_missing"
            return None, metrics

        # SEAM cache (inactif) — voir en-tête du module.
        cached = _cache_lookup(scripted_key)
        if cached:  # pragma: no cover - cache désactivé pour le baseline
            with open(cached, "rb") as fh:
                metrics["cache_served"] = True
                return fh.read(), metrics

        url = "https://api.elevenlabs.io/v1/text-to-speech/%s/stream" % voice
        body = {
            "text": text,
            "model_id": model,
            "voice_settings": {
                "stability": 0.55,
                "similarity_boost": 0.82,
                "style": 0.35,
            },
        }
        t0 = time.monotonic()
        try:
            resp = requests.post(
                url,
                headers={
                    "xi-api-key": api_key,
                    "Content-Type": "application/json",
                    "Accept": "audio/mpeg",
                },
                json=body,
                stream=True,
                timeout=45,
            )
            resp.raise_for_status()
            chunks = []
            ttfb = None
            for chunk in resp.iter_content(chunk_size=4096):
                if not chunk:
                    continue
                if ttfb is None:
                    ttfb = (time.monotonic() - t0) * 1000.0
                chunks.append(chunk)
            metrics["ttfb_ms"] = round(ttfb or (time.monotonic() - t0) * 1000.0, 1)
            metrics["total_ms"] = round((time.monotonic() - t0) * 1000.0, 1)
            return b"".join(chunks), metrics
        except requests.RequestException as exc:
            metrics["error"] = "elevenlabs_failed: %s" % str(exc)[:160]
            _logger.warning("Léa TTS échec: %s", exc)
            return None, metrics

    def _log_tts_turn(self, call_sid, turn, text, metrics, scripted=False):
        try:
            Line = request.env["lea.qc.scripted.line"].sudo()
            h = Line.hash_for(text)
            is_scripted = scripted or Line.is_scripted_hash(h)
            Turn = request.env["lea.qc.turn"].sudo()
            seen_before = bool(
                Turn.search_count(
                    [("tts_text_hash", "=", h), ("tts_chars", ">", 0)]
                )
            )
            Turn.log_stage(
                call_sid,
                turn,
                "tts",
                {
                    "bot_text": (text or "")[:2000],
                    "tts_model": metrics.get("model"),
                    "tts_chars": metrics.get("chars") or 0,
                    "tts_ttfb_ms": metrics.get("ttfb_ms") or 0.0,
                    "tts_total_ms": metrics.get("total_ms") or 0.0,
                    "tts_is_scripted": is_scripted,
                    "tts_cache_hit": seen_before,
                    "tts_text_hash": h,
                },
            )
        except Exception as exc:  # ne jamais casser la synthèse
            _logger.warning("Léa TTS log échec: %s", exc)

    # ── LLM Claude instrumenté (seam — non appelé par la boucle actuelle) ──
    @http.route(
        "/api/renov/llm/claude",
        type="http",
        auth="none",
        methods=["POST"],
        csrf=False,
    )
    def llm_claude(self, **kw):
        if not _check_key():
            return _json_resp({"error": "unauthorized"}, status=401)
        try:
            data = json.loads((request.httprequest.data or b"{}").decode("utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError):
            data = {}
        messages = data.get("messages") or []
        system = data.get("system") or ""
        if not messages:
            return _json_resp({"error": "messages_required"}, status=400)
        api_key = _read_conf("ANTHROPIC_API_KEY")
        if not api_key:
            return _json_resp({"error": "anthropic_key_missing"}, status=500)
        model = data.get("model") or "claude-sonnet-4-20250514"
        call_sid = data.get("call_sid") or ""
        turn = data.get("turn") or 0

        t0 = time.monotonic()
        ttft = None
        text_out = []
        tokens_in = tokens_out = 0
        try:
            with requests.post(
                "https://api.anthropic.com/v1/messages",
                headers={
                    "x-api-key": api_key,
                    "anthropic-version": "2023-06-01",
                    "Content-Type": "application/json",
                },
                json={
                    "model": model,
                    "max_tokens": int(data.get("max_tokens") or 150),
                    "temperature": float(data.get("temperature") or 0.7),
                    "system": system,
                    "messages": messages,
                    "stream": True,
                },
                stream=True,
                timeout=45,
            ) as resp:
                resp.raise_for_status()
                for raw in resp.iter_lines():
                    if not raw:
                        continue
                    line = raw.decode("utf-8", "ignore")
                    if not line.startswith("data:"):
                        continue
                    try:
                        evt = json.loads(line[5:].strip())
                    except json.JSONDecodeError:
                        continue
                    etype = evt.get("type")
                    if etype == "message_start":
                        usage = evt.get("message", {}).get("usage", {})
                        tokens_in = usage.get("input_tokens", 0)
                    elif etype == "content_block_delta":
                        if ttft is None:
                            ttft = (time.monotonic() - t0) * 1000.0
                        text_out.append(evt.get("delta", {}).get("text", ""))
                    elif etype == "message_delta":
                        tokens_out = evt.get("usage", {}).get("output_tokens", tokens_out)
        except requests.RequestException as exc:
            return _json_resp({"error": "claude_failed: %s" % str(exc)[:160]}, status=502)

        total_ms = round((time.monotonic() - t0) * 1000.0, 1)
        try:
            request.env["lea.qc.turn"].sudo().log_stage(
                call_sid,
                turn,
                "llm",
                {
                    "llm_model": model,
                    "llm_tokens_in": tokens_in,
                    "llm_tokens_out": tokens_out,
                    "llm_ttft_ms": round(ttft or total_ms, 1),
                    "llm_total_ms": total_ms,
                },
            )
        except Exception as exc:
            _logger.warning("Léa LLM log échec: %s", exc)
        return _json_resp(
            {
                "text": "".join(text_out),
                "tokens_in": tokens_in,
                "tokens_out": tokens_out,
                "ttft_ms": round(ttft or total_ms, 1),
                "total_ms": total_ms,
            }
        )
