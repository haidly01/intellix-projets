# -*- coding: utf-8 -*-
import logging

from odoo import _, api, fields, models
from odoo.exceptions import UserError

from odoo.addons.doorway_vicidial_campaigns.services.file_importer import FileImporter

_logger = logging.getLogger(__name__)


class DoorwayFileImportWizard(models.TransientModel):
    _name = "doorway.file.import.wizard"
    _description = "Import contacts campagne"

    campaign_id = fields.Many2one("doorway.campaign", required=True)
    data_file = fields.Binary(required=True)
    filename = fields.Char()
    inject_vicidial = fields.Boolean(string="Injecter dans VICIdial", default=True)

    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        campaign_id = self.env.context.get("default_campaign_id")
        if campaign_id and "inject_vicidial" in fields_list:
            campaign = self.env["doorway.campaign"].browse(campaign_id)
            res["inject_vicidial"] = bool(campaign.vicidial_campaign_id)
        return res

    def action_import(self):
        self.ensure_one()
        importer = FileImporter()
        country = self.campaign_id._phone_import_country()
        try:
            rows = importer.parse(
                self.data_file, self.filename or "", default_country=country
            )
        except ValueError as exc:
            raise UserError(str(exc)) from exc
        if not rows:
            raise UserError(_("Aucun contact valide."))

        Contact = self.env["doorway.campaign.contact"]
        contacts = Contact.create(
            [
                {
                    "campaign_id": self.campaign_id.id,
                    "phone_number": r["phone_number"],
                    "first_name": r.get("first_name"),
                    "last_name": r.get("last_name"),
                    "email": r.get("email"),
                    "vendor_code": r.get("vendor_lead_code") or r.get("vendor_code"),
                }
                for r in rows
            ]
        )

        vicidial_warning = None
        if self.inject_vicidial:
            try:
                if not self.campaign_id.vicidial_campaign_id:
                    self.campaign_id._create_vicidial_campaign()
                from odoo.addons.doorway_vicidial_campaigns.services.vicidial_service import (
                    VicidialService,
                )

                VicidialService(self.env).inject_campaign_contacts(
                    self.campaign_id, contacts
                )
            except UserError as exc:
                vicidial_warning = str(exc)
            except Exception as exc:  # noqa: BLE001
                _logger.exception("inject_campaign_contacts failed")
                vicidial_warning = _("Injection VICIdial impossible : %s") % exc

        if vicidial_warning:
            self.campaign_id.message_post(
                body=_(
                    "%(count)s contact(s) importé(s) dans Odoo, mais l'injection VICIdial "
                    "a échoué : %(error)s"
                )
                % {"count": len(contacts), "error": vicidial_warning},
                message_type="notification",
            )

        action = {
            "type": "ir.actions.act_window",
            "res_model": "doorway.campaign",
            "res_id": self.campaign_id.id,
            "view_mode": "form",
            "target": "current",
        }
        if vicidial_warning:
            return {
                "type": "ir.actions.client",
                "tag": "display_notification",
                "params": {
                    "title": _("Import partiel"),
                    "message": _(
                        "%(count)s contact(s) enregistré(s). VICIdial : %(error)s"
                    )
                    % {"count": len(contacts), "error": vicidial_warning},
                    "type": "warning",
                    "sticky": True,
                    "next": action,
                },
            }
        return action

    def action_cleanup_list(self):
        self.ensure_one()
        return self.campaign_id.action_cleanup_list()
