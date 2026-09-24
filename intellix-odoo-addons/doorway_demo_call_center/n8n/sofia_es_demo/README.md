# Sofia Espagne — workflows n8n DEMO (Abdallah)

Clone isolé des workflows production `sofia_es`, facturation sur le tenant demo Abdallah.

## Webhooks

| Workflow | URL |
|----------|-----|
| Outbound | `POST /webhook/sofia-es-demo/outbound` |
| VICIdial AGI | `POST /webhook/sofia-es-demo/vicidial/event` |
| Conversation | `POST /webhook/sofia-es-demo/conversation` |
| Google Sheets | `POST /webhook/sofia-es-demo/sheets` |

## Variables n8n (`/opt/n8n/.env`)

- `DOORWAY_DEMO_TENANT_API_KEY` — clé API tenant Abdallah
- `VICIDIAL_DEMO_CAMPAIGN=ABD_DEMO`
- `DEMO_AGENT_ID=sofia-es-demo-abdallah`
- `GOOGLE_SHEETS_TAB_DEMO=Leads_Sofia_Demo_Abdallah`

## Déploiement

```bash
cd /odoo/custom/addons/doorway_demo_call_center/n8n/sofia_es_demo
python3 sync_workflow_code.py
python3 import_sofia_es_demo_workflows.py
```

## Test E2E

```bash
DOORWAY_TENANT_API_KEY=<clé Abdallah> bash \
  /odoo/custom/addons/doorway_demo_call_center/scripts/test_sofia_abd_demo_e2e.sh
```

L'AGI demo (`abd-demo-bridge` / `86011`) pointe vers `/webhook/sofia-es-demo/vicidial/event`.
