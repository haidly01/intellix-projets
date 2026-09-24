# -*- coding: utf-8 -*-
from calendar import monthrange
from datetime import datetime

from odoo import _, api, fields, models

# Agentes bénéficiaires du bonus (Leila / Yamina). Martin = validateur, pas crédité.
CQ_BONUS_AGENT_LOGINS = (
    "leiladaouadi@gmail.com",
    "printempsdevie123@gmail.com",
)

PRESENCE_AVG_THRESHOLD = 5.0
BONUS_PRESENCE_DH = 1000.0
REVENUE_BONUS_START_CAD = 10000.0
REVENUE_BONUS_STEP_CAD = 5000.0
BONUS_REVENUE_STEP_DH = 500.0


class CoinsQuebecPartenariatBonus(models.Model):
    _inherit = "coins.quebec.partenariat"

    statut_presence = fields.Selection(
        [
            ("a_venir", "À venir"),
            ("present", "Présent"),
            ("absent", "Absent"),
        ],
        string="Statut présence",
        tracking=True,
        help="Rempli par Martin après la visite (validation).",
    )
    forfait_vendu_id = fields.Many2one(
        "product.product",
        string="Forfait vendu",
        domain=[("default_code", "ilike", "CQ_%")],
        tracking=True,
    )
    montant_vendu = fields.Monetary(
        string="Montant vendu",
        currency_field="currency_id",
        tracking=True,
        help="Montant CAD saisi par Martin à la validation.",
    )
    currency_id = fields.Many2one(
        "res.currency",
        string="Devise vente",
        default=lambda self: (
            self.env.ref("base.CAD", raise_if_not_found=False)
            or self.env.company.currency_id
        ).id,
    )

    @api.onchange("forfait_vendu_id")
    def _onchange_forfait_vendu_id(self):
        for rec in self:
            if rec.forfait_vendu_id and not rec.montant_vendu:
                rec.montant_vendu = rec.forfait_vendu_id.list_price or 0.0


class CoinsQuebecAgentBonusMonth(models.Model):
    """Bonus mensuel — une ligne par agente (Leila / Yamina), pas combiné."""

    _name = "coins.quebec.agent.bonus.month"
    _description = "Bonus mensuel agente Coins Québec"
    _order = "month desc, agent_id"
    _rec_name = "display_name"

    agent_id = fields.Many2one(
        "res.users",
        string="Agente",
        required=True,
        index=True,
        ondelete="restrict",
    )
    month = fields.Date(
        string="Mois",
        required=True,
        index=True,
        help="Premier jour du mois calculé.",
    )
    display_name = fields.Char(compute="_compute_display_name", store=True)
    currency_cad_id = fields.Many2one(
        "res.currency",
        string="Devise revenus",
        default=lambda self: self.env.ref("base.CAD", raise_if_not_found=False),
        readonly=True,
    )
    currency_dh_id = fields.Many2one(
        "res.currency",
        string="Devise bonus",
        default=lambda self: self.env.ref("base.MAD", raise_if_not_found=False),
        readonly=True,
    )
    jours_travailles = fields.Integer(
        string="Jours travaillés",
        readonly=True,
        help="Jours avec ≥1 RDV présent ou absent (Option B + garde-fou).",
    )
    rdv_presents = fields.Integer(string="RDV présents", readonly=True)
    rdv_absents = fields.Integer(string="RDV absents", readonly=True)
    moyenne_rdv_presents_jour = fields.Float(
        string="Moy. présents / jour",
        digits=(16, 2),
        readonly=True,
    )
    bonus_presence = fields.Monetary(
        string="Bonus présence (DH)",
        currency_field="currency_dh_id",
        readonly=True,
    )
    revenu_total_mois = fields.Monetary(
        string="Revenu total (CAD)",
        currency_field="currency_cad_id",
        readonly=True,
    )
    bonus_revenu = fields.Monetary(
        string="Bonus revenu (DH)",
        currency_field="currency_dh_id",
        readonly=True,
    )
    bonus_total = fields.Monetary(
        string="Bonus total (DH)",
        currency_field="currency_dh_id",
        readonly=True,
    )
    fiche_count = fields.Integer(string="Fiches prises en compte", readonly=True)
    note = fields.Text(string="Note", readonly=True)

    _sql_constraints = [
        (
            "cq_agent_bonus_month_uniq",
            "unique(agent_id, month)",
            "Une seule ligne bonus par agente et par mois.",
        ),
    ]

    @api.depends("agent_id", "month")
    def _compute_display_name(self):
        for rec in self:
            agent = rec.agent_id.name or "?"
            month_label = rec.month.strftime("%Y-%m") if rec.month else "?"
            rec.display_name = "%s · %s" % (agent, month_label)

    @api.model
    def _bonus_agent_users(self):
        Users = self.env["res.users"].sudo()
        agents = Users.search([("login", "in", CQ_BONUS_AGENT_LOGINS)])
        if len(agents) < len(CQ_BONUS_AGENT_LOGINS):
            found = set(agents.mapped("login"))
            missing = [l for l in CQ_BONUS_AGENT_LOGINS if l not in found]
            raise ValueError(
                _("Agentes bonus introuvables : %s") % ", ".join(missing)
            )
        return agents

    @api.model
    def _month_bounds(self, month_date):
        if isinstance(month_date, str):
            month_date = fields.Date.from_string(month_date)
        start = month_date.replace(day=1)
        last_day = monthrange(start.year, start.month)[1]
        end = start.replace(day=last_day)
        return start, end

    @api.model
    def _compute_revenue_bonus_dh(self, revenu_cad):
        if revenu_cad < REVENUE_BONUS_START_CAD:
            return 0.0
        extra = revenu_cad - REVENUE_BONUS_START_CAD
        steps = int(extra // REVENUE_BONUS_STEP_CAD)
        return BONUS_REVENUE_STEP_DH + steps * BONUS_REVENUE_STEP_DH

    @api.model
    def _compute_agent_metrics(self, agent, month_date):
        """Calcule les métriques pour une agente sur un mois."""
        Part = self.env["coins.quebec.partenariat"].sudo()
        start, end = self._month_bounds(month_date)
        start_dt = datetime.combine(start, datetime.min.time())
        end_dt = datetime.combine(end, datetime.max.time())

        fiches = Part.search(
            [
                ("coins_commercial_assigne", "=", agent.id),
                ("cq_rdv_event_id", "!=", False),
                ("cq_rdv_event_id.start", ">=", fields.Datetime.to_string(start_dt)),
                ("cq_rdv_event_id.start", "<=", fields.Datetime.to_string(end_dt)),
                ("is_demo", "=", False),
            ]
        )

        worked_days = set()
        presents = 0
        absents = 0
        revenu = 0.0
        skipped_avenir = 0

        for fiche in fiches:
            status = fiche.statut_presence or "a_venir"
            if status == "a_venir":
                skipped_avenir += 1
                continue
            rdv_day = fiche.cq_rdv_event_id.start.date()
            worked_days.add(rdv_day)
            if status == "present":
                presents += 1
            elif status == "absent":
                absents += 1
            revenu += fiche.montant_vendu or 0.0

        jours = len(worked_days)
        avg = (presents / jours) if jours else 0.0
        bonus_presence = BONUS_PRESENCE_DH if avg >= PRESENCE_AVG_THRESHOLD else 0.0
        bonus_revenu = self._compute_revenue_bonus_dh(revenu)

        note_parts = []
        if skipped_avenir:
            note_parts.append(
                _("%s RDV « à venir » exclus du dénominateur.") % skipped_avenir
            )
        if not fiches:
            note_parts.append(_("Aucune fiche créditée ce mois."))

        return {
            "jours_travailles": jours,
            "rdv_presents": presents,
            "rdv_absents": absents,
            "moyenne_rdv_presents_jour": round(avg, 2),
            "bonus_presence": bonus_presence,
            "revenu_total_mois": revenu,
            "bonus_revenu": bonus_revenu,
            "bonus_total": bonus_presence + bonus_revenu,
            "fiche_count": len(fiches),
            "note": "\n".join(note_parts) if note_parts else False,
        }

    @api.model
    def refresh_month(self, month_date=None):
        """Recalcule les lignes Leila + Yamina pour le mois donné (1er du mois)."""
        if not month_date:
            today = fields.Date.context_today(self)
            month_date = today.replace(day=1)
        else:
            month_date = fields.Date.from_string(month_date).replace(day=1)

        agents = self._bonus_agent_users()
        results = []
        for agent in agents:
            metrics = self._compute_agent_metrics(agent, month_date)
            existing = self.search(
                [("agent_id", "=", agent.id), ("month", "=", month_date)],
                limit=1,
            )
            vals = {
                "agent_id": agent.id,
                "month": month_date,
                **metrics,
            }
            if existing:
                existing.write(metrics)
                results.append(existing)
            else:
                results.append(self.create(vals))
        return results

    def action_refresh_month(self):
        month = self[:1].month if self else None
        self.env["coins.quebec.agent.bonus.month"].refresh_month(month)
        return {
            "type": "ir.actions.client",
            "tag": "reload",
        }

    @api.model
    def action_open_bonus_dashboard(self):
        self.refresh_month()
        return {
            "type": "ir.actions.act_window",
            "name": _("Bonus agentes CQ"),
            "res_model": "coins.quebec.agent.bonus.month",
            "view_mode": "list,form",
            "target": "current",
            "context": {},
        }
