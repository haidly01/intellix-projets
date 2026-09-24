# -*- coding: utf-8 -*-
import re

from odoo import api, fields, models


class CrmLeadSourceIa(models.Model):
    _inherit = "crm.lead"

    source_prenom = fields.Char(string="Prénom (lead reçu)", tracking=True)
    source_nom = fields.Char(string="Nom (lead reçu)", tracking=True)
    source_email = fields.Char(string="Courriel (lead reçu)", tracking=True)
    source_phone = fields.Char(string="Téléphone (lead reçu)", tracking=True)
    source_ville = fields.Char(string="Ville (lead reçu)", tracking=True)
    ia_call_recording_url = fields.Char(string="Enregistrement appel IA", tracking=True)
    ia_call_transcript_display = fields.Text(
        string="Transcription appel IA",
        compute="_compute_ia_call_transcript_display",
    )
    ia_qualification_score = fields.Char(
        string="Score qualification IA",
        compute="_compute_ia_qualification_display",
    )
    ia_qualification_score_numeric = fields.Integer(
        string="Score IA /100",
        compute="_compute_ia_qualification_display",
    )

    @api.depends("haidly_call_transcript", "immo_call_transcript")
    def _compute_ia_call_transcript_display(self):
        for lead in self:
            lead.ia_call_transcript_display = (
                lead.haidly_call_transcript or lead.immo_call_transcript or ""
            )

    @api.depends(
        "haidly_ia_score",
        "immo_ia_score",
        "haidly_ia_score_numeric",
        "immo_ia_score_numeric",
    )
    @api.model
    def _doorway_selection_labels(self, field):
        if not field or not field.selection:
            return {}
        selection = field.selection
        if callable(selection):
            selection = selection(self.env[self._name])
        return dict(selection)

    def _compute_ia_qualification_display(self):
        score_field = self.env["crm.lead"]._fields.get("haidly_ia_score")
        score_labels = self._doorway_selection_labels(score_field)
        for lead in self:
            raw = lead.haidly_ia_score or lead.immo_ia_score or ""
            lead.ia_qualification_score = score_labels.get(raw) or raw or "—"
            lead.ia_qualification_score_numeric = (
                lead.haidly_ia_score_numeric or lead.immo_ia_score_numeric or 0
            )

    @api.model
    def _doorway_parse_meta_contact(self, data):
        """Extrait prénom, nom et coordonnées depuis Meta / n8n / formulaire."""
        first = (
            data.get("first_name")
            or data.get("prenom")
            or data.get("firstname")
            or ""
        ).strip()
        last = (
            data.get("last_name")
            or data.get("nom")
            or data.get("lastname")
            or ""
        ).strip()
        full = (
            data.get("full_name")
            or data.get("contact_name")
            or data.get("nom_complet")
            or ""
        ).strip()
        if not first and not last and full:
            parts = full.split(None, 1)
            first = parts[0]
            last = parts[1] if len(parts) > 1 else ""

        raw_name = (data.get("name") or "").strip()
        if not first and not last and raw_name and "—" not in raw_name:
            parts = raw_name.split(None, 1)
            first = parts[0]
            last = parts[1] if len(parts) > 1 else ""

        contact_name = " ".join(p for p in (first, last) if p).strip()
        phone = (
            data.get("phone")
            or data.get("mobile")
            or data.get("tel")
            or data.get("phone_number")
            or ""
        )
        phone = str(phone).strip()
        email = (data.get("email") or data.get("email_from") or "").strip()
        city = (
            data.get("city")
            or data.get("lead_city")
            or data.get("ville")
            or data.get("city_name")
            or ""
        ).strip()
        return {
            "source_prenom": first or False,
            "source_nom": last or False,
            "source_email": email or False,
            "source_phone": phone or False,
            "source_ville": city or False,
            "contact_name": contact_name or False,
            "email_from": email or False,
            "phone": phone or False,
            "city": city or False,
        }

    def _doorway_apply_source_contact(self, data):
        """Met à jour les champs CRM à partir du payload source."""
        parsed = self._doorway_parse_meta_contact(data)
        vals = {k: v for k, v in parsed.items() if v}
        if vals:
            self.write(vals)
        return parsed

    def _doorway_register_ia_call(self, data):
        """Journalise enregistrement + transcription après post-call n8n."""
        self.ensure_one()
        recording = (
            data.get("recording_url")
            or data.get("audio_url")
            or data.get("url_enregistrement")
            or ""
        ).strip()
        transcript = data.get("transcript") or data.get("haidly_call_transcript")
        if isinstance(transcript, list):
            transcript = self.env["renovation.meta.immo.webhook"]._parse_transcript(
                {"transcript": transcript}
            )
        conversation_id = (
            data.get("conversation_id")
            or data.get("elevenlabs_conversation_id")
            or ""
        )
        duration = int(data.get("duration_sec") or data.get("duration") or 0)

        vals = {}
        if recording:
            vals["ia_call_recording_url"] = recording[:512]
        if vals:
            self.write(vals)

        if recording or transcript:
            self.env["renovation.retell.call.log"].sudo().create(
                {
                    "lead_id": self.id,
                    "phone_number": self.phone or self.source_phone or "",
                    "status": "completed",
                    "retell_call_id": str(conversation_id)[:128] if conversation_id else "",
                    "duration_seconds": duration,
                    "recording_url": recording or False,
                    "transcript_url": False,
                    "raw_payload": (str(transcript)[:4000] if transcript else False),
                }
            )

    def action_play_ia_recording(self):
        self.ensure_one()
        url = self.ia_call_recording_url
        if not url:
            log = self.retell_call_log_ids.filtered("recording_url")[:1]
            url = log.recording_url if log else False
        if not url:
            return {
                "type": "ir.actions.client",
                "tag": "display_notification",
                "params": {
                    "title": "Enregistrement",
                    "message": "Aucun enregistrement disponible pour ce lead.",
                    "type": "warning",
                    "sticky": False,
                },
            }
        return {
            "type": "ir.actions.act_url",
            "url": url,
            "target": "new",
        }

    @api.model
    def _doorway_is_test_lead_vals(self, vals):
        """Détecte un lead de test E2E / sandbox."""
        name = (vals.get("name") or "").lower()
        email = (vals.get("email_from") or vals.get("source_email") or "").lower()
        contact = (vals.get("contact_name") or "").lower()
        patterns = (
            r"^e2e\b",
            r"\be2e\b",
            r"n8norch",
            r"haidlyorch",
            r"metahub",
            r"test e2e",
            r"hub e2e",
            r"prod e2e",
            r"^ping —",
            r"^test —",
            r"validation meta",
        )
        blob = " ".join((name, email, contact))
        if any(re.search(p, blob) for p in patterns):
            return True
        if "test.intellixcrm.com" in email:
            return True
        if email.startswith("e2e.") and "agencedoorway.com" in email:
            return True
        return False
