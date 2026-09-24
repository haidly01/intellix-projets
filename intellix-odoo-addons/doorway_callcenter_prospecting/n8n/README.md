# n8n — Campagne Call Centers MA/TN

## Workflows à créer dans n8n

### 1. `extraction_callcenter_ma_tn`
1. Cron 06:00 UTC ou manuel
2. HTTP → Odoo extraction wizard (ou attendre fin campagne)
3. HTTP POST `https://intellixcrm.com/api/callcenter/extraction/import`
   - Body: `{"campagne_id": 123, "token": "..."}`
4. HTTP POST `https://intellixcrm.com/api/callcenter/prospects/validate`
5. HTTP POST `https://intellixcrm.com/api/callcenter/campaign/send-j0` (batch 100)

### 2. `campagne_whatsapp_sms_intellix`
- Cron J+2 09:00 → relances gérées par crons Odoo (`action_send_j2`, `action_send_j5`)
- Ou webhook manuel pour J0

### 3. Webhook Twilio entrant
Configurer dans Twilio Console :
`POST https://intellixcrm.com/api/callcenter/twilio/whatsapp-incoming`

## APIs Odoo

| Endpoint | Méthode | Description |
|----------|---------|-------------|
| `/api/callcenter/extraction/import` | POST | Import leads bruts → prospects |
| `/api/callcenter/prospects/ingest` | POST | Import JSON prospects |
| `/api/callcenter/prospects/validate` | POST | Twilio Lookup batch |
| `/api/callcenter/campaign/send-j0` | POST | Envoi message J0 |
| `/api/callcenter/stats` | GET | KPIs campagne |

Header : `X-Callcenter-Webhook-Token` (paramètre Odoo `doorway_callcenter_prospecting.webhook_token`)

## Conformité WhatsApp
Soumettre les templates J0/J2/J5 dans Twilio Console (catégorie MARKETING) avant envoi massif.
