# -*- coding: utf-8 -*-

from odoo import api, fields, models


class IntellixRiadPractitioner(models.Model):
    _name = "intellix.riad.practitioner"
    _description = "Prestataire bien-être (dispo par personne)"
    _order = "kind, name"

    establishment_id = fields.Many2one(
        "intellix.riad.establishment",
        required=True,
        ondelete="cascade",
        index=True,
    )
    name = fields.Char(required=True)
    kind = fields.Selection(
        [
            ("staff", "Staff interne"),
            ("external", "Prestataire"),
        ],
        string="Statut",
        required=True,
        default="external",
        help="Staff interne : employé du riad. Prestataire : intervenante externe.",
    )
    partner_id = fields.Many2one("res.partner", string="Fiche contact")
    type_ids = fields.Many2many(
        "intellix.riad.wellness.type",
        "intellix_riad_pract_type_rel",
        "practitioner_id",
        "type_id",
        string="Soins pratiqués",
    )
    active = fields.Boolean(default=True)
    notes = fields.Text()
    pe_profile_id = fields.Many2one(
        "pe.employee.profile",
        string="Fiche personnel (people_engine)",
        ondelete="set null",
    )
    slot_ids = fields.One2many(
        "intellix.riad.wellness.slot",
        "practitioner_id",
        string="Créneaux",
    )

    def kind_label(self):
        self.ensure_one()
        kind = self.kind or ("staff" if self.pe_profile_id else "external")
        return "Staff interne" if kind == "staff" else "Prestataire"

    @api.onchange("pe_profile_id")
    def _onchange_pe_profile_id(self):
        if self.pe_profile_id:
            self.kind = "staff"
            self.name = (
                self.pe_profile_id.display_name
                or (self.pe_profile_id.employee_id.name if self.pe_profile_id.employee_id else "")
                or self.name
            )

    def init(self):
        self.env.cr.execute(
            """
            SELECT 1 FROM information_schema.columns
             WHERE table_name = 'intellix_riad_practitioner' AND column_name = 'kind'
            """
        )
        if not self.env.cr.fetchone():
            return
        self.env.cr.execute(
            """
            UPDATE intellix_riad_practitioner
               SET kind = 'staff'
             WHERE pe_profile_id IS NOT NULL
               AND (kind IS NULL OR kind = 'external')
            """
        )
