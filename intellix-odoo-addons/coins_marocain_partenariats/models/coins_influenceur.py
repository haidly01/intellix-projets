# -*- coding: utf-8 -*-
from odoo import api, fields, models


class CoinsInfluenceur(models.Model):
    _name = "coins.influenceur"
    _description = "Influenceur Coins Marocain"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "date_repere desc, name"

    name = fields.Char(string="Nom / compte", required=True, tracking=True)
    plateforme = fields.Selection(
        [
            ("instagram", "Instagram"),
            ("tiktok", "TikTok"),
            ("instagram_tiktok", "Instagram + TikTok"),
            ("autre", "Autre"),
        ],
        string="Plateforme",
        default="instagram",
        tracking=True,
    )
    ville = fields.Char(string="Ville")
    niche = fields.Char(
        string="Niche",
        help="food, hôtel/riad, spa, lifestyle, voyage, etc.",
    )
    abonnes = fields.Integer(string="Abonnés")
    taux_engagement = fields.Float(
        string="Taux d'engagement (%)",
        digits=(16, 2),
        help="Pourcentage d'engagement affiché tel quel (ex. 3.5 = 3,5 %).",
    )
    audience_locale = fields.Boolean(string="Audience locale")
    statut = fields.Selection(
        [
            ("a_contacter", "À contacter"),
            ("contacte", "Contacté"),
            ("en_discussion", "En discussion"),
            ("partenaire_actif", "Partenaire actif"),
            ("decline", "Décliné"),
        ],
        string="Statut",
        default="a_contacter",
        required=True,
        tracking=True,
        index=True,
    )
    contact = fields.Char(
        string="Contact",
        help="Email ou numéro WhatsApp (E.164).",
        tracking=True,
    )
    notes = fields.Text(string="Notes")
    repere_par = fields.Many2one(
        "res.users",
        string="Repéré par",
        default=lambda self: self.env.user,
        tracking=True,
    )
    date_repere = fields.Date(
        string="Date repérée",
        default=fields.Date.context_today,
        tracking=True,
    )
    entente_ids = fields.One2many(
        "coins.entente",
        "influenceur_id",
        string="Ententes",
    )
    entente_count = fields.Integer(
        string="Nb ententes",
        compute="_compute_entente_count",
    )
    active = fields.Boolean(default=True)

    @api.depends("entente_ids")
    def _compute_entente_count(self):
        for rec in self:
            rec.entente_count = len(rec.entente_ids)

    def action_open_ententes(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": "Ententes",
            "res_model": "coins.entente",
            "view_mode": "list,form,kanban",
            "domain": [("influenceur_id", "=", self.id)],
            "context": {
                "default_influenceur_id": self.id,
                "default_type_partenaire": "influenceur",
            },
        }
