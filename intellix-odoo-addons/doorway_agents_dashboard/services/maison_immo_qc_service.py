# -*- coding: utf-8 -*-
import logging
from datetime import timedelta

from odoo import fields

_logger = logging.getLogger(__name__)

QUAL_MAP = {
    "tag_pas_interesse": "pas_interesse",
    "tag_lead_qualifie": "qualifie",
    "tag_dnc": "dnc",
}


class MaisonImmoQcService:
    """Post-appel Sophie — MaisonRecherchee.com (Québec)."""

    def __init__(self, env):
        self.env = env

    def _tag(self, name):
        Tag = self.env["crm.tag"].sudo()
        tag = Tag.search([("name", "=", name)], limit=1)
        if not tag:
            tag = Tag.create({"name": name})
        return tag

    def _team_immobilier(self):
        return self.env["crm.team"].sudo().search(
            [("name", "ilike", "Immobilier")], limit=1
        )

    def process_call_ended(self, data):
        data = data or {}
        Lead = self.env["crm.lead"].sudo()
        Partner = self.env["res.partner"].sudo()
        lead = Lead.browse(int(data.get("lead_id") or 0))
        partner = Partner.browse(int(data.get("partner_id") or 0))
        phone = (data.get("telephone") or data.get("phone") or "").strip()
        if not partner and phone:
            tail = phone[-10:]
            domain = ["|", ("phone", "ilike", tail), ("phone_sanitized", "ilike", tail)]
            if "mobile" in Partner._fields:
                domain = ["|", ("mobile", "ilike", tail)] + domain
            partner = Partner.search(domain, limit=1)
        if not lead.exists() and partner:
            lead = Lead.search([("partner_id", "=", partner.id)], limit=1, order="id desc")
        if not lead.exists() and phone:
            tail = phone[-10:]
            lead_domain = ["|", ("phone", "ilike", tail), ("phone_sanitized", "ilike", tail)]
            lead = Lead.search(lead_domain, limit=1, order="id desc")

        action = (
            data.get("crm_action")
            or data.get("statut")
            or data.get("etat_final")
            or ""
        )
        qual = QUAL_MAP.get(action, "non_fait")
        if data.get("qualified") or data.get("lead_ganador"):
            qual = "qualifie"

        duration = data.get("duration_sec") or data.get("duration_seconds") or 0
        timeline = data.get("timeline") or ""
        note_lines = [
            "Sophie MaisonRecherchee QC",
            "Durée: %ss" % duration,
            "Intention vente: %s" % (data.get("intention_vente") or "—"),
            "Timeline: %s" % (timeline or "—"),
            "Disponibilité: %s" % (data.get("preference_rappel") or "—"),
            (data.get("transcript") or "")[:800],
        ]
        note = "\n".join(note_lines)
        campaign = data.get("campaign") or "MR_IMMO_QC"
        result = {"lead_id": False, "partner_id": partner.id if partner else False}

        tags = [self._tag("Agent IA MR")]
        if timeline == "CHAUD":
            tags.append(self._tag("Chaud <6mois"))
        elif timeline == "TIEDE":
            tags.append(self._tag("Tiède 6-12mois"))
        elif timeline == "FUTUR":
            tags.append(self._tag("Futur 1-2ans"))

        if lead.exists():
            vals = {
                "qualification_statut": qual,
                "source_vicidial": True,
                "campagne_vicidial": campaign,
                "notes_qualification": note,
            }
            lead.write(vals)
            lead.write({"tag_ids": [(4, t.id) for t in tags]})
            result["lead_id"] = lead.id
        elif partner:
            team = self._team_immobilier()
            lead = Lead.create({
                "name": "Vente — %s" % (data.get("prenom") or partner.name or phone),
                "partner_id": partner.id,
                "phone": phone or partner.phone,
                "description": note,
                "qualification_statut": qual,
                "source_vicidial": True,
                "campagne_vicidial": campaign,
                "team_id": team.id if team else False,
                "type": "opportunity" if qual == "qualifie" else "lead",
            })
            lead.write({"tag_ids": [(4, t.id) for t in tags]})
            result["lead_id"] = lead.id

        result["ok"] = True
        return result

    def process_qualified(self, data):
        data = data or {}
        base = self.process_call_ended({**data, "qualified": True, "crm_action": "tag_lead_qualifie"})
        lead = self.env["crm.lead"].sudo().browse(base.get("lead_id"))
        if not lead.exists():
            return base

        pref = data.get("preference_rappel") or data.get("dispo_rappel") or "matin"
        deadline = fields.Date.today() + timedelta(days=1)
        while deadline.weekday() >= 5:
            deadline += timedelta(days=1)

        self.env["mail.activity"].sudo().create({
            "res_model": "crm.lead",
            "res_id": lead.id,
            "activity_type_id": self.env.ref("mail.mail_activity_data_call").id,
            "summary": "Rappel MR — %s" % (lead.name or ""),
            "note": "Lead qualifié Sophie MR\nTimeline: %s\nRappeler: %s" % (
                data.get("timeline") or "—",
                pref,
            ),
            "date_deadline": deadline,
            "user_id": lead.user_id.id or self.env.user.id,
        })
        lead.write({
            "qualification_statut": "qualifie",
            "prochaine_etape": "Rappel conseiller (%s)" % pref,
            "type": "opportunity",
        })
        lead.tag_ids = [(4, self._tag("Rappel Planifié").id)]
        base["activity_created"] = True
        return base

    def process_non_qualified(self, data):
        return self.process_call_ended(data)
