# -*- coding: utf-8 -*-
from odoo import models
from odoo.http import request


class IrHttp(models.AbstractModel):
    _inherit = "ir.http"

    def _doorway_user_theme(self):
        """Thème backend de l'utilisateur courant ('light' par défaut)."""
        try:
            user = request.env.user
            if user and request.session.uid:
                return user.doorway_theme or "light"
        except Exception:  # pragma: no cover - contexte sans utilisateur
            pass
        return "light"

    def color_scheme(self):
        """Bundle CSS écran : suit doorway_theme (light par défaut).
        Les tokens + classe body o_doorway_light/dark restent la source visuelle."""
        theme = self._doorway_user_theme()
        return "dark" if theme == "dark" else "light"

    def webclient_rendering_context(self):
        ctx = super().webclient_rendering_context()
        theme = self._doorway_user_theme()
        scheme = "dark" if theme == "dark" else "light"
        ctx["color_scheme"] = scheme
        ctx["doorway_theme"] = theme
        request.future_response.set_cookie(
            "color_scheme",
            scheme,
            max_age=60 * 60 * 24 * 365,
            path="/",
        )
        return ctx

    def session_info(self):
        info = super().session_info()
        try:
            if request.session.uid:
                info["doorway_theme"] = request.env.user.doorway_theme or "light"
        except Exception:  # pragma: no cover
            info["doorway_theme"] = "light"
        return info
