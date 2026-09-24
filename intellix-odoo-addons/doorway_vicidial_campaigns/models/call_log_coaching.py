import json
import logging
import os
import requests
from odoo import models, api

_logger = logging.getLogger(__name__)

ANTHROPIC_API_KEY = os.environ.get('ANTHROPIC_API_KEY', '')

SYSTEM_IA = """Tu es un expert en qualification de leads pour call center IA.
Analyse cette conversation et retourne UNIQUEMENT un JSON valide sans markdown:
{
  "score_global": <0-100>,
  "dimensions": {
    "accroche": {"score": <0-10>, "commentaire": "<texte>"},
    "qualification": {"score": <0-20>, "commentaire": "<texte>"},
    "gestion_objections": {"score": <0-20>, "commentaire": "<texte>"},
    "closing": {"score": <0-20>, "commentaire": "<texte>"},
    "fluidite": {"score": <0-30>, "commentaire": "<texte>"}
  },
  "points_forts": ["<point1>", "<point2>"],
  "axes_amelioration": ["<axe1>", "<axe2>"],
  "recommandation": "<texte court>"
}"""

SYSTEM_HUMAN = """Tu es un coach expert pour agents de call center humains.
Analyse cette conversation et retourne UNIQUEMENT un JSON valide sans markdown:
{
  "score_global": <0-100>,
  "dimensions": {
    "accroche": {"score": <0-10>, "commentaire": "<texte>"},
    "qualification": {"score": <0-20>, "commentaire": "<texte>"},
    "gestion_objections": {"score": <0-20>, "commentaire": "<texte>"},
    "closing": {"score": <0-20>, "commentaire": "<texte>"},
    "ton_empathie": {"score": <0-30>, "commentaire": "<texte>"}
  },
  "points_forts": ["<point1>", "<point2>"],
  "axes_amelioration": ["<axe1>", "<axe2>"],
  "suggestion_superviseur": "<texte>",
  "recommandation_formation": "<texte>"
}"""


class DoorwayCallLog(models.Model):
    _inherit = 'doorway.call.log'

    @api.model
    def _cron_score_pending_calls(self):
        """Cron toutes les 5 min — score les call logs pending avec Claude"""
        if not ANTHROPIC_API_KEY:
            _logger.warning('ANTHROPIC_API_KEY manquant — scoring désactivé')
            return

        pending = self.search([
            ('coaching_status', '=', 'pending'),
            ('transcript', '!=', False),
            ('transcript', '!=', ''),
        ], limit=20, order='id asc')

        _logger.info('Coaching cron: %d appels à scorer', len(pending))

        for call in pending:
            try:
                system = SYSTEM_IA if call.is_ia_agent else SYSTEM_HUMAN
                resp = requests.post(
                    'https://api.anthropic.com/v1/messages',
                    headers={
                        'x-api-key': ANTHROPIC_API_KEY,
                        'anthropic-version': '2023-06-01',
                        'content-type': 'application/json',
                    },
                    json={
                        'model': 'claude-sonnet-4-6',
                        'max_tokens': 1000,
                        'system': system,
                        'messages': [{'role': 'user', 'content': f'Transcript:\n{call.transcript[:3000]}'}],
                    },
                    timeout=30,
                )
                if resp.status_code == 200:
                    content = resp.json()['content'][0]['text'].strip()
                    content = content.replace('```json', '').replace('```', '').strip()
                    scoring = json.loads(content)
                    call.sudo().write({
                        'coaching_score': scoring.get('score_global', 0),
                        'coaching_json': json.dumps(scoring),
                        'coaching_status': 'done',
                    })
                    _logger.info('Call %s scoré: %s/100', call.id, scoring.get('score_global'))
                else:
                    call.sudo().write({'coaching_status': 'error'})
            except Exception as e:
                _logger.error('Scoring error call %s: %s', call.id, e)
                call.sudo().write({'coaching_status': 'error'})
            self.env.cr.commit()
