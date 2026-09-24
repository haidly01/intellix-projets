# -*- coding: utf-8 -*-
from odoo import http
from odoo.addons.portal.controllers.portal import CustomerPortal
from odoo.addons.portal.controllers.web import Home as PortalHome
from odoo.http import request

from .shell import (
    RENO_HOME,
    is_generic_or_wrong_shell_redirect,
    is_reno_partner,
    partner_shell_home,
)


class IntellixPartnerHome(PortalHome):
    """Login / home : Réno → /my/leads, ITEX seulement si marqueur ITEX."""

    def _ipp_portal_home(self, uid=None):
        uid = uid or request.session.uid
        if not uid:
            return None
        user = request.env["res.users"].sudo().browse(uid)
        if user.has_group("intellix_partner_portal.group_intellix_partner_portal") and not user._is_internal():
            return partner_shell_home(user) or RENO_HOME
        return None

    def _partner_backend_login_home(self, uid=None):
        uid = uid or request.session.uid
        if not uid:
            return None
        user = request.env["res.users"].sudo().browse(uid)
        if user.has_group("renovation_conciergerie.group_doorway_pipeline_assigned") or user.has_group(
            "sales_team.group_sale_salesman"
        ):
            if not is_reno_partner(user):
                return "/odoo/action-726"
        return partner_shell_home(user)

    def _login_redirect(self, uid, redirect=None):
        portal_home = self._ipp_portal_home(uid)
        backend_home = self._partner_backend_login_home(uid)
        target = portal_home or backend_home
        if target and is_generic_or_wrong_shell_redirect(redirect):
            redirect = target
        elif portal_home and (not redirect or redirect.startswith("/odoo") or redirect.startswith("/web")):
            redirect = portal_home
        return super()._login_redirect(uid, redirect=redirect)

    @http.route()
    def index(self, *args, **kw):
        target = self._ipp_portal_home()
        if target:
            return request.redirect_query(target, query=request.params)
        return super().index(*args, **kw)

    @http.route()
    def web_client(self, s_action=None, **kw):
        # Portail web seulement — ne pas expulser les partenaires backend de /odoo
        target = self._ipp_portal_home()
        if target:
            return request.redirect_query(target, query=request.params)
        return super().web_client(s_action=s_action, **kw)

    @http.route(
        "/web/login",
        type="http",
        auth="none",
        website=True,
        sitemap=False,
        csrf=False,
    )
    def web_login(self, redirect=None, **kw):
        """Pas de 400 CSRF sur le login (double POST / préfixe langue)."""
        return super().web_login(redirect=redirect, **kw)


class IntellixPartnerMyHome(CustomerPortal):
    @http.route()
    def home(self, **kw):
        target = partner_shell_home(request.env.user)
        if target:
            return request.redirect(target)
        return super().home(**kw)


try:
    from odoo.addons.account.controllers.portal import PortalAccount
except ImportError:  # pragma: no cover
    PortalAccount = None

if PortalAccount is not None:
    class IntellixPartnerPortalAccount(PortalAccount):
        @http.route()
        def portal_my_invoices(self, page=1, date_begin=None, date_end=None, sortby=None, filterby=None, **kw):
            user = request.env.user
            if user.share and user.has_group("intellix_partner_portal.group_intellix_partner_portal"):
                return request.redirect("/my/facturation")
            return super().portal_my_invoices(
                page=page, date_begin=date_begin, date_end=date_end, sortby=sortby, filterby=filterby, **kw
            )
