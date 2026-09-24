# -*- coding: utf-8 -*-
from odoo import http
from odoo.http import request


class IntellixStyleGuideController(http.Controller):
    @http.route("/intellix/style-guide", type="http", auth="user", website=False)
    def style_guide(self, **kwargs):
        return request.render("intellix_branding.style_guide_page", {})
