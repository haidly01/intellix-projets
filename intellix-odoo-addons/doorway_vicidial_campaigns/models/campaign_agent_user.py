# -*- coding: utf-8 -*-
import re

from odoo import _, api, fields, models


class DoorwayCampaignAgentUser(models.Model):
    _name = "doorway.campaign.agent.user"
    _description = "Agent humain campagne VICIdial"
    _rec_name = "vicidial_user"

    user_id = fields.Many2one("res.users", string="Utilisateur Odoo", required=True)
    vicidial_user = fields.Char(string="Login VICIdial", required=True)
    full_name = fields.Char()
    user_group = fields.Char(default="AGENTS")
    user_level = fields.Integer(default=1)
    active = fields.Boolean(default=True)
    vicidial_qualification_active = fields.Boolean(
        string="Qualification CRM temps réel",
        default=True,
        help="Ouvre automatiquement le lead CRM pendant les appels VICIdial.",
    )
    vicidial_crm_team_id = fields.Many2one(
        "crm.team",
        string="Pipeline CRM VICIdial",
    )
    vicidial_crm_stage_id = fields.Many2one(
        "crm.stage",
        string="Étape initiale VICIdial",
        domain="[('team_ids', 'in', vicidial_crm_team_id)]",
    )
    callback_phone = fields.Char(
        string="Téléphone rappel (cellulaire)",
        help="Numéro mobile appelé au démarrage de session (format 5145551234). "
        "Si vide, le mobile/téléphone du contact Odoo est utilisé.",
    )
    call_log_ids = fields.One2many(
        "doorway.call.log", "human_agent_id", string="Enregistrements"
    )
    call_log_count = fields.Integer(compute="_compute_call_log_count")

    _sql_constraints = [
        (
            "vicidial_user_uniq",
            "unique(vicidial_user)",
            "Ce login VICIdial existe déjà.",
        ),
    ]

    def _compute_call_log_count(self):
        Log = self.env["doorway.call.log"]
        for agent in self:
            agent.call_log_count = Log.search_count(
                [("human_agent_id", "=", agent.id)]
            )

    def action_view_call_logs(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": _("Enregistrements — %s") % (self.full_name or self.vicidial_user),
            "res_model": "doorway.call.log",
            "view_mode": "list,form",
            "domain": [("human_agent_id", "=", self.id)],
            "context": {"default_human_agent_id": self.id},
        }

    def action_my_call_recordings(self):
        """Action menu : enregistrements de l'agent humain connecté."""
        agent = self.search([("user_id", "=", self.env.user.id)], limit=1)
        if not agent:
            return {
                "type": "ir.actions.act_window",
                "name": _("Mes enregistrements"),
                "res_model": "doorway.call.log",
                "view_mode": "list,form",
                "domain": [("id", "=", 0)],
            }
        return agent.action_view_call_logs()

    def get_callback_phone(self):
        self.ensure_one()
        raw = (self.callback_phone or "").strip()
        if not raw:
            partner = self.user_id.partner_id
            candidates = [partner.phone]
            if "mobile" in partner._fields:
                candidates.insert(0, partner.mobile)
            for val in candidates:
                if val and len(re.sub(r"\D", "", val)) >= 10:
                    raw = val.strip()
                    break
        digits = re.sub(r"\D", "", raw)
        if len(digits) == 10:
            return digits
        if len(digits) == 11 and digits.startswith("1"):
            return digits[1:]
        return digits if len(digits) >= 10 else ""

    @api.model
    def _vicidial_login_for_user(self, user, exclude_agent_id=None):
        """Login VICIdial stable pour un utilisateur Odoo (profil PE ou agent existant)."""
        self = self.sudo()
        domain = [("user_id", "=", user.id)]
        if exclude_agent_id:
            domain.append(("id", "!=", exclude_agent_id))
        existing = self.search(domain, limit=1)
        if existing:
            return existing.vicidial_user

        if "pe.employee.profile" in self.env.registry:
            profile = self.env["pe.employee.profile"].sudo().search(
                [("user_id", "=", user.id)], limit=1
            )
            if profile and profile.vicidial_user:
                login = (profile.vicidial_user or "").strip()[:20]
                if login and not self.search_count([("vicidial_user", "=", login)]):
                    return login

        base = re.sub(
            r"[^a-zA-Z0-9_]",
            "",
            (user.login or user.name or "agent").split("@")[0],
        )[:16]
        login = base or "agent"
        n = 1
        while self.search_count([("vicidial_user", "=", login)]):
            login = "%s%d" % (base[:14], n)
            n += 1
        return login

    def action_sync_vicidial(self):
        from odoo.addons.doorway_vicidial_campaigns.services.vicidial_service import (
            VicidialService,
        )

        svc = VicidialService(self.env)
        for rec in self:
            svc.sync_user(
                rec.vicidial_user,
                rec.full_name or rec.user_id.name,
                rec.user_group,
                rec.user_level,
                rec.active,
            )
        return True
