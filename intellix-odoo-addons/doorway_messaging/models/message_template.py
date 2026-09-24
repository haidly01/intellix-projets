# -*- coding: utf-8 -*-
import json
import logging

import requests

from odoo import _, api, fields, models
from odoo.exceptions import UserError

from .channel_config import CANAL_SELECTION

_logger = logging.getLogger(__name__)

TWILIO_CONTENT_API = "https://content.twilio.com/v1/Content"

TWILIO_STATUS = [
    ("draft", "Brouillon"),
    ("unsubmitted", "Non soumis"),
    ("pending", "En attente d'approbation"),
    ("approved", "Approuvé"),
    ("rejected", "Rejeté"),
]


class DoorwayMessageTemplate(models.Model):
    _name = "doorway.message.template"
    _description = "Template message modifiable par canal"
    _order = "name"

    name = fields.Char("Nom", required=True)
    canal = fields.Selection(
        CANAL_SELECTION + [("master", "Message maître")],
        string="Canal",
        default="master",
    )
    sujet = fields.Char("Sujet (email)")
    corps = fields.Html("Contenu")
    corps_text = fields.Text("Contenu texte")
    actif = fields.Boolean(default=True)
    description = fields.Text("Notes")

    # --- Twilio Content (templates approuvés WhatsApp / SMS) ---
    twilio_content_sid = fields.Char(
        "Twilio Content SID (HX…)",
        help="Identifiant du template Twilio Content (commence par HX).",
    )
    twilio_status = fields.Selection(
        TWILIO_STATUS, string="Statut Twilio", default="draft"
    )
    twilio_language = fields.Char("Langue Twilio", default="fr")
    twilio_messaging_service_sid = fields.Char(
        "Messaging Service SID (MG…)",
        help="Optionnel : Messaging Service Twilio à utiliser pour ce template.",
    )
    twilio_variables = fields.Text(
        "Variables ({{n}} → champ destinataire)",
        help=(
            "JSON associant le numéro de variable Twilio au champ destinataire.\n"
            'Ex : {"1": "name", "2": "phone"} remplit {{1}} par le nom et '
            "{{2}} par le téléphone du destinataire."
        ),
    )
    is_twilio_ready = fields.Boolean(
        "Prêt (Twilio)", compute="_compute_is_twilio_ready", store=True
    )

    @api.depends("canal", "twilio_content_sid", "twilio_status")
    def _compute_is_twilio_ready(self):
        for rec in self:
            rec.is_twilio_ready = bool(
                rec.canal in ("sms", "whatsapp")
                and rec.twilio_content_sid
                and rec.twilio_status == "approved"
            )

    def _variable_map(self):
        self.ensure_one()
        if not self.twilio_variables:
            return {}
        try:
            data = json.loads(self.twilio_variables)
            return {str(k): str(v) for k, v in data.items()}
        except Exception:  # noqa: BLE001
            return {}

    def build_content_variables(self, recipient):
        """Construit le dict ContentVariables Twilio pour un destinataire.

        ``recipient`` est un dict (cf. campaign._collect_recipients) contenant
        au moins ``name``/``email``/``phone``.
        """
        self.ensure_one()
        mapping = self._variable_map()
        out = {}
        for key, field_name in mapping.items():
            out[key] = str((recipient or {}).get(field_name) or "")
        return out

    # ------------------------------------------------------------------
    # Synchronisation Twilio (lecture seule — aucun message envoyé)
    # ------------------------------------------------------------------
    @api.model
    def _twilio_creds(self):
        icp = self.env["ir.config_parameter"].sudo()
        sid = icp.get_param("doorway_messaging.twilio_account_sid") or icp.get_param(
            "doorway_agents_dashboard.twilio_account_sid"
        )
        token = icp.get_param("doorway_messaging.twilio_auth_token") or icp.get_param(
            "doorway_agents_dashboard.twilio_auth_token"
        )
        return sid, token

    def action_sync_twilio_templates(self):
        """Importe les templates Twilio Content et leur statut d'approbation.

        Appel API en lecture seule (liste des Content + ApprovalRequests).
        N'envoie aucun message et n'engendre aucun coût.
        """
        sid, token = self._twilio_creds()
        if not (sid and token):
            raise UserError(
                _("Configurez d'abord le SID et le token Twilio (Paramètres → Messaging).")
            )

        created = updated = 0
        url = TWILIO_CONTENT_API
        try:
            while url:
                resp = requests.get(url, auth=(sid, token), timeout=30)
                if resp.status_code >= 400:
                    raise UserError(
                        _("Erreur Twilio Content API: %s") % resp.text
                    )
                data = resp.json() or {}
                for content in data.get("contents", []):
                    if self._upsert_twilio_content(content, sid, token):
                        created += 1
                    else:
                        updated += 1
                meta = data.get("meta") or {}
                url = meta.get("next_page_url")
        except UserError:
            raise
        except Exception as exc:  # noqa: BLE001
            _logger.exception("Sync Twilio templates: %s", exc)
            raise UserError(_("Synchronisation Twilio impossible: %s") % exc)

        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": _("Templates Twilio synchronisés"),
                "message": _("%s créés, %s mis à jour.") % (created, updated),
                "type": "success",
                "sticky": False,
            },
        }

    def _upsert_twilio_content(self, content, sid, token):
        """Crée/maj un template depuis un objet Content Twilio. Renvoie True si créé.

        Le canal est déterminé par la demande d'approbation WhatsApp
        (endpoint ApprovalRequests), PAS par le préfixe des ``types`` : les
        templates WhatsApp ont des types ``twilio/...`` (texte, quick-reply,
        media…) et ne se distinguent que par leur approbation ``type=whatsapp``.
        """
        content_sid = content.get("sid")
        if not content_sid:
            return False

        approval = self._twilio_approval(content_sid, sid, token)
        wa_status = (approval.get("status") or "").lower()
        is_whatsapp = approval.get("type") == "whatsapp" or bool(wa_status)

        if is_whatsapp:
            canal = "whatsapp"
            status = wa_status if wa_status in dict(TWILIO_STATUS) else "pending"
        else:
            # Un template Content non soumis à WhatsApp reste utilisable en SMS.
            canal = "sms"
            status = "approved"

        types = content.get("types") or {}
        body_text = ""
        for tdef in types.values():
            if isinstance(tdef, dict) and tdef.get("body"):
                body_text = tdef["body"]
                break

        vals = {
            "name": content.get("friendly_name") or content_sid,
            "canal": canal,
            "corps_text": body_text,
            "twilio_content_sid": content_sid,
            "twilio_status": status,
            "twilio_language": content.get("language") or "fr",
        }
        existing = self.search(
            [("twilio_content_sid", "=", content_sid)], limit=1
        )
        if existing:
            existing.write(vals)
            return False
        self.create(vals)
        return True

    def _twilio_approval(self, content_sid, sid, token):
        """Renvoie l'objet d'approbation WhatsApp Twilio (lecture seule).

        Forme attendue : {"status": "approved", "type": "whatsapp", ...}.
        Renvoie {} si non soumis ou en erreur.
        """
        try:
            url = "%s/%s/ApprovalRequests" % (TWILIO_CONTENT_API, content_sid)
            resp = requests.get(url, auth=(sid, token), timeout=30)
            if resp.status_code >= 400:
                return {}
            data = resp.json() or {}
            return data.get("whatsapp") or {}
        except Exception:  # noqa: BLE001
            return {}
