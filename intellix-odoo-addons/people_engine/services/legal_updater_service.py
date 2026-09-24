# -*- coding: utf-8 -*-
import logging

from odoo import _, api, fields, models

_logger = logging.getLogger(__name__)

DEFAULT_PLAIN_PROMPT = """Résume en 3-4 phrases simples en français québécois cet article de loi pour un gestionnaire non-juriste."""


class PeopleEngineLegalUpdaterService(models.AbstractModel):
    _name = "pe.legal.updater.service"
    _description = "Mise à jour bibliothèque juridique (n8n)"

    DISCLAIMER_UPDATE = """
⚠️ MISE À JOUR PROPOSÉE — Non validée
Cette mise à jour a été générée automatiquement depuis des sources officielles.
Elle DOIT être révisée par un professionnel RH ou juridique avant activation.
"""

    @api.model
    def propose_article_update(
        self, article_code, jurisdiction_code, new_content, source_url=""
    ):
        jurisdiction = self.env["pe.legal.jurisdiction"].search(
            [("code", "=", jurisdiction_code)], limit=1
        )
        domain = [
            ("code", "=", article_code),
            ("is_current", "=", True),
        ]
        if jurisdiction:
            domain.append(("jurisdiction_id", "=", jurisdiction.id))
        existing = self.env["pe.legal.article"].search(domain, limit=1)
        if not existing:
            return {"status": "not_found", "article_code": article_code}

        update = self.env["pe.legal.article.update"].create(
            {
                "original_article_id": existing.id,
                "proposed_content": new_content,
                "source_url": source_url,
                "review_notes": self.DISCLAIMER_UPDATE,
                "status": "pending_review",
            }
        )
        self._notify_hr_admin(update)
        return {
            "status": "proposed",
            "update_id": update.id,
            "article": article_code,
        }

    @api.model
    def _notify_hr_admin(self, update_record):
        group = self.env.ref("people_engine.group_hr", raise_if_not_found=False)
        if not group:
            return
        for user in group.user_ids:
            self.env["mail.activity"].sudo().create(
                {
                    "activity_type_id": self.env.ref(
                        "mail.mail_activity_data_todo"
                    ).id,
                    "summary": _("Mise à jour juridique à réviser"),
                    "note": _("Article %s — révision RH requise")
                    % update_record.original_article_id.code,
                    "user_id": user.id,
                    "res_model_id": self.env["ir.model"]
                    ._get("pe.legal.article.update")
                    .id,
                    "res_id": update_record.id,
                }
            )

    @api.model
    def apply_validated_update(self, update_id):
        update = self.env["pe.legal.article.update"].browse(update_id)
        update.ensure_one()
        if update.status != "validated":
            raise ValueError(_("La mise à jour doit être validée par RH."))

        original = update.original_article_id
        original.write({"is_current": False})

        new_article = original.copy(
            {
                "content": update.proposed_content,
                "source_url": update.source_url or original.source_url,
                "last_updated": fields.Date.today(),
                "is_current": True,
                "plain_language": update.proposed_plain_language or "",
            }
        )
        if not new_article.plain_language:
            self._regenerate_plain_language(new_article)

        update.write(
            {
                "status": "applied",
                "applied_at": fields.Datetime.now(),
                "new_article_id": new_article.id,
            }
        )
        return new_article

    @api.model
    def _regenerate_plain_language(self, article):
        if "renovation.ai.service" not in self.env:
            return
        svc = self.env["renovation.ai.service"]
        if not svc._available():
            return
        try:
            text = svc._call(
                [
                    {
                        "role": "user",
                        "content": "Article %s — %s:\n%s"
                        % (
                            article.code,
                            article.title,
                            (article.content or "")[:2000],
                        ),
                    }
                ],
                system=DEFAULT_PLAIN_PROMPT,
                max_tokens=400,
                purpose="pe_legal_plain",
            )
            article.plain_language = text
        except Exception:
            _logger.exception("PE legal plain language regen")
