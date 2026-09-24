# -*- coding: utf-8 -*-
from odoo import api, fields, models


class CrmLeadImmoMeta(models.Model):
    _inherit = "crm.lead"

    immo_ia_score = fields.Selection(
        [
            ("hot", "Hot"),
            ("warm", "Warm"),
            ("cold", "Cold"),
        ],
        string="Score IA immobilier",
        tracking=True,
    )
    immo_ia_score_numeric = fields.Integer(string="Score numérique /100", tracking=True)
    elevenlabs_conversation_id = fields.Char(
        string="ElevenLabs conversation ID",
        index=True,
    )
    immo_call_transcript = fields.Text(string="Transcript appel IA")
    immo_property_type = fields.Char(
        string="Type de maison",
        help="Réponse formulaire (bungalow, cottage, condo…). "
        "Indépendant du type de toit réno.",
    )
    immo_selling_timeline = fields.Char(string="Délai de vente")
    immo_estimated_value = fields.Char(string="Valeur estimée (client)")
    immo_is_owner_confirmed = fields.Boolean(string="Propriétaire confirmé")
    immo_other_agents = fields.Boolean(string="Autres courtiers contactés")
    immo_meta_mapped_keys = fields.Char(
        string="Clés Meta mappées",
        copy=False,
        help="Liste des questions Meta effectivement mappées à la création "
        "(property_type,selling_timeline,estimated_value,is_owner,other_agents).",
    )
    immo_show_raw_meta = fields.Boolean(
        string="Voir la réponse brute Meta",
        default=False,
    )
    immo_is_meta_lead = fields.Boolean(compute="_compute_immo_meta_enrich_badges")
    immo_property_type_enrich = fields.Selection(
        [
            ("enriched", "Enrichi automatiquement"),
            ("failed", "Non enrichi — vérifier manuellement"),
        ],
        compute="_compute_immo_meta_enrich_badges",
    )
    immo_selling_timeline_enrich = fields.Selection(
        [
            ("enriched", "Enrichi automatiquement"),
            ("failed", "Non enrichi — vérifier manuellement"),
        ],
        compute="_compute_immo_meta_enrich_badges",
    )
    immo_estimated_value_enrich = fields.Selection(
        [
            ("enriched", "Enrichi automatiquement"),
            ("failed", "Non enrichi — vérifier manuellement"),
        ],
        compute="_compute_immo_meta_enrich_badges",
    )
    immo_is_owner_enrich = fields.Selection(
        [
            ("enriched", "Enrichi automatiquement"),
            ("failed", "Non enrichi — vérifier manuellement"),
        ],
        compute="_compute_immo_meta_enrich_badges",
    )
    immo_other_agents_enrich = fields.Selection(
        [
            ("enriched", "Enrichi automatiquement"),
            ("failed", "Non enrichi — vérifier manuellement"),
        ],
        compute="_compute_immo_meta_enrich_badges",
    )
    immo_transfer_at = fields.Datetime(string="Transfert humain le")
    immo_meta_lead_id = fields.Char(string="ID lead Meta", index=True)
    immo_meta_ad_id = fields.Char(string="ID publicité Meta", index=True)
    immo_meta_form_id = fields.Char(string="ID formulaire Meta")
    immo_nurture_step = fields.Integer(string="Étape nurture", default=0)
    immo_relance_number = fields.Integer(
        string="N° relance active (1=J+1, 2=J+3…)",
        default=0,
    )
    immo_total_call_attempts = fields.Integer(string="Tentatives d'appel total", default=0)
    immo_calls_today = fields.Integer(string="Appels aujourd'hui", default=0)
    immo_last_call_at = fields.Datetime(string="Dernier appel IA")
    immo_do_not_call = fields.Boolean(string="Ne plus appeler (DNC)")
    immo_explicit_refusal = fields.Boolean(string="Refus explicite contact")
    immo_callback_scheduled = fields.Datetime(string="Rappel programmé")
    immo_days_since_request = fields.Integer(
        string="Jours depuis demande",
        compute="_compute_immo_days_since_request",
        store=True,
    )
    immo_nurture_active = fields.Boolean(
        string="Séquence relance active",
        default=False,
    )
    immo_nurture_started_at = fields.Datetime(string="Début séquence relance")

    @api.depends(
        "immo_meta_lead_id",
        "immo_meta_form_id",
        "immo_meta_mapped_keys",
        "immo_property_type",
        "immo_selling_timeline",
        "immo_estimated_value",
        "immo_is_owner_confirmed",
        "immo_other_agents",
    )
    def _compute_immo_meta_enrich_badges(self):
        key_fields = (
            ("property_type", "immo_property_type", "immo_property_type_enrich", False),
            (
                "selling_timeline",
                "immo_selling_timeline",
                "immo_selling_timeline_enrich",
                False,
            ),
            (
                "estimated_value",
                "immo_estimated_value",
                "immo_estimated_value_enrich",
                False,
            ),
            ("is_owner", "immo_is_owner_confirmed", "immo_is_owner_enrich", True),
            ("other_agents", "immo_other_agents", "immo_other_agents_enrich", True),
        )
        for lead in self:
            is_meta = bool(lead.immo_meta_lead_id or lead.immo_meta_form_id)
            lead.immo_is_meta_lead = is_meta
            mapped = {
                part.strip()
                for part in (lead.immo_meta_mapped_keys or "").split(",")
                if part.strip()
            }
            for key, value_field, badge_field, is_bool in key_fields:
                if not is_meta:
                    setattr(lead, badge_field, False)
                    continue
                if key in mapped:
                    setattr(lead, badge_field, "enriched")
                    continue
                value = lead[value_field]
                if not is_bool and value:
                    setattr(lead, badge_field, False)
                else:
                    setattr(lead, badge_field, "failed")

    @api.depends("create_date")
    def _compute_immo_days_since_request(self):
        today = fields.Date.context_today(self)
        for lead in self:
            if lead.create_date:
                lead.immo_days_since_request = (today - lead.create_date.date()).days
            else:
                lead.immo_days_since_request = 0
