#!/bin/bash
# Lance Alex Driven B2B sur DW_QCB2B — LUNDI matin uniquement (après import liste).
set -euo pipefail
CAMPAIGN="DW_QCB2B"
LEA_EXT="86023"
DIAL_LEVEL="${1:-0}"

echo "=== Alex Driven B2B — démarrage campagne $CAMPAIGN (auto_dial_level=$DIAL_LEVEL) ==="
echo "ATTENTION: mode manuel par défaut (ADL=0). Passer 1.0 explicitement pour autodial."
mysql asterisk -e "UPDATE vicidial_campaigns SET active='Y', auto_dial_level=$DIAL_LEVEL, dial_method=IF($DIAL_LEVEL>0,'RATIO','MANUAL') WHERE campaign_id='$CAMPAIGN';"
mysql asterisk -e "UPDATE vicidial_remote_agents SET status='ACTIVE' WHERE campaign_id='$CAMPAIGN' AND conf_exten='$LEA_EXT';"
echo "Campagne activée. Vérifier hopper :"
mysql asterisk -N -e "SELECT COUNT(*) FROM vicidial_hopper WHERE campaign_id='$CAMPAIGN' AND status='READY';"
echo "Pour test manuel (sans VICIdial) :"
echo "  asterisk -rx \"channel originate SIP/Door_App0/1XXXXXXXXXX extension 86023@driven-b2b-qc-bridge\""
