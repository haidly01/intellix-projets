# -*- coding: utf-8 -*-
import logging

from odoo import SUPERUSER_ID

_logger = logging.getLogger(__name__)


def post_init_hook(env):
    """Utilisateur démo portail."""
    contact = env.ref(
        "intellix_partner_portal.demo_partner_portal_contact",
        raise_if_not_found=False,
    )
    if contact:
        Users = env["res.users"].with_user(SUPERUSER_ID)
        login = "portal.demo@intellixcrm.com"
        user = Users.search([("login", "=", login)], limit=1)
        portal_group = env.ref("base.group_portal")
        ipp_group = env.ref("intellix_partner_portal.group_intellix_partner_portal")
        groups = portal_group | ipp_group
        if not user:
            user = Users.create(
                {
                    "name": "Jean Beaumont (Portail Demo)",
                    "login": login,
                    "partner_id": contact.id,
                    "group_ids": [(6, 0, groups.ids)],
                }
            )
        else:
            user.write({"group_ids": [(4, g.id) for g in groups]})
        user.write({"password": "PortalDemo2026!"})
        _logger.info("Partner portal demo user ready: %s", login)
