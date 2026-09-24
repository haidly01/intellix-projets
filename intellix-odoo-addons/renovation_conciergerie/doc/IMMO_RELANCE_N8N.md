# Relances immo Meta — Sophie (Addendum 2)

## Architecture

| Jour | Canal | Agent / contenu |
|------|--------|-----------------|
| J+0 | Appel | Qualification (`elevenlabs_agent_id_immo`) |
| J+0 +30min | SMS | `sms_j0_30min` |
| J+0 +4h | WhatsApp | `wa_j0_4h` |
| J+1 10h | Appel | Relance J+1 (`elevenlabs_agent_id_relance_j1`) |
| J+2 | SMS | `sms_j1` |
| J+3 10h | Appel | Relance J+3 (`…_relance_j3`) |
| J+5 | WhatsApp | `wa_j3` |
| J+7 16h | Appel | Relance J+7 (`…_relance_j7`) |
| J+7 | WhatsApp | `wa_j7` |
| J+10 | SMS nurture | n8n |
| J+14 10h | Appel | Re-engagement (`…_relance_j14`) |
| J+14 | SMS | `sms_j14` |
| J+30 | SMS + archive Odoo | `sms_j30`, tag `nurture-passif` |

## Création des agents ElevenLabs (Odoo)

1. **Agents IA** → **Maison Recherchée** → **Setup ElevenLabs (Sophie)** (voix + qualification + relances si possible)
2. Ou uniquement relances : **Setup relances J+1…J+14**

IDs stockés dans `ir.config_parameter` :

- `doorway_agents_dashboard.elevenlabs_agent_id_immo`
- `doorway_agents_dashboard.elevenlabs_agent_id_relance_j1`
- `doorway_agents_dashboard.elevenlabs_agent_id_relance_j3`
- `doorway_agents_dashboard.elevenlabs_agent_id_relance_j7`
- `doorway_agents_dashboard.elevenlabs_agent_id_relance_j14`

Fichier export : `doorway_agents_dashboard/voice_samples/elevenlabs_ids.json`

## Variables n8n

```env
ELEVENLABS_AGENT_ID_IMMO=agent_...
ELEVENLABS_AGENT_ID_RELANCE_J1=agent_...
ELEVENLABS_AGENT_ID_RELANCE_J3=agent_...
ELEVENLABS_AGENT_ID_RELANCE_J7=agent_...
ELEVENLABS_AGENT_ID_RELANCE_J14=agent_...
MAX_CALLS_PER_DAY=3
MAX_TOTAL_CALLS=10
CALL_START_HOUR=8
CALL_END_HOUR=20
```

## Workflows n8n (ensemble)

| Workflow | Webhook | Rôle |
|----------|---------|------|
| `workflow_meta_immo_orchestrator.json` | `meta-immo-lead` | Entrée Meta + appel J+0 |
| `workflow_elevenlabs_postcall.json` | `elevenlabs-immo-postcall` | Score + déclenche nurture |
| `workflow_immo_nurture_master.json` | `immo-nurture-start` | **Séquence SMS/WA/appels J+0→J+30** |
| `workflow_immo_relance_orchestrator.json` | `immo-relance-step` | Un appel relance (CRTC) |

Voir `n8n/README_SETUP.md` pour l’import et les variables d’environnement.

## Workflow relance unitaire

Webhook `immo-relance-step` — appelé par le Master ou en test manuel.

Payload exemple :

```json
{
  "lead_id": 123,
  "phone": "+15141234567",
  "first_name": "Jean",
  "property_address": "123 rue Example, Montréal",
  "relance_number": 1,
  "days_since_request": 1,
  "previous_call_attempts": 2,
  "total_call_attempts": 2,
  "do_not_call": false,
  "explicit_refusal": false,
  "market_insight": "Les ventes se stabilisent à +2% depuis le printemps.",
  "neighborhood": "Plateau",
  "season": "printemps"
}
```

## Conformité CRTC (workflow)

- Max **3** appels / 24 h par lead
- Max **10** appels total campagne
- Appels entre **8h et 20h** (America/Toronto)
- `do_not_call` ou `explicit_refusal` → arrêt total

## Odoo — champs CRM

- `immo_total_call_attempts`, `immo_last_call_at`, `immo_do_not_call`, `immo_explicit_refusal`
- `immo_relance_number`, `immo_days_since_request`

Mise à jour via `POST /api/immo/lead/update` avec `increment_call_attempt`, `final_status`, `relance_number`.

## Messages SMS/WA

Référence : `n8n/immo_relance_messages.json` (mêmes textes que `elevenlabs_maison_immo_relance.py`).
