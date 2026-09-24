# Énergie Pro (Alex) — Doorway

## Pages Facebook Lead Ads (Meta)

| ID page | Rôle |
|---------|------|
| `962295250303049` | **ICI Thermopompe** → site `icithermopompe` (formulaire Lead Ads janv. 2026) |
| `1004010452788312` | **Énergie Pro** (page générale) |

Paramètre Odoo : `renovation_conciergerie.energie_facebook_page_ids`  
Mapping optionnel (site par page) : `energie_facebook_page_map` (JSON) — Paramètres → **Énergie Pro**.

Webhook Meta Leadgen → n8n `energie-lead` doit inclure `page_id` (ou `facebook_page_id`).

## Odoo

| Élément | Détail |
|---------|--------|
| Agent J+0 | **Énergie Pro · J+0 Qualification** (`agent_energie_pro`) |
| Relances | J+1, J+3, J+7 |
| Pipeline CRM | Rénovation |
| Téléphone | +1 581 890-0456 |
| SIP Trunk | `TK36b2a72091465e309606d218a3af145d` |
| Transfert | +14389929200 |

**Setup ElevenLabs:** Agents IA → Énergie Pro · J+0 → **Setup ElevenLabs (Alex)**

Réutilise la voix Sophie (`elevenlabs_voice_id_sophie`) si pas de voix Alex dédiée.

## API n8n → Odoo

| Méthode | URL | Header |
|---------|-----|--------|
| POST | `/api/energie/lead` | `X-Energie-Webhook-Token` |
| POST | `/api/energie/lead/update` | idem |
| GET | `/api/energie/lead/<id>` | idem |

Token : Paramètres → **Énergie Pro — Leads web**

## Sites sources

- `icithermopompe` → thermopompe, LogisVert
- `isolationqc` → isolation, Rénoclimat
- `portesetfenetresqc` → portes/fenêtres, Rénoclimat 150$/ouverture

Champs CRM : onglet **Énergie Pro (IA)** sur la fiche lead.

## n8n

Fichiers dans `renovation_conciergerie/n8n/` :

- `workflow_energie_orchestrator.json` — webhook `energie-lead`
- `workflow_elevenlabs_energie_postcall.json` — webhook `elevenlabs-energie-postcall` (dédié, pas le workspace Haidly)

Webhook ElevenLabs workspace **Énergie Pro Post-Call n8n** → agents ConvAI via `platform_settings.workspace_overrides.webhooks.post_call_webhook_id` (assigné au **Setup ElevenLabs (Alex)** et à l’upgrade module).

ICP : `renovation_conciergerie.elevenlabs_energie_postcall_webhook_id`, `elevenlabs_energie_webhook_secret`, `energie_n8n_postcall_url`

Variables d'env : `ELEVENLABS_AGENT_ID_ENERGIE`, `_J1`, `_J3`, `_J7`, `TWILIO_FROM_ENERGIE=+15818900456`, `TWILIO_SIP_TRUNK_ENERGIE=TK36b2a72091465e309606d218a3af145d`

## ICP ElevenLabs

- `doorway_agents_dashboard.elevenlabs_agent_id_energie`
- `doorway_agents_dashboard.elevenlabs_agent_id_energie_j1` / `j3` / `j7`
- `doorway_agents_dashboard.elevenlabs_phone_number_id_energie`
