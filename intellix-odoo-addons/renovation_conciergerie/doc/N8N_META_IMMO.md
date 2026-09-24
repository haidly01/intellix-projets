# Qualification immobilier Meta Ads — Guide complet

## 1. Page Facebook — Maison Recherchée

- **ID page** : `964640820063787` (paramètre Odoo `renovation_conciergerie.meta_immo_facebook_page_id`)
- **Veille sociale** garde la page **Haidly** (`574384345749047`) pour FB/IG veille — ne pas confondre.
- Paramètres Odoo → **Meta Ads — Qualification immobilier** → **Tester page Meta immo**

## 2. Publicité Meta — ID `120245070455390396` (formulaire 19 mai)

- Cet **ID publicité n’est pas enregistré en dur** dans Odoo : il arrive avec chaque lead Meta via le champ `ad_id` du webhook.
- Odoo stocke alors **`immo_meta_ad_id`** et **`immo_meta_form_id`** sur la fiche CRM (onglet Qualification IA).
- Pour **vérifier dans Meta** : token page dans **Veille sociale → Connexions** (actuellement **expiré** — régénérer dans Meta for Developers puis **Tester Meta** dans Odoo).
- Côté **n8n** : l’orchestrateur transmet `ad_id`, `form_id`, `meta_lead_id` vers `POST /api/immo/meta-lead`.
- **Déclencheur n8n (recommandé)** : nœud natif **Facebook Lead Ads** en tête du workflow `workflow_meta_immo_orchestrator.json` — vous connectez la **Page** et le **Formulaire** dans l’UI (plus de webhook manuel Meta pour l’immo).
- **Legacy** : webhook générique `meta-immo-lead` retiré de l’orchestrateur ; réservé aux tests `curl` ou intégrations tierces.

## 1b. Facebook Lead Ads — credential n8n

| Étape | Action |
|-------|--------|
| 1 | [Meta for Developers](https://developers.facebook.com/) → créer une app → mode **Live** |
| 2 | Ajouter **Facebook Login for Business** + accès avancé `leads_retrieval`, `pages_manage_metadata`, `pages_read_engagement` |
| 3 | n8n → Credentials → **Facebook Lead Ads OAuth2 API** (Client ID = App ID, Client Secret = App Secret) |
| 4 | Workflow **Immo Meta — Orchestrateur** → nœud **1 Facebook Lead Ads** → credential + **Form** (liste) |
| 5 | **Publish** le workflow |

**Page pré-configurée** : `964640820063787` (Maison Recherchée).  
**Test** : [Lead Ads Testing Tool](https://developers.facebook.com/tools/lead-ads-testing/) → Create lead → exécution visible dans n8n.

**Important** : Meta autorise **un seul webhook par app**. Si vous activez aussi un trigger Facebook sur **Énergie Pro** avec la **même** app, le dernier workflow publié écrase l’autre. Solutions :

- **Énergie** : garder le webhook `energie-lead` (config Leadgen dans Meta vers cette URL), ou
- Créer une **2e app Meta** dédiée Énergie Pro, ou
- Un workflow **routeur** unique (trigger Facebook + Switch sur `page_id`).

## 2. Tokens et URLs Odoo

| Élément | Valeur |
|---------|--------|
| Création lead | `POST https://intellixcrm.com/api/immo/meta-lead` |
| Update lead | `POST https://intellixcrm.com/api/immo/lead/update` |
| Header | `X-Immo-Webhook-Token` |
| Token | Paramètres → Meta Ads — Qualification immobilier → **Régénérer** si besoin |

## 2. Relances J+1…J+14 (Addendum 2)

Voir **`doc/IMMO_RELANCE_N8N.md`** — 4 agents ElevenLabs, SMS/WA, workflow `workflow_immo_relance_orchestrator.json`.

Bouton Odoo : **Setup relances J+1…J+14** sur la fiche Maison Recherchée.

## 3. ElevenLabs — Setup voix + agent qualification

1. Copier `Rue_Ibnou_Jahir_3.m4a` dans  
   `/odoo/custom/addons/doorway_agents_dashboard/voice_samples/`
2. Clé API : Paramètres Odoo ou `ELEVENLABS_API_KEY` dans `/etc/odoo-server.conf`
3. Odoo : **Agents IA → Maison Recherchée → Setup ElevenLabs (Sophie)**
4. Renseigner `external_agent_id` et `voice_clone_id` automatiquement

CLI alternative :

```bash
export ELEVENLABS_API_KEY=sk_...
python3 /odoo/custom/addons/doorway_agents_dashboard/scripts/setup_elevenlabs_maison_immo.py
```

## 3. n8n — Node 6 (appel sortant)

```json
POST https://api.elevenlabs.io/v1/convai/twilio/outbound-call
{
  "agent_id": "{{ $json.agent_id }}",
  "to_number": "+15145551234",
  "from_number": "+14387905970",
  "conversation_initiation_client_data": {
    "dynamic_variables": {
      "lead_name": "Jean",
      "property_address": "123 rue Principale, Laval",
      "selling_timeline": "0-3 mois",
      "lead_id_odoo": "456"
    }
  }
}
```

## 4. n8n — Post-call → Odoo

Webhook ElevenLabs : `https://doorway.app.n8n.cloud/webhook/elevenlabs-immo-postcall`  
Puis Claude scoring → `POST /api/immo/lead/update` avec `score`, `transcript`, `data_collection`.

## 5. Twilio

- SIP Trunk : `TK4005d66df6aefef66f0a63a711491166`
- From : `+14387905970`
- Transfert : `+14389929200`

## 6. Pipeline Odoo

- Équipe : **Rénovation** (configurable via `renovation_conciergerie.meta_immo_team_xmlid`)
- Tags : `immo-eval-marchande`, `meta-ads-immo`, `score-hot/warm/cold`
- Agent : **Maison Recherchée** (volet `qualification`)
