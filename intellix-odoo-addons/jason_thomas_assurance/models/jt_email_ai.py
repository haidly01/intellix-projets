import json
import logging
import re
from datetime import timedelta

from odoo import _, api, fields, models

_logger = logging.getLogger(__name__)

MAX_TASKS = 5

SYSTEM_PROMPT = (
    "Tu es l'assistant d'un conseiller en assurance vie (Jason Thomas, "
    "Nouveau-Brunswick, Canada). À partir d'un e-mail ou d'une note client, "
    "tu produis une liste de tâches de suivi concrètes et actionnables "
    "(appeler le client, réviser un renouvellement de police, envoyer une "
    "soumission, planifier un rendez-vous, vérifier des documents, "
    "relancer pour signature, etc.). "
    "Réponds UNIQUEMENT avec un tableau JSON valide (aucun texte autour, pas de "
    "balises markdown). Chaque élément est un objet : "
    '{"titre": str, "description": str (1-3 phrases, étapes clés), '
    '"jours": int (échéance suggérée en nombre de jours à partir d\'aujourd\'hui, '
    "0 si non pertinent), "
    '"priorite": "0"|"1"|"2"|"3" (0=basse, 1=moyenne, 2=haute, 3=urgente), '
    '"assigne": str (nom EXACT du conseiller fourni, ou "" si incertain)}. '
    "Maximum %s tâches. Écris en français."
) % MAX_TASKS


class JTEmailAiMixin(models.AbstractModel):
    _name = 'jt.email.ai.mixin'
    _description = 'Génération de tâches JT par IA'

    @staticmethod
    def _extract_json(raw):
        text = (raw or '').strip()
        if text.startswith('```'):
            text = re.sub(r'^```[a-zA-Z]*', '', text).strip()
            if text.endswith('```'):
                text = text[:-3].strip()
        match = re.search(r'(\[.*\]|\{.*\})', text, re.DOTALL)
        if match:
            text = match.group(1)
        data = json.loads(text)
        if isinstance(data, dict):
            for key in ('taches', 'tasks', 'items', 'resultats'):
                if isinstance(data.get(key), list):
                    return data[key]
            return [data]
        return data

    @api.model
    def _jt_default_assignee(self, mailbox=None):
        if mailbox and mailbox.user_id:
            return mailbox.user_id
        jason = self.env['res.users'].search(
            [('login', '=', 'jason@jasonthomasassurance.ca')], limit=1,
        )
        return jason or self.env.user

    @api.model
    def _jt_generate_tasks_from_text(
        self,
        source_text,
        source_label=None,
        client=None,
        message=None,
        mailbox=None,
        police=None,
        source='ai',
    ):
        """Génère et crée des jt.tache à partir d'un texte via l'IA."""
        Tache = self.env['jt.tache']
        if not source_text or not source_text.strip():
            return Tache
        if not self.env['renovation.ai.service']._available():
            return Tache

        assignee = self._jt_default_assignee(mailbox)
        assignee_name = assignee.name or 'Jason Thomas'
        user_content = _(
            "Conseiller : %(advisor)s\n"
            "Date du jour : %(today)s\n"
            "Client : %(client)s\n\n"
            "Source (%(label)s) à transformer en tâches :\n%(text)s"
        ) % {
            'advisor': assignee_name,
            'today': fields.Date.context_today(self).isoformat(),
            'client': client.full_name if client else _('(inconnu)'),
            'label': source_label or _('texte'),
            'text': source_text,
        }
        answer = self.env['renovation.ai.service']._call(
            [{'role': 'user', 'content': user_content}],
            system=self.env['renovation.ai.service']._get_prompt(
                'task_generation', SYSTEM_PROMPT,
            ),
            purpose=_('Génération de tâches JT — %s') % (client.full_name if client else assignee_name),
        )

        try:
            items = self._extract_json(answer)
        except Exception:  # noqa: BLE001
            _logger.warning('Parsing IA (courriel JT) échoué')
            return Tache
        if not isinstance(items, list):
            return Tache

        today = fields.Date.context_today(self)
        created = Tache
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
            priority = str(item.get('priorite') or item.get('priority') or '0')
            if priority not in ('0', '1', '2', '3'):
                priority = '0'
            description = (item.get('description') or '').strip()
            vals = {
                'name': title[:250],
                'priority': priority,
                'state': 'confirm',
                'source': source,
                'user_id': assignee.id,
            }
            if description:
                vals['description'] = '<p>%s</p>' % description.replace('\n', '<br/>')
            if days and days > 0:
                vals['due_date'] = today + timedelta(days=days)
            if client:
                vals['client_id'] = client.id
            if police:
                vals['police_id'] = police.id
            if message:
                vals['message_id'] = message.id
            if mailbox:
                vals['mailbox_id'] = mailbox.id
            created |= Tache.create(vals)
        return created
