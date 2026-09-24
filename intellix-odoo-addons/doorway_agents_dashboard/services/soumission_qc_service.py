# -*- coding: utf-8 -*-
import logging
from datetime import timedelta

from odoo import fields

_logger = logging.getLogger(__name__)

QUAL_MAP = {
    "tag_locataire": "locataire",
    "tag_pas_projet": "pas_interesse",
    "tag_pas_interesse": "pas_interesse",
    "tag_lead_qualifie": "qualifie",
    "tag_dnc": "dnc",
    "tag_travaux": "a_rappeler",
}


class SoumissionQcService:
    """Post-appel Sofia — Soumission Entrepreneurs (Québec)."""

    def __init__(self, env):
        self.env = env

    def _tag(self, name):
        Tag = self.env["crm.tag"].sudo()
        tag = Tag.search([("name", "=", name)], limit=1)
        if not tag:
            tag = Tag.create({"name": name})
        return tag

    def _team_renovation(self):
        return self.env["crm.team"].sudo().search(
            [("name", "ilike", "Rénovation")], limit=1
        )

    def _director_user(self):
        return self.env["res.users"].sudo().search(
            [("login", "in", ("karine", "karine@agencedoorway.com"))], limit=1
        )

    def process_call_ended(self, data):
        data = data or {}
        Lead = self.env["crm.lead"].sudo()
        Partner = self.env["res.partner"].sudo()
        lead = Lead.browse(int(data.get("lead_id") or 0))
        partner = Partner.browse(int(data.get("partner_id") or 0))
        phone = (data.get("telephone") or "").strip()
        if not partner and phone:
            partner = Partner.search(
                ["|", ("phone", "ilike", phone[-10:]), ("mobile", "ilike", phone[-10:])],
                limit=1,
            )
        if not lead.exists() and partner:
            lead = Lead.search([("partner_id", "=", partner.id)], limit=1, order="id desc")

        action = data.get("crm_action") or data.get("statut") or ""
        qual = QUAL_MAP.get(action, "non_fait")
        if data.get("qualified"):
            qual = "qualifie"

        note_lines = [
            "Émilie SoumissionEntrepreneurs QC",
            "Durée: %ss" % (data.get("duration_sec") or 0),
            "Projet: %s" % (data.get("type_projet") or data.get("travaux") or "—"),
            "Disponibilité: %s" % (data.get("preference_rappel") or data.get("dispo_rappel") or "—"),
            (data.get("transcript") or "")[:800],
        ]
        note = "\n".join(note_lines)

        result = {"lead_id": False, "partner_id": partner.id if partner else False}

        if lead.exists():
            vals = {
                "qualification_statut": qual,
                "source_vicidial": True,
                "campagne_vicidial": data.get("campaign") or "SE_RENOV_QC",
                "notes_qualification": note,
            }
            if data.get("travaux"):
                vals["type_projet"] = "reno_globale"
            lead.write(vals)
            tag = self._tag("Soumission Entrepreneurs")
            lead.write({"tag_ids": [(4, tag.id)]})
            result["lead_id"] = lead.id
        elif partner:
            team = self._team_renovation()
            lead = Lead.create({
                "name": "Rénovation — %s" % (data.get("prenom") or partner.name or phone),
                "partner_id": partner.id,
                "phone": phone or partner.phone,
                "description": note,
                "qualification_statut": qual,
                "source_vicidial": True,
                "campagne_vicidial": data.get("campaign") or "SE_RENOV_QC",
                "team_id": team.id if team else False,
                "type": "opportunity" if qual == "qualifie" else "lead",
            })
            lead.tag_ids = [(4, self._tag("Soumission Entrepreneurs").id)]
            result["lead_id"] = lead.id

        result["ok"] = True
        return result

    def process_qualified(self, data):
        data = data or {}
        base = self.process_call_ended({**data, "qualified": True, "crm_action": "tag_lead_qualifie"})
        lead = self.env["crm.lead"].sudo().browse(base.get("lead_id"))
        if not lead.exists():
            return base

        pref = data.get("preference_rappel") or data.get("dispo_rappel") or ""
        moment = pref or "matin"
        director = self._director_user()
        deadline = fields.Date.today() + timedelta(days=1)
        while deadline.weekday() >= 5:
            deadline += timedelta(days=1)

        self.env["mail.activity"].sudo().create({
            "res_model": "crm.lead",
            "res_id": lead.id,
            "activity_type_id": self.env.ref("mail.mail_activity_data_call").id,
            "summary": "Appel qualif — %s" % (lead.name or data.get("prenom") or ""),
            "note": (
                "Lead qualifié Émilie SE\n"
                "Projet: %s\nRappeler: %s"
                % (data.get("type_projet") or data.get("travaux") or "—", moment)
            ),
            "date_deadline": deadline,
            "user_id": director.id if director else self.env.user.id,
        })
        lead.write({
            "qualification_statut": "qualifie",
            "prochaine_etape": "Rappel directeur travaux (%s)" % moment,
            "type": "opportunity",
        })
        base["activity_created"] = True
        return base

    def process_non_qualified(self, data):
        data = data or {}
        action = data.get("crm_action") or ""
        base = self.process_call_ended(data)
        lead = self.env["crm.lead"].sudo().browse(base.get("lead_id"))
        if not lead.exists():
            return base

        if action == "tag_locataire":
            lead.write({"qualification_statut": "locataire"})
        elif action == "tag_pas_projet":
            lead.write({"qualification_statut": "pas_interesse"})
            self.env["mail.activity"].sudo().create({
                "res_model": "crm.lead",
                "res_id": lead.id,
                "activity_type_id": self.env.ref("mail.mail_activity_data_call").id,
                "summary": "Relance Sofia SE (+6 mois)",
                "date_deadline": fields.Date.today() + timedelta(days=180),
                "user_id": lead.user_id.id or self.env.user.id,
            })
        elif action == "tag_pas_interesse":
            lead.write({"qualification_statut": "pas_interesse"})
        elif action == "tag_dnc":
            lead.write({"qualification_statut": "dnc"})
        return base

    def daily_stats(self, date_str=None):
        """Stats Sofia SE / Léa QC — appels lea.qc.sample.call (Toronto), pas les leads CRM.

        Campagnes : DW_QCB2C, SE_RENOV_QC. Si aucun enregistrement et campagne inactive
        côté Vicidial (flag ICP), renvoie campaign_active=False pour éviter un mail à 0.
        """
        date_str = date_str or fields.Date.to_string(fields.Date.context_today(self))
        campaigns = ("SE_RENOV_QC", "DW_QCB2C")
        Metric = self.env["lea.qc.sample.call"].sudo()
        self.env.cr.execute(
            """
            SELECT
              COUNT(*) AS calls,
              COUNT(*) FILTER (
                WHERE qualified IS TRUE
                   OR crm_action IN (
                        'tag_lead_qualifie', 'tag_positif_ia', 'creer_lead_reno'
                   )
                   OR qualification_statut IN ('qualifie', 'rdv')
              ) AS qualified,
              COUNT(*) FILTER (
                WHERE crm_action = 'tag_pas_interesse'
                   OR qualification_statut = 'pas_interesse'
              ) AS pas_interesse,
              COUNT(*) FILTER (
                WHERE crm_action = 'tag_locataire'
                   OR qualification_statut = 'locataire'
              ) AS locataire,
              COUNT(*) FILTER (
                WHERE crm_action = 'tag_pas_projet'
                   OR qualification_statut = 'pas_projet'
              ) AS pas_projet
            FROM lea_qc_sample_call
            WHERE campaign IN %s
              AND (call_date AT TIME ZONE 'America/Toronto')::date = %s::date
              AND call_sid NOT LIKE '_unknown_%%'
            """,
            (campaigns, date_str),
        )
        row = self.env.cr.fetchone() or (0, 0, 0, 0, 0)
        calls = int(row[0] or 0)
        # ICP optionnel : doorway_agents_dashboard.sofia_se_campaign_active = 0/1
        Icp = self.env["ir.config_parameter"].sudo()
        flag = (Icp.get_param("doorway_agents_dashboard.sofia_se_campaign_active") or "").strip()
        if flag == "":
            # défaut : inactive tant que DW_QCB2C n'est plus en prod (évite spam 0)
            campaign_active = calls > 0
        else:
            campaign_active = flag not in ("0", "false", "False", "no", "off")
        return {
            "date": date_str,
            "calls": calls,
            "qualified": int(row[1] or 0),
            "pas_interesse": int(row[2] or 0),
            "locataire": int(row[3] or 0),
            "pas_projet": int(row[4] or 0),
            "campaign_active": campaign_active,
            "skip_zero_report": True,
            "source": "lea.qc.sample.call",
            "campaigns": list(campaigns),
        }
