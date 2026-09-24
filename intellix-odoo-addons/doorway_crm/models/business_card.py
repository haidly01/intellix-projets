# -*- coding: utf-8 -*-
import logging

from odoo import _, api, models
from odoo.exceptions import UserError

from odoo.addons.doorway_crm.services.business_card_service import BusinessCardService

_logger = logging.getLogger(__name__)


class DoorwayBusinessCard(models.AbstractModel):
    _name = "doorway.business.card"
    _description = "Scan carte de visite → contact CRM"

    @api.model
    def parse_business_card(self, datas, mimetype="image/jpeg"):
        parsed, message = BusinessCardService(self.env).parse_image(datas, mimetype)
        if not parsed:
            return {"ok": False, "error": message, "fields": {}}
        return {"ok": True, "message": message, "fields": parsed}

    @api.model
    def _attach_scan_image(self, record, datas, mimetype, name="carte_visite.jpg"):
        if not record or not datas:
            return
        raw = datas.split(",", 1)[-1] if str(datas).startswith("data:") else datas
        self.env["ir.attachment"].sudo().create(
            {
                "name": name,
                "type": "binary",
                "datas": raw,
                "mimetype": mimetype or "image/jpeg",
                "res_model": record._name,
                "res_id": record.id,
            }
        )

    @api.model
    def _find_existing_partner(self, fields_data):
        Partner = self.env["res.partner"].sudo()
        email = (fields_data.get("email") or "").strip()
        if email:
            found = Partner.search([("email", "=ilike", email)], limit=1)
            if found:
                return found
        for key in ("phone", "mobile"):
            phone = fields_data.get(key)
            if not phone:
                continue
            digits = BusinessCardService.phone_digits(phone)
            if len(digits) < 7:
                continue
            tail = digits[-10:]
            domain = [("phone", "ilike", tail)]
            if "mobile" in Partner._fields:
                domain = ["|", ("phone", "ilike", tail), ("mobile", "ilike", tail)]
            candidates = Partner.search(domain, limit=1)
            if candidates:
                return candidates
        return Partner.browse()

    @api.model
    def _partner_vals_from_scan(self, fields_data):
        name = fields_data.get("full_name") or fields_data.get("company") or _("Contact scanné")
        company = (fields_data.get("company") or "").strip()
        is_company = bool(company) and not fields_data.get("full_name")
        vals = {
            "name": company if is_company else name,
            "email": fields_data.get("email") or False,
            "phone": fields_data.get("phone") or fields_data.get("mobile") or False,
            "street": fields_data.get("street") or False,
            "city": fields_data.get("city") or False,
            "zip": fields_data.get("zip") or False,
            "website": fields_data.get("website") or False,
            "function": fields_data.get("job_title") or False,
            "comment": _("Contact créé depuis scan carte de visite."),
        }
        country_code = (fields_data.get("country_code") or "").upper()
        if country_code:
            country = self.env["res.country"].search([("code", "=", country_code)], limit=1)
            if country:
                vals["country_id"] = country.id
        if company and not is_company:
            vals["parent_id"] = self._find_or_create_company(company, fields_data).id
        return vals

    @api.model
    def _find_or_create_company(self, company_name, fields_data):
        Partner = self.env["res.partner"].sudo()
        existing = Partner.search(
            [("name", "=ilike", company_name), ("is_company", "=", True)],
            limit=1,
        )
        if existing:
            return existing
        return Partner.create(
            {
                "name": company_name,
                "is_company": True,
                "phone": fields_data.get("phone") or False,
                "email": fields_data.get("email") or False,
                "website": fields_data.get("website") or False,
                "city": fields_data.get("city") or False,
            }
        )

    @api.model
    def _lead_vals_from_scan(self, fields_data, team_id=None):
        company = (fields_data.get("company") or "").strip()
        contact_name = fields_data.get("full_name") or company or _("Contact scanné")
        opp_name = company or contact_name
        vals = {
            "name": opp_name,
            "type": "opportunity",
            "contact_name": contact_name,
            "partner_name": company or False,
            "phone": fields_data.get("phone") or fields_data.get("mobile") or False,
            "email_from": fields_data.get("email") or False,
            "city": fields_data.get("city") or False,
            "street": fields_data.get("street") or False,
            "website": fields_data.get("website") or False,
            "description": _("Opportunité créée depuis scan carte de visite."),
        }
        source = self.env["utm.source"].sudo().search([("name", "=ilike", "Carte de visite")], limit=1)
        if not source:
            source = self.env["utm.source"].sudo().create({"name": "Carte de visite"})
        vals["source_id"] = source.id
        if team_id:
            vals["team_id"] = team_id
        partner = self._find_existing_partner(fields_data)
        if partner and not partner.is_company:
            vals["partner_id"] = partner.parent_id.id if partner.parent_id else partner.id
        elif company:
            vals["partner_id"] = self._find_or_create_company(company, fields_data).id
        return vals

    @api.model
    def create_from_business_card(
        self,
        datas,
        mimetype="image/jpeg",
        target_model="crm.lead",
        record_id=None,
        fields_data=None,
        team_id=None,
    ):
        """Crée ou met à jour un contact / opportunité à partir d'une carte scannée."""
        if fields_data:
            parsed = fields_data
        else:
            parsed, err = BusinessCardService(self.env).parse_image(datas, mimetype)
            if not parsed:
                raise UserError(err or _("Analyse impossible."))
        target_model = (target_model or "crm.lead").strip()
        attachment_src = datas
        if record_id:
            record = self.env[target_model].browse(int(record_id)).exists()
            if not record:
                raise UserError(_("Enregistrement introuvable."))
            if target_model == "crm.lead":
                record.write(self._lead_update_vals(parsed))
            elif target_model == "res.partner":
                record.write(self._partner_vals_from_scan(parsed))
            else:
                raise UserError(_("Modèle non supporté."))
            self._attach_scan_image(record, attachment_src, mimetype)
            return {
                "ok": True,
                "record_id": record.id,
                "model": target_model,
                "name": record.display_name,
            }
        if target_model == "res.partner":
            existing = self._find_existing_partner(parsed)
            if existing:
                existing.write(self._partner_vals_from_scan(parsed))
                self._attach_scan_image(existing, attachment_src, mimetype)
                return {
                    "ok": True,
                    "record_id": existing.id,
                    "model": "res.partner",
                    "name": existing.display_name,
                    "updated": True,
                }
            partner = self.env["res.partner"].create(self._partner_vals_from_scan(parsed))
            self._attach_scan_image(partner, attachment_src, mimetype)
            return {
                "ok": True,
                "record_id": partner.id,
                "model": "res.partner",
                "name": partner.display_name,
            }
        lead = self.env["crm.lead"].with_context(
            doorway_skip_email_unique_check=True
        ).create(self._lead_vals_from_scan(parsed, team_id=team_id))
        self._attach_scan_image(lead, attachment_src, mimetype)
        return {
            "ok": True,
            "record_id": lead.id,
            "model": "crm.lead",
            "name": lead.display_name,
        }

    @api.model
    def _lead_update_vals(self, fields_data):
        vals = {}
        mapping = {
            "contact_name": "full_name",
            "partner_name": "company",
            "phone": "phone",
            "email_from": "email",
            "city": "city",
            "street": "street",
            "website": "website",
        }
        for odoo_key, scan_key in mapping.items():
            val = fields_data.get(scan_key)
            if val:
                if odoo_key == "phone" and not val:
                    val = fields_data.get("mobile")
                vals[odoo_key] = val
        if fields_data.get("mobile") and not vals.get("phone"):
            vals["phone"] = fields_data["mobile"]
        if fields_data.get("company") and not vals.get("name"):
            vals["name"] = fields_data["company"]
        return vals

    @api.model
    def action_open_scan_client(self, target_model="crm.lead", record_id=None, team_id=None):
        return {
            "type": "ir.actions.client",
            "tag": "doorway_business_card_scan",
            "name": _("Scanner carte de visite"),
            "params": {
                "targetModel": target_model,
                "recordId": record_id,
                "teamId": team_id,
            },
        }
