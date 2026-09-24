#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Idempotent Odoo 19 gamification setup for intellixcrm (XML-RPC).

Creates 4 personal challenges + 4 system-only badges for Sales agents.

Usage (XML-RPC):
  ODOO_USERNAME=root ODOO_PASSWORD='...' python3 /root/scripts/setup_gamification_objectifs.py

Usage (local shell on server):
  sudo -u odoo /odoo/odoo-server/odoo-bin shell -c /etc/odoo-server.conf \\
    -d intellixcrm --no-http --log-level=error <<'PY'
  import importlib.util
  p = '/root/scripts/setup_gamification_objectifs.py'
  m = importlib.util.spec_from_file_location('sg', p)
  mod = importlib.util.module_from_spec(m); m.loader.exec_module(mod)
  mod.run_setup(mod.OdooEnv(env))
  PY

Note: ``admin_passwd`` in /etc/odoo-server.conf is the database master password,
not the Odoo user login — set ODOO_PASSWORD to the res.users password.
On this instance the superuser login is ``root`` (not ``admin``).
"""
from __future__ import annotations

import importlib.util
import os
import sys
import xmlrpc.client
from typing import Any

URL = os.environ.get("ODOO_URL", "http://93.127.162.97:8069")
DB = os.environ.get("ODOO_DB", "intellixcrm")
USERNAME = os.environ.get("ODOO_USERNAME", "admin")

SALES_GROUP_XMLID = "sales_team.group_sale_salesman"

CHALLENGES = [
    {
        "name": "Chasseur de leads",
        "description": "Créer 15 nouveaux leads par semaine.",
        "period": "weekly",
        "badge_name": "Chasseur de leads",
        "badge_description": "15 leads créés en une semaine — excellente prospection !",
        "goal": {
            "def_name": "Intellix — Leads créés",
            "def_description": "Nombre de leads/opportunités CRM créés par l'agent.",
            "computation_mode": "count",
            "model": "crm.lead",
            "field_date": "create_date",
            "domain": "['|', ('type', '=', 'lead'), ('type', '=', 'opportunity')]",
            "batch_field": "user_id",
        },
        "target": 15,
    },
    {
        "name": "Closer du mois",
        "description": "Conclure 12 opportunités gagnées par mois.",
        "period": "monthly",
        "badge_name": "Closer du mois",
        "badge_description": "12 deals gagnés en un mois — performance de closer exceptionnelle.",
        "goal": {
            "def_name": "Intellix — Leads gagnés",
            "def_description": "Opportunités CRM passées en étape Gagné (stage_id.is_won).",
            "computation_mode": "count",
            "model": "crm.lead",
            "field_date": "date_closed",
            "domain": "[('stage_id.is_won', '=', True)]",
            "batch_field": "user_id",
        },
        "target": 12,
    },
    {
        "name": "Machine à appels",
        "description": "Compléter 50 appels CRM par jour (activités Call terminées).",
        "period": "daily",
        "badge_name": "Machine à appels",
        "badge_description": "50 appels en une journée — rythme de feu !",
        "goal": {
            "def_name": "Intellix — Appels CRM complétés",
            "def_description": (
                "Activités mail.activity de type Call archivées (terminées). "
                "Les appels VICIdial sont aussi dans pe.call.log si intégrés."
            ),
            "computation_mode": "count",
            "model": "mail.activity",
            "field_date": "date_done",
            "domain": "[('active', '=', False)]",
            "batch_field": "user_id",
            "activity_type_xmlid": "mail.mail_activity_data_call",
        },
        "target": 50,
    },
    {
        "name": "Score Elite",
        "description": "Atteindre un score People Engine global ≥ 85 sur le mois.",
        "period": "monthly",
        "badge_name": "Elite Performer",
        "badge_description": "Score People Engine ≥ 85 — performer d'élite.",
        "goal": {
            "def_name": "Intellix — Score PE global",
            "def_description": (
                "Score global People Engine (pe.employee.profile.score_global). "
                "Le champ n'existe pas sur hr.employee natif."
            ),
            "computation_mode": "sum",
            "model": "pe.employee.profile",
            "field": "score_global",
            "domain": "[]",
            "batch_field": "user_id",
        },
        "target": 85,
    },
]


def read_password() -> str:
    pwd = os.environ.get("ODOO_PASSWORD", "").strip()
    if pwd:
        return pwd
    raise SystemExit(
        "ODOO_PASSWORD is required (res.users login password).\n"
        "admin_passwd in odoo-server.conf is the DB master password, not a user login.\n"
        "Example: ODOO_USERNAME=root ODOO_PASSWORD='***' python3 %s" % __file__
    )


class OdooEnv:
    """Adapter for odoo-bin shell ``env``."""

    def __init__(self, env) -> None:
        self.env = env

    def search(self, model: str, domain: list, limit: int | None = None) -> list[int]:
        return self.env[model].search(domain, limit=limit or 0).ids

    def search_read(
        self, model: str, domain: list, fields: list[str], limit: int | None = None
    ) -> list[dict]:
        return self.env[model].search_read(domain, fields, limit=limit or 0)

    def create(self, model: str, vals: dict) -> int:
        return self.env[model].create(vals).id

    def write(self, model: str, ids: list[int], vals: dict) -> bool:
        self.env[model].browse(ids).write(vals)
        return True

    def xmlid_to_res_id(self, xmlid: str) -> int | None:
        rec = self.env.ref(xmlid, raise_if_not_found=False)
        return rec.id if rec else None

    def get_model_id(self, model: str) -> int:
        return self.env["ir.model"]._get(model).id

    def get_field_id(self, model: str, field_name: str) -> int | None:
        field = self.env["ir.model.fields"]._get(model, field_name)
        return field.id if field else None

    def get_report_template_id(self) -> int:
        tpl = self.env.ref("gamification.simple_report_template", raise_if_not_found=False)
        if tpl:
            return tpl.id
        recs = self.search_read(
            "mail.template",
            [("model", "=", "gamification.challenge")],
            ["id"],
            limit=1,
        )
        if recs:
            return recs[0]["id"]
        raise RuntimeError("No gamification report template found")


class OdooRPC(OdooEnv):
    def __init__(self, url: str, db: str, username: str, password: str):
        self.url = url.rstrip("/")
        self.db = db
        self.username = username
        self.password = password
        common = xmlrpc.client.ServerProxy(f"{self.url}/xmlrpc/2/common")
        self.uid = common.authenticate(db, username, password, {})
        if not self.uid:
            raise SystemExit(
                f"Authentication failed for {username}@{db}. "
                "Try ODOO_USERNAME=root on this instance."
            )
        self.models = xmlrpc.client.ServerProxy(f"{self.url}/xmlrpc/2/object")

    def search(self, model: str, domain: list, limit: int | None = None) -> list[int]:
        kwargs: dict[str, Any] = {}
        if limit is not None:
            kwargs["limit"] = limit
        return self.models.execute_kw(
            self.db, self.uid, self.password, model, "search", [domain], kwargs
        )

    def search_read(
        self, model: str, domain: list, fields: list[str], limit: int | None = None
    ) -> list[dict]:
        kwargs: dict[str, Any] = {"fields": fields}
        if limit is not None:
            kwargs["limit"] = limit
        return self.models.execute_kw(
            self.db, self.uid, self.password, model, "search_read", [domain], kwargs
        )

    def create(self, model: str, vals: dict) -> int:
        return self.models.execute_kw(
            self.db, self.uid, self.password, model, "create", [vals]
        )

    def write(self, model: str, ids: list[int], vals: dict) -> bool:
        return self.models.execute_kw(
            self.db, self.uid, self.password, model, "write", [ids, vals]
        )

    def xmlid_to_res_id(self, xmlid: str) -> int | None:
        recs = self.search_read(
            "ir.model.data",
            [
                ("module", "=", xmlid.split(".")[0]),
                ("name", "=", xmlid.split(".")[1]),
            ],
            ["res_id"],
            limit=1,
        )
        return recs[0]["res_id"] if recs else None

    def get_model_id(self, model: str) -> int:
        recs = self.search_read("ir.model", [("model", "=", model)], ["id"], limit=1)
        if not recs:
            raise RuntimeError(f"Model not found: {model}")
        return recs[0]["id"]

    def get_field_id(self, model: str, field_name: str) -> int | None:
        recs = self.search_read(
            "ir.model.fields",
            [("model", "=", model), ("name", "=", field_name)],
            ["id"],
            limit=1,
        )
        return recs[0]["id"] if recs else None


def get_sales_user_ids(odoo) -> list[int]:
    group_id = odoo.xmlid_to_res_id(SALES_GROUP_XMLID)
    if not group_id:
        raise RuntimeError(f"Group not found: {SALES_GROUP_XMLID}")
    users = odoo.search_read(
        "res.users",
        [
            ("all_group_ids", "in", [group_id]),
            ("active", "=", True),
            ("share", "=", False),
        ],
        ["id", "login", "name"],
    )
    return [u["id"] for u in users]


def get_or_create_badge(odoo, name: str, description: str) -> tuple[int, str]:
    existing = odoo.search_read(
        "gamification.badge", [("name", "=", name)], ["id"], limit=1
    )
    vals = {
        "description": f"<p>{description}</p>",
        "rule_auth": "nobody",
        "rule_max": True,
        "rule_max_number": 1,
        "active": True,
    }
    if existing:
        odoo.write("gamification.badge", [existing[0]["id"]], vals)
        return existing[0]["id"], "exists"
    badge_id = odoo.create(
        "gamification.badge",
        {"name": name, **vals},
    )
    return badge_id, "created"


def get_or_create_goal_definition(odoo, spec: dict) -> tuple[int, str]:
    def_name = spec["def_name"]
    existing = odoo.search_read(
        "gamification.goal.definition",
        [("name", "=", def_name)],
        ["id"],
        limit=1,
    )
    if existing:
        return existing[0]["id"], "exists"

    domain = spec.get("domain", "[]")
    if spec.get("activity_type_xmlid"):
        call_type_id = odoo.xmlid_to_res_id(spec["activity_type_xmlid"])
        if not call_type_id:
            raise RuntimeError("Activity type not found: %s" % spec["activity_type_xmlid"])
        domain = "[('active', '=', False), ('activity_type_id', '=', %d)]" % call_type_id

    vals: dict[str, Any] = {
        "name": def_name,
        "description": spec.get("def_description", ""),
        "computation_mode": spec["computation_mode"],
        "condition": spec.get("condition", "higher"),
        "display_mode": spec.get("display_mode", "progress"),
        "domain": domain,
    }

    model = spec["model"]
    vals["model_id"] = odoo.get_model_id(model)
    if spec.get("field_date"):
        fid = odoo.get_field_id(model, spec["field_date"])
        if fid:
            vals["field_date_id"] = fid
    if spec.get("field"):
        fid = odoo.get_field_id(model, spec["field"])
        if not fid:
            raise RuntimeError(f"Field {model}.{spec['field']} not found")
        vals["field_id"] = fid
    if spec.get("batch_field"):
        bf = odoo.get_field_id(model, spec["batch_field"])
        if not bf:
            raise RuntimeError(f"Batch field {model}.{spec['batch_field']} not found")
        vals["batch_mode"] = True
        vals["batch_distinctive_field"] = bf
        vals["batch_user_expression"] = "user.id"

    def_id = odoo.create("gamification.goal.definition", vals)
    return def_id, "created"


def get_or_create_challenge(
    odoo,
    spec: dict,
    def_id: int,
    badge_id: int,
    user_ids: list[int],
    report_template_id: int,
) -> tuple[int, str]:
    name = spec["name"]
    existing = odoo.search_read(
        "gamification.challenge",
        [("name", "=", name)],
        ["id", "state"],
        limit=1,
    )

    group_id = odoo.xmlid_to_res_id(SALES_GROUP_XMLID)
    user_domain = str(
        [
            ("all_group_ids", "in", [group_id]),
            ("active", "=", True),
            ("share", "=", False),
        ]
    )

    base_vals = {
        "description": spec.get("description", ""),
        "period": spec["period"],
        "visibility_mode": "personal",
        "report_message_frequency": "never",
        "challenge_category": "hr",
        "user_domain": user_domain,
        "reward_id": badge_id,
        "reward_realtime": True,
        "report_template_id": report_template_id,
        "state": "inprogress",
    }

    if existing:
        ch_id = existing[0]["id"]
        odoo.write(
            "gamification.challenge",
            [ch_id],
            {**base_vals, "user_ids": [(6, 0, user_ids)]},
        )
        lines = odoo.search(
            "gamification.challenge.line",
            [("challenge_id", "=", ch_id)],
            limit=1,
        )
        line_vals = {"definition_id": def_id, "target_goal": spec["target"]}
        if lines:
            odoo.write("gamification.challenge.line", lines, line_vals)
        else:
            odoo.write(
                "gamification.challenge",
                [ch_id],
                {"line_ids": [(0, 0, line_vals)]},
            )
        return ch_id, "exists"

    ch_id = odoo.create(
        "gamification.challenge",
        {
            "name": name,
            "line_ids": [(0, 0, {"definition_id": def_id, "target_goal": spec["target"]})],
            "user_ids": [(6, 0, user_ids)],
            **base_vals,
        },
    )
    return ch_id, "created"


def run_setup(odoo) -> tuple[list[dict], list[dict], list[int]]:
    """Idempotent setup. Returns (results, errors, user_ids)."""
    user_ids = get_sales_user_ids(odoo)
    print(
        "Sales group (%s / «User: Own Documents Only»): %d active users"
        % (SALES_GROUP_XMLID, len(user_ids))
    )
    report_template_id = odoo.get_report_template_id()
    results: list[dict] = []
    errors: list[dict] = []

    for spec in CHALLENGES:
        ch_name = spec["name"]
        try:
            badge_id, badge_status = get_or_create_badge(
                odoo, spec["badge_name"], spec["badge_description"]
            )
            def_id, def_status = get_or_create_goal_definition(odoo, spec["goal"])
            ch_id, ch_status = get_or_create_challenge(
                odoo, spec, def_id, badge_id, user_ids, report_template_id
            )
            row = {
                "challenge": ch_name,
                "challenge_id": ch_id,
                "challenge_status": ch_status,
                "period": spec["period"],
                "badge": spec["badge_name"],
                "badge_id": badge_id,
                "badge_status": badge_status,
                "goal_def_id": def_id,
                "goal_def_status": def_status,
                "target": spec["target"],
            }
            results.append(row)
            print(
                "  OK  %s: challenge=%s (%s), badge=%s (%s), goal_def=%s (%s)"
                % (ch_name, ch_id, ch_status, badge_id, badge_status, def_id, def_status)
            )
        except Exception as exc:
            errors.append({"challenge": ch_name, "error": str(exc)})
            print("  ERR %s: %s" % (ch_name, exc))

    print("\n=== SUMMARY ===")
    print("Challenges processed: %d/%d" % (len(results), len(CHALLENGES)))
    print("Assigned users: %d" % len(user_ids))
    if errors:
        print("Errors: %d" % len(errors))
        for e in errors:
            print("  - %s: %s" % (e["challenge"], e["error"]))
    return results, errors, user_ids


def main() -> int:
    password = read_password()
    odoo = OdooRPC(URL, DB, USERNAME, password)
    print("Connected to %s / %s as uid=%s" % (URL, DB, odoo.uid))
    _, errors, _ = run_setup(odoo)
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
