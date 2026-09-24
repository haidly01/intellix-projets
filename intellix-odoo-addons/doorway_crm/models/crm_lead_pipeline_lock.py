# -*- coding: utf-8 -*-
"""Empêche les fiches de sauter d’un pipeline à l’autre.

Odoo recalcule team_id dès que l’assigné n’est pas membre de l’équipe
(« Leila sur une fiche CQ → Réno Immobilier »). Un hook CQ vidait aussi
team_id au -u, et les fiches retombaient sur l’équipe par défaut de
la personne (Zakaria → Coins Marocain, Leila → Réno Immobilier).
"""
from odoo import api, models

LOCKED_TEAM_XMLIDS = (
    "coins_marocain_partenariats.crm_team_coins_marocain",
    "coins_marocain_partenariats.crm_team_coins_voyageurs",
    "coins_quebec.crm_team_cq_partenariats",
    "coins_quebec.crm_team_cq_voyageurs",
    "doorway_hiba_qualif.crm_team_coins_quebec",
    "reno_immobilier.crm_team_reno_immobilier",
    "renovation_conciergerie.crm_team_marketing",
    "renovation_conciergerie.crm_team_renovation",
    "renovation_conciergerie.crm_team_immobilier",
)


class CrmLeadPipelineLock(models.Model):
    _inherit = "crm.lead"

    def _doorway_locked_team_ids(self):
        ids = []
        for xmlid in LOCKED_TEAM_XMLIDS:
            team = self.env.ref(xmlid, raise_if_not_found=False)
            if team:
                ids.append(team.id)
        return ids

    def _doorway_cq_partenariats_team(self):
        return self.env.ref(
            "coins_quebec.crm_team_cq_partenariats", raise_if_not_found=False
        )

    def _doorway_cq_nouveau_stage(self, team):
        if not team:
            return self.env["crm.stage"]
        return self.env["crm.stage"].sudo().search(
            [("name", "=", "Nouveau"), ("team_ids", "in", [team.id])],
            limit=1,
        )

    def _compute_team_id(self):
        locked = set(self._doorway_locked_team_ids())
        to_super = self.browse()
        for lead in self:
            if lead.team_id and lead.team_id.id in locked:
                continue
            to_super |= lead
        if to_super:
            super(CrmLeadPipelineLock, to_super)._compute_team_id()

    def write(self, vals):
        if "team_id" in vals and not vals.get("team_id"):
            locked = set(self._doorway_locked_team_ids())
            if any(lead.team_id.id in locked for lead in self):
                vals = dict(vals)
                del vals["team_id"]
                if not vals:
                    return True
        return super().write(vals)

    @api.model_create_multi
    def create(self, vals_list):
        leads = super().create(vals_list)
        self._doorway_reroute_cq_partenaires(leads)
        return leads

    def _doorway_reroute_cq_partenaires(self, leads):
        """Fiches déjà dans coins.quebec.partenariat : pas Réno / pas CM."""
        if "coins.quebec.partenariat" not in self.env:
            return
        team_cq = self._doorway_cq_partenariats_team()
        if not team_cq:
            return
        team_cm = self.env.ref(
            "coins_marocain_partenariats.crm_team_coins_marocain",
            raise_if_not_found=False,
        )
        team_reno = self.env.ref(
            "reno_immobilier.crm_team_reno_immobilier", raise_if_not_found=False
        )
        wrong = set()
        if team_cm:
            wrong.add(team_cm.id)
        if team_reno:
            wrong.add(team_reno.id)
        names = {
            (n or "").strip().lower()
            for n in self.env["coins.quebec.partenariat"]
            .sudo()
            .with_context(active_test=False)
            .search([])
            .mapped("name")
            if n
        }
        if not names:
            return
        stage = self._doorway_cq_nouveau_stage(team_cq)
        ctx = {
            "tracking_disable": True,
            "mail_notrack": True,
            "mail_create_nolog": True,
        }
        for lead in leads:
            key = (lead.name or "").strip().lower()
            if key not in names:
                continue
            if lead.team_id.id == team_cq.id:
                continue
            if lead.team_id.id not in wrong and lead.team_id:
                continue
            vals = {"team_id": team_cq.id}
            if stage:
                vals["stage_id"] = stage.id
            lead.with_context(**ctx).sudo().write(vals)
