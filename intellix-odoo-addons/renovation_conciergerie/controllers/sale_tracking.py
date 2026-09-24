import base64

from werkzeug.exceptions import NotFound

from odoo import http
from odoo.http import request
from odoo.tools.misc import consteq


class SaleQuotationTracking(http.Controller):
    @http.route(
        "/renovation/sale/track/<int:mail_id>/<string:token>/open.gif",
        type="http",
        auth="public",
        csrf=False,
    )
    def track_sale_mail_open(self, mail_id, token, **post):
        expected = request.env["mail.mail"]._generate_sale_open_token(mail_id)
        if not consteq(token, expected):
            raise NotFound()

        mail = request.env["mail.mail"].sudo().browse(mail_id)
        if mail.exists() and mail.model == "sale.order" and mail.res_id:
            order = request.env["sale.order"].sudo().browse(mail.res_id)
            if order.exists():
                order._register_quotation_email_open()

        response = request.make_response(
            base64.b64decode(
                b"R0lGODlhAQABAIAAANvf7wAAACH5BAEAAAAALAAAAAABAAEAAAICRAEAOw=="
            ),
            headers=[("Content-Type", "image/gif")],
        )
        return response
