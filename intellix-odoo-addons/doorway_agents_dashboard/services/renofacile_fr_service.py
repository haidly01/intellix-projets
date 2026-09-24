# -*- coding: utf-8 -*-

import logging



from odoo import fields



_logger = logging.getLogger(__name__)



STATUT_MAP = {

    "proprietaire": "oui",

    "locataire": "non",

    "ne_sait_pas": False,

}



LOGEMENT_MAP = {

    "maison": "maison",

    "appartement": "appartement",

}



CHAUFFAGE_MAP = {

    "gaz": "gaz",

    "fioul": "fioul",

    "electrique": "electrique",

    "autre": "autre",

}



CONSENT_YES = frozenset({"oui", "yes", "true", "1", "o"})

CONSENT_NO = frozenset({"non", "no", "false", "0", "n"})





class RenofacileFrService:

    """Post-appel Sofia RénoFacile — France B2C (rappel Karine, sans transfert)."""



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



    def _karine_user(self):

        return self.env["res.users"].sudo().search(

            [("login", "=", "karine@agencedoorway.com")], limit=1

        )



    def _parse_consent(self, data):

        """Parse consentement explicite depuis le webhook n8n / agent."""

        for key in (

            "consentement_recontact",

            "consent_rappel",

            "consent_renov",

            "consentement_recontact_renov",

        ):

            raw = data.get(key)

            if raw is None or raw == "":

                continue

            if isinstance(raw, bool):

                return raw

            val = str(raw).lower().strip()

            if val in CONSENT_YES:

                return True

            if val in CONSENT_NO:

                return False

        return None



    def _consent_label(self, consent):

        if consent is True:

            return "oui"

        if consent is False:

            return "non"

        return "—"



    def _pipeline_placement(self, team, qual, karine):
        """Non qualifié → colonne Agent IA sans vendeur ; qualifié consenti → Qualification + Karine."""
        Lead = self.env["crm.lead"]
        if qual == "a_rappeler":
            vals = {}
            qual_stage = self.env.ref(
                "renovation_conciergerie.crm_stage_renovation_qualified",
                raise_if_not_found=False,
            )
            if qual_stage:
                vals["stage_id"] = qual_stage.id
            if karine:
                vals["user_id"] = karine.id
            return vals
        if qual in ("pas_interesse", "locataire", "messagerie"):
            vals = Lead._doorway_ai_agent_entry_vals(team=team)
            unqual = self.env.ref(
                "renovation_conciergerie.crm_stage_renovation_immo_unqualified",
                raise_if_not_found=False,
            )
            if unqual:
                vals["stage_id"] = unqual.id
            vals["user_id"] = False
            return vals
        vals = Lead._doorway_ai_agent_entry_vals(team=team)
        vals["user_id"] = False
        return vals



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

        completed = bool(data.get("qualification_complete") or data.get("completed"))

        consent = self._parse_consent(data)

        consent_yes = consent is True

        is_locataire = (data.get("statut_propriete") or "").lower() == "locataire"

        qual_positif = statut in (
            "qualifie",
            "interesse",
            "rappel",
            "a_rappeler",
            "tag_lead_qualifie",
        )

        if amd in ("machine", "answering_machine", "amd_hangup"):

            qual = "messagerie"

        elif statut in ("refus", "pas_interesse", "non", "dnc", "tag_dnc"):

            qual = "pas_interesse"

        elif is_locataire:

            qual = "locataire"

        elif completed and consent_yes and qual_positif:

            qual = "a_rappeler"

        elif completed and qual_positif:

            qual = "qualifie"

        else:

            qual = "non_fait"



        prenom = (data.get("prenom") or data.get("first_name") or "").strip()

        ville = (data.get("ville") or data.get("city") or "").strip()

        note_lines = [

            "Sofia RénoFacile FR B2C",

            "Durée: %ss" % (data.get("duration_sec") or data.get("duration") or 0),

            "Statut: %s" % (data.get("statut_propriete") or "—"),

            "Logement: %s" % (data.get("type_logement") or "—"),

            "Chauffage: %s" % (data.get("chauffage") or "—"),

            "Travaux: %s" % (data.get("travaux_existants") or "—"),

            "Consentement rappel: %s" % self._consent_label(consent),

            (data.get("transcript") or "")[:800],

        ]

        note = "\n".join(note_lines)



        karine = self._karine_user()

        team = self._team_renovation()



        vals_common = {

            "source_vicidial": True,

            "campagne_vicidial": data.get("campaign") or "DW_FRB2C",

            "notes_qualification": note,

            "qualification_statut": qual,

        }

        vals_common.update(self._pipeline_placement(team, qual, karine))

        if team and not vals_common.get("team_id"):

            vals_common["team_id"] = team.id

        if ville:

            vals_common["city"] = ville



        prop = STATUT_MAP.get((data.get("statut_propriete") or "").lower())

        if prop:

            vals_common["est_proprietaire"] = prop

        logement = LOGEMENT_MAP.get((data.get("type_logement") or "").lower())

        if logement:

            vals_common["type_logement"] = logement

        chauff = CHAUFFAGE_MAP.get((data.get("chauffage") or "").lower())

        if chauff:

            vals_common["chauffage_actuel"] = chauff



        preuve = (

            data.get("recording_url")

            or data.get("url_enregistrement")

            or data.get("vicidial_call_id")

            or data.get("call_sid")

            or data.get("uniqueid")

        )



        result = {"lead_id": False, "partner_id": partner.id if partner else False}



        def _apply_consent_tags(target_lead):

            tags = [self._tag("RénoFacile").id]

            if consent_yes:

                tags.append(self._tag("Consentement rappel OK").id)

                if qual == "a_rappeler":

                    tags.append(self._tag("Pool rappel août 2026").id)

                target_lead.register_renofacile_consent(

                    consent_renov=True,

                    consent_artisans=True,

                    preuve=preuve or False,

                    source="marenofacile",

                )

            elif completed and qual_positif and consent is False:

                tags.append(self._tag("Sans consentement rappel").id)

            target_lead.write({"tag_ids": [(4, tid) for tid in tags]})



        if lead.exists():

            lead.write(vals_common)

            _apply_consent_tags(lead)

            if qual == "a_rappeler":

                lead.action_marquer_rappel()

            result["lead_id"] = lead.id

        elif partner or phone:

            name = prenom or (partner.name if partner else phone)

            lead = Lead.create(

                {

                    "name": "RénoFacile — %s" % name,

                    "partner_id": partner.id if partner else False,

                    "phone": phone or (partner.phone if partner else ""),

                    "contact_name": prenom or False,

                    "team_id": team.id if team else False,

                    "type": "lead",

                    **vals_common,

                }

            )

            _apply_consent_tags(lead)

            if qual == "a_rappeler":

                lead.action_marquer_rappel()

            result["lead_id"] = lead.id



        try:

            from odoo.addons.doorway_vicidial_campaigns.services.vicidial_service import (

                VicidialService,

            )



            consent_notes = None

            if consent is not None:

                consent_notes = "Consentement rappel: %s" % self._consent_label(consent)



            VicidialService(self.env).upsert_call_from_pipeline(

                {

                    **data,

                    "campaign": data.get("campaign") or "DW_FRB2C",

                    "agent_id": data.get("agent_id") or "marenofacile",

                    "statut": qual,

                    "etat_final": qual,

                    "consent_captured": consent_yes,

                    "consent_notes": consent_notes,

                }

            )

        except Exception:  # noqa: BLE001

            _logger.exception("RénoFacile upsert call log failed")



        return result

