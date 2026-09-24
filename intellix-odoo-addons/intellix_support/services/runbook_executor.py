# -*- coding: utf-8 -*-
import json
import logging
import secrets
import string

from odoo import _, api, fields, models
from odoo.exceptions import UserError
from odoo.tools import format_datetime

_logger = logging.getLogger(__name__)

HOTFIX_SCRIPT = "/opt/doorway/campaign_hotfix.sh"
HOSTINGER_HOTFIX_SCRIPT = "/opt/doorway/hostinger_campaign_hotfix.sh"
LEA_VICIDIAL_IDS = ("DW_QCB2C", "SE_RENOV_QC")
LEA_REMOTE_EXTEN = "86013"


class IntellixSupportRunbookExecutor(models.AbstractModel):
    _name = "intellix.support.runbook.executor"
    _description = "Exécuteur runbooks support Intellix"

    @api.model
    def execute_proposal(self, proposal):
        proposal.ensure_one()
        code = proposal.runbook_id.code
        dispatch = {
            "access_denied": self._execute_access_denied,
            "calls_not_dialing": self._execute_calls_not_dialing,
            "lea_silent": self._execute_lea_silent,
        }
        handler = dispatch.get(code)
        if not handler:
            raise UserError(
                _("Aucun exécuteur pour le runbook « %(code)s ».")
                % {"code": code}
            )
        return handler(proposal)

    @api.model
    def build_proposal_steps(self, runbook, ticket, checks=None):
        """Étapes HTML pour fix.proposal — diagnostic read-only d'abord."""
        ticket.ensure_one()
        checks = checks if checks is not None else ticket._copilot_parse_checks()
        if runbook.code == "calls_not_dialing":
            return self._build_steps_calls_not_dialing(ticket, checks)
        if runbook.code == "lea_silent":
            return self._build_steps_lea_silent(ticket, checks)
        return ticket._copilot_build_proposal_steps_legacy(runbook, checks)

    @api.model
    def _ticket_campaigns(self, ticket):
        if "doorway.campaign" not in self.env:
            return self.env["doorway.campaign"].browse()
        Campaign = self.env["doorway.campaign"]
        domain = [("state", "in", ("active", "paused", "ready"))]
        if ticket.contact_user_id:
            domain = [("human_agent_user_ids", "in", ticket.contact_user_id.id)]
        elif ticket.partner_id:
            domain = [
                "|",
                ("company_id.partner_id", "child_of", ticket.partner_id.id),
                ("human_agent_user_ids.partner_id", "child_of", ticket.partner_id.id),
            ]
        return Campaign.search(domain, limit=5)

    @api.model
    def _vicidial_svc(self):
        try:
            from odoo.addons.doorway_vicidial_campaigns.services.vicidial_service import (
                VicidialService,
            )

            svc = VicidialService(self.env)
            if svc.is_available():
                return svc
        except Exception as exc:
            _logger.debug("VicidialService unavailable: %s", exc)
        return None

    @api.model
    def _vicidial_campaign_stats(self, vicidial_campaign_id):
        stats = {
            "hopper_count": None,
            "auto_dial_level": None,
            "active": None,
            "dial_method": None,
        }
        if not vicidial_campaign_id:
            return stats
        svc = self._vicidial_svc()
        if not svc:
            return stats
        try:
            with svc._cursor(dictionary=True) as cur:
                cur.execute(
                    """
                    SELECT active, auto_dial_level, dial_method
                    FROM vicidial_campaigns
                    WHERE campaign_id = %s LIMIT 1
                    """,
                    (vicidial_campaign_id[:20],),
                )
                row = cur.fetchone()
                if row:
                    stats["active"] = row.get("active")
                    stats["auto_dial_level"] = row.get("auto_dial_level")
                    stats["dial_method"] = row.get("dial_method")
                cur.execute(
                    """
                    SELECT COUNT(*) AS cnt FROM vicidial_hopper
                    WHERE campaign_id = %s AND status = 'READY'
                    """,
                    (vicidial_campaign_id[:20],),
                )
                hop = cur.fetchone()
                if hop:
                    stats["hopper_count"] = hop.get("cnt", 0)
        except Exception as exc:
            _logger.warning("VICIdial stats query failed for %s: %s", vicidial_campaign_id, exc)
        return stats

    @api.model
    def diagnose_calls_not_dialing(self, ticket):
        """Contrôles read-only : état campagne Odoo, ADL, hopper VICIdial."""
        ticket.ensure_one()
        findings = []
        campaigns = self._ticket_campaigns(ticket)
        if not campaigns:
            findings.append(
                {
                    "status": "warn",
                    "label": _("Campagnes"),
                    "detail": _("Aucune campagne liée au ticket."),
                }
            )
            return findings

        for camp in campaigns:
            adl = camp.dial_level or camp.dial_ratio or 0
            vid = (camp.vicidial_campaign_id or "").strip()
            line = _("%(name)s — état Odoo=%(state)s, ADL=%(adl)s, VICIdial=%(vid)s") % {
                "name": camp.name,
                "state": camp.state,
                "adl": adl,
                "vid": vid or "—",
            }
            status = "ok"
            if camp.state != "active":
                status = "warn"
            if adl in (0, 0.0, None):
                status = "fail"
            stats = self._vicidial_campaign_stats(vid)
            if stats["auto_dial_level"] is not None:
                line += _(", VICIdial ADL=%(adl)s") % {"adl": stats["auto_dial_level"]}
                if str(stats["auto_dial_level"]) in ("0", "0.0") and status != "fail":
                    status = "fail"
            if stats["hopper_count"] is not None:
                line += _(", hopper READY=%(n)s") % {"n": stats["hopper_count"]}
                if stats["hopper_count"] == 0 and status == "ok":
                    status = "warn"
            if stats["active"] == "N":
                status = "fail"
                line += _(", campagne VICIdial inactive")
            findings.append({"status": status, "label": camp.name, "detail": line, "campaign": camp})
        return findings

    @api.model
    def _build_steps_calls_not_dialing(self, ticket, checks):
        findings = self.diagnose_calls_not_dialing(ticket)
        rows = []
        for item in findings:
            icon = {"ok": "✅", "warn": "⚠️", "fail": "❌"}.get(item["status"], "•")
            rows.append(f"<li>{icon} {item['label']}: {item['detail']}</li>")
        approval_note = _(
            "Après approbation : réactivation campagne / ADL=1 si sûr, "
            "sinon référence script %(script)s."
        ) % {"script": HOTFIX_SCRIPT}
        return (
            f"<p><strong>{_('Diagnostic dialer (lecture seule)')}</strong></p>"
            f"<ul>{''.join(rows)}</ul>"
            f"<p><em>{approval_note}</em></p>"
            "<ol>"
            f"<li>{_('Vérifier trunk et agents READY dans VICIdial.')}</li>"
            f"<li>{_('Confirmer hopper alimenté (listes actives).')}</li>"
            f"<li>{_('Exécuter le correctif approuvé ou lancer campaign_hotfix.sh côté serveur.')}</li>"
            "</ol>"
        )

    @api.model
    def _execute_calls_not_dialing(self, proposal):
        ticket = proposal.ticket_id
        findings = self.diagnose_calls_not_dialing(ticket)
        now = fields.Datetime.now()
        executor = self.env.user
        actions = []
        manual = []

        for item in findings:
            camp = item.get("campaign")
            if not camp:
                continue
            writes = {}
            if camp.state in ("paused", "ready"):
                writes["state"] = "active"
                actions.append(_("Campagne « %(name)s » → active") % {"name": camp.name})
            adl = camp.dial_level or 0
            if adl in (0, None):
                writes["dial_level"] = 1
                actions.append(_("ADL Odoo « %(name)s » → 1") % {"name": camp.name})
            if writes:
                camp.sudo().write(writes)
            elif item["status"] != "ok":
                manual.append(
                    _("%(name)s : %(detail)s — voir %(script)s")
                    % {"name": camp.name, "detail": item["detail"], "script": HOTFIX_SCRIPT}
                )

        if not actions and not manual:
            actions.append(_("Aucune action Odoo automatique — configuration semble OK"))

        log_lines = [
            _("Runbook : calls_not_dialing"),
            _("Ticket : %(ref)s") % {"ref": ticket.name},
            _("Exécuté par : %(user)s") % {"user": executor.name},
            _("Date : %(dt)s") % {
                "dt": format_datetime(self.env, now, dt_format="dd/MM/yyyy HH:mm"),
            },
            _("Actions Odoo : %(actions)s") % {
                "actions": ", ".join(actions) if actions else _("aucune"),
            },
        ]
        if manual:
            log_lines.append(_("Manuel : %(items)s") % {"items": "; ".join(manual)})
        log_lines.append(_("Script référence : %(script)s") % {"script": HOTFIX_SCRIPT})
        execution_log = "\n".join(log_lines)

        ticket.message_post(
            body=_(
                "<p><em>Correctif dialer exécuté</em> — %(actions)s</p>",
                actions=", ".join(actions) if actions else _("voir journal"),
            ),
            subtype_xmlid="mail.mt_note",
        )
        return {
            "log": execution_log,
            "notify": {
                "title": _("Correctif dialer"),
                "message": actions[0] if len(actions) == 1 else _("Correctif exécuté — voir journal."),
                "type": "success",
            },
        }

    @api.model
    def diagnose_lea_silent(self, ticket):
        """Contrôles Léa QC : campagne DW_QCB2C, agent IA, crédits, stack IA."""
        ticket.ensure_one()
        findings = []

        campaigns = self._ticket_campaigns(ticket)
        lea_camps = campaigns.filtered(
            lambda c: (c.vicidial_campaign_id or "") in LEA_VICIDIAL_IDS
            or (c.ia_agent_id and "lea" in (c.ia_agent_id.name or "").lower())
        )
        if not lea_camps and ticket.category_id and ticket.category_id.code == "lea":
            lea_camps = campaigns

        if not lea_camps:
            findings.append(
                {
                    "status": "warn",
                    "label": _("Campagne Léa"),
                    "detail": _("Aucune campagne DW_QCB2C / Léa QC trouvée pour ce ticket."),
                }
            )
        else:
            for camp in lea_camps:
                detail_parts = [
                    _("état=%(state)s") % {"state": camp.state},
                    _("VICIdial=%(vid)s") % {"vid": camp.vicidial_campaign_id or "—"},
                    _("remote IA ext %(ext)s") % {"ext": LEA_REMOTE_EXTEN},
                ]
                status = "ok" if camp.state == "active" else "warn"
                if not camp.ia_agent_id:
                    status = "fail"
                    detail_parts.append(_("agent IA non assigné"))
                else:
                    agent_status = getattr(camp.ia_agent_id, "status", "active")
                    detail_parts.append(
                        _("agent=%(name)s (%(status)s)")
                        % {"name": camp.ia_agent_id.name, "status": agent_status}
                    )
                    if agent_status != "active":
                        status = "fail"
                vid = (camp.vicidial_campaign_id or "").strip()
                stats = self._vicidial_campaign_stats(vid)
                if stats["active"] == "N":
                    status = "fail"
                    detail_parts.append(_("campagne VICIdial inactive"))
                findings.append(
                    {
                        "status": status,
                        "label": camp.name,
                        "detail": ", ".join(detail_parts),
                        "campaign": camp,
                    }
                )

        icp = self.env["ir.config_parameter"].sudo()
        ai_enabled = icp.get_param("renovation_conciergerie.ai_enabled", "0")
        if str(ai_enabled) not in ("1", "True", "true"):
            findings.append(
                {
                    "status": "fail",
                    "label": _("IA / STT"),
                    "detail": _("renovation_conciergerie.ai_enabled désactivé — STT/LLM indisponibles."),
                }
            )
        else:
            findings.append(
                {
                    "status": "ok",
                    "label": _("IA / STT"),
                    "detail": _("Service IA Odoo actif (renovation.ai.service)."),
                }
            )

        n8n_base = icp.get_param("renovation_conciergerie.n8n_webhook_base", "") or icp.get_param(
            "doorway.n8n_webhook_url", ""
        )
        if n8n_base:
            findings.append(
                {
                    "status": "ok",
                    "label": _("n8n"),
                    "detail": _("Webhook base configuré."),
                }
            )
        else:
            findings.append(
                {
                    "status": "warn",
                    "label": _("n8n / AGI"),
                    "detail": _(
                        "Webhook n8n non trouvé dans ir.config_parameter — "
                        "vérifier bridge AGI 86013 et logs /var/log/lea-qc-live.log sur Hostinger."
                    ),
                }
            )

        findings.append(
            {
                "status": "warn",
                "label": _("Stack Hostinger"),
                "detail": _(
                    "Vérifier AMI stack, remote 86013 ACTIVE, AMD dialplan qc, "
                    "script %(script)s sur dialer Amériques."
                )
                % {"script": HOSTINGER_HOTFIX_SCRIPT},
            }
        )
        return findings

    @api.model
    def _build_steps_lea_silent(self, ticket, checks):
        findings = self.diagnose_lea_silent(ticket)
        rows = []
        for item in findings:
            icon = {"ok": "✅", "warn": "⚠️", "fail": "❌"}.get(item["status"], "•")
            rows.append(f"<li>{icon} {item['label']}: {item['detail']}</li>")
        hotfix_note = _(
            "Après approbation : réactivation campagne Odoo si pause ; "
            "hotfix serveur via %(script)s."
        ) % {"script": HOSTINGER_HOTFIX_SCRIPT}
        return (
            f"<p><strong>{_('Diagnostic Léa QC (lecture seule)')}</strong></p>"
            f"<ul>{''.join(rows)}</ul>"
            "<ol>"
            f"<li>{_('Consulter /var/log/lea-qc-live.log (AGI_START, STT vide, AMD).')}</li>"
            f"<li>{_('Vérifier n8n workflow Léa et bridge 86013 sur Hostinger.')}</li>"
            f"<li>{hotfix_note}</li>"
            "</ol>"
        )

    @api.model
    def _execute_lea_silent(self, proposal):
        ticket = proposal.ticket_id
        findings = self.diagnose_lea_silent(ticket)
        now = fields.Datetime.now()
        executor = self.env.user
        actions = []
        checklist = []

        for item in findings:
            camp = item.get("campaign")
            if camp and camp.state in ("paused", "ready"):
                camp.sudo().write({"state": "active"})
                actions.append(_("Campagne « %(name)s » réactivée") % {"name": camp.name})
            checklist.append(f"[{item['status']}] {item['label']}: {item['detail']}")

        if not actions:
            actions.append(
                _("Checklist enregistrée — actions serveur (STT/n8n/AGI) via %(script)s")
                % {"script": HOSTINGER_HOTFIX_SCRIPT}
            )

        execution_log = "\n".join(
            [
                _("Runbook : lea_silent"),
                _("Ticket : %(ref)s") % {"ref": ticket.name},
                _("Exécuté par : %(user)s") % {"user": executor.name},
                _("Date : %(dt)s") % {
                    "dt": format_datetime(self.env, now, dt_format="dd/MM/yyyy HH:mm"),
                },
                _("Actions Odoo : %(actions)s") % {"actions": ", ".join(actions)},
                _("Checklist :"),
                *checklist,
                _("Référence hotfix : %(script)s") % {"script": HOSTINGER_HOTFIX_SCRIPT},
            ]
        )

        ticket.message_post(
            body=_(
                "<p><em>Correctif Léa exécuté</em> — %(actions)s. "
                "Consulter le journal pour la checklist STT/n8n/AGI.</p>",
                actions=", ".join(actions),
            ),
            subtype_xmlid="mail.mt_note",
        )
        return {
            "log": execution_log,
            "notify": {
                "title": _("Correctif Léa"),
                "message": actions[0],
                "type": "warning" if len([f for f in findings if f["status"] == "fail"]) else "success",
                "sticky": True,
            },
        }

    @api.model
    def _execute_access_denied(self, proposal):
        """Réinitialise le mot de passe Odoo de l'utilisateur concerné."""
        ticket = proposal.ticket_id
        user = ticket.contact_user_id
        if not user:
            if ticket.partner_id:
                user = ticket.partner_id.user_ids.filtered("active")[:1]
            if not user:
                user = ticket.partner_id.user_ids[:1] if ticket.partner_id else user
        if not user:
            raise UserError(
                _("Renseignez l'utilisateur concerné sur le ticket avant d'exécuter ce correctif.")
            )

        now = fields.Datetime.now()
        executor = self.env.user
        actions = []

        if not user.active:
            user.sudo().write({"active": True})
            actions.append(_("Compte réactivé"))

        temp_password = self._generate_temp_password()
        ctx = user._crypt_context()
        user.sudo()._set_encrypted_password(user.id, ctx.hash(temp_password))
        actions.append(_("Mot de passe réinitialisé"))

        log_lines = [
            _("Runbook : %(code)s") % {"code": proposal.runbook_id.code},
            _("Utilisateur : %(login)s (id=%(uid)s)") % {"login": user.login, "uid": user.id},
            _("Exécuté par : %(user)s") % {"user": executor.name},
            _("Date : %(dt)s") % {
                "dt": format_datetime(self.env, now, dt_format="dd/MM/yyyy HH:mm"),
            },
            _("Actions : %(actions)s") % {"actions": ", ".join(actions)},
        ]
        execution_log = "\n".join(log_lines)

        _logger.info(
            "Support runbook access_denied ticket=%s user=%s proposal=%s executor=%s",
            ticket.name,
            user.login,
            proposal.name,
            executor.login,
        )

        ticket.message_post(
            body=_(
                "<p><em>Correctif exécuté</em> — mot de passe Odoo réinitialisé pour "
                "<strong>%(login)s</strong> (proposition %(prop)s).</p>",
                login=user.login,
                prop=proposal.name,
            ),
            subtype_xmlid="mail.mt_note",
        )

        return {
            "log": execution_log,
            "notify": {
                "title": _("Correctif exécuté"),
                "message": _(
                    "Mot de passe temporaire pour %(login)s : %(password)s — "
                    "communiquez-le au client par canal sécurisé.",
                    login=user.login,
                    password=temp_password,
                ),
                "type": "warning",
                "sticky": True,
            },
        }

    @api.model
    def _generate_temp_password(self, length=14):
        alphabet = string.ascii_letters + string.digits
        while True:
            password = "".join(secrets.choice(alphabet) for _ in range(length))
            if (
                any(c.islower() for c in password)
                and any(c.isupper() for c in password)
                and any(c.isdigit() for c in password)
            ):
                return password
