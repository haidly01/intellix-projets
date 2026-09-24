import secrets

from odoo import _, api, models

TOKEN_KEY = "renovation_conciergerie.assurance_webhook_token"
TEAM_XMLID = "renovation_conciergerie.crm_team_assurance"


class RenovationAssuranceWebhook(models.AbstractModel):
    _name = "renovation.assurance.webhook"
    _description = "Webhook public — leads Assurance (Typeform / site)"

    @api.model
    def _ensure_assurance_webhook_token(self):
        icp = self.env["ir.config_parameter"].sudo()
        if not icp.get_param(TOKEN_KEY):
            icp.set_param(TOKEN_KEY, secrets.token_urlsafe(32))

    @api.model
    def _check_token(self, data):
        expected = self.env["ir.config_parameter"].sudo().get_param(TOKEN_KEY)
        if not expected:
            return True
        provided = data.get("token") or data.get("webhook_token")
        return provided == expected

    @api.model
    def _sel(self, field, value):
        """Associe une valeur entrante à une clé de sélection (par clé OU par libellé)."""
        if value in (None, ""):
            return False
        selection = dict(self.env["crm.lead"]._fields[field].selection)
        v = str(value).strip().lower()
        for key, label in selection.items():
            if v == key.lower() or v == (label or "").lower():
                return key
        return False

    @api.model
    def _first(self, data, *keys):
        for k in keys:
            val = data.get(k)
            if val not in (None, ""):
                return val
        return None

    @api.model
    def create_lead_from_payload(self, data):
        team = self.env.ref(TEAM_XMLID, raise_if_not_found=False)
        if not team:
            return {"status": "error", "message": _("Équipe Assurance introuvable.")}, 500

        contact_name = (self._first(data, "contact_name", "prenom", "first_name", "name_contact") or "").strip()
        email = (self._first(data, "email", "email_from", "courriel") or "").strip()
        phone = (self._first(data, "phone", "telephone", "tel", "mobile") or "").strip()
        zip_code = (self._first(data, "zip", "code_postal", "postal_code", "cp") or "").strip()

        if not email and not phone:
            return {
                "status": "error",
                "message": _("Au moins un email ou un téléphone est requis."),
            }, 400

        ins_type = self._sel("ins_type", self._first(data, "ins_type", "type_assurance", "type"))
        lead_name = (self._first(data, "name", "title") or "").strip()
        if not lead_name:
            type_label = dict(self.env["crm.lead"]._fields["ins_type"].selection).get(ins_type, "")
            base = type_label or "Assurance"
            who = contact_name or email or phone
            lead_name = f"Assurance {base} — {who}" if who else f"Assurance {base}"

        assignee = team._get_default_assignee()
        vals = {
            "name": lead_name,
            "type": "opportunity",
            "team_id": team.id,
            "contact_name": contact_name or False,
            "email_from": email or False,
            "phone": phone or False,
            "zip": zip_code or False,
            # Niveau 1
            "ins_type": ins_type,
            "ins_situation": self._sel("ins_situation", self._first(data, "ins_situation", "situation")),
            "ins_montant_mensuel": self._sel("ins_montant_mensuel", self._first(data, "ins_montant_mensuel", "montant_mensuel", "montant")),
            "ins_anciennete": self._sel("ins_anciennete", self._first(data, "ins_anciennete", "anciennete")),
            "ins_age": self._sel("ins_age", self._first(data, "ins_age", "age")),
            "ins_creneau_rappel": self._sel("ins_creneau_rappel", self._first(data, "ins_creneau_rappel", "creneau_rappel", "creneau")),
            # Optionnel si le formulaire le transmet (sinon rempli en Niveau 2)
            "ins_delai_souscription": self._sel("ins_delai_souscription", self._first(data, "ins_delai_souscription", "delai_souscription", "delai")),
            # Niveau 3
            "ins_source_acquisition": self._sel("ins_source_acquisition", self._first(data, "ins_source_acquisition", "source", "utm_source")),
        }
        new_stage = self.env.ref(
            "renovation_conciergerie.crm_stage_assurance_new", raise_if_not_found=False
        )
        if new_stage:
            vals["stage_id"] = new_stage.id
        if assignee:
            vals["user_id"] = assignee.id
        company = team.company_id or (assignee.company_id if assignee else False)
        if company:
            vals["company_id"] = company.id

        lead = self.env["crm.lead"].sudo().create(vals)
        stage = lead.stage_id
        return {
            "status": "success",
            "lead_id": lead.id,
            "team_id": team.id,
            "team_name": team.name,
            "stage_id": stage.id if stage else False,
            "stage_name": stage.name if stage else False,
            "score": lead.ins_score,
        }, 200
