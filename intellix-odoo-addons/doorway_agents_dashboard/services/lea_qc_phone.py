# -*- coding: utf-8 -*-
"""Normalisation téléphone Léa-QC (QC/CA) — VICIdial + parsing chaînes concaténées."""
import logging
import re

_logger = logging.getLogger(__name__)

_ODOO_CONF = "/etc/odoo-server.conf"


def _mysql_cfg():
    """Credentials VICIdial (même source que VicidialService)."""
    conf = {}
    try:
        with open(_ODOO_CONF, encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line or line[0] in "#;" or "=" not in line:
                    continue
                key, val = line.split("=", 1)
                conf[key.strip()] = val.strip()
    except OSError:
        pass

    def _get(*keys, default=""):
        for key in keys:
            val = __import__("os").environ.get(key) or conf.get(key)
            if val:
                return val
        return default

    return {
        "host": _get("VICIDIAL_DB_HOST", default="127.0.0.1"),
        "port": int(_get("VICIDIAL_DB_PORT", default="3307") or 3307),
        "user": _get("VICIDIAL_DB_USER", default="vicidial"),
        "password": _get(
            "VICIDIAL_DB_PASSWORD",
            "VICIDIAL_DB_PASS",
            "doorway_vicidial_campaigns.db_password",
        ),
        "database": _get("VICIDIAL_DB_NAME", default="asterisk"),
    }


def _mysql_connect():
    import mysql.connector

    cfg = _mysql_cfg()
    return mysql.connector.connect(
        host=cfg["host"],
        port=cfg["port"],
        user=cfg["user"],
        password=cfg["password"],
        database=cfg["database"],
        connection_timeout=5,
    )

QC_AREA_CODES = (
    "438",
    "514",
    "819",
    "450",
    "579",
    "418",
    "581",
    "873",
    "367",
    "613",
)

INVALID_PHONES = frozenset({"", "unknown", "s", "anonymous"})


def digits_only(raw):
    return re.sub(r"\D", "", raw or "")


def is_garbage_phone(raw):
    """Numéro illisible (concaténation AGI / placeholder)."""
    phone = (raw or "").strip().lower()
    if phone in INVALID_PHONES:
        return True
    d = digits_only(phone)
    if not d or len(d) < 9:
        return True
    if len(d) > 11:
        return True
    if re.match(r"^[Vv]\d", phone):
        return True
    return False


def _valid_national_ten(d):
    return len(d) == 10 and d[:3] in QC_AREA_CODES


def extract_from_garbage(raw):
    """Extrait un numéro 10 chiffres QC depuis une chaîne longue."""
    d = digits_only(raw)
    if not d or len(d) <= 11:
        return ""
    candidates = []
    for i in range(len(d) - 9):
        w = d[i : i + 10]
        if _valid_national_ten(w):
            candidates.append(w)
    if not candidates:
        return ""
    # Préférer 819/438/450 (hors métropole) puis le premier trouvé
    priority = {"819": 0, "438": 1, "450": 2, "579": 3, "418": 4, "581": 5, "873": 6, "367": 7, "613": 8, "514": 9}
    candidates.sort(key=lambda n: (priority.get(n[:3], 99), n))
    return candidates[0]


def normalize_national(raw):
    """Retourne 10 chiffres nationaux CA/QC ou chaîne vide."""
    phone = (raw or "").strip()
    if phone.lower() in INVALID_PHONES:
        return ""
    d = digits_only(phone)
    if not d:
        return ""
    if len(d) == 11 and d.startswith("1"):
        d = d[1:]
    if _valid_national_ten(d):
        return d
    if len(d) == 10:
        return d
    if len(d) > 11:
        return extract_from_garbage(phone)
    return ""


def format_phone_display(national):
    """Affichage lisible +1 (XXX) XXX-XXXX."""
    d = normalize_national(national)
    if not d or len(d) != 10:
        return (national or "").strip() or "—"
    return "+1 (%s) %s-%s" % (d[:3], d[3:6], d[6:])


def lookup_vicidial_lead_id(raw):
    """Extrait lead_id VICIdial depuis callerid concaténé (AGI cid[10:20])."""
    d = digits_only(raw)
    if len(d) < 20:
        return ""
    try:
        lead_id = int(d[10:20])
    except ValueError:
        return ""
    if lead_id < 100000:
        return ""
    try:
        conn = _mysql_connect()
        cur = conn.cursor()
        cur.execute(
            "SELECT phone_number FROM vicidial_list WHERE lead_id=%s LIMIT 1",
            (lead_id,),
        )
        row = cur.fetchone()
        cur.close()
        conn.close()
        if row and row[0]:
            nat = normalize_national(row[0])
            if nat and d.endswith(nat[-6:]):
                return nat
    except Exception as exc:  # noqa: BLE001
        _logger.debug("lea_qc_phone lead_id lookup %s: %s", lead_id, exc)
    return ""


def lookup_vicidial_mysql(uniqueid):
    """Lit phone_number VICIdial par uniqueid (auto_calls puis log)."""
    uid = re.sub(r"[^0-9.]", "", uniqueid or "")
    if not uid:
        return ""
    try:
        conn = _mysql_connect()
        cur = conn.cursor()
        for sql in (
            "SELECT phone_number FROM vicidial_auto_calls "
            "WHERE uniqueid=%s ORDER BY call_time DESC LIMIT 1",
            "SELECT phone_number FROM vicidial_log "
            "WHERE uniqueid=%s ORDER BY call_date DESC LIMIT 1",
        ):
            cur.execute(sql, (uid,))
            row = cur.fetchone()
            if row and row[0]:
                nat = normalize_national(row[0])
                if nat:
                    cur.close()
                    conn.close()
                    return nat
        cur.close()
        conn.close()
    except Exception as exc:  # noqa: BLE001
        _logger.debug("lea_qc_phone vicidial lookup %s: %s", uniqueid, exc)
    return ""


def lookup_vicidial_suffix(raw):
    """Cherche dans vicidial_list un numéro dont le suffixe matche la fin du garbage."""
    d = digits_only(raw)
    if len(d) < 12:
        return ""
    priority = {
        "819": 0,
        "438": 1,
        "450": 2,
        "579": 3,
        "418": 4,
        "581": 5,
        "873": 6,
        "367": 7,
        "613": 8,
        "514": 9,
    }
    best = ""
    best_key = (99, 99)
    for suffix_len in (8, 7, 6):
        suffix = d[-suffix_len:]
        try:
            conn = _mysql_connect()
            cur = conn.cursor()
            cur.execute(
                "SELECT phone_number FROM vicidial_list "
                "WHERE phone_number LIKE %s LIMIT 10",
                ("%" + suffix,),
            )
            rows = cur.fetchall()
            cur.close()
            conn.close()
            for (phone,) in rows:
                nat = normalize_national(phone)
                if not nat or not nat.endswith(suffix):
                    continue
                key = (10 - suffix_len, priority.get(nat[:3], 99))
                if key < best_key:
                    best_key = key
                    best = nat
        except Exception as exc:  # noqa: BLE001
            _logger.debug("lea_qc_phone suffix lookup: %s", exc)
    return best


def resolve_phone(raw, call_sid=None, partner_phone=None):
    """
    Résout le meilleur numéro national (10 chiffres).
    Ordre : VICIdial uniqueid → (garbage: lead_id/suffix/parse) → partner → national direct.
    """
    garbage = is_garbage_phone(raw)
    for src in (lookup_vicidial_mysql(call_sid) if call_sid else "",):
        nat = normalize_national(src)
        if nat and not is_garbage_phone(nat):
            return nat
    if garbage:
        for src in (
            lookup_vicidial_lead_id(raw),
            lookup_vicidial_suffix(raw),
            extract_from_garbage(raw),
        ):
            if src and not is_garbage_phone(src):
                return src
        return ""
    for src in (partner_phone, raw):
        nat = normalize_national(src)
        if nat and not is_garbage_phone(nat):
            return nat
    return normalize_national(raw)


def apply_vicidial_dnc(raw_phone, campaign_id="DW_QCB2C", user="LEA_QC"):
    """
    Ajoute le numéro au DNC VICIdial (vicidial_dnc + statut lead DNC + purge hopper).
    Campagne DW_QCB2C : use_internal_dnc=Y — insertion globale vicidial_dnc.
    """
    phone = resolve_phone(raw_phone) or normalize_national(raw_phone)
    digits = digits_only(phone)
    if len(digits) == 11 and digits.startswith("1"):
        digits = digits[1:]
    if len(digits) != 10:
        _logger.warning("lea_qc DNC skip invalid phone=%r campaign=%s", raw_phone, campaign_id)
        return {"ok": False, "error": "invalid_phone", "phone": raw_phone}

    try:
        conn = _mysql_connect()
    except Exception as exc:  # noqa: BLE001
        _logger.warning("lea_qc DNC mysql connect failed: %s", exc)
        return {"ok": False, "error": str(exc)}

    try:
        cur = conn.cursor()
        cur.execute(
            "INSERT IGNORE INTO vicidial_dnc SET phone_number=%s",
            (digits,),
        )
        cur.execute(
            """
            INSERT INTO vicidial_dnc_log
                (phone_number, campaign_id, action, action_date, user)
            VALUES (%s, '-SYSINT-', 'add', NOW(), %s)
            """,
            (digits, user),
        )
        cur.execute(
            """
            UPDATE vicidial_list vl
            INNER JOIN vicidial_lists vls ON vl.list_id = vls.list_id
            SET vl.status = 'DNC', vl.called_since_last_reset = 'N'
            WHERE vls.campaign_id = %s AND vl.phone_number = %s
            """,
            (campaign_id, digits),
        )
        leads_updated = cur.rowcount
        cur.execute(
            """
            DELETE h FROM vicidial_hopper h
            INNER JOIN vicidial_list vl ON h.lead_id = vl.lead_id
            WHERE h.campaign_id = %s AND vl.phone_number = %s
            """,
            (campaign_id, digits),
        )
        hopper_purged = cur.rowcount
        conn.commit()
        cur.close()
        _logger.info(
            "lea_qc DNC applied phone=%s campaign=%s leads=%s hopper=%s",
            digits,
            campaign_id,
            leads_updated,
            hopper_purged,
        )
        return {
            "ok": True,
            "phone": digits,
            "campaign": campaign_id,
            "leads_updated": leads_updated,
            "hopper_purged": hopper_purged,
        }
    except Exception as exc:  # noqa: BLE001
        _logger.warning("lea_qc DNC failed phone=%s: %s", digits, exc)
        return {"ok": False, "error": str(exc), "phone": digits}
    finally:
        conn.close()
