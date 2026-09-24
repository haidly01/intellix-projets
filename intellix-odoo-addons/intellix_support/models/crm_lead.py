# -*- coding: utf-8 -*-
from odoo import fields, models


class CrmLead(models.Model):
    _inherit = "crm.lead"

    support_ticket_ids = fields.One2many(
        "intellix.support.ticket",
        "crm_lead_id",
        string="Tickets support",
    )
    support_ticket_count = fields.Integer(
        compute="_compute_support_ticket_count",
    )

    def _compute_support_ticket_count(self):
        for lead in self:
            lead.support_ticket_count = len(lead.support_ticket_ids)

    def action_create_support_ticket(self):
        self.ensure_one()
        partner = self.partner_id or (
            self.env["res.partner"].search([("email", "=", self.email_from)], limit=1)
            if self.email_from
            else self.env["res.partner"]
        )
        ticket = self.env["intellix.support.ticket"].create(
            {
                "subject": self.name or "Support CRM",
                "partner_id": partner.id if partner else False,
                "crm_lead_id": self.id,
                "contact_user_id": self.user_id.id if self.user_id else False,
            }
        )
        return {
            "type": "ir.actions.act_window",
            "name": "Ticket support",
            "res_model": "intellix.support.ticket",
            "view_mode": "form",
            "res_id": ticket.id,
        }

    def action_view_support_tickets(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": "Tickets support",
            "res_model": "intellix.support.ticket",
            "view_mode": "kanban,list,form",
            "domain": [("crm_lead_id", "=", self.id)],
            "context": {"default_crm_lead_id": self.id, "default_partner_id": self.partner_id.id},
        }
