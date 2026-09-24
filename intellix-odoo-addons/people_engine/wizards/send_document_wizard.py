# -*- coding: utf-8 -*-
from odoo import _, api, fields, models


class PeSendDocumentWizard(models.TransientModel):
    _name = "pe.send.document.wizard"
    _description = "Envoyer un document depuis la banque RH (legacy)"

    profile_id = fields.Many2one("pe.employee.profile", required=True)
    employee_id = fields.Many2one(related="profile_id.employee_id")
    lifecycle_stage_id = fields.Many2one(
        related="profile_id.lifecycle_stage_id",
        string="Stade actuel",
    )
    template_ids = fields.Many2many(
        "pe.document.template",
        "pe_send_document_wizard_template_rel",
        "wizard_id",
        "template_id",
        string="Documents à envoyer",
    )
    send_email = fields.Boolean(string="Envoyer par e-mail", default=True)
    email_subject = fields.Char(string="Objet")
    email_body = fields.Html(sanitize_attributes=False)
    arrival_pack = fields.Boolean(
        string="Pack d'arrivée",
        help="Pré-sélection des modèles marqués « Pack d'arrivée ».",
    )

    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        profile_id = res.get("profile_id") or self.env.context.get(
            "default_profile_id"
        )
        if not profile_id:
            return res
        profile = self.env["pe.employee.profile"].browse(profile_id)
        stage = profile.lifecycle_stage_id
        arrival_pack = (
            res.get("arrival_pack")
            or self.env.context.get("default_arrival_pack")
        )
        if "template_ids" in fields_list and not res.get("template_ids"):
            ctx_templates = self.env.context.get("default_template_ids")
            if ctx_templates and ctx_templates[0][0] == 6:
                res["template_ids"] = ctx_templates
            else:
                templates = self.env["pe.document.template"].search_for_stage(
                    stage,
                    arrival_pack_only=bool(arrival_pack),
                )
                res["template_ids"] = [(6, 0, templates.ids)]
        if "email_subject" in fields_list and not res.get("email_subject"):
            if arrival_pack:
                res["email_subject"] = _("Pack d'intégration — %s") % (
                    profile.display_name,
                )
            else:
                res["email_subject"] = _("Document RH — %s") % profile.display_name
        return res

    @api.onchange("profile_id", "arrival_pack")
    def _onchange_profile_templates(self):
        if not self.profile_id:
            return
        stage = self.profile_id.lifecycle_stage_id
        templates = self.env["pe.document.template"].search_for_stage(
            stage,
            arrival_pack_only=self.arrival_pack,
        )
        self.template_ids = templates

    def action_send(self):
        """Redirige vers le wizard unifié de personnalisation."""
        self.ensure_one()
        ctx = {
            "default_profile_id": self.profile_id.id,
            "default_arrival_pack": self.arrival_pack,
        }
        if self.template_ids:
            ctx["default_template_ids"] = [(6, 0, self.template_ids.ids)]
        return {
            "type": "ir.actions.act_window",
            "name": _("Document personnalisé"),
            "res_model": "pe.personalize.document.wizard",
            "view_mode": "form",
            "target": "new",
            "context": ctx,
        }
