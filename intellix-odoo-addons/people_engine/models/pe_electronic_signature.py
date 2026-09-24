# -*- coding: utf-8 -*-
import hashlib
import logging
import random
import string
from datetime import timedelta

from odoo import api, fields, models
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


class PeElectronicSignature(models.Model):
    _name = "pe.electronic.signature"
    _description = "Signature électronique contrat"
    _rec_name = "document_name"

    # Document lié (HR — rétrocompat)
    contract_id = fields.Many2one(
        "pe.employment.contract", string="Contrat RH", ondelete="cascade"
    )
    profile_id = fields.Many2one("pe.employee.profile", string="Profil employé")

    # Document générique (Coins, futurs modules)
    res_model = fields.Char(string="Modèle document", index=True)
    res_id = fields.Integer(string="ID document", index=True)

    document_name = fields.Char(string="Document", required=True)

    state = fields.Selection(
        [
            ("pending", "En attente"),
            ("otp_sent", "OTP envoyé"),
            ("signed", "Signé"),
            ("expired", "Expiré"),
            ("refused", "Refusé"),
        ],
        default="pending",
        string="Statut",
    )

    token = fields.Char(string="Token", index=True)
    token_expiry = fields.Datetime(string="Expiry token")

    otp_code = fields.Char(string="Code OTP")
    otp_expiry = fields.Datetime(string="Expiry OTP")
    otp_attempts = fields.Integer(default=0)

    signed_at = fields.Datetime(string="Signé le")
    signed_ip = fields.Char(string="IP signataire")
    signed_by_email = fields.Char(string="Email / contact signataire")
    document_hash = fields.Char(string="Hash document")
    signature_certificate = fields.Text(string="Certificat de signature")

    signer_email = fields.Char(string="Email signataire")
    signer_name = fields.Char(string="Nom signataire")
    signer_phone = fields.Char(
        string="WhatsApp signataire",
        help="Si renseigné, OTP + lien aussi envoyés par WhatsApp.",
    )

    signed_pdf = fields.Binary(string="PDF signé")
    signed_pdf_name = fields.Char(string="Nom PDF signé")

    def _generate_token(self):
        return "".join(random.choices(string.ascii_letters + string.digits, k=48))

    def _generate_otp(self):
        return "".join(random.choices(string.digits, k=6))

    def _get_base_url(self):
        return self.env["ir.config_parameter"].sudo().get_param(
            "web.base.url", "https://intellixcrm.com"
        )

    def get_related_record(self):
        """Retourne le record document (HR contract ou générique)."""
        self.ensure_one()
        if self.res_model and self.res_id:
            if self.res_model in self.env:
                return self.env[self.res_model].sudo().browse(self.res_id).exists()
            return self.env[self.res_model].browse()
        if self.contract_id:
            return self.contract_id
        return self.env["pe.employment.contract"].browse()

    def get_document_html(self):
        """HTML affiché sur /sign/contract/<token>."""
        self.ensure_one()
        record = self.get_related_record()
        if not record:
            return ""
        if hasattr(record, "_get_signature_html"):
            try:
                return record._get_signature_html() or ""
            except Exception as e:  # noqa: BLE001
                _logger.warning("get_document_html callback fail: %s", e)
        # HR fallback (comportement historique)
        if record._name == "pe.employment.contract":
            contenu = record.contenu_html
            if contenu:
                contenu_str = str(contenu).strip()
                if contenu_str and contenu_str not in (
                    "<p><br></p>",
                    "<p></p>",
                    "<p><br/></p>",
                    "<br>",
                ):
                    return contenu_str
            profile = False
            if hasattr(record.employee_id, "pe_profile_id"):
                profile = record.employee_id.mapped("pe_profile_id")[:1]
            if not profile:
                profile = self.env["pe.employee.profile"].sudo().search(
                    [("employee_id", "=", record.employee_id.id)], limit=1
                )
            template = self.env["pe.document.template"].sudo().search(
                [
                    ("contract_subtype", "=", record.contract_type),
                    ("active", "=", True),
                ],
                limit=1,
            )
            if template and profile:
                try:
                    return template.render_letter_html(profile) or ""
                except Exception:  # noqa: BLE001
                    return ""
        return ""

    def _pe_is_quebec(self):
        rec = self.get_related_record()
        if rec and rec._name == "coins.entente" and hasattr(rec, "_coins_is_quebec_entente"):
            try:
                if rec._coins_is_quebec_entente():
                    return True
            except Exception:  # noqa: BLE001
                pass
        name = self.document_name or ""
        return "Coins Québec" in name or "Coins Quebec" in name

    def _pe_brand(self):
        """Pack marque pour l'email + le portail de signature."""
        rec = self.get_related_record()
        if rec and rec._name == "pe.employment.contract":
            company = ""
            if rec.company_id and rec.company_id.name:
                company = rec.company_id.name
            return {
                "kind": "hr",
                "emetteur": company or "Agence Doorway",
                "from_email": "zakaria@agencedoorway.com",
                "accent": "#6366f1",
                "ink": "#ffffff",
                "paper": "#0a0a12",
                "card": "#1a1a2e",
            }
        if self._pe_is_quebec():
            return {
                "kind": "cq",
                "emetteur": "Coins Québec / Agence Doorway",
                "from_email": "Martin Houle <martin@agencedoorway.com>",
                "accent": "#D9A94D",
                "ink": "#1F2A1E",
                "paper": "#F5F1E6",
                "card": "#1F2A1E",
            }
        return {
            "kind": "cm",
            "emetteur": "Coins Marocain / Digital Doorway SARL",
            "from_email": "Zakaria <zakaria@agencedoorway.com>",
            "accent": "#b5732f",
            "ink": "#3a2418",
            "paper": "#f6efe4",
            "card": "#3a2418",
        }

    def _pe_mail_server(self, email_from):
        """Boîte SMTP correspondant au From — sans ça, OTP part sans serveur et timeoute Canada→Mailcow."""
        addr = (email_from or "").strip()
        if "<" in addr and ">" in addr:
            addr = addr.split("<", 1)[1].split(">", 1)[0].strip()
        Server = self.env["ir.mail_server"].sudo()
        server = Server.search([("from_filter", "=", addr)], limit=1)
        if not server:
            server = Server.search([("smtp_user", "=", addr)], limit=1)
        return server

    def get_emetteur_name(self):
        self.ensure_one()
        return self._pe_brand()["emetteur"]

    def get_sign_url(self):
        """Lien personnel /sign/contract/<token> — email, WhatsApp ou SMS."""
        self.ensure_one()
        if not self.token:
            self.token = self._generate_token()
            self.token_expiry = fields.Datetime.now() + timedelta(days=7)
        return "%s/sign/contract/%s" % (self._get_base_url().rstrip("/"), self.token)

    def _pe_invite_email_html(self, sign_url):
        brand = self._pe_brand()
        name = self.signer_name or ""
        doc = self.document_name or "l'entente"
        if brand["kind"] == "cq":
            html = """
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background:#F5F1E6;font-family:Georgia,'Times New Roman',serif;">
  <tr><td align="center" style="padding:28px 16px;">
    <table role="presentation" width="600" cellpadding="0" cellspacing="0" style="max-width:600px;width:100%;background:#ffffff;border-radius:8px;overflow:hidden;">
      <tr>
        <td style="background:#1F2A1E;padding:0;line-height:0;" align="center">
          <img src="https://coinsquebec.com/assets/cq-email-header.png" width="600" alt="Coins Québec — Agence Doorway" style="display:block;width:100%;max-width:600px;height:auto;border:0;">
        </td>
      </tr>
      <tr>
        <td style="background:#ffffff;padding:32px 32px 28px;color:#1F2A1E;font-size:16px;line-height:1.6;">
          <p style="margin:0 0 16px;">Bonjour __NAME__,</p>
          <p style="margin:0 0 16px;">Comme convenu, voici l'entente de visibilité Coins Québec à valider — émise par <strong>Agence Doorway</strong>.</p>
          <p style="margin:0 0 22px;"><strong>__DOC__</strong></p>
          <p style="text-align:center;margin:0 0 20px;">
            <a href="__URL__" style="background:#D9A94D;color:#1F2A1E;padding:13px 26px;border-radius:24px;text-decoration:none;font-weight:bold;letter-spacing:.04em;display:inline-block;">Consulter et signer l'entente</a>
          </p>
          <p style="margin:0;font-size:13px;color:#6B7265;">Ce lien est valable 7 jours. Signature électronique, code OTP.</p>
          <p style="margin:22px 0 0;">Martin Houle<br/>Coins Québec — Agence Doorway</p>
        </td>
      </tr>
      <tr>
        <td style="background:#1F2A1E;padding:16px 32px;" align="center">
          <div style="color:#F5F1E6;font-size:11px;opacity:.75;">COINS QUÉBEC — AGENCE DOORWAY · MONTRÉAL</div>
        </td>
      </tr>
    </table>
  </td></tr>
</table>
"""
        elif brand["kind"] == "cm":
            html = """
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background:#f6efe4;font-family:Georgia,serif;">
  <tr><td align="center" style="padding:28px 16px;">
    <table role="presentation" width="600" style="max-width:600px;width:100%;">
      <tr><td style="background:#3a2418;padding:24px 32px;color:#f6efe4;" align="center">
        <div style="font-size:20px;">COINS MAROCAIN</div>
        <div style="color:#b5732f;font-size:11px;letter-spacing:.18em;margin-top:8px;">DIGITAL DOORWAY SARL</div>
      </td></tr>
      <tr><td style="background:#fff;padding:28px 32px;color:#3a2418;font-size:16px;line-height:1.6;">
        <p>Bonjour __NAME__,</p>
        <p>Vous êtes invité(e) à signer : <strong>__DOC__</strong></p>
        <p style="text-align:center;"><a href="__URL__" style="background:#b5732f;color:#fff;padding:12px 24px;border-radius:4px;text-decoration:none;font-weight:600;">Consulter et signer mon contrat</a></p>
        <p style="font-size:13px;color:#7a6554;">Ce lien est valable 7 jours.</p>
        <p>Zakaria<br/>Coins Marocain — Digital Doorway SARL</p>
      </td></tr>
    </table>
  </td></tr>
</table>
"""
        else:
            html = """
<p>Bonjour __NAME__,</p>
<p>Vous êtes invité(e) à signer : <strong>__DOC__</strong></p>
<p><a href="__URL__" style="background:#6366f1;color:white;padding:12px 24px;border-radius:6px;text-decoration:none;">Consulter et signer mon contrat</a></p>
<p>Ce lien est valable 7 jours.</p>
"""
        return (
            html.replace("__NAME__", name)
            .replace("__DOC__", doc)
            .replace("__URL__", sign_url or "")
        )

    def _notify_whatsapp(self, body):
        """Envoi WhatsApp best-effort (Twilio / n8n)."""
        self.ensure_one()
        phone = (self.signer_phone or "").strip()
        if not phone:
            return False
        try:
            from odoo.addons.coins_marocain.services.yasmine_service import (
                YasmineService,
            )

            return YasmineService(self.env).send_whatsapp(phone, body)
        except Exception as e:  # noqa: BLE001
            _logger.warning("PE signature WA fail: %s", e)
            try:
                from odoo.addons.doorway_messaging.services.whatsapp_service import (
                    WhatsAppService,
                )

                return WhatsAppService(self.env).send_whatsapp(
                    to_number=phone, body=body
                )
            except Exception as e2:  # noqa: BLE001
                _logger.warning("PE signature WA doorway fail: %s", e2)
        return False

    def _notify_sms(self, body):
        """SMS best-effort : Odoo sms, puis Twilio. Sinon False (le wizard ouvre sms:)."""
        self.ensure_one()
        phone = (self.signer_phone or "").strip()
        if not phone or not (body or "").strip():
            return False
        if "sms.api" in self.env:
            try:
                self.env["sms.api"].sudo()._send_sms([phone], body)
                return True
            except Exception as exc:  # noqa: BLE001
                _logger.warning("PE signature SMS odoo: %s", exc)
        icp = self.env["ir.config_parameter"].sudo()
        sid = (
            icp.get_param("twilio.account_sid")
            or icp.get_param("doorway_messaging.twilio_account_sid")
            or icp.get_param("coins_marocain.twilio_account_sid")
        )
        token = (
            icp.get_param("twilio.auth_token")
            or icp.get_param("doorway_messaging.twilio_auth_token")
            or icp.get_param("coins_marocain.twilio_auth_token")
        )
        sender = (
            icp.get_param("twilio.from_number")
            or icp.get_param("doorway_messaging.twilio_from")
            or icp.get_param("coins_marocain.twilio_from")
        )
        if sid and token and sender:
            try:
                import requests

                resp = requests.post(
                    "https://api.twilio.com/2010-04-01/Accounts/%s/Messages.json"
                    % sid,
                    data={"From": sender, "To": phone, "Body": body},
                    auth=(sid, token),
                    timeout=12,
                )
                if resp.ok:
                    return True
                _logger.warning("PE signature SMS twilio %s: %s", resp.status_code, resp.text[:200])
            except Exception as exc:  # noqa: BLE001
                _logger.warning("PE signature SMS twilio: %s", exc)
        return False

    @api.model
    def create_for_contract(self, contract, signer_email, signer_name, document_name):
        """Crée une demande de signature pour un contrat RH (rétrocompat)."""
        token = self._generate_token()
        profile_id = False
        if hasattr(contract.employee_id, "pe_profile_id") and contract.employee_id.pe_profile_id:
            profile_id = contract.employee_id.pe_profile_id.id
        return self.create(
            {
                "contract_id": contract.id,
                "res_model": "pe.employment.contract",
                "res_id": contract.id,
                "profile_id": profile_id,
                "document_name": document_name,
                "signer_email": signer_email,
                "signer_name": signer_name,
                "token": token,
                "token_expiry": fields.Datetime.now() + timedelta(days=7),
                "state": "pending",
            }
        )

    @api.model
    def create_for_document(
        self,
        record,
        signer_email,
        signer_name,
        document_name,
        signer_phone=None,
    ):
        """Crée une demande de signature pour tout record (Coins, etc.)."""
        token = self._generate_token()
        vals = {
            "res_model": record._name,
            "res_id": record.id,
            "document_name": document_name,
            "signer_email": signer_email or False,
            "signer_name": signer_name,
            "signer_phone": signer_phone or False,
            "token": token,
            "token_expiry": fields.Datetime.now() + timedelta(days=7),
            "state": "pending",
        }
        if record._name == "pe.employment.contract":
            vals["contract_id"] = record.id
        return self.create(vals)

    def action_send_signature_request(self):
        """Envoie email (+ WhatsApp si phone) avec le lien de signature."""
        self.ensure_one()
        sign_url = self.get_sign_url()

        brand = self._pe_brand()
        if self.signer_email:
            mail = self.env["mail.mail"].create(
                {
                    "email_to": self.signer_email,
                    "email_from": brand["from_email"],
                    "subject": "Signature requise — %s" % self.document_name,
                    "body_html": self._pe_invite_email_html(sign_url),
                }
            )
            mail.send()

        if self.signer_phone:
            if brand["kind"] == "cq":
                wa = (
                    "📄 Entente Coins Québec — Agence Doorway\n\n"
                    "%s\n\nOuvre ce lien pour signer :\n%s\n\nValable 7 jours."
                    % (self.document_name, sign_url)
                )
            else:
                wa = (
                    "📄 Signature requise — %s\n\nOuvre ce lien pour signer :\n%s\n\nValable 7 jours."
                    % (self.document_name, sign_url)
                )
            self._notify_whatsapp(wa)

        if not self.signer_email and not self.signer_phone:
            raise UserError(
                "Indiquez un email ou un numéro WhatsApp pour envoyer le lien de signature."
            )

        self.write({"state": "otp_sent"})
        _logger.info(
            "Signature request sent to %s / %s for %s",
            self.signer_email,
            self.signer_phone,
            self.document_name,
        )
        return True

    def action_send_otp(self, ip_address=""):
        """Génère et envoie le code OTP (email et/ou WhatsApp)."""
        self.ensure_one()
        otp = self._generate_otp()
        self.write(
            {
                "otp_code": otp,
                "otp_expiry": fields.Datetime.now() + timedelta(minutes=15),
                "otp_attempts": 0,
                "signed_ip": ip_address,
            }
        )
        brand = self._pe_brand()
        if self.signer_email:
            outgoing = self._pe_mail_server(brand["from_email"])
            mail_vals = {
                    "email_to": self.signer_email,
                    "email_from": brand["from_email"],
                    "subject": "Code de signature — %s" % self.document_name,
                    "body_html": """
<p>Bonjour %s,</p>
<p>Votre code de signature électronique est :</p>
<h2 style="font-size:36px;letter-spacing:8px;color:%s;">%s</h2>
<p>Ce code est valable <strong>15 minutes</strong>.</p>
<p style="font-size:13px;color:#6B7265;">%s</p>
"""
                    % (
                        self.signer_name or "",
                        brand["accent"],
                        otp,
                        brand["emetteur"],
                    ),
            }
            if outgoing:
                mail_vals["mail_server_id"] = outgoing.id
            mail = self.env["mail.mail"].sudo().create(mail_vals)
            mail.sudo().send()
        if self.signer_phone:
            label = (
                "Coins Québec / Agence Doorway"
                if brand["kind"] == "cq"
                else "Coins Marocain"
            )
            self._notify_whatsapp(
                "🔐 Code de signature %s : %s\nValable 15 minutes."
                % (label, otp)
            )
        if not self.signer_email and not self.signer_phone:
            raise UserError("Aucun canal pour envoyer l'OTP (email ou WhatsApp).")
        return True

    def action_verify_otp_and_sign(self, otp_entered, ip_address=""):
        """Vérifie le code OTP et finalise la signature."""
        self.ensure_one()
        if self.state == "signed":
            raise UserError("Ce document est déjà signé.")
        if self.otp_attempts >= 3:
            raise UserError("Trop de tentatives. Demandez un nouveau code.")
        if not self.otp_expiry or fields.Datetime.now() > self.otp_expiry:
            raise UserError("Code expiré. Demandez un nouveau code.")
        if otp_entered != self.otp_code:
            self.otp_attempts += 1
            raise UserError(
                "Code incorrect. %s tentative(s) restante(s)."
                % (3 - self.otp_attempts)
            )

        signed_at = fields.Datetime.now()
        cert = (
            "SIGNATURE ÉLECTRONIQUE CERTIFIÉE\n"
            "Document: %s\n"
            "Signataire: %s <%s>\n"
            "Date: %s UTC\n"
            "Adresse IP: %s\n"
            "Méthode: OTP 6 chiffres\n"
            "Émetteur: %s\n"
        ) % (
            self.document_name,
            self.signer_name,
            self.signer_email or self.signer_phone or "",
            signed_at.strftime("%d/%m/%Y à %H:%M:%S"),
            ip_address,
            self.get_emetteur_name(),
        )
        doc_hash = hashlib.sha256(cert.encode()).hexdigest()

        self.write(
            {
                "state": "signed",
                "signed_at": signed_at,
                "signed_ip": ip_address,
                "signed_by_email": self.signer_email or self.signer_phone,
                "document_hash": doc_hash,
                "signature_certificate": cert,
            }
        )
        record = self.get_related_record()
        if record and hasattr(record, "_on_electronic_signed"):
            try:
                record._on_electronic_signed(self)
            except Exception as e:  # noqa: BLE001
                _logger.exception("on_electronic_signed fail: %s", e)
        _logger.info(
            "Document signed by %s at %s from IP %s",
            self.signer_email or self.signer_phone,
            signed_at,
            ip_address,
        )
        return True
