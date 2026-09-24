import secrets

from odoo import api, fields, models


class JTPortalAccess(models.Model):
    _name = 'jt.portal.access'
    _description = 'Accès portail client JT'
    _rec_name = 'email'

    client_id = fields.Many2one('jt.client', string='Client', required=True, ondelete='cascade', index=True)
    token = fields.Char('Token accès', index=True, copy=False)
    email = fields.Char('Email', required=True)
    is_active = fields.Boolean('Actif', default=True)
    last_login = fields.Datetime('Dernière connexion')
    created_at = fields.Datetime('Créé le', default=fields.Datetime.now)
    invitation_sent = fields.Boolean('Invitation envoyée', default=False)
    portal_url = fields.Char('URL portail', compute='_compute_portal_url')

    @api.depends('token')
    def _compute_portal_url(self):
        icp = self.env['ir.config_parameter'].sudo()
        base = icp.get_param('jt.portal.base_url') or icp.get_param('web.base.url', '')
        base = base.rstrip('/')
        for record in self:
            record.portal_url = f'{base}/portail/{record.token}' if record.token else ''

    def generate_token(self):
        for record in self:
            record.token = secrets.token_urlsafe(32)

    def send_invitation(self):
        template = self.env.ref('jt_client_portal.mail_template_invitation', raise_if_not_found=False)
        for record in self:
            if not record.token:
                record.generate_token()
            if template:
                template.send_mail(record.id, force_send=True)
            record.invitation_sent = True

    def action_send_all_invitations(self):
        pending = self.search([
            ('invitation_sent', '=', False),
            ('email', '!=', False),
            ('is_active', '=', True),
        ])
        pending.send_invitation()

    @api.model
    def action_create_all_access(self):
        created = self.create_access_for_all_clients()
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': 'Accès portail',
                'message': f'{created} nouvel(s) accès créé(s).',
                'type': 'success',
                'sticky': False,
            },
        }

    @api.model
    def create_access_for_client(self, client, email=None):
        email = (email or client.email or '').strip()
        if not email:
            return self.env['jt.portal.access']
        existing = self.search([('client_id', '=', client.id), ('email', '=', email)], limit=1)
        if existing:
            if not existing.token:
                existing.generate_token()
            return existing
        access = self.create({'client_id': client.id, 'email': email})
        access.generate_token()
        return access

    @api.model
    def create_access_for_all_clients(self):
        created = 0
        for client in self.env['jt.client'].search([('email', '!=', False)]):
            before = self.search_count([('client_id', '=', client.id)])
            self.create_access_for_client(client)
            after = self.search_count([('client_id', '=', client.id)])
            if after > before:
                created += 1
        return created
