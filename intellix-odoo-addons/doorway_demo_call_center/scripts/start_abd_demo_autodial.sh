#!/usr/bin/env bash
# Active l'auto-dial VICIdial pour ABD_DEMO (demo Abdallah)
set -euo pipefail

MYSQL=(mysql -h127.0.0.1 -P3307 -uvicidial -pa42246a8306dc369d33525c4cea6fef1 asterisk)
LOG_DIR=/var/log/astguiclient

start_screen() {
  local screen_name="$1"
  local pattern="$2"
  local cmd="$3"
  if pgrep -f "$pattern" >/dev/null 2>&1; then
    echo "  $pattern déjà actif"
    return 0
  fi
  screen -d -m -S "$screen_name" $cmd
  sleep +2
  if pgrep -f "$pattern" >/dev/null 2>&1; then
    echo "  $pattern démarré (screen $screen_name)"
  else
    echo "  ERREUR: $pattern n'a pas démarré" >&2
    return 1
  fi
}

echo "=== ABD_DEMO auto-dial ==="

# listen → send → remote → auto-dial (ordre obligatoire, via screen)
start_screen "ASTlisten" "AST_manager_listen.pl" "/usr/share/astguiclient/AST_manager_listen.pl"
start_screen "ASTsend" "AST_manager_send.pl" "/usr/share/astguiclient/AST_manager_send.pl"
if ! pgrep -f "FastAGI_log.pl" >/dev/null 2>&1; then
  screen -d -m -S ASTfastlog bash -c 'export PERL5LIB=/usr/share/astguiclient/libs; exec /usr/share/astguiclient/FastAGI_log.pl'
  sleep 2
  pgrep -f "FastAGI_log.pl" >/dev/null && echo "  FastAGI_log.pl démarré (screen ASTfastlog)" || echo "  ERREUR: FastAGI_log.pl" >&2
else
  echo "  FastAGI_log.pl déjà actif"
fi
start_screen "ASTVDremote" "AST_VDremote_agents.pl" "/usr/share/astguiclient/AST_VDremote_agents.pl --debug"
start_screen "ASTVDauto" "AST_VDauto_dial.pl" "/usr/share/astguiclient/AST_VDauto_dial.pl"
# hopper = cron one-shot (pas un daemon)
/usr/share/astguiclient/AST_VDhopper.pl --debug=0 >>"$LOG_DIR/hopper-run.log" 2>&1 || true

# Nettoyage +212 et doublons, recharge hopper ES
"${MYSQL[@]}" <<'SQL'
DELETE FROM vicidial_list WHERE list_id=1011 AND phone_number LIKE '212%';
DELETE FROM vicidial_hopper WHERE campaign_id='ABD_DEMO' AND lead_id NOT IN (
  SELECT lead_id FROM vicidial_list WHERE list_id=1011
);
UPDATE vicidial_list SET status='NEW', called_since_last_reset='N' WHERE list_id=1011;
DELETE FROM vicidial_auto_calls WHERE campaign_id='ABD_DEMO';
UPDATE vicidial_hopper SET status='READY', user='' WHERE campaign_id='ABD_DEMO' AND status IN ('INCALL','QUEUE','DONE');
DELETE FROM vicidial_hopper WHERE campaign_id='ABD_DEMO';
INSERT INTO vicidial_hopper (lead_id, campaign_id, status, list_id, gmt_offset_now, state, alt_dial, priority)
SELECT vl.lead_id, 'ABD_DEMO', 'READY', vl.list_id, 0.00, vl.state, 'NONE', 0
FROM vicidial_list vl WHERE vl.list_id=1011 AND vl.status='NEW';
# omit_phone_code=N → Vicidial compose 34+9digits → _34XXXXXXXXX TrustSIP (évite _6XXXXXXXX FR)
UPDATE vicidial_campaigns SET active='Y', dial_method='RATIO', auto_dial_level=4, hopper_level=400, dial_timeout=45, campaign_cid='34632395675', omit_phone_code='N', dial_prefix='' WHERE campaign_id='ABD_DEMO';
UPDATE vicidial_list SET phone_code='34' WHERE list_id=1011;
UPDATE vicidial_server_carriers SET dialplan_entry='exten => _34XXXXXXXXX,1,AGI(agi://127.0.0.1:4577/call_log)\nexten => _34XXXXXXXXX,2,Dial(${SIPTRUNK}/${EXTEN},${CAMPDTO},To)\nexten => _34XXXXXXXXX,3,Hangup' WHERE carrier_id='TrustSIP';
UPDATE vicidial_remote_agents SET status='ACTIVE', number_of_lines=8, on_hook_agent='Y', on_hook_ring_time=15 WHERE campaign_id='ABD_DEMO';
SQL

curl -sS "http://127.0.0.1:8080/vicidial/non_agent_api.php?source=doorway_odoo&user=doorway&pass=DoorwayAdmin2026&function=update_campaign&campaign_id=ABD_DEMO&active=Y&auto_dial_level=4" >/dev/null || true

echo "Hopper:"
"${MYSQL[@]}" -Nse "
SELECT GROUP_CONCAT(CONCAT(vl.phone_number,':',h.status) ORDER BY vl.lead_id)
FROM vicidial_hopper h JOIN vicidial_list vl ON h.lead_id=vl.lead_id WHERE h.campaign_id='ABD_DEMO';
"
echo "OK — auto-dial actif sur ABD_DEMO (TrustSIP, CID=34632395675)"
