# -*- coding: utf-8 -*-
"""Service Claude (Anthropic) — génération d'EMAILS en JSON strict.

À partir d'un brief (objectif / persona / ton / offre / CTA / marque) et, en
itération, des emails précédents + une instruction, Claude renvoie un email
unique ou une courte séquence : objet(s) (1-2 variantes A/B), pré-en-tête,
corps HTML responsive inliné, version texte de secours, et bouton(s) CTA.

Conçu pour ÉCHOUER PROPREMENT : clé absente, réseau, HTTP, JSON invalide →
renvoie ``(None, message_utilisateur)`` sans jamais lever.
"""
import json
import logging
import re
from html import unescape

import requests

from . import config_loader

_logger = logging.getLogger(__name__)

ANTHROPIC_URL = "https://api.anthropic.com/v1/messages"
ANTHROPIC_VERSION = "2023-06-01"

MAX_EMAILS = 5
MAX_SUBJECTS = 2
MAX_TOKENS = 8000

SYSTEM_PROMPT = (
    "Tu es une directrice de création et copywriter email senior, experte en "
    "marketing par email et en délivrabilité. Tu rédiges des emails clairs, "
    "modernes et orientés conversion, avec un HTML responsive compatible avec "
    "les clients de messagerie (styles INLINE, tableaux, largeur max 600px, "
    "pas de <script>, pas de CSS externe). Tu réponds UNIQUEMENT avec un objet "
    "JSON valide, sans aucun texte autour, sans préambule, sans backticks."
)


def is_available(env):
    return config_loader.is_available(env)


def _strip_html(html):
    if not html:
        return ""
    text = re.sub(r"<(script|style)[^>]*>.*?</\1>", " ", html or "", flags=re.S | re.I)
    text = re.sub(r"<br\s*/?>", "\n", text, flags=re.I)
    text = re.sub(r"</p>", "\n\n", text, flags=re.I)
    text = re.sub(r"<[^>]+>", " ", text)
    text = unescape(text)
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n\s*\n\s*\n+", "\n\n", text)
    return text.strip()


def _build_user_prompt(brief, previous_emails=None, instruction=None):
    """Construit le message utilisateur (brief + éventuelle itération)."""
    email_schema = {
        "name": "Nom interne court (ex: 'Email 1 — Bienvenue')",
        "subjects": [
            "Objet variante A (< 60 caractères)",
            "Objet variante B (optionnel, pour A/B)",
        ],
        "preheader": "Pré-en-tête / aperçu (< 110 caractères)",
        "html_body": (
            "Corps HTML responsive complet et autonome, styles INLINE, "
            "largeur max 600px, prêt à envoyer (sans <script>)"
        ),
        "text_body": "Version texte brut équivalente (fallback)",
        "cta": [{"label": "Libellé du bouton", "url": "https://… ou #"}],
        "sequence_step": "entier (1 pour le 1er email de la séquence)",
        "send_delay_days": "entier — délai en jours après l'email précédent (0 pour le 1er)",
    }
    schema = {
        "campaign_name": "Nom de la campagne / séquence",
        "tone": "ton appliqué (ex: premium, chaleureux, direct)",
        "assistant_message": (
            "court message récapitulatif adressé au client (1-3 phrases, style conseiller)"
        ),
        "emails": [email_schema],
    }

    parts = [
        "Rédige un EMAIL prêt à l'emploi (ou une courte SÉQUENCE d'emails) à "
        "partir de ce brief client.",
        "",
        "BRIEF CLIENT :",
        json.dumps(brief, ensure_ascii=False, indent=2),
        "",
    ]

    if previous_emails:
        parts += [
            "EMAIL(S) ACTUEL(S) (à faire ÉVOLUER, pas à repartir de zéro) :",
            json.dumps(previous_emails, ensure_ascii=False),
            "",
            "INSTRUCTION D'ITÉRATION DU CLIENT :",
            (instruction or "").strip() or "(améliore la cohérence et l'impact)",
            "",
            "Conserve le même nombre d'emails sauf si l'instruction demande "
            "explicitement d'en ajouter ou d'en retirer. Réutilise le champ "
            "'name' / 'sequence_step' des emails existants quand tu les modifies "
            "pour éviter les doublons.",
            "",
        ]

    seq_len = brief.get("sequence_length")
    try:
        seq_len = int(seq_len)
    except (TypeError, ValueError):
        seq_len = 1
    seq_len = max(1, min(seq_len, MAX_EMAILS))

    parts += [
        "CONTRAINTES :",
        f"- Produis exactement {seq_len} email(s) dans 'emails' "
        f"(jamais plus de {MAX_EMAILS}).",
        f"- Pour chaque email, propose 1 à {MAX_SUBJECTS} objets dans 'subjects' "
        "(2 si A/B pertinent).",
        "- 'html_body' : HTML AUTONOME et responsive, styles INLINE uniquement, "
        "structure en tableaux, largeur max 600px, centré, bouton CTA bien "
        "visible. AUCUN <script>, AUCUNE balise <html>/<head>/<body> superflue "
        "n'est requise (le contenu sera inséré dans un email). Pas d'images "
        "externes obligatoires.",
        "- 'text_body' : équivalent texte brut lisible, avec l'URL du CTA.",
        "- Rédige TOUTE la copy dans la langue du brief (français par défaut), "
        "prête à publier, sans texte de remplacement type 'Lorem ipsum'.",
        "- Respecte le ton, l'offre/proposition de valeur et le CTA du brief.",
        "- Utilise des placeholders Odoo seulement si le brief le suggère "
        "(ex: le prénom). Sinon, rédige un texte générique mais personnel.",
        "",
        "Réponds STRICTEMENT avec un objet JSON respectant ce schéma "
        "(les clés d'email optionnelles peuvent être omises) :",
        json.dumps(schema, ensure_ascii=False),
    ]
    return "\n".join(parts)


def _parse_json(raw):
    """Strip fences ```json puis json.loads sur le premier objet {...}."""
    if not raw:
        return None
    text = raw.strip()
    if text.startswith("```"):
        text = text.strip("`")
        if text.lower().startswith("json"):
            text = text[4:]
    start = text.find("{")
    end = text.rfind("}") + 1
    if start < 0 or end <= start:
        return None
    try:
        return json.loads(text[start:end])
    except json.JSONDecodeError:
        _logger.warning("Email builder : JSON Claude invalide")
        return None


def _coerce_int(value, default=0):
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _clean_subjects(raw):
    subjects = []
    if isinstance(raw, str):
        raw = [raw]
    if isinstance(raw, list):
        for item in raw:
            text = (str(item) if item is not None else "").strip()
            if text:
                subjects.append(text[:200])
            if len(subjects) >= MAX_SUBJECTS:
                break
    return subjects


def _clean_cta(raw):
    out = []
    if isinstance(raw, dict):
        raw = [raw]
    if isinstance(raw, list):
        for item in raw:
            if not isinstance(item, dict):
                continue
            label = (item.get("label") or item.get("text") or "").strip()
            url = (item.get("url") or item.get("href") or "#").strip()
            if label:
                out.append({"label": label[:120], "url": url or "#"})
    return out


def _clean_email(raw, index):
    if not isinstance(raw, dict):
        return None
    subjects = _clean_subjects(raw.get("subjects") or raw.get("subject"))
    if not subjects:
        subjects = ["(objet à définir)"]
    html_body = (raw.get("html_body") or raw.get("body_html") or "").strip()
    text_body = (raw.get("text_body") or raw.get("body_text") or "").strip()
    if not html_body and text_body:
        html_body = "<p>%s</p>" % text_body.replace("\n", "<br/>")
    if not html_body:
        return None
    if not text_body:
        text_body = _strip_html(html_body)
    name = (raw.get("name") or "").strip() or "Email %d" % (index + 1)
    return {
        "name": name[:200],
        "subjects": subjects,
        "preheader": (raw.get("preheader") or raw.get("preview") or "").strip()[:200],
        "html_body": html_body,
        "text_body": text_body,
        "cta": _clean_cta(raw.get("cta") or raw.get("ctas") or raw.get("buttons")),
        "sequence_step": _coerce_int(raw.get("sequence_step"), default=index + 1),
        "send_delay_days": _coerce_int(raw.get("send_delay_days"), default=0),
    }


def validate_payload(payload):
    """Valide/normalise la réponse Claude. Renvoie (payload_clean | None, message)."""
    if not isinstance(payload, dict):
        return None, "La réponse renvoyée n'est pas un objet JSON exploitable."
    raw_emails = payload.get("emails")
    if isinstance(raw_emails, dict):
        raw_emails = [raw_emails]
    # Tolère un email unique renvoyé à la racine.
    if not isinstance(raw_emails, list) or not raw_emails:
        if payload.get("html_body") or payload.get("subjects") or payload.get("subject"):
            raw_emails = [payload]
        else:
            return None, "La réponse ne contient aucun email exploitable."

    emails = []
    for idx, raw in enumerate(raw_emails[:MAX_EMAILS]):
        cleaned = _clean_email(raw, idx)
        if cleaned:
            emails.append(cleaned)
    if not emails:
        return None, "Aucun email valide après validation de la réponse."

    clean = {
        "campaign_name": (payload.get("campaign_name") or "Campagne email").strip()[:200],
        "tone": (payload.get("tone") or "").strip(),
        "assistant_message": (payload.get("assistant_message") or "").strip(),
        "emails": emails,
    }
    return clean, "Email(s) généré(s)."


def generate_emails(env, brief, previous_emails=None, instruction=None):
    """Appelle Claude et renvoie (payload_clean | None, message).

    :param brief: dict du brief client (objectif, persona, ton, offre, cta…).
    :param previous_emails: liste d'emails précédents (dict) pour une itération.
    :param instruction: consigne d'itération en langage naturel.
    """
    api_key = config_loader.get_api_key(env)
    if not api_key:
        return None, (
            "Clé API Claude (Anthropic) non configurée. Renseignez "
            "ANTHROPIC_API_KEY dans /etc/odoo-server.conf ou le paramètre "
            "« doorway_email_builder.anthropic_api_key »."
        )

    payload = {
        "model": config_loader.get_model(env),
        "max_tokens": MAX_TOKENS,
        "system": SYSTEM_PROMPT,
        "messages": [
            {
                "role": "user",
                "content": _build_user_prompt(brief, previous_emails, instruction),
            }
        ],
    }
    headers = {
        "x-api-key": api_key,
        "anthropic-version": ANTHROPIC_VERSION,
        "content-type": "application/json",
    }
    try:
        resp = requests.post(
            ANTHROPIC_URL, headers=headers, data=json.dumps(payload), timeout=120
        )
    except Exception as exc:  # noqa: BLE001
        _logger.warning("Email builder — réseau Claude : %s", exc)
        return None, "Service Claude injoignable. Réessayez plus tard."

    if resp.status_code != 200:
        _logger.warning(
            "Email builder — Claude HTTP %s : %s", resp.status_code, resp.text[:300]
        )
        return None, (
            "Claude a renvoyé une erreur (HTTP %s). Vérifiez la clé API ou le "
            "modèle configuré." % resp.status_code
        )

    try:
        parts = resp.json().get("content") or []
        raw = "".join(p.get("text", "") for p in parts if p.get("type") == "text")
    except Exception:  # noqa: BLE001
        return None, "Réponse Claude illisible."

    parsed = _parse_json(raw)
    if parsed is None:
        return None, "Claude n'a pas renvoyé d'email JSON exploitable."
    return validate_payload(parsed)
