# -*- coding: utf-8 -*-
"""Campagne du Configurateur de Campagnes Extracteur (INTLX-EXT).

Modèle dédié au configurateur no-code 4 étapes : il persiste la configuration
métier, l'avis Claude et le résultat du déploiement n8n. Distinct de
``doorway.campagne.extraction`` (qui gère l'extraction synchrone + crédits) afin
d'isoler proprement la logique « génération de workflow n8n ».

Expose les méthodes appelées par l'UI OWL :
- ``get_sources(pays, secteur)``
- ``preview_campaign(config)``  (Claude)
- ``deploy_campaign(config)``   (Claude + création n8n)
"""
import json
import logging

from odoo import _, api, fields, models

from odoo.addons.doorway_leads_bruts.services import claude_advisor, n8n_builder
from odoo.addons.doorway_leads_bruts.models.source_registry import (
    COUT_FORMULE_PAR_LEAD,
)

_logger = logging.getLogger(__name__)

PAYS_SELECTION = [
    ("france", "France"),
    ("canada", "Canada"),
    ("maroc", "Maroc"),
    ("belgique", "Belgique"),
]
SECTEUR_SELECTION = [
    ("assurance", "Assurance"),
    ("renovation", "Rénovation"),
    ("immobilier", "Immobilier"),
    ("telecom", "Télécom"),
    ("centres_appels", "Centres d'appels"),
]
DEFAULT_COUT_PAR_LEAD = 0.18
MARGE_REVENU_CLIENT = 0.43  # revenus client estimés = total / 0.43 (≈ 57% marge)


class DoorwayExtracteurCampaign(models.Model):
    _name = "doorway.extracteur.campaign"
    _description = "Campagne configurée (Configurateur INTLX-EXT)"
    _inherit = ["mail.thread"]
    _order = "create_date desc"

    name = fields.Char(string="Nom campagne", required=True, tracking=True)
    pays = fields.Selection(PAYS_SELECTION, required=True, default="france", tracking=True)
    secteur = fields.Selection(SECTEUR_SELECTION, required=True, default="assurance")
    zone = fields.Char(string="Zone géographique")
    cible = fields.Char(string="Cible")
    objectif_leads = fields.Integer(string="Objectif leads", default=100)
    budget_mensuel = fields.Float(string="Budget mensuel", default=500.0)
    frequence_heures = fields.Integer(string="Fréquence (heures)", default=24)
    signal_intention = fields.Char(string="Signal d'intention")
    notes_client = fields.Text(string="Notes client (pour Claude)")

    source_ids = fields.Many2many(
        "doorway.source.registry",
        "extracteur_campaign_source_rel",
        "campaign_id",
        "source_id",
        string="Sources sélectionnées",
    )

    state = fields.Selection(
        [
            ("draft", "Brouillon"),
            ("advised", "Conseillée IA"),
            ("deployed", "Déployée (n8n)"),
            ("error", "Erreur"),
        ],
        default="draft",
        tracking=True,
    )
    claude_advice = fields.Text(string="Recommandation Claude (JSON)")
    cout_estime_par_lead = fields.Float(string="Coût estimé / lead", digits=(16, 4))
    n8n_workflow_id = fields.Char(string="ID workflow n8n", readonly=True)
    n8n_workflow_name = fields.Char(string="Nom workflow n8n", readonly=True)
    n8n_url = fields.Char(string="URL n8n", readonly=True)
    error_message = fields.Text(readonly=True)
    user_id = fields.Many2one("res.users", default=lambda self: self.env.user)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    @api.model
    def _config_from_dict(self, config):
        """Normalise le dict reçu de l'UI."""
        config = config or {}
        return {
            "nom_campagne": (config.get("nom_campagne") or config.get("name") or "").strip(),
            "pays": config.get("pays") or "france",
            "secteur": config.get("secteur") or "assurance",
            "zone": (config.get("zone") or "").strip(),
            "cible": (config.get("cible") or "").strip(),
            "objectif_leads": int(config.get("objectif_leads") or 0),
            "budget_mensuel": float(config.get("budget_mensuel") or 0),
            "frequence_heures": int(config.get("frequence_heures") or 24),
            "signal_intention": (config.get("signal_intention") or "").strip(),
            "notes_client": (config.get("notes_client") or "").strip(),
            "source_ids": config.get("source_ids") or [],
        }

    @api.model
    def _resolve_sources(self, source_ids):
        """Résout les ids registre envoyés par l'UI en enregistrements + dicts."""
        registry = self.env["doorway.source.registry"]
        records = registry.browse([int(i) for i in source_ids if i]).exists()
        return records, [r._to_configurator_dict() for r in records]

    # ------------------------------------------------------------------
    # API appelée par l'UI OWL
    # ------------------------------------------------------------------
    @api.model
    def get_sources(self, pays, secteur):
        """Liste des sources disponibles pour un pays + secteur."""
        return self.env["doorway.source.registry"].get_configurator_sources(
            pays, secteur
        )

    @api.model
    def preview_campaign(self, config):
        """Étape 2 : appelle Claude pour la recommandation (sans déployer)."""
        cfg = self._config_from_dict(config)
        sources = self.env["doorway.source.registry"].get_configurator_sources(
            cfg["pays"], cfg["secteur"]
        )
        advice, message = claude_advisor.advise_campaign(self.env, cfg, sources)
        if advice is None:
            return {
                "success": False,
                "message": message,
                "claude_available": claude_advisor.is_available(self.env),
            }
        return {
            "success": True,
            "message": message,
            "advice": advice,
            "recommended_ids": self._map_advice_to_registry_ids(advice, sources),
        }

    @api.model
    def _map_advice_to_registry_ids(self, advice, sources):
        """Convertit les source_id recommandés par Claude en ids registre."""
        by_ext = {s.get("id"): s.get("registry_id") for s in sources}
        ids = []
        for rec in (advice or {}).get("sources_recommandees") or []:
            reg_id = by_ext.get(rec.get("source_id"))
            if reg_id:
                ids.append(reg_id)
        return ids

    def _compute_cout_par_lead(self, advice, source_records):
        """Coût/lead : avis Claude > moyenne des formules sources > défaut."""
        if advice and advice.get("cout_estime_par_lead"):
            try:
                return round(float(advice["cout_estime_par_lead"]), 4)
            except (TypeError, ValueError):
                pass
        costs = [
            COUT_FORMULE_PAR_LEAD.get(s.cout_estime)
            for s in source_records
            if s.cout_estime in COUT_FORMULE_PAR_LEAD
        ]
        costs = [c for c in costs if c]
        if costs:
            return round(sum(costs) / len(costs), 4)
        return DEFAULT_COUT_PAR_LEAD

    @api.model
    def deploy_campaign(self, config):
        """Étape 4 : persiste la campagne, (re)appelle Claude, déploie n8n."""
        cfg = self._config_from_dict(config)
        if not cfg["nom_campagne"]:
            return {"success": False, "message": _("Le nom de campagne est requis.")}

        source_records, source_dicts = self._resolve_sources(cfg["source_ids"])

        advice, advice_msg = claude_advisor.advise_campaign(
            self.env, cfg, source_dicts
        )
        cout_par_lead = self._compute_cout_par_lead(advice, source_records)

        campaign = self.create({
            "name": cfg["nom_campagne"],
            "pays": cfg["pays"],
            "secteur": cfg["secteur"],
            "zone": cfg["zone"],
            "cible": cfg["cible"],
            "objectif_leads": cfg["objectif_leads"],
            "budget_mensuel": cfg["budget_mensuel"],
            "frequence_heures": cfg["frequence_heures"],
            "signal_intention": cfg["signal_intention"],
            "notes_client": cfg["notes_client"],
            "source_ids": [(6, 0, source_records.ids)],
            "claude_advice": json.dumps(advice, ensure_ascii=False) if advice else False,
            "cout_estime_par_lead": cout_par_lead,
            "state": "advised" if advice else "draft",
        })

        icp = self.env["ir.config_parameter"].sudo()
        n8n_campagne = {
            "campagne_id": campaign.id,
            "nom_campagne": cfg["nom_campagne"],
            "pays": cfg["pays"],
            "secteur": cfg["secteur"],
            "zone": cfg["zone"],
            "cible": cfg["cible"],
            "objectif_leads": cfg["objectif_leads"],
            "frequence_heures": cfg["frequence_heures"],
            "odoo_url": n8n_builder.get_odoo_base_url(self.env),
            "crm_tag_id": int(icp.get_param(n8n_builder.CRM_TAG_PARAM) or 0),
            "crm_team_id": int(icp.get_param(n8n_builder.CRM_TEAM_PARAM) or 0),
        }
        result = n8n_builder.build_and_deploy(
            self.env, n8n_campagne, source_dicts, advice
        )

        if result.get("success"):
            campaign.write({
                "state": "deployed",
                "n8n_workflow_id": result.get("workflow_id"),
                "n8n_workflow_name": result.get("workflow_name"),
                "n8n_url": result.get("n8n_url"),
                "error_message": False,
            })
            campaign.message_post(
                body=_(
                    "Workflow n8n créé (INACTIF) : %(name)s — à vérifier puis activer."
                ) % {"name": result.get("workflow_name")}
            )
            return {
                "success": True,
                "campaign_id": campaign.id,
                "workflow_id": result.get("workflow_id"),
                "workflow_name": result.get("workflow_name"),
                "n8n_url": result.get("n8n_url"),
                "advice": advice,
                "cout_estime_par_lead": cout_par_lead,
                "message": _("Campagne déployée. Workflow créé en mode INACTIF."),
                "prochaines_etapes": [
                    _("Vérifier le workflow dans n8n"),
                    _("Ouvrir l'URL du workflow"),
                    _("Activer le workflow une fois vérifié"),
                ],
            }

        campaign.write({
            "state": "error",
            "error_message": result.get("error"),
        })
        return {
            "success": False,
            "campaign_id": campaign.id,
            "advice": advice,
            "cout_estime_par_lead": cout_par_lead,
            "workflow_name": result.get("workflow_name"),
            "message": result.get("error") or _("Échec du déploiement n8n."),
            "claude_message": advice_msg,
        }
