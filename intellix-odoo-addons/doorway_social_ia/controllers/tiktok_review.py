# -*- coding: utf-8 -*-
"""Public TikTok app-review demo on the registered website domain."""
import os

from odoo import http
from odoo.http import request
from odoo.modules.module import get_module_path


def _addon_file(*parts):
    root = get_module_path("doorway_social_ia")
    return os.path.join(root, *parts) if root else ""


class TiktokReviewDemoController(http.Controller):
    @http.route(
        "/doorway/publication/tiktok/demo",
        type="http",
        auth="public",
        csrf=False,
        website=False,
    )
    def tiktok_review_demo(self, **kwargs):
        path = _addon_file("static", "src", "tiktok_review", "index.html")
        if not path or not os.path.isfile(path):
            return request.not_found()
        with open(path, "rb") as handle:
            html = handle.read()
        return request.make_response(
            html,
            headers=[
                ("Content-Type", "text/html; charset=utf-8"),
                ("Cache-Control", "no-store"),
            ],
        )

    @http.route(
        "/doorway/publication/tiktok/demo/video",
        type="http",
        auth="public",
        csrf=False,
        website=False,
    )
    def tiktok_review_video(self, **kwargs):
        path = _addon_file(
            "static",
            "src",
            "tiktok_review",
            "intellix_tiktok_sandbox_demo.mp4",
        )
        if not path or not os.path.isfile(path):
            return request.not_found()
        with open(path, "rb") as handle:
            data = handle.read()
        return request.make_response(
            data,
            headers=[
                ("Content-Type", "video/mp4"),
                (
                    "Content-Disposition",
                    'attachment; filename="intellix_tiktok_sandbox_demo.mp4"',
                ),
                ("Content-Length", str(len(data))),
                ("Cache-Control", "public, max-age=300"),
            ],
        )
