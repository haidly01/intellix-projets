import re
from odoo import api, fields, models
from math import radians, sin, cos, sqrt, atan2


class RenovationLeadAssignment(models.Model):
    _inherit = "crm.lead"

    assigned_partner_id = fields.Many2one(
        "res.partner",
        string="Partenaire principal assigné",
        tracking=True,
    )
    assignment_date = fields.Datetime(
        string="Date d'attribution",
        readonly=True,
    )
    assignment_status = fields.Selection([
        ("pending", "En attente"),
        ("assigned", "Assigné"),
        ("partial", "Partiellement assigné"),
        ("no_match", "Aucun partenaire trouvé"),
    ], string="Statut attribution", default="pending")

    service_assignment_ids = fields.One2many(
        "renovation.lead.service.assignment",
        "lead_id",
        string="Attributions par service",
    )

    service_category_ids = fields.Many2many(
        "renovation.service.category",
        "crm_lead_service_category_rel",
        "lead_id",
        "category_id",
        string="Services demandés",
    )
    rdv_notes = fields.Text(string="Notes RDV")

    def _haversine_distance(self, lat1, lon1, lat2, lon2):
        R = 6371
        lat1, lon1, lat2, lon2 = map(radians, [lat1, lon1, lat2, lon2])
        dlat = lat2 - lat1
        dlon = lon2 - lon1
        a = sin(dlat/2)**2 + cos(lat1) * cos(lat2) * sin(dlon/2)**2
        c = 2 * atan2(sqrt(a), sqrt(1 - a))
        return R * c

    def _partner_covers_lead(self, partner):
        """Vérifie si la zone du partenaire couvre l'adresse du lead"""
        mode = partner.coverage_mode

        if mode == "province":
            return self.state_id and self.state_id in partner.province_ids

        elif mode == "city":
            if not partner.city_text:
                return False
            text = partner.city_text.lower()
            lead_city = (self.city or "").lower().strip()
            if not lead_city:
                return False
            # Separateur-agnostique : virgules, points-virgules, sauts de ligne
            tokens = [t.strip() for t in re.split(r"[,;\n]+", text) if t.strip()]
            if lead_city in tokens:
                return True
            # Tolerance : la ville du lead apparait dans le texte (gere les espaces)
            return lead_city in text

        elif mode == "postal":
            def _norm(z):
                return re.sub(r"[^a-z0-9]", "", (z or "").lower())
            lead_zip = _norm(self.zip)
            if not lead_zip:
                return False
            partner_zips = {_norm(z) for z in partner.postal_code_ids.mapped("postal_code")}
            return lead_zip in partner_zips

        elif mode == "radius":
            if not (partner.partner_latitude and partner.partner_longitude):
                return False
            lead_lat = getattr(self, "partner_latitude", 0)
            lead_lon = getattr(self, "partner_longitude", 0)
            if not (lead_lat and lead_lon):
                return False
            distance = self._haversine_distance(
                partner.partner_latitude,
                partner.partner_longitude,
                lead_lat,
                lead_lon,
            )
            return distance <= partner.coverage_radius_km

        return False

    def _find_partner_for_service(self, service):
        """Trouve le meilleur partenaire pour un service donné"""
        partners = self.env["res.partner"].search([
            ("package_ids.state", "=", "active"),
            ("service_category_ids", "in", service.id),
        ])
        for partner in partners:
            if self._partner_covers_lead(partner):
                return partner
        return None

    def action_assign_partner(self):
        """Attribution par service — 1 partenaire par service"""
        for lead in self:
            # Nettoie les anciennes attributions
            lead.service_assignment_ids.unlink()

            services = lead.service_category_ids
            if not services:
                lead.write({"assignment_status": "no_match"})
                continue

            assigned_partners = self.env["res.partner"]
            assignments = []

            for service in services:
                partner = lead._find_partner_for_service(service)
                status = "assigned" if partner else "no_match"
                assignments.append({
                    "lead_id": lead.id,
                    "service_category_id": service.id,
                    "partner_id": partner.id if partner else False,
                    "status": status,
                    "assignment_date": fields.Datetime.now() if partner else False,
                })
                if partner:
                    assigned_partners |= partner

            # Crée les attributions
            self.env["renovation.lead.service.assignment"].create(assignments)
            lead._recompute_partner_assignment_status()

        return True

    def _recompute_partner_assignment_status(self):
        for lead in self:
            assignments = lead.service_assignment_ids.filtered(lambda a: a.partner_id)
            if not assignments:
                lead.write({
                    "assigned_partner_id": False,
                    "assignment_status": "no_match",
                })
                continue

            assigned_partners = assignments.mapped("partner_id")
            statuses = set(assignments.mapped("status"))
            accepted_count = len(assignments.filtered(lambda a: a.status == "accepted"))

            if accepted_count == len(assignments):
                global_status = "assigned"
            elif accepted_count > 0 or "assigned" in statuses or "postponed" in statuses:
                global_status = "partial"
            elif statuses == {"no_match"}:
                global_status = "no_match"
            else:
                global_status = "pending"

            lead.write({
                "assigned_partner_id": assigned_partners[:1].id if assigned_partners else False,
                "assignment_date": fields.Datetime.now(),
                "assignment_status": global_status,
            })

    @api.model_create_multi
    def create(self, vals_list):
        leads = super().create(vals_list)
        for lead in leads:
            if lead.service_category_ids:
                lead.action_assign_partner()
        return leads
