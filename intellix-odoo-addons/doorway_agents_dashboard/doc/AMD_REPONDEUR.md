# Détection répondeur (AMD) — économie de crédits

## Deux chemins d'appels

| Chemin | Détection répondeur |
|--------|---------------------|
| **ElevenLabs** (`/convai/twilio/outbound-call`, n8n, Setup agents) | Outil système `voicemail_detection` sur chaque agent EL — raccroche **sans message** (`voicemail_message: null`) |
| **Odoo Twilio direct** (`TwilioService.make_outbound_call`) | AMD Twilio `DetectMessageEnd` → webhook `https://intellixcrm.com/doorway/agents/webhook/amd` → raccrochage si machine |

## Configuration Twilio (console)

La capture **Messaging** (SMS → webhook 3CX) ne gère **pas** les appels vocaux des agents IA.

- **SMS** : peut rester sur 3CX (`doorwaydigital.3cx.ca/...`) pour les textos entrants.
- **Voix agents IA** : numéros importés dans **ElevenLabs** (ex. Haidly `+15817058118`, SIP trunk). Les appels sortants passent par l'intégration EL ↔ Twilio, pas par le webhook Messaging.

Pour le chemin Odoo+Twilio natif, le webhook AMD doit être joignable :

`https://intellixcrm.com/doorway/agents/webhook/amd`

## Activer sur tous les agents ElevenLabs existants

1. **Agents IA** → n'importe quel agent ElevenLabs → **Activer détection répondeur (EL)**
2. Ou relancer **Setup ElevenLabs** (Sophie / Alex / Haidly) — l'outil est inclus automatiquement.

## n8n

Les orchestrateurs incluent `telephony_call_config.ringing_timeout_secs: 25` pour limiter la sonnerie inutile.

## VICIdial

Campagnes Doorway : onglet **Détection répondeur (AMD)** — `amd_enabled`, action `hangup` recommandée.
