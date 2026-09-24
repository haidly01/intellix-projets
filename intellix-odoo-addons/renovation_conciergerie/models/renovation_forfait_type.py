from odoo import api, fields, models


class RenovationForfaitType(models.Model):
    _name = "renovation.forfait.type"
    _description = "Préréglage de forfait partenaire"
    _order = "secteur, leads_inclus, name"

    name = fields.Char(required=True)
    leads_inclus = fields.Integer(string="Leads inclus", default=0)
    secteur = fields.Selection(
        [("reno", "Réno"), ("immobilier", "Immobilier")],
        required=True,
        default="reno",
    )
    categories_services_ids = fields.Many2many(
        "renovation.service.category",
        "renovation_forfait_type_category_rel",
        "forfait_type_id",
        "category_id",
        string="Catégories de services",
    )
    currency_id = fields.Many2one(
        "res.currency",
        default=lambda self: self.env.company.currency_id,
        required=True,
    )
    prix = fields.Monetary(
        string="Prix du forfait",
        compute="_compute_prix",
        store=True,
        currency_field="currency_id",
    )
    active = fields.Boolean(default=True)

    @api.depends("name")
    def _compute_display_name(self):
        for rec in self:
            rec.display_name = rec.name or ""

    @api.depends("leads_inclus", "secteur")
    def _compute_prix(self):
        Tarif = self.env["renovation.secteur.tarif"]
        tarifs = {t.secteur: t.prix_par_lead for t in Tarif.search([])}
        for rec in self:
            rec.prix = (rec.leads_inclus or 0) * (tarifs.get(rec.secteur) or 0)
