# -*- coding: utf-8 -*-
from odoo import _, api, fields, models
from odoo.exceptions import UserError


class PeopleEngineLegalArticleUpdate(models.Model):
    _name = "pe.legal.article.update"
    _description = "Mise à jour proposée article juridique"
    _order = "fetched_at desc"

    original_article_id = fields.Many2one(
        "pe.legal.article", required=True, ondelete="cascade"
    )
    proposed_content = fields.Text(required=True)
    proposed_plain_language = fields.Text()
    source_url = fields.Char()
    fetched_at = fields.Datetime(default=fields.Datetime.now)
    status = fields.Selection(
        [
            ("pending_review", "En attente révision RH"),
            ("validated", "Validé par RH"),
            ("rejected", "Rejeté"),
            ("applied", "Appliqué"),
        ],
        default="pending_review",
    )
    reviewed_by_id = fields.Many2one("hr.employee")
    review_date = fields.Datetime()
    review_notes = fields.Text()
    applied_at = fields.Datetime()
    new_article_id = fields.Many2one("pe.legal.article", readonly=True)

    def action_validate(self):
        if not self.env.user.has_group("people_engine.group_hr"):
            raise UserError(_("Validation RH requise."))
        self.write(
            {
                "status": "validated",
                "reviewed_by_id": self.env.user.employee_id.id,
                "review_date": fields.Datetime.now(),
            }
        )

    def action_reject(self):
        self.write({"status": "rejected"})

    def action_apply(self):
        for update in self:
            if update.status != "validated":
                raise UserError(_("Validez la mise à jour avant application."))
            self.env["pe.legal.updater.service"].apply_validated_update(update.id)
