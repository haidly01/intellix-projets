import logging
from email.utils import parseaddr

from odoo import _, api, fields, models
from odoo.tools import html2plaintext

_logger = logging.getLogger(__name__)


class DoorwayCrmMailboxJT(models.Model):
    _inherit = 'doorway.crm.mailbox'

    jt_auto_tasks = fields.Boolean(
        string='Créer des tâches JT (IA)',
        default=True,
        help="Analyse automatiquement les courriels entrants et crée des tâches JT via l'IA.",
    )
    jt_link_clients = fields.Boolean(
        string='Lier les courriels aux clients JT',
        default=True,
        help="Associe l'expéditeur à un client JT et publie une note sur sa fiche.",
    )

    def _jt_is_jt_mailbox(self):
        self.ensure_one()
        company = self.env.ref('jason_thomas_assurance.company_jt', raise_if_not_found=False)
        if not company:
            return False
        return self.user_id.company_id.id == company.id

    @api.model_create_multi
    def create(self, vals_list):
        company = self.env.ref('jason_thomas_assurance.company_jt', raise_if_not_found=False)
        if company:
            for vals in vals_list:
                user_id = vals.get('user_id') or self.env.user.id
                user = self.env['res.users'].browse(user_id)
                if user.company_id.id == company.id:
                    vals.setdefault('create_crm_leads', False)
                    vals.setdefault('jt_auto_tasks', True)
                    vals.setdefault('jt_link_clients', True)
        return super().create(vals_list)

    def _doorway_maybe_create_lead(self, msg_dict):
        if any(mailbox._jt_is_jt_mailbox() for mailbox in self):
            return
        return super()._doorway_maybe_create_lead(msg_dict)

    def _jt_is_inbound(self, msg_dict):
        self.ensure_one()
        email_from = (msg_dict.get('email_from') or '').strip()
        from_addr = self._doorway_extract_email(email_from)
        mailbox_addr = self._doorway_extract_email(self.email)
        return bool(from_addr) and from_addr != mailbox_addr

    def _jt_find_client_from_email(self, msg_dict):
        Client = self.env['jt.client']
        email_from = parseaddr(msg_dict.get('email_from') or '')[1]
        if not email_from:
            return Client
        client = Client.search([('email', '=ilike', email_from)], limit=1)
        if not client and email_from:
            client = Client.search([('email', 'ilike', email_from.split('@')[0])], limit=1)
        return client

    def _jt_latest_email_message(self, msg_dict):
        subject = (msg_dict.get('subject') or '').strip()
        domain = [
            ('model', '=', 'doorway.crm.mailbox'),
            ('res_id', 'in', self.ids),
            ('message_type', '=', 'email'),
        ]
        if subject:
            domain.append(('subject', '=', subject))
        return self.env['mail.message'].search(domain, order='id desc', limit=1)

    def _jt_process_inbound_email(self, msg_dict):
        self.ensure_one()
        if not self._jt_is_jt_mailbox():
            return
        if not self._jt_is_inbound(msg_dict):
            return

        client = self.env['jt.client']
        if self.jt_link_clients:
            client = self._jt_find_client_from_email(msg_dict)
            if client:
                subject = msg_dict.get('subject') or _('(sans objet)')
                body_plain = html2plaintext(msg_dict.get('body') or '')[:500].strip()
                client.message_post(
                    body=_(
                        '<p><strong>Courriel reçu</strong> — %(subject)s</p>'
                        '<p>%(snippet)s</p>'
                    ) % {
                        'subject': subject,
                        'snippet': body_plain or _('(sans contenu)'),
                    },
                    subject=subject,
                    message_type='comment',
                    subtype_xmlid='mail.mt_note',
                )

        if not self.jt_auto_tasks:
            return
        try:
            if not self.env['renovation.ai.service']._available():
                return
            subject = msg_dict.get('subject') or ''
            body = html2plaintext(msg_dict.get('body') or '')
            source_text = ('%s\n\n%s' % (subject, body)).strip()
            if not source_text:
                return
            message = self._jt_latest_email_message(msg_dict)
            police = False
            if client:
                police = self.env['jt.police'].search([
                    ('client_id', '=', client.id),
                    ('policy_status', '=', 'en_force'),
                ], order='term_date asc', limit=1)
            created = self.env['jt.tache']._jt_generate_tasks_from_text(
                source_text,
                source_label=_('courriel entrant'),
                client=client or False,
                message=message or False,
                mailbox=self,
                police=police or False,
                source='email',
            )
            if created:
                self.message_post(
                    body=_(
                        '🤖 %(count)s tâche(s) JT générée(s) automatiquement '
                        'à partir de ce courriel.'
                    ) % {'count': len(created)},
                    subtype_xmlid='mail.mt_note',
                )
        except Exception as error:  # noqa: BLE001
            _logger.warning('Courriel → tâches JT IA échoué : %s', error)
            self.message_post(
                body=_(
                    '⚠️ La génération automatique de tâches JT par l\'IA a échoué : %s'
                ) % error,
                subtype_xmlid='mail.mt_note',
            )

    def message_update(self, msg_dict, update_vals=None):
        res = super().message_update(msg_dict, update_vals=update_vals)
        for mailbox in self:
            mailbox._jt_process_inbound_email(msg_dict)
        return res
