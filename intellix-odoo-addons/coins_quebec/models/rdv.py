# -*- coding: utf-8 -*-
"""RDV générés par Leila / Yamina — flux parallèle aux créneaux Rosalie / Martin."""
import pytz
from calendar import monthrange
from datetime import datetime, time

from odoo import _, api, fields, models
from odoo.exceptions import AccessError, UserError, ValidationError

from .partenariat import CQ_CANADA_TZ, CQ_MARTIN_LOGIN

CQ_RDV_AGENTS = [
    ("leila", "Leila"),
    ("yamina", "Yamina"),
]
CQ_RDV_AGENT_LOGINS = {
    "leila": "leiladaouadi@gmail.com",
    "yamina": "printempsdevie123@gmail.com",
}
CQ_RDV_STATES = [
    ("propose", "Proposé"),
    ("confirme", "Confirmé"),
    ("effectue", "Effectué"),
    ("annule", "Annulé"),
    ("no_show", "No-show"),
]
CQ_MARTIN_STATES = [
    ("pending", "En attente"),
    ("validated", "Validé"),
    ("rejected", "Rejeté"),
]


def _cq_current_month_bounds():
    today = fields.Date.today()
    last = monthrange(today.year, today.month)[1]
    return today.replace(day=1), today.replace(day=last)


class CoinsQuebecRdv(models.Model):
    _name = "coins.quebec.rdv"
    _description = "RDV équipe Coins Québec (Leila / Yamina)"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "start_at desc, id desc"
    _rec_name = "name"

    name = fields.Char(string="Libellé", compute="_compute_name", store=True)
    agent = fields.Selection(
        CQ_RDV_AGENTS,
        string="Agent",
        required=True,
        index=True,
        tracking=True,
        default=lambda self: self._cq_default_agent(),
    )
    agent_user_id = fields.Many2one(
        "res.users",
        string="Utilisateur agente",
        compute="_compute_agent_user_id",
        store=True,
        index=True,
        readonly=True,
    )
    partenariat_id = fields.Many2one(
        "coins.quebec.partenariat",
        string="Partenaire / prospect",
        index=True,
        ondelete="restrict",
        tracking=True,
    )
    lead_id = fields.Many2one(
        "crm.lead",
        string="Lead CRM",
        index=True,
        ondelete="set null",
        tracking=True,
        help="Optionnel. Le pipeline Coins Québec utilise surtout la fiche partenariat.",
    )
    start_at = fields.Datetime(
        string="Date et heure du RDV",
        required=True,
        index=True,
        tracking=True,
    )
    start_at_display = fields.Char(
        string="RDV (heure du Canada)",
        compute="_compute_start_at_display",
    )
    state = fields.Selection(
        CQ_RDV_STATES,
        string="Statut du RDV",
        default="propose",
        required=True,
        index=True,
        tracking=True,
        group_expand="_group_expand_state",
    )
    martin_state = fields.Selection(
        CQ_MARTIN_STATES,
        string="Validation Martin",
        default="pending",
        required=True,
        index=True,
        tracking=True,
        group_expand="_group_expand_martin_state",
    )
    reject_note = fields.Text(
        string="Motif du rejet",
        tracking=True,
        help="Obligatoire si Martin rejette le RDV.",
    )
    validated_at = fields.Datetime(string="Date de validation", tracking=True, readonly=True)
    note = fields.Text(string="Notes")
    is_martin_user = fields.Boolean(compute="_compute_is_martin_user")
    can_validate = fields.Boolean(compute="_compute_is_martin_user")

    @api.model
    def _group_expand_state(self, states, domain, order=None):
        del states, domain, order
        return [key for key, _label in CQ_RDV_STATES]

    @api.model
    def _group_expand_martin_state(self, states, domain, order=None):
        del states, domain, order
        return [key for key, _label in CQ_MARTIN_STATES]

    @api.model
    def _cq_default_agent(self):
        login = (self.env.user.login or "").strip().lower()
        for key, agent_login in CQ_RDV_AGENT_LOGINS.items():
            if login == agent_login:
                return key
        return False

    @api.model
    def _cq_user_is_martin(self):
        return (self.env.user.login or "").strip().lower() == CQ_MARTIN_LOGIN

    @api.depends("agent")
    def _compute_agent_user_id(self):
        Users = self.env["res.users"].sudo()
        for rec in self:
            login = CQ_RDV_AGENT_LOGINS.get(rec.agent)
            user = Users.search([("login", "=", login)], limit=1) if login else Users.browse()
            rec.agent_user_id = user

    @api.depends("agent", "partenariat_id", "lead_id", "start_at")
    def _compute_name(self):
        for rec in self:
            who = rec.partenariat_id.name or rec.lead_id.name or "Prospect"
            agent = dict(CQ_RDV_AGENTS).get(rec.agent) or "?"
            rec.name = "%s — %s" % (agent, who)

    @api.depends("start_at")
    def _compute_start_at_display(self):
        tz = pytz.timezone(CQ_CANADA_TZ)
        for rec in self:
            if not rec.start_at:
                rec.start_at_display = False
                continue
            dt = rec.start_at
            if getattr(dt, "tzinfo", None):
                local = dt.astimezone(tz)
            else:
                local = pytz.UTC.localize(dt).astimezone(tz)
            rec.start_at_display = local.strftime("%d/%m/%Y %Hh%M")

    @api.depends_context("uid")
    def _compute_is_martin_user(self):
        is_martin = self._cq_user_is_martin()
        for rec in self:
            rec.is_martin_user = is_martin
            rec.can_validate = is_martin and rec.martin_state == "pending"

    @api.constrains("partenariat_id", "lead_id")
    def _check_partner_or_lead(self):
        for rec in self:
            if not rec.partenariat_id and not rec.lead_id:
                raise ValidationError(
                    _("Liez un partenaire Coins Québec ou un lead.")
                )

    @api.constrains("martin_state", "reject_note")
    def _check_reject_note(self):
        for rec in self:
            if rec.martin_state == "rejected" and not (rec.reject_note or "").strip():
                raise ValidationError(_("Indiquez le motif du rejet."))

    def _cq_assert_can_set_agent(self, agent_key):
        if self.env.su or self.env.user.has_group(
            "coins_quebec.group_coins_quebec_manager"
        ):
            return
        default = self._cq_default_agent()
        if default and agent_key != default:
            raise AccessError(
                _("Vous ne pouvez créer que vos propres RDV (%s).")
                % dict(CQ_RDV_AGENTS).get(default, default)
            )

    def _cq_assert_martin_write(self, vals):
        locked = {"martin_state", "validated_at", "reject_note"}
        if not (locked & set(vals)):
            return
        if self.env.su or self._cq_user_is_martin():
            return
        raise AccessError(_("Seul Martin peut valider ou rejeter un RDV."))

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            agent = vals.get("agent") or self._cq_default_agent()
            vals["agent"] = agent
            if not agent:
                raise UserError(
                    _("Choisissez l'agente (Leila ou Yamina).")
                )
            self._cq_assert_can_set_agent(agent)
            self._cq_assert_martin_write(vals)
            vals.setdefault("martin_state", "pending")
            vals.setdefault("state", "propose")
        return super().create(vals_list)

    def write(self, vals):
        if "agent" in vals:
            self._cq_assert_can_set_agent(vals["agent"])
        self._cq_assert_martin_write(vals)
        return super().write(vals)

    def action_martin_validate(self):
        self.ensure_one()
        if not self._cq_user_is_martin() and not self.env.su:
            raise AccessError(_("Seul Martin peut valider un RDV."))
        if self.martin_state != "pending":
            raise UserError(_("Ce RDV n'est plus en attente de validation."))
        self.write(
            {
                "martin_state": "validated",
                "validated_at": fields.Datetime.now(),
                "reject_note": False,
            }
        )
        return True

    def action_open_reject_wizard(self):
        self.ensure_one()
        if not self._cq_user_is_martin() and not self.env.su:
            raise AccessError(_("Seul Martin peut rejeter un RDV."))
        if self.martin_state != "pending":
            raise UserError(_("Ce RDV n'est plus en attente de validation."))
        return {
            "type": "ir.actions.act_window",
            "name": _("Rejeter le RDV"),
            "res_model": "coins.quebec.rdv.reject.wizard",
            "view_mode": "form",
            "target": "new",
            "context": {"default_rdv_id": self.id},
        }


class CoinsQuebecRdvKpi(models.TransientModel):
    _name = "coins.quebec.rdv.kpi"
    _description = "Suivi RDV Leila / Yamina"

    name = fields.Char(default="Suivi RDV équipe", readonly=True)
    date_from = fields.Date(
        string="Du",
        required=True,
        default=lambda self: _cq_current_month_bounds()[0],
    )
    date_to = fields.Date(
        string="Au",
        required=True,
        default=lambda self: _cq_current_month_bounds()[1],
    )
    show_team = fields.Boolean(compute="_compute_kpis")
    show_leila = fields.Boolean(compute="_compute_kpis")
    show_yamina = fields.Boolean(compute="_compute_kpis")
    viewer_label = fields.Char(compute="_compute_kpis")
    leila_total = fields.Integer(compute="_compute_kpis")
    leila_pending = fields.Integer(compute="_compute_kpis")
    leila_validated = fields.Integer(compute="_compute_kpis")
    leila_rejected = fields.Integer(compute="_compute_kpis")
    leila_rate = fields.Float(compute="_compute_kpis", digits=(16, 1))
    leila_done = fields.Integer(compute="_compute_kpis")
    leila_noshow = fields.Integer(compute="_compute_kpis")
    yamina_total = fields.Integer(compute="_compute_kpis")
    yamina_pending = fields.Integer(compute="_compute_kpis")
    yamina_validated = fields.Integer(compute="_compute_kpis")
    yamina_rejected = fields.Integer(compute="_compute_kpis")
    yamina_rate = fields.Float(compute="_compute_kpis", digits=(16, 1))
    yamina_done = fields.Integer(compute="_compute_kpis")
    yamina_noshow = fields.Integer(compute="_compute_kpis")

    def _cq_see_team(self):
        user = self.env.user
        return bool(
            user.has_group("coins_quebec.group_coins_quebec_manager")
            or user.has_group("base.group_system")
            or (user.login or "").strip().lower()
            in {CQ_MARTIN_LOGIN, "karine@agencedoorway.com"}
        )

    def _cq_period_domain(self):
        self.ensure_one()
        tz = pytz.timezone(CQ_CANADA_TZ)
        start = tz.localize(datetime.combine(self.date_from, time.min)).astimezone(
            pytz.UTC
        ).replace(tzinfo=None)
        end = tz.localize(datetime.combine(self.date_to, time.max)).astimezone(
            pytz.UTC
        ).replace(tzinfo=None)
        return [("start_at", ">=", start), ("start_at", "<=", end)]

    def _cq_agent_stats(self, rdv, agent_key):
        recs = rdv.filtered(lambda r: r.agent == agent_key)
        pending = recs.filtered(lambda r: r.martin_state == "pending")
        validated = recs.filtered(lambda r: r.martin_state == "validated")
        rejected = recs.filtered(lambda r: r.martin_state == "rejected")
        decided = len(validated) + len(rejected)
        rate = (100.0 * len(validated) / decided) if decided else 0.0
        return {
            "total": len(recs),
            "pending": len(pending),
            "validated": len(validated),
            "rejected": len(rejected),
            "rate": rate,
            "done": len(recs.filtered(lambda r: r.state == "effectue")),
            "noshow": len(recs.filtered(lambda r: r.state == "no_show")),
        }

    @api.depends("date_from", "date_to")
    def _compute_kpis(self):
        Rdv = self.env["coins.quebec.rdv"]
        for rec in self:
            show_team = rec._cq_see_team()
            rec.show_team = show_team
            mine = Rdv._cq_default_agent()
            rec.show_leila = show_team or mine == "leila"
            rec.show_yamina = show_team or mine == "yamina"
            if show_team:
                rec.viewer_label = (
                    "Vue équipe — Karine voit Leila et Yamina. "
                    "Leila et Yamina ne voient que leurs RDV dans la liste."
                )
            else:
                rec.viewer_label = (
                    "Vos statistiques uniquement. Karine voit le comparatif équipe."
                )
            rdv = Rdv.search(rec._cq_period_domain())
            leila = rec._cq_agent_stats(rdv, "leila")
            yamina = rec._cq_agent_stats(rdv, "yamina")
            rec.leila_total = leila["total"]
            rec.leila_pending = leila["pending"]
            rec.leila_validated = leila["validated"]
            rec.leila_rejected = leila["rejected"]
            rec.leila_rate = leila["rate"]
            rec.leila_done = leila["done"]
            rec.leila_noshow = leila["noshow"]
            rec.yamina_total = yamina["total"]
            rec.yamina_pending = yamina["pending"]
            rec.yamina_validated = yamina["validated"]
            rec.yamina_rejected = yamina["rejected"]
            rec.yamina_rate = yamina["rate"]
            rec.yamina_done = yamina["done"]
            rec.yamina_noshow = yamina["noshow"]

    @api.model
    def action_open(self):
        rec = self.create({})
        rec._compute_kpis()
        return {
            "type": "ir.actions.act_window",
            "name": _("Suivi RDV Leila / Yamina"),
            "res_model": "coins.quebec.rdv.kpi",
            "view_mode": "form",
            "res_id": rec.id,
            "target": "current",
        }

    def action_open_rdv_leila(self):
        return self._action_open_rdv("leila")

    def action_open_rdv_yamina(self):
        return self._action_open_rdv("yamina")

    def _action_open_rdv(self, agent):
        self.ensure_one()
        domain = self._cq_period_domain() + [("agent", "=", agent)]
        return {
            "type": "ir.actions.act_window",
            "name": _("RDV %s") % dict(CQ_RDV_AGENTS).get(agent),
            "res_model": "coins.quebec.rdv",
            "view_mode": "list,kanban,form",
            "domain": domain,
            "context": {"search_default_filter_agent_%s" % agent: 1},
        }
