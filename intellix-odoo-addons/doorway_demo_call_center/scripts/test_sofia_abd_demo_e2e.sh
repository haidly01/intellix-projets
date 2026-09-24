#!/usr/bin/env bash
# Test bout en bout Sofia Espagne — environnement demo Abdallah (ABD_DEMO)
set -euo pipefail

N8N_BASE="${N8N_WEBHOOK_URL:-https://n8n.intellixcrm.com/webhook}"
N8N="${N8N_BASE%/}/sofia-es-demo"
ODOO="${ODOO_URL:-https://intellixcrm.com}"
KEY="${DOORWAY_TENANT_API_KEY:?DOORWAY_TENANT_API_KEY requis}"
TEST_PHONE="${TEST_PHONE:-34612345678}"
CALL_SID="e2e-abd-$(date +%s)"
CAMPAIGN="ABD_DEMO"
AGENT_ID="sofia-es-demo-abdallah"

pass=0
fail=0
ok() { echo "  OK  $1"; pass=$((pass+1)); }
ko() { echo "  FAIL $1"; fail=$((fail+1)); }

echo "=== Sofia ES Demo Abdallah E2E — $(date -Iseconds) ==="
echo "Campagne: $CAMPAIGN | Agent: $AGENT_ID"

echo "[1] Isolation Odoo — contacts demo"
cnt=$(sudo -u odoo python3 /odoo/odoo-server/odoo-bin shell -c /etc/odoo-server.conf -d intellixcrm --no-http <<'PY'
user = env['res.users'].sudo().search([('login','=','echcherkia65@gmail.com')], limit=1)
abd = user.with_user(user)
print(abd.env['res.partner'].search_count([]))
PY
)
[[ "$cnt" -ge 0 && "$cnt" -lt 50 ]] && ok "partners isolés ($cnt)" || ko "isolation partners ($cnt)"

echo "[2] Webhook conversation (AMD machine → hangup)"
r=$(curl -sS -X POST "$N8N/conversation" \
  -H "Content-Type: application/json" \
  -d "{\"event_type\":\"amd_result\",\"amd_result\":\"machine\",\"call_sid\":\"$CALL_SID-amd\",\"to\":\"+34$TEST_PHONE\",\"provider\":\"vicidial\",\"campaign\":\"$CAMPAIGN\",\"agent_id\":\"$AGENT_ID\"}")
echo "$r" | grep -q '"action":"hangup"\|"action": "hangup"' && ok "conversation amd" || ko "conversation amd ($r)"

echo "[3] Webhook sheets"
r=$(curl -sS -X POST "$N8N/sheets" \
  -H "Content-Type: application/json" \
  -d "{\"nombre\":\"Test Abdallah E2E\",\"telefono\":\"+34$TEST_PHONE\",\"statut\":\"test\",\"amd_result\":\"human\",\"duree_sec\":45,\"qualified\":false,\"call_sid\":\"$CALL_SID\",\"campaign\":\"$CAMPAIGN\"}")
echo "$r" | grep -q '"ok":true\|"ok": true\|"message":"Workflow was started"' && ok "google sheets" || ko "google sheets ($r)"

echo "[4] Odoo call-ended — facturation tenant Abdallah (45s human)"
bal_before=$(sudo -u odoo python3 /odoo/odoo-server/odoo-bin shell -c /etc/odoo-server.conf -d intellixcrm --no-http <<'PY'
t = env['doorway.tenant'].sudo().search([('company_id.name','ilike','Abdallah')], limit=1)
print(round(t.credit_balance, 4))
PY
)
r=$(curl -sS -X POST "$ODOO/doorway/api/sofia-es/call-ended" \
  -H "Content-Type: application/json" \
  -d "{\"jsonrpc\":\"2.0\",\"method\":\"call\",\"id\":1,\"params\":{\"tenant_api_key\":\"$KEY\",\"call_sid\":\"$CALL_SID\",\"duration_seconds\":45,\"amd_result\":\"human\",\"nombre\":\"Test Abdallah E2E\",\"telephone\":\"+34$TEST_PHONE\",\"campaign\":\"$CAMPAIGN\",\"partner_id\":0}}")
echo "$r" | grep -q '"success":true\|"success": true' && ok "odoo billing" || ko "odoo billing ($r)"
bal_after=$(sudo -u odoo python3 /odoo/odoo-server/odoo-bin shell -c /etc/odoo-server.conf -d intellixcrm --no-http <<'PY'
t = env['doorway.tenant'].sudo().search([('company_id.name','ilike','Abdallah')], limit=1)
print(round(t.credit_balance, 4))
PY
)
diff=$(python3 -c "print(round($bal_before - $bal_after, 4))")
[[ "$diff" != "0.0" && "$diff" != "0" ]] && ok "crédit débité ($bal_before → $bal_after, -$diff €)" || ko "crédit non débité ($bal_before → $bal_after)"

echo "[5] Odoo AMD non facturé"
r=$(curl -sS -X POST "$ODOO/doorway/api/sofia-es/call-ended" \
  -H "Content-Type: application/json" \
  -d "{\"jsonrpc\":\"2.0\",\"method\":\"call\",\"id\":2,\"params\":{\"tenant_api_key\":\"$KEY\",\"call_sid\":\"$CALL_SID-amd2\",\"duration_seconds\":30,\"amd_result\":\"machine\",\"campaign\":\"$CAMPAIGN\"}}")
echo "$r" | grep -q '"billed":false\|"billed": false' && ok "amd zero" || ko "amd ($r)"

echo "[6] VICIdial events → n8n"
r=$(curl -sS -X POST "$N8N/vicidial/event" \
  -H "Content-Type: application/json" \
  -d "{\"event_type\":\"call_ended\",\"call_sid\":\"$CALL_SID-end\",\"phone_number\":\"+34$TEST_PHONE\",\"duration_sec\":10,\"amd_result\":\"human\",\"campaign\":\"$CAMPAIGN\",\"agent_id\":\"$AGENT_ID\"}")
echo "$r" | grep -q 'action\|engine\|normalized\|call_sid' && ok "vicidial event" || ko "vicidial event ($r)"

echo "[7] Outbound n8n → Odoo dial API"
r=$(curl -sS -X POST "$N8N/outbound" \
  -H "Content-Type: application/json" \
  -d "{\"telephone\":\"+$TEST_PHONE\",\"nombre\":\"Test Abdallah E2E\",\"partner_id\":1}")
echo "$r" | grep -q '"ok":true\|"ok": true' && ok "outbound" || ko "outbound ($r)"

echo "[8] Campagne ABD_DEMO active + hopper"
cnt=$(mysql -h127.0.0.1 -P3307 -uvicidial -pa42246a8306dc369d33525c4cea6fef1 asterisk -Nse \
  "SELECT CONCAT(active,'|',campaign_cid,'|',(SELECT COUNT(*) FROM vicidial_hopper WHERE campaign_id='ABD_DEMO')) FROM vicidial_campaigns WHERE campaign_id='ABD_DEMO';")
active="${cnt%%|*}"; rest="${cnt#*|}"; cid="${rest%%|*}"; hopper="${rest##*|}"
[[ "$active" == "Y" && "$cid" == "TrustSIP" && "$hopper" -gt 0 ]] && ok "ABD_DEMO active hopper=$hopper cid=$cid" || ko "campaign ($cnt)"

echo "[9] AGI + dialplan demo 86011"
[[ -x /var/lib/asterisk/agi-bin/n8n_sofia_es.agi ]] && asterisk -rx "dialplan show abd-demo-bridge" 2>/dev/null | grep -q 86011 && ok "agi+dialplan demo" || ko "agi/dialplan"

echo "[10] Originate TrustSIP (test téléphonie)"
if asterisk -rx "channel originate Local/${TEST_PHONE}@sofia-es-outbound application Wait 1" 2>/dev/null; then
  ok "originate lancé"
else
  ko "originate failed"
fi

echo ""
echo "Résultat: $pass OK / $((pass+fail)) — échecs: $fail"
exit $fail
