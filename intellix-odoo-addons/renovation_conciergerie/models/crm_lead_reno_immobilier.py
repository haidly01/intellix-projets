# -*- coding: utf-8 -*-
from datetime import timedelta

from odoo import api, fields, models

RENO_IMMO_TEAM_XMLIDS = (
    "renovation_conciergerie.crm_team_renovation",
    "renovation_conciergerie.crm_team_immobilier",
)

STATUS_FROM_STAGE = (
    (("gagne", "gagné", "won"), "gagne"),
    (("perdu", "lost"), "perdu"),
    (("relance", "à relancer", "a relancer", "rappel"), "a_relancer"),
    (("contacté", "contacte", "contact", "en contact", "social", "retell", "site"), "en_contact"),
    (("attrib", "assign", "qualif"), "attribue"),
    (("nouveau", "new", "à traiter", "a traiter"), "nouveau"),
)


class CrmLeadRenoImmobilier(models.Model):
    _inherit = "crm.lead"

    reno_immo_lead = fields.Boolean(
        compute="_compute_reno_immo_lead",
        search="_search_reno_immo_lead",
    )
    reno_gestion_status = fields.Selection(
        [
            ("nouveau", "Nouveau"),
            ("en_contact", "Contacté"),
            ("attribue", "Attribué"),
            ("a_relancer", "Relance"),
            ("gagne", "Gagné"),
            ("perdu", "Perdu"),
        ],
        string="Statut Réno Immobilier",
        compute="_compute_reno_gestion_status",
        inverse="_inverse_reno_gestion_status",
        store=True,
        index=True,
        group_expand="_group_expand_reno_gestion_status",
    )
    reno_source_label = fields.Char(
        string="Source / équipe",
        compute="_compute_reno_source_label",
    )
    reno_card_title = fields.Char(
        string="Titre carte",
        compute="_compute_reno_card_display",
    )
    reno_card_subtitle = fields.Char(
        string="Sous-titre carte",
        compute="_compute_reno_card_display",
    )
    reno_category_label = fields.Char(
        string="Catégorie",
        compute="_compute_reno_card_display",
    )
    reno_source_paused = fields.Boolean(
        string="Source en pause",
        compute="_compute_reno_source_paused",
        search="_search_reno_source_paused",
    )
    reno_relance_due = fields.Boolean(
        string="À relancer",
        compute="_compute_reno_relance_due",
        store=True,
    )

    def _group_expand_reno_gestion_status(self, statuses, domain):
        return [key for key, _label in self._fields["reno_gestion_status"].selection]

    def _reno_immo_team_ids(self):
        ids = []
        for xmlid in RENO_IMMO_TEAM_XMLIDS:
            team = self.env.ref(xmlid, raise_if_not_found=False)
            if team:
                ids.append(team.id)
        return ids

    @api.depends("team_id")
    def _compute_reno_immo_lead(self):
        team_ids = set(self._reno_immo_team_ids())
        for lead in self:
            lead.reno_immo_lead = bool(lead.team_id.id in team_ids)

    def _search_reno_immo_lead(self, operator, value):
        team_ids = self._reno_immo_team_ids()
        wanted = bool(value) if operator in ("=", "!=") else True
        if operator in ("=",) and not wanted:
            return [("team_id", "not in", team_ids)]
        return [("team_id", "in", team_ids)]

    def _reno_status_from_stage(self, stage):
        name = (stage.name or "").lower()
        for needles, status in STATUS_FROM_STAGE:
            if any(n in name for n in needles):
                return status
        return "nouveau"

    @api.depends("stage_id", "stage_id.name")
    def _compute_reno_gestion_status(self):
        for lead in self:
            lead.reno_gestion_status = lead._reno_status_from_stage(lead.stage_id)

    def _inverse_reno_gestion_status(self):
        for lead in self:
            stage = lead._reno_stage_for_status(lead.reno_gestion_status)
            if stage and lead.stage_id != stage:
                lead.stage_id = stage.id

    def _reno_stage_for_status(self, status):
        self.ensure_one()
        stages = self.env["crm.stage"].search(
            [
                "|",
                ("team_ids", "in", self.team_id.ids),
                ("team_ids", "=", False),
            ]
        )
        wanted = {
            "nouveau": ("nouveau", "à traiter", "new"),
            "attribue": ("attrib", "assign", "qualif"),
            "en_contact": ("contact", "social", "retell"),
            "a_relancer": ("relance", "rappel"),
            "gagne": ("gagné", "gagne", "won"),
            "perdu": ("perdu", "lost"),
        }.get(status or "", ())
        for stage in stages:
            name = (stage.name or "").lower()
            if any(w in name for w in wanted):
                return stage
        return self.env["crm.stage"]

    @api.depends("team_id", "team_id.name", "source_id", "source_id.name")
    def _compute_reno_source_label(self):
        for lead in self:
            bits = [
                lead.team_id.name or "",
                lead.source_id.name or "",
            ]
            lead.reno_source_label = " · ".join([b for b in bits if b]) or "—"

    @api.depends(
        "name",
        "contact_name",
        "partner_id",
        "partner_id.name",
        "phone",
        "team_id",
        "team_id.name",
        "source_id",
        "source_id.name",
        "reno_source_label",
    )
    def _compute_reno_card_display(self):
        for lead in self:
            title = (lead.contact_name or "").strip() or (
                lead.partner_id.name if lead.partner_id else ""
            )
            if not title or title.replace(" ", "").replace("-", "").isdigit():
                title = (lead.name or "").strip() or (lead.phone or "Sans nom")
            lead.reno_card_title = title
            source = (lead.source_id.name or "").strip()
            team = (lead.team_id.name or "").strip()
            subtitle_bits = [b for b in (source, team) if b]
            lead.reno_card_subtitle = " · ".join(subtitle_bits) or "—"
            lead.reno_category_label = team or source or "—"

    def _reno_fold_source(self, text):
        import unicodedata

        raw = unicodedata.normalize("NFD", text or "")
        folded = "".join(c for c in raw if unicodedata.category(c) != "Mn")
        return folded.lower().replace(" ", "")

    def _reno_is_paused_source(self, lead):
        blob = self._reno_fold_source(
            " ".join(
                [
                    lead.name or "",
                    lead.source_id.name or "",
                    getattr(lead, "reno_source_label", None) or "",
                ]
            )
        )
        return "renofacile" in blob

    @api.depends("name", "source_id", "source_id.name")
    def _compute_reno_source_paused(self):
        for lead in self:
            lead.reno_source_paused = self._reno_is_paused_source(lead)

    def _search_reno_source_paused(self, operator, value):
        domain = [
            "|",
            "|",
            "|",
            ("name", "ilike", "RénoFacile"),
            ("name", "ilike", "Renofacile"),
            ("source_id.name", "ilike", "RénoFacile"),
            ("source_id.name", "ilike", "Renofacile"),
        ]
        paused_ids = self.with_context(active_test=False).search(domain).ids
        wanted = bool(value) if operator in ("=", "!=") else True
        if operator == "!=":
            wanted = not wanted
        if wanted:
            return [("id", "in", paused_ids or [0])]
        return [("id", "not in", paused_ids or [0])]

    @api.depends("reno_gestion_status", "date_last_stage_update", "write_date", "create_date")
    def _compute_reno_relance_due(self):
        for lead in self:
            lead.reno_relance_due = (
                lead.reno_gestion_status == "a_relancer" or lead._reno_is_stale()
            )

    def _reno_relance_business_days(self):
        raw = (
            self.env["ir.config_parameter"]
            .sudo()
            .get_param("renovation_conciergerie.relance_business_days", "3")
        )
        try:
            return max(1, int(raw))
        except (TypeError, ValueError):
            return 3

    def _reno_is_stale(self):
        self.ensure_one()
        start = self.date_last_stage_update or self.write_date or self.create_date
        if not start:
            return False
        start_d = fields.Datetime.context_timestamp(self, start).date()
        today = fields.Date.context_today(self)
        return self._reno_business_days_between(start_d, today) >= self._reno_relance_business_days()

    @staticmethod
    def _reno_business_days_between(start, end):
        if end < start:
            return 0
        days = 0
        cursor = start
        while cursor < end:
            cursor += timedelta(days=1)
            if cursor.weekday() < 5:
                days += 1
        return days
