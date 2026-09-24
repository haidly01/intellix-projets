from odoo import fields, models


class JTTransaction(models.Model):
    _name = 'jt.transaction'
    _description = 'Transaction / événement police JT'
    _order = 'event_date desc'

    police_id = fields.Many2one('jt.police', string='Police', ondelete='cascade', index=True)
    client_name = fields.Char('Nom client')
    event_type = fields.Char('Type événement')
    event_date = fields.Datetime('Date événement')
    reference = fields.Char('Référence')
    source = fields.Selection([
        ('ago', 'AGO'),
        ('inalco', 'Inalco'),
        ('assomption_vie', 'Assomption Vie'),
    ], string='Source')
    pdf_url = fields.Char('URL PDF')
