# -*- coding: utf-8 -*-
import logging

from odoo import _, api, fields, models
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


class DoorwayCampaign(models.Model):
    _inherit = "doorway.campaign"

    dial_level = fields.Integer(
        string="Vitesse d'appels",
        help="1 = lent · 2-3 = modéré · 4 = normal · 5-6 = rapide. "
        "Plus la valeur est haute, plus Sofía compose en parallèle.",
    )
    max_concurrent_calls = fields.Integer(
        string="Appels simultanés max",
        help="Nombre maximum d'appels sortants en même temps pour cet agent IA.",
    )
    dial_timeout_seconds = fields.Integer(
        string="Durée de sonnerie (sec)",
    )
    demo_calls_today = fields.Integer(
        string="Appels aujourd'hui",
        compute="_compute_demo_live_stats",
    )
    demo_answers_today = fields.Integer(
        string="Décrochés aujourd'hui",
        compute="_compute_demo_live_stats",
    )
    demo_answer_rate_today = fields.Float(
        string="Taux de décroché %",
        compute="_compute_demo_live_stats",
    )
    demo_hopper_ready = fields.Integer(
        string="Contacts en attente",
        compute="_compute_demo_live_stats",
    )
    demo_stat_total = fields.Integer(
        string="Total appels",
        compute="_compute_demo_call_breakdown",
    )
    demo_stat_human = fields.Integer(
        string="Décrochés (humain)",
        compute="_compute_demo_call_breakdown",
    )
    demo_stat_repondeur = fields.Integer(
        string="Répondeur",
        compute="_compute_demo_call_breakdown",
    )
    demo_stat_mauvais_numero = fields.Integer(
        string="Mauvais numéro",
        compute="_compute_demo_call_breakdown",
    )
    demo_stat_sans_reponse = fields.Integer(
        string="Sans réponse",
        compute="_compute_demo_call_breakdown",
    )
    demo_stat_occupe = fields.Integer(
        string="Occupé",
        compute="_compute_demo_call_breakdown",
    )
    demo_stat_qualifie = fields.Integer(
        string="Qualifiés / intéressés",
        compute="_compute_demo_call_breakdown",
    )
    demo_stat_autre = fields.Integer(
        string="Autres",
        compute="_compute_demo_call_breakdown",
    )

    company_id = fields.Many2one(
        "res.company",
        string="Société",
        index=True,
        default=lambda self: self.env.company,
        help="Société propriétaire (isolation demo call center).",
    )
    sip_trunk_id = fields.Many2one(
        "doorway.sip.trunk",
        string="Trunk SIP",
        domain="[('company_id', '=', company_id), ('active', '=', True)]",
        help="Trunk utilisé pour les appels sortants. Le DID VICIdial = nom du trunk.",
    )

    def _demo_defaults_for_user(self, user=None):
        user = user or self.env.user
        trunk = self.env["doorway.sip.trunk"].search(
            [("company_id", "=", user.company_id.id), ("active", "=", True)],
            limit=1,
        )
        agent = self.env["doorway.campaign.agent.user"].search(
            [("user_id", "=", user.id), ("active", "=", True)],
            limit=1,
        )
        return {"trunk": trunk, "agent": agent}

    @api.model_create_multi
    def create(self, vals_list):
        user = self.env.user
        if user.demo_call_center:
            defaults = self._demo_defaults_for_user(user)
            for vals in vals_list:
                vals.setdefault("company_id", user.company_id.id)
                vals.setdefault("campaign_mode", "human_agent")
                vals.setdefault("pipeline", "marketing")
                if defaults["trunk"] and not vals.get("sip_trunk_id"):
                    vals["sip_trunk_id"] = defaults["trunk"].id
                if defaults["agent"] and not vals.get("human_agent_ids"):
                    vals["human_agent_ids"] = [(4, defaults["agent"].id)]
        return super().create(vals_list)

    @api.depends("vicidial_campaign_id", "call_log_ids", "state")
    def _compute_demo_live_stats(self):
        for rec in self:
            rec.demo_calls_today = rec.total_called or 0
            rec.demo_answers_today = rec.total_answered or 0
            rec.demo_answer_rate_today = rec.answer_rate or 0.0
            rec.demo_hopper_ready = 0
            if not rec.vicidial_campaign_id:
                continue
            live = rec._vicidial_svc().get_live_stats(rec) or {}
            calls = int(live.get("calls_today") or live.get("total_calls") or 0)
            answers = int(live.get("answers_today") or live.get("amd_human") or 0)
            if calls:
                rec.demo_calls_today = calls
                rec.demo_answers_today = answers
                rec.demo_answer_rate_today = (
                    answers / calls * 100.0 if calls else 0.0
                )
            elif rec.call_log_ids:
                rec.demo_calls_today = len(rec.call_log_ids)
                rec.demo_answers_today = len(
                    rec.call_log_ids.filtered(lambda l: l.amd_result == "human")
                )
                rec.demo_answer_rate_today = rec.answer_rate
            rec.demo_hopper_ready = int(live.get("dialable_leads") or 0)

    @api.depends("vicidial_campaign_id", "call_log_ids", "call_log_ids.amd_result")
    def _compute_demo_call_breakdown(self):
        for rec in self:
            rec.demo_stat_total = 0
            rec.demo_stat_human = 0
            rec.demo_stat_repondeur = 0
            rec.demo_stat_mauvais_numero = 0
            rec.demo_stat_sans_reponse = 0
            rec.demo_stat_occupe = 0
            rec.demo_stat_qualifie = 0
            rec.demo_stat_autre = 0
            if not rec.vicidial_campaign_id and not rec.call_log_ids:
                continue
            data = rec._vicidial_svc().get_call_breakdown(rec, days=30)
            rec.demo_stat_total = data.get("total", 0)
            rec.demo_stat_human = data.get("human", 0)
            rec.demo_stat_repondeur = data.get("repondeur", 0)
            rec.demo_stat_mauvais_numero = data.get("mauvais_numero", 0)
            rec.demo_stat_sans_reponse = data.get("sans_reponse", 0)
            rec.demo_stat_occupe = data.get("occupe", 0)
            rec.demo_stat_qualifie = data.get("qualifie", 0)
            rec.demo_stat_autre = data.get("autre", 0)

    def action_demo_open_call_results(self):
        """Liste détaillée des appels avec filtres."""
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": _("Résultats des appels — %s") % self.name,
            "res_model": "doorway.call.log",
            "view_mode": "list,form",
            "domain": [("campaign_id", "=", self.id)],
            "context": {"default_campaign_id": self.id},
        }

    @api.model
    def action_demo_open_call_results_menu(self):
        camp = self.search(
            [
                ("company_id", "in", self.env.user.company_ids.ids),
                ("ia_agent_id", "!=", False),
            ],
            order="id asc",
            limit=1,
        )
        if not camp:
            raise UserError(_("Aucune campagne IA demo trouvée."))
        return camp.action_demo_open_call_results()

    def action_demo_refresh_performance(self):
        """Sync journaux + relance campagne si besoin."""
        self.ensure_one()
        if self.state in ("completed", "cancelled", "draft"):
            if self.vicidial_campaign_id:
                self.write({"state": "ready"})
                try:
                    self.action_start()
                except UserError:
                    self.write({"state": "active"})
        svc = self._vicidial_svc()
        sync = svc.sync_call_logs(self, limit=500)
        self._demo_reset_stuck_hopper()
        self.invalidate_recordset()
        breakdown = svc.get_call_breakdown(self, days=30)
        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": _("Performance actualisée"),
                "message": _(
                    "30 jours : %(total)s appels · %(human)s décrochés · "
                    "%(rep)s répondeurs · %(bad)s mauvais numéros · "
                    "%(na)s sans réponse (+%(created)s logs Odoo)"
                )
                % {
                    "total": breakdown.get("total", 0),
                    "human": breakdown.get("human", 0),
                    "rep": breakdown.get("repondeur", 0),
                    "bad": breakdown.get("mauvais_numero", 0),
                    "na": breakdown.get("sans_reponse", 0),
                    "created": sync.get("created", 0),
                },
                "type": "success",
                "sticky": True,
                "next": {
                    "type": "ir.actions.act_window",
                    "res_model": "doorway.campaign",
                    "res_id": self.id,
                    "view_mode": "form",
                    "target": "current",
                },
            },
        }

    def _demo_reset_stuck_hopper(self):
        """Remet les leads bloqués INCALL/QUEUE en READY."""
        for rec in self.filtered("vicidial_campaign_id"):
            svc = rec._vicidial_svc()
            if not svc.is_available():
                continue
            cid = rec.vicidial_campaign_id[:20]
            conn = svc._connect()
            try:
                cur = conn.cursor()
                cur.execute(
                    """
                    UPDATE vicidial_hopper
                    SET status='READY', user=''
                    WHERE campaign_id=%s AND status IN ('INCALL','QUEUE','DONE')
                    """,
                    (cid,),
                )
                cur.execute(
                    "DELETE FROM vicidial_auto_calls WHERE campaign_id=%s",
                    (cid,),
                )
                cur.execute(
                    "UPDATE vicidial_campaigns SET active='Y' WHERE campaign_id=%s",
                    (cid,),
                )
                conn.commit()
                cur.close()
            finally:
                conn.close()

    @api.model
    def action_demo_open_performance(self):
        """Ouvre la campagne demo avec panneau performance."""
        camp = self.search(
            [
                ("company_id", "in", self.env.user.company_ids.ids),
                ("ia_agent_id", "!=", False),
            ],
            order="id asc",
            limit=1,
        )
        if not camp:
            raise UserError(_("Aucune campagne IA demo trouvée."))
        return {
            "type": "ir.actions.act_window",
            "name": _("Performance — %s") % (camp.ia_agent_id.name or camp.name),
            "res_model": "doorway.campaign",
            "res_id": camp.id,
            "view_mode": "form",
            "target": "current",
        }

    def write(self, vals):
        res = super().write(vals)
        if self.env.user.demo_call_center and any(
            key in vals
            for key in ("dial_level", "max_concurrent_calls", "dial_timeout_seconds")
        ):
            for rec in self.filtered("vicidial_campaign_id"):
                try:
                    rec._demo_apply_dial_speed(quiet=True)
                except Exception:  # noqa: BLE001
                    _logger.exception("demo dial speed sync failed for %s", rec.id)
        return res

    def _demo_apply_dial_speed(self, quiet=False):
        """Pousse vitesse / simultané vers VICIdial (ABD_DEMO, lignes Sofía)."""
        self.ensure_one()
        if not self.vicidial_campaign_id:
            if quiet:
                return False
            raise UserError(
                _(
                    "La campagne n'est pas encore reliée à la téléphonie. "
                    "Cliquez sur « Sync appels » puis réessayez."
                )
            )
        level = int(self.dial_level or 1)
        lines = min(max(int(self.max_concurrent_calls or 8), 1), 20)
        svc = self._vicidial_svc()
        if not svc.is_available():
            if quiet:
                return False
            raise UserError(_("VICIdial indisponible."))
        svc.update_campaign_dial_level(self.vicidial_campaign_id, level)
        conn = svc._connect()
        try:
            cur = conn.cursor()
            cur.execute(
                """
                UPDATE vicidial_campaigns
                SET auto_dial_level = %s, hopper_level = %s, dial_timeout = %s
                WHERE campaign_id = %s
                """,
                (
                    str(level),
                    max(lines * 50, 200),
                    int(self.dial_timeout_seconds or 45),
                    self.vicidial_campaign_id[:20],
                ),
            )
            cur.execute(
                """
                UPDATE vicidial_remote_agents
                SET number_of_lines = %s, status = 'ACTIVE', on_hook_agent = 'Y'
                WHERE campaign_id = %s
                """,
                (lines, self.vicidial_campaign_id[:20]),
            )
            conn.commit()
            cur.close()
        finally:
            conn.close()
        if not quiet:
            self.message_post(
                body=_(
                    "Vitesse d'appels mise à jour : niveau <b>%(level)s</b>, "
                    "<b>%(lines)s</b> appels simultanés."
                )
                % {"level": level, "lines": lines},
                message_type="notification",
            )
        return True

    def action_demo_apply_dial_speed(self):
        self.ensure_one()
        self._demo_apply_dial_speed()
        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": _("Vitesse appliquée"),
                "message": _(
                    "Vitesse %(level)s · %(lines)s appels simultanés actifs sur VICIdial."
                )
                % {
                    "level": self.dial_level,
                    "lines": self.max_concurrent_calls,
                },
                "type": "success",
                "sticky": False,
            },
        }

    @api.model
    def action_demo_open_dial_speed(self):
        """Ouvre la campagne IA demo pour régler la vitesse d'appels."""
        if not self.env.user.demo_call_center:
            raise UserError(_("Réservé aux comptes Demo Call Center."))
        camp = self.search(
            [
                ("company_id", "in", self.env.user.company_ids.ids),
                ("ia_agent_id", "!=", False),
                ("vicidial_campaign_id", "!=", False),
            ],
            order="id asc",
            limit=1,
        )
        if not camp:
            camp = self.search(
                [("company_id", "in", self.env.user.company_ids.ids)],
                order="id asc",
                limit=1,
            )
        if not camp:
            raise UserError(_("Aucune campagne trouvée."))
        return {
            "type": "ir.actions.act_window",
            "name": _("Vitesse d'appels — %s") % (camp.ia_agent_id.name or camp.name),
            "res_model": "doorway.campaign",
            "res_id": camp.id,
            "view_mode": "form",
            "target": "current",
        }

    def _link_demo_vicidial_agent(self):
        from odoo.addons.doorway_demo_call_center.services.demo_provisioning import (
            DemoCallCenterProvisioning,
        )

        for rec in self:
            if not rec.vicidial_campaign_id:
                continue
            agent = self.env["doorway.campaign.agent.user"].search(
                [
                    ("user_id", "in", rec.human_agent_ids.user_id.ids or [self.env.user.id]),
                    ("active", "=", True),
                ],
                limit=1,
            )
            if not agent:
                continue
            DemoCallCenterProvisioning(self.env)._link_vicidial_campaign(
                agent.vicidial_user, rec.vicidial_campaign_id
            )
            if agent not in rec.human_agent_ids:
                rec.write({"human_agent_ids": [(4, agent.id)]})

    def _apply_demo_vicidial_trunk(self):
        for rec in self.filtered("vicidial_campaign_id"):
            trunk_name = rec.sip_trunk_id.name if rec.sip_trunk_id else False
            if trunk_name:
                rec._vicidial_svc().set_campaign_cid(
                    rec.vicidial_campaign_id, trunk_name
                )

    def _create_vicidial_campaign(self):
        super()._create_vicidial_campaign()
        self._apply_demo_vicidial_trunk()
        if self.env.user.demo_call_center:
            self._link_demo_vicidial_agent()

    def action_sync_vicidial(self):
        res = super().action_sync_vicidial()
        self._apply_demo_vicidial_trunk()
        if self.env.user.demo_call_center:
            self._link_demo_vicidial_agent()
        return res

    def action_open_import_wizard(self):
        self.ensure_one()
        user = self.env.user
        if user.demo_call_center and self.company_id not in user.company_ids:
            raise UserError(_("Cette campagne n'appartient pas à votre espace demo."))
        return super().action_open_import_wizard()

    def action_demo_configure_ia_agent(self):
        """Ouvre le wizard de modification de l'agent IA lié à la campagne."""
        self.ensure_one()
        if not self.ia_agent_id:
            return self.env["doorway.agent.profile"].action_demo_open_my_agent()
        if self.company_id not in self.env.user.company_ids:
            raise UserError(_("Cet agent n'appartient pas à votre espace demo."))
        return self.ia_agent_id.action_open_edit_wizard()

    def action_demo_test_ia_agent(self):
        """Appel test pour écouter l'agent IA de la campagne."""
        self.ensure_one()
        agent = self.ia_agent_id
        if not agent:
            agents = self.env["doorway.agent.profile"].search(
                self.env["doorway.agent.profile"]._demo_agent_domain(), limit=1
            )
            agent = agents[:1]
        if not agent:
            raise UserError(_("Aucun agent IA configuré pour cette campagne."))
        return agent.action_open_test_wizard()
