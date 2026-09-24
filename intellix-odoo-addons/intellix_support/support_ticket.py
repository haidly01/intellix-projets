# -*- coding: utf-8 -*-
import logging

from odoo import _, api, fields, models

_logger = logging.getLogger(__name__)


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
        string="Partenaire client",
        tracking=True,
        index=True,
        help="Société ou organisation cliente. Laissez vide l'utilisateur pour un ticket au niveau du partenaire entier.",
    )
    user_id = fields.Many2one(
        "res.users",
        string="Assigné à",
        tracking=True,
        default=lambda self: self.env.user,
        index=True,
    )
    category_id = fields.Many2one(
        "intellix.support.category",
        string="Catégorie",
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
        string="Utilisateur concerné",
        help="Compte Odoo précis impacté. Laisser vide = tous les utilisateurs du partenaire.",
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
    copilot_suggestions = fields.Html(
        string="Suggestions Copilot",
        help="Actions suggérées par l'IA (phase 2).",
    )
    company_id = fields.Many2one(
        "res.company",
        default=lambda self: self.env.company,
        required=True,
    )

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

    @api.depends("diagnostic_ids")
    def _compute_last_diagnostic(self):
        for ticket in self:
            diag = ticket.diagnostic_ids[:1]
            ticket.last_diagnostic_id = diag
            ticket.diagnostic_summary_html = diag.summary_html if diag else False

    @api.onchange("partner_id")
    def _onchange_partner_id_contact_user(self):
        if not self.partner_id:
            self.contact_user_id = False
            return
        if self.contact_user_id:
            allowed = self.env["res.users"].search_count([
                ("id", "=", self.contact_user_id.id),
                ("partner_id", "child_of", self.partner_id.id),
                ("active", "=", True),
            ])
            if not allowed:
                self.contact_user_id = False

    @api.model_create_multi
    def create(self, vals_list):
        seq = self.env["ir.sequence"]
        user = self.env.user
        for vals in vals_list:
            if vals.get("name", _("Nouveau")) == _("Nouveau"):
                vals["name"] = seq.next_by_code("intellix.support.ticket") or _("Nouveau")
            if not vals.get("partner_id") and user.partner_id:
                vals["partner_id"] = user.partner_id.commercial_partner_id.id
            if not vals.get("contact_user_id") and not user._is_public():
                if (
                    not vals.get("partner_id")
                    or user.partner_id.commercial_partner_id.id == vals["partner_id"]
                ):
                    vals["contact_user_id"] = user.id
            vals.setdefault("company_id", user.company_id.id)
        return super().create(vals_list)

    def action_run_diagnostic(self):
        self.ensure_one()
        engine = self.env["intellix.support.diagnostic.engine"]
        diagnostic = engine.run_for_ticket(self)
        self.side_origin = diagnostic.side_origin or self.side_origin
        return {
            "type": "ir.actions.act_window",
            "name": _("Diagnostic"),
            "res_model": "intellix.support.diagnostic",
            "view_mode": "form",
            "res_id": diagnostic.id,
            "target": "new",
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
            self.env["intellix.support.diagnostic.engine"].run_for_ticket(ticket)
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
        """Phase 2 — runbook approuvé ; notification placeholder MVP."""
        self.ensure_one()
        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": _("Correctif"),
                "message": _(
                    "Application de correctif via runbook approuvé — disponible en phase 2."
                ),
                "type": "info",
                "sticky": False,
            },
        }
