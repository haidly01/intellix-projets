{
    'name': 'Lead Automation Hub',
    'version': '1.1.1',
    'category': 'CRM',
    'summary': 'Lead Import, Segmentation, and AI Outreach',
    'depends': ['crm', 'web', 'intellix_branding', 'doorway_onboarding', 'sales_team'],
    'data': [
          'security/ir.model.access.csv',
          'views/campaign_map_views.xml',
          'views/lead_automation_home.xml',
          'views/crm_lead_views.xml',
          'views/menus.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'lead_automation_hub/static/src/js/twilio_phone_click.js',
        ],
    },
    'installable': True,
    'application': True,
}
