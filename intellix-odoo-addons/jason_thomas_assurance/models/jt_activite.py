from odoo import fields, models


class JTActivite(models.Model):
    _name = 'jt.activite'
    _description = 'Activité souscription JT'
    _order = 'opened desc'

    police_id = fields.Many2one('jt.police', string='Police', ondelete='cascade', index=True)
    activity_type = fields.Char('Type activité')
    activity_subtype = fields.Char('Sous-type')
    activity_type_tc = fields.Char('Code TC')
    opened = fields.Datetime('Ouverte le')
    closed = fields.Datetime('Fermée le')
    user_code = fields.Char('Code conseiller')
    details_fr = fields.Text('Détails (FR)')
    details_en = fields.Text('Details (EN)')
