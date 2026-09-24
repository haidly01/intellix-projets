#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Déploie AGI + dialplan Sofia ES et configure VICIdial DW_ESREN."""
from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

DEPLOY = Path(__file__).resolve().parent
AGI_SRC = DEPLOY / "n8n_sofia_es.agi"
BRIDGE_SRC = Path(
    "/odoo/custom/addons/doorway_agents_dashboard/deploy/intellix_sofia/n8n_bridge.agi"
)
EXT_SRC = DEPLOY / "extensions_sofia_es.conf"
AGI_BIN = Path("/usr/share/asterisk/agi-bin")
AGI_BIN_LEGACY = Path("/var/lib/asterisk/agi-bin")
ASTERISK_ETC = Path("/etc/asterisk")
INCLUDE_LINE = "#include extensions_sofia_es.conf"
SERVER_IP = "187.124.50.69"
CAMPAIGN = "DW_ESREN"
CONF_EXTEN = "86010"


def _mysql(sql: str) -> str:
    cmd = [
        "mysql",
        "-h127.0.0.1",
        "-P3307",
        "-uvicidial",
        "-pa42246a8306dc369d33525c4cea6fef1",
        "asterisk",
        "-e",
        sql,
    ]
    return subprocess.check_output(cmd, text=True, stderr=subprocess.STDOUT)


def deploy_agi() -> None:
    AGI_BIN.mkdir(parents=True, exist_ok=True)
    shutil.copy2(AGI_SRC, AGI_BIN / "n8n_sofia_es.agi")
    (AGI_BIN / "n8n_sofia_es.agi").chmod(0o755)
    if BRIDGE_SRC.is_file():
        text = BRIDGE_SRC.read_text(encoding="utf-8")
        text = text.replace(
            "https://n8n.intellixcrm.com/webhook/telephony/vicidial/event",
            "https://n8n.intellixcrm.com/webhook/sofia-es/vicidial/event",
        )
        text = text.replace(
            'os.environ.get("AGENT_ID", "sofia-intellix-cc-fr-maroc")',
            'os.environ.get("AGENT_ID", "sofia-es-avatrade-2026")',
        )
        text = text.replace('"language": "fr-FR"', '"language": "es-ES"')
        (AGI_BIN / "n8n_bridge_sofia_es.agi").write_text(text, encoding="utf-8")
        (AGI_BIN / "n8n_bridge_sofia_es.agi").chmod(0o755)
    subprocess.run(["chown", "-R", "asterisk:asterisk", str(AGI_BIN)], check=False)
    print("AGI déployés →", AGI_BIN)


def deploy_dialplan() -> None:
    dst = ASTERISK_ETC / "extensions_sofia_es.conf"
    shutil.copy2(EXT_SRC, dst)
    dst.chmod(0o644)
    ext = ASTERISK_ETC / "extensions.conf"
    content = ext.read_text(encoding="utf-8")
    if INCLUDE_LINE not in content:
        content = content.rstrip() + "\n\n" + INCLUDE_LINE + "\n"
        ext.write_text(content, encoding="utf-8")
    subprocess.run(["asterisk", "-rx", "dialplan reload"], check=True)
    print("Dialplan rechargé:", dst)


def configure_vicidial() -> None:
    _mysql(
        f"""
        UPDATE vicidial_campaigns SET
            active='Y',
            dial_method='RATIO',
            auto_dial_level=1,
            hopper_level=200,
            amd_type='AMD',
            campaign_recording='ONDEMAND',
            omit_phone_code='Y',
            dial_prefix=''
        WHERE campaign_id='{CAMPAIGN}';
        UPDATE vicidial_list vl
        INNER JOIN vicidial_lists vls ON vl.list_id = vls.list_id
        SET vl.phone_code='34'
        WHERE vls.campaign_id IN ('DW_ESREN','ABD_DEMO','DWTOISOE','DWTOISOS','DWMAMACA','DWMATEST');
        UPDATE vicidial_server_carriers SET dialplan_entry='exten => _34XXXXXXXXX,1,AGI(agi://127.0.0.1:4577/call_log)\\nexten => _34XXXXXXXXX,2,Set(__PHONE=${EXTEN})\\nexten => _34XXXXXXXXX,n,Dial(${SIPTRUNK}/${EXTEN},${CAMPDTO},ToU(iso-esp-ia-hook^s^1(${EXTEN})))\\nexten => _34XXXXXXXXX,n,Hangup'
        WHERE carrier_id='TrustSIP';
        """
    )
    out = _mysql(
        f"SELECT remote_agent_id FROM vicidial_remote_agents "
        f"WHERE campaign_id='{CAMPAIGN}' AND conf_exten='{CONF_EXTEN}' LIMIT 1;"
    ).strip()
    if not out or out.startswith("remote_agent_id"):
        _mysql(
            f"""
            INSERT INTO vicidial_remote_agents
                (user_start, number_of_lines, server_ip, conf_exten, status, campaign_id, on_hook_agent, on_hook_ring_time)
            VALUES
                ('{CONF_EXTEN}', 5, '{SERVER_IP}', '{CONF_EXTEN}', 'ACTIVE', '{CAMPAIGN}', 'Y', 10);
            """
        )
        print("Remote agent Sofia ES créé (86010)")
    else:
        _mysql(
            f"""
            UPDATE vicidial_remote_agents SET status='ACTIVE', number_of_lines=5, on_hook_agent='Y'
            WHERE campaign_id='{CAMPAIGN}' AND conf_exten='{CONF_EXTEN}';
            """
        )
        print("Remote agent Sofia ES activé")
    _mysql(
        f"""
        INSERT INTO vicidial_hopper (lead_id, campaign_id, status, list_id, gmt_offset_now, state, alt_dial, priority)
        SELECT vl.lead_id, '{CAMPAIGN}', 'READY', vl.list_id, 0.00, vl.state, 'NONE', 0
        FROM vicidial_list vl
        INNER JOIN vicidial_lists vls ON vl.list_id = vls.list_id
        WHERE vls.campaign_id='{CAMPAIGN}' AND vl.status='NEW'
        AND vl.lead_id NOT IN (SELECT lead_id FROM vicidial_hopper WHERE campaign_id='{CAMPAIGN}')
        LIMIT 50;
        """
    )
    hopper = _mysql(
        f"SELECT COUNT(*) FROM vicidial_hopper WHERE campaign_id='{CAMPAIGN}';"
    ).strip().splitlines()[-1]
    print(f"Campagne {CAMPAIGN} active — hopper: {hopper} leads")


def main() -> None:
    deploy_agi()
    deploy_dialplan()
    configure_vicidial()
    print("OK — Sofia ES telephony prêt.")


if __name__ == "__main__":
    main()
