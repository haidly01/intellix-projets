# Sofia Espagne — n8n (VICIdial + TrustSIP)

Campagne **DW_ESREN** / liste **ESPAGNE_RENOVATION**. Téléphonie via le **trunk TrustSIP** déjà configuré dans Odoo (`sip_trunk_espagne.xml`) — **pas Telnyx**.

## Workflows

| Fichier | Webhook | Rôle |
|---------|---------|------|
| `01_outbound_vicidial.json` | `POST /webhook/sofia-es/outbound` | Lance un appel via `external_dial` VICIdial |
| `02_vicidial_events.json` | `POST /webhook/sofia-es/vicidial/event` | AGI Asterisk → moteur Sofia + facturation Odoo |
| `03_conversation_engine.json` | `POST /webhook/sofia-es/conversation` | Deepgram + Claude + répliques audio |
| `04_google_sheets.json` | `POST /webhook/sofia-es/sheets` | Écriture onglet **Leads_Sofia_Espagne** |

## Déploiement

```bash
cd /odoo/custom/addons/renovation_conciergerie/n8n/sofia_es
python3 sync_workflow_code.py
python3 import_sofia_es_workflows.py
# Si .env modifié :
cd /opt/n8n && docker compose up -d --force-recreate n8n
```

## Variables clés

- `TELEPHONY_PROVIDER=vicidial`
- `VICIDIAL_CAMPAIGN=DW_ESREN`
- `GOOGLE_SHEETS_TAB=Leads_Sofia_Espagne`
- `STORAGE_BUCKET_URL=https://intellixcrm.com/sofia-es-tts`
- `DOORWAY_TENANT_API_KEY` → facturation 0,22 €/min (AMD machine/not_sure = 0 €)

## Test outbound

```bash
curl -X POST "$N8N_WEBHOOK_URL/sofia-es/outbound" \
  -H "Content-Type: application/json" \
  -d '{"telephone":"+212674579467","nombre":"Test","partner_id":123}'
```

## AGI VICIdial

Pointer le script AGI campagne **DW_ESREN** vers :

`POST https://n8n.intellixcrm.com/webhook/sofia-es/vicidial/event`
