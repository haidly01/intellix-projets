from odoo import api, fields, models
from odoo.exceptions import ValidationError


class RenovationForfaitCredit(models.Model):
    _name = "renovation.forfait.credit"
    _description = "Crédit promo / compensation retard"
    _order = "date desc, id desc"

    forfait_id = fields.Many2one(
        "renovation.partner.package",
        string="Forfait",
        required=True,
        ondelete="cascade",
        index=True,
    )
    nombre_leads = fields.Integer(string="Leads crédités", required=True)
    motif = fields.Selection(
        [
            ("promotion", "Promotion"),
            ("retard", "Retard"),
            ("autre", "Autre"),
        ],
        required=True,
        default="promotion",
    )
    note = fields.Text()
    date = fields.Date(default=fields.Date.context_today, required=True)
    cree_par = fields.Many2one(
        "res.users",
        string="Par",
        default=lambda self: self.env.user,
        required=True,
    )
    date_short = fields.Char(string="Date", compute="_compute_credit_labels")
    leads_signed = fields.Char(string="Leads", compute="_compute_credit_labels")

    _MONTHS_FR = (
        "", "janvier", "février", "mars", "avril", "mai", "juin",
        "juillet", "août", "septembre", "octobre", "novembre", "décembre",
    )

    @api.depends("date", "nombre_leads")
    def _compute_credit_labels(self):
        for rec in self:
            if rec.date:
                rec.date_short = "%s %s" % (rec.date.day, self._MONTHS_FR[rec.date.month])
            else:
                rec.date_short = False
            rec.leads_signed = "+%s" % (rec.nombre_leads or 0)

    @api.constrains("nombre_leads")
    def _check_nombre_leads(self):
        for rec in self:
            if rec.nombre_leads <= 0:
                raise ValidationError("Le nombre de leads crédités doit être supérieur à 0.")

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        for rec in records:
            package = rec.forfait_id
            if package.state == "expired" and package.leads_remaining > 0:
                package.state = "active"
        return records
