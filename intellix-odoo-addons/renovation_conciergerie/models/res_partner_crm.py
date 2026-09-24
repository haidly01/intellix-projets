# -*- coding: utf-8 -*-
"""CRM partenaires Réno Immobilier — champs pipeline sur res.partner.

Modèles dédiés (pas coins.quebec.partenariat). Les colonnes existantes
Nom / E-mail / Téléphone / Ville / Services / Couverture / Forfait
ne sont pas remplacées.
"""
from odoo import _, api, fields, models

from .reno_rdv_tz import reno_format_canada_short

# Pipeline Réno Immobilier (B2B partenaires, pas hôtels CQ).
# Référence CQ = Nouveau → Contacté → En RDV → Suivis → Entente → Gagné/Perdu.
# Ici : pas d'Entente visibilité ; Actif = partenaire en relation commerciale.
# Liste figée (demandée avant durcissement) :
RENO_CRM_STAGES = [
    ("nouveau", "Nouveau"),
    ("contacte", "Contacté"),
    ("rdv_pris", "RDV pris"),
    ("suivi", "Suivi"),
    ("actif", "Actif"),
    ("perdu", "Perdu"),
]
RENO_CRM_STAGES_CLOSED = ("actif", "perdu")
RENO_CRM_STAGES_TO_RDV = ("nouveau", "contacte", "suivi")


def reno_group_expand_crm_stage(records, stages, domain, order=None):
    """Colonnes kanban = sequence ir.model.fields.selection (ignore order SQL)."""
    del stages, domain, order
    Selection = records.env["ir.model.fields.selection"].sudo()
    field = records.env["ir.model.fields"].sudo().search(
        [("model", "=", records._name), ("name", "=", "reno_crm_stage")],
        limit=1,
    )
    if field:
        recs = Selection.search([("field_id", "=", field.id)], order="sequence, id")
        values = [r.value for r in recs if r.value in dict(RENO_CRM_STAGES)]
        if values:
            return values
    return [value for value, _label in RENO_CRM_STAGES]


class ResPartnerRenoCrm(models.Model):
    _inherit = "res.partner"

    reno_crm_stage = fields.Selection(
        RENO_CRM_STAGES,
        string="Étape CRM Réno",
        default="nouveau",
        index=True,
        tracking=True,
        copy=False,
        group_expand="_reno_group_expand_crm_stage",
    )
    reno_crm_user_id = fields.Many2one(
        "res.users",
        string="Suivi commercial",
        tracking=True,
        index=True,
        copy=False,
        help="Qui suit la fiche (Leila, etc.). Le calendrier RDV reste Martin.",
    )
    reno_crm_rdv_event_id = fields.Many2one(
        "calendar.event",
        string="Réunion Martin planifiée",
        copy=False,
        ondelete="set null",
        index=True,
    )
    reno_crm_rdv_ids = fields.One2many(
        "renovation.partner.rdv",
        "partner_id",
        string="RDV Martin",
    )
    reno_crm_interaction_ids = fields.One2many(
        "renovation.partner.interaction",
        "partner_id",
        string="Historique des interactions",
    )
    reno_crm_interaction_count = fields.Integer(
        compute="_compute_reno_crm_meeting_display",
    )
    reno_crm_meeting_label = fields.Char(
        compute="_compute_reno_crm_meeting_display",
    )
    reno_crm_meeting_date = fields.Char(
        compute="_compute_reno_crm_meeting_display",
        string="Créneau (heure du Canada)",
    )
    reno_crm_rdv_booked_display = fields.Char(
        compute="_compute_reno_crm_meeting_display",
        string="RDV pris le",
    )

    @api.model
    def _reno_group_expand_crm_stage(self, stages, domain, order=None):
        return reno_group_expand_crm_stage(self, stages, domain, order)

    @api.model
    def _reno_crm_martin_user(self):
        return self.env["renovation.partner.rdv"]._reno_martin_user()

    @api.depends(
        "reno_crm_rdv_event_id",
        "reno_crm_rdv_event_id.start",
        "reno_crm_rdv_event_id.create_date",
        "reno_crm_rdv_event_id.active",
        "reno_crm_interaction_ids",
    )
    def _compute_reno_crm_meeting_display(self):
        for rec in self:
            rec.reno_crm_interaction_count = len(rec.reno_crm_interaction_ids)
            event = rec.reno_crm_rdv_event_id
            if event and event.active and event.start:
                rec.reno_crm_meeting_label = _("Prochaine réunion")
                rec.reno_crm_meeting_date = reno_format_canada_short(event.start)
                booked = reno_format_canada_short(event.create_date)
                rec.reno_crm_rdv_booked_display = (
                    _("Pris le %s") % booked if booked else False
                )
            else:
                rec.reno_crm_meeting_label = _("Aucune réunion")
                rec.reno_crm_meeting_date = False
                rec.reno_crm_rdv_booked_display = False

    def _reno_crm_mark_rdv_pris(self, event=None):
        """Colonne RDV pris. N'ouvre pas Actif / Perdu."""
        for rec in self:
            vals = {}
            if event and event.exists():
                vals["reno_crm_rdv_event_id"] = event.id
            if rec.reno_crm_stage in RENO_CRM_STAGES_TO_RDV:
                vals["reno_crm_stage"] = "rdv_pris"
            if vals:
                rec.with_context(reno_skip_rdv_stage=True).write(vals)

    def action_reno_book_martin_partner(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": _("Planifier une réunion (Martin)"),
            "res_model": "renovation.book.martin.wizard",
            "view_mode": "form",
            "target": "new",
            "context": {
                "default_partner_id": self.id,
                "default_lead_id": False,
            },
        }

    def action_reno_partner_meeting_stat(self):
        self.ensure_one()
        event = self.reno_crm_rdv_event_id
        if event and event.active:
            return {
                "type": "ir.actions.act_window",
                "name": _("Réunion"),
                "res_model": "calendar.event",
                "view_mode": "form",
                "res_id": event.id,
                "target": "current",
            }
        return self.action_reno_book_martin_partner()

    def action_reno_log_interaction(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": _("Noter une interaction"),
            "res_model": "renovation.partner.interaction",
            "view_mode": "form",
            "target": "new",
            "context": {
                "default_partner_id": self.id,
                "default_user_id": self.env.uid,
            },
        }

    def write(self, vals):
        res = super().write(vals)
        if (
            vals.get("reno_crm_rdv_event_id")
            and "reno_crm_stage" not in vals
            and not self.env.context.get("reno_skip_rdv_stage")
        ):
            to_move = self.filtered(
                lambda r: r.reno_crm_stage in RENO_CRM_STAGES_TO_RDV
            )
            if to_move:
                super(ResPartnerRenoCrm, to_move).write({"reno_crm_stage": "rdv_pris"})
        return res
