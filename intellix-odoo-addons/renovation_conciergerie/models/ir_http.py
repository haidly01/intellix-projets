# -*- coding: utf-8 -*-
import json

from odoo import api, models
from odoo.http import request
from werkzeug.exceptions import HTTPException


class IrHttp(models.AbstractModel):
    _inherit = "ir.http"

    @classmethod
    def _handle_error(cls, exception):
        """Double-clic login : 1er POST OK, 2e POST échoue en CSRF alors que la session est valide."""
        if (
            isinstance(exception, HTTPException)
            and exception.code == 400
            and request.httprequest.path == "/web/login"
            and request.httprequest.method == "POST"
            and request.session.uid
        ):
            redirect = (
                request.params.get("redirect")
                or request.httprequest.form.get("redirect")
                or "/odoo"
            )
            if not redirect or redirect.rstrip("?") in ("/odoo", ""):
                redirect = "/odoo"
            return request.redirect(redirect, 303)
        return super()._handle_error(exception)

    @classmethod
    def _doorway_allowed_company_ids_for_user(cls, user):
        if not user or not user.id:
            return []
        # Public / portail : ne pas toucher au contexte sociétés (login website).
        if user.share or user.login == "public":
            return []
        Team = request.env["crm.team"].sudo()
        if user._doorway_is_crm_superuser():
            return list(user.company_ids.ids)
        if user._doorway_is_crm_peer_sales_user():
            return Team._doorway_pipeline_allowed_company_ids(
                include_digital_doorway=True
            )
        return []

    @classmethod
    def _doorway_merge_allowed_companies(cls, ctx, allowed):
        """ctx est un dict pour les requêtes JSON-RPC déjà désérialisées
        (/mail/data, call_kw), mais une chaîne JSON pour des endpoints comme
        /report/download (cf. web/controllers/report.py: json.loads(context)).
        On préserve le type d'origine en sortie pour ne pas casser le
        json.loads() fait plus loin par le contrôleur appelant."""
        if not allowed:
            return ctx
        was_json_str = isinstance(ctx, str)
        if was_json_str:
            try:
                ctx = json.loads(ctx) if ctx else {}
            except (TypeError, ValueError):
                ctx = {}
        merged = dict(ctx or {})
        merged["allowed_company_ids"] = allowed
        return json.dumps(merged) if was_json_str else merged

    @classmethod
    def _doorway_patch_request_params_context(cls, allowed):
        """JSON-RPC : context peut être dans params ou params.kwargs (/mail/data, call_kw)."""
        params = getattr(request, "params", None)
        if not isinstance(params, dict):
            return
        if "context" in params:
            params["context"] = cls._doorway_merge_allowed_companies(
                params.get("context"), allowed
            )
        kwargs = params.get("kwargs")
        if isinstance(kwargs, dict) and "context" in kwargs:
            kwargs["context"] = cls._doorway_merge_allowed_companies(
                kwargs.get("context"), allowed
            )

    @classmethod
    def _doorway_apply_request_company_context(cls):
        """Évite les accès « top secret » sur crm.team / leads / chatter multi-sociétés."""
        uid = getattr(request.session, "uid", None)
        if not uid:
            return
        user = request.env["res.users"].sudo().browse(uid).exists()
        allowed = cls._doorway_allowed_company_ids_for_user(user)
        if not allowed:
            return
        request.update_context(allowed_company_ids=allowed)
        cls._doorway_patch_request_params_context(allowed)

    @classmethod
    def _doorway_ordered_company_ids(cls, user, allowed):
        digital_id = request.env["crm.team"].sudo()._doorway_digital_doorway_company_id()
        if digital_id and digital_id in allowed:
            return [digital_id] + [c for c in allowed if c != digital_id]
        return list(allowed)

    @api.model
    def lazy_session_info(self):
        """Appelé après chargement du webclient — aligne le contexte sociétés."""
        info = super().lazy_session_info()
        user = self.env.user
        allowed = self._doorway_allowed_company_ids_for_user(user)
        if allowed:
            ordered = self._doorway_ordered_company_ids(user, allowed)
            request.update_context(allowed_company_ids=ordered)
        return info

    def session_info(self):
        result = super().session_info()
        user = self.env.user
        allowed = self._doorway_allowed_company_ids_for_user(user)
        if not allowed:
            return result
        ordered = self._doorway_ordered_company_ids(user, allowed)
        request.update_context(allowed_company_ids=ordered)
        # Ne réécrire le cookie cids que s'il diffère (évite rechargements inutiles).
        cids_value = "-".join(str(c) for c in ordered)
        if request.httprequest.cookies.get("cids") != cids_value:
            request.future_response.set_cookie("cids", cids_value)
        return result

    @classmethod
    def _doorway_ensure_request_user(cls):
        """Login website : uid vide → 500 singleton ou 403 res.lang (pas de groupe Public)."""
        if request.env.uid:
            return
        uid = getattr(request.session, "uid", None)
        if uid:
            user = request.env["res.users"].sudo().with_context(active_test=False).browse(uid)
            if user.exists():
                request.update_env(user=user.id)
                return
        public_id = request.env["ir.model.data"].sudo()._xmlid_to_res_id("base.public_user")
        if public_id:
            request.update_env(user=public_id)

    @classmethod
    def _match(cls, path):
        # http_routing._match lit res.lang ; auth=none remet uid a None ensuite.
        cls._doorway_ensure_request_user()
        return super()._match(path)

    @classmethod
    def _dispatch(cls, endpoint):
        cls._doorway_apply_request_company_context()
        cls._doorway_ensure_request_user()
        return super()._dispatch(endpoint)
