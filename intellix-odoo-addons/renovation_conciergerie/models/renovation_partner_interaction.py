# -*- coding: utf-8 -*-
from odoo import api, fields, models


class RenovationPartnerInteraction(models.Model):
    """Historique d'interactions — table dédiée, pas mail.message CQ."""

    _name = "renovation.partner.interaction"
    _description = "Interaction CRM partenaire Réno Immobilier"
    _order = "date desc, id desc"
    _rec_name = "summary"

    partner_id = fields.Many2one(
        "res.partner",
        string="Partenaire",
        required=True,
        index=True,
        ondelete="cascade",
    )
    date = fields.Datetime(
        string="Date (UTC)",
        required=True,
        default=fields.Datetime.now,
        index=True,
    )
    kind = fields.Selection(
        [
            ("appel", "Appel"),
            ("email", "Courriel"),
            ("rdv", "Rendez-vous"),
            ("note", "Note"),
        ],
        string="Type",
        required=True,
        default="note",
        index=True,
    )
    summary = fields.Char(string="Résumé", required=True)
    body = fields.Text(string="Détail")
    user_id = fields.Many2one(
        "res.users",
        string="Par",
        required=True,
        default=lambda self: self.env.user,
        index=True,
    )
    rdv_id = fields.Many2one(
        "renovation.partner.rdv",
        string="RDV lié",
        ondelete="set null",
        index=True,
    )

    @api.model_create_multi
    def create(self, vals_list):
        recs = super().create(vals_list)
        for rec in recs:
            partner = rec.partner_id
            if (
                rec.kind in ("appel", "email")
                and partner.reno_crm_stage == "nouveau"
            ):
                partner.sudo().write({"reno_crm_stage": "contacte"})
            if not partner.reno_crm_user_id:
                partner.sudo().write({"reno_crm_user_id": rec.user_id.id})
            kind_label = dict(rec._fields["kind"].selection).get(rec.kind) or rec.kind
            partner.message_post(
                body="%s — %s" % (kind_label, rec.summary),
                message_type="comment",
            )
        return recs
