# Sofia — Soumission Entrepreneurs (Québec)

Agent vocal outbound **fr-CA** pour qualifier des propriétaires (visites gratuites directeur des travaux).

## Stack Doorway (adapté au VPS intellixcrm)

| Couche | Techno |
|--------|--------|
| Téléphonie | VICIdial `DW_QCB2C` ou Twilio `+15817058118` |
| Orchestration | n8n `https://n8n.intellixcrm.com` |
| STT | Deepgram nova-2 `fr-CA` (via Odoo `/api/renov/stt/deepgram`) |
| LLM | Claude (Haiku classif. + Sonnet prompt système) |
| TTS | ElevenLabs — cache MP3 sur `intellixcrm.com/soumission-qc-tts` |
| CRM | Odoo 19 `intellixcrm` |
| SMS | Twilio |

## Workflows n8n

| # | Webhook |
|---|---------|
| 01 | `POST /webhook/soumission-qc/outbound` |
| 02 | `POST /webhook/soumission-qc/event` |
| 03 | `POST /webhook/soumission-qc/conversation` |
| 04 | `POST /webhook/soumission-qc/qualified` |
| 05 | `POST /webhook/soumission-qc/non-qualified` |
| 06 | Cron 18h → stats + email manager |

## Déploiement rapide

```bash
cd /odoo/custom/addons/renovation_conciergerie/n8n/soumission_qc
cp config.env.example   # → compléter /opt/n8n/.env (bloc soumission-qc)
python3 sync_workflow_code.py
python3 import_soumission_qc_workflows.py   # N8N_API_TOKEN requis

sudo -u odoo python3 /odoo/odoo-server/odoo-bin -c /etc/odoo-server.conf -d intellixcrm \
  -u doorway_agents_dashboard,doorway_vicidial_campaigns,doorway_credits --stop-after-init
```

## Test outbound

```bash
curl -X POST "https://n8n.intellixcrm.com/webhook/soumission-qc/outbound" \
  -H "Content-Type: application/json" \
  -d '{"telephone":"+15145551234","prenom":"Jean","partner_id":123}'
```

## Fichiers livrables (brief)

- `agent_config.json` — config agent
- `system_prompt_claude.txt` — prompt qualification
- `workflows/` + `n8n_soumission_workflows.json` — import n8n
- `sms_templates.json` — SMS Twilio
- `instructions_deploiement.md` — guide pas à pas

## Credentials à configurer

Les clés existantes sur le VPS (`/etc/odoo-server.conf` + `/opt/n8n/.env`) :

1. `DEEPGRAM_API_KEY`, `ANTHROPIC_API_KEY`, `ELEVENLABS_API_KEY`, `ELEVENLABS_VOICE_ID`
2. `TWILIO_ACCOUNT_SID`, `TWILIO_AUTH_TOKEN`, `TWILIO_FROM_SOUMISSION`
3. `DOORWAY_TENANT_API_KEY`, `N8N_API_TOKEN`
4. Voix Sofia clonée ElevenLabs (fr-CA québécois neutre)

Pas de Telnyx — environnement Doorway utilise **VICIdial + Twilio**.
