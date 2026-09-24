# -*- coding: utf-8 -*-
from odoo import models
from odoo.osv import expression
from odoo.tools.safe_eval import safe_eval


class IrActionsActWindow(models.Model):
    _inherit = "ir.actions.act_window"

    def _doorway_pipeline_action_ids(self):
        """Actions fenêtre des pipelines Doorway (menus + switcher)."""
        return set(
            self.env["ir.model.data"]
            .sudo()
            .search(
                [
                    ("module", "=", "renovation_conciergerie"),
                    ("name", "=like", "doorway_action_pipeline_%"),
                    ("model", "=", "ir.actions.act_window"),
                ]
            )
            .mapped("res_id")
        )

    def _doorway_parse_action_context(self, ctx, uid=None):
        if not ctx:
            return {}
        if isinstance(ctx, dict):
            return dict(ctx)
        return safe_eval(ctx, {"uid": uid if uid is not None else self.env.uid})

    def _doorway_apply_peer_sales_to_action_vals(self, action_vals):
        if action_vals.get("res_model") != "crm.lead":
            return action_vals
        user = self.env.user
        ctx = self._doorway_parse_action_context(
            action_vals.get("context"), uid=user.id
        )
        # Karine (et admin CRM global) : jamais le filtre « My Pipeline ».
        if user._doorway_is_crm_superuser():
            ctx.pop("search_default_assigned_to_me", None)
            action_vals["context"] = ctx
            return action_vals
        if not user._doorway_is_crm_peer_sales_user():
            action_vals["context"] = ctx
            return action_vals
        peer_domain = self.env["crm.team"]._doorway_peer_sales_lead_domain()
        if not peer_domain:
            action_vals["context"] = ctx
            return action_vals
        base_domain = action_vals.get("domain") or []
        if isinstance(base_domain, str):
            base_domain = safe_eval(base_domain, {"uid": user.id})
        action_vals["domain"] = expression.AND([base_domain, peer_domain])
        ctx["search_default_assigned_to_me"] = 1
        action_vals["context"] = ctx
        return action_vals

    def _get_action_dict(self):
        result = super()._get_action_dict()
        if result.get("res_model") == "crm.lead":
            result = self._doorway_apply_peer_sales_to_action_vals(result)
        return result

    def read(self, fields=None, load="_classic_read"):
        result = super().read(fields, load=load)
        for action in result:
            record = self.browse(action["id"])
            if record.res_model == "crm.lead":
                action.update(record._doorway_apply_peer_sales_to_action_vals(action))
        return result
