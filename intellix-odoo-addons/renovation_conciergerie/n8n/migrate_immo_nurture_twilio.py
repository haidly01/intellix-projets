#!/usr/bin/env python3
"""Convertit les nœuds Twilio/relance HTTP du nurture immo en nœuds Code."""
from __future__ import annotations

import json
from pathlib import Path

PATH = Path(__file__).resolve().parent / "workflow_immo_nurture_master.json"

def _sms_code(msg_expr: str, whatsapp: bool = False) -> str:
    to_expr = (
        "encodeURIComponent('whatsapp:' + c.phone)"
        if whatsapp
        else "encodeURIComponent(c.phone)"
    )
    from_expr = (
        "encodeURIComponent('whatsapp:' + from)"
        if whatsapp
        else "encodeURIComponent(from)"
    )
    return (
        "const c = $('1 Préparer contexte').first().json;\n"
        "const sid = '{{TWILIO_ACCOUNT_SID}}';\n"
        "const auth = Buffer.from(sid + ':{{TWILIO_AUTH_TOKEN}}').toString('base64');\n"
        "const from = '{{TWILIO_FROM_IMMO}}';\n"
        f"const msg = {msg_expr};\n"
        "await this.helpers.httpRequest({\n"
        "  method: 'POST',\n"
        f"  url: `https://api.twilio.com/2010-04-01/Accounts/${{sid}}/Messages.json`,\n"
        "  headers: { Authorization: 'Basic ' + auth, "
        "'Content-Type': 'application/x-www-form-urlencoded' },\n"
        f"  body: `To=${{{to_expr}}}&From=${{{from_expr}}}&Body=${{encodeURIComponent(msg)}}`,\n"
        "});\n"
        "return [{ json: c }];"
    )


def _relance_code(body_expr: str) -> str:
    return (
        "const c = $('1 Préparer contexte').first().json;\n"
        "const base = c.n8n_base || '{{N8N_WEBHOOK_BASE}}';\n"
        f"const body = {body_expr};\n"
        "await this.helpers.httpRequest({\n"
        "  method: 'POST',\n"
        "  url: base + '/webhook/immo-relance-step',\n"
        "  headers: { 'Content-Type': 'application/json' },\n"
        "  body,\n"
        "  json: true,\n"
        "});\n"
        "return [{ json: c }];"
    )

SMS_MSGS = {
    "6 SMS J+0 30min": (
        "`Bonjour ${c.first_name}! 👋\\n\\nJe viens d'essayer de vous joindre concernant votre évaluation marchande gratuite.\\n\\nRépondez simplement OUI ici et je vous rappelle dans les prochaines minutes!\\n\\n— Sophie, Maison Recherchée.`"
    ),
    "14 SMS J+2 valeur": (
        "`Bonjour ${c.first_name}!\\n\\n💡 Les propriétés dans votre secteur se vendent en moyenne en ${c.market_days} jours.\\n\\nVotre évaluation gratuite vous donne une fourchette précise.\\n\\nDisponible pour un appel rapide aujourd'hui?\\n\\n— Agence Doorway`"
    ),
    "28 SMS J+14": (
        "`Bonjour ${c.first_name} 👋\\n\\nNotre rapport de marché ${c.season} pour votre secteur est prêt.\\n\\nRépondez OUI 📊 — Maison Recherchée.`"
    ),
    "30 SMS J+30 archive": (
        "`Bonjour ${c.first_name}, votre dossier sera archivé cette semaine. Écrivez RÉACTIVER pour reprendre. — Équipe Maison Recherchée. 🏡`"
    ),
}

WA_MSGS = {
    "8 WhatsApp J+0 4h": (
        "`Bonjour ${c.first_name} 😊\\n\\nVotre demande d'évaluation marchande est bien reçue!\\n\\nQuel est le meilleur moment pour vous appeler cette semaine?\\n\\n☐ Matin (8h-12h)\\n☐ Après-midi (12h-17h)\\n☐ Soir (17h-20h)\\n\\n— Sophie, Maison Recherchée.`"
    ),
    "20 WhatsApp J+5": (
        "`Bonjour ${c.first_name} 🏡\\n\\nCette semaine, on a aidé des propriétaires du secteur ${c.neighborhood}.\\n\\n✅ Évaluation en 24h\\n✅ Ventes comparables\\n✅ Estimation nette\\n\\nGratuit et sans engagement. On fixe ça cette semaine?`"
    ),
    "24 WhatsApp J+7 dernier": (
        "`Bonjour ${c.first_name}, dernier message 😊 — votre dossier expire dans 48h. Répondez OUI pour le garder actif. — Sophie, Maison Recherchée.`"
    ),
}

RELANCE_BODIES = {
    "11 Appel relance J+1": """{
  lead_id: c.lead_id,
  phone: c.phone,
  first_name: c.first_name,
  property_address: c.full_address,
  relance_number: 1,
  days_since_request: 1,
  previous_call_attempts: c.total_call_attempts + 1,
  total_call_attempts: c.total_call_attempts + 1,
}""",
    "17 Appel relance J+3": """{
  lead_id: c.lead_id,
  phone: c.phone,
  first_name: c.first_name,
  property_address: c.full_address,
  relance_number: 2,
  days_since_request: 3,
  market_insight: 'Les ventes récentes montrent une demande soutenue dans le secteur.',
  neighborhood: c.neighborhood,
  total_call_attempts: 3,
}""",
    "23 Appel relance J+7": """{
  lead_id: c.lead_id,
  phone: c.phone,
  first_name: c.first_name,
  relance_number: 3,
  days_since_request: 7,
  previous_attempts: 4,
  total_call_attempts: 5,
}""",
    "27 Appel J+14": """{
  lead_id: c.lead_id,
  phone: c.phone,
  first_name: c.first_name,
  relance_number: 4,
  days_since_request: 14,
  season: c.season,
  total_call_attempts: 6,
}""",
}


def _to_code(node: dict, js_code: str) -> None:
    node["type"] = "n8n-nodes-base.code"
    node["typeVersion"] = 2
    node["parameters"] = {"jsCode": js_code}
    node.pop("credentials", None)


def main() -> None:
    data = json.loads(PATH.read_text(encoding="utf-8"))
    for node in data["nodes"]:
        name = node.get("name", "")
        if name in SMS_MSGS:
            _to_code(node, _sms_code(SMS_MSGS[name]))
        elif name in WA_MSGS:
            _to_code(node, _sms_code(WA_MSGS[name], whatsapp=True))
        elif name in RELANCE_BODIES:
            _to_code(node, _relance_code(RELANCE_BODIES[name]))
    PATH.write_text(
        json.dumps(data, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    print("Migrated", PATH.name)


if __name__ == "__main__":
    main()
