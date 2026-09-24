# -*- coding: utf-8 -*-
import logging
import uuid
from datetime import timedelta

from odoo import _, api, fields, models
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


class DoorwaySocialWizard(models.TransientModel):
    _name = "doorway.social.wizard"
    _description = "Wizard calendrier éditorial IA"

    pipeline_id = fields.Many2one("crm.team", string="Marque / Pipeline", required=True)
    topic = fields.Char("Sujet ou campagne", required=True)
    period_start = fields.Date("Du", default=fields.Date.today, required=True)
    period_end = fields.Date("Au", required=True)
    frequency = fields.Integer("Posts/semaine", default=5)
    account_ids = fields.Many2many("doorway.social.account", string="Comptes cibles")
    tone = fields.Selection(
        [
            ("expert", "Expert"),
            ("proximite", "Humain"),
            ("promotionnel", "Promotionnel"),
            ("educatif", "Éducatif"),
            ("inspirant", "Inspirant"),
        ],
        default="proximite",
    )

    @api.constrains("period_start", "period_end")
    def _check_period(self):
        for rec in self:
            if rec.period_end and rec.period_start and rec.period_end < rec.period_start:
                raise UserError(_("La date de fin doit être après la date de début."))

    def action_generate(self):
        self.ensure_one()
        batch_ref = str(uuid.uuid4())
        Claude = self.env["doorway.social.claude.service"]
        calendar_data = Claude.generate_calendar(self)
        posts = self._create_posts_from_calendar(calendar_data, batch_ref)
        if not posts:
            raise UserError(
                _("Aucun post généré. Vérifiez la clé Anthropic dans la configuration.")
            )
        return {
            "name": _("Calendrier généré"),
            "type": "ir.actions.act_window",
            "res_model": "doorway.social.post",
            "view_mode": "kanban,calendar,list,form",
            "domain": [("batch_ref", "=", batch_ref)],
            "context": {
                "default_pipeline_id": self.pipeline_id.id,
                "default_batch_ref": batch_ref,
            },
        }

    def _create_posts_from_calendar(self, calendar_data, batch_ref):
        Post = self.env["doorway.social.post"]
        posts_data = calendar_data.get("posts") or []
        created = Post.browse()
        tone_label = dict(self._fields["tone"].selection).get(self.tone, self.tone)

        for item in posts_data:
            day_offset = int(item.get("day_offset") or 0)
            sched = fields.Datetime.to_datetime(self.period_start) + timedelta(days=day_offset)
            best_time = item.get("best_time") or "10:00"
            try:
                h, m = best_time.split(":")[:2]
                sched = sched.replace(hour=int(h), minute=int(m))
            except (ValueError, TypeError):
                pass

            platform = item.get("platform") or "instagram"
            post_format = item.get("format") or "publication"
            if post_format not in dict(Post._fields["post_format"].selection):
                post_format = "publication"

            vals = {
                "batch_ref": batch_ref,
                "pipeline_id": self.pipeline_id.id,
                "account_ids": [(6, 0, self.account_ids.ids)],
                "platform": platform if platform in dict(Post._fields["platform"].selection) else "instagram",
                "post_format": post_format,
                "hook": item.get("hook") or "",
                "angle": item.get("angle") or tone_label,
                "cta": item.get("cta") or "",
                "hashtags": " ".join(item.get("hashtags") or []),
                "visual_description": item.get("visual_description") or "",
                "scheduled_date": sched,
                "best_time_ai": sched,
                "state": "draft",
            }
            created |= Post.create(vals)
        return created
