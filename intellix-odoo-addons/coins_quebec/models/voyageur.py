# -*- coding: utf-8 -*-
from odoo import api, fields, models

from .partenariat import (
    CQ_PIPELINE_STAGES,
    CQ_REGIONS,
    cq_click_to_call_action,
    cq_group_expand_stage,
)


class CoinsQuebecVoyageur(models.Model):
    _name = "coins.quebec.voyageur"
    _description = "Demande voyageur (Coins Québec)"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "id desc"
    _rec_name = "name"

    name = fields.Char(string="Voyageur", required=True, tracking=True)
    phone = fields.Char(string="Téléphone")
    email = fields.Char(string="Email")
    region = fields.Selection(
        CQ_REGIONS,
        string="Région souhaitée",
        default="montreal",
        required=True,
        index=True,
    )
    city = fields.Char(string="Ville")
    type_sejour = fields.Selection(
        [
            ("hebergement", "Hébergement"),
            ("resto", "Restaurant"),
            ("spa", "Spa / bien-être"),
            ("activite", "Activité"),
            ("mixte", "Séjour mixte"),
        ],
        string="Type de séjour",
        default="hebergement",
        required=True,
        index=True,
    )
    stage = fields.Selection(
        CQ_PIPELINE_STAGES,
        string="Étape",
        default="nouveau",
        required=True,
        tracking=True,
        index=True,
        group_expand="_group_expand_stage",
    )

    @api.model
    def _group_expand_stage(self, stages, domain, order=None):
        return cq_group_expand_stage(self, stages, domain, order)

    def action_cq_phone_call(self):
        self.ensure_one()
        return cq_click_to_call_action(self.env, self.phone)
    notes = fields.Text(string="Notes")
    active = fields.Boolean(default=True)
    reservation_id = fields.Many2one(
        "coins.quebec.reservation",
        string="Réservation liée",
        ondelete="set null",
    )
    cq_evt_style = fields.Selection(
        [
            ("moderne", "Moderne"),
            ("traditionnel", "Traditionnel"),
            ("nature_rural", "Nature-Rural"),
            ("desert", "Nordique"),
        ],
        string="Style lieu (brouillon)",
        copy=False,
    )
    cq_evt_note_lieu = fields.Text(string="Lieu pressenti", copy=False)
    cq_evt_note_menu = fields.Text(string="Menu (note)", copy=False)
    cq_evt_note_divert = fields.Text(string="Divertissement (note)", copy=False)
    cq_evt_note_deco = fields.Text(string="Décoration (note)", copy=False)
    cq_evt_note_heberg = fields.Text(string="Hébergement (note)", copy=False)
    cq_evt_resume = fields.Text(
        string="Résumé événement (brouillon)",
        copy=False,
        help="Assemblé par le wizard. Pas envoyé au voyageur.",
    )

    def action_cq_planifier_evenement(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": "Planifier l'événement",
            "res_model": "coins.quebec.planifier.evenement.wizard",
            "view_mode": "form",
            "target": "new",
            "context": {
                "default_voyageur_id": self.id,
                "dialog_size": "extra-large",
            },
        }
