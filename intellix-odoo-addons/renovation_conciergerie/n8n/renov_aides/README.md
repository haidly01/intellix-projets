# renov-aides.fr — Agent vocal outbound v2

Qualification propriétaires **espagnols** — stack interchangeable Twilio / Telnyx / VICIdial+SIP.

## Architecture (4 couches)

```
TELEPHONY (Twilio | Telnyx | VICIdial) → n8n → Deepgram + Claude Haiku + ElevenLabs → Google Sheets
```

La logique métier (`core/`) ne parle **jamais** directement aux APIs téléphonie. Seul `telephony_adapter` traduit.

## Fichiers

| Fichier | Rôle |
|---------|------|
| `telephony_adapter.js` | Normalisation événements + TwiML/TeXML + outbound dispatch |
| `workflows/adapter_twilio.json` | Webhooks Twilio → format normalisé |
| `workflows/adapter_telnyx.json` | Webhooks Telnyx → format normalisé |
| `workflows/adapter_vicidial.json` | Webhooks VICIdial/AGI → format normalisé |
| `workflows/01_outbound_trigger.json` | Lit file leads + `TELEPHONY_PROVIDER` |
| `workflows/03_conversation_engine.json` | STT → Claude → TTS (state machine) |
| `workflows/05_google_sheets_writer.json` | Écriture lead qualifié |
| `workflows/utils_elevenlabs_tts.json` | TTS + cache MP3 |
| `workflows/utils_deepgram_stt.json` | Transcription enregistrement |

## Import n8n

1. Variables d'environnement : copier `config.env.example`
2. Importer dans l'ordre : `utils_*` → `adapter_*` → `05` → `03` → `01`
3. Activer les webhooks sur `N8N_WEBHOOK_URL`

## Changer de provider

```env
TELEPHONY_PROVIDER=telnyx   # ou twilio | vicidial
```

Rien d'autre à modifier dans `core/`.

## Cache TTS (économie ~60 %)

Au démarrage campagne, pré-générer via `utils_elevenlabs_tts.json` :

- `ouverture.mp3`, `q1_tipo_propiedad.mp3`, `q2_zona.mp3`, `q3_plazo.mp3`, `q4_presupuesto.mp3`, `cierre_rdv.mp3`, `despedida.mp3`

Seuls nom et créneau RDV sont générés live.

## VICIdial (VPS)

- API : `call_out_number` via `VicidialService.call_out_number()` (Odoo)
- AGI exemple : `scripts/n8n_bridge.agi.example`
- Enregistrements : `/var/spool/asterisk/monitor/` → upload n8n → Sheet

## Décision canal

| Volume/mois | Canal |
|-------------|-------|
| < 2 000 | Twilio |
| 2 000 – 10 000 | Telnyx |
| > 10 000 ou VICIdial déjà là | VICIdial + SIP OVH |

## Odoo

Service : `doorway_agents_dashboard/services/telephony_adapter_service.py`
