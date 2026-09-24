# -*- coding: utf-8 -*-
from odoo import http
from odoo.http import request


class VicidialWebphoneController(http.Controller):

    def _check_access(self):
        return request.env.user.has_group(
            "doorway_vicidial_campaigns.group_vicidial_qualifier"
        )

    @http.route(
        "/doorway/vicidial/webphone",
        type="http",
        auth="user",
        methods=["GET"],
        csrf=False,
    )
    def webphone_standalone(self, **kwargs):
        if not self._check_access():
            return request.not_found()
        Session = request.env["doorway.vicidial.agent.session"].sudo()
        session = Session.get_active_session()
        if not session or not session.vicidial_user:
            return request.make_response(
                _standalone_html(
                    title="Téléphone IntelliX",
                    error="Aucune session active. Démarrez d'abord votre poste d'appels.",
                ),
                headers=[("Content-Type", "text/html; charset=utf-8")],
            )
        from odoo.addons.doorway_vicidial_campaigns.services.vicidial_service import (
            VicidialService,
        )

        svc = VicidialService(request.env)
        live = svc.get_agent_live_status(session.vicidial_user)
        phone_ext = svc.get_agent_phone_extension(session.vicidial_user)
        registered = svc.get_webphone_call_ready(
            session.vicidial_user, live.get("conf_exten")
        )
        url = svc.build_webphone_embed_url(
            session.vicidial_user,
            session.campaign_id.vicidial_campaign_id,
            conf_exten=live.get("conf_exten"),
            layout="embed",
        )
        return request.make_response(
            _standalone_html(
                title="Téléphone IntelliX",
                agent=session.vicidial_user,
                campaign=session.campaign_id.name or "",
                viciphone_url=url,
                vicidial_status=live.get("status") or "",
                registered=registered,
            ),
            headers=[("Content-Type", "text/html; charset=utf-8")],
        )


def _standalone_html(
    title,
    viciphone_url="",
    agent="",
    campaign="",
    vicidial_status="",
    registered=False,
    error="",
):
    if error:
        body = f"""
        <div class="ix-shell ix-shell--error">
          <h1>{title}</h1>
          <p class="ix-msg">{error}</p>
          <a class="ix-btn" href="/odoo/action-1121">Retour au poste d'appels</a>
        </div>"""
    else:
        reg_badge = (
            '<span class="ix-badge ix-badge--ok">Téléphone connecté</span>'
            if registered
            else '<span class="ix-badge ix-badge--warn">Connexion en cours…</span>'
        )
        body = f"""
        <div class="ix-shell">
          <header class="ix-header">
            <h1>{title}</h1>
            <p class="ix-sub">Agent <strong>{agent}</strong> — {campaign}</p>
            <div class="ix-badges">
              <span class="ix-badge ix-badge--info">{vicidial_status or 'Session'}</span>
              {reg_badge}
            </div>
          </header>
          <ol class="ix-steps">
            <li>Autorisez le <strong>microphone</strong> si Chrome le demande.</li>
            <li>Attendez la <strong>pastille verte</strong> et le texte <strong>« En ligne »</strong> (ou « Incall »).</li>
            <li>Si « Non connecté » : cliquez l’icône <strong>téléphone bleue</strong> sous le logo.</li>
          </ol>
          <iframe
            class="ix-phone"
            src="{viciphone_url}"
            allow="microphone *; autoplay *"
            title="ViciPhone WebRTC"
          ></iframe>
          <footer class="ix-footer">
            <a class="ix-btn ix-btn--ghost" href="/odoo/action-1121">← Retour au poste d'appels</a>
          </footer>
        </div>"""
    return f"""<!DOCTYPE html>
<html lang="fr">
<head>
  <meta charset="utf-8"/>
  <meta name="viewport" content="width=device-width, initial-scale=1"/>
  <title>{title}</title>
  <style>
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      min-height: 100vh;
      background: linear-gradient(160deg, #1a1a2e 0%, #16213e 45%, #0f3460 100%);
      color: #e2e8f0;
      font-family: system-ui, -apple-system, "Segoe UI", Roboto, sans-serif;
      display: flex;
      align-items: center;
      justify-content: center;
      padding: 24px 16px;
    }}
    .ix-shell {{
      width: min(560px, 100%);
      background: rgba(15, 23, 42, 0.92);
      border: 1px solid #334155;
      border-radius: 16px;
      padding: 1.5rem 1.75rem 1.25rem;
      box-shadow: 0 24px 48px rgba(0,0,0,0.35);
    }}
    .ix-shell--error {{ text-align: center; }}
    .ix-header h1 {{
      margin: 0 0 0.35rem;
      font-size: 1.35rem;
      color: #fff;
    }}
    .ix-sub {{ margin: 0 0 0.75rem; color: #94a3b8; font-size: 0.95rem; }}
    .ix-badges {{ display: flex; flex-wrap: wrap; gap: 0.5rem; margin-bottom: 1rem; }}
    .ix-badge {{
      display: inline-block;
      padding: 0.25rem 0.65rem;
      border-radius: 999px;
      font-size: 0.8rem;
      font-weight: 600;
    }}
    .ix-badge--info {{ background: #1e40af; color: #dbeafe; }}
    .ix-badge--ok {{ background: #14532d; color: #bbf7d0; }}
    .ix-badge--warn {{ background: #78350f; color: #fde68a; }}
    .ix-steps {{
      margin: 0 0 1rem 1.1rem;
      padding: 0;
      color: #cbd5e1;
      font-size: 0.92rem;
      line-height: 1.5;
    }}
    .ix-phone {{
      display: block;
      width: 100%;
      max-width: 460px;
      height: 280px;
      margin: 0 auto;
      border: 1px solid #475569;
      border-radius: 12px;
      background: #f8fafc;
    }}
    .ix-footer {{ margin-top: 1rem; text-align: center; }}
    .ix-btn {{
      display: inline-block;
      padding: 0.55rem 1rem;
      border-radius: 8px;
      background: #6366f1;
      color: #fff;
      text-decoration: none;
      font-weight: 600;
      font-size: 0.9rem;
    }}
    .ix-btn--ghost {{ background: transparent; border: 1px solid #475569; color: #cbd5e1; }}
    .ix-msg {{ color: #fca5a5; margin: 1rem 0; }}
  </style>
</head>
<body>{body}</body>
</html>"""
