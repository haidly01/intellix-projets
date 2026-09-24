# -*- coding: utf-8 -*-

JT_ADMIN_LOGIN = 'jason@jasonthomasassurance.ca'

PLATFORM_MENU_XMLIDS = [
    'doorway_agents_dashboard.menu_agents_root',
    'doorway_vicidial_campaigns.menu_vicidial_app_root',
    'crm.crm_menu_root',
    'people_engine.menu_people_engine_root',
    'doorway_social_ia.menu_social_root',
    'doorway_agents_dashboard.menu_lea_qc_root',
    'doorway_messaging.menu_messaging_root',
    'doorway_traffic_manager.menu_traffic_root',
    'project.menu_main_pm',
    'account.menu_finance',
    'spreadsheet_dashboard.spreadsheet_dashboard_menu_root',
    'intellix_support.menu_intellix_support_root',
    'calendar.mail_menu_calendar',
    'contacts.menu_contacts',
    'doorway_leads_bruts.menu_leads_bruts_root',
    'lead_automation_hub.menu_lead_automation_root',
    'doorway_credits.menu_doorway_credits_root',
    'renovation_conciergerie.menu_renovation_root',
    # menu_partner_root volontairement exclus: réservé aux Partenaire Rénovation
    'website.menu_website_configuration',
    'utm.menu_link_tracker_root',
    'base.menu_management',
    'base.menu_tests',
]


def _restrict_intellix_menus(env):
    platform = env.ref('jason_thomas_assurance.group_intellix_platform')
    for xmlid in PLATFORM_MENU_XMLIDS:
        menu = env.ref(xmlid, raise_if_not_found=False)
        if menu:
            menu.sudo().write({'group_ids': [(6, 0, [platform.id])]})


def _ensure_jt_admin_company(env):
    """Jason n'appartient qu'à sa société — pas Digital Doorway / Agence Doorway."""
    company = env.ref('jason_thomas_assurance.company_jt', raise_if_not_found=False)
    jason = env['res.users'].search([('login', '=', JT_ADMIN_LOGIN)], limit=1)
    if not company or not jason:
        return
    jason.sudo().write({
        'company_id': company.id,
        'company_ids': [(6, 0, [company.id])],
    })
    if jason.partner_id:
        jason.partner_id.sudo().write({'company_id': company.id})


def _assign_platform_group(env):
    platform = env.ref('jason_thomas_assurance.group_intellix_platform')
    jt_admin = env.ref('jason_thomas_assurance.group_jt_admin')
    internal_users = env['res.users'].search([
        ('active', '=', True),
        ('share', '=', False),
        ('login', '!=', JT_ADMIN_LOGIN),
    ])
    for user in internal_users:
        commands = []
        if platform not in user.group_ids:
            commands.append((4, platform.id))
        if jt_admin in user.group_ids:
            commands.append((3, jt_admin.id))
        if commands:
            user.sudo().write({'group_ids': commands})

    jason = env['res.users'].search([('login', '=', JT_ADMIN_LOGIN)], limit=1)
    if jason:
        jason.sudo().write({'group_ids': [(6, 0, [jt_admin.id])]})
    _ensure_jt_admin_company(env)


def _backfill_birth_dates(env):
    """Recopie la date de naissance AGO/Inalco vers les doublons Assomption sans DOB."""
    Client = env['jt.client']
    by_name = {}
    for client in Client.search([('birth_date', '!=', False)]):
        key = (client.full_name or '').strip().upper()
        if key:
            by_name[key] = client.birth_date
    updated = 0
    for client in Client.search([('birth_date', '=', False)]):
        key = (client.full_name or '').strip().upper()
        if key and key in by_name:
            client.sudo().write({'birth_date': by_name[key]})
            updated += 1
    return updated


def _recompute_anniversaries(env):
    env['jt.client'].search([])._compute_anniversary()


def _restrict_jt_app_menu(env):
    """L'app JT ne doit pas apparaître sur intellixcrm.com/odoo pour les users Doorway."""
    menu = env.ref('jason_thomas_assurance.menu_jt_root', raise_if_not_found=False)
    jt_admin = env.ref('jason_thomas_assurance.group_jt_admin', raise_if_not_found=False)
    if menu and jt_admin:
        menu.sudo().write({'group_ids': [(6, 0, [jt_admin.id])]})


def post_init_hook(env):
    _restrict_intellix_menus(env)
    _restrict_jt_app_menu(env)
    _assign_platform_group(env)
    _backfill_birth_dates(env)
    _recompute_anniversaries(env)
    if 'jt.portal.access' in env:
        env['jt.portal.access'].create_access_for_all_clients()


def uninstall_hook(env):
    platform = env.ref('jason_thomas_assurance.group_intellix_platform', raise_if_not_found=False)
    if not platform:
        return
    users = env['res.users'].search([('group_ids', 'in', platform.id)])
    for user in users:
        user.sudo().write({'group_ids': [(3, platform.id)]})
