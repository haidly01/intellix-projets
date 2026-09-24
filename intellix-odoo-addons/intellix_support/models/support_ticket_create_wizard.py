# -*- coding: utf-8 -*-
from odoo import _, api, fields, models
from odoo.exceptions import UserError


class IntellixSupportTicketCreateWizard(models.TransientModel):
    _name = "intellix.support.ticket.create.wizard"
    _description = "Assistant création ticket support"

    partner_id = fields.Many2one(
        "res.partner",
        string="Organisation",
        required=True,
        help="Société ou organisation cliente.",
    )
    user_scope = fields.Selection(
        [
            ("all", "Tous les utilisateurs"),
            ("group", "Groupe"),
            ("specific", "Utilisateur ciblé"),
        ],
        string="Portée",
        default="all",
        required=True,
    )
    scope_group_id = fields.Many2one(
        "res.groups",
        string="Groupe d'utilisateurs",
        domain="[('share', '=', False)]",
    )
    contact_user_id = fields.Many2one(
        "res.users",
        string="Utilisateur ciblé",
        domain="[('partner_id', 'child_of', partner_id), ('active', '=', True)]",
    )
    category_id = fields.Many2one(
        "intellix.support.category",
        string="Module",
        required=True,
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
        required=True,
    )
    subject = fields.Char(string="Sujet", required=True)
    description = fields.Html(
        string="Description",
        help="Décrivez le problème ou la demande. Vous pouvez joindre une capture d'écran via le composer après création.",
    )
    launch_diagnostic = fields.Boolean(
        string="Lancer le diagnostic immédiatement",
        default=True,
    )

    @api.onchange("partner_id")
    def _onchange_partner_id_scope(self):
        if self.contact_user_id and self.partner_id:
            allowed = self.env["res.users"].search_count(
                [
                    ("id", "=", self.contact_user_id.id),
                    ("partner_id", "child_of", self.partner_id.id),
                    ("active", "=", True),
                ]
            )
            if not allowed:
                self.contact_user_id = False
        if not self.partner_id:
            self.contact_user_id = False
            self.scope_group_id = False

    @api.onchange("user_scope")
    def _onchange_user_scope(self):
        if self.user_scope != "specific":
            self.contact_user_id = False
        if self.user_scope != "group":
            self.scope_group_id = False

    def _validate_scope(self):
        self.ensure_one()
        if self.user_scope == "group" and not self.scope_group_id:
            raise UserError(_("Sélectionnez un groupe d'utilisateurs."))
        if self.user_scope == "specific" and not self.contact_user_id:
            raise UserError(_("Sélectionnez l'utilisateur ciblé."))

    def action_create_ticket(self):
        self.ensure_one()
        self._validate_scope()
        ticket = self.env["intellix.support.ticket"].create(
            {
                "partner_id": self.partner_id.id,
                "user_scope": self.user_scope,
                "scope_group_id": self.scope_group_id.id if self.user_scope == "group" else False,
                "contact_user_id": self.contact_user_id.id
                if self.user_scope == "specific"
                else False,
                "category_id": self.category_id.id,
                "ticket_type": self.ticket_type,
                "subject": self.subject,
                "description": self.description,
            }
        )
        if self.launch_diagnostic:
            ticket.action_run_diagnostic_stay_on_ticket()
        return {
            "type": "ir.actions.act_window",
            "name": _("Ticket support"),
            "res_model": "intellix.support.ticket",
            "view_mode": "form",
            "res_id": ticket.id,
            "target": "current",
        }
