# Import workflows n8n — Qualification immo Meta Ads (complet)

## Fichiers à importer (ordre recommandé)

| # | Fichier | Rôle |
|---|---------|------|
| 1 | `workflow_immo_relance_orchestrator.json` | Un appel de relance (CRTC + EL outbound) |
| 2 | `workflow_immo_nurture_master.json` | **Séquence complète J+0 → J+30** (SMS, WA, appels) |
| 0 | `workflow_meta_leads_hub.json` | **Hub Meta** — toutes pages → route Odoo → orchestrateurs |
| 3 | `workflow_meta_immo_orchestrator.json` | Meta lead → Odoo → SMS/WA → appel J+0 |
| 4 | `workflow_elevenlabs_postcall.json` | Post-appel → Claude → nurture auto |
| 5 | `workflow_nurture_sequence.json` | *(obsolète — remplacé par #2)* |

Référence messages : `immo_relance_messages.json`  
Helpers JS : `immo_n8n_helpers.js` (documentation snippets)

## Architecture

```
Meta Lead → [Orchestrateur] → Odoo + SMS bienvenue + Appel Sophie J+0
                                    ↓
                            [Post-call] → Score HOT → transfert (fin)
                                        → WARM/COLD → [Nurture Master]
                                                              ↓
                    J+0: SMS 30min + WA 4h (si pas répondu)
                    J+1: Appel relance #1 → [Relance Orchestrator]
                    J+2: SMS valeur
                    J+3: Appel #2 (angle marché)
                    J+5: WhatsApp social proof
                    J+7: Appel dernière chance + WA
                    J+14: Re-engagement + SMS
                    J+30: Archive Odoo
```

## Variables d'environnement n8n

```env
N8N_WEBHOOK_BASE=https://doorway.app.n8n.cloud

# Agents ElevenLabs (après Setup Odoo)
ELEVENLABS_AGENT_ID_IMMO=agent_2301kt6hbtnnewmvh6etes9d7fwc
ELEVENLABS_AGENT_ID_RELANCE_J1=agent_7001kt6ja9gweew92kghfck7phdc
ELEVENLABS_AGENT_ID_RELANCE_J3=agent_7201kt6jaas4e22sfnve9j31wtr6
ELEVENLABS_AGENT_ID_RELANCE_J7=agent_2801kt6jac4mf74r5b7w6dy3xq02
ELEVENLABS_AGENT_ID_RELANCE_J14=agent_3301kt6jad4req8a1g1srhdrnvxx
ELEVENLABS_PHONE_NUMBER_ID=phnum_6701kt6hprkpfntt37gfckvvefhk

TWILIO_ACCOUNT_SID=...
TWILIO_AUTH_TOKEN=...
TWILIO_FROM_NUMBER=+14387905970

# Conformité CRTC
MAX_CALLS_PER_DAY=3
MAX_TOTAL_CALLS=10
CALL_START_HOUR=8
CALL_END_HOUR=20
```

## Credentials n8n

| Nom | Type | Détail |
|-----|------|--------|
| **Facebook Lead Ads — Doorway** | **Facebook Lead Ads OAuth2** | **Obligatoire sur l’orchestrateur immo** (trigger natif) |
| Odoo Meta Immo Token | Header Auth | `X-Immo-Webhook-Token` = token Odoo Paramètres |
| ElevenLabs API | Header Auth | `xi-api-key` |
| Anthropic API | Header Auth | `x-api-key` + `anthropic-version: 2023-06-01` |
| Twilio Basic Auth | HTTP Basic | Account SID + Auth Token |

### Connecter le formulaire Meta (orchestrateur immo)

1. n8n → **Credentials** → **Add credential** → **Facebook Lead Ads OAuth2 API**
2. Créer une app sur [Meta for Developers](https://developers.facebook.com/) (mode **Live**), produit **Facebook Login for Business** + permissions Lead Ads
3. Dans le workflow **Immo Meta — Orchestrateur**, ouvrir le nœud **1 Facebook Lead Ads** :
   - Credential : *Facebook Lead Ads — Doorway*
   - **Page** : Maison Recherchée (`964640820063787`, pré-rempli)
   - **Form** : choisir votre formulaire Lead Ads dans la liste déroulante
4. **Activer** le nœud **1 Facebook Lead Ads** (il est importé **désactivé** tant que le formulaire n’est pas choisi)
5. **Désactiver** le nœud **1b Webhook secours** si vous n’en avez plus besoin
6. **Publish** le workflow — Meta n’enregistre qu’**un webhook par app Facebook**

> **Limite Meta** : une seule app = un seul workflow avec trigger Facebook Lead Ads actif.  
> **Énergie Pro** (`energie-lead`) reste sur **Webhook** (pages ICI Thermopompe / Énergie Pro) ou nécessite une **2e app Meta** + 2e workflow trigger.

Guide détaillé : `doc/N8N_META_IMMO.md` § Facebook Lead Ads.

## Webhooks (activer les workflows)

| Workflow | Déclencheur | URL / connexion |
|----------|-------------|-----------------|
| Orchestrateur Meta | **Facebook Lead Ads** (Page + Form) | Credential OAuth dans n8n |
| Énergie Pro Orchestrateur | Webhook `energie-lead` | `…/webhook/energie-lead` |
| Post-call ElevenLabs | `elevenlabs-immo-postcall` | `…/webhook/elevenlabs-immo-postcall` |
| Nurture complet | `immo-nurture-start` | `…/webhook/immo-nurture-start` |
| Appel relance unitaire | `immo-relance-step` | `…/webhook/immo-relance-step` |

## API Odoo

| Méthode | URL | Usage |
|---------|-----|--------|
| POST | `/api/immo/meta-lead` | Création lead Meta |
| POST | `/api/immo/lead/update` | Scoring, relances, archive |
| GET | `/api/immo/lead/<id>` | Contexte lead pour n8n |

Header : `X-Immo-Webhook-Token`

## Notes importantes

1. **Nurture Master** = exécution longue (jusqu’à 30 jours). Garder le workflow **actif** ; n8n cloud conserve les Wait.
2. **Hors heures** : l’orchestrateur lance quand même la nurture (sans SMS J+0 30min, appel J+1 programmé).
3. **HOT** : post-call ne déclenche **pas** la nurture.
4. **Relance Orchestrator** doit être actif pour que les appels J+1/J+3/J+7/J+14 partent depuis le Master.

## Test nurture manuel

```bash
curl -X POST https://doorway.app.n8n.cloud/webhook/immo-nurture-start \
  -H "Content-Type: application/json" \
  -d '{
    "lead_id": 123,
    "phone": "+15145551234",
    "first_name": "Test",
    "full_address": "123 rue Test, Laval",
    "score": "warm",
    "call_answered": false,
    "total_call_attempts": 1
  }'
```

## Test relance appel seul

```bash
curl -X POST https://doorway.app.n8n.cloud/webhook/immo-relance-step \
  -H "Content-Type: application/json" \
  -d '{
    "lead_id": 123,
    "phone": "+15145551234",
    "first_name": "Jean",
    "relance_number": 1,
    "days_since_request": 1,
    "total_call_attempts": 2
  }'
```
