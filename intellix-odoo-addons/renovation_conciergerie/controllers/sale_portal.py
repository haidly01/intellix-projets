from odoo import fields, http
from odoo.http import request

from odoo.addons.sale.controllers.portal import CustomerPortal


class RenovationSalePortal(CustomerPortal):
    @http.route()
    def portal_order_page(
        self,
        order_id,
        report_type=None,
        access_token=None,
        **kw,
    ):
        response = super().portal_order_page(
            order_id,
            report_type=report_type,
            access_token=access_token,
            **kw,
        )
        if report_type in ("html", "pdf", "text"):
            return response

        is_link_preview = request.httprequest.headers.get("Odoo-Link-Preview")
        if (
            request.env.user.share
            and access_token
            and is_link_preview != "True"
        ):
            order = request.env["sale.order"].sudo().browse(order_id)
            if order.exists():
                order._register_quotation_portal_view()
        return response
