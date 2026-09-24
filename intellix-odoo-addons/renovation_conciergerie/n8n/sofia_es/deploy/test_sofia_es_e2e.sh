#!/usr/bin/env bash
# Test bout en bout Sofia Espagne (VICIdial + n8n + Odoo)
set -euo pipefail

N8N="${N8N_WEBHOOK_URL:-https://n8n.intellixcrm.com/webhook}"
ODOO="${ODOO_URL:-https://intellixcrm.com}"
KEY="${DOORWAY_TENANT_API_KEY:-ejT3G-w38dJqjHFRrauVd0ZWA1nDOnwDaqndWxQBfuc}"
TEST_PHONE="${TEST_PHONE:-212674579467}"
CALL_SID="e2e-sofia-$(date +%s)"

pass=0
fail=0
ok() { echo "  OK  $1"; pass=$((pass+1)); }
ko() { echo "  FAIL $1"; fail=$((fail+1)); }

echo "=== Sofia ES E2E — $(date -Iseconds) ==="

echo "[1] Webhook conversation (amd machine → hangup)"
r=$(curl -sS -X POST "$N8N/sofia-es/conversation" \
  -H "Content-Type: application/json" \
  -d "{\"event_type\":\"amd_result\",\"amd_result\":\"machine\",\"call_sid\":\"$CALL_SID-amd\",\"to\":\"+34$TEST_PHONE\",\"provider\":\"vicidial\"}")
echo "$r" | grep -q '"action":"hangup"\|"action": "hangup"' && ok "conversation amd" || ko "conversation amd ($r)"

echo "[2] Webhook sheets"
r=$(curl -sS -X POST "$N8N/sofia-es/sheets" \
  -H "Content-Type: application/json" \
  -d "{\"nombre\":\"Test E2E\",\"telefono\":\"+34$TEST_PHONE\",\"statut\":\"test\",\"amd_result\":\"human\",\"duree_sec\":45,\"qualified\":false,\"call_sid\":\"$CALL_SID\"}")
echo "$r" | grep -q '"ok":true\|"ok": true\|"message":"Workflow was started"' && ok "google sheets" || ko "google sheets ($r)"

echo "[3] Odoo call-ended (facturation 45s human)"
r=$(curl -sS -X POST "$ODOO/doorway/api/sofia-es/call-ended" \
  -H "Content-Type: application/json" \
  -d "{\"jsonrpc\":\"2.0\",\"method\":\"call\",\"id\":1,\"params\":{\"tenant_api_key\":\"$KEY\",\"call_sid\":\"$CALL_SID\",\"duration_seconds\":45,\"amd_result\":\"human\",\"nombre\":\"Test E2E\",\"telephone\":\"+34$TEST_PHONE\",\"campaign\":\"sofia_es_avatrade\",\"etat_final\":\"test\"}}")
echo "$r" | grep -q '"success":true\|"success": true' && ok "odoo billing" || ko "odoo billing ($r)"

echo "[4] Odoo AMD not billed"
r=$(curl -sS -X POST "$ODOO/doorway/api/sofia-es/call-ended" \
  -H "Content-Type: application/json" \
  -d "{\"jsonrpc\":\"2.0\",\"method\":\"call\",\"id\":2,\"params\":{\"tenant_api_key\":\"$KEY\",\"call_sid\":\"$CALL_SID-amd2\",\"duration_seconds\":30,\"amd_result\":\"machine\",\"campaign\":\"sofia_es_avatrade\"}}")
echo "$r" | grep -q '"success":true\|"success": true' && echo "$r" | grep -q '"billed":false\|"billed": false' && ok "odoo amd zero" || ko "odoo amd ($r)"

echo "[5] VICIdial events → conversation"
r=$(curl -sS -X POST "$N8N/sofia-es/vicidial/event" \
  -H "Content-Type: application/json" \
  -d "{\"event_type\":\"call_ended\",\"call_sid\":\"$CALL_SID-end\",\"phone_number\":\"+34$TEST_PHONE\",\"duration_sec\":10,\"amd_result\":\"human\"}")
echo "$r" | grep -q 'action\|engine\|normalized\|call_sid' && ok "vicidial event" || ko "vicidial event ($r)"

echo "[6] Outbound n8n → VICIdial external_dial"
r=$(curl -sS -X POST "$N8N/sofia-es/outbound" \
  -H "Content-Type: application/json" \
  -d "{\"telephone\":\"+$TEST_PHONE\",\"nombre\":\"Test E2E\",\"partner_id\":1}")
echo "$r" | grep -q '"ok":true\|"ok": true' && ok "outbound vicidial" || ko "outbound ($r)"

echo "[7] VICIdial API version"
r=$(curl -sS "http://127.0.0.1:8080/vicidial/non_agent_api.php?source=doorway_odoo&user=doorway&pass=DoorwayAdmin2026&function=version")
echo "$r" | grep -q "VERSION" && ok "vicidial api" || ko "vicidial api ($r)"

echo "[8] Campagne DW_ESREN active + hopper"
cnt=$(mysql -h127.0.0.1 -P3307 -uvicidial -pa42246a8306dc369d33525c4cea6fef1 asterisk -Nse \
  "SELECT CONCAT(active,'|',(SELECT COUNT(*) FROM vicidial_hopper WHERE campaign_id='DW_ESREN')) FROM vicidial_campaigns WHERE campaign_id='DW_ESREN';")
active="${cnt%%|*}"; hopper="${cnt##*|}"
[[ "$active" == "Y" && "$hopper" -gt 0 ]] && ok "campaign active hopper=$hopper" || ko "campaign ($cnt)"

echo "[9] AGI binaire présent"
[[ -x /var/lib/asterisk/agi-bin/n8n_sofia_es.agi ]] && ok "agi installed" || ko "agi missing"

echo "[10] Appel live TrustSIP → $TEST_PHONE (originate)"
if asterisk -rx "channel originate Local/${TEST_PHONE}@sofia-es-outbound application Wait 1" 2>/dev/null; then
  ok "originate lancé"
else
  ko "originate failed"
fi

echo ""
echo "Résultat: $pass OK / $((pass+fail)) — échecs: $fail"
exit $fail
