# -*- coding: utf-8 -*-
from odoo import api, fields, models

from .cs_checklist import (
    SLOT_FIELDS,
    VARIABLE_TARGETS,
    checklist_copy,
    checklist_items,
    infer_origin_vertical,
    resolve_item_target,
)
from .doorway_cross_sell_line import VERTICAL_SELECTION

BONUS_CONVERSION_DH = 25.0

ORIGINE_RDV_SELECTION = [
    ("aucun", "Aucun"),
    ("rdv_pris", "RDV pris"),
    ("rdv_tenu", "RDV tenu"),
    ("no_show", "No-show"),
]


class CrmLead(models.Model):
    _inherit = "crm.lead"

    cross_sell_line_ids = fields.One2many(
        "doorway.cross.sell.line",
        "lead_origine_id",
        string="Lignes de cross-sell",
    )
    currency_cross_sell_id = fields.Many2one(
        "res.currency",
        string="Devise cross-sell (DH)",
        compute="_compute_currency_cross_sell_id",
    )
    origine_rdv_statut = fields.Selection(
        ORIGINE_RDV_SELECTION,
        string="Statut RDV d'origine",
        default="aucun",
        required=True,
        index=True,
        help="Statut du rendez-vous d'origine (réno/immo). "
        "Éditable par les agents. Indépendant du vertical secondaire des lignes.",
    )
    bonus_conversion_calcule = fields.Monetary(
        string="Bonus conversion",
        currency_field="currency_cross_sell_id",
        compute="_compute_bonus_conversion",
        store=True,
    )
    date_validation_conversion = fields.Datetime(
        string="Date validation conversion",
        compute="_compute_bonus_conversion",
        store=True,
    )
    cross_sell_statut = fields.Selection(
        [
            ("aucun", "Aucun"),
            ("en_attente", "En attente"),
            ("confirme", "Confirmé"),
        ],
        string="Statut cross-sell",
        compute="_compute_cross_sell_rollup",
        store=True,
    )
    cross_sell_montant_total = fields.Monetary(
        string="Montant cross-sell total",
        currency_field="currency_cross_sell_id",
        compute="_compute_cross_sell_rollup",
        store=True,
    )
    cross_sell_verticaux = fields.Char(
        string="Verticaux cross-sell",
        compute="_compute_cross_sell_rollup",
        store=True,
    )
    cs_origin_kind = fields.Selection(
        [
            ("immobilier", "Immobilier"),
            ("renovation", "Rénovation"),
        ],
        string="Origine checklist (large)",
        compute="_compute_cs_origin_kind",
    )
    cs_origin_vertical = fields.Selection(
        VERTICAL_SELECTION,
        string="Vertical d'origine (checklist)",
        compute="_compute_cs_origin_kind",
    )
    cs_q_travaux_vente = fields.Boolean(
        string="Question cross-sell 1",
        default=False,
        copy=False,
    )
    cs_q_rachat_reno = fields.Boolean(
        string="Question cross-sell 2",
        default=False,
        copy=False,
    )
    cs_q_autre_propriete = fields.Boolean(
        string="Question cross-sell 3",
        default=False,
        copy=False,
    )
    cs_q_target_vertical = fields.Selection(
        VARIABLE_TARGETS,
        string="Vertical mentionné",
        copy=False,
        help="Rénovation générale / cuisine, question 2 : précise le vertical "
        "avant de créer la ligne. Invisible tant que la case n'est pas cochée.",
    )
    cs_origin_badge_label = fields.Char(compute="_compute_cs_checklist_copy")
    cs_checklist_title = fields.Char(compute="_compute_cs_checklist_copy")
    cs_q1_label = fields.Char(compute="_compute_cs_checklist_copy")
    cs_q2_label = fields.Char(compute="_compute_cs_checklist_copy")
    cs_q3_label = fields.Char(compute="_compute_cs_checklist_copy")
    cs_q1_to = fields.Char(compute="_compute_cs_checklist_copy")
    cs_q2_to = fields.Char(compute="_compute_cs_checklist_copy")
    cs_q3_to = fields.Char(compute="_compute_cs_checklist_copy")
    cs_q2_needs_target = fields.Boolean(compute="_compute_cs_checklist_copy")

    def _compute_currency_cross_sell_id(self):
        mad = self.env.ref("base.MAD", raise_if_not_found=False) or self.env[
            "res.currency"
        ].search([("name", "=", "MAD")], limit=1)
        for lead in self:
            lead.currency_cross_sell_id = mad

    @api.depends("origine_rdv_statut")
    def _compute_bonus_conversion(self):
        now = fields.Datetime.now()
        for lead in self:
            if lead.origine_rdv_statut == "rdv_tenu":
                lead.bonus_conversion_calcule = BONUS_CONVERSION_DH
                # Une seule fois : re-save rdv_tenu ne ré-horodate pas.
                # Reset si on quitte rdv_tenu, puis nouveau tampon au retour.
                lead.date_validation_conversion = (
                    lead.date_validation_conversion or now
                )
            else:
                lead.bonus_conversion_calcule = 0.0
                lead.date_validation_conversion = False

    @api.depends(
        "cross_sell_line_ids",
        "cross_sell_line_ids.bonus_calcule",
        "cross_sell_line_ids.statut",
        "cross_sell_line_ids.vertical_secondaire",
        "cross_sell_line_ids.date_validation",
        "bonus_conversion_calcule",
        "origine_rdv_statut",
    )
    def _compute_cross_sell_rollup(self):
        for lead in self:
            lines = lead.cross_sell_line_ids
            conversion = lead.bonus_conversion_calcule or 0.0
            if not lines:
                lead.cross_sell_statut = "aucun"
                lead.cross_sell_montant_total = conversion
                lead.cross_sell_verticaux = False
                continue
            confirmed = any(
                line.bonus_calcule > 0 or line._is_triggering() for line in lines
            )
            lead.cross_sell_statut = "confirme" if confirmed else "en_attente"
            lead.cross_sell_montant_total = conversion + sum(
                lines.mapped("bonus_calcule")
            )
            bits = []
            for line in lines:
                vertical = line.vertical_label()
                statut = line.statut_label()
                if vertical:
                    bits.append("%s (%s)" % (vertical, statut))
            lead.cross_sell_verticaux = ", ".join(bits) or False

    @api.depends(
        "name",
        "immo_meta_lead_id",
        "immo_meta_form_id",
        "source_id",
        "source_id.name",
        "description",
        "service_category_ids",
        "service_category_ids.name",
    )
    def _compute_cs_origin_kind(self):
        for lead in self:
            vertical = lead._cs_origin_vertical()
            lead.cs_origin_vertical = vertical
            lead.cs_origin_kind = (
                "immobilier" if vertical == "immobilier" else "renovation"
            )

    @api.depends(
        "name",
        "immo_meta_lead_id",
        "immo_meta_form_id",
        "source_id",
        "source_id.name",
        "description",
        "service_category_ids",
        "service_category_ids.name",
        "cs_origin_vertical",
    )
    def _compute_cs_checklist_copy(self):
        for lead in self:
            copy = checklist_copy(lead._cs_origin_vertical())
            lead.cs_origin_badge_label = copy["badge"]
            lead.cs_checklist_title = copy["title"]
            lead.cs_q1_label = copy["q1"]
            lead.cs_q2_label = copy["q2"]
            lead.cs_q3_label = copy["q3"]
            lead.cs_q1_to = copy["to1"]
            lead.cs_q2_to = copy["to2"]
            lead.cs_q3_to = copy["to3"]
            lead.cs_q2_needs_target = lead._cs_origin_vertical() in (
                "renovation_generale",
                "cuisine",
            )

    def _cs_origin_kind(self):
        self.ensure_one()
        return "immobilier" if self._cs_origin_vertical() == "immobilier" else "renovation"

    def _cs_origin_vertical(self):
        self.ensure_one()
        cats = []
        if "service_category_ids" in self._fields:
            cats = [name for name in self.service_category_ids.mapped("name") if name]
        source = self.source_id.name if self.source_id else ""
        return infer_origin_vertical(
            name=self.name or "",
            source_label=source,
            category_names=cats,
            is_meta=bool(self.immo_meta_lead_id or self.immo_meta_form_id),
            description=self.description or "",
        )

    def _cs_checklist_verticals(self):
        """Compat : origine fine + cible par défaut de la 1re question."""
        self.ensure_one()
        origin = self._cs_origin_vertical()
        first = checklist_items(origin)[0]
        return origin, first["target"] or "renovation_generale"

    def write(self, vals):
        res = super().write(vals)
        if self.env.context.get("skip_cs_checklist_sync"):
            return res
        watched = [name for name in SLOT_FIELDS if name in vals]
        if "cs_q_target_vertical" in vals:
            watched.append("cs_q_target_vertical")
        if watched:
            self._sync_cross_sell_checklist(watched)
        return res

    def _sync_cross_sell_checklist(self, changed_fields):
        """Coche = crée une ligne transfere / bonus 0. Ne touche pas au calcul 100 DH."""
        Line = self.env["doorway.cross.sell.line"]
        for lead in self:
            origin = lead._cs_origin_vertical()
            for item in checklist_items(origin):
                field_name = item["field"]
                target_field = item.get("target_field")
                if field_name not in changed_fields and target_field not in changed_fields:
                    continue
                checked = bool(lead[field_name])
                target = resolve_item_target(
                    item,
                    lead[target_field] if target_field else None,
                )
                existing = lead.cross_sell_line_ids.filtered(
                    lambda line, checklist_key=item["key"]: line.checklist_key
                    == checklist_key
                )
                if checked and target and not existing:
                    Line.create(
                        {
                            "lead_origine_id": lead.id,
                            "vertical_origine": origin,
                            "vertical_secondaire": target,
                            "statut": "transfere",
                            "checklist_key": item["key"],
                            "moment_detection": "appel_initial",
                        }
                    )
                    add_need = getattr(lead, "_reno_add_need_from_vertical", None)
                    if callable(add_need):
                        add_need(target)
                elif checked and target and existing:
                    draft = existing.filtered(lambda line: line.statut == "transfere")
                    if draft and draft[0].vertical_secondaire != target:
                        draft[0].write({"vertical_secondaire": target})
                    add_need = getattr(lead, "_reno_add_need_from_vertical", None)
                    if callable(add_need):
                        add_need(target)
                elif checked and not target:
                    draft = existing.filtered(lambda line: line.statut == "transfere")
                    if draft:
                        draft.unlink()
                elif not checked and existing:
                    advanced = existing.filtered(lambda line: line.statut != "transfere")
                    draft = existing.filtered(lambda line: line.statut == "transfere")
                    if advanced:
                        lead.with_context(skip_cs_checklist_sync=True).write(
                            {field_name: True}
                        )
                    elif draft:
                        draft.unlink()
