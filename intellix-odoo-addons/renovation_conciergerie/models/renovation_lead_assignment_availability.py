from odoo import models


class RenovationLeadAssignmentAvailability(models.Model):
    _inherit = "crm.lead"

    def _find_partner_for_service(self, service):
        partners = self.env["res.partner"].search([
            ("package_ids.state", "=", "active"),
            ("service_category_ids", "in", service.id),
        ])
        for partner in partners:
            package = partner.active_package_id
            if package and not package._has_available_leads():
                continue
            if self._partner_covers_lead(partner):
                return partner
        return None
