# -*- coding: utf-8 -*-
from odoo import api, fields, models

IA_PROFILE_MODEL = "doorway.agent.profile"


class CoinsAssigneeMixin(models.AbstractModel):
    """Assignation unique : humain (res.users) ou agent IA (doorway.agent.profile).

    Ne crée pas de res.users pour les IA. Les KPI d'activité quotidienne
    restent sur res.users (connexions humaines).
    """

    _name = "coins.assignee.mixin"
    _description = "Assigné commercial humain ou agent IA"

    coins_commercial_assigne = fields.Many2one(
        "res.users",
        string="Commercial assigné",
        tracking=True,
        index=True,
        help="Commercial humain (res.users). Les agents IA vont sur coins_agent_ia_id.",
    )
    coins_agent_ia_id = fields.Many2one(
        IA_PROFILE_MODEL,
        string="Agent IA",
        tracking=True,
        index=True,
        help="Profil IA doorway.agent.profile — ownership / routage, pas un login.",
    )
    assignee_kind = fields.Selection(
        [
            ("humain", "Humain"),
            ("ia", "IA"),
        ],
        string="Type d'assigné",
        default="humain",
        required=True,
        index=True,
    )
    coins_assignee_display = fields.Char(
        string="Assigné",
        compute="_compute_coins_assignee_display",
        store=True,
        index=True,
    )

    @api.depends(
        "assignee_kind",
        "coins_commercial_assigne",
        "coins_commercial_assigne.name",
        "coins_agent_ia_id",
        "coins_agent_ia_id.name",
    )
    def _compute_coins_assignee_display(self):
        for rec in self:
            if rec.assignee_kind == "ia" and rec.coins_agent_ia_id:
                rec.coins_assignee_display = "IA · %s" % rec.coins_agent_ia_id.name
            elif rec.coins_commercial_assigne:
                rec.coins_assignee_display = rec.coins_commercial_assigne.name
            else:
                rec.coins_assignee_display = False

    @api.model
    def _coins_normalize_assignee_vals(self, vals):
        if not vals:
            return vals
        if vals.get("coins_agent_ia_id"):
            vals["assignee_kind"] = "ia"
            vals["coins_commercial_assigne"] = False
        elif vals.get("coins_commercial_assigne"):
            vals["assignee_kind"] = "humain"
            vals["coins_agent_ia_id"] = False
        elif vals.get("assignee_kind") == "ia":
            vals["coins_commercial_assigne"] = False
        elif vals.get("assignee_kind") == "humain":
            vals["coins_agent_ia_id"] = False
        return vals

    @api.onchange("assignee_kind")
    def _onchange_assignee_kind(self):
        if self.assignee_kind == "humain":
            self.coins_agent_ia_id = False
        elif self.assignee_kind == "ia":
            self.coins_commercial_assigne = False

    @api.onchange("coins_commercial_assigne")
    def _onchange_coins_commercial_assigne(self):
        if self.coins_commercial_assigne:
            self.assignee_kind = "humain"
            self.coins_agent_ia_id = False

    @api.onchange("coins_agent_ia_id")
    def _onchange_coins_agent_ia_id(self):
        if self.coins_agent_ia_id:
            self.assignee_kind = "ia"
            self.coins_commercial_assigne = False

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            self._coins_normalize_assignee_vals(vals)
        return super().create(vals_list)

    def write(self, vals):
        self._coins_normalize_assignee_vals(vals)
        return super().write(vals)
