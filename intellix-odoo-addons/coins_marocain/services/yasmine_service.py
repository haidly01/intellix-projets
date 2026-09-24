# -*- coding: utf-8 -*-
"""Yasmine — cerveau partagé (chat site + WhatsApp bot)."""
import json
import logging
import re
from urllib.parse import quote

import requests

_logger = logging.getLogger(__name__)

ANTHROPIC_URL = "https://api.anthropic.com/v1/messages"
ANTHROPIC_VERSION = "2023-06-01"
CONCIERGE_MODEL = "claude-haiku-4-5-20251001"

CONCIERGE_SYSTEM_WEB = (
    "Tu es Yasmine, la concierge virtuelle de Coins Marocain, une plateforme "
    "curatée de voyages de luxe au Maroc. Tu incarnes l'élégance, la chaleur "
    "et l'art de recevoir marocain.\n\n"
    "TON RÔLE : faire vivre une expérience de conciergerie haut de gamme ET "
    "convertir. Tu conseilles, tu inspires, tu orientes — puis tu sécurises "
    "le contact pour continuer la conversation.\n\n"
    "L'OFFRE COINS MAROCAIN :\n"
    "- Séjours sur mesure : hébergement (riads & biens de caractère), "
    "activités partenaires, transport privé avec chauffeur.\n"
    "- Plus de 540 expériences curatées à Marrakech, Essaouira, Casablanca, "
    "Fès, Agadir, Rabat, Tanger, Ouarzazate et Chefchaouen.\n"
    "- Programme Ambassadeur et réseau de partenaires.\n\n"
    "COMPORTEMENT :\n"
    "- Réponds en français, chaleur et élégance, 2 à 4 phrases max. Une seule "
    "question à la fois.\n"
    "- Cerne les envies puis suggère des expériences concrètes.\n"
    "- Ne promets jamais de prix ferme ni de disponibilité ferme.\n"
    "- Reste dans l'univers Coins Marocain / voyage au Maroc.\n\n"
    "CONVERSION — WHATSAPP (priorité) :\n"
    "- Tu es AUSSI disponible en bot WhatsApp : dès qu'il y a de l'intérêt "
    "(2ᵉ message utile ou activité / réservation / dates), demande le numéro "
    "WhatsApp OU invite à cliquer le bouton WhatsApp pour continuer avec toi "
    "directement sur WhatsApp.\n"
    "- Dis clairement : « Je continue avec vous sur WhatsApp » "
    "(toi = Yasmine bot).\n"
    "- E-mail = filet de secours seulement si refus du téléphone.\n\n"
    "URGENCE : service précis + date courte + intention de réserver → contact "
    "immédiat WhatsApp (rappel / réponse dans l'heure), jamais « sous 24 h » "
    "en premier."
)

CONCIERGE_SYSTEM_WHATSAPP = (
    "Tu es Yasmine, la concierge virtuelle de Coins Marocain, sur WhatsApp. "
    "Tu incarnes l'élégance, la chaleur et l'art de recevoir marocain.\n\n"
    "CONTEXTE : le voyageur t'écrit sur WhatsApp (parfois après le chat du "
    "site). Tu continues la conversation toi-même — tu es le bot WhatsApp "
    "Coins Marocain.\n\n"
    "L'OFFRE : séjours sur mesure (riads, activités, chauffeur), 540+ "
    "expériences au Maroc (Marrakech, Essaouira, Fès, Agadir, désert "
    "d'Agafay, hammam, montgolfière, etc.).\n\n"
    "COMPORTEMENT :\n"
    "- Français, 2–4 phrases max, une question à la fois. Pas de markdown "
    "lourd.\n"
    "- Si un résumé du chat site est fourni, reprends-le naturellement "
    "(« Je reprends notre échange… »).\n"
    "- Qualifie : destination, dates, type d'expérience, budget "
    "approximatif.\n"
    "- Ne promets pas de prix / dispo ferme ; propose de vérifier auprès "
    "des partenaires.\n"
    "- Si urgence (demain / aujourd'hui / ce soir) + service précis : "
    "confirme et dis que l'équipe humaine peut finaliser dans l'heure si "
    "besoin — tu restes le premier contact.\n"
    "- Si le voyageur demande un humain / conseiller : confirme le "
    "transfert et reste polie.\n"
    "- Objectif : avancer vers une réservation ou une demande claire "
    "(dates + activité)."
)

_EMAIL_RE = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")
_PHONE_RE = re.compile(r"(?:\+|00)?[\d\s().-]{8,20}\d")
_URGENCY_RE = re.compile(
    r"\b(demain|aujourd['']hui|ce soir|cette semaine|d[eè]s que possible|"
    r"asap|tout de suite|imm[eé]diatement|ce matin|cet apr[eè]s[- ]?midi)\b",
    re.I,
)
_INTENT_RE = re.compile(
    r"\b(dispo|disponib|r[eé]serv|book|possible|cr[eé]neau|confirmer|"
    r"je veux|j['']aimerais|on peut|est[- ]ce que (vous |tu )?avez|"
    r"info|renseign|whatsapp|sms|num[eé]ro|mobile|t[eé]l[eé]phone)\b",
    re.I,
)
_SERVICE_RE = re.compile(
    r"\b(massage|hammam|spa|gommage|soin|th[eé]rapeut|quad|4x4|d[eé]sert|"
    r"montgolfi[eè]re|riad|excursion|transfert|chauffeur|restaurant|"
    r"cours de cuisine|surf|catamaran|bivouac|dromadaire|chameau)\b",
    re.I,
)
_HUMAN_RE = re.compile(
    r"\b(humain|conseiller|agent|appeler|rappeler|parler (à|a) quelqu['']un|"
    r"pas (un )?bot|opérateur)\b",
    re.I,
)

# Numéro public WhatsApp Coins Marocain (wa.me / affichage).
_PUBLIC_WA_E164 = "212660159177"


class YasmineService:
    ACCUEIL_OPENING_FR = (
        "Bienvenue… Je suis Yasmine. Dis-moi simplement ce qui t’amène au "
        "Maroc en ce moment — un besoin de calme, une envie d’aventure, une "
        "célébration… Je t’écoute."
    )
    ACCUEIL_OPENING_EN = (
        "Welcome… I’m Yasmine. Just tell me what brings you to Morocco "
        "right now — a need for calm, a taste for adventure, a "
        "celebration… I’m listening."
    )
    MAX_USER_TURNS = 8
    ACCUEIL_SYSTEM = (
        "Tu es Yasmine, créatrice d’expérience personnalisée à Marrakech "
        "pour Coins Marocain. Tu n’es PAS un bot de réservation ni un "
        "formulaire.\n\n"
        "RÈGLES ABSOLUES :\n"
        "- Une seule question à la fois.\n"
        "- Reformule ce que tu comprends avant d’enchaîner (« Ah, un moment "
        "pour vous ressourcer en couple, je vois bien… »).\n"
        "- Interdit : sélectionnez, cochez, catégorie, options 1/2/3, "
        "listes à puces.\n"
        "- Ton chaleureux, immersif, 2–4 phrases max.\n"
        "- Tu explores : intention du voyage, avec qui, rythme, et "
        "éventuellement un rêve précis — mais tu sautes une question si la "
        "réponse précédente y répond déjà.\n"
        "- Quand tu as assez pour recommander (ou au plus tard après "
        "plusieurs échanges), tu termines par UNE recommandation narrative "
        "courte (2–3 expériences max), et tu peux teaser le Carnet du "
        "Voyageur (« ça pourrait être ton premier badge »).\n"
        "- Langue : réponds dans la langue du voyageur (FR par défaut, "
        "EN/ES si détecté).\n\n"
        "SIGNAL FORT (urgence / demain / ce soir / cette semaine / doutes "
        "sécurité) : si détecté, dis naturellement qu’« quelqu’un de "
        "l’équipe » va lui écrire directement — sans phrase générique de "
        "call-center.\n\n"
        "Quand tu recommandes, appelle l’outil save_recommendation avec le "
        "profil déduit et 1 à 3 activity_ids parmi le catalogue fourni "
        "(ou noms proches)."
    )
    ACCUEIL_TOOLS = [
        {
            "name": "save_recommendation",
            "description": (
                "Enregistre le profil déduit et la recommandation narrative "
                "finale (2–3 activités max)."
            ),
            "input_schema": {
                "type": "object",
                "properties": {
                    "visitor_text": {
                        "type": "string",
                        "description": (
                            "Texte narratif affiché au visiteur "
                            "(pas de liste à puces)."
                        ),
                    },
                    "intention": {
                        "type": "string",
                        "enum": [
                            "ressourcement",
                            "aventure",
                            "decouverte_humaine",
                            "celebration",
                            "mixte",
                        ],
                    },
                    "composition_groupe": {
                        "type": "string",
                        "enum": ["solo", "couple", "famille", "amis"],
                    },
                    "rythme": {
                        "type": "string",
                        "enum": ["tranquille", "dense", "mixte"],
                    },
                    "detail_libre": {"type": "string"},
                    "activity_ids": {
                        "type": "array",
                        "items": {"type": "integer"},
                        "description": "IDs coins.activite (1 à 3).",
                    },
                    "activity_names": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Noms si IDs inconnus.",
                    },
                    "score_confiance": {
                        "type": "number",
                        "minimum": 0,
                        "maximum": 1,
                    },
                    "signal_fort": {"type": "boolean"},
                    "signal_fort_type": {"type": "string"},
                },
                "required": [
                    "visitor_text",
                    "intention",
                    "score_confiance",
                ],
            },
        }
    ]

    def __init__(self, env):
        self.env = env
        self._icp = env["ir.config_parameter"].sudo()

    def anthropic_key(self):
        return (
            self._icp.get_param("doorway_agents_dashboard.anthropic_api_key")
            or self._icp.get_param("doorway_agents_ia.anthropic_api_key")
            or self._icp.get_param("renovation_conciergerie.anthropic_api_key")
        )

    def whatsapp_e164_digits(self):
        """Numéro affiché / wa.me (business Maroc)."""
        raw = (
            self._icp.get_param("coins_marocain.whatsapp_e164") or _PUBLIC_WA_E164
        ).strip()
        digits = re.sub(r"\D", "", raw)
        return digits or _PUBLIC_WA_E164

    def wa_me_url(self, prefill=""):
        digits = self.whatsapp_e164_digits()
        url = "https://wa.me/%s" % digits
        if prefill:
            url += "?text=" + quote(prefill)
        return url

    @staticmethod
    def normalize_phone(raw):
        if not raw:
            return ""
        digits = re.sub(r"\D", "", str(raw))
        if digits.startswith("00"):
            digits = digits[2:]
        return digits

    @staticmethod
    def detect_hot(msgs):
        blob = " ".join(m["content"] for m in msgs if m.get("role") == "user")
        if not blob:
            return False
        return bool(
            _SERVICE_RE.search(blob)
            and _URGENCY_RE.search(blob)
            and _INTENT_RE.search(blob)
        )

    @staticmethod
    def detect_conversion_interest(msgs):
        blob = " ".join(m["content"] for m in msgs if m.get("role") == "user")
        if not blob:
            return False
        user_turns = sum(1 for m in msgs if m.get("role") == "user")
        if _INTENT_RE.search(blob) or _SERVICE_RE.search(blob):
            return True
        return user_turns >= 2

    @staticmethod
    def wants_human(text):
        return bool(_HUMAN_RE.search(text or ""))

    def extract_email(self, text):
        m = _EMAIL_RE.search(text or "")
        return m.group(0) if m else None

    def extract_phone(self, text):
        m = _PHONE_RE.search(text or "")
        if not m:
            return None
        digits = re.sub(r"\D", "", m.group(0))
        if len(digits) < 9:
            return None
        return m.group(0).strip()

    def _get_tag(self, name):
        Tag = self.env["crm.tag"].sudo()
        tag = Tag.search([("name", "=", name)], limit=1)
        if not tag:
            tag = Tag.create({"name": name})
        return tag.id

    def create_lead(
        self,
        msgs,
        contact_email=None,
        contact_phone=None,
        hot=False,
        channel="web",
    ):
        convo = "\n".join(
            f"{m['role']}: {m['content']}" for m in msgs[-10:]
        )
        tags = [(4, self._get_tag("Coins — Concierge"))]
        name = "Concierge chat — Coins Marocain"
        desc = f"Conversation concierge ({channel}) :\n{convo}"
        if hot:
            tags.append((4, self._get_tag("Coins — Hot")))
            name = "🔥 HOT — Concierge Coins Marocain"
            desc = (
                "TRANSFERT À CHAUD (urgence détectée)\n"
                "Rappel attendu DANS L'HEURE.\n\n"
                "Conversation :\n%s" % convo
            )
        elif contact_phone or channel == "whatsapp":
            tags.append((4, self._get_tag("Coins — WhatsApp/SMS")))
            name = "Concierge WhatsApp — Coins Marocain"
        vals = {
            "name": name,
            "description": desc,
            "priority": "3" if hot else "1",
            "tag_ids": tags,
        }
        if contact_email:
            vals["email_from"] = contact_email[:120]
        if contact_phone:
            vals["phone"] = contact_phone[:40]
        return self.env["crm.lead"].sudo().create(vals)

    def notify_hot(self, lead, msgs, wa_url):
        hook = (self._icp.get_param("coins_marocain.hot_webhook_url") or "").strip()
        summary = " | ".join(
            m["content"][:120] for m in msgs if m.get("role") == "user"
        )[:500]
        payload = {
            "type": "coins_hot_handoff",
            "lead_id": lead.id if lead else None,
            "summary": summary,
            "whatsapp_url": wa_url,
            "priority": "urgent",
        }
        if hook:
            try:
                requests.post(hook, json=payload, timeout=5)
            except Exception as e:  # noqa: BLE001
                _logger.warning("coins hot webhook fail: %s", e)
        to_email = (
            self._icp.get_param("coins_marocain.hot_alert_email")
            or "info@coinsmarocain.com"
        )
        try:
            self.env["mail.mail"].sudo().create(
                {
                    "subject": "[Coins HOT] Demande urgente #%s"
                    % (lead.id if lead else "?"),
                    "email_to": to_email,
                    "body_html": (
                        "<p><b>Transfert à chaud Coins Marocain</b></p><p>"
                        f"{summary}</p><p><a href='{wa_url}'>Ouvrir WhatsApp"
                        f"</a></p><p>Lead Odoo id={lead.id if lead else 'n/a'}"
                        "</p>"
                    ),
                    "auto_delete": True,
                }
            ).send()
        except Exception as e:  # noqa: BLE001
            _logger.warning("coins hot mail fail: %s", e)

    def hot_reply(self, msgs, channel="web"):
        last = msgs[-1]["content"] if msgs else ""
        blob = " ".join(m["content"] for m in msgs if m.get("role") == "user")
        svc = _SERVICE_RE.search(last) or _SERVICE_RE.search(blob)
        when = _URGENCY_RE.search(last) or _URGENCY_RE.search(blob)
        svc_txt = svc.group(0) if svc else "votre demande"
        when_txt = when.group(0) if when else "très bientôt"
        if channel == "whatsapp":
            return (
                f"{when_txt.capitalize()} avec {svc_txt} — parfait, je "
                "m'en occupe. Confirmez-moi le créneau idéal et le nombre "
                "de personnes : je vérifie les disponibilités et je vous "
                "reviens tout de suite."
            )
        return (
            f"{when_txt.capitalize()} avec {svc_txt} — parfait, continuez "
            "avec moi sur WhatsApp pour vérifier les disponibilités en "
            "direct. 📲 Cliquez le bouton ci-dessous ou laissez votre "
            "numéro — je vous réponds dans l'heure."
        )

    def claude_reply(self, msgs, system_prompt, max_tokens=400):
        key = self.anthropic_key()
        if not key:
            return None
        try:
            resp = requests.post(
                ANTHROPIC_URL,
                headers={
                    "x-api-key": key,
                    "anthropic-version": ANTHROPIC_VERSION,
                    "content-type": "application/json",
                },
                json={
                    "model": CONCIERGE_MODEL,
                    "max_tokens": max_tokens,
                    "system": system_prompt,
                    "messages": msgs,
                },
                timeout=25,
            )
            data = resp.json()
            reply = ""
            for block in data.get("content") or []:
                if block.get("type") == "text":
                    reply += block.get("text", "")
            return (reply or "").strip() or None
        except Exception as e:  # noqa: BLE001
            _logger.exception("Yasmine Claude fail: %s", e)
            return None

    def get_or_create_session(self, phone_raw):
        phone = self.normalize_phone(phone_raw)
        if not phone:
            return False
        Session = self.env["coins.wa.session"].sudo()
        sess = Session.search([("phone", "=", phone)], limit=1)
        if not sess:
            sess = Session.create(
                {
                    "phone": phone,
                    "messages_json": "[]",
                    "active": True,
                }
            )
        return sess

    def session_messages(self, sess):
        try:
            return json.loads(sess.messages_json or "[]")
        except Exception:  # noqa: BLE001
            return []

    def append_session(self, sess, role, content):
        msgs = self.session_messages(sess)
        msgs.append({"role": role, "content": content})
        msgs = msgs[-20:]
        sess.write(
            {
                "messages_json": json.dumps(msgs, ensure_ascii=False),
            }
        )
        return msgs

    def seed_session_from_web(self, phone_raw, web_messages):
        """Bridge chat site → WhatsApp quand le voyageur donne son numéro."""
        sess = self.get_or_create_session(phone_raw)
        if not sess:
            return False
        existing = self.session_messages(sess)
        if existing:
            return sess
        cleaned = []
        for m in (web_messages or [])[-12:]:
            role = m.get("role")
            content = (m.get("content") or "").strip()
            if role not in ("user", "assistant") or not content:
                continue
            cleaned.append({"role": role, "content": content[:1500]})
        if cleaned:
            sess.write(
                {
                    "messages_json": json.dumps(cleaned, ensure_ascii=False),
                    "source": "web_bridge",
                }
            )
        return sess

    def find_lead_by_phone(self, phone_raw):
        phone = self.normalize_phone(phone_raw)
        if len(phone) < 9:
            return self.env["crm.lead"]
        tail = phone[-9:]
        Lead = self.env["crm.lead"].sudo()
        domain = [("phone", "ilike", tail)]
        if "mobile" in Lead._fields:
            domain = [
                "|",
                ("phone", "ilike", tail),
                ("mobile", "ilike", tail),
            ]
        return Lead.search(domain, order="id desc", limit=1)

    def _log_wa(
        self,
        phone,
        body,
        direction="outbound",
        statut="sent",
        provider="n8n",
        external_sid=None,
        error_message=None,
        lead_id=None,
    ):
        """Journalise dans doorway.wa.log (visible Coins + Messaging)."""
        try:
            phone_fmt = "+%s" % (
                self.normalize_phone(phone) or ""
            ).lstrip("+")
            if not phone_fmt or phone_fmt == "+":
                return None
            vals = {
                "direction": direction,
                "phone": phone_fmt,
                "body": (body or "")[:4096],
                "statut": statut,
                "provider": provider if provider in ("n8n", "twilio", "stub") else "n8n",
                "external_sid": external_sid or False,
                "error_message": error_message or False,
            }
            if lead_id:
                vals["lead_id"] = lead_id
            else:
                lead = self.find_lead_by_phone(phone_fmt)
                if lead:
                    vals["lead_id"] = lead.id
            self.env["doorway.wa.log"].sudo().create(vals)
        except Exception as e:  # noqa: BLE001
            _logger.warning("Coins WA log failed: %s", e)

    def send_whatsapp(self, to_phone, body):
        """Envoi : n8n wa-send (Twilio env) → Twilio direct → Meta Graph."""
        phone = self.normalize_phone(to_phone)
        if not phone:
            return {"success": False, "error": "no_phone"}
        body = (body or "")[:4096]
        n8n_url = (
            self._icp.get_param("doorway_messaging.n8n_wa_send_url")
            or "http://127.0.0.1:5678/webhook/wa-send"
        ).strip()
        n8n_err = tw_err = meta_err = None
        try:
            resp = requests.post(
                n8n_url,
                json={"phone": "+%s" % phone.lstrip("+"), "body": body},
                timeout=25,
            )
            data = resp.json() if resp.content else {}
            if resp.status_code < 400 and (
                data.get("ok") or data.get("success") or data.get("sid")
            ):
                sid = data.get("sid") or data.get("reply_sid") or ""
                self._log_wa(
                    phone, body, provider="n8n", external_sid=sid, statut="sent"
                )
                return {"success": True, "sid": sid, "via": "n8n"}
            n8n_err = data.get("error") or resp.text[:200]
        except Exception as e:  # noqa: BLE001
            n8n_err = str(e)
        try:
            from odoo.addons.doorway_messaging.services.whatsapp_service import (
                WhatsAppService,
            )

            res = WhatsAppService(self.env).send_whatsapp(
                to_number="+%s" % phone.lstrip("+"),
                body=body,
            )
            if res.get("success"):
                res["via"] = "twilio"
                self._log_wa(
                    phone,
                    body,
                    provider="twilio",
                    external_sid=res.get("sid"),
                    statut="sent",
                )
                return res
            tw_err = res.get("error")
        except Exception as e:  # noqa: BLE001
            tw_err = str(e)
        meta_tok = (
            self._icp.get_param("doorway_social_ia.meta_system_user_token") or ""
        ).strip()
        phone_id = (
            self._icp.get_param("coins_marocain.whatsapp_phone_number_id")
            or self._icp.get_param("doorway_social_ia.whatsapp_phone_number_id")
            or ""
        ).strip()
        if meta_tok and phone_id:
            try:
                resp = requests.post(
                    "https://graph.facebook.com/v21.0/%s/messages" % phone_id,
                    headers={"Authorization": "Bearer %s" % meta_tok},
                    json={
                        "messaging_product": "whatsapp",
                        "to": phone.lstrip("+"),
                        "type": "text",
                        "text": {"body": body},
                    },
                    timeout=25,
                )
                data = resp.json() if resp.content else {}
                if resp.status_code < 400 and not data.get("error"):
                    mid = (data.get("messages") or [{}])[0].get("id", "")
                    self._log_wa(
                        phone, body, provider="n8n", external_sid=mid, statut="sent"
                    )
                    return {"success": True, "sid": mid, "via": "meta"}
                meta_err = (data.get("error") or {}).get("message") or resp.text[:200]
            except Exception as e:  # noqa: BLE001
                meta_err = str(e)
        else:
            meta_err = "meta_not_configured"
        err = f"n8n={n8n_err} | twilio={tw_err} | meta={meta_err}"
        self._log_wa(
            phone, body, provider="n8n", statut="failed", error_message=err
        )
        return {"success": False, "error": err}

    def handle_whatsapp_inbound(self, phone_raw, body_text, message_sid=None):
        """Traite un message WhatsApp entrant → reply Yasmine + envoi Twilio."""
        body_text = (body_text or "").strip()
        if not body_text:
            return {"ok": False, "error": "empty"}
        sess = self.get_or_create_session(phone_raw)
        phone = sess.phone
        if not self.session_messages(sess):
            lead = self.find_lead_by_phone(phone)
            if lead and lead.description:
                seed = [
                    {
                        "role": "user",
                        "content": "[Résumé chat site / lead]\n%s"
                        % (lead.description or "")[:1200],
                    }
                ]
                sess.write(
                    {
                        "messages_json": json.dumps(seed, ensure_ascii=False),
                        "lead_id": lead.id,
                        "source": "lead_bridge",
                    }
                )
        msgs = self.append_session(sess, "user", body_text)
        self._log_wa(
            phone,
            body_text,
            direction="inbound",
            statut="received",
            provider="n8n",
            external_sid=message_sid,
            lead_id=sess.lead_id.id if sess.lead_id else None,
        )
        if not sess.source:
            sess.write({"source": "whatsapp"})
        if self.wants_human(body_text):
            reply = (
                "Bien sûr — je passe le relais à un conseiller Coins Marocain. "
                "Vous serez recontacté rapidement. En attendant, je reste "
                "disponible si vous voulez préciser dates ou activité."
            )
            sess.write({"human_handoff": True})
            lead = sess.lead_id or self.find_lead_by_phone(phone)
            if not lead:
                lead = self.create_lead(
                    msgs,
                    contact_phone="+%s" % phone,
                    hot=True,
                    channel="whatsapp",
                )
                sess.lead_id = lead.id
            self.notify_hot(lead, msgs, self.wa_me_url())
            self.append_session(sess, "assistant", reply)
            send = self.send_whatsapp(phone, reply)
            return {
                "ok": True,
                "reply": reply,
                "sent": send.get("success"),
                "handoff": True,
                "sid": send.get("sid"),
            }
        if sess.human_handoff and not re.search(
            r"\b(yasmine|bot|continuer|reprendre)\b", body_text, re.I
        ):
            return {
                "ok": True,
                "reply": None,
                "sent": False,
                "handoff": True,
                "paused": True,
            }
        hot = self.detect_hot(msgs)
        system = CONCIERGE_SYSTEM_WHATSAPP
        if hot:
            reply = self.hot_reply(msgs, channel="whatsapp")
        else:
            api_msgs = [m for m in msgs if m["role"] in ("user", "assistant")]
            reply = self.claude_reply(api_msgs, system, max_tokens=350)
            if not reply:
                reply = (
                    "Merci pour votre message 🌙 Dites-moi la destination et "
                    "les dates souhaitées, je vous propose des expériences "
                    "Coins Marocain adaptées."
                )
        lead = sess.lead_id
        if not lead:
            lead = self.find_lead_by_phone(phone)
        if hot or not lead:
            lead = self.create_lead(
                msgs,
                contact_phone="+%s" % phone,
                hot=hot,
                channel="whatsapp",
            )
            sess.lead_id = lead.id
        elif lead:
            try:
                lead.write(
                    {
                        "description": (lead.description or "")
                        + f"\n\n[WA] user: {body_text[:400]}"
                        + f"\n[WA] yasmine: {reply[:400]}"
                    }
                )
            except Exception:  # noqa: BLE001
                pass
        if hot and lead:
            self.notify_hot(lead, msgs, self.wa_me_url())
        self.append_session(sess, "assistant", reply)
        send = self.send_whatsapp(phone, reply)
        return {
            "ok": True,
            "reply": reply,
            "sent": bool(send.get("success")),
            "sid": send.get("sid"),
            "error": send.get("error"),
            "hot": hot,
            "lead_id": lead.id if lead else None,
            "message_sid": message_sid,
        }

    def detect_language(self, text):
        t = (text or "").lower()
        if re.search(r"[\u0600-\u06FF]", t):
            return "ar"
        if re.search(
            r"\b(the|i am|we're|we are|looking for|hello|hi)\b", t
        ) and not re.search(r"\b(je|nous|bonjour|salut|avec)\b", t):
            return "en"
        if re.search(r"\b(hola|gracias|viaje|nosotros)\b", t):
            return "es"
        return "fr"

    def detect_accueil_signal(self, msgs):
        blob = " ".join(m["content"] for m in msgs if m.get("role") == "user")
        if not blob:
            return (False, "")
        if _URGENCY_RE.search(blob):
            m = _URGENCY_RE.search(blob)
            return (True, m.group(0) if m else "urgence")
        if re.search(
            r"\b(s[eé]curit[eé]|arnaque|confiance|peur|inquiet|doute)\b",
            blob,
            re.I,
        ):
            return (True, "hesitation_confiance")
        if self.wants_human(blob):
            return (True, "demande_humain")
        return (False, "")

    def _activite_catalog_prompt(self):
        acts = (
            self.env["coins.activite"]
            .sudo()
            .search(
                [("active", "=", True), ("is_bookable", "=", True)],
                limit=40,
            )
        )
        lines = []
        for a in acts:
            lines.append(
                f"- id={a.id} | {a.name} | {a.category} | "
                f"{int(a.public_price or 0)} MAD"
            )
        if not lines:
            return "(catalogue vide — recommande narrativement sans IDs)"
        return "\n".join(lines)

    def get_or_create_accueil_conversation(self, session_id, language):
        Conv = self.env["coins.yasmine.conversation"].sudo()
        conv = Conv.search([("session_id", "=", session_id)], limit=1)
        if not conv:
            conv = Conv.create(
                {
                    "session_id": session_id,
                    "language": language or "fr",
                    "raw_transcript": "[]",
                    "state": "open",
                }
            )
        return conv

    def _conv_messages(self, conv):
        try:
            return json.loads(conv.raw_transcript or "[]")
        except Exception:  # noqa: BLE001
            return []

    def _save_conv_messages(self, conv, msgs):
        conv.write(
            {
                "raw_transcript": json.dumps(msgs[-30:], ensure_ascii=False),
                "turn_count": sum(1 for m in msgs if m.get("role") == "user"),
            }
        )

    def claude_accueil_turn(self, msgs, force_recommend=False):
        """Un tour Claude avec tool save_recommendation."""
        key = self.anthropic_key()
        if not key:
            return (None, None)
        catalog = self._activite_catalog_prompt()
        system = (
            self.ACCUEIL_SYSTEM
            + "\n\nCATALOGUE ACTIVITÉS (IDs Odoo) :\n"
            + catalog
        )
        if force_recommend:
            system += (
                "\n\nIMPORTANT : tu as assez d’éléments — termine MAINTENANT "
                "par save_recommendation."
            )
        try:
            resp = requests.post(
                ANTHROPIC_URL,
                headers={
                    "x-api-key": key,
                    "anthropic-version": ANTHROPIC_VERSION,
                    "content-type": "application/json",
                },
                json={
                    "model": CONCIERGE_MODEL,
                    "max_tokens": 700,
                    "system": system,
                    "tools": self.ACCUEIL_TOOLS,
                    "messages": msgs,
                },
                timeout=30,
            )
            data = resp.json()
            text = ""
            tool_input = None
            for block in data.get("content") or []:
                if block.get("type") == "text":
                    text += block.get("text", "")
                elif (
                    block.get("type") == "tool_use"
                    and block.get("name") == "save_recommendation"
                ):
                    tool_input = block.get("input") or {}
            return ((text or "").strip() or None, tool_input)
        except Exception as e:  # noqa: BLE001
            _logger.exception("Yasmine accueil Claude fail: %s", e)
            return (None, None)

    def _resolve_activites(self, ids=None, names=None):
        Activite = self.env["coins.activite"].sudo()
        found = Activite.browse()
        for i in ids or []:
            try:
                rec = Activite.browse(int(i))
                if rec.exists():
                    found |= rec
            except Exception:  # noqa: BLE001
                continue
        for name in names or []:
            if not name:
                continue
            rec = Activite.search(
                [("name", "ilike", name[:80])], limit=1
            )
            if rec:
                found |= rec
        return found[:3]

    def notify_zakaria_hot_handoff(self, conv, msgs, signal_type):
        """WhatsApp + webhook n8n vers Zakaria."""
        summary = " | ".join(
            m["content"][:120] for m in msgs if m.get("role") == "user"
        )[:450]
        base = (
            self._icp.get_param("coins_marocain.portal_base_url")
            or self._icp.get_param("web.base.url")
            or "https://intellixcrm.com"
        ).rstrip("/")
        odoo_link = f"{base}/web#id={conv.id}&model=coins.yasmine.conversation&view_type=form"
        body = (
            "🔥 Hot-handoff Yasmine (Coins Marocain)\nSignal : "
            f"{signal_type or '?'}\nIntention : "
            f"{conv.intention_deduite or 'en cours'}\nRésumé : "
            f"{summary}\nOdoo : {odoo_link}"
        )
        zak_phone = (
            self._icp.get_param("coins_marocain.zakaria_whatsapp")
            or self._icp.get_param("coins_marocain.emergency_whatsapp")
            or ""
        ).strip()
        wa_result = {"success": False}
        if zak_phone:
            wa_result = self.send_whatsapp(zak_phone, body)
        hook = (
            self._icp.get_param("coins_marocain.yasmine_hot_webhook_url")
            or self._icp.get_param("coins_marocain.hot_webhook_url")
            or "http://127.0.0.1:5678/webhook/coins-yasmine-hot"
        ).strip()
        try:
            requests.post(
                hook,
                json={
                    "type": "yasmine_hot_handoff",
                    "conversation_id": conv.id,
                    "conversation_name": conv.name,
                    "signal": signal_type,
                    "summary": summary,
                    "odoo_url": odoo_link,
                    "intention": conv.intention_deduite,
                    "zakaria_phone": zak_phone,
                    "body": body,
                },
                timeout=8,
            )
        except Exception as e:  # noqa: BLE001
            _logger.warning("yasmine hot webhook fail: %s", e)
        self.notify_hot(None, msgs, odoo_link)
        return wa_result

    def handle_accueil_chat(self, session_id, user_message, language=None):
        """Point d’entrée widget : ouverture / tour / recommandation / hot-handoff."""
        session_id = (session_id or "").strip()[:64]
        if not session_id:
            return {"ok": False, "error": "no_session"}
        user_message = (user_message or "").strip()
        if user_message:
            lang = language or self.detect_language(user_message)
        else:
            lang = language or "fr"
        conv = self.get_or_create_accueil_conversation(session_id, lang)
        msgs = self._conv_messages(conv)
        if not user_message and not msgs:
            opening = (
                self.ACCUEIL_OPENING_EN
                if lang == "en"
                else self.ACCUEIL_OPENING_FR
            )
            msgs = [{"role": "assistant", "content": opening}]
            self._save_conv_messages(conv, msgs)
            conv.write({"language": lang})
            return {
                "ok": True,
                "reply": opening,
                "session_id": session_id,
                "conversation_id": conv.id,
                "state": "open",
                "hot": False,
                "recommendation": None,
            }
        if not user_message:
            last_assistant = next(
                (
                    m.get("content")
                    for m in reversed(msgs)
                    if m.get("role") == "assistant"
                ),
                self.ACCUEIL_OPENING_EN
                if lang == "en"
                else self.ACCUEIL_OPENING_FR,
            )
            return {
                "ok": True,
                "reply": last_assistant,
                "session_id": session_id,
                "conversation_id": conv.id,
                "state": conv.state or "open",
                "hot": False,
                "recommendation": None,
                "already_open": True,
            }
        msgs.append({"role": "user", "content": user_message[:2000]})
        lang = (
            self.detect_language(user_message)
            or conv.language
            or "fr"
        )
        conv.write({"language": lang})
        email = self.extract_email(user_message)
        phone = self.extract_phone(user_message)
        if email or phone:
            Partner = self.env["res.partner"].sudo()
            partner = conv.partner_id
            if not partner and email:
                partner = Partner.search(
                    [("email", "=ilike", email)], limit=1
                )
            if not partner:
                partner = Partner.create(
                    {
                        "name": email or phone or "Voyageur Yasmine",
                        "email": email or False,
                        "phone": phone or False,
                        "comment": "Créé via conversation Yasmine (accueil)",
                    }
                )
            else:
                vals = {}
                if email and not partner.email:
                    vals["email"] = email
                if phone and not partner.phone:
                    vals["phone"] = phone
                if vals:
                    partner.write(vals)
            conv_vals = {"partner_id": partner.id}
            if phone:
                conv_vals["visitor_phone"] = phone
            if email:
                conv_vals["visitor_email"] = email
            conv.write(conv_vals)
        signal, signal_type = self.detect_accueil_signal(msgs)
        user_turns = sum(1 for m in msgs if m.get("role") == "user")
        force_rec = user_turns >= self.MAX_USER_TURNS
        if signal and not conv.hot_handoff_envoye:
            reply_hot = (
                "Je sens que tu as besoin d’une réponse concrète rapidement "
                "— quelqu’un de l’équipe va t’écrire directement pour "
                "t’accompagner. En attendant, je reste là si tu veux "
                "préciser ce que tu cherches."
                if lang != "en"
                else (
                    "I can tell you need a concrete answer soon — someone "
                    "from the team will message you directly. I’m still "
                    "here if you want to share more."
                )
            )
            msgs.append({"role": "assistant", "content": reply_hot})
            self._save_conv_messages(conv, msgs)
            conv.write(
                {
                    "signal_fort_detecte": True,
                    "signal_fort_type": signal_type,
                    "hot_handoff_envoye": True,
                    "state": "hot_handoff",
                }
            )
            self.notify_zakaria_hot_handoff(conv, msgs, signal_type)
            return {
                "ok": True,
                "reply": reply_hot,
                "session_id": session_id,
                "conversation_id": conv.id,
                "state": "hot_handoff",
                "hot": True,
                "recommendation": None,
            }
        text, tool = self.claude_accueil_turn(
            msgs, force_recommend=force_rec
        )
        recommendation = None
        reply = text
        if tool:
            acts = self._resolve_activites(
                tool.get("activity_ids"), tool.get("activity_names")
            )
            narrative = (
                tool.get("visitor_text") or text or ""
            ).strip()
            reply = narrative or reply
            vals = {
                "intention_deduite": tool.get("intention")
                or conv.intention_deduite,
                "composition_groupe": tool.get("composition_groupe")
                or conv.composition_groupe,
                "rythme": tool.get("rythme") or conv.rythme,
                "detail_libre": tool.get("detail_libre") or conv.detail_libre,
                "score_confiance": float(tool.get("score_confiance") or 0),
                "recommendation_narrative": narrative,
                "activites_recommandees_ids": [(6, 0, acts.ids)],
                "state": "recommended",
            }
            if tool.get("signal_fort"):
                vals["signal_fort_detecte"] = True
                vals["signal_fort_type"] = (
                    tool.get("signal_fort_type") or "tool"
                )
            conv.write(vals)
            recommendation = {
                "narrative": narrative,
                "activites": [
                    {
                        "id": a.id,
                        "name": a.name,
                        "category": a.category,
                        "public_price": a.public_price,
                        "duration": a.duration,
                    }
                    for a in acts
                ],
                "score_confiance": vals["score_confiance"],
                "intention": vals.get("intention_deduite"),
                "cta_url": (
                    f"/reservation?yasmine={conv.id}&activites="
                    + ",".join(str(i) for i in acts.ids)
                ),
            }
        if not reply:
            reply = (
                "Dis-moi encore un peu ce qui te ferait du bien ici — je "
                "compose quelque chose qui te ressemble."
                if lang != "en"
                else (
                    "Tell me a little more about what would feel right — "
                    "I’ll shape something for you."
                )
            )
        msgs.append({"role": "assistant", "content": reply})
        self._save_conv_messages(conv, msgs)
        return {
            "ok": True,
            "reply": reply,
            "session_id": session_id,
            "conversation_id": conv.id,
            "state": conv.state,
            "hot": False,
            "recommendation": recommendation,
        }
