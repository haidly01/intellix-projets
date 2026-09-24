from odoo import api, fields, models


class RenovationSecteurTarif(models.Model):
    _name = "renovation.secteur.tarif"
    _description = "Tarif au lead par secteur"
    _order = "secteur"

    secteur = fields.Selection(
        [("reno", "Réno"), ("immobilier", "Immobilier")],
        required=True,
    )
    currency_id = fields.Many2one(
        "res.currency",
        default=lambda self: self.env.company.currency_id,
        required=True,
    )
    prix_par_lead = fields.Monetary(
        string="Prix par lead",
        currency_field="currency_id",
        required=True,
    )
    name = fields.Char(compute="_compute_name", store=True)

    _secteur_uniq = models.Constraint(
        "unique(secteur)",
        "Un seul tarif par secteur.",
    )

    @api.depends("secteur", "prix_par_lead")
    def _compute_name(self):
        labels = {"reno": "Rénovation", "immobilier": "Immobilier"}
        for rec in self:
            rec.name = "%s — %s $/lead" % (
                labels.get(rec.secteur) or rec.secteur or "",
                int(rec.prix_par_lead or 0),
            )
