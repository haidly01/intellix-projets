# -*- coding: utf-8 -*-
"""Journal veille → social_actions_log (nouveaux action_type seulement).

N'altère pas like/comment/follow ni le HTML #soc-log.
Statut: genere → converti (manuel).
"""
from __future__ import annotations

import json
import sqlite3
import uuid
from datetime import datetime, timezone

DB_PATH = "/odoo/custom/reseaux-sociaux/data/reseaux-sociaux.sqlite"

# slug → branches par défaut si le compte n'existe pas encore.
SEED_ACCOUNTS = {
    "leila": {
        "display_name": "Leila — Facebook",
        "platform": "facebook",
        "branches": '["soumission_entrepreneurs","soumission_toitures","maison_recherchee"]',
        "timezone": "America/Toronto",
    },
}


def _connect():
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    return con


def ensure_leila_account(con) -> None:
    row = con.execute(
        "select id from social_accounts where slug = ? and platform = ?",
        ("leila", "facebook"),
    ).fetchone()
    if row:
        return
    spec = SEED_ACCOUNTS["leila"]
    con.execute(
        """insert into social_accounts
        (id, slug, display_name, platform, branches, status, daily_cap, timezone,
         skip_weekends, created_at, updated_at)
        values (?, 'leila', ?, 'facebook', ?, 'actif', 12, ?, 1, datetime('now'), datetime('now'))""",
        (str(uuid.uuid4()), spec["display_name"], spec["branches"], spec["timezone"]),
    )


def _account_id(con, slug: str, platform: str = "facebook") -> str | None:
    ensure_leila_account(con)
    row = con.execute(
        "select id from social_accounts where slug = ? and platform = ?",
        (slug, platform),
    ).fetchone()
    if row:
        return row["id"]
    row = con.execute(
        "select id from social_accounts where slug = ? order by platform limit 1",
        (slug,),
    ).fetchone()
    return row["id"] if row else None


def log_followup(
    *,
    slug: str,
    kind: str,
    signal_id: str,
    texte: str,
    url: str = "",
    platform: str = "facebook",
) -> dict:
    """kind: public | prive. result=genere."""
    if kind not in ("public", "prive"):
        return {"ok": False, "error": "kind invalide"}
    action = "veille_public" if kind == "public" else "veille_prive"
    con = _connect()
    try:
        ensure_leila_account(con)
        account_id = _account_id(con, slug, platform)
        if not account_id:
            return {"ok": False, "error": "compte introuvable pour %s" % slug}
        existing = con.execute(
            """select id from social_actions_log
               where action_type = ? and json_extract(detail, '$.signal_id') = ?""",
            (action, str(signal_id)),
        ).fetchone()
        if existing:
            return {"ok": True, "id": existing["id"], "already": True, "result": "genere"}
        row_id = str(uuid.uuid4())
        detail = {
            "via": "veille-manuel",
            "signal_id": str(signal_id),
            "texte_envoye": texte or "",
            "auteur": slug,
        }
        con.execute(
            """insert into social_actions_log
               (id, account_id, platform, action_type, target, result, detail, created_at)
               values (?, ?, ?, ?, ?, 'genere', ?, datetime('now'))""",
            (row_id, account_id, platform, action, url or "", json.dumps(detail, ensure_ascii=False)),
        )
        con.commit()
        return {"ok": True, "id": row_id, "result": "genere"}
    finally:
        con.close()


def set_converti(signal_id: str, slug: str | None = None) -> dict:
    con = _connect()
    try:
        sql = """update social_actions_log
                 set result = 'converti',
                     detail = json_set(coalesce(detail, '{}'), '$.converti_at', ?, '$.converti_par', ?)
                 where action_type in ('veille_public', 'veille_prive')
                   and json_extract(detail, '$.signal_id') = ?
                   and result = 'genere'"""
        con.execute(
            sql,
            (
                datetime.now(timezone.utc).isoformat(),
                slug or "",
                str(signal_id),
            ),
        )
        con.commit()
        n = con.total_changes
        return {"ok": True, "updated": n}
    finally:
        con.close()


def commission_report() -> dict:
    con = _connect()
    try:
        ensure_leila_account(con)
        rows = con.execute(
            """select a.slug, l.result,
                      count(distinct json_extract(l.detail, '$.signal_id')) as n
               from social_actions_log l
               join social_accounts a on a.id = l.account_id
               where l.action_type in ('veille_public', 'veille_prive')
               group by a.slug, l.result"""
        ).fetchall()
        people = {}
        for row in rows:
            bucket = people.setdefault(
                row["slug"],
                {"slug": row["slug"], "genere": 0, "converti": 0, "dh": 0},
            )
            bucket[row["result"]] = row["n"]
        for bucket in people.values():
            bucket["dh"] = int(bucket.get("converti") or 0) * 50
        return {
            "ok": True,
            "taux_dh": 50,
            "note": "50 DH / lead converti — comptage seulement, pas de paiement.",
            "par_personne": list(people.values()),
        }
    finally:
        con.close()


def followups_for_signal(signal_id: str) -> dict:
    con = _connect()
    try:
        rows = con.execute(
            """select l.action_type, l.result, a.slug
               from social_actions_log l
               join social_accounts a on a.id = l.account_id
               where l.action_type in ('veille_public', 'veille_prive')
                 and json_extract(detail, '$.signal_id') = ?""",
            (str(signal_id),),
        ).fetchall()
        out = {"public": None, "prive": None}
        for row in rows:
            key = "public" if row["action_type"] == "veille_public" else "prive"
            out[key] = {"result": row["result"], "slug": row["slug"]}
        return out
    finally:
        con.close()
