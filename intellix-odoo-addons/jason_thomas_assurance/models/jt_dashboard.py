from datetime import date, timedelta

from odoo import api, fields, models
from odoo.tools import html2plaintext

JOURS_FR = [
    'Lundi', 'Mardi', 'Mercredi', 'Jeudi', 'Vendredi', 'Samedi', 'Dimanche',
]
MOIS_FR = [
    'janvier', 'février', 'mars', 'avril', 'mai', 'juin',
    'juillet', 'août', 'septembre', 'octobre', 'novembre', 'décembre',
]
MOIS_FR_SHORT = [
    'janv.', 'févr.', 'mars', 'avr.', 'mai', 'juin',
    'juil.', 'août', 'sept.', 'oct.', 'nov.', 'déc.',
]


def _fmt_num(value) -> str:
    try:
        n = int(value)
    except (TypeError, ValueError):
        return str(value)
    return f'{n:,}'.replace(',', '\u202f')


def _fmt_money(value) -> str:
    try:
        n = float(value)
    except (TypeError, ValueError):
        return str(value)
    return f'{_fmt_num(int(round(n)))} $'


def _fmt_birth(bday: date) -> str:
    return f'{bday.day} {MOIS_FR_SHORT[bday.month - 1]} {bday.year}'


class JTDashboard(models.TransientModel):
    _name = 'jt.dashboard'
    _description = 'Dashboard Jason Thomas Assurance'

    dashboard_html = fields.Html(compute='_compute_dashboard_html', sanitize=False)

    @api.depends_context('uid')
    def _compute_dashboard_html(self):
        data = self.get_dashboard_data()
        for record in self:
            record.dashboard_html = self.env['ir.qweb']._render(
                'jason_thomas_assurance.jt_dashboard',
                data,
            )

    @api.model
    def _action_id(self, xmlid: str):
        action = self.env.ref(xmlid, raise_if_not_found=False)
        return action.id if action else False

    @api.model
    def _action_href(self, xmlid: str) -> str:
        action_id = self._action_id(xmlid)
        if not action_id:
            return '#'
        return f'/odoo/action-{action_id}'

    @api.model
    def _shell_context(self, active_action_id=None):
        Client = self.env['jt.client']
        Police = self.env['jt.police']
        Portal = self.env['jt.portal.access']
        today = date.today()
        nb_clients = Client.search_count([])
        nb_anniv = Client.search_count([
            ('anniversary_this_week', '=', True),
            ('birth_date', '!=', False),
        ])
        nb_renew = Police.search_count([
            ('term_date', '>=', today),
            ('term_date', '<=', today + timedelta(days=30)),
            ('policy_status', '=', 'en_force'),
        ])
        portal_action = self.env.ref('jt_client_portal.action_jt_portal_access', raise_if_not_found=False)
        calendar_action = self.env.ref('calendar.action_calendar_event', raise_if_not_found=False)
        messaging_action = self.env.ref('doorway_messaging.action_messaging_hub', raise_if_not_found=False)
        agents_action = self.env.ref('doorway_agents_dashboard.action_agents_dashboard', raise_if_not_found=False)
        courriel_action = self.env.ref('doorway_crm.action_doorway_crm_webmail', raise_if_not_found=False)
        taches_action = self.env.ref('jason_thomas_assurance.action_jt_tache', raise_if_not_found=False)
        return {
            'user_name': self.env.user.name,
            'user_role': 'Conseiller principal',
            'nb_clients_fmt': _fmt_num(nb_clients),
            'nb_anniversaires_fmt': _fmt_num(nb_anniv),
            'nb_renouvellements_30j': nb_renew,
            'nb_renouvellements_fmt': _fmt_num(nb_renew),
            'active_action_id': active_action_id,
            'action_dashboard_id': self._action_id('jason_thomas_assurance.action_jt_dashboard'),
            'action_clients_id': self._action_id('jason_thomas_assurance.action_jt_client'),
            'action_polices_id': self._action_id('jason_thomas_assurance.action_jt_police'),
            'action_anniversaires_id': self._action_id('jason_thomas_assurance.action_jt_client_anniversaires'),
            'action_renouvellements_id': self._action_id('jason_thomas_assurance.action_jt_police_renewals'),
            'action_portail_id': portal_action.id if portal_action else False,
            'action_calendar_id': calendar_action.id if calendar_action else False,
            'action_messages_id': messaging_action.id if messaging_action else False,
            'action_agents_id': agents_action.id if agents_action else False,
            'action_courriel_id': courriel_action.id if courriel_action else False,
            'action_taches_id': taches_action.id if taches_action else False,
            'nav_dashboard': self._action_href('jason_thomas_assurance.action_jt_dashboard'),
            'nav_clients': self._action_href('jason_thomas_assurance.action_jt_client'),
            'nav_polices': self._action_href('jason_thomas_assurance.action_jt_police'),
            'nav_anniversaires': self._action_href('jason_thomas_assurance.action_jt_client_anniversaires'),
            'nav_renouvellements': self._action_href('jason_thomas_assurance.action_jt_police_renewals'),
            'nav_portail': self._action_href('jt_client_portal.action_jt_portal_access') if portal_action else False,
            'nav_calendar': self._action_href('calendar.action_calendar_event') if calendar_action else False,
            'nav_messages': self._action_href('doorway_messaging.action_messaging_hub') if messaging_action else False,
            'nav_agents': self._action_href('doorway_agents_dashboard.action_agents_dashboard') if agents_action else False,
            'nav_courriel': self._action_href('doorway_crm.action_doorway_crm_webmail') if courriel_action else False,
            'nav_taches': self._action_href('jason_thomas_assurance.action_jt_tache') if taches_action else False,
            'nav_new_client': self._action_href('jason_thomas_assurance.action_jt_client'),
            'logout_url': '/web/session/logout',
        }

    @api.model
    def get_sidebar_html(self, active_action_id=None):
        ctx = self._shell_context(active_action_id=active_action_id)
        return str(self.env['ir.qweb']._render('jason_thomas_assurance.jt_sidebar', ctx))

    @api.model
    def get_dashboard_data(self):
        today = date.today()
        month_start = today.replace(day=1)
        Client = self.env['jt.client']
        Police = self.env['jt.police']
        Portal = self.env['jt.portal.access']

        polices_force = Police.search([('policy_status', '=', 'en_force')])
        nb_clients = Client.search_count([])
        nb_polices_force = len(polices_force)
        total_primes = sum(polices_force.mapped('annual_premium')) or sum(
            polices_force.mapped('premium')
        )
        total_capital = sum(polices_force.mapped('face_amount'))

        new_clients_month = Client.search_count([
            ('create_date', '>=', fields.Datetime.to_datetime(month_start)),
        ])
        new_polices_month = Police.search_count([
            ('create_date', '>=', fields.Datetime.to_datetime(month_start)),
            ('policy_status', '=', 'en_force'),
        ])
        show_monthly_delta = new_clients_month < nb_clients * 0.5

        anniversaires = []
        avatar_palette = [
            ('#fdf3e0', '#c9952a'),
            ('#e8edf5', '#0d1e40'),
            ('#f0fdf4', '#16a34a'),
            ('#fef2f2', '#dc2626'),
            ('#ede9fe', '#6d28d9'),
        ]
        for client in Client.search([('birth_date', '!=', False)]):
            bday = client.birth_date
            try:
                bday_this_year = bday.replace(year=today.year)
            except ValueError:
                bday_this_year = bday.replace(year=today.year, day=28)
            delta = (bday_this_year - today).days
            if 0 <= delta <= 7:
                initials = (
                    f'{(client.first_name or " ")[0]}{(client.last_name or " ")[0]}'
                ).upper()
                bg, fg = avatar_palette[len(anniversaires) % len(avatar_palette)]
                anniversaires.append({
                    'full_name': client.full_name,
                    'birth_date_label': _fmt_birth(bday),
                    'age': client.age,
                    'cell_phone': client.cell_phone or '',
                    'initials': initials or '?',
                    'avatar_bg': bg,
                    'avatar_fg': fg,
                    'is_today': delta == 0,
                    'bday_day_label': JOURS_FR[bday_this_year.weekday()],
                    'client_url': f'/odoo/jt.client/{client.id}',
                })
        anniversaires.sort(key=lambda item: (not item['is_today'], item['full_name']))

        renouvellements = []
        polices_renew = Police.search([
            ('term_date', '>=', today),
            ('term_date', '<=', today + timedelta(days=30)),
            ('policy_status', '=', 'en_force'),
        ], limit=8)
        for police in polices_renew:
            days = (police.term_date - today).days
            renouvellements.append({
                'client_name': police.client_id.full_name,
                'policy_number': police.policy_number,
                'product': (police.product or '')[:28],
                'days_remaining': days,
                'urgency_class': (
                    'jt-urgent' if days <= 10
                    else 'jt-soon' if days <= 20
                    else 'jt-ok'
                ),
            })
        renouvellements.sort(key=lambda item: item['days_remaining'])

        nb_assomption = Police.search_count([('institution', '=', 'assomption_vie')])
        nb_ago = Police.search_count([
            ('institution', 'in', ['ago', 'inalco', 'ia_groupe']),
        ])
        nb_total = nb_assomption + nb_ago or 1
        nb_portail = Portal.search_count([('is_active', '=', True)])
        nb_anniv = Client.search_count([
            ('anniversary_this_week', '=', True),
            ('birth_date', '!=', False),
        ])

        shell = self._shell_context(
            active_action_id=self._action_id('jason_thomas_assurance.action_jt_dashboard'),
        )
        return {
            **shell,
            'nb_clients': nb_clients,
            'nb_clients_fmt': _fmt_num(nb_clients),
            'nb_polices_force': nb_polices_force,
            'nb_polices_force_fmt': _fmt_num(nb_polices_force),
            'total_primes': total_primes,
            'total_primes_fmt': _fmt_money(total_primes),
            'total_capital_label': f'{_fmt_money(total_capital)} capital assuré',
            'new_clients_month_fmt': _fmt_num(new_clients_month),
            'new_polices_month_fmt': _fmt_num(new_polices_month),
            'show_monthly_delta': show_monthly_delta,
            'nb_renouvellements_30j': len(renouvellements),
            'nb_renouvellements_fmt': _fmt_num(len(renouvellements)),
            'anniversaires': anniversaires[:12],
            'nb_anniversaires': nb_anniv,
            'nb_anniversaires_fmt': _fmt_num(nb_anniv),
            'renouvellements': renouvellements,
            'activites_recentes': self._get_recent_activities(),
            'nb_assomption': nb_assomption,
            'nb_assomption_fmt': _fmt_num(nb_assomption),
            'nb_ago_inalco': nb_ago,
            'nb_ago_inalco_fmt': _fmt_num(nb_ago),
            'nb_portail_actifs': nb_portail,
            'nb_portail_fmt': _fmt_num(nb_portail),
            'pct_assomption': round(nb_assomption / nb_total * 100),
            'pct_ago': round(nb_ago / nb_total * 100),
            'pct_portail': min(100, round(nb_portail / (nb_clients or 1) * 100)),
            'today_date': (
                f'{JOURS_FR[today.weekday()]} {today.day} '
                f'{MOIS_FR[today.month - 1]} {today.year}'
            ),
        }

    def _get_recent_activities(self):
        activities = []
        now = fields.Datetime.now()
        Police = self.env['jt.police']

        for police in Police.search([], order='create_date desc', limit=4):
            delta = (now - police.create_date).total_seconds()
            activities.append({
                'subject': police.client_id.full_name,
                'description': f'Police {police.policy_number} — {(police.product or "Assurance vie")[:35]}',
                'time_label': self._time_label(delta),
                'color': 'green',
                'sort_key': police.create_date,
            })

        Portal = self.env['jt.portal.access']
        for access in Portal.search([('last_login', '!=', False)], order='last_login desc', limit=3):
            delta = (now - access.last_login).total_seconds()
            activities.append({
                'subject': 'Portail client',
                'description': f'Consulté par {access.client_id.full_name}',
                'time_label': self._time_label(delta),
                'color': 'gold',
                'sort_key': access.last_login,
            })

        logs = self.env['mail.message'].search([
            ('model', 'in', ['jt.client', 'jt.police']),
            ('message_type', 'in', ['comment', 'email']),
            ('author_id.name', '!=', 'OdooBot'),
        ], order='date desc', limit=3)
        for log in logs:
            delta = (now - log.date).total_seconds()
            body_text = html2plaintext(log.body or '')[:80].strip()
            if not body_text or 'created' in body_text.lower():
                continue
            activities.append({
                'subject': log.author_id.name or 'Note',
                'description': body_text,
                'time_label': self._time_label(delta),
                'color': 'navy',
                'sort_key': log.date,
            })

        activities.sort(key=lambda item: item['sort_key'], reverse=True)
        for item in activities:
            item.pop('sort_key', None)
        return activities[:5]

    @staticmethod
    def _time_label(delta_seconds: float) -> str:
        if delta_seconds < 3600:
            return f'Il y a {max(1, int(delta_seconds / 60))} min'
        if delta_seconds < 86400:
            return f'Il y a {int(delta_seconds / 3600)} h'
        return 'Hier'

    @api.model
    def action_open_dashboard(self):
        dashboard = self.create({})
        view = self.env.ref('jason_thomas_assurance.view_jt_dashboard_form')
        return {
            'type': 'ir.actions.act_window',
            'name': 'Tableau de bord',
            'res_model': 'jt.dashboard',
            'view_mode': 'form',
            'views': [(view.id, 'form')],
            'view_id': view.id,
            'res_id': dashboard.id,
            'target': 'main',
            'context': {
                'create': False,
                'edit': False,
                'form_view_initial_mode': 'readonly',
            },
        }
