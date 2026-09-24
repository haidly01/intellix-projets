# -*- coding: utf-8 -*-
import json
import logging
import os
import subprocess
import urllib.error
import urllib.request

from odoo import _, api, fields, models
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)

CURSOR_API_BASE = "https://api.cursor.com"
BRIDGE_SCRIPT = "/opt/doorway/doorway_cursor_bridge.py"
SERVER_RUNBOOK_CODES = frozenset({"calls_not_dialing", "lea_silent"})


class IntellixSupportCursorBridge(models.AbstractModel):
    _name = "intellix.support.cursor.bridge"
    _description = "Bridge Cursor Agent — analyse support (POC)"

    @api.model
    def _bridge_enabled(self):
        icp = self.env["ir.config_parameter"].sudo()
        return str(icp.get_param("intellix_support.cursor_bridge_enabled", "False")) in (
            "1",
            "True",
            "true",
        )

    @api.model
    def _api_key(self):
        icp = self.env["ir.config_parameter"].sudo()
        key = (icp.get_param("intellix_support.cursor_api_key") or "").strip()
        if not key:
            key = (os.environ.get("CURSOR_API_KEY") or "").strip()
        return key

    @api.model
    def _repo_url(self):
        return (
            self.env["ir.config_parameter"]
            .sudo()
            .get_param("intellix_support.cursor_repo_url", "")
            .strip()
        )

    @api.model
    def _build_prompt(self, ticket, proposal=None, mode="analysis"):
        lines = [
            "Tu es l'agent Cursor d'analyse support Intellix (Doorway).",
            "Mode POC : diagnostic et recommandations UNIQUEMENT.",
            "NE PAS déployer, modifier des serveurs, ni exécuter de hotfix sans approbation humaine.",
            "",
            f"Ticket : {ticket.name}",
            f"Sujet : {ticket.subject or ''}",
            f"Description : {(ticket.description or '')[:4000]}",
            f"Priorité : {ticket.priority}",
            f"Origine : {ticket.side_origin}",
            f"Partenaire : {ticket.partner_id.display_name if ticket.partner_id else '—'}",
            f"Résumé diagnostic : {ticket.copilot_summary or '—'}",
        ]
        if proposal and proposal.runbook_id:
            lines.extend(
                [
                    "",
                    f"Runbook : {proposal.runbook_id.code} — {proposal.runbook_id.name}",
                    f"Étapes proposées (HTML) : {proposal.steps_html or '—'}",
                ]
            )
        if mode == "execution_stub":
            lines.append(
                "\nContexte exécution Phase C : le correctif Odoo a été appliqué ; "
                "propose l'analyse serveur (dialplan, AGI, campaign_hotfix) sans auto-deploy."
            )
        lines.append(
            "\nRéponds en français : causes probables, vérifications serveur, "
            "commandes de diagnostic suggérées, risques."
        )
        return "\n".join(lines)

    @api.model
    def _http_json(self, method, path, payload=None, api_key=None):
        api_key = api_key or self._api_key()
        if not api_key:
            raise UserError(
                _(
                    "Clé API Cursor absente — définissez CURSOR_API_KEY "
                    "ou intellix_support.cursor_api_key."
                )
            )
        url = f"{CURSOR_API_BASE}{path}"
        data = None
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }
        if payload is not None:
            data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(url, data=data, headers=headers, method=method)
        try:
            with urllib.request.urlopen(req, timeout=60) as resp:
                raw = resp.read().decode("utf-8")
                return json.loads(raw) if raw else {}
        except urllib.error.HTTPError as err:
            body = err.read().decode("utf-8", errors="replace")
            raise UserError(_("Cursor API HTTP %(code)s : %(body)s") % {"code": err.code, "body": body[:500]}) from err
        except urllib.error.URLError as err:
            raise UserError(_("Cursor API indisponible : %s") % err) from err

    @api.model
    def _dispatch_via_script(self, ticket, prompt):
        if not os.path.isfile(BRIDGE_SCRIPT):
            return None
        payload = {
            "prompt": prompt,
            "ticket_id": ticket.id,
            "ticket_ref": ticket.name,
            "repo_url": self._repo_url() or None,
            "mode": "plan",
        }
        env = os.environ.copy()
        api_key = self._api_key()
        if api_key:
            env["CURSOR_API_KEY"] = api_key
        proc = subprocess.run(
            ["python3", BRIDGE_SCRIPT, "dispatch"],
            input=json.dumps(payload),
            capture_output=True,
            text=True,
            timeout=90,
            env=env,
            check=False,
        )
        if proc.returncode != 0:
            _logger.warning(
                "Cursor bridge script failed ticket=%s stderr=%s",
                ticket.name,
                proc.stderr[:500],
            )
            return None
        try:
            return json.loads(proc.stdout)
        except (TypeError, ValueError):
            _logger.warning("Cursor bridge script invalid JSON: %s", proc.stdout[:300])
            return None

    @api.model
    def _dispatch_via_api(self, ticket, prompt):
        body = {
            "prompt": {"text": prompt},
            "model": {"id": "composer-2.5"},
            "mode": "plan",
            "name": f"Support {ticket.name}"[:100],
        }
        repo_url = self._repo_url()
        if repo_url:
            body["repos"] = [{"url": repo_url, "startingRef": "main"}]
        return self._http_json("POST", "/v1/agents", body)

    @api.model
    def maybe_dispatch_on_ticket_created(self, ticket):
        """Auto-dispatch à la création — mode diagnostic, sans approbation."""
        ticket.ensure_one()
        if not self._bridge_enabled():
            return False
        try:
            self.dispatch_ticket_analysis(ticket, source="ticket_create")
            return True
        except UserError as err:
            _logger.warning(
                "Cursor auto-dispatch on create skipped ticket=%s: %s",
                ticket.name,
                err,
            )
            return False

    @api.model
    def maybe_dispatch_after_diagnostic(self, ticket):
        """Relance Cursor après diagnostic (contexte enrichi)."""
        ticket.ensure_one()
        if not self._bridge_enabled():
            return False
        if ticket.cursor_analysis_state == "running":
            return False
        try:
            self.dispatch_ticket_analysis(ticket, source="post_diagnostic")
            return True
        except UserError as err:
            _logger.warning(
                "Cursor post-diagnostic dispatch skipped ticket=%s: %s",
                ticket.name,
                err,
            )
            return False

    @api.model
    def dispatch_ticket_analysis(self, ticket, proposal=None, source="manual"):
        """Lance une analyse Cursor (human-in-the-loop, pas de deploy)."""
        ticket.ensure_one()
        if not self._bridge_enabled():
            raise UserError(_("Bridge Cursor désactivé — activez-le dans Paramètres Support."))

        prompt = self._build_prompt(ticket, proposal=proposal)
        result = self._dispatch_via_script(ticket, prompt)
        if not result:
            result = self._dispatch_via_api(ticket, prompt)

        agent = result.get("agent") or {}
        run = result.get("run") or {}
        agent_id = agent.get("id") or result.get("agent_id")
        run_id = run.get("id") or result.get("run_id") or agent.get("latestRunId")
        agent_url = agent.get("url") or (
            f"https://cursor.com/agents/{agent_id}" if agent_id else ""
        )

        ticket.write(
            {
                "cursor_agent_id": agent_id or False,
                "cursor_run_id": run_id or False,
                "cursor_analysis_state": "running",
                "cursor_analysis_source": source,
            }
        )

        body_parts = [
            f"<p><em>Cursor</em> — analyse lancée ({source}).</p>",
        ]
        if agent_id:
            body_parts.append(f"<p>Agent : <code>{agent_id}</code></p>")
        if run_id:
            body_parts.append(f"<p>Run : <code>{run_id}</code></p>")
        if agent_url:
            body_parts.append(f'<p><a href="{agent_url}">Ouvrir dans Cursor</a></p>')
        ticket.message_post(body="".join(body_parts), subtype_xmlid="mail.mt_note")

        return {
            "agent_id": agent_id,
            "run_id": run_id,
            "agent_url": agent_url,
        }

    @api.model
    def _fetch_run_result(self, ticket):
        agent_id = ticket.cursor_agent_id
        run_id = ticket.cursor_run_id
        if not agent_id or not run_id:
            return None
        path = f"/v1/agents/{agent_id}/runs/{run_id}"
        return self._http_json("GET", path)

    @api.model
    def _extract_run_text(self, run_payload):
        if not run_payload:
            return ""
        for key in ("result", "summary", "output"):
            val = run_payload.get(key)
            if isinstance(val, str) and val.strip():
                return val.strip()
        status = run_payload.get("status", "")
        return _("Statut run : %s") % status

    @api.model
    def poll_ticket_run(self, ticket):
        ticket.ensure_one()
        if ticket.cursor_analysis_state not in ("running", "queued"):
            return False
        if not ticket.cursor_agent_id or not ticket.cursor_run_id:
            ticket.cursor_analysis_state = "error"
            return False
        try:
            run_payload = self._fetch_run_result(ticket)
        except UserError as err:
            _logger.warning("Cursor poll failed ticket=%s: %s", ticket.name, err)
            return False

        status = (run_payload.get("status") or "").upper()
        terminal_ok = status in ("FINISHED", "COMPLETED", "DONE", "SUCCEEDED")
        terminal_err = status in ("FAILED", "ERROR", "CANCELLED", "CANCELED")

        if terminal_ok:
            text = self._extract_run_text(run_payload)
            ticket.write(
                {
                    "cursor_analysis_state": "done",
                    "cursor_analysis_result": text,
                }
            )
            ticket.message_post(
                body=_(
                    "<p><em>Cursor — analyse terminée</em></p><pre>%s</pre>",
                    text[:8000],
                ),
                subtype_xmlid="mail.mt_note",
            )
            return True
        if terminal_err:
            ticket.write({"cursor_analysis_state": "error"})
            ticket.message_post(
                body=_("<p><em>Cursor — échec run</em> (%s)</p>") % status,
                subtype_xmlid="mail.mt_note",
            )
            return True
        return False

    @api.model
    def cron_poll_cursor_runs(self):
        tickets = self.env["intellix.support.ticket"].search(
            [("cursor_analysis_state", "in", ("running", "queued"))]
        )
        for ticket in tickets:
            self.poll_ticket_run(ticket)

    @api.model
    def maybe_dispatch_on_proposal_approved(self, proposal):
        proposal.ensure_one()
        if proposal.runbook_id.code not in SERVER_RUNBOOK_CODES:
            return False
        if not self._bridge_enabled():
            return False
        try:
            self.dispatch_ticket_analysis(
                proposal.ticket_id,
                proposal=proposal,
                source="proposal_approved",
            )
            return True
        except UserError as err:
            _logger.info(
                "Cursor dispatch on approve skipped proposal=%s: %s",
                proposal.name,
                err,
            )
            return False

    @api.model
    def execution_stub_for_proposal(self, proposal):
        """Phase C stub — journalise + optionnellement lance Cursor."""
        proposal.ensure_one()
        code = proposal.runbook_id.code
        if code not in SERVER_RUNBOOK_CODES:
            return ""
        lines = [
            "",
            _("--- Bridge Cursor (Phase C stub) ---"),
            _("Runbook serveur : %(code)s") % {"code": code},
        ]
        if self._bridge_enabled():
            try:
                info = self.dispatch_ticket_analysis(
                    proposal.ticket_id,
                    proposal=proposal,
                    source="execute_stub",
                )
                lines.append(
                    _("Cursor agent=%(agent)s run=%(run)s")
                    % {"agent": info.get("agent_id"), "run": info.get("run_id")}
                )
            except UserError as err:
                lines.append(_("Cursor non lancé : %s") % err)
        else:
            lines.append(_("Bridge Cursor désactivé — exécution Odoo seule."))
        return "\n".join(lines)
