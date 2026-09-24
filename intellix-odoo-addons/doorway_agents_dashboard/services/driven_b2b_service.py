# -*- coding: utf-8 -*-
"""Post-appel Alex — qualification Driven B2B PME QC."""
import logging
import re
from datetime import timedelta

from odoo import fields

_logger = logging.getLogger(__name__)

SMS_FOLLOWUP_DAYS = (2, 5)


def _digits(value, tail=10):
    digits = re.sub(r"\D", "", value or "")
    return digits[-tail:] if digits else ""


class DrivenB2bService:
    def __init__(self, env):
        self.env = env

    def _tag(self, name):
        Tag = self.env["crm.tag"].sudo()
        tag = Tag.search([("name", "=", name)], limit=1)
        if not tag:
            tag = Tag.create({"name": name})
        return tag

    def _partner_category(self, name):
        Cat = self.env["res.partner.category"].sudo()
        cat = Cat.search([("name", "=", name)], limit=1)
        if not cat:
            cat = Cat.create({"name": name})
        return cat

    def _driven_team(self):
        team = self.env.ref(
            "renovation_conciergerie.crm_team_driven", raise_if_not_found=False
        )
        if team:
            return team
        return self.env["crm.team"].sudo().search([("name", "=", "Driven")], limit=1)

    def _martin_user(self):
        user = (
            self.env["res.users"]
            .sudo()
            .search([("login", "=", "martin@agencedoorway.com")], limit=1)
        )
        if user:
            return user
        user = (
            self.env["res.users"]
            .sudo()
            .search([("login", "ilike", "martin%")], limit=1)
        )
        if user:
            return user
        return self.env["crm.lead"].sudo()._doorway_martin_transfer_user()

    def _partner_from_payload(self, data):
        Partner = self.env["res.partner"].sudo()
        pid = int(data.get("partner_id") or data.get("contact_id") or 0)
        if pid:
            p = Partner.browse(pid)
            if p.exists():
                return p
        phone = (data.get("telephone") or data.get("phone") or "").strip()
        digits = "".join(c for c in phone if c.isdigit())[-10:]
        if digits:
            p = Partner.search([("phone", "ilike", digits)], limit=1)
            if p:
                return p
        name = (
            data.get("nom")
            or data.get("name")
            or data.get("prenom")
            or data.get("entreprise")
            or "Contact B2B QC"
        ).strip()
        return Partner.create(
            {
                "name": name[:128],
                "phone": phone or digits,
                "is_company": True,
                "category_id": [(4, self._partner_category("B2B Brut").id)],
            }
        )

    def _find_driven_lead(self, phone, partner):
        Lead = self.env["crm.lead"].sudo()
        team = self._driven_team()
        if not team:
            return Lead.browse()
        tail = _digits(phone)
        domain = [("team_id", "=", team.id)]
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

    def _schedule_rappel(self, lead, data):
        act_type = self.env.ref(
            "mail.mail_activity_data_call", raise_if_not_found=False
        )
        if not act_type or not lead:
            return False
        deadline = fields.Date.today() + timedelta(days=1)
        while deadline.weekday() >= 5:
            deadline += timedelta(days=1)
        existing = self.env["mail.activity"].sudo().search(
            [
                ("res_model", "=", "crm.lead"),
                ("res_id", "=", lead.id),
                ("activity_type_id", "=", act_type.id),
                ("date_deadline", ">=", fields.Date.today()),
            ],
            limit=1,
        )
        comment = (
            data.get("callback_when")
            or data.get("comment")
            or data.get("lead_note")
            or "CALLBK Alex Driven"
        )
        when = fields.Datetime.to_datetime("%s 10:00:00" % deadline)
        if hasattr(lead, "finance_set_alex_callback"):
            lead.finance_set_alex_callback(
                when=when,
                comment=comment,
                source="alex_driven",
            )
        if existing:
            return True
        self.env["mail.activity"].sudo().create(
            {
                "res_model": "crm.lead",
                "res_id": lead.id,
                "activity_type_id": act_type.id,
                "summary": "Rappel Alex Driven — %s" % (lead.name or ""),
                "note": (data.get("transcript") or data.get("lead_note") or "")[:800],
                "date_deadline": deadline,
                "user_id": lead.user_id.id or self._martin_user().id,
            }
        )
        return True

    def _record_metrics(self, data, partner=None, lead=None):
        try:
            Metric = self.env["lea.qc.sample.call"].sudo()
        except KeyError:
            return
        payload = dict(data or {})
        payload.setdefault("campaign", "DW_QCB2B")
        payload.setdefault("agent_id", "driven-b2b-qc-2026")
        try:
            Metric.register_call_ended(payload)
            rec = Metric.search(
                [("call_sid", "=", (payload.get("call_sid") or "").strip())], limit=1
            )
            if rec:
                vals = {"campaign": "DW_QCB2B", "agent_id": "driven-b2b-qc-2026"}
                if partner and partner.id and not rec.partner_id:
                    vals["partner_id"] = partner.id
                if lead and lead.id and not rec.lead_id:
                    vals["lead_id"] = lead.id
                rec.write(vals)
        except Exception as exc:
            _logger.warning("Driven B2B metrics skip: %s", exc)

    def _schedule_sms_followups(self, partner, prenom, phone):
        try:
            Queue = self.env["driven.b2b.sms.queue"].sudo()
        except KeyError:
            return
        base = fields.Datetime.now()
        for day in SMS_FOLLOWUP_DAYS:
            variant = "j2" if day == 2 else "j5"
            Queue.create(
                {
                    "partner_id": partner.id,
                    "phone": phone,
                    "prenom": prenom or partner.name.split()[0] if partner.name else "",
                    "variant": variant,
                    "scheduled_at": base + timedelta(days=day),
                    "state": "pending",
                }
            )

    def process_qualified(self, data):
        data = data or {}
        partner = self._partner_from_payload(data)
        phone = data.get("telephone") or partner.phone or partner.mobile
        prenom = data.get("prenom") or (partner.name or "").split()[0]
        hot = data.get("crm_action") == "tag_lead_chaud_driven" or data.get("hot_lead")
        team = self._driven_team()
        if not team:
            _logger.error("Driven B2B: équipe Driven introuvable — pas d'écriture CRM")
            return {"ok": False, "error": "driven_team_missing"}

        tags = [self._tag("Driven B2B")]
        if hot:
            tags.append(self._tag("Lead chaud Driven"))

        Lead = self.env["crm.lead"].sudo()
        lead = self._find_driven_lead(phone, partner)
        vals = {
            "name": "Alex Driven — %s" % partner.name,
            "partner_id": partner.id,
            "phone": phone,
            "user_id": self._martin_user().id,
            "team_id": team.id,
            "type": "opportunity",
            "priority": "3" if hot else "1",
            "tag_ids": [(4, t.id) for t in tags],
            "description": (
                "Qualifié Alex Driven B2B\n"
                "Ancienneté (mois): %s\nRevenus 100k+: %s\nCompte entreprise: %s\n\n%s"
            )
            % (
                data.get("anciennete_mois") or "—",
                data.get("revenus_100k") or "—",
                data.get("compte_entreprise") or "—",
                (data.get("transcript") or "")[:800],
            ),
        }
        if "finance_funnel_stage" in Lead._fields:
            vals["finance_funnel_stage"] = (
                "interest_confirmed" if (data.get("qualified") or hot) else "lead_contacted"
            )
        if lead:
            lead.write(vals)
        else:
            lead = Lead.create(vals)

        partner.write({"category_id": [(4, self._partner_category("Appelé Alex Driven").id)]})
        if data.get("trigger_sms") or data.get("sms_sent") is not False:
            self._schedule_sms_followups(partner, prenom, phone)
        self._schedule_rappel(lead, data)

        self._record_metrics(data, partner=partner, lead=lead)
        return {
            "ok": True,
            "partner_id": partner.id,
            "lead_id": lead.id,
            "team_id": team.id,
            "hot_lead": hot,
        }

    def process_non_qualified(self, data):
        data = data or {}
        partner = self._partner_from_payload(data)
        action = data.get("crm_action") or ""
        if action == "tag_dnc":
            partner.write({"category_id": [(4, self._partner_category("DNC").id)]})
        elif action.startswith("tag_disqualifie"):
            partner.write(
                {"category_id": [(4, self._partner_category("Disqualifié Driven").id)]}
            )
        self._record_metrics(data, partner=partner)
        return {"ok": True, "partner_id": partner.id, "action": action}

    def process_callback(self, data):
        """CALLBK Alex → crm.lead Driven + rappel Finance, même sans qualification."""
        data = data or {}
        partner = self._partner_from_payload(data)
        phone = data.get("telephone") or partner.phone or partner.mobile
        team = self._driven_team()
        if not team:
            _logger.error("Driven B2B: équipe Driven introuvable — pas de CALLBK CRM")
            return {"ok": False, "error": "driven_team_missing"}
        Lead = self.env["crm.lead"].sudo()
        lead = self._find_driven_lead(phone, partner)
        vals = {
            "name": "Alex Driven — %s" % partner.name,
            "partner_id": partner.id,
            "phone": phone,
            "user_id": self._martin_user().id,
            "team_id": team.id,
            "type": "opportunity",
        }
        if "finance_funnel_stage" in Lead._fields and not (
            lead and lead.finance_funnel_stage
        ):
            vals["finance_funnel_stage"] = "lead_contacted"
        if lead:
            write_vals = {k: v for k, v in vals.items() if k != "name" or not lead.name}
            lead.write(write_vals)
        else:
            lead = Lead.create(vals)
        self._schedule_rappel(lead, data)
        self._record_metrics(data, partner=partner, lead=lead)
        return {
            "ok": True,
            "partner_id": partner.id,
            "lead_id": lead.id,
            "callback": True,
        }

    def process_post_call(self, data):
        data = data or {}
        self._record_metrics(data)
        action = data.get("crm_action") or ""
        if action in ("tag_lead_chaud_driven", "tag_lead_qualifie") or data.get(
            "trigger_sms"
        ) or data.get("qualified"):
            return self.process_qualified(data)
        disp = (data.get("disposition") or data.get("statut") or "").upper()
        if disp in ("CALLBACK", "RAPPEL", "CALLBK") or data.get("interesse_sans_creneau"):
            return self.process_callback(data)
        if action:
            return self.process_non_qualified(data)
        partner = self._partner_from_payload(data)
        self._record_metrics(data, partner=partner)
        return {"ok": True, "partner_id": partner.id}

    def daily_stats(self, date_str=None):
        Metric = self.env["lea.qc.sample.call"].sudo()
        domain = [("campaign", "=", "DW_QCB2B")]
        if date_str:
            domain.append(("call_date", ">=", date_str))
            domain.append(("call_date", "<", date_str + " 23:59:59"))
        recs = Metric.search(domain)
        hot = recs.filtered(lambda r: r.crm_action == "tag_lead_chaud_driven" or r.qualified)
        disq = recs.filtered(
            lambda r: (r.crm_action or "").startswith("tag_disqualifie")
        )
        return {
            "calls": len(recs),
            "hot_leads": len(hot),
            "disqualified": len(disq),
        }
