# -*- coding: utf-8 -*-
"""Monitoring live agents IA — Sofia FR (DW_FRB2C) + Léa QC (DW_QCB2C)."""
import json
import logging
import os
from datetime import datetime
from zoneinfo import ZoneInfo

from odoo import fields

_logger = logging.getLogger(__name__)

JSON_PATH = "/opt/doorway/reports/ia_agents_live.json"
TZ_PARIS = ZoneInfo("Europe/Paris")

CAMPAIGNS = {
    "DW_FRB2C": {
        "label": "Sofia FR",
        "log_path": "/var/log/sofia-live.log",
        "log_name": "sofia-live.log",
    },
    "DW_QCB2C": {
        "label": "Léa QC",
        "log_path": "/var/log/lea-qc-live.log",
        "log_name": "lea-qc-live.log",
    },
}

LOG_PATTERNS = {
    "opening": "OPENING call=",
    "empty_rec": "EMPTY_REC",
    "empty_stt": "EMPTY_STT",
    "early_empty": "EARLY_EMPTY",
}

AMD_LABELS = {
    "human": "Humain (AMD)",
    "no_answer": "Sans réponse",
    "answering_machine": "Répondeur",
    "amd_hangup": "Répondeur (raccroché)",
    "busy": "Occupé",
    "invalid": "Invalide",
    False: "Inconnu",
    "": "Inconnu",
}

CAMPAIGN_ORDER = list(CAMPAIGNS.keys())


class IaAgentsLiveService:
    def __init__(self, env):
        self.env = env

    @staticmethod
    def parse_status_string(raw):
        """Parse 'NA:89;DROP:5' into [{"key": "NA", "count": 89}, ...]."""
        items = []
        if not raw:
            return items
        for part in str(raw).split(";"):
            part = part.strip()
            if not part or ":" not in part:
                continue
            key, _, count_str = part.partition(":")
            try:
                items.append({"key": key.strip(), "count": int(count_str.strip() or 0)})
            except ValueError:
                continue
        return items

    def build_snapshot(self, live=False):
        if not live and os.path.isfile(JSON_PATH):
            try:
                with open(JSON_PATH, encoding="utf-8") as handle:
                    data = json.load(handle)
                return self._normalize_snapshot(data, source="file")
            except Exception as exc:  # noqa: BLE001
                _logger.warning(
                    "ia_agents_live: cannot read %s: %s", JSON_PATH, exc
                )
        return self._compute_live()

    def _normalize_snapshot(self, data, source="file"):
        campaigns = {}
        for cid, cfg in CAMPAIGNS.items():
            raw = dict((data.get("campaigns") or {}).get(cid) or {})
            if not raw:
                campaigns[cid] = self._empty_campaign(cid)
                continue
            raw.setdefault("label", cfg["label"])
            raw.setdefault("log_name", cfg["log_name"])
            raw["vicidial_statuses"] = self._as_status_list(
                raw.get("vicidial_statuses")
            )
            raw["odoo_dispositions"] = self._as_status_list(
                raw.get("odoo_dispositions"), self._label_disposition
            )
            raw["odoo_amd_results"] = self._as_status_list(
                raw.get("odoo_amd_results"), self._label_amd
            )
            raw.setdefault(
                "ia_log",
                {"opening": 0, "empty_rec": 0, "empty_stt": 0, "early_empty": 0},
            )
            campaigns[cid] = raw
        return {
            "generated_at": data.get("generated_at"),
            "date_paris": data.get("date_paris"),
            "source": source,
            "vicidial_available": data.get("vicidial_available", True),
            "message": data.get("message"),
            "campaign_order": CAMPAIGN_ORDER,
            "campaigns": campaigns,
        }

    @staticmethod
    def _label_disposition(key):
        if key in ("(vide)", "", None):
            return "Non qualifié"
        return key

    @staticmethod
    def _label_amd(key):
        return AMD_LABELS.get(key, str(key) if key else "Inconnu")

    @staticmethod
    def _as_status_list(value, label_fn=None):
        if isinstance(value, list):
            if label_fn:
                return [
                    {**item, "key": label_fn(item.get("key"))}
                    for item in value
                ]
            return value
        items = IaAgentsLiveService.parse_status_string(value)
        if label_fn:
            return [{**item, "key": label_fn(item["key"])} for item in items]
        return items

    def _compute_live(self):
        now_paris = datetime.now(TZ_PARIS)
        day_str = now_paris.strftime("%Y-%m-%d")
        generated_at = now_paris.strftime("%Y-%m-%d %H:%M:%S %Z")

        vicidial_stats = {}
        vicidial_available = False
        message = None

        try:
            from odoo.addons.doorway_vicidial_campaigns.services.vicidial_service import (  # noqa: PLC0415
                VicidialService,
            )

            svc = VicidialService(self.env)
            if svc.is_available():
                vicidial_available = True
                vicidial_stats = self._fetch_vicidial_stats(svc)
            else:
                message = (
                    "VICIdial MySQL indisponible — statistiques Odoo et logs IA uniquement."
                )
        except ImportError:
            message = (
                "Module doorway_vicidial_campaigns non installé — "
                "statistiques Odoo et logs IA uniquement."
            )
        except Exception as exc:  # noqa: BLE001
            _logger.exception("ia_agents_live: vicidial query failed")
            message = "Erreur VICIdial : %s" % str(exc)[:200]

        odoo_stats = self._fetch_odoo_stats(day_str)
        campaigns = {}
        for cid, cfg in CAMPAIGNS.items():
            vic = vicidial_stats.get(cid, {})
            odoo = odoo_stats.get(
                cid, {"odoo_logs": 0, "odoo_dispositions": []}
            )
            calls = int(vic.get("calls_today") or 0)
            connected = int(vic.get("connected_today") or 0)
            rate = round(connected * 100.0 / calls, 1) if calls else 0.0
            campaigns[cid] = {
                "label": cfg["label"],
                "log_name": cfg["log_name"],
                "calls_today": calls,
                "connected_today": connected,
                "connect_rate_pct": rate,
                "hopper_ready": int(vic.get("hopper_ready") or 0),
                "auto_dial_level": vic.get("auto_dial_level"),
                "active": vic.get("active"),
                "agents_ready": int(vic.get("agents_ready") or 0),
                "odoo_logs": int(odoo.get("odoo_logs") or 0),
                "vicidial_statuses": vic.get("vicidial_statuses") or [],
                "odoo_dispositions": odoo.get("odoo_dispositions") or [],
                "odoo_amd_results": odoo.get("odoo_amd_results") or [],
                "ia_log": self._count_log_today(cfg["log_path"], day_str),
            }

        return {
            "generated_at": generated_at,
            "date_paris": day_str,
            "source": "live",
            "vicidial_available": vicidial_available,
            "message": message,
            "campaign_order": CAMPAIGN_ORDER,
            "campaigns": campaigns,
        }

    def _fetch_vicidial_stats(self, svc):
        result = {}
        conn, cur = svc._cursor()
        try:
            for cid in CAMPAIGNS:
                cur.execute(
                    """
                    SELECT COUNT(*),
                           COALESCE(SUM(
                               length_in_sec >= 8
                               AND status NOT IN ('AA', 'AM', 'AMD', 'NA')
                           ), 0)
                    FROM vicidial_log
                    WHERE call_date >= CURDATE() AND campaign_id = %s
                    """,
                    (cid,),
                )
                row = cur.fetchone() or (0, 0)
                calls_today = int(row[0] or 0)
                connected_today = int(row[1] or 0)

                cur.execute(
                    """
                    SELECT COUNT(*) FROM vicidial_hopper
                    WHERE campaign_id = %s AND status = 'READY'
                    """,
                    (cid,),
                )
                hopper_ready = int((cur.fetchone() or [0])[0])

                cur.execute(
                    """
                    SELECT auto_dial_level, active
                    FROM vicidial_campaigns
                    WHERE campaign_id = %s
                    """,
                    (cid,),
                )
                row2 = cur.fetchone()
                auto_dial_level = str(row2[0]) if row2 and row2[0] is not None else None
                active = str(row2[1]) if row2 and row2[1] is not None else None

                cur.execute(
                    """
                    SELECT COUNT(*) FROM vicidial_live_agents
                    WHERE campaign_id = %s AND status = 'READY'
                    """,
                    (cid,),
                )
                agents_ready = int((cur.fetchone() or [0])[0])

                cur.execute(
                    """
                    SELECT status, COUNT(*) AS cnt
                    FROM vicidial_log
                    WHERE call_date >= CURDATE()
                      AND campaign_id = %s
                      AND status NOT IN ('', 'NA')
                    GROUP BY status
                    ORDER BY cnt DESC
                    """,
                    (cid,),
                )
                vicidial_statuses = [
                    {"key": str(status), "count": int(count)}
                    for status, count in cur.fetchall()
                ]

                result[cid] = {
                    "calls_today": calls_today,
                    "connected_today": connected_today,
                    "hopper_ready": hopper_ready,
                    "auto_dial_level": auto_dial_level,
                    "active": active,
                    "agents_ready": agents_ready,
                    "vicidial_statuses": vicidial_statuses,
                }
        finally:
            cur.close()
            conn.close()
        return result

    def _fetch_odoo_stats(self, day_str):
        empty = {
            cid: {
                "odoo_logs": 0,
                "odoo_dispositions": [],
                "odoo_amd_results": [],
            }
            for cid in CAMPAIGNS
        }
        CallLog = self.env.get("doorway.call.log")
        Campaign = self.env.get("doorway.campaign")
        if not CallLog or not Campaign:
            return empty

        day_start_paris = datetime.strptime(day_str, "%Y-%m-%d").replace(
            tzinfo=TZ_PARIS
        )
        day_start_utc = day_start_paris.astimezone(ZoneInfo("UTC")).replace(
            tzinfo=None
        )

        campaigns = Campaign.sudo().search(
            [("vicidial_campaign_id", "in", list(CAMPAIGNS.keys()))]
        )
        if not campaigns:
            return empty

        cid_by_campaign_id = {
            rec.id: rec.vicidial_campaign_id for rec in campaigns
        }
        logs = CallLog.sudo().search(
            [
                ("campaign_id", "in", campaigns.ids),
                ("create_date", ">=", fields.Datetime.to_string(day_start_utc)),
            ]
        )

        log_counts = {cid: 0 for cid in CAMPAIGNS}
        disp_counts = {}
        amd_counts = {}
        for log in logs:
            cid = cid_by_campaign_id.get(log.campaign_id.id)
            if cid not in CAMPAIGNS:
                continue
            log_counts[cid] += 1
            disp = self._label_disposition((log.disposition or "").strip())
            key = (cid, disp)
            disp_counts[key] = disp_counts.get(key, 0) + 1
            amd_key = (cid, log.amd_result or "")
            amd_counts[amd_key] = amd_counts.get(amd_key, 0) + 1

        result = {}
        for cid in CAMPAIGNS:
            dispositions = [
                {"key": disp, "count": count}
                for (camp_id, disp), count in sorted(
                    disp_counts.items(), key=lambda item: -item[1]
                )
                if camp_id == cid
            ]
            amd_results = [
                {"key": self._label_amd(amd), "count": count}
                for (camp_id, amd), count in sorted(
                    amd_counts.items(), key=lambda item: -item[1]
                )
                if camp_id == cid
            ]
            result[cid] = {
                "odoo_logs": log_counts.get(cid, 0),
                "odoo_dispositions": dispositions,
                "odoo_amd_results": amd_results,
            }
        return result

    @staticmethod
    def _count_log_today(log_path, day_str):
        counts = {key: 0 for key in LOG_PATTERNS}
        if not os.path.isfile(log_path):
            return counts
        try:
            with open(log_path, encoding="utf-8", errors="replace") as handle:
                for line in handle:
                    if not line.startswith(day_str):
                        continue
                    for key, pattern in LOG_PATTERNS.items():
                        if pattern in line:
                            counts[key] += 1
        except OSError as exc:
            _logger.warning("ia_agents_live: cannot read %s: %s", log_path, exc)
        return counts

    def _empty_campaign(self, cid):
        cfg = CAMPAIGNS[cid]
        return {
            "label": cfg["label"],
            "log_name": cfg["log_name"],
            "calls_today": 0,
            "connected_today": 0,
            "connect_rate_pct": 0.0,
            "hopper_ready": 0,
            "auto_dial_level": None,
            "active": None,
            "agents_ready": 0,
            "odoo_logs": 0,
            "vicidial_statuses": [],
            "odoo_dispositions": [],
            "ia_log": {
                "opening": 0,
                "empty_rec": 0,
                "empty_stt": 0,
                "early_empty": 0,
            },
        }
