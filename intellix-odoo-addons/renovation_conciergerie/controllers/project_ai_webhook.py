import hmac
import json
import logging

from odoo import http
from odoo.http import request

_logger = logging.getLogger(__name__)

CORS_HEADERS = {
    "Access-Control-Allow-Origin": "*",
    "Access-Control-Allow-Methods": "POST, OPTIONS",
    "Access-Control-Allow-Headers": "Content-Type, X-Project-AI-Token",
}

TOKEN_PARAM = "renovation_conciergerie.project_ai_webhook_token"


class ProjectAiWebhookController(http.Controller):
    def _json_response(self, payload, status=200):
        headers = dict(CORS_HEADERS)
        headers["Content-Type"] = "application/json"
        return request.make_response(
            json.dumps(payload), headers=list(headers.items()), status=status
        )

    def _parse_payload(self, kwargs):
        data = dict(kwargs or {})
        try:
            raw = request.httprequest.get_data(as_text=True)
            if raw:
                parsed = json.loads(raw)
                if isinstance(parsed, dict):
                    data.update(parsed)
        except (ValueError, TypeError):
            pass
        return data

    def _resolve_project(self, data):
        env = request.env
        Project = env["project.project"].sudo()
        ref = data.get("project_id") or data.get("project")
        if ref is None:
            return Project.browse()
        if isinstance(ref, int) or (isinstance(ref, str) and ref.isdigit()):
            project = Project.browse(int(ref))
            return project if project.exists() else Project.browse()
        return Project.search([("name", "=", ref)], limit=1)

    @http.route(
        "/project/ai/webhook",
        type="http",
        auth="public",
        methods=["POST", "OPTIONS"],
        csrf=False,
    )
    def project_ai_webhook(self, **kwargs):
        if request.httprequest.method == "OPTIONS":
            return request.make_response("", headers=list(CORS_HEADERS.items()))

        data = self._parse_payload(kwargs)

        configured = (
            request.env["ir.config_parameter"].sudo().get_param(TOKEN_PARAM) or ""
        )
        provided = request.httprequest.headers.get("X-Project-AI-Token") or data.get(
            "token"
        ) or ""
        if not configured or not hmac.compare_digest(str(provided), str(configured)):
            return self._json_response(
                {"status": "error", "message": "Token invalide ou manquant."}, 401
            )

        if not request.env["renovation.ai.service"].sudo()._available():
            return self._json_response(
                {"status": "error", "message": "IA désactivée ou non configurée."}, 503
            )

        project = self._resolve_project(data)
        if not project:
            return self._json_response(
                {
                    "status": "error",
                    "message": "Projet introuvable (champ project_id ou project).",
                },
                404,
            )

        text = (data.get("text") or data.get("brief") or data.get("content") or "").strip()
        if not text:
            return self._json_response(
                {"status": "error", "message": "Champ 'text' (brief) requis."}, 400
            )

        try:
            created = project.sudo()._ai_generate_tasks_from_text(
                text, source_label=data.get("source") or "webhook"
            )
        except Exception as error:  # noqa: BLE001
            _logger.exception("Webhook tâches IA en échec")
            return self._json_response(
                {"status": "error", "message": str(error)}, 500
            )

        return self._json_response(
            {
                "status": "ok",
                "project_id": project.id,
                "created": len(created),
                "task_ids": created.ids,
            }
        )
