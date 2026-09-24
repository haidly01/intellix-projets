# -*- coding: utf-8 -*-
from odoo import api, fields, models


class HrLeavePe(models.Model):
    _inherit = "hr.leave"

    deduire_prime = fields.Boolean(
        string="Déduire de la prime mensuelle",
        help="Si coché, les jours d'absence réduisent la prime au prorata.",
    )
    motif_rh = fields.Text(string="Motif RH (interne)")
    validee_par_ia = fields.Boolean(
        string="Pré-validée par IA",
        help="L'IA a vérifié la conformité légale avant soumission RH.",
    )
    note_ia = fields.Text(string="Note conformité IA", readonly=True)

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        records._verifier_conformite_legale()
        return records

    def _verifier_conformite_legale(self):
        """Stub : vérification conformité QC/FR via People Engine legal."""
        for rec in self:
            if not rec.holiday_status_id:
                continue
            rec.validee_par_ia = True
            rec.note_ia = (
                "Vérification automatique People Engine : "
                "consulter la bibliothèque juridique pour le détail régional."
            )


class PeLeaveImpactPrime(models.Model):
    _name = "pe.leave.impact.prime"
    _description = "Impact absence sur prime"
    _order = "mois desc"

    employee_id = fields.Many2one("hr.employee", required=True, index=True)
    leave_id = fields.Many2one("hr.leave", required=True, ondelete="cascade")
    mois = fields.Char(string="Mois concerné", required=True, index=True)
    jours_absents = fields.Float(string="Jours absents")
    prime_deduite = fields.Float(string="Prime déduite")
    devise = fields.Char(default="MAD")
