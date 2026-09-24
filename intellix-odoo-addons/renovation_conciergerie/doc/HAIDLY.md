# Haidly — Concierge rénovation (SoumissionEntrepreneurs.com)

## Identité

| Paramètre | Valeur |
|-----------|--------|
| Téléphone / SMS / WhatsApp | `+15817058118` |
| SIP Trunk Twilio | `TK3d6c7ea376c52bca4e8e81c3b10db400` |
| Transfert humain | `+14389929200` |
| Upload photos | https://soumissionentrepreneurs.com/ |
| Pipeline Odoo | Rénovation |

> La page Facebook « Haidly » (Veille sociale) est distincte de cet agent vocal SoumissionEntrepreneurs.

## Agents ElevenLabs (Odoo)

1. **J+0** — `agent_haidly` — qualification initiale (2–3 min)
2. **J+1** — photos / plans 3D
3. **J+3** — angle subventions
4. **J+7** — fermeture dossier
5. **J+14** — re-engagement consultatif

### Setup dans Odoo

1. **Agents IA** → **Haidly · J+0 Qualification**
2. Joindre un échantillon voix femme FR-CA (ou coller `elevenlabs_voice_id_haidly` / réutiliser Sophie)
3. **Setup ElevenLabs (Haidly)** puis **Setup relances J+1…J+14**

Paramètres ICP créés :

- `doorway_agents_dashboard.elevenlabs_agent_id_haidly`
- `doorway_agents_dashboard.elevenlabs_agent_id_haidly_j1` … `_j14`
- `doorway_agents_dashboard.elevenlabs_phone_number_id_haidly`

Voix : `stability` 0.42, `style` 0.30 (plus expressif que Alex/Sophie).

## API Odoo (n8n)

| Route | Méthode | Header |
|-------|---------|--------|
| `/api/haidly/lead` | POST | `X-Haidly-Webhook-Token` |
| `/api/haidly/lead/update` | POST | idem |
| `/api/haidly/lead/<id>` | GET | idem |

Token : **Paramètres** → **Twilio / Webhooks** → bloc **Haidly — SoumissionEntrepreneurs**.

Réponse `POST /api/haidly/lead` :

```json
{
  "lead_id": 123,
  "elevenlabs_agent_id_haidly": "...",
  "elevenlabs_phone_number_id": "...",
  "from_number": "+15817058118",
  "sip_trunk_sid": "TK3d6c7ea376c52bca4e8e81c3b10db400",
  "transfer_number": "+14389929200",
  "upload_url": "https://soumissionentrepreneurs.com/",
  "relance_agents": { "j1": "...", "j3": "...", "j7": "...", "j14": "..." }
}
```

## n8n (import automatique)

```bash
python3 /odoo/custom/addons/renovation_conciergerie/n8n/import_doorway_workflows.py
```

| Workflow | Webhook path | URL production |
|----------|--------------|----------------|
| Orchestrateur lead | `haidly-lead` | https://n8n.intellixcrm.com/webhook/haidly-lead |
| Post-appel ElevenLabs | `haidly-postcall` | https://n8n.intellixcrm.com/webhook/haidly-postcall |
| Relance unitaire | `haidly-relance-step` | https://n8n.intellixcrm.com/webhook/haidly-relance-step |
| Nurture J+1→J+14 | `haidly-nurture-start` | https://n8n.intellixcrm.com/webhook/haidly-nurture-start |

- Heures ouvrées : Lun–Sam 9h–19h (America/Toronto)
- Post-call → Claude scoring → `/api/haidly/lead/update` + SMS photos + nurture

## ElevenLabs post-call (configuré)

Webhook workspace EL → `https://n8n.intellixcrm.com/webhook/haidly-postcall` (événement `transcript`).

ID webhook stocké : `renovation_conciergerie.elevenlabs_haidly_postcall_webhook_id`

Variables d'environnement suggérées :

```env
ELEVENLABS_AGENT_ID_HAIDLY_INIT=
ELEVENLABS_PHONE_NUMBER_ID_HAIDLY=
TWILIO_FROM_HAIDLY=+15817058118
SOUMISSION_UPLOAD_URL=https://soumissionentrepreneurs.com/
```

## Séquence nurture (référence)

| Timing | Canal |
|--------|-------|
| T+0 | SMS + WhatsApp bienvenue + lien photos |
| T+2–5 min | Appel Haidly J+0 (si heures ouvrées) |
| J+1 16h | Appel J+1 |
| J+3 10h | Appel J+3 |
| J+7 16h | Appel J+7 |
| J+14 10h | Appel J+14 |
| J+30 | Archivage Odoo |

Stages CRM : hot → **Qualification**, warm → **Relance**, cold → **Nouveau**.

## Upgrade modules

```bash
sudo -u odoo python3 /odoo/odoo-server/odoo-bin -c /etc/odoo-server.conf -d intellixcrm \
  -u doorway_agents_dashboard,renovation_conciergerie --stop-after-init
sudo systemctl restart odoo-server
```
