# -*- coding: utf-8 -*-

from odoo import fields, models


class HrEmployeeRiad(models.Model):
    _inherit = "hr.employee"

    riad_establishment_id = fields.Many2one(
        "intellix.riad.establishment",
        string="Établissement hébergement",
        ondelete="set null",
        index=True,
        help="Renseigné uniquement pour le personnel du Module Hébergement. "
        "Les employés des autres sociétés restent vides.",
    )

    def _fix_work_address(self):
        """People Engine réécrit address_id depuis write ; sur Odoo 19 le champ
        vit sur hr.version et la réécriture relance write → RecursionError.
        Garde-fou uniquement : on n'altère pas la logique People Engine."""
        if self.env.context.get("_riad_fixing_work_address"):
            return
        return super(
            HrEmployeeRiad,
            self.with_context(_riad_fixing_work_address=True),
        )._fix_work_address()

    def _ensure_pe_profile(self):
        if self.env.context.get("riad_creating_staff"):
            return self
        return super()._ensure_pe_profile()
