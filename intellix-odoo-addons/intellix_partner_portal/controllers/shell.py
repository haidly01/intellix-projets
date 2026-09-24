# -*- coding: utf-8 -*-
"""Routage portail par métier : Réno → /my/leads, ITEX seulement si marqueur ITEX."""

RENO_HOME = "/my/leads"
ITEX_HOME = "/my/finance-itex"


def _cat_name(cat):
    name = cat.name or ""
    if isinstance(name, dict):
        name = name.get("en_US") or name.get("fr_FR") or next(iter(name.values()), "")
    return (name or "").lower()


def is_reno_partner(user):
    if not user or user._is_public():
        return False
    if user.has_group("renovation_conciergerie.group_renovation_partner"):
        return True
    partner = user.partner_id.commercial_partner_id or user.partner_id
    if not partner or "renovation.partner.package" not in user.env:
        return False
    return bool(
        user.env["renovation.partner.package"].sudo().search_count(
            [
                ("partner_id", "child_of", partner.id),
                ("state", "=", "active"),
            ]
        )
    )


def is_itex_partner(user):
    if not user or user._is_public():
        return False
    partner = user.partner_id
    if not partner:
        return False
    cats = partner.category_id
    commercial = partner.commercial_partner_id
    if commercial:
        cats |= commercial.category_id
    if any("itex" in _cat_name(cat) for cat in cats):
        return True
    if "renovation.partner.package" not in user.env:
        return False
    pkgs = user.env["renovation.partner.package"].sudo().search(
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


def partner_shell_home(user):
    """Home portail : Réno d'abord, ITEX seulement si forfait/tag ITEX."""
    if is_reno_partner(user):
        return RENO_HOME
    if is_itex_partner(user):
        return ITEX_HOME
    return None


def _bare_path(redirect):
    if not redirect:
        return ""
    path = redirect.split("?", 1)[0]
    for prefix in ("/fr_CA", "/fr", "/en_US", "/en"):
        if path == prefix:
            return "/"
        if path.startswith(prefix + "/"):
            return path[len(prefix) :] or "/"
    return path


def is_generic_or_wrong_shell_redirect(redirect):
    path = _bare_path(redirect)
    if not path or path in ("/web", "/odoo", "/web/login", "/", "/my", "/my/", "/my/home"):
        return True
    if path.startswith("/web") or path.startswith("/odoo"):
        return True
    if path.startswith("/my/finance-itex") or path.startswith("/my/coins-partenaires"):
        return True
    if path.startswith("/my/itex"):
        return True
    return False
