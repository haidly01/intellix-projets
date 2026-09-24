# -*- coding: utf-8 -*-
import logging
from datetime import timedelta

from odoo import api, fields, models

_logger = logging.getLogger(__name__)

FINANCE_MIN_MONTHS = 6
FINANCE_MIN_CREDIT = 600
FINANCE_MIN_ANNUAL_REVENUE = 120000.0

FUNNEL_STAGES = [
    ("lead_contacted", "Lead contacté"),
    ("interest_confirmed", "Intérêt confirmé"),
    ("initial_approval", "Approbation initiale"),
    ("docs_requested", "Documents demandés"),
    ("docs_verified", "Documents reçus et vérifiés"),
    ("offer_presented", "Offre finale présentée"),
    ("funded", "Financé"),
]
FUNNEL_SEQ = {key: idx + 1 for idx, (key, _label) in enumerate(FUNNEL_STAGES)}
FUNNEL_HAPPY_PATH = [key for key, _lab in FUNNEL_STAGES]

LOSS_REASONS = [
    ("documentary", "Abandon documentaire"),
    ("credit", "Refus crédit"),
    ("rate", "Refus taux / conditions"),
    ("other", "Autre"),
]

BRAND_XMLIDS = {
    "driven": "renovation_conciergerie.crm_team_driven",
    "growth_capital": "intellix_finance.crm_team_growth_capital",
    "itex": "intellix_finance.crm_team_itex",
}

CANADIAN_PROVINCES = [
    ("AB", "Alberta"),
    ("BC", "Colombie-Britannique"),
    ("MB", "Manitoba"),
    ("NB", "Nouveau-Brunswick"),
    ("NL", "Terre-Neuve-et-Labrador"),
    ("NS", "Nouvelle-Écosse"),
    ("NT", "Territoires du Nord-Ouest"),
    ("NU", "Nunavut"),
    ("ON", "Ontario"),
    ("PE", "Île-du-Prince-Édouard"),
    ("QC", "Québec"),
    ("SK", "Saskatchewan"),
    ("YT", "Yukon"),
]
PROVINCE_LABELS = {key: label for key, label in CANADIAN_PROVINCES}
LANG_LABELS = {"fr": "Français", "en": "Anglais"}

DEMO_NAME_PREFIX = "[Démo Finance]"


class CrmLeadFinance(models.Model):
    _inherit = "crm.lead"

    finance_brand = fields.Selection(
        [
            ("driven", "Driven"),
            ("growth_capital", "Growth Capital"),
            ("itex", "ITEX"),
        ],
        string="Marque Finance",
        compute="_compute_finance_brand",
        store=True,
        index=True,
    )
    finance_annual_revenue = fields.Monetary(
        string="Revenu annuel",
        currency_field="company_currency",
        tracking=True,
    )
    finance_bank_statements = fields.Selection(
        [
            ("unknown", "Non renseigné"),
            ("commercial", "Relevés commerciaux"),
            ("personal", "Relevés personnels"),
        ],
        string="Relevés bancaires",
        default="unknown",
        tracking=True,
    )
    finance_bankruptcy = fields.Selection(
        [
            ("unknown", "Non renseigné"),
            ("none", "Aucune faillite"),
            ("prior", "Faillite antérieure"),
        ],
        string="Historique de faillite",
        default="unknown",
        tracking=True,
    )
    finance_months_ok = fields.Boolean(compute="_compute_finance_prequal", store=True)
    finance_credit_ok = fields.Boolean(compute="_compute_finance_prequal", store=True)
    finance_revenue_ok = fields.Boolean(compute="_compute_finance_prequal", store=True)
    finance_statements_ok = fields.Boolean(compute="_compute_finance_prequal", store=True)
    finance_bankruptcy_ok = fields.Boolean(compute="_compute_finance_prequal", store=True)
    finance_prequal_status = fields.Selection(
        [
            ("pending", "En attente de pré-qualification"),
            ("qualified", "Pré-qualifié"),
            ("not_qualified", "Non qualifié"),
        ],
        string="Pré-qualification Finance",
        compute="_compute_finance_prequal",
        store=True,
        index=True,
    )
    finance_prequal_failures = fields.Char(
        string="Critères échoués",
        compute="_compute_finance_prequal",
        store=True,
    )
    finance_in_funnel = fields.Boolean(
        string="Dans l'entonnoir de financement",
        compute="_compute_finance_in_funnel",
        search="_search_finance_in_funnel",
        store=True,
        index=True,
    )
    finance_funnel_stage = fields.Selection(
        FUNNEL_STAGES,
        string="Étape financement",
        tracking=True,
        index=True,
        group_expand="_group_expand_finance_funnel_stage",
    )
    finance_max_stage_seq = fields.Integer(default=0)
    finance_is_lost = fields.Boolean(string="Perdu (financement)", tracking=True)
    finance_lost_reason = fields.Selection(
        LOSS_REASONS,
        string="Motif de perte financement",
        tracking=True,
    )
    finance_qualified_date = fields.Datetime(string="Pré-qualifié le")
    finance_funded_date = fields.Datetime(string="Financé le")
    finance_province = fields.Selection(
        CANADIAN_PROVINCES,
        string="Province",
        tracking=True,
        index=True,
        help="10 provinces et 3 territoires canadiens — ITEX, Driven et Growth Capital.",
    )
    finance_lang = fields.Selection(
        [("fr", "Français"), ("en", "Anglais")],
        string="Langue",
        tracking=True,
        index=True,
        help="Langue du lead. Pas d'assignation agent/script ici : "
        "les agents IA ont déjà un champ langue, sans routage CRM existant.",
    )
    finance_callback_datetime = fields.Datetime(
        string="Rappel Alex convenu",
        tracking=True,
        index=True,
        help="CALLBK Alex écrit sur le lead (pas seulement les logs Vicidial).",
    )
    finance_callback_comment = fields.Char(string="Commentaire rappel Alex")
    finance_callback_source = fields.Selection(
        [
            ("alex_driven", "Alex Driven"),
            ("alex_itex", "Alex ITEX"),
            ("manual", "Manuel"),
        ],
        string="Source du rappel",
    )
    finance_callback_set = fields.Boolean(
        string="Rappel posé",
        compute="_compute_finance_callback_flags",
        store=True,
        index=True,
    )
    finance_callback_due = fields.Boolean(
        string="Rappel dû",
        compute="_compute_finance_callback_flags",
        store=True,
        index=True,
    )

    def _finance_team(self, brand):
        xmlid = BRAND_XMLIDS.get(brand)
        return self.env.ref(xmlid, raise_if_not_found=False) if xmlid else self.env["crm.team"]

    @api.model
    def _group_expand_finance_funnel_stage(self, stages, domain, order=None):
        """Toutes les colonnes Driven / GC, même vides."""
        return [key for key, _label in FUNNEL_STAGES]

    @api.depends("team_id")
    def _compute_finance_brand(self):
        teams = {brand: self._finance_team(brand) for brand in BRAND_XMLIDS}
        for lead in self:
            brand = False
            for key, team in teams.items():
                if team and lead.team_id and lead.team_id.id == team.id:
                    brand = key
                    break
            lead.finance_brand = brand

    def _finance_annual_revenue_amount(self):
        self.ensure_one()
        if self.finance_annual_revenue:
            return self.finance_annual_revenue
        if self.driven_monthly_revenue:
            return self.driven_monthly_revenue * 12.0
        return 0.0

    def _finance_criteria_snapshot(self):
        self.ensure_one()
        months = self.driven_months_in_business or 0
        credit = self.driven_credit_score or 0
        annual = self._finance_annual_revenue_amount()
        months_known = bool(self.driven_months_in_business)
        credit_known = bool(self.driven_credit_score)
        revenue_known = bool(self.finance_annual_revenue or self.driven_monthly_revenue)
        statements_known = self.finance_bank_statements not in (False, "unknown")
        bankruptcy_known = self.finance_bankruptcy not in (False, "unknown")
        return {
            "months_ok": months >= FINANCE_MIN_MONTHS,
            "credit_ok": credit >= FINANCE_MIN_CREDIT,
            "revenue_ok": annual >= FINANCE_MIN_ANNUAL_REVENUE,
            "statements_ok": self.finance_bank_statements == "commercial",
            "bankruptcy_ok": self.finance_bankruptcy == "none",
            "months_known": months_known,
            "credit_known": credit_known,
            "revenue_known": revenue_known,
            "statements_known": statements_known,
            "bankruptcy_known": bankruptcy_known,
        }

    @api.depends(
        "finance_brand",
        "driven_months_in_business",
        "driven_credit_score",
        "driven_monthly_revenue",
        "finance_annual_revenue",
        "finance_bank_statements",
        "finance_bankruptcy",
    )
    def _compute_finance_prequal(self):
        labels = {
            "months_ok": "Moins de 6 mois en affaires",
            "credit_ok": "Score de crédit < 600",
            "revenue_ok": "Revenu annuel < 120 000 $",
            "statements_ok": "Relevés non commerciaux",
            "bankruptcy_ok": "Faillite antérieure",
        }
        known_map = {
            "months_ok": "months_known",
            "credit_ok": "credit_known",
            "revenue_ok": "revenue_known",
            "statements_ok": "statements_known",
            "bankruptcy_ok": "bankruptcy_known",
        }
        for lead in self:
            snap = lead._finance_criteria_snapshot()
            lead.finance_months_ok = snap["months_ok"]
            lead.finance_credit_ok = snap["credit_ok"]
            lead.finance_revenue_ok = snap["revenue_ok"]
            lead.finance_statements_ok = snap["statements_ok"]
            lead.finance_bankruptcy_ok = snap["bankruptcy_ok"]
            if lead.finance_brand not in ("driven", "growth_capital"):
                lead.finance_prequal_status = False
                lead.finance_prequal_failures = False
                continue
            failures = []
            any_known = False
            all_known = True
            any_fail = False
            for key, label in labels.items():
                known = snap[known_map[key]]
                if known:
                    any_known = True
                    if not snap[key]:
                        any_fail = True
                        failures.append(label)
                else:
                    all_known = False
            lead.finance_prequal_failures = ", ".join(failures) if failures else False
            if any_fail:
                lead.finance_prequal_status = "not_qualified"
            elif all_known and any_known:
                lead.finance_prequal_status = "qualified"
            else:
                lead.finance_prequal_status = "pending"

    @api.depends("finance_brand", "finance_prequal_status")
    def _compute_finance_in_funnel(self):
        for lead in self:
            lead.finance_in_funnel = (
                lead.finance_brand in ("driven", "growth_capital")
                and lead.finance_prequal_status == "qualified"
            )

    def _search_finance_in_funnel(self, operator, value):
        wanted = bool(value) if operator in ("=", "!=") else True
        if operator == "!=":
            wanted = not wanted
        domain = [
            ("finance_brand", "in", ["driven", "growth_capital"]),
            ("finance_prequal_status", "=", "qualified"),
        ]
        if wanted:
            return domain
        return ["!"] + domain

    @api.model_create_multi
    def create(self, vals_list):
        leads = super().create(vals_list)
        leads._finance_sync_funnel_side_effects()
        return leads

    def write(self, vals):
        res = super().write(vals)
        if any(
            key in vals
            for key in (
                "finance_funnel_stage",
                "finance_is_lost",
                "finance_lost_reason",
                "finance_prequal_status",
                "team_id",
                "driven_months_in_business",
                "driven_credit_score",
                "driven_monthly_revenue",
                "finance_annual_revenue",
                "finance_bank_statements",
                "finance_bankruptcy",
            )
        ):
            self._finance_sync_funnel_side_effects()
        return res

    def _finance_sync_funnel_side_effects(self):
        now = fields.Datetime.now()
        for lead in self:
            updates = {}
            if lead.finance_in_funnel:
                if not lead.finance_qualified_date:
                    updates["finance_qualified_date"] = now
                if not lead.finance_funnel_stage and not lead.finance_is_lost:
                    updates["finance_funnel_stage"] = "lead_contacted"
                stage = updates.get("finance_funnel_stage") or lead.finance_funnel_stage
                seq = FUNNEL_SEQ.get(stage or "", 0)
                if seq > (lead.finance_max_stage_seq or 0):
                    updates["finance_max_stage_seq"] = seq
                if stage == "funded" and not lead.finance_funded_date:
                    updates["finance_funded_date"] = now
                    updates["finance_is_lost"] = False
                    updates["finance_lost_reason"] = False
            else:
                if lead.finance_funnel_stage:
                    updates["finance_funnel_stage"] = False
                if lead.finance_is_lost:
                    updates["finance_is_lost"] = False
                    updates["finance_lost_reason"] = False
            if updates:
                super(CrmLeadFinance, lead).write(updates)

    @api.depends("finance_callback_datetime")
    def _compute_finance_callback_flags(self):
        now = fields.Datetime.now()
        for lead in self:
            lead.finance_callback_set = bool(lead.finance_callback_datetime)
            lead.finance_callback_due = bool(
                lead.finance_callback_datetime and lead.finance_callback_datetime <= now
            )

    def finance_set_alex_callback(self, when=None, comment="", source="alex_driven"):
        """Pose un rappel Alex sur le lead Finance (Driven ou ITEX quand mappé)."""
        self.ensure_one()
        if source not in ("alex_driven", "alex_itex", "manual"):
            source = "manual"
        when = when or (fields.Datetime.now() + timedelta(days=1))
        vals = {
            "finance_callback_datetime": when,
            "finance_callback_comment": (comment or "")[:200] or False,
            "finance_callback_source": source,
        }
        if "rappel_datetime" in self._fields:
            vals["rappel_datetime"] = when
        if "immo_callback_scheduled" in self._fields:
            vals["immo_callback_scheduled"] = when
        self.write(vals)
        return True

    def action_finance_mark_lost(self):
        self.ensure_one()
        if not self.finance_in_funnel:
            return False
        reason = self.finance_lost_reason or "other"
        self.write({"finance_is_lost": True, "finance_lost_reason": reason})
        return True

    @api.model
    def _finance_harden_menus(self):
        """Paths uniques + pas de dashboard Coins / CRM générique sous Finance."""
        try:
            return self._finance_harden_menus_impl()
        except Exception:  # noqa: BLE001
            _logger.exception("intellix_finance: harden menus a échoué, upgrade continue")
            return False

    def _finance_harden_menus_impl(self):
        path_xmlids = {
            "intellix_finance.action_finance_dashboard": "fin-dashboard",
            "intellix_finance.action_finance_funnel_driven": "fin-driven",
            "intellix_finance.action_finance_funnel_growth": "fin-growth",
            "intellix_finance.action_finance_not_qualified_driven": "fin-nq-driven",
            "intellix_finance.action_finance_not_qualified_growth": "fin-nq-growth",
            "intellix_finance.action_finance_itex_leads": "fin-itex",
            "intellix_finance.action_finance_itex_partenaires_dashboard": "fin-itex-dash",
            "intellix_finance.action_finance_driven_dashboard": "fin-driven-dash",
            "intellix_finance.action_finance_callbacks_driven": "fin-driven-rappels",
            "intellix_finance.action_finance_callbacks_itex": "fin-itex-rappels",
        }
        for xmlid, path in path_xmlids.items():
            action = self.env.ref(xmlid, raise_if_not_found=False)
            if action and action.path != path:
                action.path = path

        itex_dash_menu = self.env.ref(
            "intellix_finance.menu_finance_itex_dashboard", raise_if_not_found=False
        )
        itex_dash_action = self.env.ref(
            "intellix_finance.action_finance_itex_partenaires_dashboard",
            raise_if_not_found=False,
        )
        if itex_dash_menu and itex_dash_action:
            itex_dash_menu.write(
                {
                    "active": True,
                    "name": "Dashboard ITEX",
                    "action": "%s,%s" % (itex_dash_action.type, itex_dash_action.id),
                }
            )

        driven_dash_menu = self.env.ref(
            "intellix_finance.menu_finance_driven_dashboard", raise_if_not_found=False
        )
        driven_dash_action = self.env.ref(
            "intellix_finance.action_finance_driven_dashboard",
            raise_if_not_found=False,
        )
        if driven_dash_menu and driven_dash_action:
            driven_dash_menu.write(
                {
                    "active": True,
                    "name": "Dashboard Driven",
                    "action": "%s,%s" % (driven_dash_action.type, driven_dash_action.id),
                }
            )

        comparatif = self.env.ref(
            "intellix_finance.menu_finance_dashboard", raise_if_not_found=False
        )
        if comparatif:
            comparatif.write({"active": False, "action": False})

        parent_actions = {
            "intellix_finance.menu_finance_itex": "intellix_finance.action_finance_itex_leads",
            "intellix_finance.menu_finance_driven": "intellix_finance.action_finance_driven_dashboard",
            "intellix_finance.menu_finance_growth": "intellix_finance.action_finance_funnel_growth",
            "intellix_finance.menu_finance_root": "intellix_finance.action_finance_itex_leads",
        }
        for menu_xmlid, action_xmlid in parent_actions.items():
            menu = self.env.ref(menu_xmlid, raise_if_not_found=False)
            action = self.env.ref(action_xmlid, raise_if_not_found=False)
            if menu and action:
                menu.action = "%s,%s" % (action.type, action.id)

        root = self.env.ref("intellix_finance.menu_finance_root", raise_if_not_found=False)
        if root:
            children = self.env["ir.ui.menu"].search([("id", "child_of", root.id)])
            for menu in children:
                data = self.env["ir.model.data"].search(
                    [("model", "=", "ir.ui.menu"), ("res_id", "=", menu.id)],
                    limit=1,
                )
                if data and data.module != "intellix_finance":
                    menu.active = False
        self._finance_harden_kanban_actions()
        return True

    def _finance_harden_kanban_actions(self):
        """Kanban en premier — view_ids form-first ouvre une fiche vide en Odoo 19."""
        WindowView = self.env["ir.actions.act_window.view"].sudo()
        specs = [
            (
                "intellix_finance.action_finance_itex_leads",
                "kanban,list,form",
                "intellix_finance.view_itex_funnel_kanban",
                [
                    (1, "kanban", "intellix_finance.view_itex_funnel_kanban"),
                    (2, "list", "intellix_finance.view_itex_lead_list"),
                    (3, "form", "intellix_finance.view_itex_lead_form"),
                ],
            ),
            (
                "intellix_finance.action_finance_funnel_driven",
                "kanban,list,form",
                "intellix_finance.view_finance_funnel_kanban",
                [
                    (1, "kanban", "intellix_finance.view_finance_funnel_kanban"),
                    (2, "list", "intellix_finance.view_finance_funnel_list"),
                ],
            ),
            (
                "intellix_finance.action_finance_funnel_growth",
                "kanban,list,form",
                "intellix_finance.view_finance_funnel_kanban",
                [
                    (1, "kanban", "intellix_finance.view_finance_funnel_kanban"),
                    (2, "list", "intellix_finance.view_finance_funnel_list"),
                ],
            ),
            (
                "intellix_finance.action_finance_callbacks_itex",
                "list,form",
                False,
                [
                    (1, "list", "intellix_finance.view_finance_callback_list"),
                    (2, "form", "intellix_finance.view_itex_lead_form"),
                ],
            ),
        ]
        for xmlid, mode, default_xmlid, rows in specs:
            act = self.env.ref(xmlid, raise_if_not_found=False)
            if not act:
                continue
            vals = {"view_mode": mode}
            default = (
                self.env.ref(default_xmlid, raise_if_not_found=False) if default_xmlid else False
            )
            if default:
                vals["view_id"] = default.id
            act.write(vals)
            existing = {v.view_mode: v for v in act.view_ids}
            wanted = {row[1] for row in rows}
            for seq, vmode, vxmlid in rows:
                view = self.env.ref(vxmlid, raise_if_not_found=False) if vxmlid else False
                rec = existing.get(vmode)
                row_vals = {
                    "act_window_id": act.id,
                    "view_mode": vmode,
                    "sequence": seq,
                    "view_id": view.id if view else False,
                }
                if rec:
                    rec.write(row_vals)
                else:
                    WindowView.create(row_vals)
            extras = act.view_ids.filtered(lambda v: v.view_mode not in wanted)
            extras.unlink()
        return True

    @api.model
    def get_finance_dashboard_stats(self, province=False, lang=False):
        """Métriques séparées par marque — aucun total Driven + Growth Capital."""
        itex = {}
        if "coins.entente" in self.env:
            try:
                itex = self.env["coins.entente"].get_live_dashboard_stats(period_days=30) or {}
            except Exception:  # noqa: BLE001
                itex = {}
        itex["segments"] = self._finance_brand_segments("itex", province=province, lang=lang)
        itex.update(self._itex_funnel_stats(province=province, lang=lang))
        return {
            "itex": itex,
            "driven": self._finance_brand_funnel_stats("driven", province=province, lang=lang),
            "growth_capital": self._finance_brand_funnel_stats(
                "growth_capital", province=province, lang=lang
            ),
            "filters": {
                "province": province or False,
                "lang": lang or False,
                "provinces": [{"key": k, "label": lab} for k, lab in CANADIAN_PROVINCES],
                "langs": [{"key": k, "label": lab} for k, lab in LANG_LABELS.items()],
            },
            "targets": {
                "approval_rate": 0.30,
                "cycle_min_days": 30,
                "cycle_max_days": 90,
            },
        }

    @api.model
    def get_driven_dashboard_stats(self, period_days=30):
        """KPIs Driven — crm.lead équipe Driven uniquement, hors démo Finance."""
        try:
            period_days = int(period_days or 30)
        except (TypeError, ValueError):
            period_days = 30
        if period_days not in (7, 30, 90):
            period_days = 30

        team = self._finance_team("driven")
        today = fields.Date.context_today(self)
        since = fields.Datetime.to_datetime(today) - timedelta(days=period_days - 1)
        since = since.replace(hour=0, minute=0, second=0, microsecond=0)
        as_of = fields.Datetime.now()
        empty = {
            "period_days": period_days,
            "since": fields.Datetime.to_string(since),
            "as_of": fields.Datetime.to_string(as_of),
            "team_id": team.id if team else False,
            "team_name": team.name if team else "Driven",
            "leads_period": 0,
            "interested": 0,
            "qualified": 0,
            "callbacks": 0,
            "callbacks_due": 0,
            "sans_match": 0,
            "sans_source": 0,
            "revenue_known": 0,
            "in_funnel": 0,
            "not_qualified": 0,
            "funded": 0,
            "approval_rate": None,
            "cycle_days_avg": None,
            "stages": [
                {"key": key, "label": lab, "count": 0, "seq": FUNNEL_SEQ[key]}
                for key, lab in FUNNEL_STAGES
            ],
            "sources": [],
            "sources_note": "Aucune source renseignée sur la période.",
            "recent_leads": [],
            "members_source": "crm.lead · équipe Driven · hors démo",
        }
        if not team:
            empty["members_source"] = "équipe Driven introuvable"
            return empty

        Lead = self.sudo()
        base = [
            ("team_id", "=", team.id),
            ("type", "in", ("lead", "opportunity")),
            ("name", "not like", DEMO_NAME_PREFIX + "%"),
        ]
        period = base + [("create_date", ">=", since)]
        empty["leads_period"] = Lead.search_count(period)
        empty["interested"] = Lead.search_count(
            period
            + [
                "|",
                ("finance_funnel_stage", "=", "interest_confirmed"),
                ("tag_ids.name", "=", "Lead chaud Driven"),
            ]
        )
        empty["qualified"] = Lead.search_count(
            period + [("finance_prequal_status", "=", "qualified")]
        )
        empty["callbacks"] = Lead.search_count(base + [("finance_callback_set", "=", True)])
        empty["callbacks_due"] = Lead.search_count(
            base + [("finance_callback_due", "=", True)]
        )
        empty["sans_match"] = Lead.search_count(period + [("partner_id", "=", False)])
        empty["sans_source"] = Lead.search_count(period + [("source_id", "=", False)])
        if "driven_monthly_revenue" in Lead._fields:
            empty["revenue_known"] = Lead.search_count(
                base + [("driven_monthly_revenue", ">", 0)]
            )
        empty["in_funnel"] = Lead.search_count(base + [("finance_in_funnel", "=", True)])
        empty["not_qualified"] = Lead.search_count(
            base + [("finance_prequal_status", "=", "not_qualified")]
        )
        empty["funded"] = Lead.search_count(
            base
            + [
                ("finance_funnel_stage", "=", "funded"),
                ("finance_is_lost", "=", False),
            ]
        )
        stage_counts = {key: 0 for key, _lab in FUNNEL_STAGES}
        for row in Lead.read_group(
            base
            + [
                ("finance_in_funnel", "=", True),
                ("finance_is_lost", "=", False),
                ("finance_funnel_stage", "!=", False),
            ],
            ["finance_funnel_stage"],
            ["finance_funnel_stage"],
            lazy=False,
        ) or []:
            key = row.get("finance_funnel_stage")
            if key in stage_counts:
                stage_counts[key] = int(
                    row.get("finance_funnel_stage_count") or row.get("__count") or 0
                )
        empty["stages"] = [
            {"key": key, "label": lab, "count": stage_counts[key], "seq": FUNNEL_SEQ[key]}
            for key, lab in FUNNEL_STAGES
        ]
        if empty["in_funnel"]:
            empty["approval_rate"] = empty["funded"] / empty["in_funnel"]

        grouped = Lead.read_group(
            period + [("source_id", "!=", False)],
            ["source_id"],
            ["source_id"],
            lazy=False,
        )
        sources = []
        for row in grouped or []:
            src = row.get("source_id") or [False, "Sans source"]
            sources.append(
                {
                    "code": src[0] if src and src[0] else "none",
                    "label": (src[1] if src and len(src) > 1 else None) or "Sans source",
                    "count": int(row.get("source_id_count") or row.get("__count") or 0),
                }
            )
        sources.sort(key=lambda c: (-c["count"], c["label"]))
        if empty["sans_source"]:
            sources.append(
                {
                    "code": "none",
                    "label": "Sans source",
                    "count": empty["sans_source"],
                }
            )
        max_src = max((c["count"] for c in sources), default=0)
        for row in sources:
            row["pct"] = int(round(100.0 * row["count"] / max_src)) if max_src else 0
        empty["sources"] = sources
        if sources:
            empty["sources_note"] = "source_id crm.lead · équipe Driven"
        lead_rows = Lead.search_read(
            period,
            [
                "name",
                "city",
                "source_id",
                "finance_funnel_stage",
                "finance_prequal_status",
                "finance_callback_set",
                "partner_id",
            ],
            order="create_date desc",
            limit=8,
        )
        stage_labels = dict(FUNNEL_STAGES)
        recent = []
        for row in lead_rows:
            stage_key = row.get("finance_funnel_stage")
            status = stage_labels.get(stage_key) or (row.get("finance_prequal_status") or "—")
            status_kind = "renew"
            if stage_key == "interest_confirmed" or row.get("finance_prequal_status") == "qualified":
                status_kind = "active"
            elif not row.get("partner_id") or not row.get("source_id"):
                status_kind = "nouveau"
            src = row.get("source_id") or [False, ""]
            recent.append(
                {
                    "name": row.get("name") or "—",
                    "services": (src[1] if src and len(src) > 1 else None) or "—",
                    "city": row.get("city") or "—",
                    "status": status,
                    "status_kind": status_kind,
                }
            )
        empty["recent_leads"] = recent
        return empty

    def _finance_segment_domain(self, province=False, lang=False):
        domain = []
        if province:
            domain.append(("finance_province", "=", province))
        if lang:
            domain.append(("finance_lang", "=", lang))
        return domain

    def _finance_brand_segments(self, brand, province=False, lang=False, records=None):
        if records is None:
            team = self._finance_team(brand)
            if not team:
                records = self.browse()
            else:
                domain = [
                    ("team_id", "=", team.id),
                    ("type", "in", ("lead", "opportunity")),
                ] + self._finance_segment_domain(province, lang)
                records = self.sudo().search(domain)
        by_province = {key: 0 for key, _lab in CANADIAN_PROVINCES}
        by_lang = {"fr": 0, "en": 0}
        for lead in records:
            if lead.finance_province in by_province:
                by_province[lead.finance_province] += 1
            if lead.finance_lang in by_lang:
                by_lang[lead.finance_lang] += 1
        return {
            "by_province": [
                {"key": key, "label": lab, "count": by_province[key]}
                for key, lab in CANADIAN_PROVINCES
                if by_province[key]
            ],
            "by_lang": [
                {"key": key, "label": LANG_LABELS[key], "count": by_lang[key]}
                for key in ("fr", "en")
                if by_lang[key]
            ],
        }

    @api.model
    def _finance_brand_funnel_stats(self, brand, province=False, lang=False):
        team = self._finance_team(brand)
        label = {"driven": "Driven", "growth_capital": "Growth Capital"}.get(brand, brand)
        empty = {
            "brand": brand,
            "name": label,
            "team_id": team.id if team else False,
            "pending": 0,
            "not_qualified": 0,
            "qualified": 0,
            "in_funnel": 0,
            "stages": [
                {"key": key, "label": lab, "count": 0, "seq": FUNNEL_SEQ[key]}
                for key, lab in FUNNEL_STAGES
            ],
            "loss": {
                "documentary": self._empty_loss("Abandon documentaire"),
                "credit": self._empty_loss("Refus crédit"),
                "rate": self._empty_loss("Refus taux / conditions"),
            },
            "approval_rate": None,
            "funded": 0,
            "cycle_days_avg": None,
            "target_approval": 0.30,
            "conversions": [],
            "segments": {"by_province": [], "by_lang": []},
        }
        if not team:
            return empty
        Lead = self.sudo()
        base = [
            ("team_id", "=", team.id),
            ("type", "in", ("lead", "opportunity")),
        ] + self._finance_segment_domain(province, lang)
        empty["pending"] = Lead.search_count(base + [("finance_prequal_status", "=", "pending")])
        empty["not_qualified"] = Lead.search_count(
            base + [("finance_prequal_status", "=", "not_qualified")]
        )
        funnel = Lead.search(base + [("finance_in_funnel", "=", True)])
        empty["qualified"] = len(funnel)
        empty["in_funnel"] = len(funnel)
        if not funnel:
            return empty

        stage_counts = {key: 0 for key, _lab in FUNNEL_STAGES}
        for lead in funnel:
            if lead.finance_is_lost:
                continue
            if lead.finance_funnel_stage in stage_counts:
                stage_counts[lead.finance_funnel_stage] += 1
        empty["stages"] = [
            {"key": key, "label": lab, "count": stage_counts[key], "seq": FUNNEL_SEQ[key]}
            for key, lab in FUNNEL_STAGES
        ]

        def _reached(min_seq):
            return funnel.filtered(lambda l: (l.finance_max_stage_seq or 0) >= min_seq)

        def _lost(reason):
            return funnel.filtered(
                lambda l: l.finance_is_lost and l.finance_lost_reason == reason
            )

        empty["loss"] = {
            "documentary": self._loss_block(
                "Abandon documentaire",
                _lost("documentary"),
                _reached(FUNNEL_SEQ["docs_requested"]),
            ),
            "credit": self._loss_block(
                "Refus crédit",
                _lost("credit"),
                _reached(FUNNEL_SEQ["docs_verified"]),
            ),
            "rate": self._loss_block(
                "Refus taux / conditions",
                _lost("rate"),
                _reached(FUNNEL_SEQ["offer_presented"]),
            ),
        }
        funded = funnel.filtered(
            lambda l: l.finance_funnel_stage == "funded" and not l.finance_is_lost
        )
        empty["funded"] = len(funded)
        empty["approval_rate"] = (len(funded) / len(funnel)) if funnel else None
        cycles = []
        for lead in funded:
            start = lead.finance_qualified_date or lead.create_date
            end = lead.finance_funded_date or lead.write_date
            if start and end and end >= start:
                cycles.append((end - start).days)
        empty["cycle_days_avg"] = round(sum(cycles) / len(cycles), 1) if cycles else None
        empty["conversions"] = self._finance_conversion_rows(funnel, FUNNEL_HAPPY_PATH, FUNNEL_SEQ)
        empty["segments"] = self._finance_brand_segments(brand, records=funnel)
        return empty

    @staticmethod
    def _finance_conversion_rows(records, happy_path, seq_map):
        rows = []
        labels = dict(FUNNEL_STAGES)

        def _reached(min_seq):
            return records.filtered(lambda l: (l.finance_max_stage_seq or 0) >= min_seq)

        for idx, key in enumerate(happy_path[:-1]):
            nxt = happy_path[idx + 1]
            reached = _reached(seq_map[key])
            nxt_recs = _reached(seq_map[nxt])
            rows.append(
                {
                    "from_key": key,
                    "from_label": labels.get(key, key),
                    "to_key": nxt,
                    "to_label": labels.get(nxt, nxt),
                    "reached": len(reached),
                    "next": len(nxt_recs),
                    "rate": (len(nxt_recs) / len(reached)) if reached else None,
                }
            )
        return rows

    @staticmethod
    def _empty_loss(label):
        return {"label": label, "lost": 0, "reached": 0, "rate": None}

    @staticmethod
    def _loss_block(label, lost, reached):
        n_lost = len(lost)
        n_reached = len(reached)
        return {
            "label": label,
            "lost": n_lost,
            "reached": n_reached,
            "rate": (n_lost / n_reached) if n_reached else None,
        }

    @api.model
    def _finance_seed_demo_leads(self):
        """Jeux de démo clairement identifiés — un lead à la fois (devises)."""
        driven = self._finance_team("driven")
        growth = self._finance_team("growth_capital")
        if not driven or not growth:
            return 0
        company = self.env["res.company"].search(
            [("name", "ilike", "Agence Doorway")], limit=1
        )
        created = 0
        for team, brand, rows in (
            (driven, "driven", self._finance_demo_rows_driven()),
            (growth, "growth_capital", self._finance_demo_rows_growth()),
        ):
            brand_label = brand.replace("_", " ").title()
            if self.search_count(
                [("name", "like", "%s %s%%" % (DEMO_NAME_PREFIX, brand_label))]
            ):
                continue
            for row in rows:
                vals = {
                    "name": "%s %s — %s" % (DEMO_NAME_PREFIX, brand.replace("_", " ").title(), row["title"]),
                    "type": "opportunity",
                    "team_id": team.id,
                    "contact_name": row["title"],
                    "partner_name": row["title"],
                    "driven_months_in_business": row.get("months"),
                    "driven_credit_score": row.get("credit"),
                    "driven_monthly_revenue": row.get("monthly"),
                    "finance_annual_revenue": row.get("annual"),
                    "finance_bank_statements": row.get("statements", "unknown"),
                    "finance_bankruptcy": row.get("bankruptcy", "unknown"),
                    "finance_province": row.get("province"),
                    "finance_lang": row.get("lang"),
                }
                if company:
                    vals["company_id"] = company.id
                lead = self.create(vals)
                created += 1
                extras = {}
                if row.get("stage") and lead.finance_in_funnel:
                    extras["finance_funnel_stage"] = row["stage"]
                    extras["finance_max_stage_seq"] = FUNNEL_SEQ.get(row["stage"], 0)
                if row.get("lost"):
                    extras["finance_is_lost"] = True
                    extras["finance_lost_reason"] = row["lost"]
                    extras["finance_max_stage_seq"] = max(
                        extras.get("finance_max_stage_seq") or 0,
                        FUNNEL_SEQ.get(row.get("reached") or row.get("stage") or "", 0),
                    )
                if row.get("qualified_days_ago") and lead.finance_in_funnel:
                    extras["finance_qualified_date"] = fields.Datetime.now() - timedelta(
                        days=row["qualified_days_ago"]
                    )
                if row.get("funded_days_ago") and row.get("stage") == "funded":
                    extras["finance_funded_date"] = fields.Datetime.now() - timedelta(
                        days=row["funded_days_ago"]
                    )
                if extras:
                    super(CrmLeadFinance, lead).write(extras)
        self._finance_ensure_demo_segments()
        return created

    @staticmethod
    def _finance_demo_rows_driven():
        ok = {
            "months": 18,
            "credit": 680,
            "monthly": 14000,
            "annual": 168000,
            "statements": "commercial",
            "bankruptcy": "none",
        }
        return [
            {**ok, "title": "Financé Atelier Nord", "stage": "funded", "qualified_days_ago": 52, "funded_days_ago": 4, "province": "QC", "lang": "fr"},
            {**ok, "title": "Offre présentée Clinique Maple", "stage": "offer_presented", "province": "ON", "lang": "en"},
            {**ok, "title": "Docs vérifiés Garage Saint-Laurent", "stage": "docs_verified", "province": "QC", "lang": "fr"},
            {**ok, "title": "Docs demandés Boulangerie Félix", "stage": "docs_requested", "province": "NB", "lang": "fr"},
            {**ok, "title": "Pré-approuvée Menuiserie Roy", "stage": "initial_approval", "province": "AB", "lang": "en"},
            {**ok, "title": "Intérêt confirmé Spa Lachine", "stage": "interest_confirmed", "province": "QC", "lang": "fr"},
            {**ok, "title": "Contacté Transport Gagnon", "stage": "lead_contacted", "province": "BC", "lang": "en"},
            {**ok, "title": "Abandon docs Entrepôt Hochelaga", "stage": "docs_requested", "lost": "documentary", "reached": "docs_requested", "province": "QC", "lang": "fr"},
            {**ok, "title": "Refus crédit Restaurant Bélanger", "stage": "docs_verified", "lost": "credit", "reached": "docs_verified", "province": "ON", "lang": "fr"},
            {
                "title": "Non qualifié score 540",
                "months": 24,
                "credit": 540,
                "monthly": 18000,
                "annual": 216000,
                "statements": "commercial",
                "bankruptcy": "none",
                "province": "NS",
                "lang": "en",
            },
        ]

    @staticmethod
    def _finance_demo_rows_growth():
        ok = {
            "months": 22,
            "credit": 710,
            "monthly": 16000,
            "annual": 192000,
            "statements": "commercial",
            "bankruptcy": "none",
        }
        return [
            {**ok, "title": "Financé Logistique Est", "stage": "funded", "qualified_days_ago": 71, "funded_days_ago": 8, "province": "ON", "lang": "en"},
            {**ok, "title": "Offre présentée Imprimerie Viau", "stage": "offer_presented", "province": "QC", "lang": "fr"},
            {**ok, "title": "Docs vérifiés Café Masson", "stage": "docs_verified", "province": "MB", "lang": "en"},
            {**ok, "title": "Docs demandés Quincaillerie Paul", "stage": "docs_requested", "province": "SK", "lang": "en"},
            {**ok, "title": "Pré-approuvée Toiture Lévis", "stage": "initial_approval", "province": "QC", "lang": "fr"},
            {**ok, "title": "Contacté Flotte Laval", "stage": "lead_contacted", "province": "QC", "lang": "fr"},
            {**ok, "title": "Abandon docs Studio Verdun", "stage": "docs_requested", "lost": "documentary", "reached": "docs_requested", "province": "QC", "lang": "fr"},
            {**ok, "title": "Refus taux Concession Beaubien", "stage": "offer_presented", "lost": "rate", "reached": "offer_presented", "province": "ON", "lang": "fr"},
            {**ok, "title": "Refus taux 2 Atelier Rosemont", "stage": "offer_presented", "lost": "rate", "reached": "offer_presented", "province": "AB", "lang": "en"},
            {
                "title": "Non qualifié relevés personnels",
                "months": 36,
                "credit": 720,
                "monthly": 20000,
                "annual": 240000,
                "statements": "personal",
                "bankruptcy": "none",
                "province": "BC",
                "lang": "en",
            },
        ]

    @staticmethod
    def _finance_demo_rows_itex():
        return [
            {"title": "Membre Atelier Plateau", "province": "QC", "lang": "fr"},
            {"title": "Membre Clinic Toronto", "province": "ON", "lang": "en"},
            {"title": "Membre Garage Calgary", "province": "AB", "lang": "en"},
            {"title": "Membre Boulangerie Moncton", "province": "NB", "lang": "fr"},
            {"title": "Membre Studio Vancouver", "province": "BC", "lang": "en"},
            {"title": "Membre Ferme Charlottetown", "province": "PE", "lang": "en"},
            {"title": "Membre Imprimerie Sherbrooke", "province": "QC", "lang": "fr"},
            {"title": "Membre Logistique Winnipeg", "province": "MB", "lang": "en"},
        ]

    @api.model
    def _finance_ensure_demo_segments(self):
        """Complète Province/Langue sur les démos existantes + membres ITEX."""
        itex = self._finance_team("itex")
        if itex and not self.search_count(
            [("name", "like", DEMO_NAME_PREFIX + " Itex%")]
        ):
            company = self.env["res.company"].search(
                [("name", "ilike", "Agence Doorway")], limit=1
            )
            for row in self._finance_demo_rows_itex():
                vals = {
                    "name": "%s Itex — %s" % (DEMO_NAME_PREFIX, row["title"]),
                    "type": "opportunity",
                    "team_id": itex.id,
                    "contact_name": row["title"],
                    "partner_name": row["title"],
                    "finance_province": row["province"],
                    "finance_lang": row["lang"],
                }
                if company:
                    vals["company_id"] = company.id
                self.create(vals)

        by_title = {}
        for rows in (
            self._finance_demo_rows_driven(),
            self._finance_demo_rows_growth(),
            self._finance_demo_rows_itex(),
        ):
            for row in rows:
                by_title[row["title"]] = row
        leads = self.search([("name", "like", DEMO_NAME_PREFIX + "%")])
        for lead in leads:
            if lead.finance_province and lead.finance_lang:
                continue
            match = next(
                (row for title, row in by_title.items() if title in (lead.name or "")),
                None,
            )
            if not match:
                continue
            super(CrmLeadFinance, lead).write(
                {
                    "finance_province": match.get("province"),
                    "finance_lang": match.get("lang"),
                }
            )
        return True


def _pct_label(rate):
    if rate is None:
        return "—"
    return "%.1f %%" % (rate * 100)


class CoinsEntenteItexFunnel(models.Model):
    _inherit = "coins.entente"

    @api.model
    def get_live_dashboard_stats(self, period_days=30):
        stats = super().get_live_dashboard_stats(period_days=period_days) or {}
        try:
            funnel = self.env["crm.lead"]._itex_funnel_stats()
        except Exception:  # noqa: BLE001
            _logger.exception("ITEX: stats entonnoir absentes du dashboard partenaires")
            return stats
        stats["itex_funnel"] = funnel
        stats["funnel_in"] = funnel.get("in_funnel") or 0
        stats["funnel_adherent"] = funnel.get("adherent") or 0
        stats["approval_rate"] = funnel.get("approval_rate")
        stats["approval_pct"] = _pct_label(funnel.get("approval_rate"))
        stats["cycle_days_avg"] = funnel.get("cycle_days_avg")
        stats["silence_pct"] = _pct_label((funnel.get("silence") or {}).get("rate"))
        stats["documentary_pct"] = _pct_label((funnel.get("documentary") or {}).get("rate"))
        return stats
