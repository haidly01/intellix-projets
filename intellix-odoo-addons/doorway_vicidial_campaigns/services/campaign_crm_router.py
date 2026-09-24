# -*- coding: utf-8 -*-
"""Route Vicidial CQMTG01 / DW_QCB2B / ITEXQC01 vers le bon modèle Odoo.

CQMTG01 / Rosalie → coins.quebec.partenariat (voyageur seulement si dit).
DW_QCB2B / Alex → crm.lead équipe Driven (94). Jamais Coins Marocain / Sales.
ITEXQC01 / Alex ITEX → crm.lead équipe ITEX (112). Jamais Coins / Driven.
"""
import logging
import re
from datetime import timedelta

from odoo import fields

_logger = logging.getLogger(__name__)

CQ_CAMPAIGNS = {"CQMTG01", "INBOUND_QC"}
DRIVEN_CAMPAIGNS = {"DW_QCB2B", "DW_DRIVN", "INBOUND_DRIVEN", "DW_DRIVN_RELANCE"}
ITEX_CAMPAIGNS = {"ITEXQC01", "GARQC01"}
COINS_MAROC_TEAM_NAMES = ("Coins Marocain",)
LIST_TYPE = {
    9005002: "hebergement",
    9005003: "spa",
    9005004: "resto",
    9005001: "activite",
}
CAT_TYPE = {
    "hebergement": "hebergement",
    "restauration": "resto",
    "resto": "resto",
    "bienetre": "spa",
    "spa": "spa",
    "activites": "activite",
    "activite": "activite",
}


def _digits(value, tail=10):
    digits = re.sub(r"\D", "", value or "")
    return digits[-tail:] if digits else ""


class CampaignCrmRouter:
    def __init__(self, env):
        self.env = env

    def route(self, data, dry_run=False):
        data = data or {}
        campaign = (
            data.get("campaign") or data.get("campaign_id") or ""
        ).strip().upper()
        if campaign in CQ_CAMPAIGNS or self._is_rosalie(data):
            return self.route_rosalie(data, dry_run=dry_run)
        if campaign in ITEX_CAMPAIGNS or self._is_itex(data):
            return self.route_itex(data, dry_run=dry_run)
        if campaign in DRIVEN_CAMPAIGNS or self._is_alex(data):
            return self.route_driven(data, dry_run=dry_run)
        return {
            "ok": False,
            "error": "unmapped_campaign",
            "campaign": campaign,
        }

    def _is_rosalie(self, data):
        agent = (data.get("agent_id") or data.get("agent_name") or "").lower()
        slug = (data.get("odoo_slug") or "").lower()
        return "rosalie" in agent or slug == "rosalie-coins-quebec"

    def _is_alex(self, data):
        agent = (data.get("agent_id") or data.get("agent_name") or "").lower()
        slug = (data.get("odoo_slug") or "").lower()
        return slug == "driven-b2b" or agent.startswith("agent_driven")

    def _is_itex(self, data):
        agent = (data.get("agent_id") or data.get("agent_name") or "").lower()
        slug = (data.get("odoo_slug") or "").lower()
        return (
            slug == "itex-qc"
            or agent.startswith("agent_1101")
            or agent.startswith("agent_itex")
        )

    def _is_voyageur(self, data):
        target = (data.get("target_model") or data.get("model") or "").strip()
        fiche = (data.get("fiche_type") or data.get("type_fiche") or "").strip().lower()
        return (
            target == "coins.quebec.voyageur"
            or fiche in ("voyageur", "traveler", "voyageurs")
        )

    def _martin_user(self):
        Users = self.env["res.users"].sudo()
        user = Users.search([("login", "=", "martin@agencedoorway.com")], limit=1)
        if user:
            return user
        user = Users.search([("login", "ilike", "martin@")], limit=1)
        if user:
            return user
        return Users.browse()

    def _michel_user(self):
        return (
            self.env["res.users"]
            .sudo()
            .search([("login", "=", "michel@coinsquebec.com")], limit=1)
        )

    def _activity_user(self, preferred=None):
        if preferred and preferred.exists():
            return preferred
        return self._michel_user() or self._martin_user() or self.env.user

    def _activity_type(self):
        return self.env.ref("mail.mail_activity_data_call", raise_if_not_found=False)

    def _schedule_activity(self, record, summary, note, days=1, user=None, dry_run=False):
        act_type = self._activity_type()
        if not act_type:
            return False
        deadline = fields.Date.today() + timedelta(days=days)
        while deadline.weekday() >= 5:
            deadline += timedelta(days=1)
        user = self._activity_user(user)
        vals = {
            "res_model": record._name,
            "res_id": record.id,
            "activity_type_id": act_type.id,
            "summary": summary,
            "note": note,
            "date_deadline": deadline,
            "user_id": user.id,
        }
        if dry_run:
            return {"dry_run": True, **{k: vals[k] for k in vals if k != "note"}, "note": (note or "")[:200]}
        self.env["mail.activity"].sudo().create(vals)
        return True

    def _phone(self, data):
        return (
            data.get("telephone")
            or data.get("phone")
            or data.get("phone_number")
            or data.get("caller_id")
            or ""
        ).strip()

    def _etablissement(self, data):
        return (
            data.get("etablissement")
            or data.get("first_name")
            or data.get("nom")
            or data.get("name")
            or data.get("entreprise")
            or ""
        ).strip()

    def _contact_name(self, data):
        return (
            data.get("last_name")
            or data.get("contact_name")
            or data.get("prenom")
            or ""
        ).strip()

    def _type_partenaire(self, data):
        cat = (data.get("vendor_lead_code") or data.get("categorie") or "").strip().lower()
        if cat in CAT_TYPE:
            return CAT_TYPE[cat]
        try:
            list_id = int(data.get("list_id") or 0)
        except (TypeError, ValueError):
            list_id = 0
        return LIST_TYPE.get(list_id, "resto")

    def _find_partenariat(self, phone, name):
        Part = self.env["coins.quebec.partenariat"].sudo()
        tail = _digits(phone)
        if tail:
            for rec in Part.search([("phone", "!=", False)]):
                if _digits(rec.phone) == tail:
                    return rec
        if name:
            rec = Part.search([("name", "=ilike", name)], limit=1)
            if rec:
                return rec
        return Part.browse()

    def _find_voyageur(self, phone, name):
        Voy = self.env["coins.quebec.voyageur"].sudo()
        tail = _digits(phone)
        if tail:
            for rec in Voy.search([("phone", "!=", False)]):
                if _digits(rec.phone) == tail:
                    return rec
        if name:
            rec = Voy.search([("name", "=ilike", name)], limit=1)
            if rec:
                return rec
        return Voy.browse()

    def _is_qualified(self, data):
        action = (data.get("crm_action") or "").strip()
        disp = (data.get("disposition") or data.get("statut") or "").upper()
        return bool(
            data.get("qualified")
            or data.get("lead_ganador")
            or data.get("positif_gate_passed")
            or action in ("tag_lead_qualifie", "assign_martin_review")
            or disp in ("INTERESTED", "TRANSFER", "VENTE", "QUALIFIE")
        )

    def _wants_rappel(self, data):
        disp = (data.get("disposition") or data.get("statut") or "").upper()
        action = (data.get("crm_action") or "").strip()
        return bool(
            self._is_qualified(data)
            or disp in ("CALLBACK", "RAPPEL", "CALLBK")
            or action in ("assign_martin_review",)
            or data.get("interesse_sans_creneau")
        )

    def route_rosalie(self, data, dry_run=False):
        if "coins.quebec.partenariat" not in self.env:
            return {"ok": False, "error": "coins_quebec_missing"}
        phone = self._phone(data)
        name = self._etablissement(data) or ("Établissement %s" % (phone or "CQ"))
        contact = self._contact_name(data)
        voyageur = self._is_voyageur(data)
        qualified = self._is_qualified(data)
        note = self._rosalie_note(data, name, contact)
        if voyageur:
            rec = self._find_voyageur(phone, name)
            model = "coins.quebec.voyageur"
            vals = {
                "name": name[:128],
                "phone": phone,
                "region": "monteregie",
                "stage": "contacte" if qualified else "nouveau",
            }
        else:
            rec = self._find_partenariat(phone, name)
            model = "coins.quebec.partenariat"
            vals = {
                "name": name[:128],
                "contact_name": contact or False,
                "phone": phone,
                "type_partenaire": self._type_partenaire(data),
                "region": "monteregie",
                "source": "manuel",
                "stage": "contacte" if (rec or qualified) else "nouveau",
            }
            if rec and rec.stage == "nouveau":
                vals["stage"] = "contacte"
        created = not rec
        if (
            not rec
            and not qualified
            and not self._wants_rappel(data)
            and not dry_run
        ):
            return {
                "ok": True,
                "skipped": True,
                "reason": "no_existing_and_not_qualified",
                "target_model": model,
            }
        if dry_run:
            result = {
                "ok": True,
                "dry_run": True,
                "target_model": model,
                "action": "create" if created else "update",
                "record_id": rec.id if rec else False,
                "vals": vals,
                "team": "coins.quebec — jamais crm.lead",
            }
            if self._wants_rappel(data):
                result["rappel"] = {
                    "summary": "Rappel Rosalie — %s" % name,
                    "res_model": model,
                }
            return result
        Model = self.env[model].sudo()
        if rec:
            write_vals = {k: v for k, v in vals.items() if k != "name" or not rec.name}
            if rec.stage == "nouveau":
                write_vals["stage"] = "contacte"
            rec.write(write_vals)
        else:
            rec = Model.create(vals)
        rec.message_post(body=note.replace("\n", "<br/>"))
        activity = False
        if self._wants_rappel(data):
            activity = self._schedule_activity(
                rec,
                "Rappel Rosalie — %s" % rec.name,
                note,
                user=self._michel_user() or self._martin_user(),
            )
        return {
            "ok": True,
            "target_model": model,
            "action": "create" if created else "update",
            "record_id": rec.id,
            "activity_created": bool(activity),
            "qualified": qualified,
        }

    def _rosalie_note(self, data, name, contact):
        return "\n".join(
            [
                "Rosalie · Coins Québec · CQMTG01",
                "Établissement: %s" % (name or "—"),
                "Contact: %s" % (contact or "—"),
                "Disposition: %s" % (data.get("disposition") or "—"),
                "Durée: %ss" % (data.get("duration_seconds") or data.get("duration_sec") or 0),
                "Appel: %s" % (data.get("call_sid") or "—"),
                (data.get("lead_note") or ""),
                (data.get("transcript") or "")[:800],
            ]
        )

    def _driven_team(self):
        team = self.env.ref(
            "renovation_conciergerie.crm_team_driven", raise_if_not_found=False
        )
        if team:
            return team
        return self.env["crm.team"].sudo().search([("name", "=", "Driven")], limit=1)

    def _blocked_team_ids(self):
        names = (
            "Coins Marocain",
            "Coins Québec",
            "Coins Québec — Partenariats",
            "Coins Québec — Voyageurs",
            "Coins — Voyageurs",
        )
        return self.env["crm.team"].sudo().search([("name", "in", names)]).ids

    def _find_driven_lead(self, phone, partner):
        Lead = self.env["crm.lead"].sudo()
        team = self._driven_team()
        blocked = self._blocked_team_ids()
        tail = _digits(phone)
        domain = [("team_id", "=", team.id)] if team else []
        if tail:
            phone_domain = [("phone", "ilike", tail)]
            if "mobile" in Lead._fields:
                phone_domain = ["|", ("mobile", "ilike", tail)] + phone_domain
            recs = Lead.search(
                domain + phone_domain,
                order="id desc",
                limit=8,
            )
            for rec in recs:
                if rec.team_id.id in blocked:
                    continue
                rec_mobile = rec.mobile if "mobile" in Lead._fields else ""
                if _digits(rec.phone) == tail or _digits(rec_mobile) == tail:
                    return rec
        if partner:
            rec = Lead.search(
                domain + [("partner_id", "=", partner.id)],
                order="id desc",
                limit=1,
            )
            if rec and rec.team_id.id not in blocked:
                return rec
        return Lead.browse()

    def route_driven(self, data, dry_run=False):
        from odoo.addons.doorway_agents_dashboard.services.driven_b2b_service import (
            DrivenB2bService,
        )

        svc = DrivenB2bService(self.env)
        if dry_run:
            team = self._driven_team()
            phone = self._phone(data)
            lead = self._find_driven_lead(phone, None)
            qualified = self._is_qualified(data)
            return {
                "ok": True,
                "dry_run": True,
                "target_model": "crm.lead",
                "team_id": team.id if team else False,
                "team_name": team.name if team else False,
                "action": "create" if not lead else "update",
                "lead_id": lead.id if lead else False,
                "finance_funnel_stage": (
                    "interest_confirmed" if qualified else "lead_contacted"
                ),
                "blocked_teams": self._blocked_team_ids(),
            }
        if self._is_qualified(data) or data.get("crm_action") == "tag_lead_chaud_driven":
            return svc.process_qualified(data)
        # CALLBK même sans qualif → lead Driven + rappel Finance.
        if self._wants_rappel(data):
            return svc.process_callback(data)
        if data.get("crm_action"):
            return svc.process_non_qualified(data)
        return svc.process_post_call(data)

    def _itex_team(self):
        team = self.env.ref(
            "intellix_finance.crm_team_itex", raise_if_not_found=False
        )
        if team:
            return team
        return self.env["crm.team"].sudo().search([("name", "=", "ITEX")], limit=1)

    def _find_itex_lead(self, phone, partner):
        Lead = self.env["crm.lead"].sudo().with_context(active_test=False)
        team = self._itex_team()
        tail = _digits(phone)
        test = Lead.browse(2127)
        if (
            test.exists()
            and "[TEST] Appel ITEX" in (test.name or "")
            and tail
            and tail == _digits(test.phone or test.mobile or "")
        ):
            return test
        domain = [("team_id", "=", team.id)] if team else []
        if tail:
            phone_domain = [("phone", "ilike", tail)]
            if "mobile" in Lead._fields:
                phone_domain = ["|", ("mobile", "ilike", tail)] + phone_domain
            recs = Lead.search(domain + phone_domain, order="id desc", limit=8)
            for rec in recs:
                rec_mobile = rec.mobile if "mobile" in Lead._fields else ""
                if _digits(rec.phone) == tail or _digits(rec_mobile) == tail:
                    return rec
        if partner:
            rec = Lead.search(
                domain + [("partner_id", "=", partner.id)],
                order="id desc",
                limit=1,
            )
            if rec:
                return rec
        return Lead.browse()

    def route_itex(self, data, dry_run=False):
        """Alex ITEX → crm.lead équipe 112. Jamais Coins / Driven / Sales."""
        team = self._itex_team()
        if not team:
            return {"ok": False, "error": "itex_team_missing"}
        phone = self._phone(data)
        name = self._etablissement(data) or ("Entreprise ITEX %s" % (phone or ""))
        lead = self._find_itex_lead(phone, None)
        qualified = self._is_qualified(data)
        martin = self._martin_user()
        stage = "interet_confirme" if qualified else (
            "pitch_fait" if (lead or data.get("disposition")) else "nouveau"
        )
        vals = {
            "name": lead.name if lead and lead.name else ("Alex ITEX — %s" % name[:80]),
            "phone": phone or (lead.phone if lead else False),
            "team_id": team.id,
            "type": "opportunity",
            "user_id": (lead.user_id.id if lead and lead.user_id else None)
            or (martin.id if martin else False),
        }
        Lead = self.env["crm.lead"].sudo()
        if "itex_funnel_stage" in Lead._fields:
            vals["itex_funnel_stage"] = stage
        if "coins_fiche_type" in Lead._fields:
            vals["coins_fiche_type"] = False
        if dry_run:
            return {
                "ok": True,
                "dry_run": True,
                "target_model": "crm.lead",
                "team_id": team.id,
                "team_name": team.name,
                "action": "create" if not lead else "update",
                "lead_id": lead.id if lead else False,
                "itex_funnel_stage": stage,
            }
        ctx = {
            "finance_pipeline": "itex",
            "default_team_id": team.id,
            "default_itex_funnel_stage": stage,
        }
        created = not lead
        if lead:
            lead.with_context(**ctx).write(vals)
        else:
            lead = Lead.with_context(**ctx).create(vals)
        note = "\n".join(
            [
                "Alex ITEX · ITEXQC01",
                "Disposition: %s" % (data.get("disposition") or "—"),
                "Durée: %ss" % (data.get("duration_seconds") or data.get("duration_sec") or 0),
                "Appel: %s" % (data.get("call_sid") or "—"),
                (data.get("lead_note") or ""),
                (data.get("transcript") or "")[:800],
            ]
        )
        lead.message_post(body=note.replace("\n", "<br/>"))
        if self._wants_rappel(data) and hasattr(lead, "finance_set_alex_callback"):
            lead.finance_set_alex_callback(
                comment=data.get("callback_when") or data.get("comment") or "CALLBK Alex ITEX",
                source="alex_itex",
            )
        return {
            "ok": True,
            "target_model": "crm.lead",
            "action": "create" if created else "update",
            "record_id": lead.id,
            "team_id": team.id,
            "qualified": qualified,
        }
