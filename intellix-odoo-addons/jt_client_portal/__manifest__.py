# -*- coding: utf-8 -*-
{
    'name': 'Jason Thomas — Portail Client',
    'version': '19.0.1.1.0',
    'category': 'Website',
    'summary': 'Espace client sécurisé — Jason Thomas Assurance',
    'depends': ['jason_thomas_assurance', 'website', 'mail', 'crm'],
    'data': [
        'security/ir.model.access.csv',
        'data/jt_config.xml',
        'data/crm_tag.xml',
        'data/mail_template_invitation.xml',
        'views/jt_portal_access_views.xml',
        'views/portal_layout.xml',
        'views/portal_home.xml',
        'views/portal_polices.xml',
        'views/portal_police_detail.xml',
        'views/portal_contact.xml',
        'views/menus.xml',
    ],
    'assets': {
        'web.assets_frontend': [
            'jt_client_portal/static/css/portal.css',
        ],
    },
    'installable': True,
    'application': False,
    'license': 'LGPL-3',
}
