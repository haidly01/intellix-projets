# -*- coding: utf-8 -*-
import json

from odoo import _, api, fields, models
from odoo.exceptions import UserError


class DoorwayExtractionWizard(models.TransientModel):
    _name = "doorway.extraction.wizard"
    _description = "Wizard extraction leads — 3 étapes"

    etape_courante = fields.Integer(default=1)
    name = fields.Char(string="Nom de la campagne", required=True)
    mot_cle = fields.Char(string="Mot-clé / Secteur", required=True)
    zone_geographique = fields.Selection(
        [
            ("maroc", "🇲🇦 Maroc"),
            ("france", "🇫🇷 France"),
            ("belgique", "🇧🇪 Belgique"),
            ("espagne", "🇪🇸 Espagne"),
            ("suisse", "🇨🇭 Suisse"),
            ("canada", "🇨🇦 Canada"),
            ("usa", "🇺🇸 États-Unis"),
            ("tunisie", "🇹🇳 Tunisie"),
            ("autre", "🌍 Autre pays"),
        ],
        default="france",
        required=True,
    )
    ville_region = fields.Char(string="Ville / Région", required=True)
    rayon_km = fields.Integer(default=10)
    volume_possible = fields.Integer(
        string="Volume possible",
        readonly=True,
        help="Maximum de leads estimé selon les sources sélectionnées.",
    )
    volume_cible = fields.Integer(
        string="Quantité à extraire",
        default=0,
        help="Nombre de leads à extraire (par défaut le maximum possible).",
    )
    sources_ids = fields.Many2many("doorway.source.registry", string="Sources")
    cout_credits_estime = fields.Float(digits=(16, 4), readonly=True)
    cout_detail_json = fields.Text(readonly=True)
    leads_estime_min = fields.Integer(readonly=True)
    leads_estime_max = fields.Integer(readonly=True)
    duree_estime_min = fields.Integer(readonly=True)
    duree_estime_max = fields.Integer(readonly=True)
    solde_suffisant = fields.Boolean(readonly=True)
    balance_credits = fields.Float(readonly=True, digits=(16, 4))
    balance_after = fields.Float(readonly=True, digits=(16, 4))
    prix_ht = fields.Float(readonly=True, digits=(16, 4))
    prix_ttc = fields.Float(readonly=True, digits=(16, 4))
    mode_commercial = fields.Boolean(readonly=True)
    campagne_id = fields.Many2one("doorway.campagne.extraction", readonly=True)
    marge_pct = fields.Float(default=40.0)
    extractions_passees_count = fields.Integer(
        string="Extractions passées (même cible)",
        compute="_compute_historique_info",
    )
    leads_base_count = fields.Integer(
        string="Leads déjà en base",
        compute="_compute_historique_info",
    )
    avertissement_historique = fields.Text(
        compute="_compute_historique_info",
    )

    @api.depends("mot_cle", "ville_region", "zone_geographique")
    def _compute_historique_info(self):
        Campagne = self.env["doorway.campagne.extraction"]
        Leads = self.env["doorway.leads.bruts"]
        for wiz in self:
            sim = Campagne.count_similar_past_extractions(
                wiz.mot_cle,
                wiz.ville_region,
                wiz.zone_geographique,
            )
            wiz.extractions_passees_count = sim
            wiz.leads_base_count = Leads.search_count([])
            if sim and wiz.leads_base_count:
                wiz.avertissement_historique = _(
                    "%(sim)s extraction(s) passée(s) sur ce mot-clé et cette zone. "
                    "%(total)s lead(s) déjà en base — les doublons (téléphone, email ou nom) "
                    "seront automatiquement ignorés."
                ) % {"sim": sim, "total": wiz.leads_base_count}
            elif sim:
                wiz.avertissement_historique = _(
                    "%(sim)s extraction(s) passée(s) sur ce mot-clé et cette zone. "
                    "Les contacts déjà extraits ne seront pas réimportés."
                ) % {"sim": sim}
            elif wiz.leads_base_count:
                wiz.avertissement_historique = _(
                    "%(total)s lead(s) déjà en base — les doublons seront ignorés."
                ) % {"total": wiz.leads_base_count}
            else:
                wiz.avertissement_historique = False

    @api.onchange("zone_geographique")
    def _onchange_zone(self):
        if self.zone_geographique:
            sources = self.env["doorway.source.registry"].get_sources_for_zone(
                self.zone_geographique
            )
            annuaires = sources.filtered(lambda s: s.type_source in ("annuaire", "gmaps"))
            classees = sources.filtered(lambda s: s.type_source == "classees")
            default = (annuaires[:2] | classees[:2]).ids
            self.sources_ids = [(6, 0, default)]
            self._apply_volume_defaults()

    @api.onchange("sources_ids")
    def _onchange_sources_ids(self):
        self._apply_volume_defaults()

    def _apply_volume_defaults(self):
        Campagne = self.env["doorway.campagne.extraction"]
        possible = Campagne.compute_volume_possible(self.sources_ids)
        self.volume_possible = possible
        if not self.volume_cible or self.volume_cible > possible:
            self.volume_cible = possible

    def _check_volume_cible(self):
        self.ensure_one()
        if not self.volume_possible:
            raise UserError(_("Aucun lead possible avec les sources sélectionnées."))
        if self.volume_cible <= 0:
            raise UserError(_("Indiquez une quantité à extraire supérieure à 0."))
        if self.volume_cible > self.volume_possible:
            raise UserError(
                _(
                    "La quantité à extraire (%(qty)s) dépasse le volume possible (%(max)s)."
                )
                % {"qty": self.volume_cible, "max": self.volume_possible}
            )

    def action_etape_suivante(self):
        self.ensure_one()
        if self.etape_courante == 1:
            if not self.name or not self.mot_cle or not self.ville_region:
                raise UserError(_("Remplissez tous les champs obligatoires."))
            self.etape_courante = 2
            if not self.sources_ids:
                self._onchange_zone()
            else:
                self._apply_volume_defaults()
        elif self.etape_courante == 2:
            if not self.sources_ids:
                raise UserError(_("Sélectionnez au moins une source."))
            self._apply_volume_defaults()
            self._check_volume_cible()
            self._calculer_cout()
            self.etape_courante = 3
        return self._reopen_wizard()

    def action_etape_precedente(self):
        self.ensure_one()
        if self.etape_courante > 1:
            self.etape_courante -= 1
        return self._reopen_wizard()

    def _calculer_cout(self):
        Campagne = self.env["doorway.campagne.extraction"]
        result = Campagne.calculer_cout_estime(
            self.zone_geographique,
            self.sources_ids,
            self.volume_cible,
            self.marge_pct,
        )
        self.write({
            "volume_possible": result["volume_possible"],
            "cout_credits_estime": result["total_credits"],
            "cout_detail_json": json.dumps(result, ensure_ascii=False),
            "leads_estime_min": result["leads_estime_min"],
            "leads_estime_max": result["leads_estime_max"],
            "duree_estime_min": result["duree_estime_min"],
            "duree_estime_max": result["duree_estime_max"],
            "solde_suffisant": result["solde_suffisant"],
            "balance_credits": result["balance_credits"],
            "balance_after": result["balance_after"],
            "prix_ht": result["prix_ht"],
            "prix_ttc": result["prix_ttc"],
            "mode_commercial": result["mode_commercial"],
        })

    @api.model
    def wizard_compute_cost(self, wizard_data):
        """RPC pour recalcul temps réel depuis le JS."""
        Campagne = self.env["doorway.campagne.extraction"]
        sources = self.env["doorway.source.registry"].browse(
            wizard_data.get("source_ids", [])
        )
        volume_possible = Campagne.compute_volume_possible(sources)
        volume_cible = int(wizard_data.get("volume_cible") or 0)
        if not volume_cible or volume_cible > volume_possible:
            volume_cible = volume_possible
        return Campagne.calculer_cout_estime(
            wizard_data.get("zone_geographique"),
            sources,
            volume_cible or 1,
            float(wizard_data.get("marge_pct") or 40),
        )

    def action_valider_lancer(self):
        self.ensure_one()
        if not self.solde_suffisant:
            raise UserError(_("Solde de crédits insuffisant pour cette extraction."))
        campagne = self.env["doorway.campagne.extraction"].create({
            "name": self.name,
            "mot_cle": self.mot_cle,
            "zone_geographique": self.zone_geographique,
            "ville_region": self.ville_region,
            "rayon_km": self.rayon_km,
            "volume_possible": self.volume_possible,
            "volume_cible": self.volume_cible,
            "sources_selectionnees": [(6, 0, self.sources_ids.ids)],
            "marge_pct": self.marge_pct,
            "cout_credits_estime": self.cout_credits_estime,
            "cout_detail_json": self.cout_detail_json,
            "leads_estime_min": self.leads_estime_min,
            "leads_estime_max": self.leads_estime_max,
            "duree_estime_min": self.duree_estime_min,
            "duree_estime_max": self.duree_estime_max,
        })
        campagne.action_lancer_extraction()
        self.campagne_id = campagne.id
        return {
            "type": "ir.actions.act_window",
            "res_model": "doorway.campagne.extraction",
            "res_id": campagne.id,
            "view_mode": "form",
            "target": "current",
        }

    def _reopen_wizard(self):
        return {
            "type": "ir.actions.act_window",
            "res_model": "doorway.extraction.wizard",
            "res_id": self.id,
            "view_mode": "form",
            "target": "new",
        }
