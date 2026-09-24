# -*- coding: utf-8 -*-
from odoo import api, fields, models


class CoinsEvenementPrestataire(models.Model):
    _name = "coins.evenement.prestataire"
    _description = "Prestataire assigné à un événement"
    _order = "category, id"

    evenement_id = fields.Many2one(
        "coins.evenement",
        string="Événement",
        required=True,
        ondelete="cascade",
        index=True,
    )
    partner_activity_id = fields.Many2one(
        "coins.partner_activity", string="Partenaire activité", ondelete="set null"
    )
    detente_partner_id = fields.Many2one(
        "coins.detente_partner", string="Partenaire bien-être", ondelete="set null"
    )
    partner_id = fields.Many2one("res.partner", string="Contact", ondelete="set null")
    category = fields.Selection(
        [
            ("artist", "Artiste / spectacle"),
            ("photo", "Photographe / vidéaste"),
            ("catering", "Traiteur"),
            ("deco", "Décoration"),
            ("furniture", "Mobilier"),
            ("coordination", "Coordination"),
            ("wellness", "Bien-être"),
            ("other", "Autre"),
        ],
        string="Prestation",
        default="other",
        required=True,
    )
    currency_id = fields.Many2one(
        related="evenement_id.currency_id", readonly=True
    )
    cost_planned = fields.Monetary(
        string="Coût prévu", currency_field="currency_id", default=0
    )
    cost_actual = fields.Monetary(
        string="Coût réel", currency_field="currency_id", default=0
    )
    commission_pct = fields.Float(
        string="Commission (%)",
        help="Taux variable par prestataire (repris du partenaire si vide).",
    )
    confirmation_state = fields.Selection(
        [
            ("to_contact", "À contacter"),
            ("quote_requested", "Devis demandé"),
            ("confirmed", "Confirmé"),
            ("paid", "Payé"),
        ],
        string="Confirmation",
        default="to_contact",
        required=True,
    )
    quote_requested_date = fields.Date(
        string="Devis demandé le",
        help="Date de passage en « Devis demandé » — relance auto après 3 jours.",
    )
    notes = fields.Text(string="Notes")
    display_name = fields.Char(compute="_compute_display_name")

    @api.depends(
        "partner_activity_id.name",
        "detente_partner_id.name",
        "partner_id.name",
        "category",
    )
    def _compute_display_name(self):
        cat = dict(self._fields["category"].selection)
        for rec in self:
            label = (
                rec.partner_activity_id.name
                or rec.detente_partner_id.name
                or rec.partner_id.name
                or "Prestataire"
            )
            rec.display_name = f"{label} — {cat.get(rec.category, rec.category)}"

    @api.onchange("partner_activity_id", "detente_partner_id")
    def _onchange_partner_commission(self):
        for rec in self:
            if rec.partner_activity_id and getattr(
                rec.partner_activity_id, "commission_pct", False
            ):
                rec.commission_pct = rec.partner_activity_id.commission_pct
                continue
            dp = rec.detente_partner_id
            if not dp:
                continue
            if (
                getattr(dp, "commission_type", None) == "percent"
                and getattr(dp, "commission_value", None)
            ):
                rec.commission_pct = dp.commission_value
            elif getattr(dp, "direct_rental_commission_percent", None):
                rec.commission_pct = dp.direct_rental_commission_percent

    def write(self, vals):
        if vals.get("confirmation_state") == "quote_requested" and not vals.get(
            "quote_requested_date"
        ):
            vals = dict(vals, quote_requested_date=fields.Date.context_today(self))
        return super().write(vals)
