# -*- coding: utf-8 -*-
"""KPI équipe partenariats — agrégats sur crm.lead + coins.entente existants."""
from datetime import timedelta
from collections import defaultdict

from odoo import api, fields, models


class CoinsPartenariatKpiDaily(models.Model):
    _name = "coins.partenariat.kpi.daily"
    _description = "Activité quotidienne partenariats (appels / conversations)"
    _order = "date desc, user_id"
    _rec_name = "display_name"

    date = fields.Date(
        string="Date",
        required=True,
        default=fields.Date.context_today,
        index=True,
    )
    user_id = fields.Many2one(
        "res.users",
        string="Commercial",
        required=True,
        default=lambda self: self.env.user,
        index=True,
    )
    appels_composes = fields.Integer(
        string="Appels composés",
        help="Volume d'appels composés ce jour. Distinct des conversations.",
    )
    conversations_completees = fields.Integer(
        string="Conversations complétées",
        help="Conversations abouties ce jour. Ne jamais fusionner avec les appels.",
    )
    notes = fields.Char(string="Note")
    display_name = fields.Char(compute="_compute_display_name")

    _sql_constraints = [
        (
            "uniq_user_date",
            "unique(date, user_id)",
            "Une seule ligne d'activité par commercial et par jour.",
        )
    ]

    @api.depends("date", "user_id")
    def _compute_display_name(self):
        for rec in self:
            rec.display_name = "%s — %s" % (
                rec.date or "?",
                rec.user_id.name or "?",
            )

    def _period_bounds(self, period):
        today = fields.Date.context_today(self)
        if period == "week":
            return today - timedelta(days=6), today
        return today, today

    def _targets(self, period):
        icp = self.env["ir.config_parameter"].sudo()
        appels = int(
            icp.get_param(
                "coins_marocain_partenariats.kpi_target_appels_jour", "100"
            )
            or 100
        )
        conv = int(
            icp.get_param(
                "coins_marocain_partenariats.kpi_target_conversations_jour", "40"
            )
            or 40
        )
        days = 7 if period == "week" else 1
        return {
            "appels_jour": appels,
            "conversations_jour": conv,
            "appels": appels * days,
            "conversations": conv * days,
            "response_rate_pct": 40.0,
        }

    def _partner_lead_domain(self, date_from, date_to, commercial_id=False):
        team = self.env.ref(
            "coins_marocain_partenariats.crm_team_coins_marocain",
            raise_if_not_found=False,
        )
        domain = [("coins_fiche_type", "=", "partenariat")]
        if team:
            domain = [
                "&",
                ("coins_fiche_type", "=", "partenariat"),
                ("team_id", "=", team.id),
            ]
        if commercial_id:
            domain.append(("coins_commercial_assigne", "=", int(commercial_id)))
        return domain

    def _commercials(self):
        team = self.env.ref(
            "coins_marocain_partenariats.crm_team_coins_marocain",
            raise_if_not_found=False,
        )
        users = self.env["res.users"]
        if team:
            users |= team.member_ids | team.user_id
        Lead = self.env["crm.lead"].sudo()
        assigned = Lead.search(
            [("coins_commercial_assigne", "!=", False)]
        ).mapped("coins_commercial_assigne")
        daily = self.sudo().search([]).mapped("user_id")
        users |= assigned | daily
        return [
            {"id": u.id, "name": u.name}
            for u in users.filtered(lambda u: u.active and not u.share).sorted("name")
        ]

    def _stage_dwell(self, leads):
        today = fields.Date.context_today(self)
        by_stage = defaultdict(list)
        for lead in leads:
            stage = lead.stage_id.name or "—"
            start = fields.Date.to_date(
                lead.date_last_stage_update or lead.create_date or today
            )
            by_stage[stage].append(max((today - start).days, 0))
        rows = []
        for name, days in sorted(by_stage.items()):
            avg = sum(days) / float(len(days)) if days else 0.0
            rows.append(
                {
                    "stage": name,
                    "count": len(days),
                    "avg_days": round(avg, 1),
                }
            )
        return rows

    @api.model
    def get_equipe_kpi(self, period="day", commercial_id=False):
        period = "week" if period == "week" else "day"
        date_from, date_to = self._period_bounds(period)
        targets = self._targets(period)
        commercial_id = int(commercial_id) if commercial_id else False

        daily_domain = [("date", ">=", date_from), ("date", "<=", date_to)]
        if commercial_id:
            daily_domain.append(("user_id", "=", commercial_id))
        lines = self.sudo().search(daily_domain)
        appels = sum(lines.mapped("appels_composes"))
        conversations = sum(lines.mapped("conversations_completees"))
        response_rate = (
            round(100.0 * conversations / float(appels), 1) if appels else 0.0
        )

        Lead = self.env["crm.lead"].sudo()
        base = self._partner_lead_domain(date_from, date_to, commercial_id)
        conv_leads = Lead.search(
            base
            + [
                ("coins_conversation_completee", "=", True),
                ("coins_date_conversation", ">=", date_from),
                ("coins_date_conversation", "<=", date_to),
            ]
        )
        interet_n = len(conv_leads.filtered("coins_interet_confirme"))
        conv_n = len(conv_leads)
        conv_to_interest = (
            round(100.0 * interet_n / float(conv_n), 1) if conv_n else 0.0
        )

        split_leads = Lead.search(base + [("canal_traitement", "!=", False)])
        autonome = len(split_leads.filtered(lambda l: l.canal_traitement == "autonome"))
        accompagne = len(
            split_leads.filtered(lambda l: l.canal_traitement == "accompagne")
        )

        visites_planifiees = Lead.search_count(
            base
            + [
                ("coins_date_visite", ">=", date_from),
                ("coins_date_visite", "<=", date_to),
            ]
        )
        visites_realisees_recs = Lead.search(
            base
            + [
                ("coins_date_visite_realisee", ">=", date_from),
                ("coins_date_visite_realisee", "<=", date_to),
            ]
        )
        visites_realisees = len(visites_realisees_recs)
        signed = visites_realisees_recs.filtered(
            lambda l: (l.coins_entente_statut in ("active", "a_renouveler"))
            or bool(l.coins_entente_id.date_signature)
            or bool(l.stage_id.is_won)
        )
        visite_to_entente = (
            round(100.0 * len(signed) / float(visites_realisees), 1)
            if visites_realisees
            else 0.0
        )
        delays = []
        for lead in visites_realisees_recs:
            start = lead.coins_date_conversation or lead.coins_date_appel
            if start and lead.coins_date_visite_realisee:
                delays.append((lead.coins_date_visite_realisee - start).days)
        delay_avg = round(sum(delays) / float(len(delays)), 1) if delays else 0.0

        Entente = self.env["coins.entente"].sudo()
        ententes_signees = Entente.search_count(
            [
                ("active", "=", True),
                "|",
                ("date_signature", "!=", False),
                ("statut_entente", "in", ("active", "a_renouveler")),
            ]
        )
        pipeline = Lead.search(base)
        qualification = {
            "appels_composes": int(appels),
            "conversations_completees": int(conversations),
            "response_rate_pct": response_rate,
            "conversion_interet_pct": conv_to_interest,
            "conversations_avec_interet": int(interet_n),
            "conversations_fiches": int(conv_n),
            "autonome": int(autonome),
            "accompagne": int(accompagne),
        }
        visites = {
            "visites_realisees": int(visites_realisees),
            "visites_planifiees": int(visites_planifiees),
            "conversion_entente_pct": visite_to_entente,
            "ententes_apres_visite": int(len(signed)),
            "delai_qualif_visite_jours": delay_avg,
        }
        return {
            "period": period,
            "date_from": fields.Date.to_string(date_from),
            "date_to": fields.Date.to_string(date_to),
            "as_of": fields.Datetime.to_string(fields.Datetime.now()),
            "commercial_id": commercial_id or False,
            "commercials": self._commercials(),
            "targets": targets,
            "qualification": qualification,
            "visites": visites,
            "fille": qualification,
            "zakaria": visites,
            "shared": {
                "ententes_signees_cumul": int(ententes_signees),
                "stages": self._stage_dwell(pipeline),
            },
        }


class CoinsPartenariatKpiSettings(models.TransientModel):
    _name = "coins.partenariat.kpi.settings"
    _description = "Objectifs KPI partenariats (ajustables)"

    target_appels_jour = fields.Integer(
        string="Objectif appels composés / jour",
        default=100,
    )
    target_conversations_jour = fields.Integer(
        string="Objectif conversations complétées / jour",
        default=40,
    )

    @api.model
    def default_get(self, fields_list):
        vals = super().default_get(fields_list)
        icp = self.env["ir.config_parameter"].sudo()
        vals["target_appels_jour"] = int(
            icp.get_param(
                "coins_marocain_partenariats.kpi_target_appels_jour", "100"
            )
            or 100
        )
        vals["target_conversations_jour"] = int(
            icp.get_param(
                "coins_marocain_partenariats.kpi_target_conversations_jour", "40"
            )
            or 40
        )
        return vals

    def action_save(self):
        self.ensure_one()
        icp = self.env["ir.config_parameter"].sudo()
        icp.set_param(
            "coins_marocain_partenariats.kpi_target_appels_jour",
            str(self.target_appels_jour or 100),
        )
        icp.set_param(
            "coins_marocain_partenariats.kpi_target_conversations_jour",
            str(self.target_conversations_jour or 40),
        )
        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": "Objectifs enregistrés",
                "message": "Appels %s / jour · Conversations %s / jour"
                % (self.target_appels_jour, self.target_conversations_jour),
                "type": "success",
                "sticky": False,
            },
        }
