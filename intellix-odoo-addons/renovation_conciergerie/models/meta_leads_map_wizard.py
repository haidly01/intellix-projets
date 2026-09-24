# -*- coding: utf-8 -*-
import json

from odoo import _, api, fields, models
from odoo.exceptions import UserError

_META_LEADS_MAP_ICP = "renovation_conciergerie.meta_leads_global_page_map"


class RenovationMetaLeadsMapEditor(models.TransientModel):
    _name = "renovation.meta.leads.map.editor"
    _description = "Éditeur mapping Meta Lead Ads (JSON)"

    map_json = fields.Text(
        string="Mapping global (JSON)",
        required=True,
        help="Structure page_id → pipeline, webhook n8n, agents. Voir doc/META_LEADS_GLOBAL_MAP.md",
    )

    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        raw = (
            self.env["ir.config_parameter"]
            .sudo()
            .get_param(_META_LEADS_MAP_ICP)
            or ""
        )
        if raw.strip():
            try:
                parsed = json.loads(raw)
                res["map_json"] = json.dumps(parsed, ensure_ascii=False, indent=2)
            except json.JSONDecodeError:
                res["map_json"] = raw
        else:
            from odoo.addons.renovation_conciergerie.models.meta_leads_routing import (
                DEFAULT_META_LEADS_GLOBAL_MAP,
            )

            res["map_json"] = json.dumps(
                DEFAULT_META_LEADS_GLOBAL_MAP, ensure_ascii=False, indent=2
            )
        return res

    def _validate_json(self):
        self.ensure_one()
        try:
            data = json.loads(self.map_json or "{}")
        except json.JSONDecodeError as err:
            raise UserError(_("JSON invalide : %s") % err) from err
        if not isinstance(data, dict):
            raise UserError(_("Le mapping doit être un objet JSON (racine {})."))
        return data

    def action_save(self):
        self.ensure_one()
        data = self._validate_json()
        self.env["ir.config_parameter"].sudo().set_param(
            _META_LEADS_MAP_ICP,
            json.dumps(data, ensure_ascii=False, indent=2),
        )
        self.env["renovation.meta.leads.routing"].sudo()._ensure_meta_leads_global_map()
        return {"type": "ir.actions.act_window_close"}

    def action_reset_default(self):
        self.ensure_one()
        from odoo.addons.renovation_conciergerie.models.meta_leads_routing import (
            DEFAULT_META_LEADS_GLOBAL_MAP,
        )

        self.map_json = json.dumps(
            DEFAULT_META_LEADS_GLOBAL_MAP, ensure_ascii=False, indent=2
        )
        return {
            "type": "ir.actions.act_window",
            "res_model": self._name,
            "res_id": self.id,
            "view_mode": "form",
            "target": "new",
        }
