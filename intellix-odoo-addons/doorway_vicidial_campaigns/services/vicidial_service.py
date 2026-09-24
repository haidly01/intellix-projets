# -*- coding: utf-8 -*-
"""Connecteur VICIdial : MySQL + API non_agent (doorway_odoo)."""
import glob
import json
import logging
import os
import re
import threading
import time
from datetime import datetime

from odoo import _, api, fields, SUPERUSER_ID

_logger = logging.getLogger(__name__)
CONF_PATH = "/etc/odoo-server.conf"
API_SOURCE = "doorway_odoo"

# ── Throttle appels déclenchés par l'IA (call_out_number) ────────────────
# Ne s'applique QU'aux appels sortants initiés par les agents IA
# (non_agent_api). Les appels manuels des agents humains passent par
# dial_manual_number / dial_manual_next_call et ne sont JAMAIS limités ici.
AI_CALLS_PER_HOUR_PARAM = "doorway_vicidial_campaigns.ai_calls_per_hour"
AI_CALLS_DEFAULT_PER_HOUR = 30  # démarrage prudent « qualité, pas quantité »
AI_CALL_WINDOW_PARAM = "doorway_vicidial_campaigns.ai_call_throttle_window"


# Extensions Asterisk (context default) — tests audio poste Odoo / ViciPhone
MANUAL_DIAL_INTERNAL_EXTENSIONS = frozenset({
    "86028999",  # Playback(demo-echotest) — extensions_manual_webphone_fr.conf
})

AMD_ACTION_MAP = {
    "leave_message": "MESSAGE",
    "hangup": "HANGUP",
    "callback_schedule": "CALLMENU",
}
DIAL_MODE_MAP = {
    "preview": "MANUAL",
    "progressive": "RATIO",
    "predictive": "RATIO",
}
SPAIN_TRUSTSIP_CAMPAIGN_IDS = (
    "ABD_DEMO",
    "DW_ESREN",
    "DWTOISOE",
    "DWTOISOS",
    "DWMAMACA",
    "DWMATEST",
)
IA_REMOTE_AGENT_EXTEN = {
    "DW_ESREN": "86010",
    "ABD_DEMO": "86011",
    "DWTOISOE": "86012",
    "SE_RENOV_QC": "86013",
    "MR_IMMO_QC": "86014",
    "DW_QCB2C": "86013",
    "DW_QCB2B": "86023",
    "DW_FRB2C": "86022",
}
QC_IA_CAMPAIGN_IDS = ("SE_RENOV_QC", "MR_IMMO_QC", "DW_QCB2C", "DW_QCB2B")
TRUSTSIP_ES_DIALPLAN = (
    "exten => _34XXXXXXXXX,1,AGI(agi://127.0.0.1:4577/call_log)\n"
    "exten => _34XXXXXXXXX,n,Set(PHONE=${EXTEN})\n"
    "exten => _34XXXXXXXXX,n,Set(__PHONE=${EXTEN})\n"
    "exten => _34XXXXXXXXX,n,Dial(${SIPTRUNK}/${EXTEN},"
    "${CAMPDTO},ToU(iso-esp-ia-hook^s^1(${EXTEN})))\n"
    "exten => _34XXXXXXXXX,n,Hangup"
)
DOOR_APP0_QC_CAMPAIGN_IDS = (
    "DW_QCB2C",
    "DW_QCB2B",
    "DW_RAPQC",
    "SE_RENOV_QC",
    "MR_IMMO_QC",
)

IA_AGENT_LABELS = {
    "DW_QCB2C": "Léa · QC",
    "DW_QCB2B": "Alex · Driven QC",
    "SE_RENOV_QC": "Émilie · SE QC",
    "MR_IMMO_QC": "Sophie · Immo QC",
    "DW_FRB2C": "Sofia · RénoFacile FR",
    "DW_LEAFR": "Léa · FR B2B",
}
HOSTINGER_MANUAL_ONLY_VICIDIAL = frozenset({"DW_QCB2C", "DW_QCB2B"})
IA_MANUAL_QUALITY_VICIDIAL = frozenset(
    {"DW_FRB2C", "DW_LEAFR", "DW_FRB2B", "DW_QCB2C", "DW_QCB2B"}
)
IA_MANUAL_QUALITY_FLAG = "/opt/doorway/IA_MANUAL_QUALITY.flag"
HOSTINGER_FLAG_BY_VICIDIAL = {
    "DW_QCB2C": "/opt/doorway/LEA_QC_HOSTINGER_ONLY.flag",
    "DW_QCB2B": "/opt/doorway/ALEX_HOSTINGER_ONLY.flag",
}
LEA_QC_CAMPAIGN_IDS = frozenset({"DW_QCB2C", "SE_RENOV_QC", "MR_IMMO_QC"})
DOOR_APP0_FR_CAMPAIGN_IDS = ("DW_FRB2C", "DW_FRB2B", "DW_FRAC")
DOOR_APP0_FR_CALLER_ID = "33424436337"
DOOR_APP0_QC_CALLER_ID = "15817058118"
TRUSTSIP_ES_CALLER_ID = "34632395675"
INVALID_CAMPAIGN_CIDS = frozenset({
    "",
    "anonymous",
    "Anonymous",
    "TrustSIP",
    "Door_App0",
    "Door_App0_FR",
})


DOOR_APP0_FR_PEER_SUFFIX = """
; France outbound CLI (Africa-Con) — peer séparé pour fromuser FR
[Door_App0_FR]
type=peer
host=%(host)s
port=%(port)s
context=trunkinbound
insecure=invite,port
deny=0.0.0.0/0.0.0.0
permit=%(host)s/32
disallow=all
allow=ulaw
allow=alaw
dtmfmode=rfc2833
canreinvite=no
directmedia=no
nat=force_rport,comedia
callerid=\"%(fr_cid)s\" <%(fr_cid)s>
fromuser=%(fr_cid)s
fromdomain=187.124.50.69
sendrpid=yes
trustrpid=no
qualify=yes
qualifyfreq=60
"""

def _door_app0_dialplan():
    """Trunk par défaut Door_App0 — numéros sans + ni 00."""
    lines = [
        "; Africa-Con Door_App0 — FR / Afrique / Canada",
        "exten => _33X.,1,AGI(agi://127.0.0.1:4577/call_log)",
        "exten => _33X.,n,Dial(${DOORTRUNK}/${EXTEN},${CAMPDTO},To)",
        "exten => _33X.,n,Hangup",
        "exten => _32X.,1,AGI(agi://127.0.0.1:4577/call_log)",
        "exten => _32X.,n,Dial(${DOORTRUNK}/${EXTEN},${CAMPDTO},To)",
        "exten => _32X.,n,Hangup",
    ]
    for prefix in ("20", "21", "22", "23", "24", "25", "26", "27", "28"):
        lines.extend(
            [
                "exten => _%sX.,1,AGI(agi://127.0.0.1:4577/call_log)" % prefix,
                "exten => _%sX.,n,Dial(${DOORTRUNK}/${EXTEN},${CAMPDTO},To)"
                % prefix,
                "exten => _%sX.,n,Hangup" % prefix,
            ]
        )
    # 29x sauf 296 (conf agent ConfBridge 29600xxx)
    for prefix in ("290", "291", "292", "293", "294", "295", "297", "298", "299"):
        lines.extend(
            [
                "exten => _%sX.,1,AGI(agi://127.0.0.1:4577/call_log)" % prefix,
                "exten => _%sX.,n,Dial(${DOORTRUNK}/${EXTEN},${CAMPDTO},To)"
                % prefix,
                "exten => _%sX.,n,Hangup" % prefix,
            ]
        )
    lines.extend(
        [
            "exten => _1NXXNXXXXXX,1,AGI(agi://127.0.0.1:4577/call_log)",
            "exten => _1NXXNXXXXXX,n,Dial(${DOORTRUNK}/${EXTEN},${CAMPDTO},To)",
            "exten => _1NXXNXXXXXX,n,Hangup",
            "exten => _NXXNXXXXXX,1,AGI(agi://127.0.0.1:4577/call_log)",
            "exten => _NXXNXXXXXX,n,Dial(${DOORTRUNK}/1${EXTEN},${CAMPDTO},To)",
            "exten => _NXXNXXXXXX,n,Hangup",
        ]
    )
    return "\n".join(lines)


class VicidialService:
    def __init__(self, env):
        self.env = env
        self._icp = env["ir.config_parameter"].sudo()
        self._conn = None
        self._cfg = None

    def _load_config(self):
        if self._cfg is not None:
            return self._cfg
        conf_file = {}
        try:
            with open(CONF_PATH, encoding="utf-8") as handle:
                for line in handle:
                    line = line.strip()
                    if not line or line[0] in "#;" or "=" not in line:
                        continue
                    key, val = line.split("=", 1)
                    conf_file[key.strip()] = val.strip()
        except OSError:
            pass

        def _get(*keys, default=""):
            for key in keys:
                val = os.environ.get(key) or conf_file.get(key)
                if val:
                    return val
            return default

        self._cfg = {
            "host": _get(
                "VICIDIAL_DB_HOST",
                "doorway_vicidial_campaigns.db_host",
                "doorway_agents_dashboard.vicidial_db_host",
                "doorway_agents_ia.vicidial_db_host",
                default="127.0.0.1",
            ),
            "port": int(
                _get(
                    "VICIDIAL_DB_PORT",
                    "doorway_vicidial_campaigns.db_port",
                    "doorway_agents_dashboard.vicidial_db_port",
                    "doorway_agents_ia.vicidial_db_port",
                    default="3307",
                )
                or 3307
            ),
            "user": _get(
                "VICIDIAL_DB_USER",
                "doorway_vicidial_campaigns.db_user",
                "doorway_agents_dashboard.vicidial_db_user",
                "doorway_agents_ia.vicidial_db_user",
                default="vicidial",
            ),
            "password": _get(
                "VICIDIAL_DB_PASS",
                "VICIDIAL_DB_PASSWORD",
                "doorway_vicidial_campaigns.db_password",
                "doorway_agents_dashboard.vicidial_db_password",
                "doorway_agents_ia.vicidial_db_password",
            ),
            "database": _get(
                "VICIDIAL_DB_NAME",
                "doorway_vicidial_campaigns.db_name",
                "doorway_agents_dashboard.vicidial_db_name",
                "doorway_agents_ia.vicidial_db_name",
                default="asterisk",
            ),
            "api_user": _get("VICIDIAL_API_USER", default="admin"),
            "api_pass": _get("VICIDIAL_API_PASS", default=""),
            "base_url": self._resolve_vicidial_base_url(_get),
        }
        return self._cfg

    @staticmethod
    def _hostinger_only_vicidial_ids():
        return {
            vid
            for vid, path in HOSTINGER_FLAG_BY_VICIDIAL.items()
            if path and os.path.isfile(path)
        }

    def _is_hostinger_campaign(self, campaign_id):
        return (campaign_id or "")[:8] in self._hostinger_only_vicidial_ids()

    def _load_hostinger_config(self):
        conf_file = {}
        try:
            with open(CONF_PATH, encoding="utf-8") as handle:
                for line in handle:
                    line = line.strip()
                    if not line or line[0] in "#;" or "=" not in line:
                        continue
                    key, val = line.split("=", 1)
                    conf_file[key.strip()] = val.strip()
        except OSError:
            pass

        def _get(*keys, default=""):
            for key in keys:
                val = os.environ.get(key) or conf_file.get(key)
                if val:
                    return val
            return default

        return {
            "host": _get(
                "VICIDIAL_HOSTINGER_DB_HOST",
                "doorway_vicidial_campaigns.hostinger_db_host",
                default="2.25.153.82",
            ),
            "port": int(
                _get(
                    "VICIDIAL_HOSTINGER_DB_PORT",
                    "doorway_vicidial_campaigns.hostinger_db_port",
                    default="3306",
                )
                or 3306
            ),
            "user": _get(
                "VICIDIAL_HOSTINGER_DB_USER",
                "doorway_vicidial_campaigns.hostinger_db_user",
                default="vicidial",
            ),
            "password": _get(
                "VICIDIAL_HOSTINGER_DB_PASSWORD",
                "doorway_vicidial_campaigns.hostinger_db_password",
            ),
            "database": _get(
                "VICIDIAL_HOSTINGER_DB_NAME",
                "doorway_vicidial_campaigns.hostinger_db_name",
                default="asterisk",
            ),
        }

    def _db_config_for_campaign(self, campaign_id=None):
        if campaign_id and self._is_hostinger_campaign(campaign_id):
            return self._load_hostinger_config()
        return self._load_config()

    def _hostinger_ssh_config(self):
        conf_file = {}
        try:
            with open(CONF_PATH, encoding="utf-8") as handle:
                for line in handle:
                    line = line.strip()
                    if not line or line[0] in "#;" or "=" not in line:
                        continue
                    key, val = line.split("=", 1)
                    conf_file[key.strip()] = val.strip()
        except OSError:
            pass

        def _get(*keys, default=""):
            for key in keys:
                val = os.environ.get(key) or conf_file.get(key)
                if val:
                    return val
            return default

        return {
            "host": _get("VICIDIAL_HOSTINGER_SSH_HOST", default="2.25.153.82"),
            "user": _get("VICIDIAL_HOSTINGER_SSH_USER", default="root"),
            "key": _get(
                "VICIDIAL_HOSTINGER_SSH_KEY",
                default="/root/.ssh/ovh_bhs_intellix",
            ),
            "query_script": _get(
                "VICIDIAL_HOSTINGER_QUERY_SCRIPT",
                default="/usr/local/bin/intellix-hostinger-vicidial-query.sh",
            ),
        }

    @staticmethod
    def _sanitize_vicidial_id(campaign_id):
        if not campaign_id or isinstance(campaign_id, int):
            return ""
        return re.sub(r"[^A-Z0-9_]", "", str(campaign_id).upper())[:8]

    def _vicidial_campaign_from_conv(self, conv):
        """ID campagne VICIdial (str) depuis payload — pas l'FK Odoo doorway.campaign."""
        conv = conv or {}
        raw = conv.get("campaign")
        if not raw:
            raw_cid = conv.get("campaign_id")
            if isinstance(raw_cid, str):
                raw = raw_cid
        return self._sanitize_vicidial_id(raw)

    def _hostinger_ids_sql(self, ids):
        return ",".join("'%s'" % self._sanitize_vicidial_id(i) for i in ids if i)

    def _hostinger_query_rows(self, sql, columns=None):
        """Exécute une requête MySQL sur Hostinger via SSH (MySQL non exposé)."""
        import csv
        import io
        import subprocess

        cfg = self._hostinger_ssh_config()
        script = cfg["query_script"]
        if not os.path.isfile(script):
            raise OSError("Hostinger query script missing: %s" % script)
        cmd = ["sudo", script, sql]
        env = os.environ.copy()
        env["VICIDIAL_HOSTINGER_SSH_HOST"] = cfg["host"]
        env["VICIDIAL_HOSTINGER_SSH_USER"] = cfg["user"]
        env["VICIDIAL_HOSTINGER_SSH_KEY"] = cfg["key"]
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=45,
            env=env,
            check=False,
        )
        if proc.returncode != 0:
            err = (proc.stderr or proc.stdout or "").strip()
            raise RuntimeError(err or "Hostinger query failed")
        raw = (proc.stdout or "").strip()
        if not raw:
            return []
        reader = csv.reader(io.StringIO(raw), delimiter="\t")
        data_rows = list(reader)
        if not data_rows:
            return []
        if columns:
            return [dict(zip(columns, row)) for row in data_rows]
        headers = data_rows[0]
        return [dict(zip(headers, row)) for row in data_rows[1:]]

    def _hostinger_execute_sql(self, sql):
        """Exécute UPDATE/DELETE MySQL sur Hostinger via SSH."""
        import shlex
        import subprocess

        cfg = self._hostinger_ssh_config()
        remote = "mysql asterisk -e %s" % shlex.quote(sql)
        cmd = [
            "ssh",
            "-i",
            cfg["key"],
            "-o",
            "StrictHostKeyChecking=no",
            "-o",
            "ConnectTimeout=12",
            "-o",
            "BatchMode=yes",
            "%s@%s" % (cfg["user"], cfg["host"]),
            remote,
        ]
        proc = subprocess.run(
            cmd, capture_output=True, text=True, timeout=45, check=False
        )
        if proc.returncode != 0:
            err = (proc.stderr or proc.stdout or "").strip()
            raise RuntimeError(err or "Hostinger execute failed")
        return True

    def _agent_portal_base(self):
        """Base URL navigateur (HTTPS Odoo) pour webphone / vicidial.php."""
        web = (self._icp.get_param("web.base.url") or "").rstrip("/")
        if web.startswith("https://"):
            return "%s/vicidial-web" % web
        admin = (self._icp.get_param("doorway.vicidial_admin_url") or "").strip()
        if admin:
            return "%s/agc" % admin.rstrip("/")
        return "%s/agc" % self._resolve_vicidial_base_url(
            lambda *a, **k: "http://localhost:8080"
        )

    def _resolve_vicidial_base_url(self, conf_get):
        """URL Apache VICIdial (:8080) — jamais 127.0.0.1 côté navigateur agent."""
        icp_admin = (self._icp.get_param("doorway.vicidial_admin_url") or "").strip()
        if icp_admin:
            return icp_admin.rstrip("/")
        icp_agent = (self._icp.get_param("doorway.vicidial_agent_url") or "").strip()
        if icp_agent:
            base = icp_agent.split("/agc/")[0].rstrip("/")
            if base:
                return base
        server_ip = (
            self._icp.get_param("doorway.vicidial_campaigns.server_ip") or ""
        ).strip()
        if server_ip and server_ip not in ("127.0.0.1", "localhost"):
            return "http://%s:8080" % server_ip
        return conf_get(
            "VICIDIAL_BASE_URL",
            "doorway_vicidial_campaigns.admin_url",
            default="http://localhost:8080",
        ).rstrip("/")

    @property
    def api_base(self):
        cfg = self._load_config()
        return "%s/vicidial/non_agent_api.php" % cfg["base_url"]

    @property
    def api_auth(self):
        cfg = self._load_config()
        return "user=%s&pass=%s&source=%s" % (
            cfg["api_user"],
            cfg["api_pass"],
            API_SOURCE,
        )

    def is_available(self):
        try:
            conn = self._connect()
            conn.close()
            self._conn = None
            return True
        except Exception:  # noqa: BLE001
            return False

    def _os_local_now(self):
        """Heure locale de l'OS (naive), alignee sur perl localtime utilise par
        AST_VDauto_dial.pl pour le seuil de lag. Odoo force TZ=UTC dans son
        process, donc fields.Datetime.now() renvoie UTC : on lit la vraie zone
        via /etc/localtime pour ecrire les horodatages VICIdial en heure locale
        (sinon last_update_time est toujours en retard -> PAUSE random_id=10)."""
        from datetime import datetime
        try:
            import os
            from zoneinfo import ZoneInfo
            zone = os.path.realpath("/etc/localtime").split("zoneinfo/")[-1]
            return datetime.now(ZoneInfo(zone)).replace(tzinfo=None)
        except Exception:  # noqa: BLE001
            return datetime.now()

    def _connect(self, campaign_id=None):
        import mysql.connector

        if campaign_id and self._is_hostinger_campaign(campaign_id):
            raise RuntimeError(
                "Direct MySQL to Hostinger blocked; use _hostinger_query_rows()"
            )
        cfg = self._db_config_for_campaign(campaign_id)
        conn = mysql.connector.connect(
            host=cfg["host"],
            port=cfg["port"],
            user=cfg["user"],
            password=cfg["password"],
            database=cfg["database"],
            connection_timeout=10,
        )
        # Aligne le fuseau de la session MySQL sur l'heure locale de l'OS.
        # MySQL tourne en UTC (system_time_zone=UTC) mais AST_VDauto_dial.pl
        # calcule le seuil de lag en heure locale (localtime). Sans cet
        # alignement, last_update_time (NOW() = UTC) est toujours ~2h en retard
        # -> l'agent est remis en PAUSE immediate (random_id=10) juste apres
        # etre passe READY. On force donc NOW() en heure locale (DST-proof).
        try:
            import os as _os
            from datetime import datetime as _dt
            try:
                # Odoo force TZ=UTC dans son process : on lit la vraie zone de
                # l'OS via /etc/localtime (ex: Europe/Paris) pour obtenir le
                # meme offset que perl localtime (AST_VDauto_dial). DST-proof.
                from zoneinfo import ZoneInfo as _ZI
                _zone = _os.path.realpath("/etc/localtime").split("zoneinfo/")[-1]
                _off = _dt.now(_ZI(_zone)).utcoffset()
            except Exception:  # noqa: BLE001
                _off = _dt.now().astimezone().utcoffset()
            _tot = int(_off.total_seconds())
            _sign = "+" if _tot >= 0 else "-"
            _tot = abs(_tot)
            _tz = "%s%02d:%02d" % (_sign, _tot // 3600, (_tot % 3600) // 60)
            _c = conn.cursor()
            _c.execute("SET time_zone = %s", (_tz,))
            _c.close()
        except Exception:  # noqa: BLE001
            pass
        return conn

    def _cursor(self, dictionary=False, campaign_id=None):
        conn = self._connect(campaign_id=campaign_id)
        return conn, conn.cursor(dictionary=dictionary)

    def _api_get(self, params):
        import requests

        url = "%s?%s&%s" % (self.api_base, self.api_auth, params)
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        return response.text

    @staticmethod
    def _slug_campaign_id(name):
        return re.sub(r"[^a-z0-9_]", "", (name or "campaign").lower().replace(" ", "_"))[:20]

    @staticmethod
    def _human_vicidial_statuses():
        return frozenset(
            {"A", "SALE", "S", "HUMAN", "PU", "PM", "XFER", "INT", "INTEREST"}
        )

    @staticmethod
    def _is_voicemail_call(amd_result=None, disposition=None, status=None):
        """Répondeur / IVR — pas d'enregistrement conversation à conserver."""
        if amd_result in ("answering_machine", "amd_hangup"):
            return True
        if disposition == "REPONDEUR":
            return True
        st = (status or "").upper()
        return st in ("AA", "AM", "AMD", "IVR")

    def _hostinger_agi_amd_hint(self, uniqueid):
        """Lit les logs AGI Hostinger (IVR gate, AMD machine, AGI_START)."""
        epoch = self._uniqueid_epoch(uniqueid)
        if not epoch:
            return False
        script = self._icp.get_param(
            "doorway_vicidial_campaigns.hostinger_agi_grep_script",
            "/usr/local/bin/intellix-hostinger-agi-grep.sh",
        )
        lines = ""
        try:
            import subprocess

            if os.path.isfile(script) and os.access(script, os.X_OK):
                proc = subprocess.run(
                    ["sudo", script, epoch],
                    capture_output=True,
                    text=True,
                    timeout=12,
                    check=False,
                )
                lines = proc.stdout or ""
            if not lines.strip():
                key = self._icp.get_param(
                    "doorway_vicidial_campaigns.hostinger_ssh_key",
                    "/root/.ssh/ovh_bhs_intellix",
                )
                host = self._icp.get_param(
                    "doorway_vicidial_campaigns.hostinger_ssh_host", "2.25.153.82"
                )
                proc = subprocess.run(
                    [
                        "ssh",
                        "-o",
                        "BatchMode=yes",
                        "-o",
                        "ConnectTimeout=5",
                        "-i",
                        key,
                        "root@%s" % host,
                        "grep '%s' /var/log/lea-qc-live.log /var/log/alex-qc-live.log "
                        "/var/log/driven-b2b-qc-live.log 2>/dev/null | tail -25"
                        % epoch,
                    ],
                    capture_output=True,
                    text=True,
                    timeout=10,
                    check=False,
                )
                lines = proc.stdout or ""
        except Exception:
            return False
        if not lines.strip():
            return False
        if "AGI_START" in lines and "AMD_DIALPLAN_MACHINE" not in lines:
            return "human"
        if any(
            token in lines
            for token in (
                "AMD_DIALPLAN_MACHINE",
                "IVR_GATE_HIT",
                "IVR_GATE_PASS",
                "PHANTOM_PICKUP",
            )
        ):
            return "amd_hangup"
        return False

    def _infer_amd_for_hostinger_call(
        self, uniqueid, status=None, duration=0, use_agi=False
    ):
        """AMD QC Hostinger — logs AGI seulement si use_agi (évite N×SSH en sync bulk)."""
        if use_agi:
            hint = self._hostinger_agi_amd_hint(uniqueid)
            if hint:
                return hint
        mapped = self.map_amd_from_vicidial(None, status=status)
        if mapped:
            return mapped
        if int(duration or 0) <= 0:
            return "no_answer"
        return False

    @staticmethod
    def map_amd_from_vicidial(amd_status, status=None, amd_action=None):
        s = (amd_status or "").upper()
        st = (status or "").upper()
        if "MACHINE" in s or st in ("AA", "AM", "AMD"):
            if (amd_action or "") == "hangup":
                return "amd_hangup"
            return "answering_machine"
        if st == "IVR":
            return "amd_hangup"
        if s in ("HUMAN", "PERSON") or st in ("A", "SALE", "HUMAN"):
            return "human"
        if st in ("NA", "NOANSWER", "N", "ADC"):
            return "no_answer"
        if st in ("B", "BUSY", "AB"):
            return "busy"
        if st in ("DC", "DISCONNECT", "INVALID"):
            return "invalid"
        return False

    @staticmethod
    def map_disposition_from_vicidial(status):
        mapping = {
            "SALE": "VENTE",
            "S": "VENTE",
            "INTEREST": "INTERET",
            "INT": "INTERET",
            "CALLBK": "RAPPEL",
            "CB": "RAPPEL",
            "NI": "REFUS",
            "DNC": "REFUS",
            "AA": "REPONDEUR",
            "AM": "REPONDEUR",
            "IVR": "REPONDEUR",
            "DC": "INVALIDE",
        }
        return mapping.get((status or "").upper(), False)

    @staticmethod
    def map_crm_qualification_to_vicidial_status(statut):
        """Statut VICIdial (vicidial_list.status) depuis qualification CRM."""
        return {
            "qualifie": "SALE",
            "rdv": "SALE",
            "a_rappeler": "CALLBK",
            "pas_interesse": "NI",
            "refus": "NI",
            "non_qualifie": "NI",
            "disqualifie": "NI",
            "messagerie": "AM",
            "faux_num": "DC",
            "dnc": "DNC",
            "deja_servi": "NI",
            "locataire": "NI",
            "hors_cible": "NI",
            "b2b_valide": "INT",
            "pas_reponse": "NA",
            "repondu": "NA",
        }.get((statut or "").strip(), "NA")

    @staticmethod
    def map_crm_qualification_to_call_disposition(statut):
        """Disposition doorway.call.log depuis qualification workstation."""
        return {
            "qualifie": "INTERET",
            "rdv": "VENTE",
            "a_rappeler": "RAPPEL",
            "pas_interesse": "REFUS",
            "refus": "REFUS",
            "non_qualifie": "REFUS",
            "disqualifie": "REFUS",
            "messagerie": "REPONDEUR",
            "faux_num": "INVALIDE",
            "dnc": "REFUS",
            "deja_servi": "REFUS",
            "locataire": "REFUS",
            "hors_cible": "REFUS",
            "b2b_valide": "INTERET",
            "pas_reponse": "REPONDEUR",
            "repondu": "INTERET",
        }.get((statut or "").strip())

    def sync_qualification_to_vicidial(self, lead, statut, agent_login=None):
        """Met à jour vicidial_list, hopper et call log après qualification."""
        lead = lead.sudo()
        statut = (statut or "").strip()
        vic_status = self.map_crm_qualification_to_vicidial_status(statut)
        disp = self.map_crm_qualification_to_call_disposition(statut)
        cid = (lead.campagne_vicidial or "")[:8]
        if not cid:
            session = (
                self.env["doorway.vicidial.agent.session"]
                .sudo()
                .get_active_session(self.env.user)
            )
            if session and session.campaign_id:
                cid = (session.campaign_id.vicidial_campaign_id or "")[:8]
        phone = (lead.phone or "").strip()
        result = {
            "ok": False,
            "vicidial_status": vic_status,
            "vicidial_lead_id": False,
            "skipped": False,
        }
        if not phone:
            result["skipped"] = "no_phone"
            return result

        Session = self.env["doorway.vicidial.agent.session"]
        tails = Session._phone_search_tails(phone)
        vic_lead_id = False
        if self.is_available() and cid and tails:
            conn = self._connect()
            try:
                cur = conn.cursor(dictionary=True)
                for tail in tails:
                    cur.execute(
                        """
                        SELECT vl.lead_id FROM vicidial_list vl
                        INNER JOIN vicidial_lists vls ON vl.list_id = vls.list_id
                        WHERE vls.campaign_id = %s
                          AND (
                            vl.phone_number LIKE %s
                            OR vl.phone_number LIKE %s
                            OR RIGHT(vl.phone_number, 9) = %s
                          )
                        ORDER BY vl.lead_id DESC LIMIT 1
                        """,
                        (cid, "%" + tail, tail, tail[-9:]),
                    )
                    row = cur.fetchone()
                    if row:
                        vic_lead_id = int(row["lead_id"])
                        break
                if vic_lead_id:
                    cur.execute(
                        """
                        UPDATE vicidial_list
                        SET status = %s, user = %s
                        WHERE lead_id = %s
                        """,
                        (vic_status, (agent_login or "")[:20], vic_lead_id),
                    )
                    cur.execute(
                        "DELETE FROM vicidial_hopper WHERE lead_id = %s",
                        (vic_lead_id,),
                    )
                conn.commit()
                cur.close()
            finally:
                conn.close()
            result["ok"] = bool(vic_lead_id)
            result["vicidial_lead_id"] = vic_lead_id or False
        else:
            result["skipped"] = "mysql_or_campaign"

        if disp:
            log = self.env["doorway.call.log"].sudo().search(
                [("lead_id", "=", lead.id)],
                order="call_date desc",
                limit=1,
            )
            if not log and lead.vicidial_call_uid:
                log = self.env["doorway.call.log"].sudo().search(
                    [("vicidial_call_id", "=", lead.vicidial_call_uid)],
                    limit=1,
                )
            if log:
                log.write({"disposition": disp})

        Sync = self.env["doorway.vicidial.call.sync"].sudo()
        sync = Sync.search(
            [("lead_id", "=", lead.id)],
            order="date_debut desc",
            limit=1,
        )
        if sync:
            sync.write(
                {
                    "qualification_faite": statut
                    not in ("repondu", "pas_reponse", "non_fait")
                }
            )
        return result

    def schedule_vicidial_callback(
        self,
        phone,
        campaign_id,
        days=30,
        comments="",
        vicidial_user="VDAD",
        lead_status="CALLBK",
    ):
        """Programme un rappel VICIdial (vicidial_callbacks + statut CALLBK sur le lead)."""
        cid = self._sanitize_vicidial_id(campaign_id)
        phone = (phone or "").strip()
        days = max(1, int(days or 30))
        result = {
            "ok": False,
            "campaign_id": cid,
            "lead_id": False,
            "callback_time": False,
            "error": False,
        }
        if not cid or not phone:
            result["error"] = "missing_phone_or_campaign"
            return result

        Session = self.env["doorway.vicidial.agent.session"]
        tails = Session._phone_search_tails(phone)
        if not tails:
            result["error"] = "invalid_phone"
            return result

        safe_comment = (comments or "Rappel Odoo IA")[:255].replace("'", "''")
        use_hostinger = self._is_hostinger_campaign(cid)
        vicidial_user_safe = (vicidial_user or "VDAD")[:20].replace("'", "''")

        def _find_and_schedule(conn):
            cur = conn.cursor(dictionary=True)
            vic_lead_id = False
            list_id = False
            for tail in tails:
                cur.execute(
                    """
                    SELECT vl.lead_id, vl.list_id
                      FROM vicidial_list vl
                      INNER JOIN vicidial_lists vls ON vl.list_id = vls.list_id
                     WHERE vls.campaign_id = %s
                       AND (
                         vl.phone_number LIKE %s
                         OR vl.phone_number LIKE %s
                         OR RIGHT(vl.phone_number, 9) = %s
                       )
                     ORDER BY vl.lead_id DESC
                     LIMIT 1
                    """,
                    (cid, "%" + tail, tail, tail[-9:]),
                )
                row = cur.fetchone()
                if row:
                    vic_lead_id = int(row["lead_id"])
                    list_id = row["list_id"]
                    break
            if not vic_lead_id:
                return False, False, "lead_not_found"
            cur.execute(
                """
                UPDATE vicidial_list
                   SET status = %s, user = %s
                 WHERE lead_id = %s
                """,
                (lead_status, (vicidial_user or "VDAD")[:20], vic_lead_id),
            )
            cur.execute(
                "DELETE FROM vicidial_hopper WHERE lead_id = %s",
                (vic_lead_id,),
            )
            cur.execute(
                """
                UPDATE vicidial_callbacks
                   SET status = 'INACTIVE'
                 WHERE lead_id = %s
                   AND status NOT IN ('INACTIVE', 'DEAD', 'ARCHIVE')
                """,
                (vic_lead_id,),
            )
            cur.execute(
                """
                INSERT INTO vicidial_callbacks (
                    lead_id, list_id, campaign_id, status, entry_time,
                    callback_time, user, recipient, comments, lead_status
                ) VALUES (
                    %s, %s, %s, 'ACTIVE', NOW(),
                    DATE_ADD(NOW(), INTERVAL %s DAY), %s, 'ANYONE', %s, %s
                )
                """,
                (
                    vic_lead_id,
                    list_id,
                    cid,
                    days,
                    (vicidial_user or "VDAD")[:20],
                    safe_comment,
                    lead_status,
                ),
            )
            cur.execute(
                "SELECT callback_time FROM vicidial_callbacks "
                "WHERE lead_id = %s ORDER BY callback_id DESC LIMIT 1",
                (vic_lead_id,),
            )
            cb_row = cur.fetchone()
            conn.commit()
            cb_time = cb_row.get("callback_time") if cb_row else False
            return vic_lead_id, cb_time, None

        try:
            if use_hostinger:
                vic_lead_id = False
                list_id = False
                for tail in tails:
                    rows = self._hostinger_query_rows(
                        """
                        SELECT vl.lead_id, vl.list_id
                          FROM vicidial_list vl
                          INNER JOIN vicidial_lists vls ON vl.list_id = vls.list_id
                         WHERE vls.campaign_id = '%s'
                           AND (
                             vl.phone_number LIKE '%%%s'
                             OR vl.phone_number LIKE '%s'
                             OR RIGHT(vl.phone_number, 9) = '%s'
                           )
                         ORDER BY vl.lead_id DESC
                         LIMIT 1
                        """
                        % (cid, tail[-9:], tail, tail[-9:]),
                        columns=["lead_id", "list_id"],
                    )
                    if rows:
                        vic_lead_id = int(rows[0]["lead_id"])
                        list_id = rows[0]["list_id"]
                        break
                if not vic_lead_id:
                    result["error"] = "lead_not_found"
                    return result
                lid = int(vic_lead_id)
                self._hostinger_execute_sql(
                    "UPDATE vicidial_list SET status='%s', user='%s' WHERE lead_id=%s"
                    % (lead_status, vicidial_user_safe, lid)
                )
                self._hostinger_execute_sql(
                    "DELETE FROM vicidial_hopper WHERE lead_id=%s" % lid
                )
                self._hostinger_execute_sql(
                    "UPDATE vicidial_callbacks SET status='INACTIVE' "
                    "WHERE lead_id=%s AND status NOT IN ('INACTIVE','DEAD','ARCHIVE')"
                    % lid
                )
                self._hostinger_execute_sql(
                    """
                    INSERT INTO vicidial_callbacks (
                        lead_id, list_id, campaign_id, status, entry_time,
                        callback_time, user, recipient, comments, lead_status
                    ) VALUES (
                        %s, %s, '%s', 'ACTIVE', NOW(),
                        DATE_ADD(NOW(), INTERVAL %s DAY), '%s', 'ANYONE', '%s', '%s'
                    )
                    """
                    % (
                        lid,
                        list_id,
                        cid,
                        days,
                        vicidial_user_safe,
                        safe_comment,
                        lead_status,
                    )
                )
                cb_rows = self._hostinger_query_rows(
                    "SELECT callback_time FROM vicidial_callbacks "
                    "WHERE lead_id=%s ORDER BY callback_id DESC LIMIT 1" % lid,
                    columns=["callback_time"],
                )
                result["ok"] = True
                result["lead_id"] = lid
                result["callback_time"] = cb_rows[0]["callback_time"] if cb_rows else False
                return result

            if not self.is_available():
                result["error"] = "mysql_unavailable"
                return result
            conn = self._connect(campaign_id=cid)
            try:
                vic_lead_id, cb_time, err = _find_and_schedule(conn)
            finally:
                conn.close()
            if err:
                result["error"] = err
                return result
            result["ok"] = True
            result["lead_id"] = vic_lead_id
            result["callback_time"] = cb_time
            return result
        except Exception as exc:  # noqa: BLE001
            _logger.exception("schedule_vicidial_callback %s %s", cid, phone)
            result["error"] = str(exc)
            return result

    def apply_ia_refusal_status(self, phone, campaign_id, qual, vicidial_user="VDAD"):
        """Marque un refus sur vicidial_list (NI/DNC), purge hopper, annule rappels actifs."""
        cid = self._sanitize_vicidial_id(campaign_id)
        phone = (phone or "").strip()
        qual = (qual or "").strip()
        vic_status = self.map_crm_qualification_to_vicidial_status(qual)
        if vic_status not in ("NI", "DNC"):
            vic_status = "NI"
        result = {
            "ok": False,
            "campaign_id": cid,
            "lead_id": False,
            "vicidial_status": vic_status,
            "callbacks_deactivated": 0,
            "error": False,
        }
        if not cid or not phone:
            result["error"] = "missing_phone_or_campaign"
            return result

        Session = self.env["doorway.vicidial.agent.session"]
        tails = Session._phone_search_tails(phone)
        if not tails:
            result["error"] = "invalid_phone"
            return result

        use_hostinger = self._is_hostinger_campaign(cid)
        vicidial_user_safe = (vicidial_user or "VDAD")[:20].replace("'", "''")

        def _apply_refusal(conn):
            cur = conn.cursor(dictionary=True)
            vic_lead_id = False
            for tail in tails:
                cur.execute(
                    """
                    SELECT vl.lead_id
                      FROM vicidial_list vl
                      INNER JOIN vicidial_lists vls ON vl.list_id = vls.list_id
                     WHERE vls.campaign_id = %s
                       AND (
                         vl.phone_number LIKE %s
                         OR vl.phone_number LIKE %s
                         OR RIGHT(vl.phone_number, 9) = %s
                       )
                     ORDER BY vl.lead_id DESC
                     LIMIT 1
                    """,
                    (cid, "%" + tail, tail, tail[-9:]),
                )
                row = cur.fetchone()
                if row:
                    vic_lead_id = int(row["lead_id"])
                    break
            if not vic_lead_id:
                return False, 0, "lead_not_found"
            cur.execute(
                """
                UPDATE vicidial_list
                   SET status = %s, user = %s
                 WHERE lead_id = %s
                """,
                (vic_status, (vicidial_user or "VDAD")[:20], vic_lead_id),
            )
            cur.execute(
                "DELETE FROM vicidial_hopper WHERE lead_id = %s",
                (vic_lead_id,),
            )
            cur.execute(
                """
                UPDATE vicidial_callbacks
                   SET status = 'INACTIVE'
                 WHERE lead_id = %s
                   AND status NOT IN ('INACTIVE', 'DEAD', 'ARCHIVE')
                """,
                (vic_lead_id,),
            )
            deactivated = cur.rowcount
            conn.commit()
            return vic_lead_id, deactivated, None

        try:
            if use_hostinger:
                vic_lead_id = False
                for tail in tails:
                    rows = self._hostinger_query_rows(
                        """
                        SELECT vl.lead_id
                          FROM vicidial_list vl
                          INNER JOIN vicidial_lists vls ON vl.list_id = vls.list_id
                         WHERE vls.campaign_id = '%s'
                           AND (
                             vl.phone_number LIKE '%%%s'
                             OR vl.phone_number LIKE '%s'
                             OR RIGHT(vl.phone_number, 9) = '%s'
                           )
                         ORDER BY vl.lead_id DESC
                         LIMIT 1
                        """
                        % (cid, tail[-9:], tail, tail[-9:]),
                        columns=["lead_id"],
                    )
                    if rows:
                        vic_lead_id = int(rows[0]["lead_id"])
                        break
                if not vic_lead_id:
                    result["error"] = "lead_not_found"
                    return result
                lid = int(vic_lead_id)
                self._hostinger_execute_sql(
                    "UPDATE vicidial_list SET status='%s', user='%s' WHERE lead_id=%s"
                    % (vic_status, vicidial_user_safe, lid)
                )
                self._hostinger_execute_sql(
                    "DELETE FROM vicidial_hopper WHERE lead_id=%s" % lid
                )
                self._hostinger_execute_sql(
                    "UPDATE vicidial_callbacks SET status='INACTIVE' "
                    "WHERE lead_id=%s AND status NOT IN ('INACTIVE','DEAD','ARCHIVE')"
                    % lid
                )
                result["ok"] = True
                result["lead_id"] = lid
                return result

            if not self.is_available():
                result["error"] = "mysql_unavailable"
                return result
            conn = self._connect(campaign_id=cid)
            try:
                vic_lead_id, deactivated, err = _apply_refusal(conn)
            finally:
                conn.close()
            if err:
                result["error"] = err
                return result
            result["ok"] = True
            result["lead_id"] = vic_lead_id
            result["callbacks_deactivated"] = deactivated
            return result
        except Exception as exc:  # noqa: BLE001
            _logger.exception("apply_ia_refusal_status %s %s", cid, phone)
            result["error"] = str(exc)
            return result

    @staticmethod
    def map_amd_from_pipeline(amd_result, duration=0):
        s = (amd_result or "").lower()
        if s in ("human", "person"):
            return "human"
        if s in ("machine", "not_sure", "fax", "answering_machine"):
            return "answering_machine"
        if int(duration or 0) > 0:
            return "human"
        return "no_answer"

    def _web_base_url(self):
        return (self._icp.get_param("web.base.url") or "").rstrip("/")

    def _recording_proxy_url(self, uniqueid):
        base = self._web_base_url()
        if not base or not uniqueid:
            return False
        return "%s/doorway/vicidial/recording/%s" % (base, uniqueid)

    def get_recording_file_path(self, uniqueid):
        if not uniqueid:
            return False
        row = self._fetch_recording_row(uniqueid)
        if not row:
            return False
        location = (row.get("location") or "").strip()
        filename = (row.get("filename") or "").strip()
        candidates = []
        if location:
            candidates.append(location)
            if filename and filename not in location:
                candidates.append(os.path.join(location, filename))
        monitor = "/var/spool/asterisk/monitor"
        if filename:
            candidates.extend(
                [
                    os.path.join(monitor, filename),
                    os.path.join(monitor, "ivr", filename),
                    os.path.join(monitor, "MIX", filename),
                    os.path.join(monitor, "DONE", filename),
                ]
            )
        for path in candidates:
            if path and os.path.isfile(path):
                return path
        # Recherche recursive dans tous les sous-dossiers de monitor
        if filename:
            import glob
            matches = glob.glob(os.path.join(monitor, '**', filename), recursive=True)
            if matches:
                return matches[0]
        return False

    def _fetch_recording_row(self, uniqueid):
        conn = self._connect()
        try:
            cur = conn.cursor(dictionary=True)
            pattern = "%%%s%%" % uniqueid
            cur.execute(
                """
                SELECT filename, location
                FROM recording_log
                WHERE filename LIKE %s OR vicidial_id = %s
                ORDER BY recording_id DESC
                LIMIT 1
                """,
                (pattern, uniqueid),
            )
            row = cur.fetchone()
            cur.close()
            return row
        except Exception as exc:
            _logger.debug("recording_log lookup failed for %s: %s", uniqueid, exc)
            return False
        finally:
            conn.close()

    def _sofia_recordings_config(self):
        base_url = self._icp.get_param(
            "doorway_vicidial_campaigns.sofia_recordings_url",
            "https://intellixcrm.com/sofia-recordings",
        ).rstrip("/")
        rec_dir = self._icp.get_param(
            "doorway_vicidial_campaigns.sofia_recordings_path",
            "/var/www/sofia-recordings",
        )
        return base_url, rec_dir

    def _lea_recordings_config(self):
        base_url = self._icp.get_param(
            "doorway_vicidial_campaigns.lea_recordings_url",
            "https://intellixcrm.com/lea-recordings",
        ).rstrip("/")
        rec_dir = self._icp.get_param(
            "doorway_vicidial_campaigns.lea_recordings_path",
            "/var/www/lea-recordings",
        )
        return base_url, rec_dir

    def resolve_lea_recording_url(self, uniqueid):
        """Dernier WAV archivé par l'AGI Léa QC ({uid}_{turn}.wav ou _full.wav)."""
        uid = str(uniqueid or "").strip()
        epoch = self._uniqueid_epoch(uid)
        if not epoch:
            return False
        base_url, rec_dir = self._lea_recordings_config()
        if not os.path.isdir(rec_dir):
            return False
        patterns = [
            os.path.join(rec_dir, "%s_*.wav" % uid),
            os.path.join(rec_dir, "%s.*_*.wav" % epoch),
            os.path.join(rec_dir, "%s_*.wav" % epoch),
            os.path.join(rec_dir, "hostinger-ivr", "ia_%s_*.wav" % epoch),
        ]
        matches = []
        for pattern in patterns:
            matches.extend(glob.glob(pattern))
        matches = [p for p in matches if os.path.getsize(p) > 44]
        if not matches:
            return False
        full = [p for p in matches if p.endswith("_full.wav")]
        if full:
            best = full[0]
        else:
            def _turn(path):
                base = os.path.basename(path)
                try:
                    return int(base.rsplit("_", 1)[-1].replace(".wav", ""))
                except ValueError:
                    return -1

            best = max(matches, key=lambda p: (os.path.getmtime(p), _turn(p)))
        rel = os.path.relpath(best, rec_dir).replace("\\", "/")
        return "%s/%s" % (base_url, rel)

    def _uniqueid_epoch(self, uniqueid):
        uid = str(uniqueid or "").strip()
        if not uid:
            return ""
        return uid.split(".", 1)[0]

    @staticmethod
    def is_sofia_conversation(payload):
        """True si appel humain avec dialogue réel (pas répondeur / vide / AMD machine)."""
        payload = payload or {}
        amd = (
            payload.get("amd_result")
            or payload.get("amd_status")
            or payload.get("AMDSTATUS")
            or ""
        )
        amd = str(amd).lower()
        if amd in (
            "machine",
            "fax",
            "answering_machine",
            "amd_hangup",
            "not_sure",
        ):
            return False
        transcript = (payload.get("transcript") or "").strip()
        duration = int(
            payload.get("duration_sec")
            or payload.get("duration_seconds")
            or payload.get("duration")
            or 0
        )
        min_chars = 12
        min_dur = 8
        rec = (payload.get("recording_url") or "").strip()
        if rec.startswith(("http://", "https://")) and duration >= min_dur:
            return True
        if len(transcript) >= min_chars:
            return True
        if duration >= min_dur and len(transcript) > 0:
            return True
        if duration >= min_dur and amd == "human":
            return True
        return False

    def resolve_sofia_recording_url(self, uniqueid):
        """Dernier WAV archivé par l'AGI Sofia ({epoch}_{turn}.wav)."""
        uid = str(uniqueid or "").strip()
        epoch = self._uniqueid_epoch(uid)
        if not epoch:
            return False
        base_url, rec_dir = self._sofia_recordings_config()
        if not os.path.isdir(rec_dir):
            return False
        patterns = [
            os.path.join(rec_dir, "%s_*.wav" % uid),
            os.path.join(rec_dir, "%s.*_*.wav" % epoch),
            os.path.join(rec_dir, "%s_*.wav" % epoch),
            os.path.join(rec_dir, "hostinger-ivr", "ia_%s_*.wav" % epoch),
        ]
        matches = []
        for pattern in patterns:
            matches.extend(glob.glob(pattern))
        matches = [p for p in matches if os.path.getsize(p) > 44]
        if not matches:
            return False
        full = [p for p in matches if p.endswith("_full.wav")]
        if full:
            best = full[0]
        else:
            def _turn(path):
                base = os.path.basename(path)
                try:
                    return int(base.rsplit("_", 1)[-1].replace(".wav", ""))
                except ValueError:
                    return -1

            best = max(matches, key=lambda p: (os.path.getmtime(p), _turn(p)))
        return "%s/%s" % (base_url, os.path.basename(best))

    def _pick_recording_url(self, old_url, new_url):
        new_url = (new_url or "").strip()
        old_url = (old_url or "").strip()
        if not new_url:
            return old_url or False
        if not old_url:
            return new_url
        if old_url.startswith("file://") and new_url.startswith("https://"):
            return new_url
        if "sofia-recordings" in new_url:
            if "sofia-recordings" not in old_url:
                return new_url

            def _turn(url):
                match = re.search(r"_(\d+)\.wav", url)
                return int(match.group(1)) if match else 0

            return new_url if _turn(new_url) >= _turn(old_url) else old_url
        return new_url

    def normalize_recording_url(self, raw_url, uniqueid=None):
        raw = (raw_url or "").strip()
        if raw.startswith(("http://", "https://")):
            if "sofia-recordings" in raw:
                return raw
            if uniqueid:
                sofia = self.resolve_sofia_recording_url(uniqueid)
                if sofia and "sofia-recordings" not in raw:
                    return sofia
            return raw
        if raw.startswith("file://"):
            raw = raw[7:]
        row = self._fetch_recording_row(uniqueid) if uniqueid else False
        if row:
            location = (row.get("location") or "").strip()
            if location.startswith(("http://", "https://")):
                return location
            if location or raw:
                proxy = self._recording_proxy_url(uniqueid)
                if proxy:
                    return proxy
        vicidial_web = self._icp.get_param(
            "doorway_vicidial_campaigns.recording_base_url"
        )
        if vicidial_web and row and row.get("filename"):
            return "%s/%s" % (vicidial_web.rstrip("/"), row["filename"])
        if raw and os.path.isfile(raw) and uniqueid:
            return self._recording_proxy_url(uniqueid) or raw
        if uniqueid:
            sofia = self.resolve_sofia_recording_url(uniqueid)
            if sofia:
                return sofia
            lea = self.resolve_lea_recording_url(uniqueid)
            if lea:
                return lea
        return raw or False

    def _resolve_campaign_from_payload(self, payload, company_id=False):
        Campaign = self.env["doorway.campaign"].sudo()
        cid = (payload.get("campaign_id") or payload.get("campaign") or "")[:8]
        if cid:
            camp = Campaign.search([("vicidial_campaign_id", "=", cid)], limit=1)
            if camp:
                return camp
        if company_id:
            return Campaign.search(
                [("company_id", "=", company_id)],
                order="id desc",
                limit=1,
            )
        return Campaign.browse()


    def _ia_agent_label(self, campaign_vicidial_id, agent_login):
        cid = (campaign_vicidial_id or "")[:8]
        login = (agent_login or "").strip()
        if cid in IA_AGENT_LABELS and (
            login in ("", "VDAD", "VDCL")
            or login.startswith("86")
            or (login.isdigit() and len(login) >= 5)
        ):
            return IA_AGENT_LABELS[cid]
        return IA_AGENT_LABELS.get(cid) if cid in IA_REMOTE_AGENT_EXTEN else None

    def _resolve_human_agent(self, vicidial_user):
        login = (vicidial_user or "").strip()
        if not login:
            return self.env["doorway.campaign.agent.user"].browse()
        return self.env["doorway.campaign.agent.user"].sudo().search(
            [("vicidial_user", "=", login)],
            limit=1,
        )

    def _resolve_agent_name(self, payload, campaign):
        human = self._resolve_human_agent(
            payload.get("user")
            or payload.get("vicidial_user")
            or payload.get("agent")
            or payload.get("agent_name")
        )
        if human:
            return human.full_name or human.user_id.name or human.vicidial_user
        agent_key = payload.get("agent_id") or payload.get("agent_external_id")
        Agent = self.env["doorway.agent.profile"].sudo()
        if agent_key:
            agent = Agent.search([("external_agent_id", "=", agent_key)], limit=1)
            if agent:
                return agent.name
        if campaign.ia_agent_id:
            return campaign.ia_agent_id.name
        return (
            payload.get("agent_name")
            or payload.get("user")
            or payload.get("agent")
            or False
        )

    def _prepare_call_log_vals(self, payload, company_id=False, skip_lead_lookup=False):
        vicidial_call_id = (
            payload.get("vicidial_call_id")
            or payload.get("uniqueid")
            or payload.get("unique_id")
            or payload.get("call_sid")
            or payload.get("CallSid")
        )
        if not vicidial_call_id:
            return False
        campaign = self._resolve_campaign_from_payload(payload, company_id=company_id)
        if not campaign:
            return False
        duration = int(
            payload.get("duration")
            or payload.get("length_in_sec")
            or payload.get("duration_seconds")
            or payload.get("duration_sec")
            or 0
        )
        amd_raw = (
            payload.get("amd_result")
            or payload.get("amd_status")
            or payload.get("AMDSTATUS")
        )
        status = payload.get("status") or payload.get("disposition")
        disp_raw = payload.get("disposition")
        valid_disp = {"VENTE", "INTERET", "RAPPEL", "REFUS", "REPONDEUR", "INVALIDE"}
        amd_result = self.map_amd_from_vicidial(
            amd_raw,
            status=status,
            amd_action=payload.get("amd_action"),
        )
        if not amd_result and amd_raw:
            amd_result = self.map_amd_from_pipeline(amd_raw, duration=duration)
        phone = (
            payload.get("phone_number")
            or payload.get("phone")
            or payload.get("telephone")
            or payload.get("telefono")
            or payload.get("to")
            or payload.get("from")
        )
        raw_rec = (
            payload.get("recording_url")
            or payload.get("recording")
            or payload.get("RecordingUrl")
            or payload.get("audio_url")
            or payload.get("url_enregistrement")
        )
        is_conv = self.is_sofia_conversation(payload)
        if not is_conv:
            raw_rec = False
        if (
            skip_lead_lookup
            and raw_rec
            and str(raw_rec).strip().startswith(("http://", "https://"))
        ):
            recording_url = str(raw_rec).strip()
        elif is_conv:
            recording_url = self.normalize_recording_url(
                raw_rec, vicidial_call_id
            ) or self.resolve_sofia_recording_url(vicidial_call_id)
        else:
            recording_url = False
        vals = {
            "campaign_id": campaign.id,
            "vicidial_call_id": str(vicidial_call_id),
            "phone_number": phone,
            "call_date": payload.get("call_date") or fields.Datetime.now(),
            "duration": duration,
            "amd_result": amd_result or False,
            "disposition": disp_raw
            if disp_raw in valid_disp
            else self.map_disposition_from_vicidial(status)
            or False,
            "agent_name": self._resolve_agent_name(payload, campaign),
            "recording_url": recording_url,
        }
        human = self._resolve_human_agent(
            payload.get("user")
            or payload.get("vicidial_user")
            or payload.get("agent")
        )
        if human:
            vals["human_agent_id"] = human.id
        if not skip_lead_lookup:
            lead = self._find_lead_for_call(vals.get("phone_number"), vicidial_call_id)
            if lead:
                vals["lead_id"] = lead.id
        consent_raw = payload.get("consent_captured")
        if consent_raw in (True, "true", "True", 1, "1", "oui", "OUI", "yes"):
            vals["consent_captured"] = True
        elif consent_raw in (False, "false", "False", 0, "0", "non", "NON", "no"):
            vals["consent_captured"] = False
        if payload.get("consent_notes"):
            vals["consent_notes"] = payload.get("consent_notes")
        if self._is_voicemail_call(
            vals.get("amd_result"), vals.get("disposition"), status
        ):
            vals["recording_url"] = False
        return vals

    def _find_call_log_by_uniqueid(self, uid):
        CallLog = self.env["doorway.call.log"].sudo()
        uid = str(uid or "").strip()
        if not uid:
            return CallLog.browse()
        rec = CallLog.search([("vicidial_call_id", "=", uid)], limit=1)
        if rec:
            return rec
        epoch = self._uniqueid_epoch(uid)
        if epoch:
            rec = CallLog.search(
                [("vicidial_call_id", "=like", epoch + ".%")],
                order="call_date desc, id desc",
                limit=1,
            )
            if rec:
                return rec
        return CallLog.browse()

    def _sofia_duration_from_recordings(self, uniqueid):
        uid = str(uniqueid or "").strip()
        epoch = self._uniqueid_epoch(uid)
        if not epoch:
            return 0
        _, rec_dir = self._sofia_recordings_config()
        if not os.path.isdir(rec_dir):
            return 0
        patterns = [
            os.path.join(rec_dir, "%s_*.wav" % uid),
            os.path.join(rec_dir, "%s.*_*.wav" % epoch),
        ]
        total_bytes = 0
        for pattern in patterns:
            for path in glob.glob(pattern):
                try:
                    total_bytes += max(0, os.path.getsize(path) - 44)
                except OSError:
                    pass
        return max(1, total_bytes // 8000) if total_bytes > 44 else 0

    def _vicidial_row_for_epoch(self, campaign_vicidial_id, epoch):
        cid = self._sanitize_vicidial_id(campaign_vicidial_id)
        if not epoch:
            return {}
        if self._is_hostinger_campaign(cid):
            try:
                rows = self._hostinger_query_rows(
                    """
                    SELECT phone_number, call_date, length_in_sec, status, uniqueid
                    FROM vicidial_log
                    WHERE campaign_id = '%s' AND uniqueid LIKE '%s.%%'
                    ORDER BY call_date DESC LIMIT 1
                    """
                    % (cid, re.sub(r"[^0-9]", "", str(epoch))),
                    columns=[
                        "phone_number",
                        "call_date",
                        "length_in_sec",
                        "status",
                        "uniqueid",
                    ],
                )
                return rows[0] if rows else {}
            except Exception as exc:
                _logger.debug("hostinger vicidial row lookup %s: %s", epoch, exc)
                return {}
        try:
            conn = self._connect(campaign_id=cid)
        except Exception as exc:
            _logger.debug("vicidial connect %s: %s", cid, exc)
            return {}
        try:
            cur = conn.cursor(dictionary=True)
            cur.execute(
                """
                SELECT phone_number, call_date, length_in_sec, status, uniqueid
                FROM vicidial_log
                WHERE campaign_id = %s AND uniqueid LIKE %s
                ORDER BY call_date DESC LIMIT 1
                """,
                (cid, epoch + ".%"),
            )
            row = cur.fetchone() or {}
            cur.close()
            return row
        except Exception as exc:
            _logger.debug("vicidial row lookup %s: %s", epoch, exc)
            return {}
        finally:
            conn.close()

    def backfill_sofia_recordings(self, campaign_vicidial_id, limit=500, fast_only=False):
        """Rattache WAV + durées Sofia aux doorway.call.log."""
        camp = self.env["doorway.campaign"].sudo().search(
            [("vicidial_campaign_id", "=", campaign_vicidial_id)], limit=1
        )
        if not camp:
            return {"patched": 0, "scanned": 0, "created": 0}
        fast = self._patch_recent_call_log_recordings(camp, limit=limit)
        if fast_only:
            return {"patched": fast, "created": 0, "scanned": 0, "fast": fast}
        CallLog = self.env["doorway.call.log"].sudo()
        _, rec_dir = self._sofia_recordings_config()
        patched = 0
        created = 0
        groups = {}
        if os.path.isdir(rec_dir):
            for path in glob.glob(os.path.join(rec_dir, "*_*.wav")):
                base = os.path.basename(path)
                match = re.match(r"^(\d+\.\d+)_(?:full|\d+)\.wav$", base)
                if not match:
                    continue
                sid = match.group(1)
                try:
                    size = os.path.getsize(path)
                except OSError:
                    continue
                if size <= 44:
                    continue
                groups.setdefault(sid, []).append(path)
        for sid in sorted(groups.keys(), reverse=True)[:limit]:
            rec = self.resolve_sofia_recording_url(sid)
            if not rec:
                continue
            duration = self._sofia_duration_from_recordings(sid)
            log = self._find_call_log_by_uniqueid(sid)
            if not log:
                epoch = self._uniqueid_epoch(sid)
                row = self._vicidial_row_for_epoch(campaign_vicidial_id, epoch)
                if row:
                    vals = self._prepare_call_log_vals(
                        {
                            "vicidial_call_id": row.get("uniqueid") or sid,
                            "campaign": campaign_vicidial_id,
                            "phone_number": row.get("phone_number"),
                            "call_date": row.get("call_date"),
                            "duration": duration or int(row.get("length_in_sec") or 0),
                            "status": row.get("status"),
                            "recording_url": rec,
                        }
                    )
                    if vals:
                        if not self._is_voicemail_call(
                            vals.get("amd_result"),
                            vals.get("disposition"),
                            row.get("status"),
                        ):
                            vals["recording_url"] = rec
                        if duration:
                            vals["duration"] = duration
                        log = CallLog.create(vals)
                        created += 1
                        continue
            if not log:
                continue
            if self._is_voicemail_call(log.amd_result, log.disposition):
                continue
            patch = {}
            merged_rec = self._pick_recording_url(log.recording_url, rec)
            if merged_rec and merged_rec != (log.recording_url or ""):
                patch["recording_url"] = merged_rec
            if duration and (log.duration or 0) < duration:
                patch["duration"] = duration
            if patch:
                log.write(patch)
                patched += 1
        return {
            "patched": patched + fast,
            "created": created,
            "scanned": len(groups),
            "fast": fast,
        }

    def _lea_duration_from_recordings(self, uniqueid):
        uid = str(uniqueid or "").strip()
        epoch = self._uniqueid_epoch(uid)
        if not epoch:
            return 0
        _, rec_dir = self._lea_recordings_config()
        if not os.path.isdir(rec_dir):
            return 0
        patterns = [
            os.path.join(rec_dir, "%s_*.wav" % uid),
            os.path.join(rec_dir, "%s.*_*.wav" % epoch),
        ]
        total_bytes = 0
        for pattern in patterns:
            for path in glob.glob(pattern):
                try:
                    total_bytes += max(0, os.path.getsize(path) - 44)
                except OSError:
                    pass
        return max(1, total_bytes // 8000) if total_bytes > 44 else 0

    def pull_hostinger_recordings(self):
        """Rsync WAV Hostinger → /var/www/lea-recordings/ (script système)."""
        import subprocess

        script = self._icp.get_param(
            "doorway_vicidial_campaigns.hostinger_recordings_pull_script",
            "/usr/local/bin/intellix-pull-hostinger-recordings.sh",
        )
        if not os.path.isfile(script):
            return {"ok": False, "error": "script missing"}
        try:
            proc = subprocess.run(
                ["sudo", script],
                capture_output=True,
                text=True,
                timeout=180,
                check=False,
            )
            return {
                "ok": proc.returncode == 0,
                "stdout": (proc.stdout or "")[-500:],
                "stderr": (proc.stderr or "")[-500:],
            }
        except Exception as exc:  # noqa: BLE001
            return {"ok": False, "error": str(exc)}

    def _patch_recent_call_log_recordings(self, camp, limit=200):
        """Rattache enregistrements aux logs récents sans scan complet du répertoire."""
        CallLog = self.env["doorway.call.log"].sudo()
        cid = (camp.vicidial_campaign_id or "")[:8]
        if cid in LEA_QC_CAMPAIGN_IDS or cid in DOOR_APP0_QC_CAMPAIGN_IDS:
            resolve_rec = self.resolve_lea_recording_url
            duration_fn = self._lea_duration_from_recordings
        else:
            resolve_rec = self.resolve_sofia_recording_url
            duration_fn = self._sofia_duration_from_recordings
        logs = CallLog.search(
            [
                ("campaign_id", "=", camp.id),
                "|",
                ("recording_url", "=", False),
                ("duration", "<=", 0),
            ],
            order="call_date desc",
            limit=limit,
        )
        patched = 0
        for log in logs:
            uid = log.vicidial_call_id
            if not uid:
                continue
            if self._is_voicemail_call(
                log.amd_result, log.disposition
            ):
                continue
            rec = resolve_rec(uid)
            if not rec:
                continue
            patch = {"recording_url": rec}
            dur = duration_fn(uid)
            if dur and (log.duration or 0) < dur:
                patch["duration"] = dur
            log.write(patch)
            patched += 1
        return patched

    def sync_hostinger_campaign_background(self, campaign, limit=15):
        """Sync Hostinger léger (sans rsync ni scan WAV complet)."""
        cid = (campaign.vicidial_campaign_id or "")[:8]
        if not self._is_hostinger_campaign(cid):
            return {"sync": {}, "fast": 0}
        sync = self.sync_call_logs(campaign, limit=limit, fast=True)
        fast = self._patch_recent_call_log_recordings(campaign, limit=limit)
        return {"sync": sync, "fast": fast}

    def backfill_lea_recordings(self, campaign_vicidial_id="DW_QCB2C", limit=500, fast_only=False):
        """Rattache WAV + durées Léa QC aux doorway.call.log."""
        camp = self.env["doorway.campaign"].sudo().search(
            [("vicidial_campaign_id", "=", campaign_vicidial_id)], limit=1
        )
        if not camp:
            return {"patched": 0, "scanned": 0, "created": 0}
        fast = self._patch_recent_call_log_recordings(camp, limit=limit)
        if fast_only:
            return {"patched": fast, "created": 0, "scanned": 0, "fast": fast}
        CallLog = self.env["doorway.call.log"].sudo()
        _, rec_dir = self._lea_recordings_config()
        patched = 0
        created = 0
        groups = {}
        if os.path.isdir(rec_dir):
            for path in glob.glob(os.path.join(rec_dir, "*_*.wav")):
                base = os.path.basename(path)
                match = re.match(r"^(\d+\.\d+)_(?:full|\d+)\.wav$", base)
                if not match:
                    continue
                sid = match.group(1)
                try:
                    size = os.path.getsize(path)
                except OSError:
                    continue
                if size <= 44:
                    continue
                groups.setdefault(sid, []).append(path)
        for sid in sorted(groups.keys(), reverse=True)[:limit]:
            rec = self.resolve_lea_recording_url(sid)
            if not rec:
                continue
            duration = self._lea_duration_from_recordings(sid)
            log = self._find_call_log_by_uniqueid(sid)
            if not log:
                epoch = self._uniqueid_epoch(sid)
                row = self._vicidial_row_for_epoch(campaign_vicidial_id, epoch)
                if row:
                    row_status = row.get("status")
                    row_dur = duration or int(row.get("length_in_sec") or 0)
                    amd = self._infer_amd_for_hostinger_call(
                        row.get("uniqueid") or sid,
                        status=row_status,
                        duration=row_dur,
                        use_agi=True,
                    )
                    vals = self._prepare_call_log_vals(
                        {
                            "vicidial_call_id": row.get("uniqueid") or sid,
                            "campaign": campaign_vicidial_id,
                            "phone_number": row.get("phone_number"),
                            "call_date": row.get("call_date"),
                            "duration": row_dur,
                            "status": row_status,
                            "recording_url": rec,
                            "amd_result": amd,
                        }
                    )
                    if vals:
                        if self._is_voicemail_call(
                            amd, vals.get("disposition"), row_status
                        ):
                            vals["recording_url"] = False
                        else:
                            vals["recording_url"] = rec
                        if duration:
                            vals["duration"] = duration
                        if amd:
                            vals["amd_result"] = amd
                            if amd in ("amd_hangup", "answering_machine"):
                                vals.setdefault("disposition", "REPONDEUR")
                                vals["recording_url"] = False
                        CallLog.create(vals)
                        created += 1
                        continue
            if not log:
                continue
            if self._is_voicemail_call(log.amd_result, log.disposition):
                continue
            patch = {}
            merged_rec = self._pick_recording_url(log.recording_url, rec)
            if merged_rec and merged_rec != (log.recording_url or ""):
                patch["recording_url"] = merged_rec
            if duration and (log.duration or 0) < duration:
                patch["duration"] = duration
            if log.amd_result == "human":
                inferred = self._infer_amd_for_hostinger_call(
                    sid, duration=duration or log.duration, use_agi=True
                )
                if inferred and inferred != "human":
                    patch["amd_result"] = inferred
                    if inferred in ("amd_hangup", "answering_machine"):
                        patch.setdefault("disposition", "REPONDEUR")
                        patch["recording_url"] = False
            if patch:
                log.write(patch)
                patched += 1
        return {
            "patched": patched + fast,
            "created": created,
            "scanned": len(groups),
            "fast": fast,
        }

    def _apply_call_log_side_effects(self, log_rec):
        if not log_rec:
            return
        if log_rec._is_renofacile_call():
            log_rec._apply_recording_retention_policy()
        self._sync_coaching_from_call_log(log_rec)

    def _schedule_call_log_enrichment(self, log_id, payload=None):
        """Enrichissement différé (lead, durée WAV, coaching) après réponse HTTP."""
        dbname = self.env.cr.dbname
        payload = dict(payload or {})

        def _worker():
            try:
                from odoo.modules.registry import Registry

                with Registry(dbname).cursor() as cr:
                    env = api.Environment(cr, SUPERUSER_ID, {})
                    VicidialService(env)._enrich_call_log_recording(log_id, payload)
                    cr.commit()
            except Exception as exc:
                _logger.exception(
                    "call log enrichment failed id=%s: %s", log_id, exc
                )

        @self.env.cr.postcommit.add
        def _run_enrichment():
            threading.Thread(
                target=_worker,
                daemon=True,
                name="call-log-enrich-%s" % log_id,
            ).start()

    def _enrich_call_log_recording(self, log_id, payload=None):
        """Complète doorway.call.log : lead, durée, rétention, coaching, contact campagne."""
        log_rec = self.env["doorway.call.log"].sudo().browse(log_id)
        if not log_rec.exists():
            return
        payload = payload or {}
        patch = {}
        if not log_rec.lead_id:
            lead = self._find_lead_for_call(
                log_rec.phone_number, log_rec.vicidial_call_id
            )
            if lead:
                patch["lead_id"] = lead.id
        if int(log_rec.duration or 0) <= 0:
            dur = int(
                payload.get("duration_sec")
                or payload.get("duration_seconds")
                or payload.get("duration")
                or 0
            )
            if dur <= 0:
                cid = (log_rec.campaign_id.vicidial_campaign_id or "")[:8]
                if cid in LEA_QC_CAMPAIGN_IDS or cid in DOOR_APP0_QC_CAMPAIGN_IDS:
                    dur = self._lea_duration_from_recordings(log_rec.vicidial_call_id)
                else:
                    dur = self._sofia_duration_from_recordings(log_rec.vicidial_call_id)
            if dur > 0:
                patch["duration"] = dur
        if not log_rec.recording_url and log_rec.vicidial_call_id:
            cid = (log_rec.campaign_id.vicidial_campaign_id or "")[:8]
            if cid in LEA_QC_CAMPAIGN_IDS or cid in DOOR_APP0_QC_CAMPAIGN_IDS:
                rec = self.resolve_lea_recording_url(log_rec.vicidial_call_id)
            else:
                rec = self.resolve_sofia_recording_url(log_rec.vicidial_call_id)
            if rec:
                patch["recording_url"] = rec
        disp = (payload.get("disposition") or payload.get("statut") or "").upper()
        valid_disp = {"VENTE", "INTERET", "RAPPEL", "REFUS", "REPONDEUR", "INVALIDE"}
        if disp in valid_disp and not log_rec.disposition:
            patch["disposition"] = disp
        elif payload.get("lead_ganador") in (True, "true", "OUI", "oui", 1, "1"):
            patch.setdefault("disposition", "INTERET")
        if patch:
            log_rec.write(patch)
        self._sync_campaign_contact_from_call_log(log_rec, payload)
        self._apply_call_log_side_effects(log_rec)

    def _sync_campaign_contact_from_call_log(self, log, payload):
        phone = (
            log.phone_number
            or payload.get("telephone")
            or payload.get("phone")
            or payload.get("phone_number")
            or ""
        ).strip()
        if not phone or not log.campaign_id:
            return
        Contact = self.env["doorway.campaign.contact"].sudo()
        contact = Contact.search(
            [
                ("campaign_id", "=", log.campaign_id.id),
                ("phone_number", "=", phone),
            ],
            limit=1,
        )
        if not contact:
            return
        note = (
            payload.get("notes")
            or payload.get("consent_notes")
            or payload.get("transcript")
            or ""
        )
        patch = {"state": "called"}
        if note and not (contact.ai_note or "").strip():
            patch["ai_note"] = str(note)[:2000]
        contact.write(patch)

    def _save_call_log(self, vals, defer_side_effects=False, payload=None):
        if not vals:
            return False
        uid = vals.get("vicidial_call_id")
        existing = self._find_call_log_by_uniqueid(uid)
        new_rec = vals.get("recording_url")
        if not new_rec and uid and not defer_side_effects:
            conv = payload or vals
            if self.is_sofia_conversation(conv):
                new_rec = (
                    self.resolve_sofia_recording_url(uid)
                    or self.normalize_recording_url(False, uid)
                )
            else:
                campaign = self._vicidial_campaign_from_conv(conv)
                amd = (conv.get("amd_result") or vals.get("amd_result") or "").lower()
                dur = int(
                    conv.get("duration")
                    or conv.get("duration_sec")
                    or conv.get("duration_seconds")
                    or vals.get("duration")
                    or 0
                )
                if campaign in DOOR_APP0_QC_CAMPAIGN_IDS and amd == "human" and dur >= 8:
                    new_rec = self.resolve_lea_recording_url(uid)
        if existing:
            patch = {k: v for k, v in vals.items() if v is not False}
            if int(patch.get("duration") or 0) <= 0:
                patch.pop("duration", None)
            merged_rec = self._pick_recording_url(existing.recording_url, new_rec)
            if merged_rec:
                patch["recording_url"] = merged_rec
            elif not patch.get("recording_url"):
                patch.pop("recording_url", None)
            existing.write(patch)
            log_rec = existing
        else:
            if not new_rec and not defer_side_effects:
                new_rec = self.normalize_recording_url(False, uid)
            vals["recording_url"] = new_rec or False
            log_rec = self.env["doorway.call.log"].sudo().create(vals)
        if defer_side_effects:
            self._schedule_call_log_enrichment(log_rec.id, payload or {})
        else:
            self._apply_call_log_side_effects(log_rec)
        return log_rec

    def upsert_sofia_call_recording(self, payload, company_id=False, fast=True):
        """Crée ou met à jour doorway.call.log dès qu'un enregistrement Sofia est prêt."""
        uid = (
            payload.get("call_sid")
            or payload.get("vicidial_call_id")
            or payload.get("uniqueid")
        )
        if not uid:
            return False
        raw_rec = (payload.get("recording_url") or "").strip()
        if not raw_rec.startswith(("http://", "https://")) and not self.is_sofia_conversation(
            payload
        ):
            _logger.info(
                "sofia call-recording skipped (non-conversation) uid=%s amd=%s dur=%s",
                uid,
                payload.get("amd_result"),
                payload.get("duration_sec") or payload.get("duration_seconds"),
            )
            return False
        if raw_rec.startswith(("http://", "https://")):
            rec = self.normalize_recording_url(raw_rec, uid)
        else:
            rec = self.normalize_recording_url(
                raw_rec, uid
            ) or self.resolve_sofia_recording_url(uid) or self.resolve_lea_recording_url(uid)
        if not rec:
            return False
        patch = dict(payload)
        patch.update(
            {
                "vicidial_call_id": str(uid),
                "call_sid": str(uid),
                "recording_url": rec,
            }
        )
        vals = self._prepare_call_log_vals(
            patch, company_id=company_id, skip_lead_lookup=fast
        )
        if not vals:
            return False
        vals["recording_url"] = self._pick_recording_url(
            False, vals.get("recording_url") or rec
        )
        dur = int(payload.get("duration_sec") or payload.get("duration_seconds") or 0)
        if dur <= 0 and not fast:
            dur = self._sofia_duration_from_recordings(uid)
        campaign = self._sanitize_vicidial_id(
            payload.get("campaign") or payload.get("campaign_id")
        )
        if dur > 0:
            vals["duration"] = dur
        elif int(vals.get("duration") or 0) <= 0:
            vals.pop("duration", None)
        if not vals.get("amd_result"):
            if self._is_hostinger_campaign(campaign):
                inferred = self._infer_amd_for_hostinger_call(
                    uid, duration=dur or int(vals.get("duration") or 0)
                )
                if inferred:
                    vals["amd_result"] = inferred
            elif dur > 0:
                vals["amd_result"] = "human"
        return self._save_call_log(vals, defer_side_effects=fast, payload=patch)

    def upsert_call_from_pipeline(self, payload, company_id=False):
        """Fin d'appel agents IA (Sofia ES, Soumission QC, n8n, etc.)."""
        payload = dict(payload or {})
        if not self.is_sofia_conversation(payload):
            has_https_rec = str(
                payload.get("recording_url")
                or payload.get("RecordingUrl")
                or payload.get("audio_url")
                or ""
            ).strip().startswith(("http://", "https://"))
            for key in (
                "recording_url",
                "recording",
                "RecordingUrl",
                "audio_url",
                "url_enregistrement",
            ):
                if has_https_rec and key in (
                    "recording_url",
                    "RecordingUrl",
                    "audio_url",
                    "url_enregistrement",
                ):
                    continue
                payload.pop(key, None)
        vals = self._prepare_call_log_vals(payload, company_id=company_id)
        if vals:
            uid = vals.get("vicidial_call_id")
            duration = int(vals.get("duration") or 0)
            if uid and duration <= 0 and self.is_available():
                campaign = self._sanitize_vicidial_id(
                    payload.get("campaign") or payload.get("campaign_id")
                )
                if self._is_hostinger_campaign(campaign):
                    try:
                        rows = self._hostinger_query_rows(
                            "SELECT length_in_sec FROM call_log WHERE uniqueid = '%s' LIMIT 1"
                            % re.sub(r"[^0-9.]", "", str(uid)),
                            columns=["length_in_sec"],
                        )
                        if rows and int(rows[0].get("length_in_sec") or 0) > duration:
                            duration = int(rows[0]["length_in_sec"])
                            vals["duration"] = duration
                            st = (payload.get("status") or "").upper()
                            if duration >= 10 and st in self._human_vicidial_statuses():
                                vals["amd_result"] = "human"
                    except Exception:
                        pass
                else:
                    conn = self._connect(campaign_id=campaign or None)
                    try:
                        cur = conn.cursor()
                        cur.execute(
                            "SELECT length_in_sec FROM call_log WHERE uniqueid = %s LIMIT 1",
                            (str(uid),),
                        )
                        row = cur.fetchone()
                        if row and int(row[0] or 0) > duration:
                            duration = int(row[0])
                            vals["duration"] = duration
                            st = (payload.get("status") or "").upper()
                            if duration >= 10 and st in self._human_vicidial_statuses():
                                vals["amd_result"] = "human"
                        cur.close()
                    finally:
                        conn.close()
            statut = (payload.get("etat_final") or payload.get("statut") or "").lower()
            if payload.get("lead_ganador") in (True, "true", "OUI", "oui", 1, "1"):
                vals["disposition"] = "INTERET"
            elif statut in ("qualifie", "qualified"):
                vals["disposition"] = "INTERET"
            elif statut in ("non_qualifie", "pas_interesse", "refus"):
                vals["disposition"] = "REFUS"
        duration = int(vals.get("duration") or 0) if vals else 0
        if vals and duration <= 0 and not vals.get("recording_url"):
            amd = vals.get("amd_result")
            if amd not in ("human", "answering_machine"):
                return False
        return self._save_call_log(vals, payload=payload)

    def upsert_call_from_vicidial_sync(self, sync):
        """Fin d'appel agent humain VICIdial (sync temps réel)."""
        sync.ensure_one()
        if not sync.vicidial_call_id:
            return False
        company_id = False
        cid = (sync.campagne_vicidial or "")[:8]
        if cid:
            camp = self.env["doorway.campaign"].sudo().search(
                [("vicidial_campaign_id", "=", cid)], limit=1
            )
            if camp:
                company_id = camp.company_id.id
        duration = int(sync.duree_secondes or 0)
        payload = {
            "vicidial_call_id": sync.vicidial_call_id,
            "campaign": sync.campagne_vicidial,
            "phone_number": sync.phone,
            "telephone": sync.phone,
            "duration": duration,
            "duration_seconds": duration,
            "call_date": sync.date_debut or fields.Datetime.now(),
            "user": sync.vicidial_agent_id,
            "amd_result": "human" if duration > 0 else "no_answer",
        }
        vals = self._prepare_call_log_vals(payload, company_id=company_id)
        if not vals:
            return False
        if duration <= 0 and not vals.get("recording_url"):
            return False
        return self._save_call_log(vals)

    # ── Campagnes ─────────────────────────────────────────────

    def create_campaign(
        self,
        name,
        dial_level,
        max_calls,
        amd_enabled,
        amd_action="DONTCARE",
        dial_timeout=30,
        auto_dial_mode="RATIO",
        campaign_id=None,
    ):
        """Crée campagne dans VICIdial via MySQL."""
        dial_method = DIAL_MODE_MAP.get(
            (auto_dial_mode or "").lower(), (auto_dial_mode or "RATIO").upper()
        )
        if dial_method not in DIAL_MODE_MAP.values():
            dial_method = "RATIO"
        cid = (campaign_id or self._slug_campaign_id(name))[:20]
        conn = self._connect()
        try:
            cur = conn.cursor()
            amd_val = "Y" if amd_enabled else "N"
            try:
                cur.execute(
                    """
                    INSERT INTO vicidial_campaigns (
                        campaign_id, campaign_name, active, dial_method,
                        dial_level, answering_machine_detection, amd_action,
                        manual_dial_timeout, hopper_level
                    ) VALUES (%s, %s, 'N', %s, %s, %s, %s, %s, %s)
                    ON DUPLICATE KEY UPDATE
                        campaign_name = VALUES(campaign_name),
                        dial_method = VALUES(dial_method),
                        dial_level = VALUES(dial_level),
                        answering_machine_detection = VALUES(answering_machine_detection),
                        amd_action = VALUES(amd_action),
                        manual_dial_timeout = VALUES(manual_dial_timeout),
                        hopper_level = VALUES(hopper_level)
                    """,
                    (
                        cid,
                        (name or cid)[:40],
                        dial_method,
                        dial_level,
                        amd_val,
                        (amd_action or "DONTCARE").upper(),
                        dial_timeout,
                        max_calls or 100,
                    ),
                )
            except Exception:  # noqa: BLE001
                cur.execute(
                    """
                    INSERT INTO vicidial_campaigns (
                        campaign_id, campaign_name, active, dial_method,
                        auto_dial_level, hopper_level, amd_send_to_vmx,
                        drop_call_seconds, dial_timeout
                    ) VALUES (%s, %s, 'N', %s, %s, %s, %s, %s, %s)
                    ON DUPLICATE KEY UPDATE
                        campaign_name = VALUES(campaign_name),
                        dial_method = VALUES(dial_method),
                        auto_dial_level = VALUES(auto_dial_level),
                        hopper_level = VALUES(hopper_level),
                        amd_send_to_vmx = VALUES(amd_send_to_vmx),
                        drop_call_seconds = VALUES(drop_call_seconds),
                        dial_timeout = VALUES(dial_timeout)
                    """,
                    (
                        cid,
                        (name or cid)[:40],
                        (auto_dial_mode or "RATIO").upper()[:20],
                        str(min(max(float(dial_level or 1), 0), 99.99)),
                        max_calls or 100,
                        amd_val,
                        dial_timeout,
                        dial_timeout,
                    ),
                )
            list_id = self._ensure_list(cur, cid, name)
            conn.commit()
            cur.close()
            _logger.info("VICIdial campaign created: %s", cid)
            return {"campaign_id": cid, "list_id": list_id}
        finally:
            conn.close()

    def _ensure_list(self, cur, cid, name, list_name=None):
        if list_name:
            cur.execute(
                """
                SELECT list_id FROM vicidial_lists
                WHERE campaign_id = %s AND list_name = %s LIMIT 1
                """,
                (cid, list_name[:30]),
            )
            row = cur.fetchone()
            if row:
                return str(row[0])
        elif not list_name:
            cur.execute(
                """
                SELECT list_id FROM vicidial_lists
                WHERE campaign_id = %s ORDER BY list_id DESC LIMIT 1
                """,
                (cid,),
            )
            row = cur.fetchone()
            if row:
                return str(row[0])
        cur.execute("SELECT COALESCE(MAX(list_id), 100) + 1 FROM vicidial_lists")
        new_list_id = cur.fetchone()[0]
        label = (list_name or ("LIST_%s" % cid))[:30]
        cur.execute(
            """
            INSERT INTO vicidial_lists (
                list_id, list_name, campaign_id, active, list_description
            ) VALUES (%s, %s, %s, 'Y', %s)
            """,
            (new_list_id, label, cid, ("Odoo — %s" % name)[:255]),
        )
        return str(new_list_id)

    def create_campaign_from_record(self, campaign):
        campaign.ensure_one()
        cid = campaign.vicidial_campaign_id or self.env["doorway.campaign"]._generate_vicidial_id(
            campaign.name, campaign.pipeline
        )
        try:
            created = self.create_campaign(
                name=campaign.name,
                dial_level=campaign.dial_level or 1,
                max_calls=campaign.max_concurrent_calls,
                amd_enabled=campaign.amd_enabled,
                amd_action=AMD_ACTION_MAP.get(campaign.amd_action, "DONTCARE"),
                dial_timeout=campaign.dial_timeout_seconds or 30,
                auto_dial_mode=DIAL_MODE_MAP.get(
                    campaign.auto_dial_mode, "RATIO"
                ),
                campaign_id=cid,
            )
            return {"ok": True, **created}
        except Exception as exc:  # noqa: BLE001
            _logger.exception("create_campaign_from_record")
            return {"ok": False, "message": str(exc)}

    def _list_id_for(self, cid):
        conn = self._connect()
        try:
            cur = conn.cursor()
            cur.execute(
                "SELECT list_id FROM vicidial_lists WHERE campaign_id = %s LIMIT 1",
                (cid[:8],),
            )
            row = cur.fetchone()
            cur.close()
            return str(row[0]) if row else ""
        finally:
            conn.close()

    def sync_campaign_record(self, campaign):
        return self.create_campaign_from_record(campaign)

    @classmethod
    def spain_campaign_ids(cls):
        return tuple(SPAIN_TRUSTSIP_CAMPAIGN_IDS)

    def audit_spain_dialing_config(self):
        """Contrôle indicatif 34 + dialplan TrustSIP sur tous les environnements ES."""
        report = {"ok": True, "campaigns": [], "carrier": {}, "lists": []}
        if not self.is_available():
            report["ok"] = False
            report["error"] = "MySQL VICIdial indisponible"
            return report

        conn = self._connect()
        try:
            cur = conn.cursor(dictionary=True)
            placeholders = ",".join(["%s"] * len(SPAIN_TRUSTSIP_CAMPAIGN_IDS))
            cur.execute(
                f"""
                SELECT campaign_id, campaign_name, active, omit_phone_code,
                       dial_prefix, campaign_cid
                FROM vicidial_campaigns
                WHERE campaign_id IN ({placeholders})
                ORDER BY campaign_id
                """,
                SPAIN_TRUSTSIP_CAMPAIGN_IDS,
            )
            for row in cur.fetchall():
                valid = (
                    row.get("omit_phone_code") == "Y"
                    and (row.get("dial_prefix") or "") == "34"
                )
                row["valid"] = valid
                report["campaigns"].append(row)
                if not valid:
                    report["ok"] = False

            cur.execute(
                "SELECT carrier_id, active, dialplan_entry "
                "FROM vicidial_server_carriers WHERE carrier_id = 'TrustSIP'"
            )
            carrier = cur.fetchone() or {}
            dialplan = carrier.get("dialplan_entry") or ""
            carrier["valid"] = (
                "${EXTEN}," in dialplan or "${EXTEN}\n" in dialplan
            ) and "${EXTEN:2}" not in dialplan
            report["carrier"] = carrier
            if not carrier.get("valid"):
                report["ok"] = False

            cur.execute(
                f"""
                SELECT vls.list_id, vls.list_name, vls.campaign_id,
                       vl.phone_code, COUNT(*) AS lead_count
                FROM vicidial_lists vls
                INNER JOIN vicidial_list vl ON vl.list_id = vls.list_id
                WHERE vls.campaign_id IN ({placeholders})
                GROUP BY vls.list_id, vls.list_name, vls.campaign_id, vl.phone_code
                ORDER BY vls.list_id, lead_count DESC
                """,
                SPAIN_TRUSTSIP_CAMPAIGN_IDS,
            )
            for row in cur.fetchall():
                row["valid"] = row.get("phone_code") == "34"
                report["lists"].append(row)
                if not row["valid"]:
                    report["ok"] = False
            cur.close()
        finally:
            conn.close()
        return report

    def ensure_spain_outbound_dialing(self, campaign_id=None):
        """Indicatif 34 conservé jusqu'au trunk TrustSIP (dial_prefix + EXTEN complet)."""
        campaign_ids = (
            [(campaign_id or "")[:20]]
            if campaign_id
            else list(SPAIN_TRUSTSIP_CAMPAIGN_IDS)
        )
        conn = self._connect()
        try:
            cur = conn.cursor()
            cur.execute(
                """
                UPDATE vicidial_server_carriers SET
                    dialplan_entry = %s,
                    globals_string = 'SIPTRUNK = SIP/TrustSIP'
                WHERE carrier_id = 'TrustSIP'
                """,
                (TRUSTSIP_ES_DIALPLAN,),
            )
            placeholders = ",".join(["%s"] * len(campaign_ids))
            cur.execute(
                f"""
                UPDATE vicidial_campaigns SET
                    omit_phone_code = 'Y',
                    dial_prefix = ''
                WHERE campaign_id IN ({placeholders})
                   OR campaign_cid = 'TrustSIP'
                   OR campaign_id IN (
                       SELECT DISTINCT campaign_id FROM vicidial_lists
                       WHERE list_name LIKE '%%ESPAGNE%%'
                          OR list_name LIKE '%%ABD_DEMO%%'
                          OR list_name LIKE '%%ISO%%'
                   )
                """,
                campaign_ids,
            )
            cur.execute(
                f"""
                UPDATE vicidial_list vl
                INNER JOIN vicidial_lists vls ON vl.list_id = vls.list_id
                SET vl.phone_code = '34'
                WHERE vls.campaign_id IN ({placeholders})
                   OR vls.list_name LIKE '%%ESPAGNE%%'
                   OR vls.list_name LIKE '%%ABD_DEMO%%'
                   OR vls.list_name LIKE '%%ISO%%'
                """,
                campaign_ids,
            )
            cur.execute(
                "UPDATE servers SET rebuild_conf_files = 'Y' "
                "WHERE generate_vicidial_conf = 'Y'"
            )
            for cid in campaign_ids:
                if cid in IA_REMOTE_AGENT_EXTEN:
                    self.ensure_ia_remote_agent(cid, cur=cur, conn=conn)
            conn.commit()
            cur.close()
            return self.audit_spain_dialing_config()
        finally:
            conn.close()

    def ensure_ia_remote_agent(self, campaign_id, number_of_lines=5, cur=None, conn=None):
        """Remote agent VICIdial (conf_exten) → dialplan Sofia / AGI."""
        cid = (campaign_id or "")[:20]
        conf_exten = IA_REMOTE_AGENT_EXTEN.get(cid)
        if not conf_exten:
            return False
        server_ip = self._server_ip()
        own_conn = cur is None
        if own_conn:
            conn = self._connect(campaign_id=cid if self._is_hostinger_campaign(cid) else None)
        elif conn is None and cur is not None:
            conn = getattr(cur, "connection", None) or getattr(cur, "_connection", None)
        try:
            if own_conn:
                cur = conn.cursor()
            cur.execute(
                """
                SELECT remote_agent_id FROM vicidial_remote_agents
                WHERE campaign_id = %s AND conf_exten = %s LIMIT 1
                """,
                (cid, conf_exten),
            )
            if not cur.fetchone():
                cur.execute(
                    """
                    INSERT INTO vicidial_remote_agents (
                        user_start, number_of_lines, server_ip, conf_exten,
                        status, campaign_id, on_hook_agent, on_hook_ring_time
                    ) VALUES (%s, %s, %s, %s, 'ACTIVE', %s, 'Y', 10)
                    """,
                    (conf_exten, number_of_lines, server_ip, conf_exten, cid),
                )
            else:
                cur.execute(
                    """
                    UPDATE vicidial_remote_agents SET
                        status = 'ACTIVE',
                        number_of_lines = %s,
                        on_hook_agent = 'Y',
                        on_hook_ring_time = 10,
                        server_ip = %s
                    WHERE campaign_id = %s AND conf_exten = %s
                    """,
                    (number_of_lines, server_ip, cid, conf_exten),
                )
            cur.execute(
                """
                UPDATE vicidial_campaigns SET
                    amd_send_to_vmx = 'N',
                    campaign_recording = 'ALLCALLS',
                    campaign_vdad_exten = '8369',
                    cpd_amd_action = 'DISPO',
                    dial_prefix = '',
                    dial_timeout = 30
                WHERE campaign_id = %s
                """,
                (cid,),
            )
            if own_conn:
                conn.commit()
                cur.close()
            return True
        finally:
            if own_conn:
                conn.close()

    @staticmethod
    def _normalize_campaign_cid(caller_id):
        """Rejette CLI vide, anonymous ou nom de trunk (Africa-Con/TrustSIP)."""
        label = (caller_id or "").strip()[:20]
        if not label or label in INVALID_CAMPAIGN_CIDS:
            return None
        if not re.match(r"^\d{10,15}$", label):
            return None
        return label

    def set_campaign_cid(self, campaign_id, caller_id):
        """DID E.164 sans + — jamais nom de trunk ni anonymous."""
        cid = (campaign_id or "")[:20]
        label = self._normalize_campaign_cid(caller_id)
        if not cid or not label:
            _logger.warning(
                "set_campaign_cid rejected campaign=%s caller_id=%r",
                cid,
                caller_id,
            )
            return False
        conn = self._connect()
        try:
            cur = conn.cursor()
            cur.execute(
                "UPDATE vicidial_campaigns SET campaign_cid = %s, use_custom_cid = 'Y' "
                "WHERE campaign_id = %s",
                (label, cid),
            )
            conn.commit()
            cur.close()
            return True
        finally:
            conn.close()

    def ensure_no_anonymous_cid(self, campaign_id=None):
        """Corrige campaign_cid invalide (TrustSIP, vide, anonymous) par région."""
        mapping = [
            (DOOR_APP0_FR_CAMPAIGN_IDS, DOOR_APP0_FR_CALLER_ID),
            (DOOR_APP0_QC_CAMPAIGN_IDS, DOOR_APP0_QC_CALLER_ID),
            (SPAIN_TRUSTSIP_CAMPAIGN_IDS, TRUSTSIP_ES_CALLER_ID),
        ]
        conn = self._connect()
        try:
            cur = conn.cursor()
            for campaign_ids, expected_cid in mapping:
                ids = (
                    [(campaign_id or "")[:20]]
                    if campaign_id
                    else list(campaign_ids)
                )
                if campaign_id and ids[0] not in campaign_ids:
                    continue
                placeholders = ",".join(["%s"] * len(ids))
                cur.execute(
                    f"""
                    UPDATE vicidial_campaigns
                    SET campaign_cid = %s, use_custom_cid = 'Y'
                    WHERE campaign_id IN ({placeholders})
                      AND (
                        campaign_cid IS NULL OR campaign_cid = ''
                        OR LOWER(campaign_cid) = 'anonymous'
                        OR campaign_cid IN ('TrustSIP', 'Door_App0', 'Door_App0_FR')
                        OR campaign_cid != %s
                      )
                    """,
                    (expected_cid, *ids, expected_cid),
                )
            conn.commit()
            cur.close()
            return True
        finally:
            conn.close()

    def ensure_ia_manual_quality(self, campaign_id, clear_hopper=False):
        """Mode manuel permanent qualité — ADL=0, pas de hopper autodial."""
        import os

        cid = self._sanitize_vicidial_id(campaign_id)
        if cid not in IA_MANUAL_QUALITY_VICIDIAL:
            return False
        if not os.path.isfile(IA_MANUAL_QUALITY_FLAG):
            return False
        if self._is_hostinger_campaign(cid):
            self._hostinger_execute_sql(
                "UPDATE vicidial_campaigns SET auto_dial_level=0, dial_method='MANUAL', "
                "no_hopper_dialing='Y' WHERE campaign_id='%s'" % cid
            )
            if clear_hopper:
                self._hostinger_execute_sql(
                    "DELETE FROM vicidial_hopper WHERE campaign_id='%s'" % cid
                )
                self._hostinger_execute_sql(
                    "DELETE FROM vicidial_auto_calls WHERE campaign_id='%s'" % cid
                )
            return True
        if not self.is_available():
            return False
        conn = self._connect(campaign_id=cid)
        try:
            cur = conn.cursor()
            cur.execute(
                "UPDATE vicidial_campaigns SET auto_dial_level=0, dial_method='MANUAL', "
                "no_hopper_dialing='Y' WHERE campaign_id=%s",
                (cid,),
            )
            if clear_hopper:
                cur.execute("DELETE FROM vicidial_hopper WHERE campaign_id=%s", (cid,))
                cur.execute(
                    "DELETE FROM vicidial_auto_calls WHERE campaign_id=%s", (cid,)
                )
            conn.commit()
            cur.close()
            return True
        finally:
            conn.close()

    def ensure_hostinger_manual_only(self, campaign_id, clear_hopper=False):
        """Hostinger QC : ADL=0 + MANUAL (pas d'autodial depuis le hopper)."""
        cid = self._sanitize_vicidial_id(campaign_id)
        if not self._is_hostinger_campaign(cid):
            return False
        self._hostinger_execute_sql(
            "UPDATE vicidial_campaigns SET auto_dial_level=0, dial_method='MANUAL', "
            "no_hopper_dialing='Y' WHERE campaign_id='%s'" % cid
        )
        if clear_hopper:
            self._hostinger_execute_sql(
                "DELETE FROM vicidial_hopper WHERE campaign_id='%s'" % cid
            )
            self._hostinger_execute_sql(
                "DELETE FROM vicidial_auto_calls WHERE campaign_id='%s'" % cid
            )
        return True

    def _set_campaign_active_mysql(self, campaign_id, active):
        cid = (campaign_id or "")[:8]
        conn = self._connect(campaign_id=cid)
        try:
            cur = conn.cursor()
            cur.execute(
                "UPDATE vicidial_campaigns SET active = %s WHERE campaign_id = %s",
                ("Y" if active else "N", cid),
            )
            conn.commit()
            cur.close()
            return True
        finally:
            conn.close()

    def update_campaign_dial_level(self, campaign_id, new_level):
        cid = (campaign_id or "")[:8]
        level = float(new_level)
        if cid in HOSTINGER_MANUAL_ONLY_VICIDIAL and level > 0:
            self.ensure_hostinger_manual_only(cid, clear_hopper=True)
            return True
        if cid in IA_MANUAL_QUALITY_VICIDIAL and level > 0:
            self.ensure_ia_manual_quality(cid, clear_hopper=True)
            return True
        if self._is_hostinger_campaign(cid):
            conn = self._connect(campaign_id=cid)
            try:
                cur = conn.cursor()
                dial_method = "MANUAL" if level <= 0 else "RATIO"
                cur.execute(
                    """
                    UPDATE vicidial_campaigns
                       SET auto_dial_level = %s, dial_method = %s
                     WHERE campaign_id = %s
                    """,
                    (level, dial_method, cid),
                )
                if level <= 0:
                    cur.execute(
                        "DELETE FROM vicidial_hopper WHERE campaign_id = %s",
                        (cid,),
                    )
                conn.commit()
                cur.close()
                return True
            finally:
                conn.close()
        try:
            self._api_get(
                "function=update_campaign&campaign_id=%s&auto_dial_level=%s"
                % (cid, level)
            )
            return True
        except Exception as exc:  # noqa: BLE001
            _logger.error("update_dial_level error: %s", exc)
            return False

    def start_campaign(self, campaign_id):
        cid = campaign_id
        if hasattr(campaign_id, "vicidial_campaign_id"):
            cid = campaign_id.vicidial_campaign_id
        cid = (cid or "")[:8]
        try:
            if self._is_hostinger_campaign(cid):
                self._set_campaign_active_mysql(cid, True)
                self.ensure_quebec_outbound_dialing(cid)
                if cid in IA_REMOTE_AGENT_EXTEN:
                    self.ensure_ia_remote_agent(cid)
                if cid in HOSTINGER_MANUAL_ONLY_VICIDIAL:
                    self.ensure_hostinger_manual_only(cid)
                return True
            self._api_get(
                "function=update_campaign&campaign_id=%s&active=Y" % cid
            )
            if cid in IA_REMOTE_AGENT_EXTEN:
                self.ensure_ia_remote_agent(cid)
                if (
                    cid.startswith("DW_ES")
                    or cid.startswith("DWTO")
                    or cid in ("ABD_DEMO",)
                ):
                    self.ensure_spain_outbound_dialing(cid)
                elif cid.startswith("DW_QC") or cid in QC_IA_CAMPAIGN_IDS:
                    self.ensure_quebec_outbound_dialing(cid)
            return True
        except Exception as exc:  # noqa: BLE001
            _logger.error("start_campaign error: %s", exc)
            return False

    def pause_campaign(self, campaign_id):
        cid = (campaign_id or "")[:8]
        try:
            if self._is_hostinger_campaign(cid):
                return self._set_campaign_active_mysql(cid, False)
            self._api_get(
                "function=update_campaign&campaign_id=%s&active=N" % cid
            )
            return True
        except Exception as exc:  # noqa: BLE001
            _logger.error("pause_campaign error: %s", exc)
            return False

    def api_version(self):
        """Test connectivité non_agent_api (function=version)."""
        try:
            return self._api_get("function=version").strip()
        except Exception as exc:  # noqa: BLE001
            _logger.error("api_version error: %s", exc)
            return ""

    def _ai_calls_per_hour_cap(self):
        """Plafond horaire d'appels IA (ir.config_parameter). <=0 => illimité."""
        raw = self._icp.get_param(
            AI_CALLS_PER_HOUR_PARAM, AI_CALLS_DEFAULT_PER_HOUR
        )
        try:
            return int(float(raw))
        except (TypeError, ValueError):
            return AI_CALLS_DEFAULT_PER_HOUR

    def _ai_call_throttle_acquire(self):
        """Token-bucket horaire (fenêtre fixe) pour les appels IA sortants.

        N'affecte QUE call_out_number (non_agent_api / agents IA).
        Les appels manuels humains (dial_manual_*) ne passent jamais ici.
        Retourne (allowed: bool, info: dict). En cas d'erreur on laisse
        passer l'appel (fail-open) pour ne jamais bloquer la téléphonie.
        """
        try:
            cap = self._ai_calls_per_hour_cap()
            if cap <= 0:
                return True, {"cap": cap, "throttle": "disabled"}
            now = time.time()
            raw = self._icp.get_param(AI_CALL_WINDOW_PARAM) or ""
            try:
                state = json.loads(raw) if raw else {}
            except (TypeError, ValueError):
                state = {}
            start = float(state.get("start") or 0)
            count = int(state.get("count") or 0)
            if start <= 0 or (now - start) >= 3600:
                start, count = now, 0
            if count >= cap:
                return False, {
                    "cap": cap,
                    "count": count,
                    "window_reset_in_s": max(int(3600 - (now - start)), 0),
                }
            self._icp.set_param(
                AI_CALL_WINDOW_PARAM,
                json.dumps({"start": start, "count": count + 1}),
            )
            return True, {"cap": cap, "count": count + 1}
        except Exception as exc:  # noqa: BLE001 — fail-open, jamais bloquer
            _logger.warning("AI call throttle check failed (fail-open): %s", exc)
            return True, {"throttle": "error", "error": str(exc)}

    def call_out_number(
        self,
        phone_number,
        campaign=None,
        phone_code="34",
        outbound_cid=None,
    ):
        """
        Déclenche un appel sortant via non_agent_api (renov-aides / outbound v2).
        phone_number : E.164 ou national (sans +)

        APPELS IA UNIQUEMENT — soumis au plafond horaire
        `doorway_vicidial_campaigns.ai_calls_per_hour`. Les agents humains
        composent via dial_manual_number / dial_manual_next_call et ne sont
        jamais limités par ce plafond.
        """
        phone = (phone_number or "").strip().lstrip("+")
        if phone_code and phone.startswith(phone_code):
            phone = phone[len(phone_code) :]
        campaign = (campaign or "renov_es")[:20]
        if not phone:
            return {"ok": False, "message": "phone_number required"}
        allowed, throttle = self._ai_call_throttle_acquire()
        if not allowed:
            _logger.warning(
                "call_out_number THROTTLED — plafond IA %s appels/h atteint "
                "(campagne=%s). Réessai dans %ss.",
                throttle.get("cap"),
                campaign,
                throttle.get("window_reset_in_s"),
            )
            return {
                "ok": False,
                "throttled": True,
                "message": (
                    "Plafond horaire d'appels IA atteint (%s/h). "
                    "Réessayez dans %ss."
                )
                % (throttle.get("cap"), throttle.get("window_reset_in_s")),
                "throttle": throttle,
                "campaign": campaign,
                "phone": phone,
            }
        cid = (outbound_cid or "").strip().lstrip("+") or ""
        params = (
            "function=call_out_number"
            "&campaign=%s"
            "&phone_number=%s"
            "&phone_code=%s"
        ) % (campaign, phone, phone_code)
        if cid:
            params += "&outbound_cid=%s" % cid
        try:
            raw = self._api_get(params).strip()
            ok = "SUCCESS" in raw.upper() or "HAS BEEN PLACED" in raw.upper()
            if not ok and "ERROR" in raw.upper():
                ok = False
            return {"ok": ok, "raw": raw, "campaign": campaign, "phone": phone}
        except Exception as exc:  # noqa: BLE001
            _logger.error("call_out_number error: %s", exc)
            return {"ok": False, "message": str(exc)}

    # ── Contacts ──────────────────────────────────────────────

    def inject_contacts(
        self, campaign_id, contacts, phone_code="33", list_name=None
    ):
        cid = (campaign_id or "")[:20]
        conn = self._connect()
        try:
            cur = conn.cursor()
            list_id = self._list_id_for(cid)
            if not list_id and list_name:
                cur.execute(
                    """
                    SELECT list_id FROM vicidial_lists
                    WHERE campaign_id = %s AND list_name = %s LIMIT 1
                    """,
                    (cid, list_name[:30]),
                )
                row = cur.fetchone()
                list_id = str(row[0]) if row else ""
            if not list_id:
                list_id = self._ensure_list(cur, cid, cid, list_name=list_name)
                conn.commit()
        finally:
            conn.close()
        conn = self._connect()
        ok, errors = 0, 0
        try:
            cur = conn.cursor()
            for c in contacts:
                try:
                    if hasattr(c, "phone_number"):
                        row = {
                            "phone_number": c.phone_number,
                            "first_name": c.first_name or "",
                            "last_name": c.last_name or "",
                            "email": c.email or "",
                            "city": "",
                            "postal_code": "",
                            "address1": "",
                            "vendor_lead_code": c.vendor_code or "",
                            "source_id": "ODOO",
                            "phone_code": phone_code,
                        }
                    else:
                        row = c
                    pcode = row.get("phone_code") or phone_code
                    cur.execute(
                        """
                        INSERT INTO vicidial_list (
                            entry_date, status, list_id, phone_code, phone_number,
                            first_name, last_name, email, address1, city, state,
                            province, postal_code, country_code, comments, `rank`,
                            vendor_lead_code, source_id, called_count
                        ) VALUES (
                            NOW(), %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                            %s, %s, %s, %s, %s, %s, %s, %s
                        )
                        """,
                        (
                            (row.get("status") or "NEW")[:6],
                            list_id,
                            pcode,
                            row.get("phone_number", ""),
                            (row.get("first_name") or "")[:30],
                            (row.get("last_name") or "")[:30],
                            (row.get("email") or "")[:70],
                            (row.get("address1") or "")[:100],
                            (row.get("city") or "")[:50],
                            (row.get("state") or "")[:2],
                            (row.get("state") or row.get("province") or "")[:50],
                            (row.get("postal_code") or "")[:10],
                            (row.get("country_code") or "")[:3],
                            (row.get("comments") or "")[:255],
                            int(row.get("rank") or 0),
                            (row.get("vendor_lead_code") or "")[:20],
                            (row.get("source_id") or "ODOO")[:50],
                            int(row.get("called_count") or 0),
                        ),
                    )
                    ok += 1
                except Exception as exc:  # noqa: BLE001
                    _logger.warning("Contact insert error: %s", exc)
                    errors += 1
            conn.commit()
            cur.close()
        finally:
            conn.close()
        return {
            "success": ok,
            "errors": errors,
            "ok": ok > 0,
            "list_id": list_id,
            "log": "%s ok, %s err" % (ok, errors),
        }

    def setup_espagne_renovation_campaign(self):
        """Campagne Espagne rénovation — trunk TrustSIP, liste ESPAGNE_RENOVATION."""
        cid = "DW_ESREN"
        list_name = "ESPAGNE_RENOVATION"
        carrier_id = "TrustSIP"
        host = "116.202.233.75"
        sip_user = "trustsip"
        sip_pass = "4i9jgo7"
        sip_port = 5060
        account_entry = (
            "[%s]\n"
            "type=friend\n"
            "host=%s\n"
            "port=%s\n"
            "username=%s\n"
            "secret=%s\n"
            "fromuser=%s\n"
            "fromdomain=%s\n"
            "context=trunkinbound\n"
            "insecure=port,invite\n"
            "qualify=yes\n"
            "disallow=all\n"
            "allow=ulaw\n"
            "allow=alaw\n"
            "dtmfmode=rfc2833\n"
            "sendrpid=yes\n"
            "trustrpid=no\n"
            "usecallerid=yes\n"
        ) % (carrier_id, host, sip_port, sip_user, sip_pass, sip_user, host)
        registration = "register => %s:%s@%s:%s" % (
            sip_user,
            sip_pass,
            host,
            sip_port,
        )
        dialplan = (
            "exten => _34XXXXXXXXX,1,AGI(agi://127.0.0.1:4577/call_log)\n"
            "exten => _34XXXXXXXXX,2,Dial(${SIPTRUNK}/${EXTEN},${CAMPDTO},To)\n"
            "exten => _34XXXXXXXXX,3,Hangup"
        )
        conn = self._connect()
        try:
            cur = conn.cursor()
            cur.execute(
                "SELECT carrier_id FROM vicidial_server_carriers WHERE carrier_id = %s",
                (carrier_id,),
            )
            if not cur.fetchone():
                cur.execute(
                    """
                    INSERT INTO vicidial_server_carriers (
                        carrier_id, carrier_name, registration_string, template_id,
                        account_entry, protocol, globals_string, dialplan_entry,
                        server_ip, active, carrier_description, user_group
                    ) VALUES (%s, %s, %s, '--NONE--', %s, 'SIP', %s, %s, %s, 'Y', %s, '---ALL---')
                    """,
                    (
                        carrier_id,
                        "TrustSIP — Espagne rénovation",
                        registration,
                        account_entry,
                        "SIPTRUNK = SIP/%s" % carrier_id,
                        dialplan,
                        self._server_ip(),
                        "Trunk SIP TrustSIP — %s:%s (Espagne)" % (host, sip_port),
                    ),
                )
            else:
                cur.execute(
                    """
                    UPDATE vicidial_server_carriers SET
                        carrier_name = %s,
                        registration_string = %s,
                        account_entry = %s,
                        globals_string = %s,
                        dialplan_entry = %s,
                        active = 'Y',
                        carrier_description = %s
                    WHERE carrier_id = %s
                    """,
                    (
                        "TrustSIP — Espagne rénovation",
                        registration,
                        account_entry,
                        "SIPTRUNK = SIP/%s" % carrier_id,
                        dialplan,
                        "Trunk SIP TrustSIP — %s:%s (Espagne)" % (host, sip_port),
                        carrier_id,
                    ),
                )
            cur.execute(
                "SELECT campaign_id FROM vicidial_campaigns WHERE campaign_id = %s",
                (cid,),
            )
            if not cur.fetchone():
                cur.execute(
                    """
                    INSERT INTO vicidial_campaigns (
                        campaign_id, campaign_name, active, dial_method,
                        auto_dial_level, hopper_level, dial_prefix, campaign_cid,
                        local_call_time, dial_timeout, campaign_description
                    )
                    SELECT %s, %s, 'N', dial_method, auto_dial_level, hopper_level,
                           %s, campaign_cid, local_call_time, dial_timeout, %s
                    FROM vicidial_campaigns WHERE campaign_id = 'DW_FRB2C' LIMIT 1
                    """,
                    (
                        cid,
                        "Espagne rénovation — sortants",
                        "34",
                        "Espagne rénovation — Sofía IA — trunk TrustSIP",
                    ),
                )
            else:
                cur.execute(
                    """
                    UPDATE vicidial_campaigns SET
                        campaign_name = %s,
                        dial_prefix = %s,
                        campaign_description = %s
                    WHERE campaign_id = %s
                    """,
                    (
                        "Espagne rénovation — sortants",
                        "34",
                        "Espagne rénovation — Sofía IA — trunk TrustSIP",
                        cid,
                    ),
                )
            list_id = self._ensure_list(
                cur, cid, "Espagne rénovation", list_name=list_name
            )
            cur.execute(
                """
                UPDATE vicidial_campaigns SET
                    omit_phone_code = 'Y',
                    dial_prefix = '34'
                WHERE campaign_id = %s
                """,
                (cid,),
            )
            cur.execute(
                "UPDATE vicidial_list SET phone_code = '34' WHERE list_id = %s",
                (list_id,),
            )
            cur.execute(
                "UPDATE servers SET rebuild_conf_files='Y' WHERE generate_vicidial_conf='Y'"
            )
            conn.commit()
            cur.close()
            self.ensure_spain_outbound_dialing(cid)
            return {
                "campaign_id": cid,
                "list_id": list_id,
                "list_name": list_name,
                "carrier_id": carrier_id,
            }
        finally:
            conn.close()

    def _server_ip(self):
        return (
            self.env["ir.config_parameter"]
            .sudo()
            .get_param("doorway_vicidial_campaigns.server_ip", "93.127.162.97")
        )

    def setup_rappel_quebec_campaign(self):
        """Campagne B2C rappels Québec — trunk Door_App0, liste RAPPEL_B2C_QC."""
        cid = "DW_RAPQC"
        list_name = "RAPPEL_B2C_QC"
        conn = self._connect()
        try:
            cur = conn.cursor()
            cur.execute(
                "SELECT campaign_id FROM vicidial_campaigns WHERE campaign_id = %s",
                (cid,),
            )
            exists = cur.fetchone()
            if not exists:
                cur.execute(
                    """
                    INSERT INTO vicidial_campaigns (
                        campaign_id, campaign_name, active, dial_method,
                        auto_dial_level, hopper_level, dial_prefix, campaign_cid,
                        local_call_time, dial_timeout, campaign_description
                    )
                    SELECT %s, %s, 'Y', dial_method, auto_dial_level, hopper_level,
                           dial_prefix, campaign_cid, local_call_time, dial_timeout,
                           %s
                    FROM vicidial_campaigns WHERE campaign_id = 'DW_QCB2C' LIMIT 1
                    """,
                    (
                        cid,
                        "B2C Rappels Québec — sortants",
                        "Rappels B2C Québec — SIP trunk Door_App0",
                    ),
                )
            list_id = self._ensure_list(
                cur, cid, "B2C Rappels Québec", list_name=list_name
            )
            conn.commit()
            cur.close()
            return {"campaign_id": cid, "list_id": list_id, "list_name": list_name}
        finally:
            conn.close()

    def _setup_qc_ia_campaign(self, cid, campaign_name, list_name, description, clone_from="DW_QCB2C"):
        """Campagne IA Québec — trunk Door_App0, remote agent, AMD."""
        conn = self._connect()
        try:
            cur = conn.cursor()
            cur.execute(
                "SELECT campaign_id FROM vicidial_campaigns WHERE campaign_id = %s",
                (cid,),
            )
            if not cur.fetchone():
                cur.execute(
                    """
                    INSERT INTO vicidial_campaigns (
                        campaign_id, campaign_name, active, dial_method,
                        auto_dial_level, hopper_level, dial_prefix, campaign_cid,
                        local_call_time, dial_timeout, campaign_description,
                        amd_status, cpd_amd_action, wrapup_seconds
                    )
                    SELECT %s, %s, 'N', 'RATIO', 1.3, hopper_level,
                           '', campaign_cid, local_call_time, 22, %s,
                           'Y', 'VOICEMAIL', 10
                    FROM vicidial_campaigns WHERE campaign_id = %s LIMIT 1
                    """,
                    (cid, campaign_name, description, clone_from),
                )
            else:
                cur.execute(
                    """
                    UPDATE vicidial_campaigns SET
                        campaign_name = %s,
                        dial_method = 'RATIO',
                        auto_dial_level = 1.3,
                        dial_timeout = 22,
                        amd_status = 'Y',
                        cpd_amd_action = 'VOICEMAIL',
                        wrapup_seconds = 10,
                        campaign_description = %s
                    WHERE campaign_id = %s
                    """,
                    (campaign_name, description, cid),
                )
            list_id = self._ensure_list(cur, cid, campaign_name, list_name=list_name)
            conn.commit()
            cur.close()
            self.ensure_quebec_outbound_dialing(cid)
            if cid in IA_REMOTE_AGENT_EXTEN:
                self.ensure_ia_remote_agent(cid)
            return {"campaign_id": cid, "list_id": list_id, "list_name": list_name}
        finally:
            conn.close()

    def setup_se_renov_qc_campaign(self):
        """SoumissionEntrepreneurs QC — agent Émilie, liste SE_RENOV_QC."""
        return self._setup_qc_ia_campaign(
            "SE_RENOV_QC",
            "SoumissionEntrepreneurs QC Rénovation",
            "SE_RENOV_QC",
            "Agent IA Émilie — propriétaires + projets rénovation QC",
        )

    def setup_maison_immo_qc_campaign(self):
        """MaisonRecherchee QC — agent Sophie, liste MR_IMMO_QC."""
        return self._setup_qc_ia_campaign(
            "MR_IMMO_QC",
            "MaisonRecherchee QC Vendeurs",
            "MR_IMMO_QC",
            "Agent IA Sophie — intention vente immobilier QC",
        )

    def setup_driven_b2b_qc_campaign(self):
        """Alex Driven B2B QC — campagne DW_QCB2B, ext 86023, auto_dial 0."""
        result = self._setup_qc_ia_campaign(
            "DW_QCB2B",
            "Québec B2B — Driven Alex",
            "DW_QCB2B",
            "Agent IA Alex — qualification financement PME Driven",
            clone_from="DW_QCB2C",
        )
        conn = self._connect()
        try:
            cur = conn.cursor()
            cur.execute(
                "UPDATE vicidial_campaigns SET auto_dial_level = 0, active = 'Y' "
                "WHERE campaign_id = 'DW_QCB2B'"
            )
            conn.commit()
            cur.close()
        finally:
            conn.close()
        self.ensure_ia_remote_agent("DW_QCB2B")
        self.ensure_quebec_outbound_dialing("DW_QCB2B")
        return result

    def inject_campaign_contacts(self, campaign, contact_records):
        rows = [
            {
                "phone_number": c.phone_number,
                "first_name": c.first_name,
                "last_name": c.last_name,
                "email": c.email,
                "vendor_code": c.vendor_code,
            }
            for c in contact_records
        ]
        country = campaign._phone_import_country()
        phone_code = {"ES": "34", "CA": "1", "QC": "1", "US": "1"}.get(
            country, "33"
        )
        cid = (campaign.vicidial_campaign_id or "")[:8]
        if country in ("CA", "QC") or cid.startswith("DW_QC") or cid in QC_IA_CAMPAIGN_IDS:
            self.ensure_quebec_outbound_dialing(cid)
        elif cid.startswith("DW_ES") or cid.startswith("DWTO"):
            self.ensure_spain_outbound_dialing(cid)
        result = self.inject_contacts(
            campaign.vicidial_campaign_id, rows, phone_code=phone_code
        )
        if result.get("success"):
            for contact in contact_records[: result["success"]]:
                contact.write({"state": "in_hopper", "error_message": False})
        return result

    def cleanup_campaign_list(self, campaign, reload_hopper=True):
        """Supprime numéros invalides/doublons (Odoo + VICIdial) et recharge le hopper."""
        from odoo.addons.doorway_vicidial_campaigns.services.file_importer import (
            is_valid_phone,
        )

        campaign.ensure_one()
        country = campaign._phone_import_country()
        stats = {
            "total": 0,
            "kept": 0,
            "normalized": 0,
            "removed": 0,
            "dupes_removed": 0,
            "odoo_removed": 0,
            "hopper": 0,
        }

        Contact = self.env["doorway.campaign.contact"].sudo()
        odoo_contacts = Contact.search([("campaign_id", "=", campaign.id)])
        stats["total"] = len(odoo_contacts)
        seen_odoo = {}
        to_unlink = []
        to_normalize = []
        for contact in odoo_contacts:
            valid, norm = is_valid_phone(contact.phone_number, country)
            if not valid:
                to_unlink.append(contact.id)
                stats["removed"] += 1
                stats["odoo_removed"] += 1
                continue
            if norm in seen_odoo:
                to_unlink.append(contact.id)
                stats["removed"] += 1
                stats["dupes_removed"] += 1
                stats["odoo_removed"] += 1
                continue
            seen_odoo[norm] = contact.id
            if norm != (contact.phone_number or "").strip():
                to_normalize.append((contact.id, norm))
                stats["normalized"] += 1
            stats["kept"] += 1

        for i in range(0, len(to_unlink), 500):
            Contact.browse(to_unlink[i : i + 500]).unlink()
        for contact_id, norm in to_normalize:
            Contact.browse(contact_id).write({"phone_number": norm})

        cid = (campaign.vicidial_campaign_id or "")[:8]
        if not cid or not self.is_available():
            stats["hopper"] = stats["kept"]
            return stats

        list_id = (campaign.vicidial_list_id or "").strip() or self._list_id_for(cid)
        if not list_id:
            stats["hopper"] = stats["kept"]
            return stats

        if country == "ES":
            self.ensure_spain_outbound_dialing(cid)

        conn = self._connect()
        try:
            cur = conn.cursor()
            if country == "ES":
                cur.execute(
                    "UPDATE vicidial_list SET phone_code = '34' WHERE list_id = %s",
                    (list_id,),
                )
            cur.execute(
                "SELECT lead_id, phone_number FROM vicidial_list WHERE list_id = %s",
                (list_id,),
            )
            rows = cur.fetchall()
            seen_vic = {}
            to_delete = []
            updates = []
            vic_invalid = 0
            vic_dupes = 0
            for lead_id, phone in rows:
                valid, norm = is_valid_phone(phone, country)
                if not valid:
                    to_delete.append(int(lead_id))
                    vic_invalid += 1
                    continue
                if norm in seen_vic:
                    to_delete.append(int(lead_id))
                    vic_dupes += 1
                    continue
                seen_vic[norm] = int(lead_id)
                if norm != (phone or "").strip():
                    updates.append((norm, int(lead_id)))

            for i in range(0, len(to_delete), 500):
                chunk = to_delete[i : i + 500]
                if not chunk:
                    continue
                placeholders = ",".join(["%s"] * len(chunk))
                cur.execute(
                    f"DELETE FROM vicidial_hopper WHERE lead_id IN ({placeholders})",
                    chunk,
                )
                cur.execute(
                    f"DELETE FROM vicidial_auto_calls WHERE lead_id IN ({placeholders})",
                    chunk,
                )
                cur.execute(
                    f"DELETE FROM vicidial_list WHERE lead_id IN ({placeholders})",
                    chunk,
                )

            for norm, lead_id in updates:
                cur.execute(
                    """
                    UPDATE vicidial_list
                    SET phone_number = %s, status = 'NEW',
                        called_since_last_reset = 'N', called_count = 0
                    WHERE lead_id = %s
                    """,
                    (norm, lead_id),
                )

            if reload_hopper:
                cur.execute(
                    "DELETE FROM vicidial_hopper WHERE campaign_id = %s",
                    (cid,),
                )
                cur.execute(
                    "DELETE FROM vicidial_auto_calls WHERE campaign_id = %s",
                    (cid,),
                )
                cur.execute(
                    """
                    UPDATE vicidial_list
                    SET status = 'NEW', called_since_last_reset = 'N'
                    WHERE list_id = %s AND status NOT IN ('DNC', 'SALE')
                    """,
                    (list_id,),
                )
                cur.execute(
                    """
                    INSERT INTO vicidial_hopper (
                        lead_id, campaign_id, status, list_id,
                        gmt_offset_now, state, alt_dial, priority
                    )
                    SELECT lead_id, %s, 'READY', list_id, 0.00, state, 'NONE', 0
                    FROM vicidial_list
                    WHERE list_id = %s AND status = 'NEW'
                    """,
                    (cid, list_id),
                )

            cur.execute(
                "SELECT COUNT(*) FROM vicidial_list WHERE list_id = %s",
                (list_id,),
            )
            vic_list_row = cur.fetchone()
            if vic_list_row:
                stats["kept"] = int(vic_list_row[0])
            cur.execute(
                "SELECT COUNT(*) FROM vicidial_hopper WHERE campaign_id = %s",
                (cid,),
            )
            hopper_row = cur.fetchone()
            stats["hopper"] = int(hopper_row[0]) if hopper_row else stats["kept"]
            stats["removed"] += vic_invalid + vic_dupes
            stats["dupes_removed"] += vic_dupes
            conn.commit()
            cur.close()
        finally:
            conn.close()

        if list_id and list_id != campaign.vicidial_list_id:
            campaign.sudo().write({"vicidial_list_id": str(list_id)})
        return stats

    def _resolve_vicidial_lead_id(self, cur, campaign_id, contact):
        """Retourne lead_id VICIdial pour un contact Odoo."""
        if contact.vicidial_lead_id:
            return int(contact.vicidial_lead_id)
        phone = (contact.phone_number or "").strip()
        if not phone:
            return None
        cur.execute(
            """
            SELECT vl.lead_id FROM vicidial_list vl
            INNER JOIN vicidial_lists vls ON vl.list_id = vls.list_id
            WHERE vls.campaign_id = %s AND vl.phone_number = %s
            ORDER BY vl.lead_id DESC LIMIT 1
            """,
            (campaign_id[:8], phone),
        )
        row = cur.fetchone()
        return int(row[0]) if row else None

    def relaunch_contacts_priority(self, campaign, contacts, priority=99):
        """Remet des contacts en file prioritaire VICIdial (hopper)."""
        cid = (campaign.vicidial_campaign_id or "")[:8]
        if not cid:
            return {"ok": False, "message": "Campagne VICIdial non liée.", "count": 0}
        conn = self._connect()
        ok = 0
        errors = []
        try:
            cur = conn.cursor()
            for contact in contacts:
                try:
                    lead_id = self._resolve_vicidial_lead_id(cur, cid, contact)
                    if not lead_id:
                        errors.append(
                            {"contact_id": contact.id, "error": "lead_id introuvable"}
                        )
                        continue
                    cur.execute(
                        """
                        UPDATE vicidial_list
                        SET status = 'NEW', called_since_last_reset = 'N'
                        WHERE lead_id = %s
                        """,
                        (lead_id,),
                    )
                    cur.execute(
                        """
                        DELETE FROM vicidial_hopper
                        WHERE lead_id = %s AND campaign_id = %s
                        """,
                        (lead_id, cid),
                    )
                    cur.execute(
                        """
                        INSERT INTO vicidial_hopper (
                            lead_id, campaign_id, status, priority, source
                        ) VALUES (%s, %s, 'READY', %s, 'ODDO')
                        """,
                        (lead_id, cid, int(priority)),
                    )
                    contact.write({"vicidial_lead_id": lead_id})
                    ok += 1
                except Exception as exc:  # noqa: BLE001
                    _logger.warning("relaunch contact %s: %s", contact.id, exc)
                    errors.append({"contact_id": contact.id, "error": str(exc)})
            conn.commit()
            cur.close()
        finally:
            conn.close()
        return {"ok": ok > 0, "count": ok, "errors": errors}

    def ensure_africa_con_door_trunk(self):
        """Door_App provider gone — keep carriers inactive; globals point to ZakariSIP/zakarifr.

        Historical name kept so callers (hooks/sync) do not recreate Africa-Con peers.
        """
        server_ip = self._server_ip()
        dialplan = _door_app0_dialplan()
        conn = self._connect()
        try:
            cur = conn.cursor()
            cur.execute(
                """
                UPDATE vicidial_server_carriers SET
                    active = 'N',
                    globals_string = 'DOORTRUNK = SIP/ZakariSIP\\nDOORTRUNK_FR = SIP/zakarifr',
                    dialplan_entry = %s,
                    carrier_description = 'DISABLED — provider gone; use ZakariSIP / zakarifr peers'
                WHERE carrier_id LIKE 'Door_App%%'
                """,
                (dialplan,),
            )
            cur.execute(
                """
                UPDATE vicidial_server_carriers SET
                    active = 'N',
                    dialplan_entry = '; Twilio désactivé — ZakariSIP par défaut'
                WHERE carrier_id = 'Twilio_QC'
                """
            )
            # Do NOT set rebuild_conf_files=Y — would regenerate Door_App peers from account_entry
            conn.commit()
            cur.close()
            _logger.info(
                "ensure_africa_con_door_trunk: Door_App* forced inactive; Zakari globals (server=%s)",
                server_ip,
            )
            return True
        finally:
            conn.close()

    def ensure_twilio_quebec_carrier(self):
        """Trunk Twilio +15817058118 pour sortants Québec (10/11 chiffres)."""
        carrier_id = "Twilio_QC"
        sip_user = self.env["ir.config_parameter"].sudo().get_param(
            "doorway_vicidial_campaigns.twilio_qc_sip_user", "vicidialqc"
        )
        sip_pass = self.env["ir.config_parameter"].sudo().get_param(
            "doorway_vicidial_campaigns.twilio_qc_sip_pass", "VicidialQC2026!"
        )
        from_number = self.env["ir.config_parameter"].sudo().get_param(
            "doorway_vicidial_campaigns.twilio_qc_from_number", "15817058118"
        )
        account_entry = (
            "[%s]\n"
            "type=peer\n"
            "host=15817058118.pstn.twilio.com\n"
            "port=5060\n"
            "username=%s\n"
            "secret=%s\n"
            "fromuser=%s\n"
            "fromdomain=15817058118.pstn.twilio.com\n"
            "context=trunkinbound\n"
            "insecure=port,invite\n"
            "qualify=yes\n"
            "disallow=all\n"
            "allow=ulaw\n"
            "allow=alaw\n"
            "dtmfmode=rfc2833\n"
            "sendrpid=yes\n"
            "trustrpid=no\n"
        ) % (carrier_id, sip_user, sip_pass, from_number)
        dialplan = (
            "exten => _NXXNXXXXXX,1,AGI(agi://127.0.0.1:4577/call_log)\n"
            "exten => _NXXNXXXXXX,2,Dial(${TWILIOQCTRUNK}/+1${EXTEN},${CAMPDTO},To)\n"
            "exten => _NXXNXXXXXX,3,Hangup\n"
            "exten => _1NXXNXXXXXX,1,AGI(agi://127.0.0.1:4577/call_log)\n"
            "exten => _1NXXNXXXXXX,2,Dial(${TWILIOQCTRUNK}/+${EXTEN},${CAMPDTO},To)\n"
            "exten => _1NXXNXXXXXX,3,Hangup"
        )
        conn = self._connect()
        try:
            cur = conn.cursor()
            cur.execute(
                "SELECT carrier_id FROM vicidial_server_carriers WHERE carrier_id = %s",
                (carrier_id,),
            )
            if not cur.fetchone():
                cur.execute(
                    """
                    INSERT INTO vicidial_server_carriers (
                        carrier_id, carrier_name, registration_string, template_id,
                        account_entry, protocol, globals_string, dialplan_entry,
                        server_ip, active, carrier_description, user_group
                    ) VALUES (%s, %s, '', '--NONE--', %s, 'SIP', %s, %s, %s, 'Y', %s, '---ALL---')
                    """,
                    (
                        carrier_id,
                        "Twilio Québec — Soumission QC",
                        account_entry,
                        "TWILIOQCTRUNK = SIP/%s" % carrier_id,
                        dialplan,
                        self._server_ip(),
                        "Twilio Elastic SIP — Québec +%s" % from_number,
                    ),
                )
            else:
                cur.execute(
                    """
                    UPDATE vicidial_server_carriers SET
                        carrier_name = %s,
                        account_entry = %s,
                        globals_string = %s,
                        dialplan_entry = %s,
                        active = 'Y',
                        carrier_description = %s
                    WHERE carrier_id = %s
                    """,
                    (
                        "Twilio Québec — Soumission QC",
                        account_entry,
                        "TWILIOQCTRUNK = SIP/%s" % carrier_id,
                        dialplan,
                        "Twilio Elastic SIP — Québec +%s" % from_number,
                        carrier_id,
                    ),
                )
            cur.execute(
                """
                UPDATE vicidial_campaigns SET campaign_cid = %s
                WHERE campaign_id LIKE 'DW_QC%%' OR campaign_id = 'DW_RAPQC'
                """,
                (from_number,),
            )
            conn.commit()
            cur.close()
            return True
        finally:
            conn.close()

    def ensure_quebec_outbound_dialing(self, campaign_id=None):
        """Campagnes QC/CA : trunk Door_App0 (10 chiffres 450… ou 11 chiffres 1…)."""
        self.ensure_africa_con_door_trunk()
        cid = (campaign_id or "")[:8]
        conn = self._connect(campaign_id=cid or None)
        try:
            cur = conn.cursor()
            sql = """
                UPDATE vicidial_campaigns
                SET omit_phone_code = 'Y', dial_prefix = '',
                    campaign_cid = %s,
                    campaign_name = CASE
                        WHEN campaign_id = 'DW_QCB2C'
                            THEN 'Québec B2C — Door_App0 (Estrie)'
                        WHEN campaign_id = 'DW_QCB2B'
                            THEN 'Québec B2B — Door_App0'
                        WHEN campaign_id = 'DW_RAPQC'
                            THEN 'B2C Rappels Québec — Door_App0'
                        WHEN campaign_id = 'SE_RENOV_QC'
                            THEN 'SoumissionEntrepreneurs QC Rénovation'
                        WHEN campaign_id = 'MR_IMMO_QC'
                            THEN 'MaisonRecherchee QC Vendeurs'
                        ELSE campaign_name
                    END
                WHERE campaign_id LIKE 'DW_QC%%'
                   OR campaign_id = 'DW_RAPQC'
                   OR campaign_id IN ('SE_RENOV_QC', 'MR_IMMO_QC')
            """
            qc_cid = self.env["ir.config_parameter"].sudo().get_param(
                "doorway_vicidial_campaigns.door_app0_caller_id", DOOR_APP0_QC_CALLER_ID
            )
            params = (qc_cid,)
            if cid:
                sql += " AND campaign_id = %s"
                params = (qc_cid, cid)
            cur.execute(sql, params)
            conn.commit()
            cur.close()
            return True
        finally:
            conn.close()

    def ensure_fr_campaign_cid(self, campaign_id=None):
        """Impose le CLI France Africa-Con (pas le numéro QC +1)."""
        fr_cid = self.env["ir.config_parameter"].sudo().get_param(
            "doorway_vicidial_campaigns.door_app0_fr_caller_id", DOOR_APP0_FR_CALLER_ID
        )
        ids = (
            [(campaign_id or "")[:8]]
            if campaign_id
            else list(DOOR_APP0_FR_CAMPAIGN_IDS)
        )
        conn = self._connect()
        try:
            cur = conn.cursor()
            placeholders = ",".join(["%s"] * len(ids))
            cur.execute(
                f"""
                UPDATE vicidial_campaigns
                SET campaign_cid = %s
                WHERE campaign_id IN ({placeholders})
                  AND (campaign_cid IS NULL OR campaign_cid != %s)
                """,
                (fr_cid, *ids, fr_cid),
            )
            conn.commit()
            cur.close()
            return True
        finally:
            conn.close()

    def ensure_france_outbound_dialing(self, campaign_id=None):
        """Campagnes France : trunk Door_App0_FR, indicatif 33 conservé."""
        self.ensure_africa_con_door_trunk()
        fr_cid = self.env["ir.config_parameter"].sudo().get_param(
            "doorway_vicidial_campaigns.door_app0_fr_caller_id", DOOR_APP0_FR_CALLER_ID
        )
        ids = (
            [(campaign_id or "")[:8]]
            if campaign_id
            else list(DOOR_APP0_FR_CAMPAIGN_IDS)
        )
        call_time = self._france_call_time_for_now()
        conn = self._connect()
        try:
            cur = conn.cursor()
            placeholders = ",".join(["%s"] * len(ids))
            cur.execute(
                f"""
                UPDATE vicidial_campaigns
                SET omit_phone_code = 'Y', dial_prefix = '',
                    campaign_cid = %s,
                    local_call_time = %s,
                    amd_send_to_vmx = 'N',
                    cpd_amd_action = 'DISPO',
                    campaign_vdad_exten = '8369',
                    dial_timeout = 30,
                    auto_dial_level = GREATEST(auto_dial_level, 2.5)
                WHERE campaign_id IN ({placeholders})
                """,
                (fr_cid, call_time, *ids),
            )
            conn.commit()
            cur.close()
            return True
        finally:
            conn.close()

    @staticmethod
    def _france_call_time_for_now():
        """Profil VICIdial selon l'heure Paris (10h-20h, pause déjeuner 13h-14h)."""
        try:
            from zoneinfo import ZoneInfo

            now = datetime.now(ZoneInfo("Europe/Paris"))
        except Exception:
            return "FR9AM1PM"
        if now.weekday() == 6:
            return "FRLUNCH"
        hm = now.hour * 100 + now.minute
        if 1000 <= hm < 1300:
            return "FR9AM1PM"
        if 1300 <= hm < 1400:
            return "FRLUNCH"
        if 1400 <= hm < 2000:
            return "FR2PM7PM"
        return "FRLUNCH"

    def reload_campaign_hopper(self, campaign, max_leads=None, list_id=None):
        """Recharge le hopper VICIdial (liste ciblée ou toutes les listes actives)."""
        campaign.ensure_one()
        cid = (campaign.vicidial_campaign_id or "")[:8]
        if not cid or not self.is_available():
            return 0

        if cid.startswith("DW_QC") or cid == "DW_RAPQC" or cid in QC_IA_CAMPAIGN_IDS:
            self.ensure_quebec_outbound_dialing(cid)
        elif cid.startswith("DW_FR"):
            self.ensure_france_outbound_dialing(cid)
        else:
            self.ensure_africa_con_door_trunk()

        target_list = (list_id or campaign.vicidial_list_id or "").strip()
        hopper_level = max_leads
        conn = self._connect()
        try:
            cur = conn.cursor()
            if hopper_level is None:
                cur.execute(
                    "SELECT hopper_level FROM vicidial_campaigns WHERE campaign_id = %s",
                    (cid,),
                )
                row = cur.fetchone()
                hopper_level = int(row[0]) if row and row[0] else 100

            cur.execute("DELETE FROM vicidial_hopper WHERE campaign_id = %s", (cid,))
            hopper_sql = """
                INSERT INTO vicidial_hopper (
                    lead_id, campaign_id, status, list_id,
                    gmt_offset_now, state, alt_dial, priority
                )
                SELECT vl.lead_id, %s, 'READY', vl.list_id,
                       vl.gmt_offset_now, vl.state, 'NONE', 0
                FROM vicidial_list vl
                INNER JOIN vicidial_lists vls ON vl.list_id = vls.list_id
                WHERE vls.campaign_id = %s AND vls.active = 'Y'
                  AND vl.status = 'NEW' AND vl.called_since_last_reset = 'N'
            """
            params = [cid, cid]
            if target_list:
                hopper_sql += " AND vl.list_id = %s"
                params.append(int(target_list))
            hopper_sql += " ORDER BY vl.lead_id LIMIT %s"
            params.append(int(hopper_level))
            cur.execute(hopper_sql, tuple(params))
            cur.execute(
                "SELECT COUNT(*) FROM vicidial_hopper WHERE campaign_id = %s",
                (cid,),
            )
            count_row = cur.fetchone()
            count = int(count_row[0]) if count_row else 0
            cur.execute(
                "UPDATE servers SET rebuild_conf_files = 'Y' WHERE generate_vicidial_conf = 'Y'"
            )
            conn.commit()
            cur.close()
            return count
        finally:
            conn.close()

    def is_manual_dial_campaign(self, campaign_id, odoo_auto_dial_mode=None):
        """True si la campagne est en numérotation manuelle (Odoo preview ou VICIdial MANUAL)."""
        if (odoo_auto_dial_mode or "").lower() == "preview":
            return True
        cid = (campaign_id or "")[:8]
        if not cid or not self.is_available():
            return False
        conn = self._connect()
        try:
            cur = conn.cursor(dictionary=True)
            cur.execute(
                """
                SELECT dial_method, auto_dial_level
                FROM vicidial_campaigns
                WHERE campaign_id = %s
                LIMIT 1
                """,
                (cid,),
            )
            row = cur.fetchone()
            cur.close()
            if not row:
                return False
            dial_method = (row.get("dial_method") or "").upper()
            level = row.get("auto_dial_level")
            try:
                level_f = float(level)
            except (TypeError, ValueError):
                level_f = 1.0
            if dial_method in ("MANUAL", "INBOUND_MAN"):
                return True
            return level_f <= 0
        finally:
            conn.close()

    def get_hopper_count(self, campaign_id):
        """Nombre de leads prêts dans le hopper VICIdial."""
        cid = (campaign_id or "")[:8]
        if not cid or not self.is_available():
            return 0
        conn = self._connect()
        try:
            cur = conn.cursor()
            cur.execute(
                "SELECT COUNT(*) FROM vicidial_hopper WHERE campaign_id = %s",
                (cid,),
            )
            row = cur.fetchone()
            cur.close()
            return int(row[0]) if row else 0
        finally:
            conn.close()

    def ensure_campaign_hopper(self, campaign, min_count=1):
        """Recharge le hopper si vide alors que des leads NEW existent."""
        campaign.ensure_one()
        cid = (campaign.vicidial_campaign_id or "")[:8]
        if not cid or not self.is_available():
            return 0
        current = self.get_hopper_count(cid)
        if current >= min_count:
            return current
        list_id = campaign.vicidial_list_id or None
        reloaded = self.reload_campaign_hopper(campaign, list_id=list_id)
        if reloaded > 0:
            return reloaded
        return self.get_hopper_count(cid)

    def _next_agent_webphone_extension(self, cur):
        cur.execute(
            """
            SELECT CAST(extension AS UNSIGNED) AS ext_num
            FROM phones
            WHERE extension REGEXP '^[0-9]+$' AND CAST(extension AS UNSIGNED) >= 86019
            ORDER BY CAST(extension AS UNSIGNED) DESC
            LIMIT 1
            """
        )
        row = cur.fetchone()
        base = int(row[0]) + 1 if row and row[0] else 86019
        return str(base)

    def _webrtc_sip_host(self):
        """FQDN SIP/WebRTC (certificat Let's Encrypt) — pas l'IP brute."""
        web = (self._icp.get_param("web.base.url") or "").strip()
        if web.startswith("https://"):
            from urllib.parse import urlparse

            host = urlparse(web).hostname or ""
            if host:
                return host
        return "intellixcrm.com"

    def _get_web_socket_url(self):
        server_ip = self._server_ip()
        host = self._webrtc_sip_host()
        default = "wss://%s/pjsip-ws" % host
        if not self.is_available():
            return default
        conn = self._connect()
        try:
            cur = conn.cursor()
            cur.execute(
                "SELECT web_socket_url FROM servers WHERE server_ip = %s LIMIT 1",
                (server_ip,),
            )
            row = cur.fetchone()
            cur.close()
            if row and row[0]:
                return str(row[0]).strip()
        except Exception:  # noqa: BLE001
            pass
        finally:
            conn.close()
        return default

    def ensure_webrtc_viciphone(self):
        """ViciPhone WebRTC : template PJSIP, URLs système, rebuild Asterisk."""
        if not self.is_available():
            return False
        server_ip = self._server_ip()
        host = self._webrtc_sip_host()
        webphone_url = "https://%s/vicidial-web/ViciPhone/viciphone.php" % host
        ws_url = "wss://%s/pjsip-ws" % host
        template = (
            "aor/max_contacts=10\n"
            "aor/remove_existing=yes\n"
            "aor/maximum_expiration=3600\n"
            "aor/minimum_expiration=60\n"
            "aor/default_expiration=120\n"
            "endpoint/rtcp_mux=yes\n"
            "endpoint/use_avpf=yes\n"
            "endpoint/transport=transport-wss\n"
            "endpoint/dtls_setup=actpass\n"
            "endpoint/ice_support=yes\n"
            "endpoint/dtls_verify=fingerprint\n"
            "endpoint/media_encryption=dtls\n"
            "endpoint/dtls_cert_file=/etc/asterisk/keys/intellixcrm-fullchain.pem\n"
            "endpoint/dtls_private_key=/etc/asterisk/keys/intellixcrm-privkey.pem\n"
            "endpoint/media_use_received_transport=yes\n"
            "endpoint/webrtc=yes\n"
            "endpoint/context=default\n"
            "endpoint/direct_media=no\n"
            "endpoint/from_domain=%s\n"
            "endpoint/rewrite_contact=yes\n"
            "endpoint/rtp_symmetric=yes\n"
            "endpoint/force_rport=yes\n"
            "endpoint/identify_by=username,auth_username,ip\n"
        ) % host
        conn = self._connect()
        try:
            cur = conn.cursor()
            cur.execute(
                """
                INSERT INTO vicidial_conf_templates
                    (template_id, template_name, template_contents, user_group)
                VALUES (%s, %s, %s, '---ALL---')
                ON DUPLICATE KEY UPDATE
                    template_name = VALUES(template_name),
                    template_contents = VALUES(template_contents)
                """,
                ("PJSIP_WEBRTC", "WebRTC ViciPhone", template),
            )
            cur.execute(
                "UPDATE system_settings SET webphone_url = %s",
                (webphone_url,),
            )
            cur.execute(
                """
                UPDATE servers SET
                    web_socket_url = %s,
                    rebuild_conf_files = 'Y'
                WHERE server_ip = %s
                """,
                (ws_url, server_ip),
            )
            cur.execute(
                """
                UPDATE phones SET
                    protocol = 'PJSIP',
                    template_id = '--NONE--',
                    is_webphone = 'Y',
                    webphone_auto_answer = 'Y',
                    codecs_list = 'ulaw,alaw,opus',
                    conf_override = '; WebRTC endpoint in pjsip_custom_webrtc.conf'
                WHERE extension = '86019' AND active = 'Y'
                """
            )
            cur.execute(
                """
                UPDATE phones SET
                    protocol = 'PJSIP',
                    template_id = 'PJSIP_WEBRTC',
                    is_webphone = 'Y',
                    webphone_auto_answer = 'Y',
                    codecs_list = 'ulaw,alaw,opus'
                WHERE is_webphone = 'Y' AND active = 'Y' AND extension != '86019'
                """
            )
            conn.commit()
            cur.close()
            self._ensure_pjsip_custom_webrtc_only()
            self._reload_asterisk_sip_stack()
            return True
        finally:
            conn.close()

    def _rebuild_vicidial_pjsip_phones(self):
        """Regénère pjsip_wizard-vicidial.conf (template PJSIP_WEBRTC sur 86019)."""
        import subprocess

        try:
            subprocess.run(
                [
                    "/usr/share/astguiclient/ADMIN_keepalive_ALL.pl",
                    "--cu3way",
                    "--noprompt",
                ],
                capture_output=True,
                timeout=120,
                check=False,
            )
        except Exception as exc:  # noqa: BLE001
            _logger.warning("_rebuild_vicidial_pjsip_phones: %s", exc)

    def _ensure_pjsip_custom_webrtc_only(self):
        """86019 dans pjsip_custom_webrtc.conf — wizard VICIdial désactivé."""
        from pathlib import Path

        wizard_conf = Path("/etc/asterisk/pjsip_wizard.conf")
        pjsip_conf = Path("/etc/asterisk/pjsip.conf")
        try:
            if wizard_conf.exists():
                text = wizard_conf.read_text()
                active = '#include "pjsip_wizard-vicidial.conf"'
                disabled = ';#include "pjsip_wizard-vicidial.conf"  ; WebRTC 86019 → pjsip_custom_webrtc.conf'
                if active in text and disabled not in text:
                    wizard_conf.write_text(text.replace(active, disabled))
            if pjsip_conf.exists():
                text = pjsip_conf.read_text()
                custom = '#include "pjsip_custom_webrtc.conf"'
                if custom not in text:
                    text = text.replace(
                        '#include "pjsip-vicidial.conf"',
                        '#include "pjsip-vicidial.conf"\n#include "pjsip_custom_webrtc.conf"',
                    )
                    pjsip_conf.write_text(text)
            self._strip_vicidial_wizard_extension("86019")
            self._add_pjsip_custom_webrtc_extension("86019", "Youness Marzguioui")
        except Exception as exc:  # noqa: BLE001
            _logger.warning("_ensure_pjsip_custom_webrtc_only: %s", exc)

    def _add_pjsip_custom_webrtc_extension(self, extension, full_name=None):
        """Endpoint WebRTC explicite (wizard VICIdial désactivé)."""
        from pathlib import Path

        ext = re.sub(r"\D", "", str(extension or ""))
        if not ext:
            return False
        path = Path("/etc/asterisk/pjsip_custom_webrtc.conf")
        marker = "[%s-auth]" % ext
        if path.exists() and marker in path.read_text():
            self._strip_vicidial_wizard_extension(ext)
            return True
        label = (full_name or ext).replace('"', "")[:40]
        block = (
            "\n; WebRTC agent %s\n"
            "[%s-auth]\n"
            "type=auth\n"
            "auth_type=userpass\n"
            "password=1234\n"
            "username=%s\n"
            "\n"
            "[%s]\n"
            "type=aor\n"
            "max_contacts=10\n"
            "remove_existing=yes\n"
            "\n"
            "[%s]\n"
            "type=endpoint\n"
            "transport=transport-wss\n"
            "context=default\n"
            "disallow=all\n"
            "allow=ulaw,alaw,opus\n"
            "auth=%s-auth\n"
            "aors=%s\n"
            "from_domain=intellixcrm.com\n"
            "identify_by=username,auth_username,ip\n"
            "rewrite_contact=yes\n"
            "rtp_symmetric=yes\n"
            "force_rport=yes\n"
            "webrtc=yes\n"
            "dtls_verify=fingerprint\n"
            "dtls_setup=actpass\n"
            "media_encryption=dtls\n"
            "dtls_cert_file=/etc/asterisk/keys/intellixcrm-fullchain.pem\n"
            "dtls_private_key=/etc/asterisk/keys/intellixcrm-privkey.pem\n"
            "media_use_received_transport=yes\n"
            "rtcp_mux=yes\n"
            "use_avpf=yes\n"
            "ice_support=yes\n"
            "direct_media=no\n"
            'callerid="%s" <15817058118>\n'
        ) % (ext, ext, ext, ext, ext, ext, ext, label)
        try:
            with path.open("a", encoding="utf-8") as handle:
                handle.write(block)
            self._strip_vicidial_wizard_extension(ext)
            self._reload_asterisk_sip_stack()
            return True
        except Exception as exc:  # noqa: BLE001
            _logger.warning("_add_pjsip_custom_webrtc_extension %s: %s", ext, exc)
            return False

    def _preferred_conf_exten(self, vicidial_user):
        """Salles de conf dédiées (isolation tests / prod)."""
        login = (vicidial_user or "").strip()
        raw = {
            "karine": "9600053",
            "karine_test": "9600001",
            "leiladaouadi": "8600055",
        }.get(login)
        if not raw:
            return None
        if self._get_conf_engine() == "CONFBRIDGE" and raw.startswith("860"):
            return "9" + raw[1:]
        return raw

    def _create_vicidial_agent_log(self, cur, login, server_ip, campaign_id, user_group):
        """Crée une entrée vicidial_agent_log (requis pour manDiaLnextCaLL / MySQL 8)."""
        import time

        epoch = int(time.time())
        now = self._os_local_now()
        cur.execute(
            """
            INSERT INTO vicidial_agent_log (
                user, server_ip, event_time, campaign_id,
                pause_epoch, pause_sec, wait_epoch, user_group, sub_status, pause_type
            ) VALUES (%s, %s, %s, %s, %s, 0, %s, %s, 'LOGIN', 'AGENT')
            """,
            (login, server_ip, now, campaign_id, epoch, epoch, user_group or "AGENTS"),
        )
        return cur.lastrowid

    def _resolve_agent_log_id(self, login):
        """Dernier agent_log_id VICIdial pour numérotation manuelle Odoo."""
        conn = self._connect()
        try:
            cur = conn.cursor()
            cur.execute(
                """
                SELECT agent_log_id FROM vicidial_agent_log
                WHERE user = %s
                ORDER BY agent_log_id DESC
                LIMIT 1
                """,
                (login,),
            )
            row = cur.fetchone()
            cur.close()
            return int(row[0]) if row and row[0] else 0
        finally:
            conn.close()

    def _strip_vicidial_wizard_extension(self, extension):
        """Retire un wizard VICIdial en conflit (legacy)."""
        import re
        from pathlib import Path

        path = Path("/etc/asterisk/pjsip_wizard-vicidial.conf")
        if not path.exists():
            return
        try:
            text = path.read_text()
            pattern = r"\n\[%s\][\s\S]*?(?=\n\n; END OF FILE|\Z)" % re.escape(
                extension
            )
            cleaned = re.sub(pattern, "\n", text)
            marker = "; %s → pjsip_custom_webrtc.conf\n" % extension
            if marker not in cleaned:
                cleaned = cleaned.replace(
                    "; PJSIP_WIZ Phone Settings: \n",
                    "; PJSIP_WIZ Phone Settings: \n\n%s" % marker,
                )
            if cleaned != text:
                path.write_text(cleaned)
        except Exception as exc:  # noqa: BLE001
            _logger.warning("_strip_vicidial_wizard_extension %s: %s", extension, exc)

    def _reload_asterisk_sip_stack(self):
        """Évite que chan_sip (UDP) bloque l'enregistrement WebRTC PJSIP.

        sudo -n : jamais de prompt mot de passe (sinon le process Odoo unique
        bloque jusqu'à 15s x 2 à chaque cron, ce qui rend /web/login glacial).
        """
        import subprocess

        for cmd in (
            ["sudo", "-n", "asterisk", "-rx", "module reload chan_sip.so"],
            ["sudo", "-n", "asterisk", "-rx", "pjsip reload"],
        ):
            try:
                subprocess.run(cmd, capture_output=True, timeout=3, check=False)
            except Exception:  # noqa: BLE001
                _logger.debug("asterisk reload skipped: %s", cmd)

    def _asterisk_rx(self, command):
        """Exécute une commande CLI Asterisk (sudo pour user odoo)."""
        import subprocess

        try:
            proc = subprocess.run(
                ["sudo", "-n", "/usr/local/bin/doorway-asterisk-rx", command],
                capture_output=True,
                text=True,
                timeout=12,
                check=False,
            )
            return (proc.stdout or "") + (proc.stderr or "")
        except Exception as exc:  # noqa: BLE001
            _logger.debug("asterisk rx failed %s: %s", command, exc)
            return ""

    def _agent_in_confbridge_db(self, extension, conf_exten):
        """Conf agent réservée dans vicidial_confbridges (PJSIP/86020)."""
        ext = re.sub(r"\D", "", str(extension or ""))
        room = str(conf_exten or "").strip()
        if not ext or not room or not self.is_available():
            return False
        server_ip = self._server_ip()
        table = self._conf_table()
        conn = self._connect()
        try:
            cur = conn.cursor()
            cur.execute(
                """
                SELECT extension FROM %s
                WHERE conf_exten = %%s AND server_ip = %%s
                LIMIT 1
                """
                % table,
                (room, server_ip),
            )
            row = cur.fetchone()
            cur.close()
            if not row or not row[0]:
                return False
            return ext in re.sub(r"\D", "", str(row[0]))
        except Exception:  # noqa: BLE001
            return False
        finally:
            conn.close()

    def _agent_in_confbridge(self, extension, conf_exten):
        """True si l'extension webphone est dans la conf agent (état Incall ViciPhone)."""
        if self._agent_in_confbridge_db(extension, conf_exten):
            return True
        ext = re.sub(r"\D", "", str(extension or ""))
        room = str(conf_exten or "").strip()
        if not ext or not room:
            return False
        out = self._asterisk_rx("confbridge list %s" % room)
        return bool(re.search(r"PJSIP/%s\b" % ext, out, re.I))


    def ensure_webphone_in_conference(self, vicidial_user, conf_exten=None):
        """Place le webphone PJSIP dans ConfBridge (29600XXX) si ViciPhone SESSION a échoué."""
        import time

        login = (vicidial_user or "").strip()[:20]
        if not login or not self.is_available():
            return {"ok": False, "reason": "unavailable"}
        live = self.get_agent_live_status(login)
        room = (conf_exten or live.get("conf_exten") or "").strip()
        ext = self.get_agent_phone_extension(login)
        if not room or not ext:
            return {"ok": False, "reason": "missing_room_or_ext"}
        if self._agent_in_confbridge(ext, room):
            return {"ok": True, "skipped": True, "reason": "already_in_conf"}
        if not self.get_pjsip_registered(ext):
            return {"ok": False, "reason": "pjsip_not_registered"}
        dial = self._webphone_session_dial_exten(room)
        if not dial:
            return {"ok": False, "reason": "no_dial_exten"}
        channel = "PJSIP/%s" % ext
        cli = self._asterisk_rx(
            "channel originate %s extension %s@default" % (channel, dial)
        )
        time.sleep(0.9)
        joined = self._agent_in_confbridge(ext, room)
        if joined:
            server_ip = self._server_ip()
            table = self._conf_table()
            conn = self._connect()
            try:
                cur = conn.cursor()
                cur.execute(
                    """
                    UPDATE %s
                    SET extension = %%s, leave_3way = '0'
                    WHERE conf_exten = %%s AND server_ip = %%s
                    """
                    % table,
                    ("PJSIP/%s" % ext, room, server_ip),
                )
                conn.commit()
                cur.close()
            finally:
                conn.close()
        return {"ok": joined, "joined": joined, "cli": (cli or "")[:160]}

    def recover_agent_after_webphone_hangup(self, vicidial_user, conf_exten=None):
        """Réconcilie l'état agent après coupure WebRTC ou INCALL orphelin en base."""
        login = (vicidial_user or "").strip()[:20]
        if not login or not self.is_available():
            return {"ok": False}
        live = self.get_agent_live_status(login)
        status = (live.get("status") or "").upper()
        room = (conf_exten or live.get("conf_exten") or "").strip()
        ext = self.get_agent_phone_extension(login)
        channel = (live.get("channel") or "").strip()
        in_conf = ext and room and self._agent_in_confbridge(ext, room)
        pjsip_ok = self.get_pjsip_registered(ext) if ext else False

        # Appel actif réel — ne jamais clear_webphone / pjsip reload (tue le micro WebRTC).
        if status in ("INCALL", "QUEUE", "DIAL") and (channel or in_conf):
            return {"ok": True, "skipped": True, "reason": "active_call"}

        # État nominal WebRTC : READY dans la conf agent — ne jamais expulser.
        if status == "READY" and in_conf:
            return {"ok": True, "skipped": True, "reason": "ready_in_conf"}

        # Conf zombie sans contact PJSIP (webphone déconnecté, agent en pause système).
        if in_conf and not pjsip_ok and status in ("PAUSED", "CLOSER", "DISPO"):
            self.clear_webphone_extension(ext, room, kick_agent=True, reload_pjsip=False)
            return {"ok": True, "recovered": True, "reason": "cleared_zombie_conf"}

        if status not in ("INCALL", "QUEUE", "DIAL"):
            return {"ok": True, "skipped": True}

        keys = self._vicidial_live_user_keys(login)
        placeholders = ",".join(["%s"] * len(keys))
        conn = self._connect()
        try:
            cur = conn.cursor()
            cur.execute(
                """
                UPDATE vicidial_live_agents
                SET status = 'READY', lead_id = 0, channel = '', callerid = '',
                    uniqueid = '', external_hangup = 0, external_dial = '',
                    external_status = '', external_pause = '', comments = 'REMOTE',
                    last_state_change = NOW(), last_update_time = NOW()
                WHERE user IN (%s) AND status IN ('INCALL', 'QUEUE', 'DIAL')
                """
                % placeholders,
                tuple(keys),
            )
            updated = cur.rowcount
            conn.commit()
            cur.close()
            return {"ok": updated > 0, "recovered": updated > 0}
        finally:
            conn.close()

    def clear_webphone_extension(
        self, extension, conf_exten=None, kick_agent=False, reload_pjsip=False
    ):
        """Libère une extension webphone (canaux zombie, optionnel kick conf + reload PJSIP)."""
        ext = re.sub(r"\D", "", str(extension or ""))
        if not ext:
            return False
        room = str(conf_exten or "").strip()
        cleared = []
        out = self._asterisk_rx("core show channels concise")
        for line in (out or "").splitlines():
            chan = (line.split("!")[0] or "").strip()
            if not chan:
                continue
            hang = False
            if kick_agent and bool(re.search(r"PJSIP/%s-" % ext, line, re.I)):
                hang = True
            if room and room in line:
                if chan.startswith("CBAnn/"):
                    hang = True
                elif kick_agent and re.search(r"PJSIP/%s\b" % ext, line, re.I):
                    hang = True
            if hang:
                self._asterisk_rx("channel request hangup %s" % chan)
                cleared.append(chan)
        if kick_agent and room:
            conf_out = self._asterisk_rx("confbridge list %s" % room)
            if re.search(r"PJSIP/%s\b" % ext, conf_out, re.I):
                self._asterisk_rx("confbridge kick %s PJSIP/%s all" % (room, ext))
        if reload_pjsip:
            self._asterisk_rx("pjsip reload")
        return bool(cleared) or bool(kick_agent and room)

    def get_webphone_call_ready(self, vicidial_user, conf_exten=None):
        """Prêt à recevoir/placer un appel (PJSIP enregistré ou déjà en conf Incall)."""
        live = self.get_agent_live_status(vicidial_user)
        status = (live.get("status") or "").upper()
        if status in ("INCALL", "QUEUE", "DIAL"):
            return True
        ext = self.get_agent_phone_extension(vicidial_user)
        if not conf_exten:
            conf_exten = live.get("conf_exten")
        if self._agent_in_confbridge_db(ext, conf_exten):
            return True
        if self.get_pjsip_registered(ext):
            return True
        return self._agent_in_confbridge(ext, conf_exten)

    def get_pjsip_registered(self, extension):
        """True si le webphone a un contact PJSIP actif (Reachable/Avail)."""
        ext = re.sub(r"\D", "", str(extension or ""))
        if not ext:
            return False
        out = self._asterisk_rx("pjsip show aor %s" % ext)
        if "Unable to find object" in out:
            return False
        return bool(re.search(r"Contact:\s+\S+/sip:", out, re.I))

    def get_agent_phone_extension(self, vicidial_user):
        login = (vicidial_user or "").strip()[:20]
        if not login or not self.is_available():
            return ""
        conn = self._connect()
        try:
            cur = conn.cursor()
            cur.execute(
                "SELECT phone_login FROM vicidial_users WHERE user = %s LIMIT 1",
                (login,),
            )
            row = cur.fetchone()
            cur.close()
            return (row[0] if row else "") or ""
        finally:
            conn.close()

    def ensure_agent_webphone(self, vicidial_user, full_name=None):
        """Crée ou met à jour un webphone PJSIP WebRTC pour un agent humain."""
        login = (vicidial_user or "").strip()[:20]
        if not login or not self.is_available():
            return False

        self.ensure_webrtc_viciphone()
        server_ip = self._server_ip()
        conn = self._connect()
        try:
            cur = conn.cursor()
            cur.execute(
                "SELECT phone_login FROM vicidial_users WHERE user = %s LIMIT 1",
                (login,),
            )
            user_row = cur.fetchone()
            phone_login = (user_row[0] if user_row else "") or ""
            if phone_login:
                cur.execute(
                    """
                    SELECT extension FROM phones
                    WHERE (extension = %s OR login = %s) AND active = 'Y'
                    LIMIT 1
                    """,
                    (phone_login, phone_login),
                )
                if cur.fetchone():
                    cur.execute(
                        """
                        UPDATE phones SET
                            protocol = 'PJSIP',
                            template_id = '--NONE--',
                            is_webphone = 'Y',
                            webphone_auto_answer = 'Y',
                            conf_secret = COALESCE(NULLIF(conf_secret, ''), '1234'),
                            codecs_list = 'ulaw,alaw,opus',
                            conf_override = '; WebRTC endpoint in pjsip_custom_webrtc.conf'
                        WHERE extension = %s OR login = %s
                        """,
                        (phone_login, phone_login),
                    )
                    self._ensure_pjsip_custom_webrtc_only()
                    self._add_pjsip_custom_webrtc_extension(
                        phone_login, full_name or login
                    )
                    self._reload_asterisk_sip_stack()
                    conn.commit()
                    cur.close()
                    return True

            extension = self._next_agent_webphone_extension(cur)
            cur.execute(
                """
                INSERT INTO phones (
                    extension, dialplan_number, voicemail_id, server_ip,
                    login, pass, status, active, phone_type, fullname,
                    protocol, local_gmt, is_webphone, template_id,
                    phone_context, conf_secret, webphone_dialpad,
                    webphone_auto_answer, on_hook_agent,
                    AGI_call_logging_enabled, user_switching_enabled,
                    conferencing_enabled, admin_monitor_enabled,
                    call_parking_enabled, auto_dial_next_number, codecs_list
                ) VALUES (
                    %s, %s, %s, %s, %s, '1234', 'ACTIVE', 'Y',
                    'VICIPHONE', %s, 'PJSIP', '-5.00', 'Y', 'PJSIP_WEBRTC',
                    'default', '1234', 'N', 'Y', 'N',
                    '1', '1', '1', '1', '1', '1', 'ulaw,alaw,opus'
                )
                """,
                (
                    extension,
                    extension,
                    extension,
                    server_ip,
                    extension,
                    (full_name or login)[:50],
                ),
            )
            cur.execute(
                """
                UPDATE vicidial_users
                SET phone_login = %s, phone_pass = '1234'
                WHERE user = %s
                """,
                (extension, login),
            )
            cur.execute(
                "UPDATE servers SET rebuild_conf_files = 'Y' WHERE server_ip = %s",
                (server_ip,),
            )
            conn.commit()
            cur.close()
            self._ensure_pjsip_custom_webrtc_only()
            self._add_pjsip_custom_webrtc_extension(extension, full_name or login)
            self._reload_asterisk_sip_stack()
            return True
        finally:
            conn.close()

    @property
    def agent_api_base(self):
        cfg = self._load_config()
        return "%s/agc/api.php" % cfg["base_url"]

    @staticmethod
    def _row_value(row, index=0):
        if not row:
            return None
        if isinstance(row, dict):
            return list(row.values())[index]
        return row[index]

    def _get_conf_engine(self):
        server_ip = self._server_ip()
        if not self.is_available():
            return "MEETME"
        conn = self._connect()
        try:
            cur = conn.cursor()
            cur.execute(
                "SELECT conf_engine FROM servers WHERE server_ip = %s LIMIT 1",
                (server_ip,),
            )
            row = cur.fetchone()
            cur.close()
            engine = (self._row_value(row) or "MEETME").strip().upper()
            return engine if engine in ("MEETME", "CONFBRIDGE") else "MEETME"
        finally:
            conn.close()

    def _conf_table(self):
        return (
            "vicidial_confbridges"
            if self._get_conf_engine() == "CONFBRIDGE"
            else "vicidial_conferences"
        )

    def _conf_room_start(self):
        return 9600051 if self._get_conf_engine() == "CONFBRIDGE" else 8600051

    def _webphone_session_dial_exten(self, conf_exten):
        """Extension à composer dans ViciPhone pour rejoindre la conf agent."""
        exten = str(conf_exten or "").strip()
        if not exten:
            return ""
        # ConfBridge agent entry is the dialplan pattern _29600XXX (rooms 9600XXX):
        # only a genuine ConfBridge room may receive the "2" prefix. Prefixing any
        # other room number (e.g. a stale MeetMe 8600XXX room) produces 28600XXX,
        # which matches the outbound carrier route _28X. and is rejected by the
        # carrier with SIP 403 "No Rates Found" instead of joining the conference.
        if self._get_conf_engine() == "CONFBRIDGE" and exten.startswith("9600"):
            return "2%s" % exten
        return exten

    def _ensure_conference_rooms(self, cur, server_ip, start=None, count=80):
        if start is None:
            start = self._conf_room_start()
        table = self._conf_table()
        cur.execute(
            "SELECT COUNT(*) FROM %s WHERE server_ip = %%s" % table,
            (server_ip,),
        )
        row = cur.fetchone()
        existing = int(self._row_value(row) or 0)
        if existing >= 10:
            return existing
        for offset in range(count):
            conf_exten = start + offset
            cur.execute(
                """
                INSERT IGNORE INTO %s (conf_exten, server_ip, extension)
                VALUES (%%s, %%s, '')
                """
                % table,
                (conf_exten, server_ip),
            )
        return start + count

    def _release_agent_conference(self, cur, vicidial_user, server_ip):
        table = self._conf_table()
        cur.execute(
            "SELECT conf_exten FROM vicidial_live_agents WHERE user = %s LIMIT 1",
            (vicidial_user,),
        )
        row = cur.fetchone()
        conf_exten = self._row_value(row)
        if conf_exten:
            cur.execute(
                """
                UPDATE %s
                SET extension = '', leave_3way = '0'
                WHERE conf_exten = %%s AND server_ip = %%s
                """
                % table,
                (conf_exten, server_ip),
            )
        phone = self._vicidial_phone_login(vicidial_user)
        if phone:
            cur.execute(
                "UPDATE %s SET extension = '', leave_3way = '0' WHERE server_ip = %%s AND extension IN (%%s, %%s)" % table,
                (server_ip, "PJSIP/%s" % phone, "SIP/%s" % phone),
            )

    def _generate_vicidial_session_name(self, extension):
        import random
        import re
        import time

        session_ext = re.sub(r"[^a-z0-9]", "", (extension or "").lower())[:10]
        session_rand = random.randint(1, 9999999) + 10000000
        return "%s_%s%s" % (int(time.time()), session_ext, session_rand)

    def get_vicidial_web_session_name(self, vicidial_user):
        """Session_name courante enregistrée côté VICIdial (web_client_sessions)."""
        login = (vicidial_user or "").strip()[:20]
        if not login or not self.is_available():
            return ""
        server_ip = self._server_ip()
        conn = self._connect()
        try:
            cur = conn.cursor(dictionary=True)
            cur.execute(
                """
                SELECT session_name
                FROM vicidial_session_data
                WHERE user = %s AND server_ip = %s
                ORDER BY login_time DESC
                LIMIT 1
                """,
                (login, server_ip),
            )
            row = cur.fetchone()
            cur.close()
            return str(row.get("session_name") or "").strip() if row else ""
        finally:
            conn.close()

    def resolve_vicidial_session_name(self, vicidial_user, session_name):
        """Préfère le session_name VICIdial DB (évite stale Odoo après reconnexion)."""
        stored = (session_name or "").strip()
        db_name = self.get_vicidial_web_session_name(vicidial_user)
        if db_name:
            return db_name
        return stored

    def _vdc_db_query_error(self, body):
        """Interprète la réponse vdc_db_query.php (manDiaLnextCaLL, etc.)."""
        upper = (body or "").upper()
        if "INVALID SESSION_NAME" in upper or "INVALID USERNAME" in upper:
            return {
                "ok": False,
                "message": _(
                    "Session VICIdial expirée — actualisez la page (Ctrl+F5) "
                    "ou terminez puis redémarrez la session."
                ),
                "reason": "invalid_session_name",
            }
        if "NOTINSYSTEM" in upper:
            return {
                "ok": False,
                "message": _(
                    "Numéro absent du système — vérifiez le filtre composition manuelle."
                ),
            }
        if "NOTINCAMPLISTS" in upper:
            return {
                "ok": False,
                "message": _("Numéro absent des listes de la campagne."),
            }
        if "HOPPER EMPTY" in upper and "PHONE" not in upper:
            return {"ok": False, "message": _("Aucun prospect dans la file (hopper vide).")}
        if "ALREADY INCALL" in upper:
            return {"ok": False, "message": _("Vous êtes déjà en appel.")}
        if "OUTSIDE OF LOCAL CALL TIME" in upper or "NOTINCALLTIME" in upper:
            return {
                "ok": False,
                "message": _("Hors plage horaire d'appel pour ce numéro."),
            }
        first_line = (body or "").split("\n")[0].upper()
        if "ERROR" in first_line:
            return {"ok": False, "message": (body or "").split("\n")[0][:200]}
        return None

    def register_vicidial_web_session(
        self, cur, login, campaign_id, conf_exten, extension, session_name=None
    ):
        """Enregistre web_client_sessions + vicidial_session_data (requis par conf_exten_check)."""
        server_ip = self._server_ip()
        cid = (campaign_id or "")[:8]
        sip_extension = extension or ""
        if "/" in sip_extension:
            sip_extension = sip_extension.split("/", 1)[1]
        session_name = session_name or self._generate_vicidial_session_name(
            sip_extension
        )
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        cur.execute(
            "DELETE FROM web_client_sessions WHERE extension = %s AND server_ip = %s",
            (extension, server_ip),
        )
        cur.execute(
            """
            INSERT INTO web_client_sessions
                (extension, server_ip, program, start_time, session_name)
            VALUES (%s, %s, 'vicidial', %s, %s)
            """,
            (extension, server_ip, now, session_name),
        )
        cur.execute(
            "DELETE FROM vicidial_session_data WHERE user = %s AND server_ip = %s",
            (login, server_ip),
        )
        cur.execute(
            """
            INSERT INTO vicidial_session_data
                (session_name, user, campaign_id, server_ip, conf_exten,
                 extension, login_time, webphone_url, agent_login_call)
            VALUES (%s, %s, %s, %s, %s, %s, %s, '', '')
            """,
            (
                session_name,
                login,
                cid,
                server_ip,
                conf_exten,
                extension,
                now,
            ),
        )
        return session_name

    def send_conf_exten_heartbeat(
        self, vicidial_user, session_name, campaign_id, conf_exten
    ):
        """Heartbeat natif VICIdial via conf_exten_check.php (équivalent dialpad JS)."""
        import urllib.error
        import urllib.parse
        import urllib.request

        login = (vicidial_user or "").strip()[:20]
        session_name = (session_name or "").strip()
        cid = (campaign_id or "")[:8]
        conf_exten = (conf_exten or "").strip()
        if not login or not session_name or not conf_exten or not self.is_available():
            return {"ok": False, "reason": "missing_params"}

        conn = self._connect()
        try:
            cur = conn.cursor(dictionary=True)
            cur.execute(
                "SELECT pass FROM vicidial_users WHERE user = %s LIMIT 1",
                (login,),
            )
            user_row = cur.fetchone()
            cur.execute(
                "SELECT auto_dial_level FROM vicidial_campaigns WHERE campaign_id = %s LIMIT 1",
                (cid,),
            )
            camp_row = cur.fetchone()
            cur.close()
            if not user_row:
                return {"ok": False, "reason": "user_not_found"}
            vd_pass = user_row.get("pass") or ""
            auto_dial_level = camp_row.get("auto_dial_level") if camp_row else "1"
        finally:
            conn.close()

        server_ip = self._server_ip()
        base = self.env["ir.config_parameter"].sudo().get_param(
            "doorway_vicidial_campaigns.conf_exten_check_url",
            "http://127.0.0.1:8080/agc/conf_exten_check.php",
        )
        payload = urllib.parse.urlencode(
            {
                "server_ip": server_ip,
                "session_name": session_name,
                "user": login,
                "pass": vd_pass,
                "client": "vdc",
                "conf_exten": conf_exten,
                "auto_dial_level": str(auto_dial_level or "1"),
                "campagentstdisp": "NO",
                "campaign": cid,
                "customer_chat_id": "",
                "live_call_seconds": "0",
                "active_ingroup_dial": "",
                "xferchannel": "",
                "check_for_answer": "N",
                "MDnextCID": "",
                "phone_number": "",
                "visibility": "",
                "latency": "0",
                "dead_count": "0",
                "clicks": "",
                "ACTION": "refresh",
            }
        ).encode("utf-8")
        req = urllib.request.Request(
            base,
            data=payload,
            method="POST",
            headers={"Content-Type": "application/x-www-form-urlencoded; charset=UTF-8"},
        )
        try:
            with urllib.request.urlopen(req, timeout=8) as resp:
                body = (resp.read() or b"").decode("utf-8", errors="replace")
            if "Invalid session_name" in body or "Invalid Username" in body:
                return {"ok": False, "reason": "auth_failed", "body": body[:200]}
            return {"ok": True, "body_preview": body[:120]}
        except urllib.error.URLError as exc:
            _logger.warning("conf_exten_check heartbeat failed %s: %s", login, exc)
            return {"ok": False, "reason": str(exc)}

    def _vdc_db_query_url(self):
        icp = self.env["ir.config_parameter"].sudo()
        url = (
            icp.get_param("doorway_vicidial_campaigns.vdc_db_query_url") or ""
        ).strip()
        if url:
            return url
        check_url = (
            icp.get_param("doorway_vicidial_campaigns.conf_exten_check_url") or ""
        ).strip()
        if check_url and "conf_exten_check.php" in check_url:
            return check_url.replace("conf_exten_check.php", "vdc_db_query.php")
        base = self._resolve_vicidial_base_url(
            lambda *a, **k: "http://localhost:8080"
        ).rstrip("/")
        return "%s/agc/vdc_db_query.php" % base

    def _manager_send_url(self):
        icp = self.env["ir.config_parameter"].sudo()
        url = (
            icp.get_param("doorway_vicidial_campaigns.manager_send_url") or ""
        ).strip()
        if url:
            return url
        check_url = (
            icp.get_param("doorway_vicidial_campaigns.conf_exten_check_url") or ""
        ).strip()
        if check_url and "conf_exten_check.php" in check_url:
            return check_url.replace("conf_exten_check.php", "manager_send.php")
        base = self._resolve_vicidial_base_url(
            lambda *a, **k: "http://localhost:8080"
        ).rstrip("/")
        return "%s/agc/manager_send.php" % base

    @staticmethod
    def _vicidial_user_abb(login):
        abb = (login or "") * 4
        stop = 0
        while len(abb) > 4 and stop < 200:
            abb = re.sub(r"^\.", "", abb, count=1)
            stop += 1
        return abb

    def _find_conf_customer_channels(self, conf_exten, agent_extension):
        """Canaux client dans la conf agent (hors webphone PJSIP de l agent)."""
        room = str(conf_exten or "").strip()
        agent_ext = re.sub(r"\D", "", str(agent_extension or ""))
        if not room:
            return []
        channels = []
        seen = set()

        def _add(chan):
            chan = (chan or "").strip()
            if not chan or chan in seen:
                return
            if agent_ext and re.search(r"PJSIP/%s[-/]" % agent_ext, chan, re.I):
                return
            seen.add(chan)
            channels.append(chan)

        out = self._asterisk_rx("confbridge list %s" % room)
        if "No conference bridge" not in out:
            for line in (out or "").splitlines():
                m = re.match(
                    r"^(PJSIP/\S+|Local/\S+|SIP/\S+|IAX2/\S+)",
                    line.strip(),
                )
                if m:
                    _add(m.group(1))

        server_ip = self._server_ip()
        if self.is_available():
            conn = self._connect()
            try:
                cur = conn.cursor()
                for table in ("live_sip_channels", "live_channels"):
                    cur.execute(
                        """
                        SELECT channel FROM %s
                        WHERE server_ip = %%s AND extension = %%s
                        """
                        % table,
                        (server_ip, room),
                    )
                    for row in cur.fetchall() or []:
                        _add(self._row_value(row))
                cur.close()
            finally:
                conn.close()

        concise = self._asterisk_rx("core show channels concise")
        for line in (concise or "").splitlines():
            parts = line.split("!")
            if len(parts) < 8:
                continue
            chan, bridged = parts[0], parts[7] if len(parts) > 7 else ""
            if room in bridged or room in line:
                _add(chan)
        return channels

    def _manager_send_hangup(
        self,
        vicidial_user,
        vd_pass,
        session_name,
        channel,
        conf_exten,
        campaign_id,
        call_server_ip=None,
    ):
        import time
        import urllib.error
        import urllib.parse
        import urllib.request

        login = (vicidial_user or "").strip()[:20]
        chan = (channel or "").strip()
        if not login or not chan:
            return {"ok": False, "reason": "missing_channel"}
        server_ip = self._server_ip()
        query_cid = "HLvdcW%d%s" % (
            int(time.time()),
            self._vicidial_user_abb(login),
        )
        payload = urllib.parse.urlencode(
            {
                "server_ip": server_ip,
                "session_name": session_name or "",
                "ACTION": "Hangup",
                "format": "text",
                "user": login,
                "pass": vd_pass or "",
                "channel": chan,
                "call_server_ip": call_server_ip or server_ip,
                "queryCID": query_cid,
                "auto_dial_level": "0",
                "exten": conf_exten or "",
                "campaign": (campaign_id or "")[:8],
                "stage": "CALLHANGUP",
                "nodeletevdac": "",
                "log_campaign": (campaign_id or "")[:8],
            }
        ).encode("utf-8")
        req = urllib.request.Request(
            self._manager_send_url(),
            data=payload,
            method="POST",
            headers={
                "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8"
            },
        )
        try:
            with urllib.request.urlopen(req, timeout=12) as resp:
                body = (resp.read() or b"").decode("utf-8", errors="replace")
            ok = bool(body.strip()) and "not inserted" not in body.lower()
            return {"ok": ok, "body": body[:200]}
        except urllib.error.URLError as exc:
            _logger.warning("manager_send hangup failed %s %s: %s", login, chan, exc)
            return {"ok": False, "reason": str(exc)}

    def hangup_agent_call(
        self,
        vicidial_user,
        session_name=None,
        campaign_id=None,
        conf_exten=None,
    ):
        """Raccroche le client en conf et repasse l agent en READY (poste Odoo)."""
        login = (vicidial_user or "").strip()[:20]
        if not login or not self.is_available():
            return {"ok": False, "message": "VICIdial indisponible"}
        session_name = self.resolve_vicidial_session_name(vicidial_user, session_name)
        server_ip = self._server_ip()
        conn = self._connect()
        try:
            cur = conn.cursor(dictionary=True)
            cur.execute(
                """
                SELECT user, status, lead_id, campaign_id, channel, conf_exten,
                       call_server_ip, callerid, uniqueid
                FROM vicidial_live_agents
                WHERE user = %s
                LIMIT 1
                """,
                (login,),
            )
            live = cur.fetchone()
            cur.execute(
                "SELECT pass FROM vicidial_users WHERE user = %s LIMIT 1",
                (login,),
            )
            user_row = cur.fetchone()
            cur.execute(
                "SELECT ext_context FROM servers WHERE server_ip = %s LIMIT 1",
                (server_ip,),
            )
            srv = cur.fetchone()
            cur.close()
        finally:
            conn.close()

        if not live:
            return {"ok": False, "message": "Agent non connecté à VICIdial"}

        status = (live.get("status") or "").upper()
        vd_pass = (user_row or {}).get("pass") or ""
        room = (conf_exten or live.get("conf_exten") or "").strip()
        cid = (campaign_id or live.get("campaign_id") or "")[:8]
        agent_ext = self.get_agent_phone_extension(login)
        lead_id = int(live.get("lead_id") or 0)
        in_call_status = status in ("INCALL", "QUEUE", "DIAL")
        in_conf = agent_ext and room and self._agent_in_confbridge(agent_ext, room)
        live_channel = (live.get("channel") or "").strip()
        if not in_call_status and not in_conf and not live_channel:
            orphan = (
                self._find_conf_customer_channels(room, agent_ext) if room else []
            )
            if not orphan:
                return {"ok": True, "skipped": True, "message": "Pas en appel actif"}

        hung = []

        channels = self._find_conf_customer_channels(room, agent_ext)
        if live_channel and live_channel not in channels:
            if not agent_ext or agent_ext not in live_channel:
                channels.insert(0, live_channel)

        for chan in channels:
            res = self._manager_send_hangup(
                login,
                vd_pass,
                session_name,
                chan,
                room,
                cid,
                live.get("call_server_ip") or server_ip,
            )
            if res.get("ok"):
                hung.append(chan)
            else:
                self._asterisk_rx("channel request hangup %s" % chan)

        ext_context = (srv or {}).get("ext_context") or "default"
        if room and not hung:
            import time
            import urllib.error
            import urllib.parse
            import urllib.request

            query_cid = "GTvdcW%d%s" % (
                int(time.time()),
                self._vicidial_user_abb(login),
            )
            payload = urllib.parse.urlencode(
                {
                    "server_ip": server_ip,
                    "session_name": session_name or "",
                    "ACTION": "HangupConfDial",
                    "format": "text",
                    "user": login,
                    "pass": vd_pass,
                    "exten": room,
                    "ext_context": ext_context,
                    "queryCID": query_cid,
                }
            ).encode("utf-8")
            req = urllib.request.Request(
                self._manager_send_url(),
                data=payload,
                method="POST",
                headers={
                    "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8"
                },
            )
            try:
                with urllib.request.urlopen(req, timeout=12) as resp:
                    body = (resp.read() or b"").decode("utf-8", errors="replace")
                if "Hangup command sent" in body:
                    hung.append("HangupConfDial:%s" % room)
            except urllib.error.URLError as exc:
                _logger.warning("HangupConfDial failed %s: %s", login, exc)

        # Garder PJSIP/86028 dans la conf agent après raccrochage client (session WebRTC).

        conn = self._connect()
        try:
            cur = conn.cursor()
            cur.execute(
                """
                UPDATE vicidial_live_agents
                SET status = 'READY', lead_id = 0, channel = '', callerid = '',
                    uniqueid = '', external_hangup = 0, external_status = '',
                    external_dial = '', external_pause = '', comments = 'REMOTE',
                    last_state_change = NOW(), last_update_time = NOW()
                WHERE user = %s AND (
                    status IN ('INCALL', 'QUEUE', 'DIAL')
                    OR channel != '' OR callerid != '' OR uniqueid != ''
                )
                """,
                (login,),
            )
            updated = cur.rowcount
            if lead_id:
                cur.execute(
                    """
                    UPDATE vicidial_list
                    SET status = 'NA', user = ''
                    WHERE lead_id = %s AND status IN ('INCALL', 'QUEUE', 'ADCD')
                    """,
                    (lead_id,),
                )
            cur.close()
            if lead_id:
                cur2 = conn.cursor(dictionary=True)
                self._release_stuck_manual_lead(cur2, lead_id)
                cur2.close()
            conn.commit()
        finally:
            conn.close()

        self.touch_agent_heartbeat(login)
        cleaned = bool(updated) or bool(hung)
        return {
            "ok": cleaned,
            "hung_channels": hung,
            "lead_id": lead_id or "",
            "message": (
                "Appel raccroché"
                if cleaned
                else "État agent inchangé"
            ),
        }

    def _manual_dial_gmt_offset(self, country):
        return {
            "CA": "-5",
            "QC": "-5",
            "US": "-5",
            "ES": "1",
            "FR": "1",
        }.get((country or "FR").upper(), "0")

    _STUCK_MANUAL_LEAD_STATUSES = frozenset({"INCALL", "QUEUE", "ADCD"})

    def _release_stuck_manual_lead(self, cur, lead_id):
        """Libère un lead manual_dial bloqué (INCALL sans agent actif sur ce lead)."""
        lead_id = int(lead_id or 0)
        if not lead_id:
            return False
        cur.execute(
            "SELECT status FROM vicidial_list WHERE lead_id = %s LIMIT 1",
            (lead_id,),
        )
        row = cur.fetchone()
        status = (row.get("status") or "").upper() if row else ""
        if status not in self._STUCK_MANUAL_LEAD_STATUSES:
            return False
        cur.execute(
            """
            SELECT user FROM vicidial_live_agents
            WHERE lead_id = %s AND status IN ('INCALL', 'QUEUE')
            LIMIT 1
            """,
            (lead_id,),
        )
        if cur.fetchone():
            return False
        cur.execute(
            """
            UPDATE vicidial_list
            SET status = 'NEW', called_since_last_reset = 'N', user = ''
            WHERE lead_id = %s
            """,
            (lead_id,),
        )
        return cur.rowcount > 0

    def _parse_manual_dial_body(self, body, vicidial_user, expected_phone=None):
        """Interprète manDiaLnextCaLL : détecte lead INCALL fantôme (pas de bridge)."""
        err = self._vdc_db_query_error(body)
        if err:
            return err
        lines = [ln.strip() for ln in (body or "").split("\n") if ln.strip()]
        lead_id = ""
        dialed_phone = ""
        if len(lines) >= 8:
            lead_id = lines[1]
            dialed_phone = lines[6]
        exp_digits = re.sub(r"\D", "", str(expected_phone or ""))
        dial_digits = re.sub(r"\D", "", str(dialed_phone or ""))
        if len(dial_digits) < 8 and len(exp_digits) >= 8:
            dialed_phone = exp_digits
        if len(lines) >= 3 and (lines[2] or "").upper() == "INCALL":
            released = False
            if lead_id and self.is_available():
                conn = self._connect()
                try:
                    cur = conn.cursor(dictionary=True)
                    released = self._release_stuck_manual_lead(cur, lead_id)
                    if released:
                        conn.commit()
                    cur.close()
                finally:
                    conn.close()
            msg = _(
                "Le contact était bloqué en appel (lead INCALL) — "
                "réessayez dans quelques secondes."
            )
            if released:
                msg = _(
                    "Contact débloqué automatiquement — relancez l'appel."
                )
            return {
                "ok": False,
                "message": msg,
                "reason": "stuck_lead_incall",
                "lead_id": lead_id,
            }
        return {
            "ok": True,
            "lead_id": lead_id,
            "phone_number": dialed_phone,
            "body_preview": (body or "")[:160],
        }

    def ensure_manual_dial_lead(self, phone_number, phone_code, list_id, country="CA"):
        """Pré-crée le lead avant manDiaLnextCaLL (évite gmt_offset vide côté PHP QC/CA)."""
        phone_number = re.sub(r"\D", "", str(phone_number or ""))
        phone_code = re.sub(r"\D", "", str(phone_code or "1"))
        list_id = re.sub(r"\D", "", str(list_id or ""))
        if len(phone_number) < 8 or not list_id or not self.is_available():
            return None
        gmt_offset = self._manual_dial_gmt_offset(country)
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        conn = self._connect()
        try:
            cur = conn.cursor(dictionary=True)
            cur.execute(
                """
                SELECT lead_id, status FROM vicidial_list
                WHERE phone_number = %s AND list_id = %s
                LIMIT 1
                """,
                (phone_number, list_id),
            )
            row = cur.fetchone()
            if row:
                lead_id = int(row.get("lead_id") or 0)
                if self._release_stuck_manual_lead(cur, lead_id):
                    conn.commit()
                cur.close()
                return lead_id
            cur.execute(
                """
                INSERT INTO vicidial_list (
                    phone_code, phone_number, list_id, status,
                    called_since_last_reset, entry_date, modify_date,
                    gmt_offset_now, user, source_id
                ) VALUES (%s, %s, %s, 'NEW', 'N', %s, %s, %s, 'odoo', 'MANUAL_DIAL')
                """,
                (phone_code, phone_number, list_id, now, now, gmt_offset),
            )
            lead_id = cur.lastrowid
            conn.commit()
            cur.close()
            return lead_id
        finally:
            conn.close()

    def get_outbound_cid_aliases(self, campaign_vicidial_id=None):
        """Alias CID sortants actifs (groups_alias) pour le sélecteur poste d'appels."""
        if not self.is_available():
            return []
        vicidial_cid = (campaign_vicidial_id or "").strip().upper()
        if vicidial_cid == "DW_FRB2B":
            allowed = ("TWILIO_FR_CLI", "DOOR_FR_CLI")
            labels = {
                "TWILIO_FR_CLI": "France Twilio",
                "DOOR_FR_CLI": "France Africa-Con",
            }
        elif vicidial_cid == "DW_FRAC":
            allowed = ("DOOR_FR_CLI",)
            labels = {
                "DOOR_FR_CLI": "France Africa-Con",
            }
        else:
            allowed = ("DOOR_FR_CLI", "DOOR_QC_CLI")
            labels = {
                "DOOR_QC_CLI": "Québec",
                "DOOR_FR_CLI": "France",
            }
        placeholders = ",".join(["%s"] * len(allowed))
        conn = self._connect()
        try:
            cur = conn.cursor(dictionary=True)
            cur.execute(
                f"""
                SELECT group_alias_id, group_alias_name, caller_id_number
                FROM groups_alias
                WHERE active = 'Y'
                  AND group_alias_id IN ({placeholders})
                ORDER BY FIELD(group_alias_id, {placeholders})
                """,
                (*allowed, *allowed),
            )
            rows = cur.fetchall()
            cur.close()
            return [
                {
                    "id": row.get("group_alias_id") or "",
                    "label": labels.get(
                        row.get("group_alias_id") or "",
                        row.get("group_alias_name") or row.get("group_alias_id") or "",
                    ),
                    "caller_id_number": row.get("caller_id_number") or "",
                }
                for row in rows
                if row.get("group_alias_id")
            ]
        finally:
            conn.close()

    def _manual_dial_group_alias_fields(self, group_alias_id):
        """Champs VICIdial manDiaLnextCaLL pour alias de groupe (Caller ID sortant)."""
        alias_id = (group_alias_id or "").strip()[:30]
        if not alias_id or not self.is_available():
            return {}
        conn = self._connect()
        try:
            cur = conn.cursor(dictionary=True)
            cur.execute(
                """
                SELECT group_alias_id, caller_id_number
                FROM groups_alias
                WHERE group_alias_id = %s AND active = 'Y'
                LIMIT 1
                """,
                (alias_id,),
            )
            row = cur.fetchone()
            cur.close()
            if not row:
                return {}
            return {
                "account": row.get("group_alias_id") or alias_id,
                "usegroupalias": "1",
                "campaign_cid": row.get("caller_id_number") or "",
            }
        finally:
            conn.close()

    def dial_manual_next_call(
        self,
        vicidial_user,
        session_name,
        campaign_id,
        conf_exten,
        group_alias_id=None,
    ):
        """Appel manuel : prochain lead du hopper (équivalent bouton Dial Next VICIdial)."""
        import urllib.error
        import urllib.parse
        import urllib.request

        login = (vicidial_user or "").strip()[:20]
        session_name = self.resolve_vicidial_session_name(vicidial_user, session_name)
        cid = (campaign_id or "")[:8]
        conf_exten = (conf_exten or "").strip()
        if not login or not session_name or not cid or not conf_exten:
            return {"ok": False, "message": "Session VICIdial incomplète (rechargez la page)."}
        if not self.is_available():
            return {"ok": False, "message": "VICIdial indisponible"}

        server_ip = self._server_ip()
        conn = self._connect()
        try:
            cur = conn.cursor(dictionary=True)
            cur.execute(
                "SELECT pass FROM vicidial_users WHERE user = %s LIMIT 1",
                (login,),
            )
            user_row = cur.fetchone()
            cur.execute(
                """
                SELECT dial_prefix, campaign_cid, manual_dial_timeout, dial_method,
                       use_internal_dnc, use_campaign_dnc, omit_phone_code,
                       manual_dial_filter
                FROM vicidial_campaigns
                WHERE campaign_id = %s
                LIMIT 1
                """,
                (cid,),
            )
            camp = cur.fetchone()
            cur.execute(
                "SELECT ext_context FROM servers WHERE server_ip = %s LIMIT 1",
                (server_ip,),
            )
            srv = cur.fetchone()
            cur.execute(
                """
                SELECT status FROM vicidial_live_agents
                WHERE user = %s
                LIMIT 1
                """,
                (login,),
            )
            live = cur.fetchone()
            cur.execute(
                """
                SELECT agent_log_id FROM vicidial_agent_log
                WHERE user = %s
                ORDER BY agent_log_id DESC
                LIMIT 1
                """,
                (login,),
            )
            log_row = cur.fetchone()
            agent_log_id = int(log_row.get("agent_log_id") or 0) if log_row else 0
            if not agent_log_id:
                agent_log_id = self._create_vicidial_agent_log(
                    cur,
                    login,
                    server_ip,
                    cid,
                    "AGENTS",
                )
                conn.commit()
            cur.close()
            if not user_row:
                return {"ok": False, "message": "Agent VICIdial introuvable"}
            if not camp:
                return {"ok": False, "message": "Campagne VICIdial introuvable"}
            if not live:
                return {"ok": False, "message": "Agent non connecté à VICIdial"}
            if (live.get("status") or "").upper() == "INCALL":
                return {"ok": False, "message": "Vous êtes déjà en appel"}
        finally:
            conn.close()

        join = self.ensure_webphone_in_conference(login, conf_exten)
        if not join.get("ok"):
            return {
                "ok": False,
                "message": _(
                    "Micro WebRTC hors conférence agent — attendez « Connecté » "
                    "puis réessayez (ou rafraîchissez la page)."
                ),
            }

        ext_context = (srv or {}).get("ext_context") or "default"
        payload_fields = {
            "server_ip": server_ip,
            "session_name": session_name,
            "ACTION": "manDiaLnextCaLL",
            "conf_exten": conf_exten,
            "user": login,
            "pass": user_row.get("pass") or "",
            "campaign": cid,
            "ext_context": ext_context,
            "dial_timeout": str(camp.get("manual_dial_timeout") or 30),
            "dial_prefix": camp.get("dial_prefix") or "",
            "campaign_cid": camp.get("campaign_cid") or "",
            "preview": "NO",
            "agent_log_id": str(agent_log_id),
            "callback_id": "",
            "lead_id": "",
            "phone_code": "",
            "phone_number": "",
            "list_id": "",
            "stage": "",
            "use_internal_dnc": camp.get("use_internal_dnc") or "N",
            "use_campaign_dnc": camp.get("use_campaign_dnc") or "N",
            "omit_phone_code": camp.get("omit_phone_code") or "N",
            "manual_dial_filter": camp.get("manual_dial_filter") or "NONE",
            "dial_method": camp.get("dial_method") or "MANUAL",
            "nocall_dial_flag": "",
            "cid_lock": "0",
        }
        payload_fields.update(self._manual_dial_group_alias_fields(group_alias_id))
        payload = urllib.parse.urlencode(payload_fields).encode("utf-8")
        req = urllib.request.Request(
            self._vdc_db_query_url(),
            data=payload,
            method="POST",
            headers={
                "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8"
            },
        )
        try:
            with urllib.request.urlopen(req, timeout=20) as resp:
                body = (resp.read() or b"").decode("utf-8", errors="replace")
        except urllib.error.URLError as exc:
            _logger.warning("dial_manual_next_call failed %s: %s", login, exc)
            return {"ok": False, "message": str(exc)}

        parsed = self._parse_manual_dial_body(body, login, "")
        if not parsed.get("ok"):
            return parsed
        parsed["session_name"] = session_name
        return parsed

    def normalize_workstation_phone(self, raw_phone, country="FR"):
        """Normalise un numéro saisi (FR/CA/ES) pour composition manuelle."""
        from odoo.addons.doorway_vicidial_campaigns.services.file_importer import (
            is_valid_phone,
        )

        valid, norm = is_valid_phone(raw_phone, country)
        if not valid:
            return None, None
        phone_code = {"ES": "34", "CA": "1", "QC": "1", "US": "1"}.get(
            (country or "FR").upper(), "33"
        )
        return norm, phone_code

    @staticmethod
    def _vicidial_dial_phone_number(phone_number, phone_code, country, omit_phone_code):
        """Chaîne réellement composée par VICIdial (omit_phone_code=Y n'ajoute pas phone_code)."""
        dial = re.sub(r"\D", "", str(phone_number or ""))
        code = re.sub(r"\D", "", str(phone_code or ""))
        country = (country or "FR").upper()
        if (omit_phone_code or "N").upper() != "Y":
            return dial
        if country in ("FR",) and code == "33":
            if dial.startswith("33") and len(dial) >= 11:
                return dial
            if len(dial) == 10 and dial.startswith("0"):
                return "33" + dial[1:]
            if len(dial) == 9:
                return "33" + dial
        if country in ("ES", "ESP", "SPAIN") and code == "34":
            if dial.startswith("34") and len(dial) >= 11:
                return dial
            if len(dial) == 9:
                return "34" + dial
        return dial

    def normalize_manual_dial_phone(self, raw_phone, campaign_country="FR"):
        """Normalise un numéro pour composition MANUELLE en auto-détectant le pays.

        Le pays est déduit des chiffres saisis ; le pays de la campagne ne sert
        que de repli pour lever l'ambiguïté FR/ES (tous deux à 9 chiffres) :
        - 11 chiffres commençant par 1, ou 10 chiffres NANP -> CA (phone_code 1)
        - 11+ chiffres commençant par 33 -> FR (phone_code 33)
        - 9 chiffres -> ambigu FR/ES -> on suit le pays campagne (33 / 34)
        - sinon -> dernier essai avec le pays campagne, puis invalide.
        """
        from odoo.addons.doorway_vicidial_campaigns.services.file_importer import (
            is_valid_phone,
        )

        digits = re.sub(r"\D", "", str(raw_phone or ""))
        if not digits:
            return None, None
        if digits in MANUAL_DIAL_INTERNAL_EXTENSIONS:
            return digits, "1"
        campaign_country = (campaign_country or "FR").upper()

        # E.164 France (+33…) — avant le test NANP 10 chiffres
        if digits.startswith("33") and len(digits) >= 11:
            valid, norm = is_valid_phone(raw_phone, "FR")
            if valid:
                return norm, "33"

        # 11 chiffres commençant par 1, ou 10 chiffres NANP (2-9…) -> Canada
        if (len(digits) == 11 and digits.startswith("1")) or (
            len(digits) == 10 and digits[0] in "23456789"
        ):
            valid, norm = is_valid_phone(raw_phone, "CA")
            if valid:
                return norm, "1"

        # 10 chiffres commençant par 0 -> national FR/ES (0478…, pas NANP)
        if len(digits) == 10 and digits.startswith("0"):
            fallback = "ES" if campaign_country in ("ES", "ESP", "SPAIN") else "FR"
            valid, norm = is_valid_phone(raw_phone, fallback)
            if valid:
                return norm, ("34" if fallback == "ES" else "33")

        # 9 chiffres -> ambigu FR/ES : on s'appuie sur le pays de la campagne
        if len(digits) == 9:
            fallback = "ES" if campaign_country in ("ES", "ESP", "SPAIN") else "FR"
            valid, norm = is_valid_phone(raw_phone, fallback)
            if valid:
                return norm, ("34" if fallback == "ES" else "33")

        # Dernier recours : tenter directement le pays de la campagne
        valid, norm = is_valid_phone(raw_phone, campaign_country)
        if valid:
            phone_code = {
                "ES": "34", "ESP": "34", "SPAIN": "34",
                "CA": "1", "QC": "1", "US": "1",
            }.get(campaign_country, "33")
            return norm, phone_code

        return None, None

    def get_campaign_manual_dial_list_id(self, campaign_id):
        """Liste VICIdial pour insertion lead en composition manuelle."""
        cid = (campaign_id or "")[:8]
        if not cid or not self.is_available():
            return ""
        conn = self._connect()
        try:
            cur = conn.cursor(dictionary=True)
            cur.execute(
                """
                SELECT manual_dial_list_id
                FROM vicidial_campaigns
                WHERE campaign_id = %s
                LIMIT 1
                """,
                (cid,),
            )
            row = cur.fetchone()
            manual_list = str(row.get("manual_dial_list_id") or "").strip()
            if manual_list and manual_list not in ("0", "NONE"):
                cur.close()
                return manual_list
            cur.execute(
                """
                SELECT list_id FROM vicidial_lists
                WHERE campaign_id = %s AND active = 'Y'
                ORDER BY list_id ASC
                LIMIT 1
                """,
                (cid,),
            )
            list_row = cur.fetchone()
            cur.close()
            return str(list_row.get("list_id") or "") if list_row else ""
        finally:
            conn.close()

    def dial_manual_number(
        self,
        vicidial_user,
        session_name,
        campaign_id,
        conf_exten,
        phone_number,
        phone_code="",
        list_id="",
        country="CA",
        group_alias_id=None,
    ):
        """Composition manuelle d'un numéro saisi (vdc_db_query manDiaLnextCaLL)."""
        import urllib.error
        import urllib.parse
        import urllib.request

        login = (vicidial_user or "").strip()[:20]
        session_name = self.resolve_vicidial_session_name(vicidial_user, session_name)
        cid = (campaign_id or "")[:8]
        conf_exten = (conf_exten or "").strip()
        phone_number = re.sub(r"\D", "", str(phone_number or ""))
        phone_code = re.sub(r"\D", "", str(phone_code or ""))
        list_id = re.sub(r"\D", "", str(list_id or ""))
        if not login or not session_name or not cid or not conf_exten:
            return {"ok": False, "message": "Session VICIdial incomplète (rechargez la page)."}
        if (
            phone_number not in MANUAL_DIAL_INTERNAL_EXTENSIONS
            and len(phone_number) < 8
        ):
            return {"ok": False, "message": "Numéro trop court."}
        if not self.is_available():
            return {"ok": False, "message": "VICIdial indisponible"}
        if phone_number in MANUAL_DIAL_INTERNAL_EXTENSIONS:
            list_id = list_id or "1005"
        elif not list_id:
            list_id = self.get_campaign_manual_dial_list_id(cid)
        manual_lead_id = self.ensure_manual_dial_lead(
            phone_number, phone_code, list_id, country=country
        )

        server_ip = self._server_ip()
        conn = self._connect()
        try:
            cur = conn.cursor(dictionary=True)
            cur.execute(
                "SELECT pass FROM vicidial_users WHERE user = %s LIMIT 1",
                (login,),
            )
            user_row = cur.fetchone()
            cur.execute(
                """
                SELECT dial_prefix, campaign_cid, manual_dial_timeout, dial_method,
                       use_internal_dnc, use_campaign_dnc, omit_phone_code,
                       manual_dial_filter
                FROM vicidial_campaigns
                WHERE campaign_id = %s
                LIMIT 1
                """,
                (cid,),
            )
            camp = cur.fetchone()
            cur.execute(
                "SELECT ext_context FROM servers WHERE server_ip = %s LIMIT 1",
                (server_ip,),
            )
            srv = cur.fetchone()
            cur.execute(
                """
                SELECT status FROM vicidial_live_agents
                WHERE user = %s
                LIMIT 1
                """,
                (login,),
            )
            live = cur.fetchone()
            cur.execute(
                """
                SELECT agent_log_id FROM vicidial_agent_log
                WHERE user = %s
                ORDER BY agent_log_id DESC
                LIMIT 1
                """,
                (login,),
            )
            log_row = cur.fetchone()
            agent_log_id = int(log_row.get("agent_log_id") or 0) if log_row else 0
            if not agent_log_id:
                agent_log_id = self._create_vicidial_agent_log(
                    cur,
                    login,
                    server_ip,
                    cid,
                    "AGENTS",
                )
                conn.commit()
            cur.close()
            if not user_row:
                return {"ok": False, "message": "Agent VICIdial introuvable"}
            if not camp:
                return {"ok": False, "message": "Campagne VICIdial introuvable"}
            if not live:
                return {"ok": False, "message": "Agent non connecté à VICIdial"}
            if (live.get("status") or "").upper() == "INCALL":
                return {"ok": False, "message": "Vous êtes déjà en appel"}
        finally:
            conn.close()

        ext_context = (srv or {}).get("ext_context") or "default"
        omit_phone_code = camp.get("omit_phone_code") or "N"
        dial_phone = self._vicidial_dial_phone_number(
            phone_number, phone_code, country, omit_phone_code
        )
        join = self.ensure_webphone_in_conference(login, conf_exten)
        if not join.get("ok"):
            return {
                "ok": False,
                "message": _(
                    "Micro WebRTC hors conférence agent — attendez « Connecté » "
                    "puis réessayez (ou rafraîchissez la page)."
                ),
            }

        payload_fields = {
            "server_ip": server_ip,
            "session_name": session_name,
            "ACTION": "manDiaLnextCaLL",
            "conf_exten": conf_exten,
            "user": login,
            "pass": user_row.get("pass") or "",
            "campaign": cid,
            "ext_context": ext_context,
            "dial_timeout": str(camp.get("manual_dial_timeout") or 30),
            "dial_prefix": camp.get("dial_prefix") or "",
            "campaign_cid": camp.get("campaign_cid") or "",
            "preview": "NO",
            "agent_log_id": str(agent_log_id),
            "callback_id": "",
            "lead_id": str(manual_lead_id or ""),
            "phone_code": phone_code,
            "phone_number": dial_phone,
            "list_id": list_id,
            "stage": "",
            "use_internal_dnc": camp.get("use_internal_dnc") or "N",
            "use_campaign_dnc": camp.get("use_campaign_dnc") or "N",
            "omit_phone_code": omit_phone_code,
            "manual_dial_filter": camp.get("manual_dial_filter") or "NONE",
            "dial_method": camp.get("dial_method") or "MANUAL",
            "nocall_dial_flag": "",
            "cid_lock": "0",
        }
        payload_fields.update(self._manual_dial_group_alias_fields(group_alias_id))
        payload = urllib.parse.urlencode(payload_fields).encode("utf-8")
        req = urllib.request.Request(
            self._vdc_db_query_url(),
            data=payload,
            method="POST",
            headers={
                "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8"
            },
        )
        try:
            with urllib.request.urlopen(req, timeout=20) as resp:
                body = (resp.read() or b"").decode("utf-8", errors="replace")
        except urllib.error.URLError as exc:
            _logger.warning("dial_manual_number failed %s: %s", login, exc)
            return {"ok": False, "message": str(exc)}

        parsed = self._parse_manual_dial_body(body, login, dial_phone)
        if not parsed.get("ok"):
            return parsed
        parsed["session_name"] = session_name
        if not parsed.get("phone_number"):
            parsed["phone_number"] = phone_number
        return parsed

    def touch_agent_heartbeat(self, vicidial_user):
        """Rafraîchit last_update_time (secours si conf_exten_check indisponible)."""
        login = (vicidial_user or "").strip()[:20]
        if not login or not self.is_available():
            return False
        conn = self._connect()
        try:
            cur = conn.cursor()
            cur.execute(
                """
                UPDATE vicidial_live_agents
                SET last_update_time = NOW()
                WHERE user = %s
                  AND status IN ('READY', 'INCALL', 'QUEUE', 'CLOSER', 'MQUEUE')
                """,
                (login,),
            )
            updated = cur.rowcount
            cur.execute(
                """
                INSERT INTO vicidial_live_agents_details
                    (user, latency, web_ip, update_date)
                VALUES (%s, '0', 'odoo', NOW())
                ON DUPLICATE KEY UPDATE update_date = NOW(), web_ip = 'odoo'
                """,
                (login,),
            )
            conn.commit()
            cur.close()
            return updated > 0
        finally:
            conn.close()

    def get_agent_pause_alert(self, vicidial_user, odoo_session_active=False):
        """Détecte une pause automatique système (LAGGED / timeout inactivité)."""
        login = (vicidial_user or "").strip()[:20]
        if not login or not self.is_available():
            return {"active": False}
        conn = self._connect()
        try:
            cur = conn.cursor(dictionary=True)
            cur.execute(
                """
                SELECT status, pause_code, random_id, last_state_change,
                       campaign_id, last_update_time
                FROM vicidial_live_agents
                WHERE user = %s
                LIMIT 1
                """,
                (login,),
            )
            live = cur.fetchone()
            if not live or (live.get("status") or "") != "PAUSED":
                return {"active": False}

            cur.execute(
                """
                SELECT sub_status, pause_type, event_time
                FROM vicidial_agent_log
                WHERE user = %s
                ORDER BY event_time DESC
                LIMIT 1
                """,
                (login,),
            )
            last_log = cur.fetchone() or {}
            cur.close()

            pause_code = (live.get("pause_code") or "").strip()
            sub_status = (last_log.get("sub_status") or "").strip()
            pause_type = (last_log.get("pause_type") or "").strip()
            random_id = int(live.get("random_id") or 0)
            manual_codes = {"BREAK", "LUNCH", "MEET", "TRAIN", "PRECAL"}

            is_auto = (
                random_id == 10
                or sub_status == "LAGGED"
                or (pause_type == "SYSTEM" and pause_code not in manual_codes)
                or (odoo_session_active and not pause_code)
            )
            if not is_auto:
                return {"active": False}

            paused_seconds = 0
            last_change = live.get("last_state_change")
            if last_change:
                from datetime import datetime

                if hasattr(last_change, "timestamp"):
                    paused_seconds = max(
                        int(datetime.now().timestamp() - last_change.timestamp()), 0
                    )

            reason = "LAGGED"
            if pause_code in ("WAIT", "AUTO", "KICK", "EMPLY"):
                reason = pause_code
            elif sub_status == "LAGGED" or random_id == 10:
                reason = "LAGGED"

            reason_labels = {
                "LAGGED": "déconnexion détectée (heartbeat manquant)",
                "KICK": "déconnexion détectée",
                "WAIT": "timeout inactivité",
                "AUTO": "pause automatique système",
                "EMPLY": "file vide",
            }
            label = reason_labels.get(reason, "pause automatique système")
            return {
                "active": True,
                "reason": reason,
                "pause_code": pause_code or reason,
                "pause_type": pause_type or "SYSTEM",
                "paused_seconds": paused_seconds,
                "campaign_id": live.get("campaign_id") or "",
                "message": "Agent mis en pause : %s." % label,
            }
        finally:
            conn.close()

    def sync_agent_ready_for_session(
        self, vicidial_user, campaign_id, session_name=None
    ):
        """Maintient l'agent READY tant que la session Odoo est active."""
        cid = (campaign_id or "")[:8]
        session_name = self.resolve_vicidial_session_name(vicidial_user, session_name)
        live = self.get_agent_live_status(vicidial_user)
        if (
            live.get("status") == "READY"
            and live.get("campaign_id") == cid
            and live.get("logged_in")
        ):
            if session_name and live.get("conf_exten"):
                self.send_conf_exten_heartbeat(
                    vicidial_user,
                    session_name,
                    cid,
                    live.get("conf_exten"),
                )
            # Toujours rafraichir last_update_time via NOW() (= heure locale OS
            # depuis le fix fuseau). Le heartbeat PHP conf_exten_check peut écrire
            # en UTC selon le fuseau de sa connexion MySQL ; on garantit ici que
            # le dernier write est en heure locale, sinon AST_VDauto_dial voit
            # l'agent "en retard" et le repasse en PAUSE (random_id=10).
            self.touch_agent_heartbeat(vicidial_user)
            live["session_name"] = session_name
            return live

        pause_alert = {}
        if live.get("logged_in") and live.get("status") == "PAUSED":
            pause_alert = self.get_agent_pause_alert(
                vicidial_user, odoo_session_active=True
            )

        result = self.activate_agent_ready(vicidial_user, campaign_id)
        if pause_alert.get("active"):
            result["pause_alert"] = pause_alert
            result["auto_pause_recovered"] = bool(result.get("ok"))
        return result


    def _vicidial_phone_login(self, vicidial_user):
        """Extension webphone (86029) liée au login VICIdial (martin)."""
        login = (vicidial_user or "").strip()[:20]
        if not login or not self.is_available():
            return ""
        conn = self._connect()
        try:
            cur = conn.cursor()
            cur.execute(
                "SELECT phone_login FROM vicidial_users WHERE user = %s LIMIT 1",
                (login,),
            )
            row = cur.fetchone()
            cur.close()
            return (row[0] if row else "") or ""
        finally:
            conn.close()

    def _vicidial_live_user_keys(self, vicidial_user):
        """Clés possibles dans vicidial_live_agents (login ou poste numérique)."""
        login = (vicidial_user or "").strip()[:20]
        keys = []
        if login:
            keys.append(login)
        phone = self._vicidial_phone_login(login)
        if phone and phone not in keys:
            keys.append(phone)
        return keys

    def get_agent_live_status(self, vicidial_user):
        login = (vicidial_user or "").strip()[:20]
        if not login or not self.is_available():
            return {}
        conn = self._connect()
        try:
            cur = conn.cursor(dictionary=True)
            keys = self._vicidial_live_user_keys(login)
            placeholders = ",".join(["%s"] * len(keys))
            query = (
                """
                SELECT user, campaign_id, status, conf_exten, extension, calls_today,
                       pause_code, random_id, last_state_change, last_update_time
                FROM vicidial_live_agents
                WHERE user IN ({in_clause})
                ORDER BY CASE WHEN user = %s THEN 0 ELSE 1 END, last_update_time DESC
                LIMIT 1
                """
            ).format(in_clause=placeholders)
            cur.execute(query, tuple(keys) + (login,))
            row = cur.fetchone()
            cur.close()
            if not row:
                return {"logged_in": False, "status": "", "campaign_id": ""}

            def _dt_str(value):
                if not value:
                    return False
                if hasattr(value, "isoformat"):
                    return value.isoformat(sep=" ", timespec="seconds")
                return str(value)

            return {
                "logged_in": True,
                "status": row.get("status") or "",
                "campaign_id": row.get("campaign_id") or "",
                "ready": (row.get("status") or "") == "READY",
                "conf_exten": row.get("conf_exten") or "",
                "pause_code": row.get("pause_code") or "",
                "random_id": int(row.get("random_id") or 0),
                "last_state_change": _dt_str(row.get("last_state_change")),
                "last_update_time": _dt_str(row.get("last_update_time")),
            }
        finally:
            conn.close()

    def dial_agent_mobile_to_conference(
        self, vicidial_user, conf_exten, callback_phone, campaign_id=None
    ):
        """Appelle le cellulaire de l'agent via Door_App0 et le place en conférence VICIdial."""
        import random
        import re
        from datetime import datetime

        login = (vicidial_user or "").strip()[:20]
        room = (conf_exten or "").strip()
        digits = re.sub(r"\D", "", callback_phone or "")
        if len(digits) == 10:
            dial_number = "1%s" % digits
        elif len(digits) == 11 and digits.startswith("1"):
            dial_number = digits
        else:
            return {"ok": False, "message": "Numéro mobile invalide (10 chiffres requis)"}
        if not login or not room or not self.is_available():
            return {"ok": False, "message": "Session agent invalide"}

        self.ensure_africa_con_door_trunk()
        server_ip = self._server_ip()
        outbound_cid = self.env["ir.config_parameter"].sudo().get_param(
            "doorway_vicidial_campaigns.door_app0_caller_id", "15817058118"
        )
        cid = (campaign_id or "")[:8]
        conn = self._connect()
        try:
            cur = conn.cursor()
            if cid:
                cur.execute(
                    "SELECT campaign_cid FROM vicidial_campaigns WHERE campaign_id = %s LIMIT 1",
                    (cid,),
                )
                row = cur.fetchone()
                if row and row[0]:
                    outbound_cid = re.sub(r"\D", "", str(row[0])) or outbound_cid

            now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            query_cid = "DOORCALL%09d" % random.randint(1, 999999999)
            trunk = "zakarifr" if cid.startswith("DW_FR") else "ZakariSIP"
            channel = "SIP/%s/%s" % (trunk, dial_number)
            callerid = 'Callerid: "%s" <%s>' % (query_cid, outbound_cid)
            cur.execute(
                """
                INSERT INTO vicidial_manager SET
                    entry_date = %s, status = 'NEW', response = 'N',
                    server_ip = %s, action = 'Originate', callerid = %s,
                    cmd_line_b = %s, cmd_line_c = %s, cmd_line_d = %s,
                    cmd_line_e = 'Priority: 1', cmd_line_f = %s
                """,
                (
                    now,
                    server_ip,
                    query_cid,
                    "Exten: %s" % room,
                    "Context: default",
                    "Channel: %s" % channel,
                    callerid,
                ),
            )
            conn.commit()
            cur.close()
            masked = "***-***-%s" % digits[-4:]
            return {
                "ok": True,
                "conf_exten": room,
                "phone_masked": masked,
                "channel": channel,
            }
        except Exception as exc:  # noqa: BLE001
            _logger.exception("dial_agent_mobile_to_conference %s", login)
            return {"ok": False, "message": str(exc)}
        finally:
            conn.close()

    def activate_agent_ready(self, vicidial_user, campaign_id, mobile_callback=False):
        """Connecte l'agent dans vicidial_live_agents en statut READY."""
        import random

        login = (vicidial_user or "").strip()[:20]
        cid = (campaign_id or "")[:8]
        if not login or not cid or not self.is_available():
            return {"ok": False, "message": "Paramètres agent/campagne invalides"}

        server_ip = self._server_ip()
        now = self._os_local_now()
        conn = self._connect()
        try:
            cur = conn.cursor(dictionary=True)
            self._ensure_conference_rooms(cur, server_ip)

            cur.execute(
                """
                SELECT user, phone_login, phone_pass, user_level, user_group
                FROM vicidial_users
                WHERE user = %s AND active = 'Y'
                LIMIT 1
                """,
                (login,),
            )
            vu = cur.fetchone()
            if not vu:
                return {"ok": False, "message": "Agent VICIdial introuvable"}

            phone = {"is_webphone": "N", "protocol": "SIP", "extension": "86019"}
            sip_user = "SIP/86019"
            if mobile_callback:
                phone_login = (vu.get("phone_login") or "").strip() or "86019"
            else:
                phone_login = (vu.get("phone_login") or "").strip()
                if not phone_login:
                    self.ensure_agent_webphone(login)
                    cur.execute(
                        "SELECT phone_login FROM vicidial_users WHERE user = %s",
                        (login,),
                    )
                    refreshed = cur.fetchone()
                    phone_login = (refreshed[0] if refreshed else "") or ""

                cur.execute(
                    """
                    SELECT extension, protocol, is_webphone
                    FROM phones
                    WHERE (login = %s OR extension = %s) AND active = 'Y'
                    LIMIT 1
                    """,
                    (phone_login, phone_login),
                )
                phone_row = cur.fetchone()
                if not phone_row:
                    return {"ok": False, "message": "Webphone agent non configuré"}
                phone = phone_row
                protocol = phone.get("protocol") or "SIP"
                extension = phone.get("extension") or phone_login
                sip_user = "%s/%s" % (protocol, extension)

            # Épingle la salle déjà attribuée à l'agent : évite la dérive de
            # salle (webphone qui décroche -> ça ne sonne pas) et la fuite de
            # salles à chaque passage READY. On réutilise la salle courante.
            cur.execute(
                "SELECT conf_exten FROM vicidial_live_agents WHERE user = %s LIMIT 1",
                (login,),
            )
            _sticky = cur.fetchone()
            sticky_room = str((_sticky or {}).get("conf_exten") or "").strip()

            # Épingle aussi le session_name VICIdial : sinon chaque passage READY
            # genere un nouveau nom -> le contrôleur réécrit la session Odoo a
            # chaque heartbeat -> collisions "could not serialize access due to
            # concurrent update" -> heartbeats en échec -> "heartbeat manquant".
            cur.execute(
                "SELECT session_name FROM vicidial_session_data WHERE user = %s AND server_ip = %s LIMIT 1",
                (login, server_ip),
            )
            _sname = cur.fetchone()
            sticky_session_name = str((_sname or {}).get("session_name") or "").strip()

            self._release_agent_conference(cur, login, server_ip)
            cur.execute("DELETE FROM vicidial_live_agents WHERE user = %s", (login,))
            cur.execute("DELETE FROM vicidial_session_data WHERE user = %s", (login,))

            conf_table = self._conf_table()
            conf = None
            preferred = self._preferred_conf_exten(login) or sticky_room
            if preferred:
                cur.execute(
                    """
                    SELECT conf_exten FROM %s
                    WHERE server_ip = %%s AND conf_exten = %%s
                      AND (extension = '' OR extension IS NULL)
                    LIMIT 1
                    """
                    % conf_table,
                    (server_ip, preferred),
                )
                conf = cur.fetchone()
            if not conf:
                cur.execute(
                    """
                    SELECT conf_exten FROM %s
                    WHERE server_ip = %%s AND (extension = '' OR extension IS NULL)
                    ORDER BY conf_exten
                    LIMIT 1
                    """
                    % conf_table,
                    (server_ip,),
                )
                conf = cur.fetchone()
            if not conf:
                return {"ok": False, "message": "Aucune salle de conférence libre"}

            session_id = str(conf["conf_exten"])
            cur.execute(
                """
                UPDATE %s
                SET extension = %%s, leave_3way = '0'
                WHERE conf_exten = %%s AND server_ip = %%s
                """
                % conf_table,
                (sip_user, session_id, server_ip),
            )

            cur.execute(
                """
                SELECT campaign_weight, calls_today, campaign_grade
                FROM vicidial_campaign_agents
                WHERE user = %s AND campaign_id = %s
                LIMIT 1
                """,
                (login, cid),
            )
            ca = cur.fetchone()
            campaign_weight = int((ca or {}).get("campaign_weight") or 0)
            calls_today = int((ca or {}).get("calls_today") or 0)
            campaign_grade = int((ca or {}).get("campaign_grade") or 1)
            user_level = int(vu.get("user_level") or 1)
            random_id = random.randint(10000000, 99999999)
            on_hook_agent = (
                "Y" if (phone.get("is_webphone") or "") == "Y" else "N"
            )

            cur.execute(
                """
                INSERT INTO vicidial_live_agents (
                    user, server_ip, conf_exten, extension, status, lead_id,
                    campaign_id, uniqueid, callerid, channel, random_id,
                    last_call_time, last_update_time, last_call_finish,
                    closer_campaigns, user_level, campaign_weight, calls_today,
                    last_state_change, outbound_autodial, manager_ingroup_set,
                    on_hook_ring_time, on_hook_agent, last_inbound_call_time,
                    last_inbound_call_finish, campaign_grade, pause_code,
                    last_inbound_call_time_filtered, last_inbound_call_finish_filtered
                ) VALUES (
                    %s, %s, %s, %s, 'READY', 0,
                    %s, '', '', '', %s,
                    %s, NOW(), %s,
                    '', %s, %s, %s,
                    %s, 'Y', 'N',
                    '60', %s, %s,
                    %s, %s, '',
                    %s, %s
                )
                """,
                (
                    login,
                    server_ip,
                    session_id,
                    sip_user,
                    cid,
                    random_id,
                    now,
                    now,
                    user_level,
                    campaign_weight,
                    calls_today,
                    now,
                    on_hook_agent,
                    now,
                    now,
                    campaign_grade,
                    now,
                    now,
                ),
            )
            session_name = self.register_vicidial_web_session(
                cur, login, cid, session_id, sip_user,
                session_name=sticky_session_name or None,
            )
            agent_log_id = self._create_vicidial_agent_log(
                cur,
                login,
                server_ip,
                cid,
                (vu.get("user_group") if isinstance(vu, dict) else None)
                or "AGENTS",
            )
            cur.execute(
                """
                INSERT INTO vicidial_live_agents_details
                    (user, latency, web_ip, update_date)
                VALUES (%s, '0', 'odoo', NOW())
                ON DUPLICATE KEY UPDATE update_date = NOW(), web_ip = 'odoo'
                """,
                (login,),
            )
            conn.commit()
            cur.close()
            return {
                "ok": True,
                "status": "READY",
                "campaign_id": cid,
                "conf_exten": session_id,
                "extension": sip_user,
                "session_name": session_name,
                "agent_log_id": agent_log_id,
                "webphone": (phone.get("is_webphone") or "") == "Y",
                "mobile_callback": bool(mobile_callback),
            }
        except Exception as exc:  # noqa: BLE001
            _logger.exception("activate_agent_ready %s", login)
            return {"ok": False, "message": str(exc)}
        finally:
            conn.close()

    def set_agent_paused(self, vicidial_user):
        login = (vicidial_user or "").strip()[:20]
        if not login or not self.is_available():
            return {"ok": False}
        conn = self._connect()
        try:
            cur = conn.cursor()
            cur.execute(
                """
                UPDATE vicidial_live_agents
                SET status = 'PAUSED', last_state_change = NOW(), last_update_time = NOW()
                WHERE user = %s
                """,
                (login,),
            )
            updated = cur.rowcount
            conn.commit()
            cur.close()
            return {"ok": updated > 0}
        finally:
            conn.close()

    def deactivate_agent(self, vicidial_user):
        login = (vicidial_user or "").strip()[:20]
        if not login or not self.is_available():
            return {"ok": False}
        server_ip = self._server_ip()
        conn = self._connect()
        try:
            cur = conn.cursor()
            self._release_agent_conference(cur, login, server_ip)
            keys = self._vicidial_live_user_keys(login)
            placeholders = ",".join(["%s"] * len(keys))
            cur.execute(
                "DELETE FROM vicidial_live_agents WHERE user IN (%s)" % placeholders,
                tuple(keys),
            )
            cur.execute(
                "DELETE FROM vicidial_live_agents_details WHERE user IN (%s)" % placeholders,
                tuple(keys),
            )
            cur.execute(
                "DELETE FROM vicidial_session_data WHERE user IN (%s)" % placeholders,
                tuple(keys),
            )
            phone = self._vicidial_phone_login(login)
            if phone:
                cur.execute(
                    "DELETE FROM web_client_sessions WHERE extension LIKE %s AND server_ip = %s",
                    ("%%%s%%" % phone, server_ip),
                )
            conn.commit()
            cur.close()
            return {"ok": True}
        finally:
            conn.close()

    def build_agent_console_url(self, vicidial_user, campaign_id):
        """URL vicidial.php pré-remplie (console agent + webphone)."""
        login = (vicidial_user or "").strip()[:20]
        cid = (campaign_id or "")[:8]
        if not login or not cid:
            return ""
        conn = self._connect()
        try:
            cur = conn.cursor()
            cur.execute(
                "SELECT pass, phone_login, phone_pass FROM vicidial_users WHERE user = %s",
                (login,),
            )
            row = cur.fetchone()
            cur.close()
            if not row:
                return ""
            vd_pass, phone_login, phone_pass = row[0], row[1], row[2]
        finally:
            conn.close()

        base = "%s/vicidial.php" % self._agent_portal_base()
        from urllib.parse import urlencode

        params = urlencode(
            {
                "VD_login": login,
                "VD_pass": vd_pass or "",
                "VD_campaign": cid,
                "phone_login": phone_login or "",
                "phone_pass": phone_pass or "",
                "relogin": "YES",
                "hide_relogin_fields": "YES",
            }
        )
        return "%s?%s" % (base, params)

    def build_webphone_embed_url(
        self, vicidial_user, campaign_id=None, conf_exten=None, layout="embed"
    ):
        """URL ViciPhone WebRTC embarquée dans le poste Odoo."""
        import base64

        self.ensure_webrtc_viciphone()
        login = (vicidial_user or "").strip()[:20]
        if not login or not self.is_available():
            return ""
        conn = self._connect()
        try:
            cur = conn.cursor()
            cur.execute(
                "SELECT phone_login, phone_pass FROM vicidial_users WHERE user = %s",
                (login,),
            )
            row = cur.fetchone()
            if not row:
                cur.close()
                return ""
            phone_login, phone_pass = row[0], row[1]
            cur.execute(
                """
                SELECT conf_secret, pass FROM phones
                WHERE active = 'Y'
                  AND (login = %s OR extension = %s)
                LIMIT 1
                """,
                (phone_login, phone_login),
            )
            phone_row = cur.fetchone()
            if phone_row:
                # ViciPhone SIP REGISTER = conf_secret (pas phones.pass = login web)
                phone_pass = (phone_row[0] or phone_pass or phone_row[1] or "")
            cur.close()
        finally:
            conn.close()

        sip_host = self._webrtc_sip_host()
        ws_url = self._get_web_socket_url()
        callerid = ""
        if campaign_id:
            conn = self._connect()
            try:
                cur = conn.cursor()
                cur.execute(
                    "SELECT campaign_cid FROM vicidial_campaigns WHERE campaign_id = %s",
                    ((campaign_id or "")[:8],),
                )
                crow = cur.fetchone()
                cur.close()
                if crow and crow[0]:
                    callerid = str(crow[0])
            finally:
                conn.close()

        css_layout = "css/intellix-standalone.css"
        if layout == "embed":
            css_layout = "css/intellix-embed.css"
        # ViciPhone parse SETTINGS avec explode('\\n') — séparateur littéral \n
        fr_labels = (
            "dialRegExten:1\\n"
            "langInit:Demarrage...\\n"
            "langRegistering:Connexion...\\n"
            "langRegistered:Connecte\\n"
            "langIncall:En ligne\\n"
            "langUnregistered:Non connecte\\n"
            "langDisconnected:Deconnecte\\n"
            "langSend:Appeler"
        )
        option_parts = [
            "WEBSOCKETURL%s" % ws_url,
            "AUTOANSWER_Y",
            "WEBPHONELAYOUT%s" % css_layout,
            "SETTINGS%s" % fr_labels,
        ]
        if conf_exten:
            dial_exten = self._webphone_session_dial_exten(conf_exten)
            if dial_exten:
                option_parts.append("SESSION%s" % dial_exten)
        options = "--".join(option_parts)

        from urllib.parse import urlencode

        b64 = lambda v: base64.b64encode((v or "").encode()).decode()
        base = "%s/ViciPhone/viciphone.php" % self._agent_portal_base()
        params = urlencode(
            {
                "phone_login": b64(phone_login or ""),
                "phone_pass": b64(phone_pass or ""),
                "server_ip": b64(sip_host),
                "callerid": b64(callerid),
                "protocol": b64("PJSIP"),
                "codecs": b64("ulaw,alaw,opus"),
                "options": b64(options),
                "system_key": b64(""),
            }
        )
        return "%s?%s" % (base, params)

    # ── Agents ────────────────────────────────────────────────

    def create_agent_user(self, user_data):
        conn = self._connect()
        try:
            cur = conn.cursor()
            cur.execute(
                """
                INSERT INTO vicidial_users (
                    user, pass, full_name, user_level, user_group, active,
                    phone_login, phone_pass, agentcall_manual
                ) VALUES (%s, %s, %s, %s, %s, 'Y', %s, '1234', '1')
                ON DUPLICATE KEY UPDATE
                    full_name = VALUES(full_name),
                    user_level = VALUES(user_level),
                    user_group = VALUES(user_group),
                    active = VALUES(active),
                    agentcall_manual = '1'
                """,
                (
                    user_data["vicidial_user"][:20],
                    user_data.get("vicidial_pass", "ChangeMe2026"),
                    (user_data.get("name") or user_data["vicidial_user"])[:50],
                    user_data.get("user_level", 1),
                    (user_data.get("user_group") or "AGENTS")[:20],
                    user_data.get("extension", user_data["vicidial_user"])[:20],
                ),
            )
            conn.commit()
            cur.close()
            return user_data["vicidial_user"]
        finally:
            conn.close()

    def sync_user(self, vicidial_user, full_name, user_group, user_level, active):
        return bool(
            self.create_agent_user(
                {
                    "vicidial_user": vicidial_user,
                    "name": full_name,
                    "user_group": user_group,
                    "user_level": user_level,
                    "vicidial_pass": "ChangeMe2026",
                    "extension": vicidial_user,
                }
            )
        )

    def get_agents_status(self, campaign_id):
        cid = (campaign_id or "")[:8]
        conn = self._connect()
        try:
            cur = conn.cursor(dictionary=True)
            cur.execute(
                """
                SELECT vc.user, vc.status, vc.calls_today, vc.campaign_id,
                       vu.full_name
                FROM vicidial_live_agents vc
                JOIN vicidial_users vu ON vc.user = vu.user
                WHERE vc.campaign_id = %s
                """,
                (cid,),
            )
            rows = cur.fetchall()
            cur.close()
            return rows
        finally:
            conn.close()

    def count_live_agents(self, campaign_id=None):
        rows = self.get_agents_status(campaign_id) if campaign_id else []
        if not campaign_id:
            conn = self._connect()
            try:
                cur = conn.cursor()
                cur.execute("SELECT COUNT(*) FROM vicidial_live_agents")
                count = cur.fetchone()[0]
                cur.close()
                return int(count)
            finally:
                conn.close()
        return len(rows)

    # ── Stats live ────────────────────────────────────────────

    def _json_safe_number(self, value, default=0):
        """Convertit Decimal MySQL / float Odoo en nombre JSON-serializable."""
        if value is None:
            return default
        from decimal import Decimal

        if isinstance(value, Decimal):
            return int(value) if value % 1 == 0 else float(value)
        if isinstance(value, float):
            return round(value, 4)
        if isinstance(value, int):
            return value
        try:
            num = float(value)
            return int(num) if num.is_integer() else num
        except (TypeError, ValueError):
            return default

    def _compose_live_stats(self, record, stats_row, amd_by_status, live_agents):
        from decimal import Decimal

        stats = {}
        if stats_row:
            for key, val in stats_row.items():
                if isinstance(val, (int, float, Decimal)):
                    stats[key] = self._json_safe_number(val, default=0)
                else:
                    stats[key] = val
        by = amd_by_status or {}
        stats.update(
            {
                "total_contacts": record.total_contacts,
                "answer_rate": self._json_safe_number(record.answer_rate, default=0.0),
                "state": record.state,
                "total_calls": int(
                    stats.get("calls_today") or record.total_called or 0
                ),
                "answered": record.total_answered,
                "amd_by_status": by,
                "amd_human": by.get("HUMAN", 0),
                "amd_machine": sum(
                    v for k, v in by.items() if k in ("AMD", "AA", "AM")
                ),
                "live_agents": int(live_agents or 0),
            }
        )
        return stats

    def _fetch_campaign_operational_meta(self, ids, use_hostinger=False):
        """Lit active/ADL/remote depuis MySQL PROD ou Hostinger (SSH)."""
        meta = {}
        if not ids:
            return meta
        if use_hostinger:
            in_sql = self._hostinger_ids_sql(ids)
            for row in self._hostinger_query_rows(
                "SELECT campaign_id, active, auto_dial_level FROM vicidial_campaigns "
                "WHERE campaign_id IN (%s)" % in_sql,
                columns=["campaign_id", "active", "auto_dial_level"],
            ):
                cid = row["campaign_id"]
                meta[cid] = {
                    "active": row.get("active") or "N",
                    "auto_dial_level": int(float(row.get("auto_dial_level") or 0)),
                    "remote_lines": 0,
                }
            for row in self._hostinger_query_rows(
                "SELECT campaign_id, SUM(CASE WHEN status='ACTIVE' THEN number_of_lines "
                "ELSE 0 END) AS remote_lines_sum FROM vicidial_remote_agents "
                "WHERE campaign_id IN (%s) GROUP BY campaign_id" % in_sql,
                columns=["campaign_id", "remote_lines_sum"],
            ):
                cid = row["campaign_id"]
                if cid in meta:
                    meta[cid]["remote_lines"] = int(row.get("remote_lines_sum") or 0)
            return meta
        placeholders = ",".join(["%s"] * len(ids))
        conn = self._connect()
        try:
            cur = conn.cursor(dictionary=True)
            cur.execute(
                f"""
                SELECT campaign_id, active, auto_dial_level
                FROM vicidial_campaigns
                WHERE campaign_id IN ({placeholders})
                """,
                ids,
            )
            for row in cur.fetchall():
                cid = row["campaign_id"]
                meta[cid] = {
                    "active": row.get("active") or "N",
                    "auto_dial_level": int(float(row.get("auto_dial_level") or 0)),
                    "remote_lines": 0,
                }
            cur.execute(
                f"""
                SELECT campaign_id,
                       SUM(CASE WHEN status='ACTIVE' THEN number_of_lines ELSE 0 END) AS remote_lines_sum
                FROM vicidial_remote_agents
                WHERE campaign_id IN ({placeholders})
                GROUP BY campaign_id
                """,
                ids,
            )
            for row in cur.fetchall():
                cid = row["campaign_id"]
                if cid in meta:
                    meta[cid]["remote_lines"] = int(row.get("remote_lines_sum") or 0)
            cur.close()
        finally:
            conn.close()
        return meta

    def get_campaign_operational_meta_batch(self, vicidial_ids):
        """État dial VICIdial (active, ADL, remote IA) pour sync Odoo."""
        ids = [(v or "")[:8] for v in vicidial_ids if v]
        ids = list(dict.fromkeys(ids))
        result = {
            cid: {
                "active": "N",
                "auto_dial_level": 0,
                "remote_lines": 0,
            }
            for cid in ids
        }
        if not ids:
            return result
        hostinger_ids = self._hostinger_only_vicidial_ids()
        prod_ids = [i for i in ids if i not in hostinger_ids]
        host_ids = [i for i in ids if i in hostinger_ids]
        try:
            if prod_ids:
                result.update(self._fetch_campaign_operational_meta(prod_ids))
            if host_ids:
                result.update(
                    self._fetch_campaign_operational_meta(
                        host_ids, use_hostinger=True
                    )
                )
        except Exception as exc:  # noqa: BLE001
            _logger.error("get_campaign_operational_meta_batch: %s", exc)
        return result

    def _fetch_live_stats_from_db(self, vicidial_ids, use_hostinger=False):
        stats_rows = {}
        amd_by_cid = {}
        live_by_cid = {}
        in_progress_by_cid = {}
        if not vicidial_ids:
            return stats_rows, amd_by_cid, live_by_cid, in_progress_by_cid
        if use_hostinger:
            in_sql = self._hostinger_ids_sql(vicidial_ids)
            for row in self._hostinger_query_rows(
                "SELECT campaign_id, dialable_leads, calls_today, answers_today, "
                "drops_today, calls_hour, answers_hour FROM vicidial_campaign_stats "
                "WHERE campaign_id IN (%s)" % in_sql,
                columns=[
                    "campaign_id", "dialable_leads", "calls_today", "answers_today",
                    "drops_today", "calls_hour", "answers_hour",
                ],
            ):
                stats_rows[row["campaign_id"]] = row
            for row in self._hostinger_query_rows(
                "SELECT campaign_id, status, COUNT(*) AS count FROM vicidial_log "
                "WHERE campaign_id IN (%s) AND call_date >= CURDATE() "
                "GROUP BY campaign_id, status" % in_sql,
                columns=["campaign_id", "status", "count"],
            ):
                amd_by_cid.setdefault(row["campaign_id"], {})[row["status"]] = int(
                    row["count"]
                )
            for row in self._hostinger_query_rows(
                "SELECT campaign_id, COUNT(*) AS count FROM vicidial_live_agents "
                "WHERE campaign_id IN (%s) GROUP BY campaign_id" % in_sql,
                columns=["campaign_id", "count"],
            ):
                live_by_cid[row["campaign_id"]] = int(row["count"])
            for row in self._hostinger_query_rows(
                "SELECT campaign_id, COUNT(*) AS count FROM vicidial_auto_calls "
                "WHERE campaign_id IN (%s) AND status IN ('SENT','LIVE','RINGING') "
                "GROUP BY campaign_id" % in_sql,
                columns=["campaign_id", "count"],
            ):
                in_progress_by_cid[row["campaign_id"]] = int(row["count"])
            return stats_rows, amd_by_cid, live_by_cid, in_progress_by_cid
        placeholders = ",".join(["%s"] * len(vicidial_ids))
        conn = self._connect()
        try:
            cur = conn.cursor(dictionary=True)
            cur.execute(
                f"""
                SELECT campaign_id, dialable_leads, calls_today, answers_today,
                       drops_today, calls_hour, answers_hour
                FROM vicidial_campaign_stats
                WHERE campaign_id IN ({placeholders})
                """,
                vicidial_ids,
            )
            for row in cur.fetchall():
                stats_rows[row["campaign_id"]] = row

            cur.execute(
                f"""
                SELECT campaign_id, status, COUNT(*) AS count
                FROM vicidial_log
                WHERE campaign_id IN ({placeholders})
                  AND call_date >= CURDATE()
                GROUP BY campaign_id, status
                """,
                vicidial_ids,
            )
            for row in cur.fetchall():
                amd_by_cid.setdefault(row["campaign_id"], {})[
                    row["status"]
                ] = int(row["count"])

            cur.execute(
                f"""
                SELECT campaign_id, COUNT(*) AS count
                FROM vicidial_live_agents
                WHERE campaign_id IN ({placeholders})
                GROUP BY campaign_id
                """,
                vicidial_ids,
            )
            for row in cur.fetchall():
                live_by_cid[row["campaign_id"]] = int(row["count"])

            cur.execute(
                f"""
                SELECT campaign_id, COUNT(*) AS count
                FROM vicidial_auto_calls
                WHERE campaign_id IN ({placeholders})
                  AND status IN ('SENT', 'LIVE', 'RINGING')
                GROUP BY campaign_id
                """,
                vicidial_ids,
            )
            for row in cur.fetchall():
                in_progress_by_cid[row["campaign_id"]] = int(row["count"])
            cur.close()
        finally:
            conn.close()
        return stats_rows, amd_by_cid, live_by_cid, in_progress_by_cid

    def get_live_stats_batch(self, campaigns):
        """Stats live — PROD et Hostinger selon campagne."""
        result = {rec.id: {} for rec in campaigns}
        linked = campaigns.filtered("vicidial_campaign_id")
        if not linked:
            return result

        hostinger_ids = self._hostinger_only_vicidial_ids()
        all_ids = []
        prod_ids = []
        host_ids = []
        for rec in linked:
            cid = (rec.vicidial_campaign_id or "")[:8]
            if not cid or cid in all_ids:
                continue
            all_ids.append(cid)
            if cid in hostinger_ids:
                host_ids.append(cid)
            else:
                prod_ids.append(cid)

        stats_rows = {}
        amd_by_cid = {}
        live_by_cid = {}
        in_progress_by_cid = {}
        try:
            if prod_ids:
                s, a, l, p = self._fetch_live_stats_from_db(prod_ids)
                stats_rows.update(s)
                amd_by_cid.update(a)
                live_by_cid.update(l)
                in_progress_by_cid.update(p)
            if host_ids:
                s, a, l, p = self._fetch_live_stats_from_db(
                    host_ids, use_hostinger=True
                )
                stats_rows.update(s)
                amd_by_cid.update(a)
                live_by_cid.update(l)
                in_progress_by_cid.update(p)
        except Exception as exc:  # noqa: BLE001
            _logger.error("get_live_stats_batch MySQL error: %s", exc)

        for rec in linked:
            cid = (rec.vicidial_campaign_id or "")[:8]
            stats = self._compose_live_stats(
                rec,
                stats_rows.get(cid, {}),
                amd_by_cid.get(cid, {}),
                live_by_cid.get(cid, 0),
            )
            stats["calls_in_progress"] = in_progress_by_cid.get(cid, 0)
            result[rec.id] = stats
        return result

    def get_live_stats(self, campaign):
        """Accepte enregistrement doorway.campaign ou campaign_id str."""
        if hasattr(campaign, "vicidial_campaign_id"):
            cid = (campaign.vicidial_campaign_id or "")[:8]
            record = campaign
        else:
            cid = (campaign or "")[:8]
            record = self.env["doorway.campaign"].search(
                [("vicidial_campaign_id", "=", cid)], limit=1
            )
        if not record:
            return {}
        return self.get_live_stats_batch(record).get(record.id, {})

    def get_call_log(self, campaign_id, limit=100):
        cid = self._sanitize_vicidial_id(campaign_id)
        lim = max(1, min(int(limit or 100), 500))
        if self._is_hostinger_campaign(cid):
            try:
                rows = self._hostinger_query_rows(
                    """
                    SELECT vl.call_date, vl.phone_number, vl.status, vl.user,
                           vl.uniqueid,
                           GREATEST(
                               COALESCE(vl.length_in_sec, 0),
                               COALESCE((
                                   SELECT MAX(cl.length_in_sec)
                                   FROM call_log cl
                                   WHERE cl.uniqueid LIKE CONCAT(
                                       SUBSTRING_INDEX(vl.uniqueid, '.', 1), '.%%'
                                   )
                               ), 0)
                           ) AS length_in_sec
                    FROM vicidial_log vl
                    WHERE vl.campaign_id = '%s'
                    ORDER BY vl.call_date DESC
                    LIMIT %d
                    """
                    % (cid, lim),
                    columns=[
                        "call_date",
                        "phone_number",
                        "status",
                        "agent",
                        "uniqueid",
                        "length_in_sec",
                    ],
                )
                return rows
            except Exception as exc:
                _logger.warning("Hostinger get_call_log %s: %s", cid, exc)
                return []
        conn = self._connect(campaign_id=cid)
        try:
            cur = conn.cursor(dictionary=True)
            cur.execute(
                """
                SELECT vl.call_date, vl.phone_number, vl.status,
                       vl.user AS agent, vl.uniqueid,
                       GREATEST(
                           COALESCE(vl.length_in_sec, 0),
                           COALESCE(cl.length_in_sec, 0)
                       ) AS length_in_sec
                FROM vicidial_log vl
                LEFT JOIN call_log cl ON cl.uniqueid = vl.uniqueid
                WHERE vl.campaign_id = %s
                ORDER BY vl.call_date DESC
                LIMIT %s
                """,
                (cid, lim),
            )
            rows = cur.fetchall()
            cur.close()
            return rows
        finally:
            conn.close()

    def get_amd_stats(self, campaign_id):
        cid = self._sanitize_vicidial_id(campaign_id)
        if self._is_hostinger_campaign(cid):
            try:
                rows = self._hostinger_query_rows(
                    """
                    SELECT status, COUNT(*) AS count
                    FROM vicidial_log
                    WHERE campaign_id = '%s' AND call_date >= CURDATE()
                    GROUP BY status
                    """
                    % cid,
                    columns=["status", "count"],
                )
                total = sum(int(r.get("count") or 0) for r in rows)
                return {
                    "by_status": {r["status"]: int(r["count"]) for r in rows},
                    "total": total,
                }
            except Exception as exc:
                _logger.warning("Hostinger get_amd_stats %s: %s", cid, exc)
                return {"by_status": {}, "total": 0}
        conn = self._connect(campaign_id=cid)
        try:
            cur = conn.cursor(dictionary=True)
            cur.execute(
                """
                SELECT status, COUNT(*) AS count
                FROM vicidial_log
                WHERE campaign_id = %s
                  AND call_date >= CURDATE()
                GROUP BY status
                """,
                (cid,),
            )
            rows = cur.fetchall()
            cur.close()
            total = sum(int(r.get("count") or 0) for r in rows)
            return {
                "by_status": {r["status"]: int(r["count"]) for r in rows},
                "total": total,
            }
        finally:
            conn.close()

    def get_call_stats(self, campaign_id=None):
        cid = (campaign_id or "")[:8]
        amd = self.get_amd_stats(cid) if cid else {}
        by = amd.get("by_status", {})
        return {
            "total_calls": amd.get("total", 0),
            "answered": by.get("HUMAN", 0) + by.get("A", 0),
        }

    @staticmethod
    def _vicidial_status_bucket(status):
        """Regroupe un code VICIdial en catégorie lisible."""
        st = (status or "").upper()
        if st in ("A", "SALE", "S", "HUMAN", "PU", "PM", "XFER"):
            return "human"
        if st in ("AA", "AM", "AMD", "AB", "MACHINE"):
            return "repondeur"
        if st in ("DC", "DISCONNECT", "INVALID", "ERR", "PDROP", "DNC"):
            return "mauvais_numero"
        if st in ("NA", "NOANSWER", "N", "TIMEOT", "TIMEOUT"):
            return "sans_reponse"
        if st in ("B", "BUSY"):
            return "occupe"
        return "autre"

    def get_call_breakdown(self, campaign, days=30):
        """Compteurs appels par résultat (VICIdial + journaux Odoo)."""
        empty = {
            "total": 0,
            "human": 0,
            "repondeur": 0,
            "mauvais_numero": 0,
            "sans_reponse": 0,
            "occupe": 0,
            "qualifie": 0,
            "autre": 0,
            "period_days": days,
        }
        if not campaign:
            return empty
        buckets = {k: 0 for k in empty if k not in ("period_days",)}
        cid = (campaign.vicidial_campaign_id or "")[:8]
        if cid and self.is_available():
            conn = self._connect()
            try:
                cur = conn.cursor(dictionary=True)
                cur.execute(
                    """
                    SELECT vl.status,
                           COUNT(*) AS count,
                           SUM(
                               CASE WHEN COALESCE(cl.length_in_sec, 0) >= 10
                               THEN 1 ELSE 0 END
                           ) AS connected
                    FROM vicidial_log vl
                    LEFT JOIN call_log cl ON cl.uniqueid = vl.uniqueid
                    WHERE vl.campaign_id = %s
                      AND vl.call_date >= DATE_SUB(CURDATE(), INTERVAL %s DAY)
                    GROUP BY vl.status
                    """,
                    (cid, int(days)),
                )
                human_from_duration = 0
                for row in cur.fetchall():
                    count = int(row.get("count") or 0)
                    connected = int(row.get("connected") or 0)
                    human_from_duration += connected
                    buckets["total"] += count
                    if (row.get("status") or "").upper() in (
                        "SALE",
                        "S",
                        "INTEREST",
                        "INT",
                    ):
                        buckets["qualifie"] += count
                    no_connect = count - connected
                    st = (row.get("status") or "").upper()
                    if connected:
                        buckets["human"] += connected
                    if no_connect:
                        bucket = self._vicidial_status_bucket(row.get("status"))
                        if bucket == "human":
                            bucket = "sans_reponse"
                        buckets[bucket] = buckets.get(bucket, 0) + no_connect
                if human_from_duration and not buckets["qualifie"]:
                    buckets["autre"] = max(
                        0,
                        buckets["total"]
                        - buckets["human"]
                        - buckets["repondeur"]
                        - buckets["mauvais_numero"]
                        - buckets["sans_reponse"]
                        - buckets["occupe"],
                    )
                cur.close()
            finally:
                conn.close()

        if not buckets["total"]:
            CallLog = self.env["doorway.call.log"].sudo()
            since = fields.Datetime.subtract(
                fields.Datetime.now(), days=int(days)
            )
            logs = CallLog.search(
                [
                    ("campaign_id", "=", campaign.id),
                    ("call_date", ">=", since),
                ]
            )
            for log in logs:
                bucket = self._classify_odoo_call_log(log)
                buckets[bucket] = buckets.get(bucket, 0) + 1
                buckets["total"] += 1
                if log.disposition in ("VENTE", "INTERET"):
                    buckets["qualifie"] += 1

        buckets["period_days"] = days
        return buckets

    @staticmethod
    def _classify_odoo_call_log(log):
        if log.amd_result == "human":
            return "human"
        if log.amd_result in ("answering_machine", "amd_hangup") or (
            log.disposition == "REPONDEUR"
        ):
            return "repondeur"
        if log.disposition == "INVALIDE" or log.amd_result == "invalid":
            return "mauvais_numero"
        if log.amd_result == "no_answer":
            return "sans_reponse"
        if log.amd_result == "busy":
            return "occupe"
        return "autre"

    def sync_call_logs(self, campaigns, limit=100, fast=False):
        CallLog = self.env["doorway.call.log"].sudo()
        created = 0
        updated = 0
        lim = max(1, min(int(limit or 100), 500))
        for camp in campaigns:
            if not camp.vicidial_campaign_id:
                continue
            cid = (camp.vicidial_campaign_id or "")[:8]
            for row in self.get_call_log(cid, lim):
                uid = row.get("uniqueid")
                if not uid:
                    continue
                existing = CallLog.search([("vicidial_call_id", "=", uid)], limit=1)
                rec_url = False
                if not fast:
                    rec_url = self.normalize_recording_url(False, uid)
                    if cid in LEA_QC_CAMPAIGN_IDS or cid in DOOR_APP0_QC_CAMPAIGN_IDS:
                        if not rec_url:
                            rec_url = self.resolve_lea_recording_url(uid)
                agent_login = row.get("agent")
                human = self._resolve_human_agent(agent_login)
                duration = int(row.get("length_in_sec") or 0)
                status = row.get("status")
                if self._is_hostinger_campaign(cid):
                    amd_result = self._infer_amd_for_hostinger_call(
                        uid, status=status, duration=duration, use_agi=not fast
                    )
                else:
                    amd_result = self.map_amd_from_vicidial(None, status=status)
                    st = (status or "").upper()
                    if (
                        duration >= 10
                        and amd_result in ("no_answer", False)
                        and st in self._human_vicidial_statuses()
                    ):
                        amd_result = "human"
                if self._is_voicemail_call(amd_result, status=status):
                    rec_url = False
                if existing:
                    patch = {}
                    merged_rec = self._pick_recording_url(
                        existing.recording_url, rec_url
                    )
                    if (
                        merged_rec
                        and merged_rec != existing.recording_url
                        and not self._is_voicemail_call(
                            amd_result or existing.amd_result,
                            existing.disposition,
                            status,
                        )
                    ):
                        patch["recording_url"] = merged_rec
                    ia_label = self._ia_agent_label(cid, agent_login)
                    if human and not existing.human_agent_id:
                        patch["human_agent_id"] = human.id
                        if not existing.agent_name:
                            patch["agent_name"] = (
                                human.full_name or human.user_id.name
                            )
                    elif ia_label and (
                        not existing.agent_name
                        or existing.agent_name in ("VDAD", "VDCL")
                    ):
                        patch["agent_name"] = ia_label
                    if duration and (existing.duration or 0) < duration:
                        patch["duration"] = duration
                        if amd_result:
                            patch["amd_result"] = amd_result
                            if self._is_voicemail_call(
                                amd_result, existing.disposition, status
                            ):
                                patch["recording_url"] = False
                                patch.setdefault("disposition", "REPONDEUR")
                        elif (
                            self._is_hostinger_campaign(cid)
                            and existing.amd_result == "human"
                            and not fast
                        ):
                            inferred = self._infer_amd_for_hostinger_call(
                                uid,
                                status=status,
                                duration=duration,
                                use_agi=True,
                            )
                            if inferred and inferred != "human":
                                patch["amd_result"] = inferred
                                if inferred in (
                                    "amd_hangup",
                                    "answering_machine",
                                ):
                                    patch.setdefault("disposition", "REPONDEUR")
                    if patch:
                        existing.write(patch)
                        updated += 1
                    continue
                human = self._resolve_human_agent(agent_login)
                ia_label = self._ia_agent_label(cid, agent_login)
                CallLog.create(
                    {
                        "campaign_id": camp.id,
                        "vicidial_call_id": uid,
                        "phone_number": row.get("phone_number"),
                        "call_date": row.get("call_date"),
                        "duration": duration,
                        "agent_name": (
                            (human.full_name or human.user_id.name)
                            if human
                            else (ia_label or agent_login)
                        ),
                        "human_agent_id": human.id if human else False,
                        "amd_result": amd_result,
                        "disposition": self.map_disposition_from_vicidial(status),
                        "recording_url": False
                        if self._is_voicemail_call(amd_result, status=status)
                        else (rec_url or False),
                    }
                )
                created += 1
        return {"created": created, "updated": updated}

    def upsert_call_from_webhook(self, payload):
        vals = self._prepare_call_log_vals(payload)
        return bool(self._save_call_log(vals))

    def _find_lead_for_call(self, phone, vicidial_call_id):
        Lead = self.env["crm.lead"].sudo()
        if vicidial_call_id:
            sync = self.env["doorway.vicidial.call.sync"].sudo().search(
                [("vicidial_call_id", "=", str(vicidial_call_id))], limit=1
            )
            if sync and sync.lead_id:
                return sync.lead_id
            lead = Lead.search([("vicidial_call_uid", "=", str(vicidial_call_id))], limit=1)
            if lead:
                return lead
        if phone:
            digits = re.sub(r"\D", "", phone)[-9:]
            if digits:
                domain = [("active", "=", True), ("phone", "ilike", digits)]
                if "mobile" in Lead._fields:
                    domain = [
                        ("active", "=", True),
                        "|",
                        ("phone", "ilike", digits),
                        ("mobile", "ilike", digits),
                    ]
                return Lead.search(domain, limit=1)
        return Lead.browse()

    def _sync_coaching_from_call_log(self, log):
        if not log.lead_id or not log.recording_url:
            return
        Coaching = self.env.get("pe.coaching.call")
        if not Coaching:
            return
        existing = Coaching.sudo().search(
            [("vicidial_call_id", "=", log.vicidial_call_id)], limit=1
        )
        employee = self.env["doorway.vicidial.call.sync"]._resolve_employee_for_user(
            log.lead_id.user_id or self.env.user
        )
        if not employee:
            return
        vals = {
            "employee_id": employee.id,
            "date_appel": log.call_date or datetime.now(),
            "source": "vicidial",
            "vicidial_call_id": log.vicidial_call_id,
            "duree_secondes": log.duration or 0,
            "numero_appele": log.phone_number,
            "lead_id": log.lead_id.id,
            "audio_url": log.recording_url,
        }
        if "qualification_appel" in Coaching._fields:
            vals["qualification_appel"] = log.lead_id.qualification_statut
        if existing:
            existing.write(vals)
        else:
            Coaching.sudo().create(vals)
