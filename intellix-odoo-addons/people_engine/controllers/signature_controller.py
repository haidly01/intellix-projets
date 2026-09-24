# -*- coding: utf-8 -*-
import html as html_lib
import json
import logging
from datetime import datetime

from odoo import http
from odoo.http import request

_logger = logging.getLogger(__name__)


def _pe_sign_theme(sig):
    """CSS du portail selon la marque (CQ / CM / RH)."""
    brand = {"kind": "hr"}
    if hasattr(sig, "_pe_brand"):
        try:
            brand = sig._pe_brand()
        except Exception:  # noqa: BLE001
            brand = {"kind": "hr"}
    kind = brand.get("kind") or "hr"
    if kind == "cq":
        return {
            "kind": "cq",
            "title": "Signature — Coins Québec",
            "kicker": "Agence Doorway · Montréal",
            "body_bg": "#F5F1E6",
            "body_fg": "#1F2A1E",
            "card_bg": "#1F2A1E",
            "card_fg": "#F5F1E6",
            "accent": "#D9A94D",
            "btn_fg": "#1F2A1E",
            "border": "#D9A94D",
            "input_bg": "#F5F1E6",
            "input_fg": "#1F2A1E",
            "muted": "#C4B89A",
            "error": "#C45C4A",
            "ok": "#D9A94D",
            "font": "Georgia, 'Times New Roman', serif",
            "radius": "8px",
            "btn_radius": "24px",
        }
    if kind == "cm":
        return {
            "kind": "cm",
            "title": "Signature — Coins Marocain",
            "kicker": "Digital Doorway SARL",
            "body_bg": "#f6efe4",
            "body_fg": "#3a2418",
            "card_bg": "#3a2418",
            "card_fg": "#f6efe4",
            "accent": "#b5732f",
            "btn_fg": "#ffffff",
            "border": "#b5732f",
            "input_bg": "#f6efe4",
            "input_fg": "#3a2418",
            "muted": "#c4b49a",
            "error": "#d97757",
            "ok": "#b5732f",
            "font": "Georgia, 'Times New Roman', serif",
            "radius": "8px",
            "btn_radius": "4px",
        }
    return {
        "kind": "hr",
        "title": "Signature électronique",
        "kicker": "",
        "body_bg": "#0a0a12",
        "body_fg": "#ffffff",
        "card_bg": "#1a1a2e",
        "card_fg": "#ffffff",
        "accent": "#6366f1",
        "btn_fg": "#ffffff",
        "border": "#6366f1",
        "input_bg": "#0a0a12",
        "input_fg": "#ffffff",
        "muted": "#aaaaaa",
        "error": "#f87171",
        "ok": "#06b6d4",
        "font": "Arial, sans-serif",
        "radius": "12px",
        "btn_radius": "8px",
    }


class SignatureController(http.Controller):

    @http.route("/sign/contract/<string:token>", type="http", auth="public", website=False)
    def sign_page(self, token, **kwargs):
        """Page de signature du contrat (HR + documents génériques)."""
        sig = request.env["pe.electronic.signature"].sudo().search(
            [
                ("token", "=", token),
                ("state", "in", ["pending", "otp_sent"]),
            ],
            limit=1,
        )

        if not sig:
            return request.make_response(
                "<h2>Lien invalide ou expiré.</h2>",
                headers=[("Content-Type", "text/html")],
            )

        if sig.token_expiry and sig.token_expiry < datetime.now():
            sig.write({"state": "expired"})
            return request.make_response(
                "<h2>Ce lien a expiré.</h2>",
                headers=[("Content-Type", "text/html")],
            )

        contract_html = sig.get_document_html() or ""
        emetteur = sig.get_emetteur_name()
        contact_hint = sig.signer_email or sig.signer_phone or "votre contact"
        theme = _pe_sign_theme(sig)
        doc = html_lib.escape(sig.document_name or "")
        signer = html_lib.escape(sig.signer_name or "")
        emetteur_e = html_lib.escape(emetteur or "")
        contact_e = html_lib.escape(contact_hint)
        token_e = html_lib.escape(token)
        kicker = (
            '<div class="kicker">%s</div>' % html_lib.escape(theme["kicker"])
            if theme.get("kicker")
            else ""
        )
        contract_block = (
            '<div class="contract-content">%s</div>' % contract_html
            if contract_html
            else ""
        )

        html = f"""<!DOCTYPE html>
<html lang="fr">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Signature — {doc}</title>
<style>
  body {{ font-family: {theme["font"]}; max-width: 800px; margin: 40px auto; padding: 20px; background: {theme["body_bg"]}; color: {theme["body_fg"]}; }}
  .card {{ background: {theme["card_bg"]}; color: {theme["card_fg"]}; border-radius: {theme["radius"]}; padding: 30px; border: 1px solid {theme["border"]}; margin-bottom: 20px; }}
  .kicker {{ color: {theme["accent"]}; font-size: 11px; letter-spacing: .22em; text-transform: uppercase; margin-bottom: 10px; }}
  .contract-content {{ background: #fff; color: #1F2A1E; border-radius: {theme["radius"]}; padding: 30px; margin: 20px 0; }}
  h1 {{ color: {theme["accent"]}; margin: 0 0 16px; font-size: 26px; }}
  .btn {{ background: {theme["accent"]}; color: {theme["btn_fg"]}; padding: 14px 28px; border: none; border-radius: {theme["btn_radius"]}; cursor: pointer; font-size: 16px; width: 100%; margin-top: 16px; font-weight: 600; letter-spacing: .03em; }}
  .btn:hover {{ opacity: 0.92; }}
  .btn-secondary {{ background: transparent; color: {theme["card_fg"]}; border: 1px solid {theme["border"]}; }}
  input {{ width: 100%; padding: 12px; border-radius: 8px; border: 1px solid {theme["border"]}; background: {theme["input_bg"]}; color: {theme["input_fg"]}; font-size: 18px; text-align: center; letter-spacing: 8px; margin-top: 12px; box-sizing: border-box; }}
  .info {{ background: {theme["body_bg"]}; color: {theme["body_fg"]}; padding: 16px; border-radius: 8px; margin: 16px 0; font-size: 14px; }}
  .success {{ color: {theme["ok"]}; font-size: 18px; text-align: center; padding: 20px; }}
  .error {{ color: {theme["error"]}; margin-top: 8px; }}
  .meta {{ color: {theme["muted"]}; }}
</style>
</head>
<body>
<div class="card">
  {kicker}
  <h1>{html_lib.escape(theme["title"])}</h1>
  <p><strong>Document :</strong> {doc}</p>
  <p><strong>Signataire :</strong> {signer}</p>
  <p><strong>Émetteur :</strong> {emetteur_e}</p>
</div>

{contract_block}

<div class="card">
  <div class="info">
    En signant ce document, vous acceptez les termes et conditions de l'entente.
    Un code de vérification sera envoyé à <strong>{contact_e}</strong>.
  </div>

  <div id="step1">
    <button class="btn" onclick="requestOTP()">Recevoir mon code de signature</button>
  </div>

  <div id="step2" style="display:none">
    <p>Code envoyé à <strong>{contact_e}</strong></p>
    <input type="text" id="otpInput" placeholder="000000" maxlength="6">
    <div id="otpError" class="error"></div>
    <button class="btn" onclick="verifySig()">Signer le document</button>
    <button class="btn btn-secondary" onclick="requestOTP()">Renvoyer le code</button>
  </div>

  <div id="step3" style="display:none" class="success">
    <h2>Document signé</h2>
    <p>Votre signature a été enregistrée.</p>
  </div>
</div>

<script>
const token = '{token_e}';

async function requestOTP() {{
  const res = await fetch('/sign/send-otp/' + token, {{method: 'POST'}});
  const data = await res.json();
  if (data.ok) {{
    document.getElementById('step1').style.display = 'none';
    document.getElementById('step2').style.display = 'block';
  }} else {{
    alert(data.error || 'Erreur envoi OTP');
  }}
}}

async function verifySig() {{
  const otp = document.getElementById('otpInput').value;
  const res = await fetch('/sign/verify/' + token, {{
    method: 'POST',
    headers: {{'Content-Type': 'application/json'}},
    body: JSON.stringify({{jsonrpc: '2.0', method: 'call', params: {{otp: otp}}, id: 1}})
  }});
  const payload = await res.json();
  const data = payload.result || payload;
  if (data.ok) {{
    document.getElementById('step2').style.display = 'none';
    document.getElementById('step3').style.display = 'block';
  }} else {{
    document.getElementById('otpError').textContent = data.error || 'Code incorrect';
  }}
}}
</script>
</body>
</html>"""
        return request.make_response(
            html, headers=[("Content-Type", "text/html; charset=utf-8")]
        )

    @http.route(
        "/sign/send-otp/<string:token>",
        type="http",
        auth="public",
        methods=["POST"],
        csrf=False,
    )
    def send_otp(self, token, **kwargs):
        sig = request.env["pe.electronic.signature"].sudo().search(
            [("token", "=", token)], limit=1
        )
        if not sig:
            return request.make_response(
                json.dumps({"ok": False, "error": "Token invalide"}),
                headers=[("Content-Type", "application/json")],
            )
        try:
            ip = request.httprequest.remote_addr
            sig.action_send_otp(ip_address=ip)
            return request.make_response(
                json.dumps({"ok": True}),
                headers=[("Content-Type", "application/json")],
            )
        except Exception as e:  # noqa: BLE001
            return request.make_response(
                json.dumps({"ok": False, "error": str(e)}),
                headers=[("Content-Type", "application/json")],
            )

    @http.route(
        "/sign/verify/<string:token>",
        type="jsonrpc",
        auth="public",
        methods=["POST"],
        csrf=False,
    )
    def verify_otp(self, token, otp="", **kwargs):
        sig = request.env["pe.electronic.signature"].sudo().search(
            [("token", "=", token)], limit=1
        )
        if not sig:
            return {"ok": False, "error": "Token invalide"}
        try:
            ip = request.httprequest.remote_addr
            # jsonrpc may pass otp in kwargs
            code = otp or kwargs.get("otp") or ""
            sig.action_verify_otp_and_sign(code, ip_address=ip)
            return {"ok": True}
        except Exception as e:  # noqa: BLE001
            return {"ok": False, "error": str(e)}
