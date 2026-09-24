# -*- coding: utf-8 -*-
"""Formulaire public /avis/<token> — un séjour, un lien, publication manuelle ensuite."""
import logging

from odoo import http
from odoo.exceptions import UserError
from odoo.http import request

_logger = logging.getLogger(__name__)


class CoinsReviewPortal(http.Controller):
    def _review(self, token):
        token = (token or "").strip()
        if not token or len(token) < 8:
            return request.env["coins.property.review"]
        return (
            request.env["coins.property.review"]
            .sudo()
            .search([("token", "=", token)], limit=1)
        )

    @http.route(
        ["/avis/<string:token>", "/avis/<string:token>/"],
        type="http",
        auth="public",
        website=False,
        csrf=True,
        methods=["GET", "POST"],
    )
    def avis_form(self, token, **kw):
        review = self._review(token)
        if not review:
            return request.render("coins_marocain.review_portal_unknown", {})
        error = ""
        submitted = review.state == "a_valider" and bool(review.submitted_at)
        published = review.state == "publie"
        if request.httprequest.method == "POST" and not published:
            try:
                note = int(kw.get("note") or 0)
            except (TypeError, ValueError):
                note = 0
            try:
                review.submit_from_token(
                    kw.get("texte") or "",
                    author_name=kw.get("author_name") or "",
                    note=note,
                )
                submitted = True
            except UserError as exc:
                error = str(exc)
            except Exception:
                _logger.exception("soumission avis token=%s", token[:8])
                error = "L’enregistrement a échoué. Réessayez ou écrivez à Yasmine."
        return request.render(
            "coins_marocain.review_portal_page",
            {
                "review": review,
                "token": token,
                "submitted": submitted,
                "published": published,
                "error": error,
                "csrf_token": request.csrf_token(),
            },
        )
