# -*- coding: utf-8 -*-
import json
import logging
from html import escape

from odoo import _, api, models

_logger = logging.getLogger(__name__)


class IntellixSupportDiagnosticEngine(models.AbstractModel):
    _name = "intellix.support.diagnostic.engine"
    _description = "Moteur diagnostic support Intellix"

    @api.model
    def run_for_ticket(self, ticket):
        ticket.ensure_one()
        checks = []
        checks.extend(self._check_partner(ticket))
        checks.extend(self._check_user_account(ticket))
        checks.extend(self._check_campaigns(ticket))
        checks.extend(self._check_credits(ticket))
        checks.extend(self._check_anydesk_readiness(ticket))

        passed = sum(1 for c in checks if c["status"] == "ok")
        failed = sum(1 for c in checks if c["status"] == "fail")
        warning = sum(1 for c in checks if c["status"] == "warn")
        side_origin = self._infer_side_origin(checks)

        summary_html = self._render_summary(checks, side_origin)
        diagnostic = self.env["intellix.support.diagnostic"].create(
            {
                "ticket_id": ticket.id,
                "side_origin": side_origin,
                "summary_html": summary_html,
                "result_json": json.dumps(checks, ensure_ascii=False, indent=2),
                "checks_passed": passed,
                "checks_failed": failed,
                "checks_warning": warning,
                "state": "done",
            }
        )
        ticket.copilot_summary = self._build_copilot_summary(checks, side_origin)
        suggestions = self._build_copilot_suggestions(checks, side_origin)
        replies_html, replies_plain = self._build_copilot_replies(ticket, checks, side_origin)
        ticket.copilot_suggestions = suggestions + replies_html
        ticket.copilot_replies_html = replies_html
        ticket.copilot_replies_data = json.dumps(replies_plain, ensure_ascii=False)
        if side_origin:
            ticket.side_origin = side_origin
        self.env["intellix.support.alert.dispatcher"].dispatch_for_ticket(ticket)
        self.env["intellix.support.cursor.bridge"].maybe_dispatch_after_diagnostic(ticket)
        return diagnostic

    @api.model
    def _check_partner(self, ticket):
        partner = ticket.partner_id
        if not partner:
            return [
                {
                    "code": "partner_missing",
                    "label": _("Client"),
                    "status": "warn",
                    "detail": _("Aucun client lié au ticket."),
                    "side": "unknown",
                }
            ]
        return [
            {
                "code": "partner_ok",
                "label": _("Client"),
                "status": "ok",
                "detail": _("%(name)s — %(phone)s") % {
                    "name": partner.display_name,
                    "phone": partner.phone or "—",
                },
                "side": "unknown",
            }
        ]

    @api.model
    def _check_user_account(self, ticket):
        user = ticket.contact_user_id
        if not user:
            if ticket.partner_id and ticket.partner_id.user_ids:
                user = ticket.partner_id.user_ids[:1]
        if not user:
            return [
                {
                    "code": "user_missing",
                    "label": _("Compte Odoo"),
                    "status": "warn",
                    "detail": _("Aucun utilisateur lié — vérifier accès / invitation."),
                    "side": "client",
                }
            ]
        status = "ok" if user.active else "fail"
        detail = _("%(login)s — actif=%(active)s, dernière connexion=%(login_date)s") % {
            "login": user.login,
            "active": user.active,
            "login_date": user.login_date or _("jamais"),
        }
        return [
            {
                "code": "user_account",
                "label": _("Compte Odoo"),
                "status": status,
                "detail": detail,
                "side": "client" if status != "ok" else "unknown",
            }
        ]

    @api.model
    def _check_campaigns(self, ticket):
        if "doorway.campaign" not in self.env:
            return [
                {
                    "code": "campaign_module",
                    "label": _("Campagnes VICIdial"),
                    "status": "warn",
                    "detail": _("Module doorway_vicidial_campaigns non installé."),
                    "side": "unknown",
                }
            ]
        Campaign = self.env["doorway.campaign"]
        domain = [("state", "in", ("active", "paused", "ready"))]
        if ticket.contact_user_id:
            domain = [
                ("human_agent_user_ids", "in", ticket.contact_user_id.id),
            ]
        campaigns = Campaign.search(domain, limit=5)
        if not campaigns:
            return [
                {
                    "code": "campaign_none",
                    "label": _("Campagnes"),
                    "status": "warn",
                    "detail": _("Aucune campagne trouvée pour ce client."),
                    "side": "unknown",
                }
            ]
        lines = []
        platform_issues = 0
        for camp in campaigns:
            state = getattr(camp, "state", False) or "?"
            adl = getattr(camp, "dial_level", None) or getattr(camp, "dial_ratio", None)
            line = _("%(name)s — état %(state)s") % {"name": camp.name, "state": state}
            if adl is not None:
                line += f", ADL={adl}"
            lines.append(line)
            if state != "active":
                platform_issues += 1
        status = "ok" if platform_issues == 0 else "warn"
        return [
            {
                "code": "campaign_status",
                "label": _("Campagnes"),
                "status": status,
                "detail": "; ".join(lines),
                "side": "platform" if platform_issues else "unknown",
            }
        ]

    @api.model
    def _check_credits(self, ticket):
        if "doorway.credit.account" not in self.env:
            return []
        Tenant = self.env.get("doorway.tenant")
        account = self.env["doorway.credit.account"]
        if Tenant and ticket.partner_id:
            tenant = Tenant.search(
                [
                    "|",
                    ("email_admin", "=", ticket.partner_id.email or ""),
                    ("company_id.partner_id", "child_of", ticket.partner_id.id),
                ],
                limit=1,
            )
            if tenant and tenant.credit_account_id:
                account = tenant.credit_account_id
            else:
                account = account.browse()
        else:
            account = account.browse()
        if not account:
            return [
                {
                    "code": "credits_none",
                    "label": _("Crédits IA"),
                    "status": "warn",
                    "detail": _("Compte crédits introuvable."),
                    "side": "unknown",
                }
            ]
        balance = getattr(account, "balance", None)
        status = "ok"
        side = "unknown"
        if balance is not None and balance <= 0:
            status = "fail"
            side = "platform"
        return [
            {
                "code": "credits_balance",
                "label": _("Crédits IA"),
                "status": status,
                "detail": _("Solde : %(balance)s") % {"balance": balance if balance is not None else "?"},
                "side": side,
            }
        ]

    @api.model
    def _check_anydesk_readiness(self, ticket):
        anydesk = ticket.anydesk_id or (
            ticket.partner_id.support_anydesk_id if ticket.partner_id else False
        )
        if not anydesk:
            return [
                {
                    "code": "anydesk_missing",
                    "label": _("AnyDesk"),
                    "status": "warn",
                    "detail": _("ID AnyDesk non renseigné — session distante impossible."),
                    "side": "client",
                }
            ]
        consent = ticket.anydesk_consent
        status = "ok" if consent else "warn"
        return [
            {
                "code": "anydesk_ready",
                "label": _("AnyDesk"),
                "status": status,
                "detail": _("ID %(id)s — consentement=%(consent)s") % {
                    "id": anydesk,
                    "consent": _("oui") if consent else _("non"),
                },
                "side": "client",
            }
        ]

    @api.model
    def _infer_side_origin(self, checks):
        platform = sum(1 for c in checks if c.get("side") == "platform" and c["status"] != "ok")
        client = sum(1 for c in checks if c.get("side") == "client" and c["status"] != "ok")
        if platform > client:
            return "platform"
        if client > platform:
            return "client"
        return "unknown"

    @api.model
    def _render_summary(self, checks, side_origin):
        labels = {
            "ok": "✅",
            "warn": "⚠️",
            "fail": "❌",
        }
        side_labels = {
            "unknown": _("Non déterminé"),
            "client": _("Probable côté client"),
            "platform": _("Probable côté Intellix"),
        }
        rows = []
        for check in checks:
            icon = labels.get(check["status"], "•")
            rows.append(
                f"<li>{icon} <strong>{escape(check['label'])}</strong> — "
                f"{escape(check['detail'])}</li>"
            )
        return (
            f"<p><strong>{escape(_('Origine probable'))}:</strong> "
            f"{escape(side_labels.get(side_origin, side_origin))}</p>"
            f"<ul>{''.join(rows)}</ul>"
        )

    @api.model
    def _build_copilot_summary(self, checks, side_origin):
        issues = [c for c in checks if c["status"] in ("fail", "warn")]
        if not issues:
            return _("Aucun problème détecté par le diagnostic automatique.")
        parts = [c["label"] + ": " + c["detail"] for c in issues[:5]]
        return "\n".join(parts)

    @api.model
    def _diag_card(self, css_class, icon, title, subtitle, text, actions):
        buttons = []
        for item in actions:
            if len(item) == 3:
                label, kind, action_code = item
            else:
                label, kind = item
                action_code = None
            if action_code:
                buttons.append(
                    f'<a href="#" role="button" class="diag-btn diag-btn-{kind} '
                    f'copilot-act-{escape(action_code)}">{escape(label)}</a>'
                )
            else:
                buttons.append(
                    f'<span class="diag-btn diag-btn-{kind}">{escape(label)}</span>'
                )
        return (
            f'<div class="diag-card {css_class}">'
            f'<div class="diag-card-header">'
            f'<span class="diag-icon">{icon}</span>'
            f'<div><div class="diag-card-title">{escape(title)}</div>'
            f'<div class="diag-card-sub">{escape(subtitle)}</div></div>'
            f"</div>"
            f'<div class="diag-card-body">'
            f'<div class="diag-card-text">{text}</div>'
            f'<div class="diag-actions">{"".join(buttons)}</div>'
            f"</div></div>"
        )

    @api.model
    def _check_by_code(self, checks, *codes):
        for check in checks:
            if check.get("code") in codes:
                return check
        return None

    @api.model
    def _build_copilot_suggestions(self, checks, side_origin):
        """Cartes Copilot HTML — maquette Écran 2 (4 types colorés)."""
        side_labels = {
            "unknown": _("Non déterminé"),
            "client": _("Probable côté client"),
            "platform": _("Probable côté Intellix"),
        }
        issues = [c for c in checks if c["status"] in ("fail", "warn")]
        issue_count = len(issues)
        summary_text = escape(self._build_copilot_summary(checks, side_origin)).replace(
            "\n", "<br/>"
        )
        cards = [
            self._diag_card(
                "diag-summary",
                "🔍",
                _("Diagnostic — Résumé"),
                _("%(side)s · %(count)s points") % {
                    "side": side_labels.get(side_origin, side_origin),
                    "count": issue_count,
                },
                summary_text,
                [
                    (_("🔍 Inspecter le diagnostic"), "primary", "inspect_diagnostic"),
                    (_("Proposer correctif"), "ghost", "propose_fix_auto"),
                ],
            )
        ]

        user_check = self._check_by_code(checks, "user_account", "user_missing")
        if user_check:
            cards.append(
                self._diag_card(
                    "diag-odoo",
                    "👤",
                    _("Compte Odoo"),
                    _("Suggestion corrective"),
                    escape(user_check["detail"]),
                    [
                        (_("Approuver"), "primary", "approve_fix"),
                        (_("Exécuter"), "ghost", "execute_fix"),
                    ],
                )
            )

        camp_check = self._check_by_code(
            checks, "campaign_status", "campaign_none", "campaign_module"
        )
        if camp_check:
            sub = _("5 campagnes détectées") if camp_check["status"] == "ok" else camp_check["label"]
            cards.append(
                self._diag_card(
                    "diag-campaigns",
                    "📞",
                    _("Campagnes VICIdial"),
                    sub,
                    escape(camp_check["detail"]),
                    [
                        (_("📋 Voir les campagnes"), "primary", "view_campaigns"),
                        (_("Valider la config"), "ghost", "validate_campaign_config"),
                    ],
                )
            )

        credit_check = self._check_by_code(checks, "credits_balance", "credits_none")
        if credit_check:
            cards.append(
                self._diag_card(
                    "diag-credits",
                    "💳",
                    _("Crédits IA"),
                    _("Compte introuvable") if credit_check["status"] != "ok" else _("Solde vérifié"),
                    escape(credit_check["detail"]),
                    [
                        (_("💳 Créer le compte crédits"), "primary", "create_credits_account"),
                        (_("Assigner plan existant"), "ghost", "assign_credit_plan"),
                    ],
                )
            )

        anydesk_check = self._check_by_code(checks, "anydesk_missing", "anydesk_ready")
        if anydesk_check:
            if anydesk_check.get("code") == "anydesk_missing":
                ad_actions = [
                    (_("📨 Demander l'ID AnyDesk"), "primary", "request_anydesk_id"),
                ]
            elif anydesk_check.get("status") != "ok":
                ad_actions = [
                    (_("✓ Enregistrer le consentement"), "primary", "confirm_anydesk_consent"),
                    (_("🖥 Ouvrir session AnyDesk"), "ghost", "open_anydesk_session"),
                ]
            else:
                ad_actions = [
                    (_("🖥 Ouvrir session AnyDesk"), "primary", "open_anydesk_session"),
                    (_("📝 Notes de session"), "ghost", "open_anydesk_tab"),
                ]
            cards.append(
                self._diag_card(
                    "diag-anydesk",
                    "🖥",
                    _("AnyDesk — accès distant"),
                    _("Session distante") if anydesk_check["status"] == "ok" else _("Configuration requise"),
                    escape(anydesk_check["detail"]),
                    ad_actions,
                )
            )

        if not issues:
            cards.append(
                self._diag_card(
                    "diag-summary",
                    "✅",
                    _("Tout semble OK"),
                    _("Aucun point bloquant"),
                    escape(_("Aucune action corrective suggérée.")),
                    [],
                )
            )
        return "".join(cards)

    @api.model
    def _normalize_reply(self, text):
        cleaned = (text or "").strip()
        if len(cleaned) >= 2 and cleaned[0] == '"' and cleaned[-1] == '"':
            return cleaned[1:-1]
        return cleaned

    @api.model
    def _build_copilot_replies(self, ticket, checks, side_origin):
        """Réponses client suggérées (bas de panneau Copilot)."""
        partner = ticket.partner_id.display_name if ticket.partner_id else _("client")
        issue_count = sum(1 for c in checks if c["status"] in ("fail", "warn"))
        anydesk = self._check_by_code(checks, "anydesk_missing", "anydesk_ready")

        replies = []
        if issue_count:
            replies.append(
                _(
                    '"Bonjour, nous avons identifié %(count)s points à configurer pour '
                    'finaliser votre demande. Je m\'en occupe et vous confirme rapidement."'
                )
                % {"count": issue_count}
            )
        if anydesk and anydesk.get("code") == "anydesk_missing":
            replies.append(
                _(
                    '"Pouvez-vous me communiquer votre ID AnyDesk pour que je puisse '
                    'accéder à votre poste et finaliser la configuration à distance ?"'
                )
            )
        if not replies:
            replies.append(
                _(
                    '"Bonjour %(partner)s, votre ticket %(ref)s est pris en charge. '
                    'Nous revenons vers vous sous peu."'
                )
                % {"partner": partner, "ref": ticket.name}
            )

        plain_replies = [self._normalize_reply(text) for text in replies[:3]]
        items = []
        icons = ("📧", "🔗", "💬")
        for idx, text in enumerate(replies[:3]):
            icon = icons[idx % len(icons)]
            items.append(
                f'<div class="suggest-reply copilot-reply-{idx}" role="button" tabindex="0">'
                f'<span class="suggest-reply-icon">{icon}</span>'
                f'<span class="suggest-reply-text">{escape(text)}</span>'
                f'<span class="suggest-reply-use">{escape(_("Utiliser →"))}</span>'
                "</div>"
            )
        html = (
            '<div class="suggest-replies-section">'
            f'<div class="suggest-replies-title">{escape(_("Réponses suggérées au client"))}</div>'
            f'<div class="suggest-replies">{"".join(items)}</div>'
            "</div>"
        )
        return html, plain_replies

    @api.model
    def answer_question(self, ticket, question):
        """Q&A Copilot — LLM Claude si disponible, sinon règles locales."""
        if "intellix.support.copilot.llm" in self.env:
            result = self.env["intellix.support.copilot.llm"].ask(ticket, question)
            return result.get("html", "")
        return self._answer_question_rules(ticket, question)

    @api.model
    def _answer_question_rules(self, ticket, question):
        """Fallback Q&A par mots-clés (si LLM indisponible)."""
        question = (question or "").strip()
        q = question.lower()
        checks = []
        if ticket.last_diagnostic_id and ticket.last_diagnostic_id.result_json:
            try:
                checks = json.loads(ticket.last_diagnostic_id.result_json)
            except (TypeError, ValueError):
                checks = []

        side_labels = {
            "unknown": _("non déterminée"),
            "client": _("côté client"),
            "platform": _("côté Intellix"),
        }
        side = side_labels.get(ticket.side_origin, ticket.side_origin)
        issues = [c for c in checks if c.get("status") in ("fail", "warn")]

        if any(k in q for k in ("campagn", "vicidial", "adl", "appel")):
            camp = self._check_by_code(checks, "campaign_status", "campaign_none", "campaign_module")
            detail = camp["detail"] if camp else _("Lancez un diagnostic pour analyser les campagnes.")
            return (
                f"<p>{escape(_('Concernant les campagnes VICIdial pour ce ticket'))} "
                f"({escape(ticket.name)}):</p>"
                f"<p>{escape(detail)}</p>"
                f"<p><em>{escape(_('Utilisez « Voir les campagnes » pour ouvrir la liste filtrée.'))}</em></p>"
            )

        if any(k in q for k in ("crédit", "credit", "solde", "factur")):
            cred = self._check_by_code(checks, "credits_balance", "credits_none")
            detail = cred["detail"] if cred else _("Compte crédits non vérifié.")
            return (
                f"<p>{escape(_('État crédits IA'))}: {escape(detail)}</p>"
                f"<p><em>{escape(_('Boutons « Créer le compte crédits » / « Assigner plan » disponibles dans la carte Crédits.'))}</em></p>"
            )

        if any(k in q for k in ("odoo", "compte", "accès", "login", "mot de passe")):
            user = self._check_by_code(checks, "user_account", "user_missing")
            detail = user["detail"] if user else _("Utilisateur non lié au ticket.")
            return (
                f"<p>{escape(_('Compte Odoo'))}: {escape(detail)}</p>"
                f"<p><em>{escape(_('Runbook « Accès Odoo refusé » applicable si le compte est inactif.'))}</em></p>"
            )

        if any(k in q for k in ("anydesk", "distant", "remote")):
            ad = self._check_by_code(checks, "anydesk_missing", "anydesk_ready")
            detail = ad["detail"] if ad else ticket.anydesk_id or _("Non renseigné")
            return f"<p>{escape(_('AnyDesk'))}: {escape(str(detail))}</p>"

        if any(k in q for k in ("origine", "côté", "client", "plateforme", "diagnostic")):
            summary = ticket.copilot_summary or _("Aucun diagnostic lancé.")
            issue_lines = "".join(
                f"<li>{escape(c.get('label', ''))}: {escape(c.get('detail', ''))}</li>"
                for c in issues[:5]
            )
            body = (
                f"<p>{escape(_('Origine probable'))}: <strong>{escape(side)}</strong></p>"
                f"<p>{escape(summary).replace(chr(10), '<br/>')}</p>"
            )
            if issue_lines:
                body += f"<ul>{issue_lines}</ul>"
            return body

        summary = ticket.copilot_summary or _("Lancez un diagnostic pour enrichir le contexte.")
        return (
            f"<p>{escape(_('Contexte ticket'))} <strong>{escape(ticket.name)}</strong> — "
            f"{escape(ticket.subject or '')}</p>"
            f"<p>{escape(summary).replace(chr(10), '<br/>')}</p>"
            f"<p><em>{escape(_('Posez une question sur les campagnes, crédits, compte Odoo ou AnyDesk.'))}</em></p>"
        )
