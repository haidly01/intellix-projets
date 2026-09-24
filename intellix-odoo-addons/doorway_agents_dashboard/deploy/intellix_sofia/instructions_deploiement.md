# Intellix — Déploiement Sofia (centres d'appels Maroc)

Stack cible : **VICIdial + n8n + Deepgram + Claude + ElevenLabs + Odoo + WhatsApp Meta**

> **Pas de Retell** et **pas de trunk Doorway France** dans cette version.  
> La téléphonie passe par VICIdial → AGI → n8n. WhatsApp depuis **+212 660159177**.

---

## Fichiers livrés

| Fichier | Rôle |
|---------|------|
| `sofia_agent_config.json` | Config agent Sofia (prompt, voix, intents, webhooks) |
| `sip_vicidial_n8n.conf` | Dialplan Asterisk/VICIdial → n8n |
| `n8n_bridge.agi` | Script AGI Python bridge appels → n8n → Odoo |
| `n8n_intellix_workflows.json` | 6 workflows + moteur conversation |
| `instructions_deploiement.md` | Ce guide |

Chemin serveur : `/odoo/custom/addons/doorway_agents_dashboard/deploy/intellix_sofia/`

---

## Prérequis (déjà sur intellixcrm)

| Variable | Valeur connue |
|----------|---------------|
| `ODOO_URL` | `https://intellixcrm.com` |
| `N8N_BASE_URL` | `https://n8n.intellixcrm.com` |
| `ELEVENLABS_VOICE_ID` | `FqF9IZCNgkSbGVwutMcg` |
| `STORAGE_BUCKET_URL` | `https://intellixcrm.com/sofia-tts` |
| `WHATSAPP_SENDER` | `+212 660159177` |
| `DEEPGRAM_API_KEY` | Configuré dans `/etc/odoo-server.conf` |
| `DOORWAY_AGENTS_WEBHOOK_KEY` | Configuré dans `/etc/odoo-server.conf` |

À compléter dans n8n :

| `WHATSAPP_PHONE_ID` | `917370758130261` |
| `WHATSAPP_TOKEN` | = `META_PAGE_ACCESS_TOKEN` (déjà dans `/opt/n8n/.env`) |
| `ODOO_CALENDAR_BOOKING_URL` | `https://intellixcrm.com/intellix/rdv/zakaria` |
| `ANTHROPIC_API_KEY` | Configuré (Odoo + n8n) |

---

## ÉTAPE 1 — Agent Sofia (n8n)

### 1.1 Importer la config agent

```bash
# Sur le serveur ou en local
curl -sS -X POST "https://n8n.intellixcrm.com/webhook/doorway/agents/sync" \
  -H "Authorization: Bearer $N8N_API_TOKEN" \
  -H "Content-Type: application/json" \
  -d @/odoo/custom/addons/doorway_agents_dashboard/deploy/intellix_sofia/sofia_agent_config.json
```

### 1.2 Créer le profil Odoo

Dans **Agents IA → Profils**, créer ou mettre à jour :

- **Nom** : Sofia — Intellix CC Maroc
- **Provider** : n8n
- **ID externe** : `sofia-intellix-cc-fr-maroc`
- **Pipeline** : intellix_callcenter
- **Langue** : fr
- **Volet** : cold_call

### 1.3 Tester Sofia (sans téléphone)

Odoo → Agent → **Test web** (micro navigateur)

Stack attendue : `n8n+deepgram+claude+elevenlabs`  
Webhook : `POST /webhook/doorway/agents/start-web-test`

### 1.4 Webhooks à noter

| Webhook | URL |
|---------|-----|
| Conversation téléphonie | `https://n8n.intellixcrm.com/webhook/intellix/conversation` |
| Booking démo | `https://n8n.intellixcrm.com/webhook/intellix/booking-demo` |
| Callback Odoo | `https://intellixcrm.com/api/agents/webhook/n8n` |

---

## ÉTAPE 2 — ElevenLabs

1. Console [elevenlabs.io](https://elevenlabs.io) → **Voices**
2. Vérifier la voix Sofia : ID `FqF9IZCNgkSbGVwutMcg`
3. Tester TTS français :

```bash
curl -sS -X POST "https://api.elevenlabs.io/v1/text-to-speech/FqF9IZCNgkSbGVwutMcg" \
  -H "xi-api-key: $ELEVENLABS_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"text":"Bonjour, je suis Sofia d Intellix.","model_id":"eleven_multilingual_v2"}' \
  --output /tmp/sofia-test.mp3
```

4. Uploader les prompts audio pré-enregistrés vers `STORAGE_BUCKET_URL` (optionnel, accélère les appels).

---

## ÉTAPE 3 — VICIdial + Asterisk (sans Doorway SIP)

### 3.1 Déployer le dialplan

```bash
sudo cp /odoo/custom/addons/doorway_agents_dashboard/deploy/intellix_sofia/sip_vicidial_n8n.conf \
  /etc/asterisk/extensions_intellix_sofia.conf

# Ajouter dans extensions.conf :
# #include extensions_intellix_sofia.conf

sudo asterisk -rx "dialplan reload"
```

### 3.2 Déployer l'AGI

```bash
sudo cp /odoo/custom/addons/doorway_agents_dashboard/deploy/intellix_sofia/n8n_bridge.agi \
  /var/lib/asterisk/agi-bin/
sudo chmod +x /var/lib/asterisk/agi-bin/n8n_bridge.agi
sudo chown asterisk:asterisk /var/lib/asterisk/agi-bin/n8n_bridge.agi
```

Variables d'environnement AGI (dans `extensions.conf` ou `agi.conf`) :

```ini
export N8N_WEBHOOK_URL=https://n8n.intellixcrm.com/webhook/telephony/vicidial/event
export ODOO_WEBHOOK_URL=https://intellixcrm.com/api/agents/webhook/n8n
export ODOO_WEBHOOK_KEY=<DOORWAY_AGENTS_WEBHOOK_KEY>
export AGENT_ID=sofia-intellix-cc-fr-maroc
```

### 3.3 Configurer VICIdial

1. **Admin → Campaigns** → nouvelle campagne `INTELLIX_CC_MA`
2. **Dial method** : RATIO ou ADAPT
3. **Recording** : Yes + post-call script AGI
4. **CallerID** : numéro autorisé par votre opérateur actuel
5. **Inbound** (si callback) : DID → context `intellix-incoming`
6. **Remote agents** : lier agents IA si dialer auto

### 3.4 Test appel

```bash
# Test AGI manuel depuis Asterisk CLI
asterisk -rx "channel originate Local/86000@from-internal-custom application Wait 1"
```

Vérifier dans n8n → Executions que le webhook `telephony/vicidial/event` reçoit l'événement.

---

## ÉTAPE 4 — n8n

### 4.1 Variables d'environnement n8n

Dans **Settings → Variables** :

```
ODOO_URL=https://intellixcrm.com
ODOO_API_KEY=<clé API Odoo>
ANTHROPIC_API_KEY=<clé Anthropic>
DEEPGRAM_API_KEY=<clé Deepgram>
ELEVENLABS_API_KEY=<clé ElevenLabs>
ELEVENLABS_VOICE_ID=FqF9IZCNgkSbGVwutMcg
WHATSAPP_PHONE_ID=<ID Meta>
WHATSAPP_TOKEN=<token Meta>
WHATSAPP_SENDER_E164=212660159177
STORAGE_BUCKET_URL=https://intellixcrm.com/sofia-tts
ODOO_CALENDAR_BOOKING_URL=https://intellixcrm.com/intellix/rdv/zakaria
WHATSAPP_PHONE_ID=917370758130261
WHATSAPP_TOKEN=<META_PAGE_ACCESS_TOKEN>
DEMO_VIDEO_URL=<lien vidéo démo 2 min>
N8N_BASE_URL=https://n8n.intellixcrm.com
DOORWAY_AGENTS_WEBHOOK_KEY=<clé hex>
```

### 4.2 Importer les workflows

Le fichier `n8n_intellix_workflows.json` contient **7 workflows** (6 + moteur conversation).

Import : n8n → **Workflows → Import from File** — importer **chaque workflow** individuellement  
(ou copier les objets du tableau `workflows[]` un par un).

**Ordre d'activation** (du plus indépendant au trigger) :

1. WF6 — Onboarding *(désactivé jusqu'au premier client)*
2. WF5 — Post démo
3. WF4 — Gestion no-show
4. WF3 — Rappel H-30
5. WF2 — Booking démo
6. **Conversation Engine Sofia** *(téléphonie)*
7. WF1 — Prospection sortante *(en dernier)*

### 4.3 Credentials n8n

| Credential | Usage |
|------------|-------|
| Odoo API Key | JSON-2 API Odoo 19 |
| ElevenLabs | TTS vocaux WhatsApp |
| WhatsApp Business | Meta Graph API v21 |
| Anthropic | Claude Haiku conversation |
| Deepgram | STT temps réel |

---

## ÉTAPE 5 — Odoo

### 5.1 Tags CRM à créer

| Tag | Usage |
|-----|-------|
| À prospecter | Trigger WF1 |
| WhatsApp invalide | Numéro sans WhatsApp |
| Do Not Contact | Réponse STOP |
| Pas intéressé | Intent Sofia |
| Démo Intellix | Booking confirmé |
| No-show | Absent au RDV |
| Client actif | Onboarding terminé |
| Invalide | Mauvais numéro |
| Rappel programmé | Rappeler plus tard |

### 5.2 Webhook sortant vers n8n (WF1)

Automatisation Odoo ou `lead_automation_hub` :

```
Quand tag "À prospecter" ajouté sur crm.lead
→ POST https://n8n.intellixcrm.com/webhook/intellix/prospection-start
Body: { lead_id, prenom, phone, nom_centre, partner_id }
```

### 5.3 Webhook entrant n8n → Odoo

Déjà actif : `POST /api/agents/webhook/n8n`  
Header : `X-Doorway-Key: <DOORWAY_AGENTS_WEBHOOK_KEY>`

### 5.4 Devis automatiques (WF5)

Modèles disponibles (`intellix_catalog`) :

| Agents estimés | Modèle devis |
|----------------|--------------|
| ≤ 10 | Call Center — 10 agents |
| ≤ 30 | Call Center — 30 agents |
| > 30 | Call Center — 50 agents |

### 5.5 Calendrier Zakaria (Odoo natif)

Lien public de réservation démo (10 min) :

**https://intellixcrm.com/intellix/rdv/zakaria**

- Calendrier : `zakaria@agencedoorway.com` (user_id 6)
- Créneaux : lun–ven, 9h–22h, fuseau Casablanca
- Variable n8n : `ODOO_CALENDAR_BOOKING_URL`
- API : `GET /api/intellix/booking/url`

---

## ÉTAPE 6 — Test end-to-end

### Scénario complet

```
1. Créer lead test Odoo
   Nom : Centre Test Casablanca
   Téléphone : +2126XXXXXXXX
   Tag : "À prospecter"

2. Vérifier WF1
   → Vocal WhatsApp J1 (9h00)
   → Texte démo J1 (9h01)

3. Simuler réponse OUI
   → WF2 booking
   → Événement calendrier créé
   → Lien Cal.com envoyé

4. H-30 : WF3 vocal rappel

5. Marquer démo "Tenu" dans Odoo
   → WF5 devis auto (modèle 10/30/50 agents)
   → WhatsApp lien devis

6. Accepter + signer devis
   → WF6 onboarding (tâches + vocal bienvenue)

7. Test téléphonie (parallèle)
   → Campagne VICIdial → AGI → n8n conversation
   → Intent OUI_DEMO → WF2
```

### Commandes de vérification

```bash
# Test webhook booking
curl -sS -X POST "https://n8n.intellixcrm.com/webhook/intellix/booking-demo" \
  -H "Content-Type: application/json" \
  -d '{"prenom":"Karim","nom_centre":"CallPro Casa","phone":"212660159177","lead_id":999,"partner_id":1}'

# Test callback Odoo
curl -sS -X POST "https://intellixcrm.com/api/agents/webhook/n8n" \
  -H "Content-Type: application/json" \
  -H "X-Doorway-Key: $DOORWAY_AGENTS_WEBHOOK_KEY" \
  -d '{"call_id":"test-001","agent_id":"sofia-intellix-cc-fr-maroc","duration_ms":45000,"intent":"OUI_DEMO","transcript":[{"role":"user","content":"Oui jeudi"}]}'
```

---

## Architecture

```
┌─────────────┐     ┌──────────┐     ┌───────────┐     ┌────────────┐
│  VICIdial   │────▶│ AGI n8n  │────▶│    n8n    │────▶│  Deepgram  │
│  (dialer)   │     │  bridge  │     │  Engine   │     │    STT     │
└─────────────┘     └──────────┘     └─────┬─────┘     └────────────┘
                                           │
                    ┌──────────────────────┼──────────────────────┐
                    ▼                      ▼                      ▼
              ┌──────────┐          ┌──────────┐          ┌────────────┐
              │  Claude  │          │ElevenLabs│          │  WhatsApp  │
              │  Haiku   │          │   TTS    │          │ +212660... │
              └──────────┘          └──────────┘          └────────────┘
                                           │
                                           ▼
                                    ┌─────────────┐
                                    │    Odoo     │
                                    │ intellixcrm │
                                    └─────────────┘
```

---

## Dépannage

| Symptôme | Cause probable | Action |
|----------|----------------|--------|
| AGI silencieux | `n8n_bridge.agi` non exécutable | `chmod +x` + owner asterisk |
| Pas de transcript | Deepgram key absente dans n8n | Vérifier variable env |
| WhatsApp 400 | Phone ID / token invalides | Meta Business → API Setup |
| Odoo 401 webhook | Mauvaise `X-Doorway-Key` | Sync avec `DOORWAY_AGENTS_WEBHOOK_KEY` |
| Voix anglaise | Mauvais `voice_id` | `FqF9IZCNgkSbGVwutMcg` + model multilingual |

---

## Évolution future (optionnel)

- Activer section `[doorway-trunk]` dans `sip_vicidial_n8n.conf` quand numéro France E164 disponible
- Brancher campagne VICIdial sortante sur CallerID France
- Ajouter codec `opus` si opérateur compatible

---

*Intellix — La suite IA pour centres d'appels performants | intellix.ai*
