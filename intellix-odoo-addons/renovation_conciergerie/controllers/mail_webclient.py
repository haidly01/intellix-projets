# -*- coding: utf-8 -*-
from odoo.http import request
from odoo.addons.mail.controllers.webclient import WebclientController


class DoorwayMailWebclientController(WebclientController):
    """Chatter /mail/data : le client envoie souvent allowed_company_ids=[Agence] seul."""

    @classmethod
    def _doorway_mail_allowed_company_ids(cls):
        user = request.env.user
        if user._doorway_is_crm_superuser():
            return list(user.company_ids.ids)
        if user._doorway_is_crm_peer_sales_user():
            return request.env["crm.team"]._doorway_pipeline_allowed_company_ids(
                include_digital_doorway=True
            )
        return []

    @classmethod
    def _process_request(cls, fetch_params, context=None):
        allowed = cls._doorway_mail_allowed_company_ids()
        if allowed:
            context = dict(context or {})
            context["allowed_company_ids"] = allowed
        return super()._process_request(fetch_params, context=context)
