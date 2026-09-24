# -*- coding: utf-8 -*-
"""Post-appel Léa FR — recrutement artisans partenaires MaRénoFacile (B2B, France).

Un artisan qualifié (RDV pris avec Karine) :
  => crm.lead assigné à Karine
  => activité "RDV MaRénoFacile" (créneau + métier + territoire)
Sinon : lead non assigné, taggé selon l'issue de l'appel.
"""

import logging
from datetime import date, timedelta

from odoo import fields

_logger = logging.getLogger(__name__)

_TRUEISH = frozenset({"1", "true", "oui", "yes", "y", "o", True, 1})


class LeaFrService:
    def __init__(self, env):
        self.env = env

    def _tag(self, name):
        Tag = self.env["crm.tag"].sudo()
        tag = Tag.search([("name", "=", name)], limit=1)
        if not tag:
            tag = Tag.create({"name": name})
        return tag

    def _team(self):
        Team = self.env["crm.team"].sudo()
        team = Team.search([("name", "ilike", "Marketing")], limit=1)
        if not team:
            team = Team.search([("name", "ilike", "Rénovation")], limit=1)
        return team

    def _karine_user(self):
        return self.env["res.users"].sudo().search(
            [("login", "=", "karine@agencedoorway.com")], limit=1
        )

    @staticmethod
    def _is_true(val):
        if isinstance(val, bool):
            return val
        return str(val).strip().lower() in _TRUEISH

    def _schedule_rdv_activity(self, lead, karine, dispo, metier, territoire, transcript):
        """Activité RDV MaRénoFacile pour Karine (rappel confirmation secteur)."""
        try:
            act_type = self.env.ref(
                "mail.mail_activity_data_todo", raise_if_not_found=False
            )
            summary = "RDV MaRénoFacile — %s" % (dispo or "créneau à confirmer")
            note = "\n".join(
                [
                    "Artisan à rappeler pour valider la disponibilité de son secteur.",
                    "Créneau souhaité : %s" % (dispo or "—"),
                    "Métier : %s" % (metier or "—"),
                    "Territoire : %s" % (territoire or "—"),
                    "",
                    (transcript or "")[:600],
                ]
            )
            lead.activity_schedule(
                act_type_xmlid="mail.mail_activity_data_todo",
                date_deadline=date.today() + timedelta(days=1),
                summary=summary,
                note=note.replace("\n", "<br/>"),
                user_id=karine.id if karine else self.env.uid,
            )
        except Exception:  # noqa: BLE001
            _logger.exception("Léa FR: échec création activité RDV")

    def process_call_ended(self, data):
        data = data or {}
        Lead = self.env["crm.lead"].sudo()
        Partner = self.env["res.partner"].sudo()

        phone = (data.get("telephone") or data.get("phone_number") or "").strip()
        lead = Lead.browse(int(data.get("lead_id") or 0))
        partner = Partner.browse(int(data.get("partner_id") or 0))

        if not partner.exists() and phone:
            partner = Partner.search(
                [
                    "|",
                    ("phone", "ilike", phone[-9:]),
                    ("phone_sanitized", "ilike", phone[-9:]),
                ],
                limit=1,
            )

        amd = (data.get("amd_result") or "").lower()
        statut = (data.get("statut") or data.get("etat_final") or "").lower()
        rdv_pris = self._is_true(data.get("rdv_pris")) or statut == "rdv_pris"

        metier = (data.get("metier") or "").strip()
        territoire = (data.get("territoire") or "").strip()
        generation = (data.get("generation_actuelle") or "").strip()
        dispo = (data.get("dispo_rdv") or "").strip()
        transcript = data.get("transcript") or ""
        prenom = (data.get("prenom") or data.get("first_name") or "").strip()

        if amd in ("machine", "answering_machine", "amd_hangup", "fax", "not_sure"):
            qual = "messagerie"
        elif rdv_pris or statut in ("rdv_pris", "rdv"):
            qual = "rdv"  # Selection crm.lead.qualification_statut
        elif statut in ("dnc", "tag_dnc"):
            qual = "dnc"
        elif statut in ("refus", "pas_interesse", "non"):
            qual = "pas_interesse"
        else:
            qual = "non_fait"

        note = "\n".join(
            [
                "Léa FR — Recrutement artisan MaRénoFacile",
                "Durée: %ss" % (data.get("duration_sec") or 0),
                "Métier: %s" % (metier or "—"),
                "Territoire: %s" % (territoire or "—"),
                "Génération leads actuelle: %s" % (generation or "—"),
                "Créneau RDV: %s" % (dispo or "—"),
                "RDV pris: %s" % ("oui" if rdv_pris else "non"),
                "",
                transcript[:800],
            ]
        )

        karine = self._karine_user()
        team = self._team()

        vals_common = {
            "source_vicidial": True,
            "campagne_vicidial": data.get("campaign") or "DW_LEAFR",
            "notes_qualification": note,
            "qualification_statut": qual,
        }
        if team:
            vals_common["team_id"] = team.id
        # Tous les leads Léa FR → Karine (jamais Leila)
        vals_common["user_id"] = karine.id if karine else False

        result = {"lead_id": False, "partner_id": partner.id if partner else False}

        def _apply_tags(target_lead):
            tags = [self._tag("Léa FR").id, self._tag("MaRénoFacile Partenaire").id]
            if rdv_pris:
                tags.append(self._tag("RDV MaRénoFacile").id)
            target_lead.write({"tag_ids": [(4, tid) for tid in tags]})

        # Faux positifs / non-qualifiés : archiver pour ne pas polluer le pipeline Karine
        if qual in ("messagerie", "non_fait", "pas_interesse", "dnc"):
            vals_common["active"] = False

        if lead.exists():
            lead.write(vals_common)
            _apply_tags(lead)
            result["lead_id"] = lead.id
        elif partner or phone:
            name = prenom or (partner.name if partner else phone)
            lead = Lead.create(
                {
                    "name": "MaRénoFacile Artisan — %s" % name,
                    "partner_id": partner.id if partner else False,
                    "phone": phone or (partner.phone if partner else ""),
                    "contact_name": prenom or False,
                    "type": "lead",
                    **vals_common,
                }
            )
            _apply_tags(lead)
            result["lead_id"] = lead.id

        if result["lead_id"] and rdv_pris:
            self._schedule_rdv_activity(
                Lead.browse(result["lead_id"]),
                karine,
                dispo,
                metier,
                territoire,
                transcript,
            )

        try:
            from odoo.addons.doorway_vicidial_campaigns.services.vicidial_service import (
                VicidialService,
            )

            VicidialService(self.env).upsert_call_from_pipeline(
                {
                    **data,
                    "campaign": data.get("campaign") or "DW_LEAFR",
                    "agent_id": data.get("agent_id") or "lea-fr",
                    "statut": qual,
                    "etat_final": qual,
                }
            )
        except Exception:  # noqa: BLE001
            _logger.exception("Léa FR upsert call log failed")

        return result
