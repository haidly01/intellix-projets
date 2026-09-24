#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Vérifie la chaîne Twilio → Deepgram → moteur Sofía (renov-aides)."""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import requests

CONF_PATHS = (Path("/etc/odoo-server.conf"), Path("/opt/n8n/.env"))


def read_conf(key: str) -> str:
    for path in CONF_PATHS:
        if not path.is_file():
            continue
        for line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
            line = line.strip()
            if line.startswith(f"{key}=") or line.startswith(f";{key}="):
                return line.split("=", 1)[1].strip()
    return ""


def ok(msg: str) -> None:
    print(f"  OK  {msg}")


def fail(msg: str) -> None:
    print(f"  FAIL {msg}")


def test_env() -> bool:
    print("\n=== 1. Variables environnement ===")
    passed = True
    required = {
        "DEEPGRAM_API_KEY": read_conf("DEEPGRAM_API_KEY"),
        "TWILIO_ACCOUNT_SID": read_conf("TWILIO_ACCOUNT_SID"),
        "TWILIO_AUTH_TOKEN": read_conf("TWILIO_AUTH_TOKEN"),
        "TWILIO_PHONE_NUMBER": read_conf("TWILIO_PHONE_NUMBER") or read_conf("TWILIO_FROM_NUMBER"),
        "ANTHROPIC_API_KEY": read_conf("ANTHROPIC_API_KEY"),
        "N8N_WEBHOOK_URL": read_conf("N8N_WEBHOOK_URL") or "https://n8n.intellixcrm.com/webhook",
    }
    for key, val in required.items():
        if val:
            ok(f"{key} présent")
        else:
            fail(f"{key} manquant")
            passed = False
    bypass = (read_conf("SOFIA_STT_BYPASS") or "false").lower()
    if bypass in ("false", "0", "no"):
        ok("SOFIA_STT_BYPASS=false (Deepgram actif)")
    else:
        fail(f"SOFIA_STT_BYPASS={bypass} — Deepgram désactivé")
        passed = False
    return passed


def test_deepgram_twilio_recording() -> tuple[bool, str]:
    print("\n=== 2. Deepgram + auth Twilio (dernier enregistrement) ===")
    sid = read_conf("TWILIO_ACCOUNT_SID")
    token = read_conf("TWILIO_AUTH_TOKEN")
    dg_key = read_conf("DEEPGRAM_API_KEY")
    calls = requests.get(
        f"https://api.twilio.com/2010-04-01/Accounts/{sid}/Calls.json?PageSize=5",
        auth=(sid, token),
        timeout=30,
    ).json().get("calls", [])
    if not calls:
        fail("aucun appel Twilio récent")
        return False, ""
    call_sid = calls[0]["sid"]
    recs = requests.get(
        f"https://api.twilio.com/2010-04-01/Accounts/{sid}/Calls/{call_sid}/Recordings.json",
        auth=(sid, token),
        timeout=30,
    ).json().get("recordings", [])
    if not recs:
        fail(f"pas d'enregistrement pour {call_sid}")
        return False, ""
    mp3 = "https://api.twilio.com" + recs[0]["uri"].replace(".json", "") + ".mp3"
    audio = requests.get(mp3, auth=(sid, token), timeout=60)
    if audio.status_code != 200:
        fail(f"téléchargement Twilio HTTP {audio.status_code}")
        return False, mp3
    ok(f"MP3 téléchargé ({len(audio.content)} bytes)")

    dg_url = (
        "https://api.deepgram.com/v1/listen"
        "?language=es&model=nova-2&smart_format=true"
    )
    dg = requests.post(
        dg_url,
        headers={"Authorization": f"Token {dg_key}", "Content-Type": "audio/mpeg"},
        data=audio.content,
        timeout=120,
    )
    if not dg.ok:
        fail(f"Deepgram HTTP {dg.status_code}: {dg.text[:200]}")
        return False, mp3
    transcript = (
        dg.json().get("results", {})
        .get("channels", [{}])[0]
        .get("alternatives", [{}])[0]
        .get("transcript", "")
        .strip()
    )
    if not transcript:
        fail("transcription vide")
        return False, mp3
    ok(f"transcription: {transcript[:120]}...")
    if re.search(r"propiet|soy propietario|sí", transcript, re.I):
        ok("détection « propietario » possible")
    else:
        fail("pas de mot propriétaire dans la transcription")
    return True, mp3


def test_odoo_stt_proxy(recording_url: str) -> bool:
    print("\n=== 2b. Proxy Odoo STT ===")
    odoo = read_conf("ODOO_URL") or "https://intellixcrm.com"
    stt_key = read_conf("SOFIA_STT_WEBHOOK_KEY") or "doorway-sofia-stt"
    import base64

    sid = read_conf("TWILIO_ACCOUNT_SID")
    token = read_conf("TWILIO_AUTH_TOKEN")
    mp3 = recording_url if recording_url.endswith(".mp3") else recording_url + ".mp3"
    audio = requests.get(mp3, auth=(sid, token), timeout=60)
    if not audio.ok:
        fail(f"download Twilio HTTP {audio.status_code}")
        return False
    payload = {
        "recording_b64": base64.b64encode(audio.content).decode("ascii"),
        "language": "es",
    }
    resp = requests.post(
        f"{odoo.rstrip('/')}/api/renov/stt/deepgram",
        headers={"Content-Type": "application/json", "X-Renov-Stt-Key": stt_key},
        json=payload,
        timeout=120,
    )
    if not resp.ok:
        fail(f"Odoo STT HTTP {resp.status_code}: {resp.text[:200]}")
        return False
    data = resp.json()
    tr = (data.get("transcript") or "").strip()
    if not tr:
        fail("transcript vide via Odoo")
        return False
    ok(f"Odoo STT: {tr[:100]}...")
    return True


def test_conversation_webhook(recording_url: str) -> bool:
    print("\n=== 3. Webhook n8n /renov/conversation ===")
    base = (read_conf("N8N_WEBHOOK_URL") or "https://n8n.intellixcrm.com/webhook").rstrip("/")
    import base64
    import time

    sid = read_conf("TWILIO_ACCOUNT_SID")
    token = read_conf("TWILIO_AUTH_TOKEN")
    mp3 = recording_url if recording_url.endswith(".mp3") else recording_url + ".mp3"
    audio = requests.get(mp3, auth=(sid, token), timeout=60)
    recording_b64 = base64.b64encode(audio.content).decode("ascii") if audio.ok else ""

    call_sid = f"TEST_PIPELINE_{int(time.time())}"
    ev = {
        "event_type": "recording_ready",
        "call_sid": call_sid,
        "recording_url": recording_url.replace(".mp3", ""),
        "recording_b64": recording_b64,
        "duration_sec": 18,
        "provider": "twilio",
        "to": "+212674579467",
        "from": read_conf("TWILIO_PHONE_NUMBER") or "+14387905970",
    }
    resp = requests.post(f"{base}/renov/conversation", json=ev, timeout=120)
    if not resp.ok:
        fail(f"HTTP {resp.status_code}: {resp.text[:300]}")
        return False
    data = resp.json()
    action = data.get("action")
    session = data.get("session") or {}
    log = session.get("transcript_log") or []
    transcript_field = data.get("transcript") or ""
    ok(f"action={action}, etape={session.get('etape')}")
    if log:
        ok(f"transcript_log: {log[-1][:140]}")
    else:
        fail("transcript_log vide")
    if transcript_field and not transcript_field.startswith("[Deepgram error"):
        ok(f"transcript moteur: {transcript_field[:100]}...")
    elif transcript_field.startswith("[Deepgram error"):
        fail(transcript_field)
        return False
    else:
        fail("transcript moteur vide")
        return False
    if "[Deepgram error" in (transcript_field or "") or "[TEST sans Deepgram" in (transcript_field or ""):
        fail(f"Deepgram non utilisé: {transcript_field[:120]}")
        return False
    if action == "play_audio" and session.get("etape") == "Q2":
        ok("intent propriétaire → passage Q2 (Deepgram OK)")
        return True
    if action == "play_audio" and session.get("etape") in ("Q1_clarif", "ouverture"):
        fail("bloqué en clarif — vérifier audio/intent")
        return False
    if action == "hangup":
        fail(f"raccrochage inattendu — statut {data.get('statut')}")
        return False
    ok("réponse moteur cohérente")
    return True


def test_workflows_active() -> bool:
    print("\n=== 4. Workflows n8n actifs ===")
    token = read_conf("N8N_API_TOKEN")
    base = (read_conf("N8N_BASE_URL") or "https://n8n.intellixcrm.com").rstrip("/")
    if not token:
        fail("N8N_API_TOKEN manquant — skip API")
        return True
    names = [
        "renov-aides — 03 Conversation Engine",
        "renov-aides — Adapter Twilio",
        "renov-aides — 01 Outbound Trigger",
    ]
    r = requests.get(f"{base}/api/v1/workflows?limit=100", headers={"X-N8N-API-KEY": token}, timeout=30)
    if not r.ok:
        fail(f"API n8n HTTP {r.status_code}")
        return False
    by_name = {w["name"]: w for w in r.json().get("data", [])}
    passed = True
    for name in names:
        wf = by_name.get(name)
        if wf and wf.get("active"):
            ok(f"{name}")
        else:
            fail(f"{name} inactif ou absent")
            passed = False
    wf_ce = by_name.get("renov-aides — 03 Conversation Engine")
    if wf_ce:
        code = json.dumps(wf_ce)
        if "/api/renov/stt/deepgram" in code:
            ok("proxy STT Odoo→Deepgram présent dans le workflow")
        else:
            fail("fix auth Twilio→Deepgram ABSENT — relancer sync + import")
            passed = False
    return passed


def main() -> int:
    print("Test pipeline Sofía — Twilio + Deepgram")
    results = [test_env()]
    dg_ok, mp3 = test_deepgram_twilio_recording()
    results.append(dg_ok)
    results.append(test_odoo_stt_proxy(mp3) if mp3 else False)
    results.append(test_conversation_webhook(mp3) if mp3 else False)
    results.append(test_workflows_active())
    print("\n=== Résumé ===")
    if all(results):
        print("TOUS LES TESTS OK")
        return 0
    print(f"{sum(results)}/{len(results)} tests réussis")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
