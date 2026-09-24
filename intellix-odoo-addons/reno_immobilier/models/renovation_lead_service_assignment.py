# -*- coding: utf-8 -*-
from odoo import api, fields, models

from .partner_match import services_overlap


class RenovationLeadServiceAssignmentReno(models.Model):
    _inherit = "renovation.lead.service.assignment"

    eligible_partner_ids = fields.Many2many(
        "res.partner",
        compute="_compute_eligible_partner_ids",
        string="Partenaires possibles",
    )

    @api.depends(
        "service_category_id",
        "lead_id",
        "lead_id.city",
    )
    def _compute_eligible_partner_ids(self):
        Package = self.env["renovation.partner.package"].sudo()
        active = Package.search([("state", "=", "active")]).mapped("partner_id")
        for rec in self:
            partners = active
            service_partners = active
            if rec.service_category_id:
                names = [rec.service_category_id.name]
                service_partners = active.filtered(
                    lambda p, n=names: services_overlap(
                        n, p.service_category_ids.mapped("name")
                    )
                )
            geo = service_partners
            if rec.lead_id and rec.lead_id.city:
                geo = service_partners.filtered(
                    lambda p, lead=rec.lead_id: lead._partner_covers_lead(p)
                )
            rec.eligible_partner_ids = geo or service_partners or active
