# -*- coding: utf-8 -*-
from odoo import _, api, fields, models


class ResPartner(models.Model):
    _inherit = "res.partner"

    support_anydesk_id = fields.Char(string="ID AnyDesk (support)")
    support_ticket_ids = fields.One2many(
        "intellix.support.ticket",
        "partner_id",
        string="Tickets support",
    )
    support_ticket_count = fields.Integer(
        compute="_compute_support_ticket_count",
    )

    @api.depends("name", "parent_id", "is_company")
    @api.depends_context("support_ticket_partner_picker")
    def _compute_display_name(self):
        if not self.env.context.get("support_ticket_partner_picker"):
            return super()._compute_display_name()
        for partner in self:
            if partner.is_company:
                partner.display_name = partner.name or ""
            elif partner.parent_id:
                partner.display_name = f"{partner.name} ({partner.parent_id.name})"
            else:
                partner.display_name = partner.name or ""

    def _compute_support_ticket_count(self):
        for partner in self:
            partner.support_ticket_count = len(partner.support_ticket_ids)

    def action_view_support_tickets(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": "Tickets support",
            "res_model": "intellix.support.ticket",
            "view_mode": "kanban,list,form",
            "domain": [("partner_id", "=", self.id)],
            "context": {"default_partner_id": self.id},
        }

    def action_create_support_ticket(self):
        self.ensure_one()
        ticket = self.env["intellix.support.ticket"].create(
            {
                "subject": _("Nouveau ticket support"),
                "partner_id": self.id,
            }
        )
        return {
            "type": "ir.actions.act_window",
            "name": _("Ticket support"),
            "res_model": "intellix.support.ticket",
            "view_mode": "form",
            "res_id": ticket.id,
            "target": "current",
        }
