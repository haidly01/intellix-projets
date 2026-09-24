from datetime import timedelta

from odoo import _, api, fields, models
from odoo.exceptions import UserError

from ..models.jt_email_ai import MAX_TASKS, SYSTEM_PROMPT


class JTEmailTaskWizard(models.TransientModel):
    _name = 'jt.email.task.wizard'
    _inherit = 'jt.email.ai.mixin'
    _description = 'Génération de tâches JT par IA'

    client_id = fields.Many2one('jt.client', string='Client')
    mailbox_id = fields.Many2one('doorway.crm.mailbox', string='Boîte mail')
    source_text = fields.Text(
        string='Courriel / note',
        help="Collez ici le courriel ou la note à transformer en tâches.",
    )
    extra_instructions = fields.Char(string='Instructions supplémentaires (optionnel)')
    state = fields.Selection(
        selection=[('input', 'Saisie'), ('review', 'Révision')],
        default='input',
        string='Étape',
    )
    line_ids = fields.One2many(
        'jt.email.task.wizard.line', 'wizard_id', string='Tâches proposées',
    )

    def action_generate(self):
        self.ensure_one()
        if not self.source_text or not self.source_text.strip():
            raise UserError(_('Veuillez saisir un texte à transformer en tâches.'))

        assignee = self._jt_default_assignee(self.mailbox_id)
        user_content = _(
            "Conseiller : %(advisor)s\n"
            "Date du jour : %(today)s\n"
            "Client : %(client)s\n"
        ) % {
            'advisor': assignee.name,
            'today': fields.Date.context_today(self).isoformat(),
            'client': self.client_id.full_name if self.client_id else _('(inconnu)'),
        }
        if self.extra_instructions:
            user_content += _('Consignes : %s\n') % self.extra_instructions
        user_content += _('\nTexte à transformer en tâches :\n%s') % self.source_text

        answer = self.env['renovation.ai.service']._call(
            [{'role': 'user', 'content': user_content}],
            system=self.env['renovation.ai.service']._get_prompt(
                'task_generation', SYSTEM_PROMPT,
            ),
            purpose=_('Génération de tâches JT — révision manuelle'),
        )

        try:
            items = self._extract_json(answer)
        except (ValueError, TypeError) as error:
            raise UserError(
                _(
                    "La réponse de l'IA n'a pas pu être interprétée. "
                    "Réessayez ou reformulez le texte.\n\nRéponse brute :\n%s"
                )
                % (answer or '')[:1000]
            ) from error
        if not isinstance(items, list) or not items:
            raise UserError(_("L'IA n'a proposé aucune tâche. Reformulez le texte."))

        lines = []
        for item in items[:MAX_TASKS]:
            if not isinstance(item, dict):
                continue
            title = (item.get('titre') or item.get('title') or '').strip()
            if not title:
                continue
            try:
                days = int(item.get('jours') or item.get('days') or 0)
            except (TypeError, ValueError):
                days = 0
            deadline = False
            if days and days > 0:
                deadline = fields.Date.context_today(self) + timedelta(days=days)
            priority = str(item.get('priorite') or item.get('priority') or '0')
            if priority not in ('0', '1', '2', '3'):
                priority = '0'
            lines.append((0, 0, {
                'selected': True,
                'name': title[:250],
                'description': (item.get('description') or '').strip(),
                'due_date': deadline,
                'priority': priority,
                'user_id': assignee.id,
            }))

        if not lines:
            raise UserError(_("L'IA n'a proposé aucune tâche exploitable."))

        self.line_ids = [(5, 0, 0)] + lines
        self.state = 'review'
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'jt.email.task.wizard',
            'res_id': self.id,
            'view_mode': 'form',
            'target': 'new',
            'name': _('Tâches proposées par l\'IA'),
        }

    def action_create_tasks(self):
        self.ensure_one()
        lines = self.line_ids.filtered('selected')
        if not lines:
            raise UserError(_('Sélectionnez au moins une tâche à créer.'))
        Tache = self.env['jt.tache']
        created = Tache
        for line in lines:
            vals = {
                'name': line.name,
                'priority': line.priority,
                'state': 'confirm',
                'source': 'ai',
                'user_id': line.user_id.id or self._jt_default_assignee(self.mailbox_id).id,
            }
            if line.description:
                vals['description'] = '<p>%s</p>' % line.description.replace('\n', '<br/>')
            if line.due_date:
                vals['due_date'] = line.due_date
            if self.client_id:
                vals['client_id'] = self.client_id.id
            if self.mailbox_id:
                vals['mailbox_id'] = self.mailbox_id.id
            created |= Tache.create(vals)
        return {
            'type': 'ir.actions.act_window',
            'name': _('Tâches créées'),
            'res_model': 'jt.tache',
            'domain': [('id', 'in', created.ids)],
            'view_mode': 'list,form,kanban',
        }


class JTEmailTaskWizardLine(models.TransientModel):
    _name = 'jt.email.task.wizard.line'
    _description = 'Tâche JT proposée par l\'IA'

    wizard_id = fields.Many2one(
        'jt.email.task.wizard', required=True, ondelete='cascade',
    )
    selected = fields.Boolean(string='Créer', default=True)
    name = fields.Char(string='Titre', required=True)
    description = fields.Text(string='Description')
    due_date = fields.Date(string='Échéance')
    priority = fields.Selection(
        selection=[
            ('0', 'Basse'),
            ('1', 'Moyenne'),
            ('2', 'Haute'),
            ('3', 'Urgente'),
        ],
        default='0',
        string='Priorité',
    )
    user_id = fields.Many2one('res.users', string='Assigné')
