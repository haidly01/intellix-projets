# -*- coding: utf-8 -*-
"""Dashboard partenaires live — portail + JSON (recalcul à chaque requête)."""
from odoo import http
from odoo.exceptions import AccessError
from odoo.http import request

RENO_HOME = "/my/leads"
ITEX_HOME = "/my/finance-itex"


class CoinsPartenairesDashboardController(http.Controller):

    def _cat_name(self, cat):
        name = cat.name or ""
        if isinstance(name, dict):
            name = name.get("en_US") or name.get("fr_FR") or next(iter(name.values()), "")
        return (name or "").lower()

    def _is_reno_partner(self, user):
        if not user or user._is_public():
            return False
        if user.has_group("renovation_conciergerie.group_renovation_partner"):
            return True
        partner = user.partner_id.commercial_partner_id or user.partner_id
        if not partner or "renovation.partner.package" not in request.env:
            return False
        return bool(
            request.env["renovation.partner.package"].sudo().search_count(
                [
                    ("partner_id", "child_of", partner.id),
                    ("state", "=", "active"),
                ]
            )
        )

    def _is_itex_partner(self, user):
        if not user or user._is_public():
            return False
        partner = user.partner_id
        if not partner:
            return False
        cats = partner.category_id
        commercial = partner.commercial_partner_id
        if commercial:
            cats |= commercial.category_id
        if any("itex" in self._cat_name(cat) for cat in cats):
            return True
        if "renovation.partner.package" not in request.env:
            return False
        pkgs = request.env["renovation.partner.package"].sudo().search(
            [
                ("partner_id", "child_of", (commercial or partner).id),
                ("state", "=", "active"),
            ]
        )
        for pkg in pkgs:
            blob = " ".join(
                filter(
                    None,
                    [
                        pkg.name or "",
                        pkg.package_type_id.name or "",
                        pkg.forfait_type_id.name if pkg.forfait_type_id else "",
                    ],
                )
            ).lower()
            if "itex" in blob:
                return True
        return False

    def _partner_shell_home(self, user):
        if self._is_reno_partner(user):
            return RENO_HOME
        if self._is_itex_partner(user):
            return ITEX_HOME
        return None

    def _can_view(self):
        """Shell Finance / ITEX : marqueur ITEX seulement, pas les partenaires Réno."""
        user = request.env.user
        if user._is_public():
            return False
        if self._is_reno_partner(user) and not self._is_itex_partner(user):
            return False
        return self._is_itex_partner(user) or user.has_group(
            "intellix_partner_portal.group_intellix_partner_portal"
        )

    def _crm_home(self):
        user = request.env.user
        reno_home = self._partner_shell_home(user)
        if reno_home:
            return reno_home
        if user._is_internal() and (
            user.has_group("renovation_conciergerie.group_doorway_pipeline_assigned")
            or user.has_group("sales_team.group_sale_salesman")
        ):
            return "/odoo/action-726"
        return "/odoo"

    def _stats(self, period_days=30):
        return request.env["coins.entente"].sudo().get_live_dashboard_stats(
            period_days=period_days
        )

    def _redirect_reno_if_needed(self):
        user = request.env.user
        if self._is_reno_partner(user) and not self._is_itex_partner(user):
            return request.redirect(RENO_HOME)
        return None

    @http.route(
        [
            "/my/finance-itex",
            "/my/finance-itex/<int:period>",
            "/my/itex",
            "/my/itex/<int:period>",
        ],
        type="http",
        auth="user",
        website=True,
        sitemap=False,
    )
    def portal_dashboard(self, period=30, **kw):
        reno = self._redirect_reno_if_needed()
        if reno:
            return reno
        if not self._can_view():
            crm = self._crm_home()
            if crm:
                return request.redirect(crm)
            raise AccessError("Accès réservé aux partenaires / utilisateurs autorisés.")
        try:
            period = int(period or kw.get("period") or 30)
        except (TypeError, ValueError):
            period = 30
        stats = self._stats(period_days=period)
        partner_name = (
            request.env.user.partner_id.name
            or request.env.user.name
            or "Partenaire"
        )
        initials = ((partner_name or "IX")[:2] or "IX").upper()
        return request.render(
            "coins_marocain_partenariats.portal_partenaires_dashboard",
            {
                "stats": stats,
                "period": stats.get("period_days") or 30,
                "page_name": "finance_itex",
                "partner_name": partner_name,
                "initials": initials,
            },
        )

    @http.route(
        ["/my/coins-partenaires", "/my/coins-partenaires/<int:period>"],
        type="http",
        auth="user",
        website=True,
        sitemap=False,
    )
    def portal_dashboard_legacy(self, period=30, **kw):
        """Ancienne URL « coins » → Réno ou Finance / ITEX selon le métier."""
        user = request.env.user
        target = self._partner_shell_home(user)
        if target == RENO_HOME:
            return request.redirect(RENO_HOME)
        try:
            period = int(period or 30)
        except (TypeError, ValueError):
            period = 30
        if period in (7, 90):
            return request.redirect("%s/%s" % (ITEX_HOME, period))
        return request.redirect(ITEX_HOME)

    @http.route(
        "/coins/partenaires/dashboard/stats",
        type="json",
        auth="user",
    )
    def dashboard_stats_json(self, period_days=30, **kw):
        if not self._can_view():
            raise AccessError("Accès refusé.")
        return self._stats(period_days=period_days)
