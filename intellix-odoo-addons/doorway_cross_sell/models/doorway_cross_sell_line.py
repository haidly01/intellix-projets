# -*- coding: utf-8 -*-
from odoo import _, api, fields, models
from odoo.exceptions import AccessError

# Aligné sur les catégories reno (Isolation, Toiture, Thermopompe,
# Portes et fenêtres, Immobilier) + verticaux Coins demandés.
VERTICAL_SELECTION = [
    ("isolation", "Isolation"),
    ("toiture", "Toiture"),
    ("thermopompe", "Thermopompe"),
    ("portes_fenetres", "Portes et fenêtres"),
    ("renovation_generale", "Rénovation générale"),
    ("immobilier", "Immobilier"),
    ("cuisine", "Cuisine"),
    ("courtier_hypothecaire", "Courtier hypothécaire"),
    ("coins_quebec", "Coins Québec"),
    ("coins_marocain", "Coins Marocain"),
]

STATUT_SELECTION = [
    ("transfere", "Transféré"),
    ("rdv_pris", "RDV pris"),
    ("rdv_tenu", "RDV tenu"),
    ("no_show", "No-show"),
    ("qualifie_partenaire", "Qualifié partenaire"),
]

# Traçabilité seulement : coins_* restent sélectionnables, bonus toujours 0.
COINS_VERTICALS = frozenset({"coins_quebec", "coins_marocain"})
RENO_IMMO_VERTICALS = frozenset(
    {
        "isolation",
        "toiture",
        "thermopompe",
        "portes_fenetres",
        "renovation_generale",
        "immobilier",
        "courtier_hypothecaire",
    }
)

BONUS_RENO_DH = 100.0


class DoorwayCrossSellLine(models.Model):
    _name = "doorway.cross.sell.line"
    _description = "Ligne de cross-sell"
    _order = "date_detection desc, id desc"

    lead_origine_id = fields.Many2one(
        "crm.lead",
        string="Lead d'origine",
        required=True,
        ondelete="cascade",
        index=True,
    )
    vertical_origine = fields.Selection(
        VERTICAL_SELECTION,
        string="Vertical d'origine",
    )
    vertical_secondaire = fields.Selection(
        VERTICAL_SELECTION,
        string="Vertical secondaire",
        required=True,
    )
    call_journal_id = fields.Many2one(
        "renovation.twilio.call.log",
        string="Journal d'appel Twilio",
        ondelete="set null",
        index=True,
        help="Lien vers le journal d'appels Twilio réel (DNI). "
        "Le modèle doorway.call.journal n'existe pas sur ce serveur.",
    )
    agent_credite_manuel_id = fields.Many2one(
        "res.users",
        string="Agent crédité (manuel)",
        ondelete="set null",
        index=True,
        help="Surcharge manuelle. Si vide, l'agent crédité reste le commercial du lead. "
        "create_uid du journal n'est pas utilisé (Twilio vide / VICIdial système).",
    )
    agent_credite_manuel_visible = fields.Boolean(
        compute="_compute_agent_credite_manuel_flags",
    )
    agent_credite_manuel_editable = fields.Boolean(
        compute="_compute_agent_credite_manuel_flags",
    )
    agent_credite_id = fields.Many2one(
        "res.users",
        string="Agent crédité",
        compute="_compute_agent_credite_id",
        store=True,
        readonly=True,
    )
    moment_detection = fields.Selection(
        [
            ("appel_initial", "Appel initial"),
            ("suivi_satisfaction", "Suivi satisfaction"),
        ],
        string="Moment de détection",
        default="appel_initial",
        required=True,
    )
    date_detection = fields.Datetime(
        string="Date de détection",
        default=fields.Datetime.now,
        required=True,
    )
    statut = fields.Selection(
        STATUT_SELECTION,
        string="Statut",
        default="transfere",
        required=True,
        index=True,
    )
    currency_id = fields.Many2one(
        "res.currency",
        string="Devise (DH)",
        compute="_compute_currency_id",
        store=True,
    )
    bonus_calcule = fields.Monetary(
        string="Bonus calculé",
        currency_field="currency_id",
        compute="_compute_bonus_and_validation",
        store=True,
    )
    date_validation = fields.Datetime(
        string="Date de validation",
        compute="_compute_bonus_and_validation",
        store=True,
    )
    checklist_key = fields.Char(
        string="Clé checklist",
        index=True,
        copy=False,
        help="Identifiant de la case cochée sur la fiche lead "
        "(travaux_vente / toiture_q1 / reno_q3…). "
        "Pas un nouveau modèle : sert seulement à relier la case à la ligne.",
    )

    @api.model
    def _mad_currency(self):
        mad = self.env.ref("base.MAD", raise_if_not_found=False)
        if mad:
            return mad
        return self.env["res.currency"].search([("name", "=", "MAD")], limit=1)

    @api.depends("lead_origine_id")
    def _compute_currency_id(self):
        mad = self._mad_currency()
        for line in self:
            line.currency_id = mad

    def _system_credit_user_ids(self):
        ids = set()
        for xid in ("base.user_root", "base.public_user"):
            user = self.env.ref(xid, raise_if_not_found=False)
            if user:
                ids.add(user.id)
        return ids

    @api.model
    def _user_can_edit_credit_manuel(self):
        user = self.env.user
        if user.has_group("base.group_system"):
            return True
        if user.has_group("sales_team.group_sale_manager"):
            return True
        if user.has_group("renovation_conciergerie.group_agence_doorway_crm"):
            return True
        login = (user.login or "").strip().lower()
        return login == "karine@agencedoorway.com"

    @api.depends(
        "call_journal_id",
        "call_journal_id.create_uid",
        "lead_origine_id",
        "lead_origine_id.user_id",
    )
    def _compute_agent_credite_manuel_flags(self):
        system_ids = self._system_credit_user_ids()
        can_edit = self._user_can_edit_credit_manuel()
        for line in self:
            journal = line.call_journal_id
            lead_user = line.lead_origine_id.user_id
            if not journal:
                visible = True
            else:
                creator = journal.create_uid
                visible = (
                    not creator
                    or creator.id in system_ids
                    or (lead_user and creator != lead_user)
                )
            line.agent_credite_manuel_visible = visible
            line.agent_credite_manuel_editable = visible and can_edit

    @api.depends(
        "agent_credite_manuel_id",
        "lead_origine_id",
        "lead_origine_id.user_id",
    )
    def _compute_agent_credite_id(self):
        for line in self:
            if line.agent_credite_manuel_id:
                line.agent_credite_id = line.agent_credite_manuel_id
            elif line.lead_origine_id:
                line.agent_credite_id = line.lead_origine_id.user_id
            else:
                line.agent_credite_id = False

    def write(self, vals):
        if "agent_credite_manuel_id" in vals and not self._user_can_edit_credit_manuel():
            raise AccessError(
                _(
                    "Seul un manager ou Karine Barmaki peut modifier "
                    "l'agent crédité manuellement."
                )
            )
        return super().write(vals)

    @api.model_create_multi
    def create(self, vals_list):
        if any(
            vals.get("agent_credite_manuel_id") for vals in vals_list
        ) and not self._user_can_edit_credit_manuel():
            raise AccessError(
                _(
                    "Seul un manager ou Karine Barmaki peut modifier "
                    "l'agent crédité manuellement."
                )
            )
        return super().create(vals_list)

    def _is_triggering(self):
        self.ensure_one()
        return (
            self.vertical_secondaire in RENO_IMMO_VERTICALS
            and self.statut == "qualifie_partenaire"
        )

    def _bonus_amount(self):
        self.ensure_one()
        if self.vertical_secondaire in COINS_VERTICALS:
            return 0.0
        if (
            self.vertical_secondaire in RENO_IMMO_VERTICALS
            and self.statut == "qualifie_partenaire"
        ):
            return BONUS_RENO_DH
        return 0.0

    @api.depends("vertical_secondaire", "statut")
    def _compute_bonus_and_validation(self):
        now = fields.Datetime.now()
        for line in self:
            line.bonus_calcule = line._bonus_amount()
            if line._is_triggering():
                line.date_validation = line.date_validation or now
            else:
                line.date_validation = False

    def vertical_label(self):
        self.ensure_one()
        return dict(VERTICAL_SELECTION).get(
            self.vertical_secondaire, self.vertical_secondaire or ""
        )

    def statut_label(self):
        self.ensure_one()
        return dict(STATUT_SELECTION).get(self.statut, self.statut or "")
