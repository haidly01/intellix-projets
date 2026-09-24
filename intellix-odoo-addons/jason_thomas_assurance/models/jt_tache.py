from datetime import date, timedelta

from odoo import api, fields, models


class JTTache(models.Model):
    _name = 'jt.tache'
    _description = 'Tâche Jason Thomas Assurance'
    _inherit = ['mail.thread', 'mail.activity.mixin', 'jt.email.ai.mixin']
    _order = 'due_date asc, priority desc, id desc'

    name = fields.Char('Titre', required=True, tracking=True)
    description = fields.Html('Description')
    client_id = fields.Many2one(
        'jt.client', string='Client', ondelete='set null', index=True, tracking=True,
    )
    police_id = fields.Many2one(
        'jt.police', string='Police', ondelete='set null', index=True,
        domain="[('client_id', '=', client_id)]",
    )
    due_date = fields.Date('Échéance', tracking=True)
    priority = fields.Selection([
        ('0', 'Basse'),
        ('1', 'Moyenne'),
        ('2', 'Haute'),
        ('3', 'Urgente'),
    ], string='Priorité', default='0', tracking=True)
    state = fields.Selection([
        ('draft', 'Brouillon'),
        ('confirm', 'Confirmée'),
        ('done', 'Terminée'),
        ('cancel', 'Annulée'),
    ], string='État', default='draft', required=True, tracking=True)
    source = fields.Selection([
        ('email', 'Courriel'),
        ('manual', 'Manuelle'),
        ('renewal', 'Renouvellement'),
        ('ai', 'IA'),
    ], string='Source', default='manual', required=True)
    message_id = fields.Many2one('mail.message', string='Message source', ondelete='set null')
    mailbox_id = fields.Many2one('doorway.crm.mailbox', string='Boîte mail', ondelete='set null')
    user_id = fields.Many2one(
        'res.users', string='Assigné à', default=lambda self: self.env.user, tracking=True,
    )

    def action_confirm(self):
        self.write({'state': 'confirm'})

    def action_done(self):
        self.write({'state': 'done'})

    def action_cancel(self):
        self.write({'state': 'cancel'})

    def action_draft(self):
        self.write({'state': 'draft'})

    @api.onchange('client_id')
    def _onchange_client_id(self):
        if self.police_id and self.police_id.client_id != self.client_id:
            self.police_id = False
