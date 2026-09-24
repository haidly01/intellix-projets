# -*- coding: utf-8 -*-
from odoo import api, fields, models


class CrmLeadEnergie(models.Model):
    _inherit = "crm.lead"

    energie_site_source = fields.Selection(
        [
            ("icithermopompe", "IciThermopompe.com"),
            ("isolationqc", "IsolationQC.com"),
            ("portesetfenetresqc", "PortesFenetresQC.com"),
            ("inconnu", "Inconnu"),
        ],
        string="Site source énergie",
        tracking=True,
    )
    energie_projet_type = fields.Selection(
        [
            ("thermopompe", "Thermopompe"),
            ("isolation", "Isolation"),
            ("portes_fenetres", "Portes & Fenêtres"),
            ("multi", "Projet multiple"),
        ],
        string="Type de projet énergie",
        tracking=True,
    )
    energie_chauffage_actuel = fields.Selection(
        [
            ("electrique", "Électrique"),
            ("mazout", "Mazout"),
            ("propane", "Propane"),
            ("gaz_naturel", "Gaz naturel"),
            ("autre", "Autre"),
        ],
        string="Chauffage actuel",
    )
    energie_subvention_estimee = fields.Float(string="Subvention estimée ($)")
    energie_programmes_eligibles = fields.Char(string="Programmes éligibles")
    energie_type_thermopompe = fields.Selection(
        [
            ("murale", "Murale (monosplit)"),
            ("multi_zones", "Multisplit"),
            ("centrale", "Centrale"),
            ("geothermique", "Géothermique"),
        ],
        string="Type thermopompe",
    )
    energie_zones_isolation = fields.Char(string="Zones à isoler")
    energie_evaluation_renoclimat = fields.Boolean(string="Évaluation Rénoclimat faite")
    energie_nb_ouvertures = fields.Integer(string="Nombre d'ouvertures")
    energie_type_vitrage_actuel = fields.Selection(
        [
            ("simple", "Simple vitrage"),
            ("double", "Double vitrage"),
            ("triple", "Triple vitrage"),
            ("inconnu", "Inconnu"),
        ],
        string="Vitrage actuel",
    )
    energie_ia_score = fields.Selection(
        [("hot", "Hot"), ("warm", "Warm"), ("cold", "Cold")],
        string="Score IA Énergie",
        tracking=True,
    )
    energie_ia_score_numeric = fields.Integer(string="Score numérique /100", tracking=True)
    energie_elevenlabs_conv_id = fields.Char(
        string="ElevenLabs Conv ID (énergie)", index=True
    )
    energie_call_transcript = fields.Text(string="Transcript appel énergie")
    energie_transfer_at = fields.Datetime(string="Transfert humain le")
    energie_nurture_active = fields.Boolean(string="Séquence nurture active", default=False)
    energie_total_call_attempts = fields.Integer(string="Tentatives d'appel", default=0)
    energie_do_not_call = fields.Boolean(string="Ne plus appeler (DNC)")
    energie_meta_page_id = fields.Char(
        string="ID page Facebook (Lead Ads)",
        index=True,
        help="Page Meta reliée à Énergie Pro (96229525030304 ou 1004010452788312).",
    )
