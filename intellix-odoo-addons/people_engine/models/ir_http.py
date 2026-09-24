# -*- coding: utf-8 -*-
from odoo import models
from odoo.http import request


class IrHttp(models.AbstractModel):
    _inherit = "ir.http"

    @classmethod
    def _pe_hr_allowed_company_ids(cls, user):
        """RH / admin système : toutes les sociétés autorisées pour hr.employee."""
        if not user:
            return []
        try:
            from odoo.addons.renovation_conciergerie.models.res_users import (
                DOORWAY_HR_DIRECTOR_LOGINS,
            )
        except ImportError:
            DOORWAY_HR_DIRECTOR_LOGINS = ()
        if user.login in DOORWAY_HR_DIRECTOR_LOGINS:
            return list(user.company_ids.ids)
        if user.has_group("base.group_system") or user.has_group(
            "people_engine.group_hr"
        ) or user.has_group("people_engine.group_manager"):
            return list(user.company_ids.ids)
        return []

    @classmethod
    def _pe_merge_context_companies(cls, allowed):
        params = getattr(request, "params", None)
        if not isinstance(params, dict):
            return
        for key in ("context",):
            if key in params and isinstance(params[key], dict):
                ctx = dict(params[key])
                ctx["allowed_company_ids"] = allowed
                params[key] = ctx
        kwargs = params.get("kwargs")
        if isinstance(kwargs, dict) and isinstance(kwargs.get("context"), dict):
            ctx = dict(kwargs["context"])
            ctx["allowed_company_ids"] = allowed
            kwargs["context"] = ctx

    @classmethod
    def _dispatch(cls, endpoint):
        uid = getattr(request.session, "uid", None)
        if uid:
            user = request.env["res.users"].sudo().browse(uid).exists()
            allowed = cls._pe_hr_allowed_company_ids(user)
            if allowed:
                request.update_context(allowed_company_ids=allowed)
                cls._pe_merge_context_companies(allowed)
        return super()._dispatch(endpoint)
