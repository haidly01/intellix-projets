# -*- coding: utf-8 -*-
import logging
import mimetypes
import os

from odoo import http
from odoo.http import request

_logger = logging.getLogger(__name__)


class VicidialRecordingController(http.Controller):
    @http.route(
        "/doorway/vicidial/recording/<string:uniqueid>",
        type="http",
        auth="user",
        methods=["GET"],
        csrf=False,
    )
    def serve_recording(self, uniqueid, **kwargs):
        log = request.env["doorway.call.log"].search(
            [("vicidial_call_id", "=", uniqueid)], limit=1
        )
        if not log:
            return request.not_found()

        from odoo.addons.doorway_vicidial_campaigns.services.vicidial_service import (
            VicidialService,
        )

        path = VicidialService(request.env).get_recording_file_path(uniqueid)
        if not path or not os.path.isfile(path):
            if log.recording_url and log.recording_url.startswith(("http://", "https://")):
                return request.redirect(log.recording_url)
            return request.not_found()

        mime, _encoding = mimetypes.guess_type(path)
        if not mime:
            mime = "audio/wav" if path.endswith(".wav") else "application/octet-stream"
        with open(path, "rb") as handle:
            data = handle.read()
        return request.make_response(
            data,
            headers=[
                ("Content-Type", mime),
                ("Content-Disposition", 'inline; filename="%s"' % os.path.basename(path)),
            ],
        )
