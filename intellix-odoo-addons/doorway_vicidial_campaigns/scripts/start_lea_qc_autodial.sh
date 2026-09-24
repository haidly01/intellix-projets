#!/usr/bin/env bash
# Lance Léa IA sur DW_QCB2C — progressive RATIO, hopper Estrie, pause Zakaria.
set -euo pipefail

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
MCNF="/opt/intellix-mcp/mysql-vicidial.cnf"
MYSQL=(mysql --defaults-extra-file="$MCNF" asterisk --connect-timeout=5)
LOG_DIR=/var/log/astguiclient
CAMPAIGN="DW_QCB2C"
LEA_EXT="86013"

start_screen() {
  local screen_name="$1" pattern="$2" cmd="$3"
  if pgrep -f "$pattern" >/dev/null 2>&1; then
    echo "  $pattern déjà actif"
    return 0
  fi
  screen -d -m -S "$screen_name" $cmd
  sleep 2
  pgrep -f "$pattern" >/dev/null && echo "  $pattern démarré ($screen_name)" || { echo "  ERREUR: $pattern" >&2; return 1; }
}

echo "=== Léa QC — lancement DW_QCB2C ==="

# n8n workflows
python3 /odoo/custom/addons/renovation_conciergerie/n8n/lea_qc/import_lea_qc_workflows.py

# Hopper Estrie 200+
/opt/doorway/fill_lea_estrie_hopper.sh 200

# Remote agent Léa + pause Zakaria
"${MYSQL[@]}" <<SQL
UPDATE vicidial_remote_agents SET status='ACTIVE', number_of_lines=1, conf_exten='$LEA_EXT'
  WHERE campaign_id='$CAMPAIGN' AND user_start='$LEA_EXT';
INSERT INTO vicidial_remote_agents (user_start, number_of_lines, conf_exten, status, campaign_id, on_hook_agent, on_hook_ring_time)
  SELECT '$LEA_EXT', 1, '$LEA_EXT', 'ACTIVE', '$CAMPAIGN', 'N', 15
  FROM DUAL WHERE NOT EXISTS (
    SELECT 1 FROM vicidial_remote_agents WHERE campaign_id='$CAMPAIGN' AND user_start='$LEA_EXT'
  );
UPDATE vicidial_live_agents SET status='PAUSED', comments='AUTO-PAUSE: Léa IA lancement'
  WHERE user='zakaria' AND campaign_id='$CAMPAIGN' AND status IN ('READY','QUEUE','INCALL');
UPDATE vicidial_campaigns SET auto_dial_level=1.5, active='Y', dial_method='RATIO',
  cpd_amd_action='DISPO', campaign_vdad_exten='8369', campaign_cid='15817058118'
  WHERE campaign_id='$CAMPAIGN';
DELETE FROM vicidial_auto_calls WHERE campaign_id='$CAMPAIGN' AND status IN ('SENT','XFER')
  AND (uniqueid IS NULL OR uniqueid='') AND call_time < NOW()-INTERVAL 90 SECOND;
SQL

asterisk -rx "dialplan reload" >/dev/null 2>&1 || true

start_screen "ASTlisten" "AST_manager_listen_AMI2.pl" "/usr/bin/perl /usr/share/astguiclient/AST_manager_listen_AMI2.pl"
start_screen "ASTsend" "AST_manager_send.pl" "/usr/bin/perl /usr/share/astguiclient/AST_manager_send.pl"
start_screen "ASTVDremote" "AST_VDremote_agents.pl" "/usr/bin/perl /usr/share/astguiclient/AST_VDremote_agents.pl --debug"
start_screen "ASTVDauto" "AST_VDauto_dial.pl" "/usr/bin/perl /usr/share/astguiclient/AST_VDauto_dial.pl"
/usr/share/astguiclient/AST_VDhopper.pl --debug=0 >>"$LOG_DIR/hopper-run.log" 2>&1 || true

/opt/doorway/campaign_hotfix.sh

echo ""
echo "=== Statut ==="
"${MYSQL[@]}" -Nse "
SELECT CONCAT('campaign active=',active,' adl=',auto_dial_level,' hopper_target=',hopper_level,' cid=',campaign_cid)
  FROM vicidial_campaigns WHERE campaign_id='$CAMPAIGN';
SELECT CONCAT('hopper ready=',COUNT(*),' estrie=',SUM(list_id=1010)) FROM vicidial_hopper WHERE campaign_id='$CAMPAIGN' AND status='READY';
SELECT CONCAT('lea ',user,' ',status,' conf=',conf_exten) FROM vicidial_live_agents WHERE campaign_id='$CAMPAIGN' AND user='$LEA_EXT';
SELECT CONCAT('zakaria ',status) FROM vicidial_live_agents WHERE user='zakaria' AND campaign_id='$CAMPAIGN' LIMIT 1;
"
