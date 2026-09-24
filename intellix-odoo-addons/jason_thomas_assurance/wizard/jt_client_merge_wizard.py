from odoo import _, api, fields, models
from odoo.exceptions import UserError


class JTClientMergeWizard(models.TransientModel):
    _name = 'jt.client.merge.wizard'
    _description = 'Fusionner des clients JT'

    destination_id = fields.Many2one(
        'jt.client', string='Fiche à conserver', required=True,
    )
    source_ids = fields.Many2many(
        'jt.client', 'jt_client_merge_wizard_src_rel', 'wizard_id', 'client_id',
        string='Fiches à fusionner',
    )
    police_count = fields.Integer('Polices à réassigner', compute='_compute_counts')
    tache_count = fields.Integer('Tâches à réassigner', compute='_compute_counts')

    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        active_ids = self.env.context.get('active_ids') or []
        if not active_ids:
            return res
        clients = self.env['jt.client'].browse(active_ids).exists()
        if len(clients) < 2:
            return res
        destination = max(clients, key=lambda c: (len(c.full_name or ''), c.id))
        res['destination_id'] = destination.id
        res['source_ids'] = [(6, 0, (clients - destination).ids)]
        return res

    @api.depends('source_ids')
    def _compute_counts(self):
        for wizard in self:
            wizard.police_count = sum(len(c.police_ids) for c in wizard.source_ids)
            wizard.tache_count = sum(len(c.tache_ids) for c in wizard.source_ids)

    @api.onchange('destination_id')
    def _onchange_destination_id(self):
        active_ids = self.env.context.get('active_ids') or []
        if not active_ids or not self.destination_id:
            return
        others = [cid for cid in active_ids if cid != self.destination_id.id]
        self.source_ids = [(6, 0, others)]

    def action_merge(self):
        self.ensure_one()
        if not self.source_ids:
            raise UserError(_('Sélectionnez au moins une fiche source à fusionner.'))
        if self.destination_id in self.source_ids:
            raise UserError(_('La fiche destination ne peut pas être dans les sources.'))
        dest = self.destination_id.merge_clients(self.source_ids)
        return {
            'type': 'ir.actions.act_window',
            'name': _('Client fusionné'),
            'res_model': 'jt.client',
            'view_mode': 'form',
            'res_id': dest.id,
            'target': 'current',
        }
