# -*- coding: utf-8 -*-
from odoo import _, api, fields, models
from odoo.exceptions import UserError


class DoorwayLeadsBruts(models.Model):
    _name = "doorway.leads.bruts"
    _description = "Lead brut extrait"
    _order = "create_date desc"
    _inherit = ["mail.thread"]

    name = fields.Char(string="Entreprise / Contact", required=True, tracking=True)
    phone = fields.Char(tracking=True)
    email = fields.Char(tracking=True)
    website = fields.Char()
    address = fields.Char()
    city = fields.Char()
    region = fields.Char()
    source_id = fields.Many2one("doorway.source.registry", string="Source", index=True)
    source_key = fields.Char(index=True)
    source_url = fields.Char()
    dedup_key = fields.Char(
        string="Clé anti-doublon",
        index=True,
        copy=False,
        help="Téléphone, email ou nom normalisé — unique sur toutes les extractions.",
    )
    campagne_id = fields.Many2one(
        "doorway.campagne.extraction",
        string="Campagne",
        ondelete="cascade",
        index=True,
    )
    state = fields.Selection(
        [
            ("brut", "Brut"),
            ("nettoye", "Nettoyé IA"),
            ("qualifie", "Qualifié"),
            ("importe", "Importé CRM"),
            ("rejete", "Rejeté"),
        ],
        default="brut",
        tracking=True,
    )
    score_qualite = fields.Integer(string="Score qualité (0-100)")
    has_phone = fields.Boolean(compute="_compute_has_contact", store=True)
    has_email = fields.Boolean(compute="_compute_has_contact", store=True)
    crm_lead_id = fields.Many2one("crm.lead", string="Opportunité CRM", copy=False)
    notes = fields.Text()
    raw_data = fields.Text(string="Données brutes JSON")

    _sql_constraints = [
        (
            "dedup_key_uniq",
            "unique(dedup_key)",
            "Ce lead existe déjà dans une extraction passée (même téléphone, email ou nom).",
        ),
    ]

    @api.model
    def _prepare_dedup_key(self, vals):
        Campagne = self.env["doorway.campagne.extraction"]
        return Campagne._lead_dedup_key(vals)

    @api.model_create_multi
    def create(self, vals_list):
        Campagne = self.env["doorway.campagne.extraction"]
        clean_vals = []
        for vals in vals_list:
            vals = dict(vals)
            if not vals.get("dedup_key"):
                vals["dedup_key"] = Campagne._lead_dedup_key(vals)
            if not vals.get("dedup_key"):
                continue
            if self.search_count([("dedup_key", "=", vals["dedup_key"])]):
                continue
            clean_vals.append(vals)
        if not clean_vals:
            return self.browse()
        return super().create(clean_vals)

    @api.depends("phone", "email")
    def _compute_has_contact(self):
        for rec in self:
            rec.has_phone = bool((rec.phone or "").strip())
            rec.has_email = bool((rec.email or "").strip())

    def action_import_crm(self):
        """Importe le lead vers crm.lead — pipeline Marketing Doorway (Zakaria)."""
        Lead = self.env["crm.lead"]
        Exporter = self.env["doorway.leads.bruts.crm.export"]
        for rec in self:
            if rec.crm_lead_id:
                continue
            if not (rec.phone or "").strip() and not (rec.email or "").strip():
                raise UserError(
                    _("Le lead « %s » doit avoir au moins un téléphone ou un email.")
                    % rec.name
                )
            vals = Exporter.prepare_crm_vals_from_lead_brut(rec)
            crm = Lead.sudo().create(vals)
            rec.write({"crm_lead_id": crm.id, "state": "importe"})
