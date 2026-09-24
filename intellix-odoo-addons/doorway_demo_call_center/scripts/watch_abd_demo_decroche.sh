#!/usr/bin/env bash
# Surveille ABD_DEMO : liste valide, chaîne call_log → vicidial_log → Odoo, décrochés.
set -euo pipefail

MYSQL=(mysql -h127.0.0.1 -P3307 -uvicidial -pa42246a8306dc369d33525c4cea6fef1 asterisk -Nse)
CAMPAIGN=ABD_DEMO
LIST_ID=1011
ODOO_CAMPAIGN_ID=18
INTERVAL="${1:-60}"
RUNS="${2:-0}"

log() { echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*"; }

check_list() {
  local total invalid
  total=$("${MYSQL[@]}" "SELECT COUNT(*) FROM vicidial_list WHERE list_id=${LIST_ID}")
  invalid=$("${MYSQL[@]}" "SELECT COUNT(*) FROM vicidial_list WHERE list_id=${LIST_ID} AND phone_number NOT REGEXP '^[6789][0-9]{8}\$'")
  if [[ "$invalid" -gt 0 ]]; then
    log "LISTE: ${invalid}/${total} invalides — nettoyage..."
    python3 /odoo/custom/addons/doorway_demo_call_center/scripts/cleanup_abd_demo_phones.py
  else
    log "LISTE: ${total} numéros valides (0 invalide)"
  fi
}

check_vicidial() {
  local call_log open_calls na human autodial
  call_log=$("${MYSQL[@]}" "SELECT COUNT(*) FROM call_log")
  open_calls=$("${MYSQL[@]}" "SELECT COUNT(*) FROM call_log WHERE end_time IS NULL")
  na=$("${MYSQL[@]}" "SELECT COUNT(*) FROM vicidial_log WHERE campaign_id='${CAMPAIGN}' AND call_date>=CURDATE() AND status='NA'")
  human=$("${MYSQL[@]}" "SELECT COUNT(*) FROM vicidial_log WHERE campaign_id='${CAMPAIGN}' AND call_date>=CURDATE() AND status IN ('A','SALE','PU','PM','XFER','HUMAN')")
  autodial=$("${MYSQL[@]}" "SELECT COUNT(*) FROM vicidial_auto_calls WHERE campaign_id='${CAMPAIGN}' AND status='SENT'")
  log "VICIDIAL: call_log=${call_log} (ouverts=${open_calls}) NA=${na} DÉCROCHÉ=${human} SENT=${autodial}"
  if [[ "$open_calls" -gt 50 ]]; then
    log "ALERTE: call_log ouverts élevés — vérifier FastAGI_log.pl"
  fi
}

sync_odoo() {
  sudo -u odoo python3 /odoo/odoo-server/odoo-bin shell -c /etc/odoo-server.conf -d intellixcrm --no-http <<PYEOF
from odoo.addons.doorway_vicidial_campaigns.services.vicidial_service import VicidialService
campaign = env['doorway.campaign'].browse(${ODOO_CAMPAIGN_ID})
svc = VicidialService(env)
result = svc.sync_call_logs(campaign, limit=500)
breakdown = svc.get_call_breakdown(campaign, days=1)
total = env['doorway.call.log'].search_count([('campaign_id','=',${ODOO_CAMPAIGN_ID})])
human = env['doorway.call.log'].search_count([('campaign_id','=',${ODOO_CAMPAIGN_ID}), ('amd_result','=','human')])
print(f"ODOO sync={result} logs={total} human={human} breakdown={breakdown}")
PYEOF
}

check_daemons() {
  local missing=0
  for pat in "AST_VDauto_dial.pl" "AST_VDremote_agents.pl" "FastAGI_log.pl"; do
    if ! pgrep -f "$pat" >/dev/null 2>&1; then
      log "ALERTE: $pat arrêté"
      missing=1
    fi
  done
  if [[ "$missing" -eq 1 ]]; then
    log "Relance stack auto-dial..."
    bash /odoo/custom/addons/doorway_demo_call_center/scripts/start_abd_demo_autodial.sh
  fi
}

iteration=0
while true; do
  iteration=$((iteration + 1))
  log "--- cycle ${iteration} ---"
  check_daemons
  check_list
  check_vicidial
  sync_odoo
  if [[ "$RUNS" -gt 0 && "$iteration" -ge "$RUNS" ]]; then
    log "Fin surveillance (${RUNS} cycles)"
    break
  fi
  sleep "$INTERVAL"
done
