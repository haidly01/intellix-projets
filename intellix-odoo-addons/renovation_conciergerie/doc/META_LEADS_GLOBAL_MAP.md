# Mapping global Meta Lead Ads

Une **seule app Meta** + **un hub n8n** (`meta-leads-hub`) pour toutes les pages / formulaires.

## Architecture

```
Meta (10 pages × 1 form) → webhook Leadgen → n8n meta-leads-hub
        → POST /api/meta/leads/resolve (Odoo)
        → meta-immo-lead | energie-lead | haidly-lead
        → Odoo create lead + agent IA (round-robin si configuré)
```

## Tableau initial (informations déjà connues)

| page_id | Nom | Pipeline | Webhook n8n | Site / notes |
|---------|-----|----------|-------------|--------------|
| `964640820063787` | Maison Recherchée | **immo** | `meta-immo-lead` | Form `1016997697520697` → pipeline **Réno** + agent `agent_maison_recherchee` |
| `962295250303049` | ICI Thermopompe | **energie** | `energie-lead` | Form `1912811406106600` → `icithermopompe` + agent `agent_energie_pro` |
| `1004010452788312` | Énergie Pro | **energie** | `energie-lead` | Général |
| `574384345749047` | Haidly Reno | **haidly** | `haidly-lead` | Form `1177919251120913` → agent `agent_haidly` |
| `499982889862307` | Agence Doorway | **marketing** | *(direct Odoo)* | Form `1002390528799358` → Zakaria, colonne **Nouveau**, sans agent IA |
| *(à renseigner)* | Isolation QC | **energie** | `energie-lead` | Fallback `site=isolationqc` |
| *(à renseigner)* | Portes & Fenêtres QC | **energie** | `energie-lead` | Fallback `site=portesetfenetresqc` |
| — | SoumissionEntrepreneurs | **haidly** | `haidly-lead` | Formulaire web (pas page Meta) |

Complétez les `page_id` manquants dans **Paramètres → Agents IA → Hub global Meta** (JSON).

## Formulaires Meta (form_id)

Meta envoie `form_id` avec ou sans préfixe `f:` (ex. `f:1016997697520697`). Odoo normalise automatiquement.

| form_id | Page | Pipeline CRM | Agent IA |
|---------|------|--------------|----------|
| `1016997697520697` | Maison Recherchée | Rénovation (`crm_team_renovation`) via immo | `doorway_agents_dashboard.agent_maison_recherchee` |
| `1912811406106600` | ICI Thermopompe | Énergie (`crm_team_renovation` + tags site) | `doorway_agents_dashboard.agent_energie_pro` |
| `1177919251120913` | Haidly Reno (`574384345749047`) | Haidly (`haidly-lead` → `crm_team_renovation`) | `doorway_agents_dashboard.agent_haidly` |
| `1002390528799358` | Agence Doorway (`499982889862307`) | Marketing (`crm_team_marketing`) | — (Zakaria, `POST /api/marketing/meta-lead`) |

## 3 agents sur le même formulaire

Dans le JSON, section `forms` :

```json
"forms": {
  "VOTRE_FORM_ID": {
    "agent_assignment": "round_robin",
    "agent_profile_xmlids": [
      "doorway_agents_dashboard.agent_energie_pro",
      "doorway_agents_dashboard.agent_energie_pro_2",
      "doorway_agents_dashboard.agent_energie_pro_3"
    ]
  }
}
```

Ou au niveau **page** avec `agent_assignment: "round_robin"` et la liste des xmlids.

Odoo incrémente un compteur ICP `meta_leads_rr_{form_id}` à chaque lead.

## Paramètres Odoo (ICP)

| Clé | Usage |
|-----|--------|
| `renovation_conciergerie.meta_leads_global_page_map` | JSON complet |
| `renovation_conciergerie.meta_leads_hub_webhook_url` | URL hub n8n |
| `renovation_conciergerie.meta_leads_routing_token` | Header `X-Meta-Leads-Token` |

## API

```bash
curl -X POST https://intellixcrm.com/api/meta/leads/resolve \
  -H "Content-Type: application/json" \
  -H "X-Meta-Leads-Token: VOTRE_TOKEN" \
  -d '{"page_id":"962295250303049","form_id":"123","first_name":"Test"}'
```

Réponse : `pipeline`, `n8n_webhook`, `skip_orchestrator`, `site`, etc.

## Meta for Developers

1. **Une** app Meta (mode Live).
2. Webhook Leadgen → `https://n8n.intellixcrm.com/webhook/meta-leads-hub`
3. Abonner **chaque page** Lead Ads à l’app (install app on page).
4. Ne pas activer plusieurs workflows n8n avec **Facebook Lead Ads Trigger** sur la même app.

## Import n8n

```bash
python3 /odoo/custom/addons/renovation_conciergerie/n8n/import_doorway_workflows.py workflow_meta_leads_hub.json
```
