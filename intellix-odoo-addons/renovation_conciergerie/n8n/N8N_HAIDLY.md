# n8n — Haidly + imports Doorway

## Import / mise à jour

```bash
python3 /odoo/custom/addons/renovation_conciergerie/n8n/import_doorway_workflows.py
```

Réimporte et **active** les workflows (tokens injectés depuis Odoo + `/etc/odoo-server.conf`).

## Webhooks actifs (n8n.intellixcrm.com)

| Path | Usage |
|------|--------|
| `/webhook/haidly-lead` | Formulaire SoumissionEntrepreneurs → Odoo + SMS + appel J+0 |
| `/webhook/haidly-postcall` | **ElevenLabs** fin d'appel → Claude → Odoo |
| `/webhook/haidly-relance-step` | Appel relance J+1/J+3/J+7/J+14 |
| `/webhook/haidly-nurture-start` | Séquence Wait (nurture longue durée) |

## Brancher le site / formulaire

`POST https://n8n.intellixcrm.com/webhook/haidly-lead`

```json
{
  "first_name": "Jean",
  "phone": "+15145551234",
  "city": "Longueuil",
  "project_type": "cuisine",
  "email": "jean@example.com"
}
```

## ElevenLabs

Post-call workspace configuré vers `haidly-postcall` (événement `transcript`).

Secret HMAC (console EL / Odoo ICP `elevenlabs_haidly_webhook_secret`) — optionnel pour validation n8n ultérieure.

Après **Setup ElevenLabs (Haidly)** dans Odoo, les appels utiliseront les vrais `agent_id` / `phone_number_id` retournés par `/api/haidly/lead`.
