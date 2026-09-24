# -*- coding: utf-8 -*-
import json
import logging
from datetime import timedelta
from html import escape

from odoo import _, api, fields, models
from odoo.exceptions import UserError
from odoo.tools import format_datetime

_logger = logging.getLogger(__name__)

_SLA_HOURS = {"0": 72, "1": 24, "2": 8, "3": 4}


class IntellixSupportTicket(models.Model):
    _name = "intellix.support.ticket"
    _description = "Ticket support Intellix"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "priority desc, id desc"

    name = fields.Char(
        string="Référence",
        required=True,
        copy=False,
        readonly=True,
        default=lambda self: _("Nouveau"),
    )
    subject = fields.Char(string="Sujet", required=True, tracking=True)
    description = fields.Html(string="Description")
    partner_id = fields.Many2one(
        "res.partner",
        string="Organisation",
        tracking=True,
        index=True,
        help="Société ou organisation cliente (partenaire).",
    )
    user_scope = fields.Selection(
        [
            ("all", "Tous les utilisateurs"),
            ("group", "Groupe"),
            ("specific", "Utilisateur ciblé"),
        ],
        string="Portée",
        default="all",
        tracking=True,
        help="Utilisateurs impactés par le ticket au sein de l'organisation.",
    )
    scope_group_id = fields.Many2one(
        "res.groups",
        string="Groupe d'utilisateurs",
        tracking=True,
        domain="[('share', '=', False)]",
    )
    ticket_type = fields.Selection(
        [
            ("bug", "Bug / incident"),
            ("feature_request", "Nouvelle fonctionnalité"),
            ("question", "Question / aide"),
            ("other", "Autre demande"),
        ],
        string="Type de demande",
        default="bug",
        tracking=True,
    )
    user_id = fields.Many2one(
        "res.users",
        string="Assigné à",
        tracking=True,
        index=True,
        help="Laisser vide : le ticket reste en file d'attente (pas d'auto-assignation au créateur).",
    )
    category_id = fields.Many2one(
        "intellix.support.category",
        string="Module",
        tracking=True,
    )
    stage_id = fields.Many2one(
        "intellix.support.stage",
        string="Étape",
        tracking=True,
        index=True,
        group_expand="_read_group_stage_ids",
        default=lambda self: self._default_stage_id(),
    )
    priority = fields.Selection(
        [
            ("0", "Basse"),
            ("1", "Normale"),
            ("2", "Haute"),
            ("3", "Urgente"),
        ],
        default="1",
        tracking=True,
    )
    color = fields.Integer(string="Couleur")
    category_color = fields.Integer(
        related="category_id.color",
        string="Couleur catégorie",
    )
    side_origin = fields.Selection(
        [
            ("unknown", "Non déterminé"),
            ("client", "Côté client"),
            ("platform", "Côté Intellix"),
        ],
        string="Origine probable",
        default="unknown",
        tracking=True,
    )
    anydesk_id = fields.Char(string="ID AnyDesk")
    anydesk_consent = fields.Boolean(
        string="Consentement accès distant",
        help="Le client a accepté une session AnyDesk.",
    )
    anydesk_session_notes = fields.Text(string="Notes session AnyDesk")
    contact_user_id = fields.Many2one(
        "res.users",
        string="Utilisateur ciblé",
        help="Compte Odoo précis impacté lorsque la portée est « Utilisateur ciblé ».",
    )
    crm_lead_id = fields.Many2one(
        "crm.lead",
        string="Opportunité CRM",
        index=True,
    )
    diagnostic_ids = fields.One2many(
        "intellix.support.diagnostic",
        "ticket_id",
        string="Diagnostics",
    )
    proposal_ids = fields.One2many(
        "intellix.support.fix.proposal",
        "ticket_id",
        string="Propositions de correctif",
    )
    proposal_count = fields.Integer(compute="_compute_proposal_count")
    active_proposal_id = fields.Many2one(
        "intellix.support.fix.proposal",
        compute="_compute_active_proposal",
        string="Proposition active",
    )
    diagnostic_count = fields.Integer(compute="_compute_diagnostic_count", store=True)
    last_diagnostic_id = fields.Many2one(
        "intellix.support.diagnostic",
        compute="_compute_last_diagnostic",
        string="Dernier diagnostic",
    )
    diagnostic_summary_html = fields.Html(
        compute="_compute_last_diagnostic",
        string="Résumé diagnostic",
    )
    copilot_summary = fields.Text(
        string="Résumé Copilot",
        help="Synthèse IA (phase 2).",
    )
    copilot_summary_html = fields.Html(
        compute="_compute_copilot_summary_html",
        string="Résumé Copilot HTML",
    )
    copilot_suggestions = fields.Html(
        string="Cartes diagnostic Copilot",
        help="Cartes diagnostic IA (4 types maquette).",
    )
    copilot_replies_html = fields.Html(
        string="Réponses suggérées",
        help="Réponses client suggérées par le Copilot.",
    )
    copilot_replies_data = fields.Text(
        string="Réponses suggérées (JSON)",
        help="Textes bruts pour insertion dans le composer (RPC JS).",
    )
    copilot_chat_log = fields.Html(
        string="Historique chat Copilot",
        help="Questions / réponses Copilot sur ce ticket.",
    )
    attachment_count = fields.Integer(compute="_compute_message_stats")
    message_count = fields.Integer(compute="_compute_message_stats")
    attachment_ids = fields.Many2many(
        "ir.attachment",
        compute="_compute_attachment_ids",
        string="Fichiers joints",
    )
    sla_state = fields.Selection(
        [
            ("ok", "OK"),
            ("warn", "Attention"),
            ("breach", "Dépassé"),
        ],
        compute="_compute_sla_state",
        store=True,
        string="État SLA",
    )
    sla_label = fields.Char(compute="_compute_sla_state", store=True, string="Badge SLA")
    stage_is_closed = fields.Boolean(
        related="stage_id.is_closed",
        string="Étape clôturée",
    )
    priority_css = fields.Char(
        string="Classe priorité CSS",
        compute="_compute_kanban_display",
    )
    category_tag_class = fields.Char(
        string="Classe tag catégorie",
        compute="_compute_kanban_display",
    )
    has_ai_flag = fields.Boolean(
        string="Diagnostic IA",
        compute="_compute_kanban_display",
    )
    time_ago_label = fields.Char(
        string="Temps relatif",
        compute="_compute_kanban_display",
    )
    company_id = fields.Many2one(
        "res.company",
        default=lambda self: self.env.company,
        required=True,
    )
    alert_last_trigger = fields.Char(
        string="Dernière alerte (clé)",
        copy=False,
        help="Évite les doublons webhook/mail pour le même jeu de déclencheurs.",
    )
    alert_last_sent_at = fields.Datetime(string="Dernière alerte envoyée", copy=False)
    cursor_agent_id = fields.Char(string="Cursor agent ID", copy=False, tracking=True)
    cursor_run_id = fields.Char(string="Cursor run ID", copy=False)
    cursor_analysis_state = fields.Selection(
        [
            ("idle", "Inactif"),
            ("queued", "En file"),
            ("running", "En cours"),
            ("done", "Terminé"),
            ("error", "Erreur"),
        ],
        string="Analyse Cursor",
        default="idle",
        copy=False,
        tracking=True,
    )
    cursor_analysis_source = fields.Char(string="Source analyse Cursor", copy=False)
    cursor_analysis_result = fields.Text(string="Résultat analyse Cursor", copy=False)

    @api.model
    def _default_stage_id(self):
        return self.env["intellix.support.stage"].search(
            [("code", "=", "new")], limit=1
        )

    @api.model
    def _read_group_stage_ids(self, stages, domain):
        return self.env["intellix.support.stage"].search([], order="sequence")

    @api.depends("diagnostic_ids")
    def _compute_diagnostic_count(self):
        for ticket in self:
            ticket.diagnostic_count = len(ticket.diagnostic_ids)

    @api.depends("proposal_ids")
    def _compute_proposal_count(self):
        for ticket in self:
            ticket.proposal_count = len(ticket.proposal_ids)

    @api.depends("proposal_ids", "proposal_ids.state")
    def _compute_active_proposal(self):
        open_states = ("draft", "pending_approval", "approved")
        for ticket in self:
            ticket.active_proposal_id = ticket.proposal_ids.filtered(
                lambda p: p.state in open_states
            )[:1]

    @api.depends("diagnostic_ids")
    def _compute_last_diagnostic(self):
        for ticket in self:
            diag = ticket.diagnostic_ids[:1]
            ticket.last_diagnostic_id = diag
            ticket.diagnostic_summary_html = diag.summary_html if diag else False

    @api.depends("copilot_summary", "diagnostic_count", "side_origin")
    def _compute_copilot_summary_html(self):
        side_labels = {
            "unknown": _("Non déterminé"),
            "client": _("Probable côté client"),
            "platform": _("Probable côté Intellix"),
        }
        for ticket in self:
            summary = ticket.copilot_summary or _(
                "Lancez un diagnostic pour obtenir une synthèse IA."
            )
            side = side_labels.get(ticket.side_origin, ticket.side_origin)
            ticket.copilot_summary_html = (
                '<div class="intellix-copilot-summary-block">'
                f'<p class="intellix-copilot-summary-side">{side}</p>'
                f'<p class="intellix-copilot-summary-text">{summary}</p>'
                "</div>"
            )

    @api.depends("message_ids", "message_ids.attachment_ids")
    def _compute_message_stats(self):
        Attachment = self.env["ir.attachment"]
        for ticket in self:
            ticket.message_count = len(ticket.message_ids)
            ticket.attachment_count = Attachment.search_count(
                [
                    ("res_model", "=", ticket._name),
                    ("res_id", "=", ticket.id),
                ]
            )

    @api.depends("message_ids")
    def _compute_attachment_ids(self):
        Attachment = self.env["ir.attachment"]
        for ticket in self:
            ticket.attachment_ids = Attachment.search(
                [
                    ("res_model", "=", ticket._name),
                    ("res_id", "=", ticket.id),
                ]
            )

    @api.depends("create_date", "priority", "stage_id", "stage_id.is_closed")
    def _compute_sla_state(self):
        now = fields.Datetime.now()
        for ticket in self:
            if ticket.stage_id.is_closed:
                ticket.sla_state = "ok"
                ticket.sla_label = _("SLA respecté")
                continue
            hours = _SLA_HOURS.get(ticket.priority or "1", 24)
            deadline = ticket.create_date + timedelta(hours=hours) if ticket.create_date else now
            remaining = deadline - now
            remaining_hours = max(int(remaining.total_seconds() // 3600), 0)
            if remaining.total_seconds() <= 0:
                ticket.sla_state = "breach"
                ticket.sla_label = _("SLA dépassé")
            elif remaining_hours <= max(hours // 4, 1):
                ticket.sla_state = "warn"
                ticket.sla_label = _("SLA %(hours)sh restantes") % {"hours": remaining_hours}
            else:
                ticket.sla_state = "ok"
                ticket.sla_label = _("SLA OK")

    @api.depends(
        "priority",
        "category_id",
        "category_id.code",
        "diagnostic_count",
        "create_date",
        "write_date",
    )
    def _compute_kanban_display(self):
        priority_map = {
            "3": "p-critical",
            "2": "p-high",
            "1": "p-medium",
            "0": "p-low",
        }
        category_tag_map = {
            "crm": "tag-config",
            "rh": "tag-onboard",
            "dialer": "tag-config",
            "lea": "tag-ai",
            "billing": "tag-billing",
            "formation": "tag-onboard",
            "client_env": "tag-config",
        }
        now = fields.Datetime.now()
        for ticket in self:
            ticket.priority_css = priority_map.get(ticket.priority, "p-medium")
            code = ticket.category_id.code if ticket.category_id else False
            ticket.category_tag_class = category_tag_map.get(code, "tag-config")
            ticket.has_ai_flag = bool(ticket.diagnostic_count)
            ref_dt = ticket.write_date or ticket.create_date
            ticket.time_ago_label = ticket._format_time_ago(ref_dt, now)

    @api.model
    def _format_time_ago(self, ref_dt, now=None):
        if not ref_dt:
            return ""
        now = now or fields.Datetime.now()
        seconds = int((now - ref_dt).total_seconds())
        if seconds < 3600:
            minutes = max(1, seconds // 60)
            return _("Il y a %(minutes)smin", minutes=minutes)
        if seconds < 86400:
            hours = max(1, seconds // 3600)
            return _("Il y a %(hours)sh", hours=hours)
        days = max(1, seconds // 86400)
        if days == 1:
            return _("Hier")
        return _("Il y a %(days)sj", days=days)

    @api.model
    def get_dashboard_kpis(self):
        """KPI bar — maquette Kanban écran 1."""
        month_start = fields.Datetime.now().replace(day=1, hour=0, minute=0, second=0)
        open_domain = [("stage_id.is_closed", "=", False)]
        breach_domain = open_domain + [("sla_state", "=", "breach")]
        resolved_domain = [
            ("stage_id.code", "in", ("resolved", "closed")),
            ("write_date", ">=", fields.Datetime.to_string(month_start)),
        ]
        resolved = self.search(resolved_domain)
        resolved_count = len(resolved)
        durations = []
        for ticket in resolved:
            if ticket.create_date and ticket.write_date:
                mins = (ticket.write_date - ticket.create_date).total_seconds() / 60.0
                if mins > 0:
                    durations.append(mins)
        if durations:
            avg_mins = sum(durations) / len(durations)
            hours, mins = divmod(int(round(avg_mins)), 60)
            avg_resolution = f"{hours}h {mins}m" if hours else f"{mins}m"
        else:
            avg_resolution = "—"
        if resolved_count:
            ok = resolved.filtered(lambda t: t.sla_state != "breach")
            satisfaction = f"{round(100.0 * len(ok) / resolved_count)}%"
        else:
            satisfaction = "—"
        return {
            "open_total": self.search_count(open_domain),
            "sla_breach": self.search_count(breach_domain),
            "avg_resolution": avg_resolution,
            "satisfaction": satisfaction,
            "resolved_month": resolved_count,
        }

    @api.onchange("partner_id")
    def _onchange_partner_id_contact_user(self):
        if not self.partner_id:
            self.contact_user_id = False
            return
        if not self.company_id:
            self.company_id = self.env.company
        if self.contact_user_id:
            allowed = self.env["res.users"].search_count([
                ("id", "=", self.contact_user_id.id),
                ("partner_id", "child_of", self.partner_id.id),
                ("active", "=", True),
            ])
            if not allowed:
                self.contact_user_id = False

    @api.onchange("user_scope")
    def _onchange_user_scope(self):
        if self.user_scope != "specific":
            self.contact_user_id = False
        if self.user_scope != "group":
            self.scope_group_id = False

    def _sync_scope_from_legacy_fields(self, vals):
        """Compatibilité tickets existants sans user_scope."""
        if vals.get("user_scope"):
            return vals
        if vals.get("contact_user_id"):
            vals["user_scope"] = "specific"
        elif vals.get("scope_group_id"):
            vals["user_scope"] = "group"
        else:
            vals.setdefault("user_scope", "all")
        return vals

    @api.model_create_multi
    def create(self, vals_list):
        seq = self.env["ir.sequence"]
        user = self.env.user
        for vals in vals_list:
            vals = self._sync_scope_from_legacy_fields(vals)
            if vals.get("user_scope") != "specific":
                vals["contact_user_id"] = False
            if vals.get("user_scope") != "group":
                vals["scope_group_id"] = False
            if vals.get("name", _("Nouveau")) == _("Nouveau"):
                vals["name"] = seq.next_by_code("intellix.support.ticket") or _("Nouveau")
            if not vals.get("partner_id") and user.partner_id:
                vals["partner_id"] = user.partner_id.commercial_partner_id.id
            if not vals.get("contact_user_id") and not user._is_public():
                if (
                    vals.get("user_scope", "all") == "specific"
                    and (
                        not vals.get("partner_id")
                        or user.partner_id.commercial_partner_id.id == vals["partner_id"]
                    )
                ):
                    vals["contact_user_id"] = user.id
                    vals["user_scope"] = "specific"
            if "user_id" not in vals:
                vals["user_id"] = False
            vals.setdefault("company_id", user.company_id.id)
        tickets = super().create(vals_list)
        tickets._dispatch_support_alerts()
        return tickets

    def write(self, vals):
        vals = dict(vals)
        if "user_scope" in vals:
            if vals["user_scope"] != "specific":
                vals["contact_user_id"] = False
            if vals["user_scope"] != "group":
                vals["scope_group_id"] = False
        elif vals.get("contact_user_id"):
            vals.setdefault("user_scope", "specific")
        res = super().write(vals)
        alert_fields = {"priority", "sla_state", "side_origin", "stage_id"}
        if alert_fields & set(vals.keys()):
            self._dispatch_support_alerts()
        return res

    def _dispatch_support_alerts(self):
        dispatcher = self.env["intellix.support.alert.dispatcher"]
        for ticket in self:
            dispatcher.dispatch_for_ticket(ticket)

    def _auto_dispatch_cursor_bridge(self):
        """Lance l'analyse Cursor à la création (si bridge activé)."""
        bridge = self.env["intellix.support.cursor.bridge"]
        for ticket in self:
            bridge.maybe_dispatch_on_ticket_created(ticket)

    def action_analyze_with_cursor(self):
        """Bouton header — lance une analyse Cursor (POC, sans deploy)."""
        self.ensure_one()
        bridge = self.env["intellix.support.cursor.bridge"]
        info = bridge.dispatch_ticket_analysis(self, source="manual_button")
        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": _("Cursor"),
                "message": _(
                    "Analyse lancée — agent %(agent)s",
                    agent=info.get("agent_id") or "—",
                ),
                "type": "success",
                "sticky": False,
            },
        }

    def _format_create_date(self):
        self.ensure_one()
        if not self.create_date:
            return ""
        return format_datetime(self.env, self.create_date, dt_format="d MMMM yyyy · HH'h'mm")

    def action_run_diagnostic(self):
        self.ensure_one()
        return self.action_run_diagnostic_stay_on_ticket(open_popup=True)

    def action_run_diagnostic_stay_on_ticket(self, open_popup=False):
        """Lance diagnostic + Cursor + alerte Karine si demande non-bug."""
        self.ensure_one()
        if not self.partner_id:
            raise UserError(_("Sélectionnez d'abord l'organisation."))
        if not self.category_id:
            raise UserError(_("Sélectionnez le module concerné."))
        if self.user_scope == "group" and not self.scope_group_id:
            raise UserError(_("Sélectionnez le groupe d'utilisateurs."))
        if self.user_scope == "specific" and not self.contact_user_id:
            raise UserError(_("Sélectionnez l'utilisateur ciblé."))

        engine = self.env["intellix.support.diagnostic.engine"]
        diagnostic = engine.run_for_ticket(self)
        self.side_origin = diagnostic.side_origin or self.side_origin

        self.env["intellix.support.alert.dispatcher"].dispatch_karine_product_alert(self)

        if open_popup:
            return {
                "type": "ir.actions.act_window",
                "name": _("Diagnostic"),
                "res_model": "intellix.support.diagnostic",
                "view_mode": "form",
                "res_id": diagnostic.id,
                "target": "new",
            }
        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": _("Diagnostic"),
                "message": _("Analyse lancée — Copilot et Cursor notifiés."),
                "type": "success",
                "sticky": False,
            },
        }

    def action_run_diagnostic_refresh(self):
        """Relance le diagnostic et reste sur la fiche ticket."""
        for ticket in self:
            diagnostic = self.env["intellix.support.diagnostic.engine"].run_for_ticket(ticket)
            ticket.side_origin = diagnostic.side_origin or ticket.side_origin
        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": _("Diagnostic"),
                "message": _("Analyse Copilot mise à jour."),
                "type": "success",
                "sticky": False,
            },
        }

    def action_open_diagnostics(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": _("Diagnostics"),
            "res_model": "intellix.support.diagnostic",
            "view_mode": "list,form",
            "domain": [("ticket_id", "=", self.id)],
            "context": {"default_ticket_id": self.id},
        }

    def action_run_diagnostic_silent(self):
        """Lance le diagnostic depuis le Kanban sans ouvrir la popup."""
        for ticket in self:
            diagnostic = self.env["intellix.support.diagnostic.engine"].run_for_ticket(ticket)
            ticket.side_origin = diagnostic.side_origin or ticket.side_origin
        return True

    def action_inspect_diagnostic(self):
        """Ouvre le dernier diagnostic (panneau Copilot)."""
        self.ensure_one()
        if self.last_diagnostic_id:
            return {
                "type": "ir.actions.act_window",
                "name": _("Diagnostic"),
                "res_model": "intellix.support.diagnostic",
                "view_mode": "form",
                "res_id": self.last_diagnostic_id.id,
                "target": "new",
            }
        return self.action_run_diagnostic()

    def action_apply_suggested_fix(self):
        """Raccourci header — délègue au handler Copilot."""
        self.ensure_one()
        return self.copilot_dispatch_action("apply_fix")

    def _copilot_client_notify(self, title, message, ntype="info"):
        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": title,
                "message": message,
                "type": ntype,
                "sticky": False,
            },
        }

    def _copilot_stub(self, message, runbook_code=None):
        self.ensure_one()
        runbook = self.env["intellix.support.runbook"].browse()
        if runbook_code:
            runbook = self.env["intellix.support.runbook"].search(
                [("code", "=", runbook_code)], limit=1
            )
        _logger.info(
            "Copilot stub ticket=%s runbook=%s: %s",
            self.name,
            runbook.code if runbook else None,
            message,
        )
        self.message_post(
            body=f"<p><em>Copilot</em> — {escape(message)}</p>",
            subtype_xmlid="mail.mt_note",
        )
        return {"notify": {"title": _("Copilot"), "message": message, "type": "info"}}

    def _copilot_refresh_diagnostic(self):
        self.ensure_one()
        diagnostic = self.env["intellix.support.diagnostic.engine"].run_for_ticket(self)
        self.side_origin = diagnostic.side_origin or self.side_origin
        return {
            "reload": True,
            "notify": {
                "title": _("Diagnostic"),
                "message": _("Analyse Copilot mise à jour."),
                "type": "success",
            },
        }

    def _copilot_inspect_diagnostic(self):
        self.ensure_one()
        if self.last_diagnostic_id:
            return {
                "action": {
                    "type": "ir.actions.act_window",
                    "name": _("Diagnostic"),
                    "res_model": "intellix.support.diagnostic",
                    "view_mode": "form",
                    "res_id": self.last_diagnostic_id.id,
                    "target": "new",
                }
            }
        return self._copilot_refresh_diagnostic()

    def action_open_proposals(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": _("Propositions de correctif"),
            "res_model": "intellix.support.fix.proposal",
            "view_mode": "list,form",
            "domain": [("ticket_id", "=", self.id)],
            "context": {"default_ticket_id": self.id},
        }

    def _copilot_parse_checks(self):
        self.ensure_one()
        if not self.last_diagnostic_id or not self.last_diagnostic_id.result_json:
            return []
        try:
            return json.loads(self.last_diagnostic_id.result_json)
        except (TypeError, ValueError):
            return []

    def _copilot_match_runbook(self, runbook_code=None):
        self.ensure_one()
        Runbook = self.env["intellix.support.runbook"]
        if runbook_code:
            return Runbook.search([("code", "=", runbook_code), ("active", "=", True)], limit=1)
        checks = self._copilot_parse_checks()
        codes = {c.get("code") for c in checks}
        subject = (self.subject or "").lower()
        category_code = self.category_id.code if self.category_id else ""
        if category_code == "lea" or any(k in subject for k in ("léa", "lea", "86013", "qcb2c")):
            runbook = Runbook.search([("code", "=", "lea_silent"), ("active", "=", True)], limit=1)
            if runbook:
                return runbook
        if "user_account" in codes or "user_missing" in codes:
            return Runbook.search([("code", "=", "access_denied"), ("active", "=", True)], limit=1)
        if {"campaign_status", "campaign_none", "campaign_module"} & codes:
            return Runbook.search([("code", "=", "calls_not_dialing"), ("active", "=", True)], limit=1)
        if category_code == "dialer" or any(
            k in subject for k in ("appel", "dial", "vicidial", "hopper", "adl")
        ):
            return Runbook.search([("code", "=", "calls_not_dialing"), ("active", "=", True)], limit=1)
        return Runbook.browse()

    def _copilot_build_proposal_steps(self, runbook, checks):
        self.ensure_one()
        executor = self.env["intellix.support.runbook.executor"]
        return executor.build_proposal_steps(runbook, self, checks)

    def _copilot_build_proposal_steps_legacy(self, runbook, checks):
        self.ensure_one()
        user_check = next(
            (c for c in checks if c.get("code") in ("user_account", "user_missing")),
            None,
        )
        user_line = ""
        if user_check:
            user_line = f"<li>{escape(user_check.get('label', ''))} — {escape(user_check.get('detail', ''))}</li>"
        elif self.contact_user_id:
            user_line = (
                f"<li>{escape(_('Utilisateur concerné'))}: "
                f"{escape(self.contact_user_id.login)}</li>"
            )
        steps = runbook.description or ""
        if user_line:
            steps = (
                f"<p><strong>{escape(_('Contexte diagnostic'))}</strong></p>"
                f"<ul>{user_line}</ul>"
                f"{steps}"
            )
        if runbook.code == "access_denied":
            steps += (
                "<ol>"
                f"<li>{escape(_('Vérifier que le compte Odoo est actif.'))}</li>"
                f"<li>{escape(_('Réinitialiser le mot de passe temporaire.'))}</li>"
                f"<li>{escape(_('Communiquer les identifiants au client par canal sécurisé.'))}</li>"
                "</ol>"
            )
        return steps

    def _copilot_propose_fix(self, runbook_code=None):
        self.ensure_one()
        if not self.last_diagnostic_id:
            return {
                "notify": {
                    "title": _("Correctif"),
                    "message": _("Lancez d'abord un diagnostic."),
                    "type": "warning",
                }
            }
        runbook = self._copilot_match_runbook(runbook_code)
        if not runbook:
            return {
                "notify": {
                    "title": _("Correctif"),
                    "message": _("Aucun runbook correspondant au diagnostic."),
                    "type": "warning",
                }
            }
        open_states = ("draft", "pending_approval", "approved")
        existing = self.proposal_ids.filtered(
            lambda p: p.runbook_id == runbook and p.state in open_states
        )
        if existing:
            proposal = existing[:1]
            message = _("Proposition existante : %(name)s (%(state)s).") % {
                "name": proposal.name,
                "state": dict(proposal._fields["state"].selection).get(proposal.state),
            }
        else:
            checks = self._copilot_parse_checks()
            initial_state = "pending_approval" if runbook.requires_approval else "approved"
            vals = {
                "ticket_id": self.id,
                "runbook_id": runbook.id,
                "diagnostic_id": self.last_diagnostic_id.id,
                "steps_html": self._copilot_build_proposal_steps(runbook, checks),
                "state": initial_state,
            }
            if initial_state == "approved":
                vals["approved_by"] = self.env.user.id
                vals["approved_date"] = fields.Datetime.now()
            proposal = self.env["intellix.support.fix.proposal"].create(vals)
            message = _("Proposition %(name)s créée — runbook « %(runbook)s ».") % {
                "name": proposal.name,
                "runbook": runbook.name,
            }
            self.message_post(
                body=f"<p><em>Copilot</em> — {escape(message)}</p>",
                subtype_xmlid="mail.mt_note",
            )
        return {
            "reload": True,
            "notify": {
                "title": _("Proposition de correctif"),
                "message": message,
                "type": "success",
            },
        }

    def _copilot_approve_fix_proposal(self, runbook_code=None):
        self.ensure_one()
        if not self.env.user.has_group("intellix_support.group_intellix_support_manager"):
            return {
                "notify": {
                    "title": _("Approbation"),
                    "message": _("Réservé aux responsables support."),
                    "type": "danger",
                }
            }
        runbook = self._copilot_match_runbook(runbook_code)
        domain = [("ticket_id", "=", self.id), ("state", "=", "pending_approval")]
        if runbook:
            domain.append(("runbook_id", "=", runbook.id))
        proposal = self.env["intellix.support.fix.proposal"].search(domain, limit=1)
        if not proposal:
            return {
                "notify": {
                    "title": _("Approbation"),
                    "message": _("Aucune proposition en attente d'approbation."),
                    "type": "warning",
                }
            }
        proposal.action_approve()
        return {
            "reload": True,
            "notify": {
                "title": _("Correctif approuvé"),
                "message": _("Proposition %(name)s approuvée — prête à exécuter.") % {
                    "name": proposal.name,
                },
                "type": "success",
            },
        }

    def _copilot_execute_fix(self, runbook_code=None):
        self.ensure_one()
        if not self.env.user.has_group("intellix_support.group_intellix_support_manager"):
            return {
                "notify": {
                    "title": _("Exécution"),
                    "message": _("Réservé aux responsables support."),
                    "type": "danger",
                }
            }
        runbook = self._copilot_match_runbook(runbook_code)
        domain = [("ticket_id", "=", self.id), ("state", "=", "approved")]
        if runbook:
            domain.append(("runbook_id", "=", runbook.id))
        proposal = self.env["intellix.support.fix.proposal"].search(domain, limit=1)
        if not proposal:
            return {
                "notify": {
                    "title": _("Exécution"),
                    "message": _(
                        "Aucune proposition approuvée. Proposez puis approuvez le correctif d'abord."
                    ),
                    "type": "warning",
                }
            }
        if proposal.runbook_id.phase != "ready":
            return {
                "notify": {
                    "title": _("Exécution"),
                    "message": _("Ce runbook n'est pas encore exécutable (phase %(phase)s).") % {
                        "phase": proposal.runbook_id.phase,
                    },
                    "type": "warning",
                }
            }
        try:
            result = self.env["intellix.support.runbook.executor"].execute_proposal(proposal)
            proposal.write(
                {
                    "state": "executed",
                    "execution_log": result.get("log", ""),
                    "error_message": False,
                }
            )
            notify = result.get("notify") or {
                "title": _("Correctif exécuté"),
                "message": _("Runbook exécuté avec succès."),
                "type": "success",
            }
            return {"reload": True, "notify": notify}
        except Exception as err:
            proposal.write(
                {
                    "state": "failed",
                    "error_message": str(err),
                }
            )
            return {
                "reload": True,
                "notify": {
                    "title": _("Échec"),
                    "message": str(err),
                    "type": "danger",
                },
            }

    def _copilot_apply_fix(self, mode, runbook_code=None):
        self.ensure_one()
        runbook = self.env["intellix.support.runbook"].browse()
        if runbook_code:
            runbook = self.env["intellix.support.runbook"].search(
                [("code", "=", runbook_code)], limit=1
            )
        labels = {
            "auto": _("Correctif automatique enregistré — runbook « %(name)s » (approbation requise)."),
            "approve": _("Correctif approuvé — exécution runbook en attente d'implémentation."),
            "manual": _("Application manuelle du correctif — consultez le runbook associé."),
        }
        message = labels.get(mode, _("Correctif enregistré.")) % {
            "name": runbook.name if runbook else "—",
        }
        _logger.info("Copilot fix ticket=%s mode=%s runbook=%s", self.name, mode, runbook_code)
        self.message_post(
            body=f"<p><em>Copilot</em> — {escape(message)}</p>",
            subtype_xmlid="mail.mt_note",
        )
        return {
            "notify": {
                "title": _("Correctif"),
                "message": message,
                "type": "success" if mode == "approve" else "info",
            }
        }

    def _copilot_view_campaigns(self):
        self.ensure_one()
        if "doorway.campaign" not in self.env:
            return {
                "notify": {
                    "title": _("Campagnes"),
                    "message": _("Module doorway_vicidial_campaigns non installé."),
                    "type": "warning",
                }
            }
        domain = [("state", "in", ("active", "paused", "ready"))]
        if self.contact_user_id:
            domain = [("human_agent_user_ids", "in", self.contact_user_id.id)]
        return {
            "action": {
                "type": "ir.actions.act_window",
                "name": _("Campagnes VICIdial"),
                "res_model": "doorway.campaign",
                "view_mode": "list,form",
                "domain": domain,
                "target": "current",
            }
        }

    def _copilot_create_credits_account(self):
        self.ensure_one()
        if "doorway.credit.account" not in self.env:
            return {
                "notify": {
                    "title": _("Crédits IA"),
                    "message": _("Module crédits Doorway non installé."),
                    "type": "warning",
                }
            }
        return self._copilot_stub(
            _("Création compte crédits — wizard à brancher (hook Phase 2)."),
        )

    def _copilot_assign_credit_plan(self):
        self.ensure_one()
        return self._copilot_stub(
            _("Assignation plan crédits existant — wizard à brancher (hook Phase 2)."),
        )

    def _copilot_anydesk_id(self):
        self.ensure_one()
        return self.anydesk_id or (
            self.partner_id.support_anydesk_id if self.partner_id else False
        )

    def _copilot_request_anydesk_id(self):
        self.ensure_one()
        reply = _(
            '"Pour diagnostiquer votre poste à distance, pouvez-vous me communiquer '
            'votre ID AnyDesk (affiché dans l\'application AnyDesk) ?"'
        )
        self.message_post(
            body=(
                f"<p><em>{escape(_('Copilot AnyDesk'))}</em> — "
                f"{escape(_('Demande ID AnyDesk envoyée (réponse suggérée).'))}</p>"
            ),
            subtype_xmlid="mail.mt_note",
        )
        return {
            "notify": {
                "title": _("AnyDesk"),
                "message": _("Utilisez la réponse suggérée pour demander l'ID au client."),
                "type": "info",
            },
            "suggested_reply": reply,
        }

    def _copilot_confirm_anydesk_consent(self):
        self.ensure_one()
        if not self._copilot_anydesk_id():
            return {
                "notify": {
                    "title": _("AnyDesk"),
                    "message": _("Renseignez d'abord l'ID AnyDesk sur le ticket ou le partenaire."),
                    "type": "warning",
                }
            }
        self.anydesk_consent = True
        self.message_post(
            body=(
                f"<p><em>{escape(_('Copilot AnyDesk'))}</em> — "
                f"{escape(_('Consentement accès distant enregistré.'))}</p>"
            ),
            subtype_xmlid="mail.mt_note",
        )
        return {
            "reload": True,
            "notify": {
                "title": _("AnyDesk"),
                "message": _("Consentement enregistré — session distante autorisée."),
                "type": "success",
            },
        }

    def _copilot_open_anydesk_session(self):
        """Stub — ouvre le client AnyDesk local via protocole anydesk: (pas d'API cloud)."""
        self.ensure_one()
        anydesk_id = self._copilot_anydesk_id()
        if not anydesk_id:
            return self._copilot_request_anydesk_id()
        if not self.anydesk_consent:
            return {
                "notify": {
                    "title": _("AnyDesk"),
                    "message": _(
                        "Consentement client requis avant connexion. "
                        "Utilisez « Enregistrer le consentement »."
                    ),
                    "type": "warning",
                }
            }
        deeplink = f"anydesk:{anydesk_id}"
        self.message_post(
            body=(
                f"<p><em>{escape(_('Copilot AnyDesk'))}</em> — "
                f"{escape(_('Session distante initiée (stub)'))} "
                f"<a href=\"{escape(deeplink)}\">{escape(anydesk_id)}</a></p>"
            ),
            subtype_xmlid="mail.mt_note",
        )
        return {
            "notify": {
                "title": _("AnyDesk"),
                "message": _(
                    "Lien session : %(link)s — le client AnyDesk doit être installé "
                    "sur le poste support. API my.anydesk à brancher en Phase 3."
                )
                % {"link": deeplink},
                "type": "success",
            },
            "anydesk_deeplink": deeplink,
        }

    def _copilot_open_anydesk_tab(self):
        self.ensure_one()
        return {
            "notify": {
                "title": _("AnyDesk"),
                "message": _("Consultez l'onglet AnyDesk du ticket pour les notes de session."),
                "type": "info",
            }
        }

    def copilot_dispatch_action(self, action_code):
        """Route les boutons du panneau Copilot (appel RPC JS)."""
        self.ensure_one()
        dispatch = {
            "inspect_diagnostic": self._copilot_inspect_diagnostic,
            "refresh_diagnostic": self._copilot_refresh_diagnostic,
            "propose_fix": lambda: self._copilot_propose_fix("access_denied"),
            "propose_fix_auto": lambda: self._copilot_propose_fix(),
            "apply_fix_auto": lambda: self._copilot_propose_fix("access_denied"),
            "approve_fix": lambda: self._copilot_approve_fix_proposal("access_denied"),
            "approve_fix_proposal": lambda: self._copilot_approve_fix_proposal(),
            "execute_fix": lambda: self._copilot_execute_fix("access_denied"),
            "apply_fix": lambda: self._copilot_execute_fix("access_denied"),
            "view_campaigns": self._copilot_view_campaigns,
            "validate_campaign_config": lambda: self._copilot_stub(
                _("Validation configuration campagnes enregistrée."),
                "calls_not_dialing",
            ),
            "create_credits_account": self._copilot_create_credits_account,
            "assign_credit_plan": self._copilot_assign_credit_plan,
            "request_anydesk_id": self._copilot_request_anydesk_id,
            "confirm_anydesk_consent": self._copilot_confirm_anydesk_consent,
            "open_anydesk_session": self._copilot_open_anydesk_session,
            "open_anydesk_tab": self._copilot_open_anydesk_tab,
        }
        handler = dispatch.get(action_code)
        if not handler:
            return {
                "notify": {
                    "title": _("Copilot"),
                    "message": _("Action inconnue : %s") % action_code,
                    "type": "warning",
                }
            }
        return handler()

    def copilot_get_suggested_reply(self, index):
        """Retourne le texte d'une réponse suggérée pour le composer."""
        self.ensure_one()
        try:
            replies = json.loads(self.copilot_replies_data or "[]")
        except (TypeError, ValueError):
            replies = []
        idx = int(index)
        if idx < 0 or idx >= len(replies):
            return {"text": "", "error": _("Réponse introuvable.")}
        return {"text": replies[idx]}

    def copilot_ask(self, question):
        """Question libre au Copilot — Q&A contextuelle + note interne."""
        self.ensure_one()
        question = (question or "").strip()
        if not question:
            return {
                "notify": {
                    "title": _("AI Copilot"),
                    "message": _("Saisissez une question."),
                    "type": "warning",
                }
            }
        engine = self.env["intellix.support.diagnostic.engine"]
        llm = self.env["intellix.support.copilot.llm"]
        llm_result = llm.ask(self, question)
        answer_html = llm_result.get("html") or engine._answer_question_rules(self, question)
        source = llm_result.get("source", "rules")
        source_label = _("Claude") if source == "llm" else _("Règles")
        entry = (
            '<div class="copilot-chat-entry">'
            f'<div class="copilot-chat-q"><strong>{escape(_("Vous"))}</strong>'
            f"<p>{escape(question)}</p></div>"
            f'<div class="copilot-chat-a"><strong>{escape(_("Copilot"))} ({escape(source_label)})</strong>'
            f"{answer_html}</div></div>"
        )
        self.copilot_chat_log = (self.copilot_chat_log or "") + entry
        self.message_post(
            body=(
                f"<p><strong>{escape(_('Copilot Q'))}:</strong> {escape(question)}</p>"
                f"{answer_html}"
            ),
            subtype_xmlid="mail.mt_note",
        )
        return {
            "answer_html": answer_html,
            "chat_log": self.copilot_chat_log,
            "source": source,
            "reload": True,
            "notify": {
                "title": _("AI Copilot"),
                "message": _("Réponse générée (%s).") % source_label,
                "type": "success",
            },
        }

    def action_resolve(self):
        """Passe le ticket à l'étape Résolu."""
        self.ensure_one()
        stage = self.env["intellix.support.stage"].search(
            [("code", "=", "resolved")], limit=1
        )
        if stage:
            self.stage_id = stage
        return True

    def action_copilot_ask(self):
        """Compatibilité bouton object — le JS appelle copilot_ask directement."""
        self.ensure_one()
        return self.copilot_ask("")

    @api.model
    def _cron_check_sla_alerts(self):
        self.env["intellix.support.alert.dispatcher"].cron_check_sla_alerts()

    @api.model
    def _cron_poll_cursor_runs(self):
        self.env["intellix.support.cursor.bridge"].cron_poll_cursor_runs()
