# -*- coding: utf-8 -*-
import base64

from odoo import _, api, fields, models
from odoo.exceptions import UserError


class PePersonalizeDocumentWizard(models.TransientModel):
    _name = "pe.personalize.document.wizard"
    _description = "Personnaliser et envoyer un document RH"

    profile_id = fields.Many2one("pe.employee.profile", required=True)
    employee_id = fields.Many2one(related="profile_id.employee_id")
    lifecycle_stage_id = fields.Many2one(
        related="profile_id.lifecycle_stage_id",
        string="Stade actuel",
    )
    available_template_ids = fields.Many2many(
        "pe.document.template",
        compute="_compute_available_template_ids",
        string="Modèles disponibles",
    )
    template_ids = fields.Many2many(
        "pe.document.template",
        "pe_personalize_document_wizard_template_rel",
        "wizard_id",
        "template_id",
        string="Documents",
        domain="[('id', 'in', available_template_ids)]",
    )
    template_id = fields.Many2one(
        "pe.document.template",
        string="Document (aperçu)",
        domain="[('id', 'in', available_template_ids)]",
    )
    batch_mode = fields.Boolean(
        compute="_compute_batch_mode",
        string="Envoi multiple",
    )
    arrival_pack = fields.Boolean(
        string="Pack d'arrivée",
        help="Pré-sélection des modèles marqués « Pack d'arrivée ».",
    )
    letter_date = fields.Date(
        string="Date du document",
        default=fields.Date.context_today,
        required=True,
    )
    personalized_content = fields.Html(
        string="Aperçu personnalisé",
        sanitize_attributes=False,
    )
    has_html_content = fields.Boolean(compute="_compute_template_flags")
    has_file_attachment = fields.Boolean(compute="_compute_template_flags")
    is_file_only = fields.Boolean(compute="_compute_template_flags")
    email_subject = fields.Char(string="Objet du courriel")
    email_intro = fields.Html(
        string="Message d'accompagnement",
        sanitize_attributes=False,
        help="Court message ajouté avant le contenu dans le courriel.",
    )
    employee_email = fields.Char(string="Courriel du collaborateur", readonly=True)
    include_pdf_attachment = fields.Boolean(
        string="Joindre le PDF personnalisé",
        default=True,
        help="Génère un PDF à partir du contenu HTML personnalisé.",
    )
    include_template_file = fields.Boolean(
        string="Joindre le fichier modèle",
        default=True,
        help="Inclut le fichier PDF/DOC joint au modèle, le cas échéant.",
    )

    @api.depends("profile_id", "arrival_pack")
    def _compute_available_template_ids(self):
        Template = self.env["pe.document.template"]
        for wizard in self:
            stage = wizard.profile_id.lifecycle_stage_id
            templates = Template.search_for_stage(
                stage,
                arrival_pack_only=wizard.arrival_pack,
            )
            wizard.available_template_ids = templates

    @api.depends("template_ids")
    def _compute_batch_mode(self):
        for wizard in self:
            wizard.batch_mode = len(wizard.template_ids) > 1

    @api.depends("template_id")
    def _compute_template_flags(self):
        for wizard in self:
            template = wizard.template_id
            wizard.has_html_content = bool(template and template.has_letter_content)
            wizard.has_file_attachment = bool(template and template.has_file_attachment)
            wizard.is_file_only = bool(template and template.is_file_only)

    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        profile_id = res.get("profile_id") or self.env.context.get(
            "default_profile_id"
        )
        if not profile_id:
            return res
        profile = self.env["pe.employee.profile"].browse(profile_id)
        arrival_pack = bool(
            res.get("arrival_pack")
            or self.env.context.get("default_arrival_pack")
        )
        res["arrival_pack"] = arrival_pack
        stage = profile.lifecycle_stage_id

        if "employee_email" in fields_list:
            res["employee_email"] = self._profile_email(profile)

        templates = self.env["pe.document.template"].search_for_stage(
            stage,
            arrival_pack_only=arrival_pack,
        )
        ctx_templates = self.env.context.get("default_template_ids")
        if "template_ids" in fields_list and not res.get("template_ids"):
            if ctx_templates and ctx_templates[0][0] == 6:
                res["template_ids"] = ctx_templates
            elif arrival_pack and templates:
                res["template_ids"] = [(6, 0, templates.ids)]
            elif templates:
                default = self.env["pe.document.template"].default_template_for_stage(
                    stage,
                    arrival_pack_only=arrival_pack,
                )
                if default:
                    res["template_ids"] = [(6, 0, default.ids)]

        template_id = res.get("template_id") or self.env.context.get(
            "default_template_id"
        )
        if not template_id and res.get("template_ids"):
            template_ids = res["template_ids"][0][2]
            template_id = template_ids[0] if template_ids else False
        if template_id and "template_id" in fields_list:
            res["template_id"] = template_id

        letter_date = res.get("letter_date") or fields.Date.context_today(self)
        if template_id and "personalized_content" in fields_list:
            template = self.env["pe.document.template"].browse(template_id)
            res["personalized_content"] = template.render_document_html(
                profile,
                letter_date=letter_date,
            ) or template.render_letter_html(profile, letter_date=letter_date)

        if "email_subject" in fields_list and not res.get("email_subject"):
            if arrival_pack:
                res["email_subject"] = _("Pack d'intégration — %s") % profile.display_name
            elif template_id:
                template = self.env["pe.document.template"].browse(template_id)
                res["email_subject"] = _("%s — %s") % (template.name, profile.display_name)
            else:
                res["email_subject"] = _("Document RH — %s") % profile.display_name

        if "email_intro" in fields_list and not res.get("email_intro"):
            if template_id:
                template = self.env["pe.document.template"].browse(template_id)
                res["email_intro"] = template.default_email_intro_html(
                    profile,
                    letter_date=letter_date,
                )
            else:
                res["email_intro"] = _(
                    "<p>Bonjour,</p><p>Veuillez trouver ci-joint le(s) document(s) RH.</p>"
                )
        return res

    def _profile_email(self, profile=None):
        profile = profile or self.profile_id
        emp = profile.employee_id
        return (
            emp.work_email
            or emp.private_email
            or (profile.user_id.email if profile.user_id else "")
        )

    @api.onchange("profile_id", "arrival_pack")
    def _onchange_profile_templates(self):
        if not self.profile_id:
            return
        templates = self.available_template_ids
        if self.arrival_pack:
            self.template_ids = templates
        elif not self.template_ids:
            default = self.env["pe.document.template"].default_template_for_stage(
                self.profile_id.lifecycle_stage_id,
                arrival_pack_only=self.arrival_pack,
            )
            self.template_ids = default

    @api.onchange("profile_id")
    def _onchange_profile_id(self):
        if self.profile_id:
            self.employee_email = self._profile_email()

    @api.onchange("template_ids")
    def _onchange_template_ids(self):
        if self.template_ids and (
            not self.template_id or self.template_id not in self.template_ids
        ):
            self.template_id = self.template_ids[0]
        if len(self.template_ids) == 1:
            self.template_id = self.template_ids[0]

    @api.onchange("template_id", "letter_date", "profile_id")
    def _onchange_template_render(self):
        if not self.template_id or not self.profile_id:
            return
        content = self.template_id.render_document_html(
            self.profile_id,
            letter_date=self.letter_date,
        )
        if not content:
            content = self.template_id.render_letter_html(
                self.profile_id,
                letter_date=self.letter_date,
            )
        self.personalized_content = content
        self.email_subject = _("%s — %s") % (
            self.template_id.name,
            self.profile_id.display_name,
        )
        self.email_intro = self.template_id.default_email_intro_html(
            self.profile_id,
            letter_date=self.letter_date,
        )

    def _get_selected_templates(self):
        self.ensure_one()
        templates = self.template_ids
        if not templates and self.template_id:
            templates = self.template_id
        if not templates:
            raise UserError(_("Sélectionnez au moins un document."))
        return templates

    def _validate_templates_stage(self, templates):
        self.ensure_one()
        stage = self.profile_id.lifecycle_stage_id
        invalid = templates.filtered(
            lambda t: stage and t.stage_ids and stage not in t.stage_ids
        )
        if invalid:
            raise UserError(
                _("Ces modèles ne sont pas applicables au stade « %s » : %s")
                % (stage.name, ", ".join(invalid.mapped("name")))
            )

    def _render_content_for_template(self, template):
        content = template.render_document_html(
            self.profile_id,
            letter_date=self.letter_date,
        )
        if not content and not template.is_file_only:
            content = template.render_letter_html(
                self.profile_id,
                letter_date=self.letter_date,
            )
        return content

    def _create_employee_document(self, template, content_html, delivery_method):
        self.ensure_one()
        return self.env["pe.employee.document"].create(
            {
                "name": template.name,
                "profile_id": self.profile_id.id,
                "template_id": template.id,
                "stage_at_send_id": self.profile_id.lifecycle_stage_id.id
                if self.profile_id.lifecycle_stage_id
                else False,
                "content_html": content_html or False,
                "letter_date": self.letter_date,
                "delivery_method": delivery_method,
                "state": "sent",
                "sent_date": fields.Datetime.now(),
                "sent_by_id": self.env.user.id,
                "notes": template.description,
            }
        )

    def _generate_pdf_attachment(self, document):
        report = self.env.ref(
            "people_engine.action_report_pe_employee_letter",
            raise_if_not_found=False,
        )
        if not report:
            raise UserError(_("Le rapport d'impression est introuvable."))
        pdf_content, _report_format = self.env["ir.actions.report"]._render_qweb_pdf(
            report.report_name,
            document.ids,
        )
        attachment = self.env["ir.attachment"].create(
            {
                "name": "%s.pdf" % document.name,
                "type": "binary",
                "datas": base64.b64encode(pdf_content),
                "res_model": "pe.employee.document",
                "res_id": document.id,
                "mimetype": "application/pdf",
            }
        )
        document.attachment_id = attachment.id
        return attachment

    def _copy_template_file(self, template, document):
        if not template.attachment_id:
            return self.env["ir.attachment"]
        attachment = template.attachment_id.copy(
            {
                "name": template.attachment_id.name or template.name,
                "res_model": "pe.employee.document",
                "res_id": document.id,
            }
        )
        if not document.attachment_id:
            document.attachment_id = attachment.id
        return attachment

    def _build_document_attachments(self, document, template, content_html):
        attachments = []
        if content_html and self.include_pdf_attachment:
            attachments.append(self._generate_pdf_attachment(document))
        if template.attachment_id and self.include_template_file:
            file_att = template.attachment_id.copy(
                {
                    "name": template.attachment_id.name or template.name,
                    "res_model": "pe.employee.document",
                    "res_id": document.id,
                }
            )
            if not document.attachment_id:
                document.attachment_id = file_att.id
            attachments.append(file_att)
        return [a for a in attachments if a]

    def _log_delivery(self, documents, delivery_method, email=""):
        label = _("courriel") if delivery_method == "email" else _("impression")
        names = ", ".join(documents.mapped("name"))
        attachment_ids = [
            doc.attachment_id.id for doc in documents if doc.attachment_id
        ]
        self.profile_id.message_post(
            body=_("Document(s) « %s » (%s) : %s")
            % (names, label, email or _("PDF généré")),
            attachment_ids=attachment_ids,
        )
        self.env["pe.action.log"].log_action(
            self.profile_id,
            "document_sent",
            _("Document personnalisé (%s) : %s") % (label, names),
            actor_type="hr",
        )

    def _prepare_email_body(self, templates):
        self.ensure_one()
        body_parts = []
        intro = self.email_intro
        if intro:
            body_parts.append(intro)
        if not self.batch_mode and self.personalized_content and self.template_id:
            if self.template_id.has_letter_content or (
                self.personalized_content and not self.template_id.is_file_only
            ):
                body_parts.append(self.personalized_content)
        elif self.batch_mode:
            for template in templates:
                content = self._render_content_for_template(template)
                if content and not template.is_file_only:
                    body_parts.append(
                        "<h4>%s</h4>%s" % (template.name, content)
                    )
        if not body_parts:
            body_parts.append(
                _("<p>Bonjour,</p><p>Veuillez trouver ci-joint le(s) document(s) RH.</p>")
            )
        return "".join(body_parts)

    def action_send_email(self):
        self.ensure_one()
        templates = self._get_selected_templates()
        self._validate_templates_stage(templates)
        email = self.employee_email or self._profile_email()
        if not email:
            raise UserError(
                _("Aucune adresse e-mail pour %s.") % self.profile_id.display_name
            )

        documents = self.env["pe.employee.document"]
        mail_attachments = []

        for template in templates:
            content = self._render_content_for_template(template)
            if not content and template.is_file_only and not template.attachment_id:
                raise UserError(
                    _("Le modèle « %s » n'a ni contenu HTML ni fichier joint.")
                    % template.name
                )
            document = self._create_employee_document(template, content, "email")
            documents |= document
            mail_attachments.extend(
                self._build_document_attachments(document, template, content)
            )

        subject = self.email_subject
        if self.batch_mode and self.arrival_pack:
            subject = subject or _("Pack d'intégration — %s") % (
                self.profile_id.display_name,
            )
        elif not subject and len(templates) == 1:
            subject = _("%s — %s") % (templates.name, self.profile_id.display_name)
        subject = subject or _("Document RH — %s") % self.profile_id.display_name

        body_html = self._prepare_email_body(templates)
        self.env["mail.mail"].sudo().create(
            {
                "subject": subject,
                "body_html": body_html,
                "email_to": email,
                "attachment_ids": [(6, 0, [a.id for a in mail_attachments if a])],
                "auto_delete": True,
            }
        ).send()
        self._log_delivery(documents, "email", email=email)
        return self._return_documents_action(documents)

    def action_print(self):
        self.ensure_one()
        templates = self._get_selected_templates()
        self._validate_templates_stage(templates)
        documents = self.env["pe.employee.document"]

        for template in templates:
            content = self._render_content_for_template(template)
            if self.template_id == template and self.personalized_content:
                content = self.personalized_content
            if not content and template.is_file_only and not template.attachment_id:
                raise UserError(
                    _("Le modèle « %s » n'a ni contenu HTML ni fichier joint.")
                    % template.name
                )
            document = self._create_employee_document(template, content, "print")
            attachments = self._build_document_attachments(document, template, content)
            if not attachments and template.attachment_id:
                self._copy_template_file(template, document)
            documents |= document

        self._log_delivery(documents, "print")

        if len(documents) == 1:
            doc = documents[0]
            if doc.content_html:
                report = self.env.ref("people_engine.action_report_pe_employee_letter")
                return report.report_action(doc)
            if doc.attachment_id:
                return {
                    "type": "ir.actions.act_url",
                    "url": "/web/content/%s?download=true" % doc.attachment_id.id,
                    "target": "new",
                }

        return self._return_documents_action(documents)

    def _return_documents_action(self, documents):
        documents = documents if hasattr(documents, "ids") else documents
        if len(documents) == 1:
            return {
                "type": "ir.actions.act_window",
                "name": _("Document envoyé"),
                "res_model": "pe.employee.document",
                "view_mode": "form",
                "res_id": documents.id,
                "target": "current",
            }
        return {
            "type": "ir.actions.act_window",
            "name": _("Documents envoyés"),
            "res_model": "pe.employee.document",
            "view_mode": "list,form",
            "domain": [("id", "in", documents.ids)],
            "target": "current",
        }
