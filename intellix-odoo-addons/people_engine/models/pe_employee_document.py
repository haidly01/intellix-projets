# -*- coding: utf-8 -*-
import base64

from odoo import _, api, fields, models
from odoo.exceptions import UserError


class PeEmployeeDocument(models.Model):
    _name = "pe.employee.document"
    _description = "Document envoyé à un employé"
    _inherit = ["mail.thread"]
    _order = "sent_date desc, id desc"
    _rec_name = "name"

    name = fields.Char(required=True, tracking=True)
    profile_id = fields.Many2one(
        "pe.employee.profile",
        required=True,
        ondelete="cascade",
        index=True,
    )
    employee_id = fields.Many2one(
        related="profile_id.employee_id",
        store=True,
        readonly=True,
    )
    template_id = fields.Many2one("pe.document.template", string="Modèle source")
    attachment_id = fields.Many2one(
        "ir.attachment",
        string="Fichier",
        ondelete="restrict",
    )
    content_html = fields.Html(
        string="Contenu personnalisé",
        sanitize_attributes=False,
    )
    letter_date = fields.Date(string="Date de la lettre")
    delivery_method = fields.Selection(
        [
            ("email", "Courriel"),
            ("print", "Impression"),
            ("file", "Fichier joint"),
        ],
        string="Mode de remise",
    )
    stage_at_send_id = fields.Many2one(
        "pe.employee.lifecycle.stage",
        string="Stade à l'envoi",
    )
    sent_date = fields.Datetime(readonly=True)
    sent_by_id = fields.Many2one("res.users", string="Envoyé par", readonly=True)
    state = fields.Selection(
        [
            ("draft", "Brouillon"),
            ("sent", "Envoyé"),
            ("acknowledged", "Accusé réception"),
        ],
        default="draft",
        tracking=True,
    )
    notes = fields.Text()

    def action_mark_acknowledged(self):
        for doc in self:
            doc.state = "acknowledged"
            self.env["pe.action.log"].log_action(
                doc.profile_id,
                "document_acknowledged",
                _("Document « %s » accusé réception") % doc.name,
            )

    def action_print_letter(self):
        self.ensure_one()
        if self.content_html:
            if not self.attachment_id:
                report = self.env.ref("people_engine.action_report_pe_employee_letter")
                pdf_content, _report_format = self.env["ir.actions.report"]._render_qweb_pdf(
                    report.report_name,
                    self.ids,
                )
                attachment = self.env["ir.attachment"].create(
                    {
                        "name": "%s.pdf" % self.name,
                        "type": "binary",
                        "datas": base64.b64encode(pdf_content),
                        "res_model": "pe.employee.document",
                        "res_id": self.id,
                        "mimetype": "application/pdf",
                    }
                )
                self.attachment_id = attachment.id
            report = self.env.ref("people_engine.action_report_pe_employee_letter")
            return report.report_action(self)
        if self.attachment_id:
            return {
                "type": "ir.actions.act_url",
                "url": "/web/content/%s?download=true" % self.attachment_id.id,
                "target": "new",
            }
        raise UserError(_("Aucun contenu à imprimer."))

    def action_resend(self):
        self.ensure_one()
        if self.state == "draft":
            raise UserError(_("Le document n'a pas encore été envoyé."))
        ctx = {
            "default_profile_id": self.profile_id.id,
            "default_letter_date": self.letter_date,
        }
        if self.template_id:
            ctx["default_template_ids"] = [(6, 0, [self.template_id.id])]
            ctx["default_template_id"] = self.template_id.id
        return {
            "type": "ir.actions.act_window",
            "name": _("Document personnalisé"),
            "res_model": "pe.personalize.document.wizard",
            "view_mode": "form",
            "target": "new",
            "context": ctx,
        }
