# -*- coding: utf-8 -*-
from odoo import api, fields, models, _


class CoinsQuebecSendEntenteWizard(models.TransientModel):
    """Popup mauve — Martin envoie l'entente depuis la fiche CQ (resto compris)."""

    _name = "coins.quebec.send.entente.wizard"
    _description = "Envoyer l'entente Coins Québec"

    partenariat_id = fields.Many2one(
        "coins.quebec.partenariat",
        string="Fiche",
        required=True,
        ondelete="cascade",
    )
    etablissement = fields.Char(related="partenariat_id.name", readonly=True)
    type_label = fields.Char(string="Catégorie", compute="_compute_offer")
    commission_pct = fields.Integer(string="Commission %", compute="_compute_offer")
    contact = fields.Char(string="Destinataire", compute="_compute_offer")
    statut = fields.Char(string="Statut", compute="_compute_offer")

    @api.depends(
        "partenariat_id",
        "partenariat_id.type_partenaire",
        "partenariat_id.email",
        "partenariat_id.phone",
        "partenariat_id.cq_entente_res_id",
        "partenariat_id.cq_entente_label",
    )
    def _compute_offer(self):
        labels = {
            "hebergement": "Hébergement",
            "spa": "Spa / bien-être",
            "resto": "Restaurant / Gourmand",
            "activite": "Activité / divertissement",
            "evenement": "Événement",
            "autre": "Partenaire",
        }
        for wiz in self:
            part = wiz.partenariat_id
            if not part:
                wiz.type_label = False
                wiz.commission_pct = 0
                wiz.contact = False
                wiz.statut = False
                continue
            kind = part.type_partenaire or "autre"
            wiz.type_label = labels.get(kind, "Partenaire")
            wiz.commission_pct = int(part._cq_commission_pct())
            wiz.contact = (part.email or "").strip() or (part.phone or "").strip() or _(
                "Aucun email ni téléphone"
            )
            wiz.statut = part.cq_entente_label or _("Aucune entente")

    def action_confirm(self):
        self.ensure_one()
        return self.partenariat_id.action_cq_send_entente_now()
