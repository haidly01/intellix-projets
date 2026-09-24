from datetime import date

from odoo import api, fields, models
from odoo.exceptions import UserError


class JTClient(models.Model):
    _name = 'jt.client'
    _description = 'Client Jason Thomas Assurance'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'last_name, first_name'

    partner_id = fields.Many2one('res.partner', string='Contact Odoo', ondelete='set null')
    source = fields.Selection([
        ('assomption_vie', 'Assomption Vie'),
        ('ago', 'Assure & Go'),
        ('inalco', 'Inalco / iA'),
        ('ago_inalco', 'AGO + Inalco'),
    ], string='Source', required=True, tracking=True)
    client_id_source = fields.Char('ID source (UUID)', index=True)
    first_name = fields.Char('Prénom')
    last_name = fields.Char('Nom')
    full_name = fields.Char('Nom complet', compute='_compute_full_name', store=True, index=True)
    birth_date = fields.Date('Date de naissance')
    age = fields.Integer('Âge', compute='_compute_age')
    gender = fields.Selection([('homme', 'Homme'), ('femme', 'Femme')], string='Genre')
    cell_phone = fields.Char('Cellulaire')
    home_phone = fields.Char('Domicile')
    office_phone = fields.Char('Bureau')
    postal_code = fields.Char('Code postal')
    spouse_first_name = fields.Char('Prénom conjoint(e)')
    spouse_last_name = fields.Char('Nom conjoint(e)')
    email = fields.Char('Courriel')
    police_ids = fields.One2many('jt.police', 'client_id', string='Polices')
    police_count = fields.Integer('Nb polices', compute='_compute_police_count')
    tache_ids = fields.One2many('jt.tache', 'client_id', string='Tâches')
    tache_count = fields.Integer('Nb tâches', compute='_compute_tache_count')
    anniversary_this_week = fields.Boolean(
        string='Anniversaire cette semaine',
        compute='_compute_anniversary',
        store=True,
        index=True,
    )
    premium_total = fields.Float('Primes totales', compute='_compute_premium_total')

    @api.depends('first_name', 'last_name')
    def _compute_full_name(self):
        for record in self:
            record.full_name = f'{record.first_name or ""} {record.last_name or ""}'.strip()

    @api.depends('birth_date')
    def _compute_age(self):
        today = date.today()
        for record in self:
            if record.birth_date:
                record.age = today.year - record.birth_date.year - (
                    (today.month, today.day) < (record.birth_date.month, record.birth_date.day)
                )
            else:
                record.age = 0

    @api.depends('police_ids')
    def _compute_police_count(self):
        for record in self:
            record.police_count = len(record.police_ids)

    @api.depends('tache_ids')
    def _compute_tache_count(self):
        for record in self:
            record.tache_count = len(record.tache_ids)

    @api.depends('police_ids.premium', 'police_ids.policy_status')
    def _compute_premium_total(self):
        for record in self:
            record.premium_total = sum(
                p.premium or 0.0
                for p in record.police_ids
                if p.policy_status == 'en_force'
            )

    @api.depends('birth_date')
    def _compute_anniversary(self):
        today = date.today()
        for record in self:
            if record.birth_date:
                try:
                    bday_this_year = record.birth_date.replace(year=today.year)
                except ValueError:
                    bday_this_year = record.birth_date.replace(year=today.year, day=28)
                delta = (bday_this_year - today).days
                record.anniversary_this_week = 0 <= delta <= 7
            else:
                record.anniversary_this_week = False

    def action_view_polices(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': 'Polices',
            'res_model': 'jt.police',
            'view_mode': 'list,form',
            'domain': [('client_id', '=', self.id)],
            'context': {'default_client_id': self.id},
        }

    def action_view_taches(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': 'Tâches',
            'res_model': 'jt.tache',
            'view_mode': 'list,form,kanban',
            'domain': [('client_id', '=', self.id)],
            'context': {'default_client_id': self.id},
        }

    def _merge_pick_text(self, dest_val, src_val):
        dest_val = (dest_val or '').strip()
        src_val = (src_val or '').strip()
        if not dest_val:
            return src_val
        if not src_val:
            return dest_val
        return src_val if len(src_val) > len(dest_val) else dest_val

    def _merge_source_field(self, dest, sources):
        values = {dest.source} | set(sources.mapped('source'))
        if 'ago_inalco' in values:
            return 'ago_inalco'
        if 'ago' in values and 'inalco' in values:
            return 'ago_inalco'
        return dest.source

    def _police_dedup_key(self, police):
        return (
            (police.policy_number or '').strip(),
            (police.coverage_number or '').strip(),
        )

    def merge_clients(self, sources):
        """Fusionne les fiches sources dans self (destination)."""
        self.ensure_one()
        sources = sources - self
        if not sources:
            return self

        merge_fields = [
            'first_name', 'last_name', 'birth_date', 'gender',
            'cell_phone', 'home_phone', 'office_phone', 'email',
            'postal_code', 'spouse_first_name', 'spouse_last_name',
            'client_id_source',
        ]
        vals = {}
        for field in merge_fields:
            current = getattr(self, field)
            for src in sources:
                current = self._merge_pick_text(current, getattr(src, field))
            if field in ('birth_date', 'gender') and not current:
                for src in sources:
                    src_val = getattr(src, field)
                    if src_val:
                        current = src_val
                        break
            if current and current != getattr(self, field):
                vals[field] = current

        merged_source = self._merge_source_field(self, sources)
        if merged_source != self.source:
            vals['source'] = merged_source

        if vals:
            self.write(vals)

        dest_keys = {self._police_dedup_key(p) for p in self.police_ids}
        Police = self.env['jt.police']
        for src in sources:
            for police in src.police_ids:
                key = self._police_dedup_key(police)
                if key in dest_keys and key[0]:
                    police.unlink()
                else:
                    police.write({'client_id': self.id})
                    dest_keys.add(key)

            src.tache_ids.write({'client_id': self.id})

            if 'jt.portal.access' in self.env:
                Portal = self.env['jt.portal.access']
                for access in Portal.search([('client_id', '=', src.id)]):
                    existing = Portal.search([
                        ('client_id', '=', self.id),
                        ('email', '=', access.email),
                    ], limit=1)
                    if existing:
                        access.unlink()
                    else:
                        access.write({'client_id': self.id})

            src.message_ids.write({'res_id': self.id})
            src.activity_ids.write({'res_id': self.id})

        merged_names = ', '.join(sources.mapped('full_name'))
        self.message_post(
            body=(
                f'Fusion de {len(sources)} fiche(s) : {merged_names}. '
                f'Polices et tâches réassignées.'
            ),
            subtype_xmlid='mail.mt_note',
        )
        sources.unlink()
        return self

    def action_open_merge_wizard(self):
        if len(self) < 2:
            raise UserError('Sélectionnez au moins 2 clients à fusionner.')
        return {
            'type': 'ir.actions.act_window',
            'name': 'Fusionner les clients',
            'res_model': 'jt.client.merge.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {'active_ids': self.ids},
        }

    def _ensure_portal_access(self):
        if 'jt.portal.access' not in self.env:
            return
        Portal = self.env['jt.portal.access']
        for client in self:
            if client.email:
                Portal.create_access_for_client(client)

    @api.model_create_multi
    def create(self, vals_list):
        clients = super().create(vals_list)
        clients._ensure_portal_access()
        return clients

    def write(self, vals):
        res = super().write(vals)
        if 'email' in vals:
            self._ensure_portal_access()
        return res
