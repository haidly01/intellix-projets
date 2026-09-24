# Déploiement — Sofia Soumission Entrepreneurs (Québec)

Environnement cible : **Odoo intellixcrm** @ 187.124.50.69, n8n @ n8n.intellixcrm.com, VICIdial port 8080.

## ÉTAPE 1 — ElevenLabs

1. Cloner la voix Sofia (5–10 min audio fr-CA clair)
2. Noter `ELEVENLABS_VOICE_ID`
3. Pré-générer les MP3 listés dans `lib/soumission_qc_config.js` → uploader sur  
   `https://intellixcrm.com/soumission-qc-tts/{nom}.mp3`

## ÉTAPE 2 — Deepgram

- Clé déjà dans `/etc/odoo-server.conf` → `DEEPGRAM_API_KEY`
- Test : POST `/api/renov/stt/deepgram` avec `language: fr-CA`

## ÉTAPE 3 — Claude (Anthropic)

- `ANTHROPIC_API_KEY` dans odoo-server.conf
- Prompt système : `system_prompt_claude.txt`
- Modèle conversation : `claude-3-5-haiku-20241022` (classif.) ou Sonnet pour répliques dynamiques

## ÉTAPE 4 — Téléphonie

**Option A — VICIdial (recommandé volume)**

- Campagne : `DW_QCB2C`, liste `SOUMISSION_QC`
- AGI → `POST https://n8n.intellixcrm.com/webhook/soumission-qc/event`
- Dial via Odoo : `/doorway/api/soumission-qc/dial`

**Option B — Twilio (test / faible volume)**

- `TELEPHONY_PROVIDER=twilio` dans n8n `.env`
- Numéro sortant : `+15817058118`

## ÉTAPE 5 — n8n

```bash
cd /odoo/custom/addons/renovation_conciergerie/n8n/soumission_qc
python3 sync_workflow_code.py
python3 import_soumission_qc_workflows.py
cd /opt/n8n && docker compose up -d --force-recreate n8n
```

Activer dans l'ordre : **06 → 05 → 04 → 03 → 02 → 01**

## ÉTAPE 6 — Odoo

```bash
sudo systemctl stop odoo-server
sudo -u odoo python3 /odoo/odoo-server/odoo-bin -c /etc/odoo-server.conf -d intellixcrm \
  -u doorway_agents_dashboard,doorway_vicidial_campaigns,doorway_credits --stop-after-init
sudo systemctl start odoo-server
```

Vérifier :
- Menu Agents → **Sofia · Soumission Entrepreneurs QC**
- Campagne **DW_QCB2C** liée à l'agent

## ÉTAPE 7 — Test E2E

1. Créer un contact test dans Odoo (tag « À appeler »)
2. `POST /webhook/soumission-qc/outbound` avec téléphone test +1
3. Vérifier : STT → étapes qualification → CRM mis à jour
4. Si qualifié : SMS Twilio + activité « Appel qualif » pour Karine

## ÉTAPE 8 — Production

- Écouter 10 premiers appels réels
- Ajuster `endpointing` Deepgram (300 ms) et débit ElevenLabs (1.05)
- Remplir hopper VICIdial `SOUMISSION_QC`
- Activer AMD sur campagne (`campaign_vdad_exten=8369`)

## API Odoo

| Route | Rôle |
|-------|------|
| `/doorway/api/soumission-qc/dial` | Lance appel sortant |
| `/doorway/api/soumission-qc/call-ended` | Log + qualification CRM |
| `/doorway/api/soumission-qc/qualified` | Tâche directeur + SMS |
| `/doorway/api/soumission-qc/non-qualified` | Tags locataire / DNC / relance 6 mois |
| `/doorway/api/soumission-qc/daily-stats` | Rapport quotidien |

Toutes les routes exigent `tenant_api_key` (`DOORWAY_TENANT_API_KEY`).
