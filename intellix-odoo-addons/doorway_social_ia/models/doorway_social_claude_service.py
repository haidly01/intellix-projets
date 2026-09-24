# -*- coding: utf-8 -*-
import json
import logging
import re

from odoo import models

_logger = logging.getLogger(__name__)

CALENDAR_SYSTEM = """Tu es expert en stratégie de contenu social media.
Génère un calendrier éditorial en JSON uniquement, sans texte autour.
Format :
{
  "posts": [
    {
      "day_offset": 0,
      "platform": "instagram",
      "format": "reel|story|publication|carrousel",
      "content_type": "video|image|carousel",
      "theme": "thème court",
      "hook": "accroche max 15 mots",
      "angle": "avant_apres|conseil|coulisse|preuve_sociale|education|promotion",
      "cta": "call to action",
      "hashtags": ["#tag1","#tag2","#tag3"],
      "visual_description": "description visuel pour Canva ou HeyGen (2 phrases max)",
      "best_time": "HH:MM"
    }
  ]
}"""


class DoorwaySocialClaudeService(models.AbstractModel):
    _name = "doorway.social.claude.service"
    _description = "Service Claude — contenu social IA"

    def _api_key(self):
        icp = self.env["ir.config_parameter"].sudo()
        return (
            icp.get_param("doorway_agents_dashboard.anthropic_api_key")
            or icp.get_param("doorway_social_ia.anthropic_api_key")
            or ""
        )

    def _call(self, system, user, max_tokens=4000):
        import requests

        key = self._api_key()
        if not key:
            _logger.warning("Anthropic API key manquante")
            return ""
        try:
            resp = requests.post(
                "https://api.anthropic.com/v1/messages",
                headers={
                    "x-api-key": key,
                    "anthropic-version": "2023-06-01",
                    "content-type": "application/json",
                },
                json={
                    "model": "claude-sonnet-4-20250514",
                    "max_tokens": max_tokens,
                    "system": system,
                    "messages": [{"role": "user", "content": user}],
                },
                timeout=90,
            )
            if resp.status_code != 200:
                _logger.warning("Claude HTTP %s", resp.status_code)
                return ""
            parts = resp.json().get("content") or []
            return "".join(
                p.get("text", "") for p in parts if p.get("type") == "text"
            ).strip()
        except Exception as exc:  # noqa: BLE001
            _logger.warning("Claude API: %s", exc)
            return ""

    def _parse_json(self, text):
        if not text:
            return {}
        m = re.search(r"\{[\s\S]*\}", text)
        try:
            return json.loads(m.group(0) if m else text)
        except json.JSONDecodeError:
            return {}

    def generate_calendar(self, wizard):
        days = max(1, (wizard.period_end - wizard.period_start).days)
        nb_posts = wizard.frequency * max(1, days // 7)
        accounts_info = ", ".join(
            f"{a.name} ({a.platform})" for a in wizard.account_ids
        )
        tone_label = dict(wizard._fields["tone"].selection).get(wizard.tone, wizard.tone)
        user = f"""Marque : {wizard.pipeline_id.name}
Sujet : {wizard.topic}
Période : {wizard.period_start} → {wizard.period_end}
Nombre de posts : {nb_posts}
Comptes : {accounts_info or 'tous'}
Ton : {tone_label}
Génère le calendrier complet."""
        raw = self._call(CALENDAR_SYSTEM, user, max_tokens=4000)
        data = self._parse_json(raw)
        if not data.get("posts"):
            data = self._fallback_calendar(wizard, nb_posts)
        return data

    def _fallback_calendar(self, wizard, nb_posts):
        """Calendrier minimal si Claude indisponible."""
        posts = []
        platforms = [a.platform for a in wizard.account_ids] or ["instagram", "facebook"]
        for i in range(min(nb_posts, 14)):
            posts.append({
                "day_offset": i * (max(1, (wizard.period_end - wizard.period_start).days) // max(nb_posts, 1)),
                "platform": platforms[i % len(platforms)],
                "format": "publication" if i % 3 else "reel",
                "hook": f"{wizard.topic[:40]} — idée {i + 1}",
                "angle": "conseil",
                "cta": "Contactez-nous",
                "hashtags": ["#renovation", "#quebec"],
                "visual_description": wizard.topic,
                "best_time": "10:00",
            })
        return {"posts": posts}

    def generate_caption(self, post, short=False):
        system = (
            "Tu rédiges des captions social media en français québécois. "
            "Réponds uniquement avec le texte de la caption, sans guillemets."
        )
        if short:
            system += " Maximum 2 phrases."
        user = f"""Plateforme : {post.platform}
Format : {post.post_format}
Accroche : {post.hook}
Angle : {post.angle}
CTA : {post.cta}
Hashtags : {post.hashtags}
Description visuel : {post.visual_description}"""
        return self._call(system, user, max_tokens=300 if short else 600) or post.hook or ""

    def generate_script(self, post):
        system = (
            "Tu écris des scripts vidéo courts (30-45s) pour avatar IA HeyGen. "
            "Français québécois, ton naturel. Réponds uniquement avec le script."
        )
        user = f"""Marque : {post.pipeline_id.name}
Plateforme : {post.platform} / {post.post_format}
Accroche : {post.hook}
Angle : {post.angle}
Description : {post.visual_description}"""
        return self._call(system, user, max_tokens=800) or post.hook or ""

    def auto_reply(self, inbox, incoming_text):
        system = (
            "Tu réponds aux messages clients pour une agence marketing québécoise. "
            "Réponse courte (1-3 phrases), professionnelle et chaleureuse."
        )
        user = f"Canal : {inbox.inbox_source}\nMessage : {incoming_text}"
        return self._call(system, user, max_tokens=200)

    def _call_haiku(self, system, user, max_tokens=300):
        import requests

        key = self._api_key()
        if not key:
            _logger.warning("Anthropic API key manquante")
            return ""
        try:
            resp = requests.post(
                "https://api.anthropic.com/v1/messages",
                headers={
                    "x-api-key": key,
                    "anthropic-version": "2023-06-01",
                    "content-type": "application/json",
                },
                json={
                    "model": "claude-haiku-4-5-20251001",
                    "max_tokens": max_tokens,
                    "system": system,
                    "messages": [{"role": "user", "content": user}],
                },
                timeout=60,
            )
            if resp.status_code != 200:
                _logger.warning("Claude Haiku HTTP %s", resp.status_code)
                return ""
            parts = resp.json().get("content") or []
            return "".join(
                p.get("text", "") for p in parts if p.get("type") == "text"
            ).strip()
        except Exception as exc:  # noqa: BLE001
            _logger.warning("Claude Haiku API: %s", exc)
            return ""

    def suggest_inbox_reply(self, inbox):
        history = inbox.message_line_ids[-10:]
        context = "\n".join(
            f"{'Client' if m.direction == 'inbound' else 'Nous'}: {m.content}"
            for m in history
        )
        account_context = inbox.account_id.name if inbox.account_id else "la marque"
        system = f"""Tu es un assistant pour {account_context}.
Génère une réponse courte, professionnelle et chaleureuse au dernier message.
Maximum 3 phrases. Langue détectée automatiquement.
Réponds UNIQUEMENT avec le texte de la réponse, sans introduction."""
        user = f"Historique :\n{context}"
        return self._call_haiku(system, user, max_tokens=300)

    def suggest_comment_reply(self, comment_text, account_name=""):
        system = """Génère une réponse courte et engageante à ce commentaire sur les réseaux sociaux.
Maximum 2 phrases. Ton chaleureux et professionnel.
Réponds UNIQUEMENT avec le texte de la réponse."""
        brand = account_name or "la marque"
        user = f"Marque : {brand}\nCommentaire : {comment_text}"
        return self._call_haiku(system, user, max_tokens=200)
