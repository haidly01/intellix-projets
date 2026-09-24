# -*- coding: utf-8 -*-
"""Post-appel Léa — qualification B2C Québec (proprio/locataire, immo, réno)."""
import logging
from datetime import timedelta

from odoo import fields

_logger = logging.getLogger(__name__)

CRM_ACTION_MAP = {
    "tag_locataire": "locataire",
    "tag_pas_projet": "pas_interesse",
    "tag_pas_interesse": "pas_interesse",
    "tag_dnc": "dnc",
    "tag_rappeler": "rappeler",
    "tag_rappeler_plus_tard": "rappeler_plus_tard",
}


class LeaQcService:
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

    def _team(self, pipeline_key):
        xmlid = {
            "immobilier": "renovation_conciergerie.crm_team_immobilier",
            "renovation": "renovation_conciergerie.crm_team_renovation",
        }.get(pipeline_key)
        if xmlid:
            return self.env.ref(xmlid, raise_if_not_found=False)
        return self.env["crm.team"].sudo().search([], limit=1)

    def _martin_user(self):
        user = (
            self.env["res.users"]
            .sudo()
            .search(
                [
                    "|",
                    ("login", "=", "martin@agencedoorway.com"),
                    ("login", "ilike", "martin%houle%"),
                ],
                limit=1,
            )
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
        from odoo.addons.doorway_agents_dashboard.services.lea_qc_phone import (
            resolve_phone,
        )

        call_sid = (data.get("call_sid") or data.get("uniqueid") or "").strip()
        resolved = resolve_phone(phone, call_sid=call_sid)
        digits = (resolved or "".join(c for c in phone if c.isdigit()))[-10:]
        if resolved:
            phone = resolved
        elif digits:
            phone = digits
        if digits:
            p = Partner.search(
                [
                    
                    ("phone", "ilike", digits),
                    
                ],
                limit=1,
            )
            if p:
                return p
        name = (data.get("nom") or data.get("name") or data.get("prenom") or "Contact QC").strip()
        return Partner.create(
            {
                "name": name[:128],
                "phone": phone or digits,
                
                "category_id": [(4, self._partner_category("B2C Brut").id)],
            }
        )

    def _resolve_action(self, data):
        return (
            data.get("action_crm")
            or data.get("crm_action")
            or data.get("etat_final")
            or ""
        )

    def _resolve_lead_type(self, data):
        lead_type = (data.get("lead_type") or "").lower()
        if lead_type:
            return lead_type
        besoin = (data.get("besoin") or "").lower()
        mapping = {"reno": "renovation", "immo": "immobilier", "les_deux": "les_deux"}
        if besoin in mapping:
            return mapping[besoin]
        if data.get("intention_vente") and data.get("type_projet"):
            return "les_deux"
        if data.get("intention_vente"):
            return "immobilier"
        if data.get("type_projet"):
            return "renovation"
        return ""

    def _infer_lead_type_from_transcript(self, data):
        transcript = (data.get("transcript") or "").lower()
        has_reno = any(x in transcript for x in ("réno", "reno", "rénovation", "toiture", "salle de bain"))
        has_immo = any(
            x in transcript
            for x in ("immobilier", "vente", "éval", "evaluation", "les 2", "les deux")
        )
        if has_reno and has_immo:
            return "les_deux"
        if has_immo:
            return "immobilier"
        if has_reno:
            return "renovation"
        return "renovation"

    def _is_qualified_positive(self, data):
        action = self._resolve_action(data)
        if action == "tag_lead_qualifie":
            return True
        return bool(
            (data.get("qualified") or data.get("lead_ganador"))
            and (data.get("proprietaire") or data.get("propietario"))
        )

    def _lead_notes(self, data):
        parts = []
        if data.get("notes"):
            parts.append(str(data.get("notes")))
        dispo = (
            data.get("preference_rappel")
            or data.get("dispo_rappel")
            or data.get("meilleur_moment_rappel")
        )
        if not dispo:
            transcript = (data.get("transcript") or "").lower()
            if "après-midi" in transcript or "apres-midi" in transcript:
                dispo = "après-midi"
            elif "matin" in transcript:
                dispo = "matin"
            elif "soir" in transcript:
                dispo = "soir"
        if dispo:
            parts.append("Dispo rappel: %s" % dispo)
        if data.get("type_projet"):
            parts.append("Projet: %s" % data.get("type_projet"))
        if data.get("recording_url"):
            parts.append("Enregistrement: %s" % data.get("recording_url"))
        return "\n".join(parts) or "—"

    def _lead_vals_base(self, partner, data, team):
        transcript = (data.get("transcript") or "")[:800]
        today = fields.Datetime.now()
        return {
            "partner_id": partner.id,
            "phone": partner.phone,
            "user_id": self._martin_user().id,
            "priority": "2",
            "description": (
                "Qualifié par Léa — %s\n"
                "Lead type: %s\n"
                "Notes: %s\n\n"
                "Transcript:\n%s"
            )
            % (
                today,
                self._resolve_lead_type(data) or "—",
                self._lead_notes(data),
                transcript,
            ),
            "team_id": team.id if team else False,
            "type": "opportunity",
        }

    def _lead_env(self):
        return self.env["crm.lead"].sudo().with_context(
            doorway_skip_email_unique_check=True
        )

    def _create_lead_immo(self, partner, data):
        team = self._team("immobilier")
        Lead = self._lead_env()
        tags = [
            self._tag("Propriétaire"),
            self._tag("Évaluation Marchande"),
            self._tag("Martin Rappelle"),
        ]
        lead = Lead.create(
            {
                **self._lead_vals_base(partner, data, team),
                "name": "Léa — Éval. marchande — %s" % partner.name,
                "tag_ids": [(4, t.id) for t in tags],
            }
        )
        return lead

    def _create_lead_reno(self, partner, data):
        team = self._team("renovation")
        Lead = self._lead_env()
        type_reno = data.get("type_reno") or data.get("type_projet") or "autre"
        tags = [
            self._tag("Propriétaire"),
            self._tag("Projet Réno"),
            self._tag("Martin Rappelle"),
        ]
        lead = Lead.create(
            {
                **self._lead_vals_base(partner, data, team),
                "name": "Léa — Réno — %s — %s" % (partner.name, type_reno),
                "tag_ids": [(4, t.id) for t in tags],
            }
        )
        return lead

    def _activity_martin(self, record, note, deadline=None):
        if not record or not record.id:
            return
        deadline = deadline or fields.Date.today()
        user = self._martin_user()
        if not user:
            return
        try:
            self.env["mail.activity"].sudo().create(
                {
                    "res_model_id": self.env["ir.model"]._get(record._name).id,
                    "res_id": int(record.id),
                    "activity_type_id": self.env.ref("mail.mail_activity_data_call").id,
                    "summary": "Rappel Léa — Martin",
                    "note": note,
                    "date_deadline": deadline,
                    "user_id": user.id,
                }
            )
        except Exception as exc:
            _logger.warning(
                "Léa activity skip %s=%s: %s", record._name, record.id, exc
            )

    def _record_metrics(self, data, partner=None, lead=None):
        """Enregistre/maj la ligne d'instrumentation de précision (non bloquant)."""
        try:
            Metric = self.env["lea.qc.sample.call"].sudo()
        except KeyError:
            return
        try:
            Metric.register_call_ended(data)
            rec = Metric.search(
                [("call_sid", "=", (data.get("call_sid") or "").strip())], limit=1
            )
            if rec:
                vals = {}
                if partner and partner.id and not rec.partner_id:
                    vals["partner_id"] = partner.id
                if lead and lead.id and not rec.lead_id:
                    vals["lead_id"] = lead.id
                if vals:
                    rec.write(vals)
        except Exception as exc:  # pragma: no cover - jamais bloquant
            _logger.warning("Léa metrics record échec: %s", exc)

    def process_post_call(self, data):
        """Point d'entrée unique post-qualification Léa."""
        data = data or {}
        # Instrumentation d'abord : on veut la mesure même si le CRM échoue.
        self._record_metrics(data)
        partner = self._partner_from_payload(data)
        action = self._resolve_action(data)
        if action == "tag_dnc":
            return self.process_non_qualified(data)
        lead_type = self._resolve_lead_type(data)
        if not lead_type and self._is_qualified_positive(data):
            lead_type = self._infer_lead_type_from_transcript(data)
        result = {
            "ok": True,
            "partner_id": partner.id,
            "lead_immo_id": False,
            "lead_reno_id": False,
            "lead_type": lead_type,
            "crm_action": action,
        }

        appelle = self._partner_category("Appelé Léa")
        partner.write({"category_id": [(4, appelle.id)]})

        create_immo = lead_type in ("immobilier", "les_deux") or action in (
            "creer_lead_immo",
            "creer_les_deux",
        )
        create_reno = lead_type in ("renovation", "les_deux") or action in (
            "creer_lead_reno",
            "creer_les_deux",
        )

        if create_immo:
            lead = self._create_lead_immo(partner, data)
            result["lead_immo_id"] = lead.id
            dispo = (
                data.get("preference_rappel")
                or data.get("dispo_rappel")
                or data.get("meilleur_moment_rappel")
            )
            if not dispo:
                transcript = (data.get("transcript") or "").lower()
                if "après-midi" in transcript or "apres-midi" in transcript:
                    dispo = "après-midi"
                elif "matin" in transcript:
                    dispo = "matin"
                elif "soir" in transcript:
                    dispo = "soir"
            dispo = dispo or "—"
            self._activity_martin(
                lead,
                "Propriétaire intéressé évaluation marchande (Léa). Rappeler: %s" % dispo,
            )

        if create_reno:
            lead = self._create_lead_reno(partner, data)
            result["lead_reno_id"] = lead.id
            type_reno = data.get("type_reno") or data.get("type_projet") or "—"
            dispo = (
                data.get("preference_rappel")
                or data.get("dispo_rappel")
                or data.get("meilleur_moment_rappel")
            )
            if not dispo:
                transcript = (data.get("transcript") or "").lower()
                if "après-midi" in transcript or "apres-midi" in transcript:
                    dispo = "après-midi"
                elif "matin" in transcript:
                    dispo = "matin"
                elif "soir" in transcript:
                    dispo = "soir"
            dispo = dispo or "—"
            self._activity_martin(
                lead,
                "Propriétaire intéressé rénovation (%s). Rappeler: %s"
                % (type_reno, dispo),
            )

        if lead_type == "negatif" and data.get("proprietaire"):
            partner.write(
                {
                    "category_id": [
                        (4, self._partner_category("Propriétaire").id),
                        (4, self._partner_category("Non Intéressé").id),
                    ],
                }
            )

        if lead_type == "locataire" or action == "retirer_liste":
            brut = self._partner_category("B2C Brut")
            loc = self._partner_category("Locataire")
            cats = partner.category_id.ids
            if brut.id in cats:
                cats.remove(brut.id)
            partner.write({"category_id": [(6, 0, cats + [loc.id])]})

        if (data.get("etat_suivant") == "rappel" or action == "noter_rappel") and data.get(
            "meilleur_moment_rappel"
        ):
            partner.write(
                {"category_id": [(4, self._partner_category("Rappel Demandé").id)]}
            )
            lead = self.env["crm.lead"].sudo().browse(
                result.get("lead_immo_id") or result.get("lead_reno_id") or []
            )
            if lead:
                self._activity_martin(
                    lead,
                    "Rappel demandé : %s" % data.get("meilleur_moment_rappel"),
                    fields.Date.today() + timedelta(days=1),
                )

        attempts = int(partner.comment and partner.comment.count("Léa appel") or 0)
        partner.comment = (
            (partner.comment or "")
            + "\nLéa appel %s — %s — %s"
            % (fields.Datetime.now(), lead_type or action, (data.get("notes") or "")[:120])
        ).strip()

        if data.get("amd_result") in ("machine", "fax", "not_sure"):
            attempts += 1
            if attempts >= int(data.get("max_attempts") or 3):
                partner.write(
                    {"category_id": [(4, self._partner_category("Non Intéressé").id)]}
                )

        result["call_attempts"] = attempts + 1

        lead = self.env["crm.lead"].sudo().browse(
            result.get("lead_immo_id") or result.get("lead_reno_id") or []
        )
        self._record_metrics(data, partner=partner, lead=lead if lead else None)
        return result

    def process_qualified(self, data):
        """Appel qualifié (workflow n8n 04) — idempotent avec call-ended."""
        data = dict(data or {})
        data.setdefault("qualified", True)
        data.setdefault("crm_action", "tag_lead_qualifie")
        return self.process_post_call(data)

    def process_non_qualified(self, data):
        """Post-appel non qualifié — tags CRM selon crm_action n8n."""
        data = data or {}
        self._record_metrics(data)
        partner = self._partner_from_payload(data)
        action = data.get("crm_action") or data.get("action_crm") or ""
        qual = CRM_ACTION_MAP.get(action, "non_qualifie")
        result = {"ok": True, "partner_id": partner.id, "crm_action": action, "qualification": qual}

        appelle = self._partner_category("Appelé Léa")
        partner.write({"category_id": [(4, appelle.id)]})

        if action == "tag_locataire":
            brut = self._partner_category("B2C Brut")
            loc = self._partner_category("Locataire")
            cats = [c for c in partner.category_id.ids if c != brut.id]
            partner.write({"category_id": [(6, 0, cats + [loc.id])]})
        elif action == "tag_dnc":
            dnc_cat = self._partner_category("DNC")
            partner.write(
                {
                    "category_id": [
                        (4, dnc_cat.id),
                        (4, self._partner_category("Non Intéressé").id),
                    ]
                }
            )
            from odoo.addons.doorway_agents_dashboard.services.lea_qc_phone import (
                apply_vicidial_dnc,
            )

            campaign = (data.get("campaign") or "DW_QCB2C").strip()
            phone = (
                data.get("telephone")
                or data.get("phone")
                or partner.phone
                or ""
            )
            dnc_res = apply_vicidial_dnc(phone, campaign_id=campaign)
            result["vicidial_dnc"] = dnc_res
        elif action in ("tag_rappeler", "tag_rappeler_plus_tard"):
            partner.write({"category_id": [(4, self._partner_category("Rappel Demandé").id)]})
            delay = 30 if action == "tag_rappeler_plus_tard" else 3
            self._activity_martin(
                partner,
                "Rappel Léa demandé (%s)." % action.replace("tag_", ""),
                fields.Date.today() + timedelta(days=delay),
            )
        elif action in ("tag_pas_interesse", "tag_pas_projet"):
            partner.write({"category_id": [(4, self._partner_category("Non Intéressé").id)]})

        partner.comment = (
            (partner.comment or "")
            + "\nLéa non-qualifié %s — %s"
            % (fields.Datetime.now(), action or qual)
        ).strip()

        self._record_metrics(data, partner=partner)
        return result
