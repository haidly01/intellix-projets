# Alex — Qualification Driven B2B PME QC

Agent outbound B2B Québec pour préqualification financement Driven (10K$–500K$).  
Architecture clonée de **Léa QC** — campagne **séparée** (`DW_QCB2B`), sans impact sur `DW_QCB2C`.

## Identifiants production

| Élément | Valeur |
|---------|--------|
| Campagne VICIdial | `DW_QCB2B` |
| Extension remote agent | `86023` |
| Agent ID | `driven-b2b-qc-2026` |
| AGI Asterisk | `/var/lib/asterisk/agi-bin/n8n_driven_b2b.agi` |
| TTS nginx | `https://intellixcrm.com/driven-b2b-tts/` |
| Greeting ulaw (pre-cache) | `/tmp/greeting_ALEX.ulaw` |

## Workflows n8n

| # | Nom |
|---|-----|
| 01 | `driven-b2b-qc — 01 Outbound` |
| 02 | `driven-b2b-qc — 02 Telephony Events` |
| 03 | `driven-b2b-qc — 03 Conversation Engine` |
| 04 | `driven-b2b-qc — 04 Lead Chaud Driven` |
| 05 | `driven-b2b-qc — 05 Lead Non Qualifié` |
| 06 | `driven-b2b-qc — 06 Stats Quotidiennes` |

Webhooks : `/webhook/driven-b2b-qc/{outbound,event,conversation,qualified,non-qualified,stats}`

## Arbre de qualification

1. **Accroche** — intérêt financement ?
2. **Q1** — ancienneté ≥ 6 mois
3. **Q2** — revenus ≥ 100 000 $/an
4. **Q3** — compte bancaire entreprise → **lead chaud** + SMS immédiat

## SMS (fail-open)

| Jour | Message |
|------|---------|
| J+0 | Lien `driven.ca/partners/agence-doorway` (workflow qualified + Twilio) |
| J+2 | « Avez-vous eu la chance de vérifier ? » (cron Odoo `driven.b2b.sms.queue`) |
| J+5 | Relance finale 50K$–200K$ |

## Checklist lancement LUNDI

### Avant 9h — vérifications

```bash
# Dialer OFF (doit afficher 0)
mysql asterisk -N -e "SELECT auto_dial_level FROM vicidial_campaigns WHERE campaign_id='DW_QCB2B';"

# Remote agent actif
mysql asterisk -N -e "SELECT conf_exten,status FROM vicidial_remote_agents WHERE campaign_id='DW_QCB2B';"

# TTS accessible
curl -I https://intellixcrm.com/driven-b2b-tts/alex_ouverture.mp3

# n8n conversation (doit retourner play_audio + URL alex_ouverture)
curl -s -X POST http://127.0.0.1:5678/webhook/driven-b2b-qc/conversation \
  -H 'Content-Type: application/json' \
  -d '{"event_type":"call_start","call_sid":"test-lundi","to":"15145551234"}'
```

### Import liste contacts (MANUEL)

1. Préparer CSV : `phone`, `first_name`, `last_name`
2. Odoo → Campagnes VICIdial → **Québec B2B — Driven Alex** → Importer contacts  
   **OU** API VICIdial liste `DW_QCB2B`

### Test appel unique (sans auto-dial)

```bash
asterisk -rx "channel originate SIP/Door_App0/1XXXXXXXXXX extension 86023@driven-b2b-qc-bridge"
```

### Démarrer la campagne (après validation Martin)

```bash
/odoo/custom/addons/doorway_vicidial_campaigns/scripts/start_driven_b2b_autodial.sh 1.0
```

`auto_dial_level=0` tant que la liste n'est pas validée.

## Maintenance / déploiement code

```bash
cd /odoo/custom/addons/renovation_conciergerie/n8n/driven_b2b_qc

# Regénérer TTS (voix via ELEVENLABS_VOICE_ID_ALEX dans /etc/odoo-server.conf)
python3 generate_driven_b2b_tts.py

# Sync JS → workflows JSON
python3 sync_workflow_code.py

# Publier dans n8n (préféré si API 401)
python3 fix_n8n_publish.py

# Upgrade Odoo (routes API + cron SMS)
sudo -u odoo /odoo/odoo-server/odoo-bin -c /etc/odoo-server.conf -d intellixcrm \
  -u doorway_agents_dashboard,doorway_credits --stop-after-init --no-http
sudo systemctl restart odoo
```

## API Odoo

- `POST /doorway/api/driven-b2b/call-ended`
- `POST /doorway/api/driven-b2b/dial`
- `POST /doorway/api/driven-b2b/qualified`
- `POST /doorway/api/driven-b2b/non-qualified`
- `POST /doorway/api/driven-b2b/daily-stats`

Tags CRM : **Driven B2B**, **Lead chaud Driven**

## Encore manuel

- [ ] **Import liste** PME Québec dans VICIdial (`DW_QCB2B`)
- [ ] **Voix Alex** — clips générés avec voix Léa (`tiVm574z…`) ; définir `ELEVENLABS_VOICE_ID_ALEX` (voix homme) et regénérer TTS
- [ ] **Approbation Martin** avant `start_driven_b2b_autodial.sh`
- [ ] Vérifier cron SMS actif : Paramètres → Technique → Actions planifiées → « Alex Driven B2B — relances SMS »

## Backups créés (2026-06-13)

- `/etc/asterisk/extensions_qc_ia.conf.bak.*`
- `/etc/nginx/sites-available/odoo.bak.*`
- `vicidial_service.py.bak.*`

## Séparation Léa QC

- Léa : `DW_QCB2C` / ext `86013` / webhooks `lea-qc/*` — **non modifié**
- Alex : `DW_QCB2B` / ext `86023` / webhooks `driven-b2b-qc/*`
