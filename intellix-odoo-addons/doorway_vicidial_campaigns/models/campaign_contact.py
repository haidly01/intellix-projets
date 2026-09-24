# -*- coding: utf-8 -*-
from odoo import api, fields, models


class DoorwayCampaignContact(models.Model):
    _name = "doorway.campaign.contact"
    _description = "Contact campagne VICIdial"
    _order = "last_attempt_date desc, id desc"

    campaign_id = fields.Many2one(
        "doorway.campaign",
        required=True,
        ondelete="cascade",
        index=True,
    )
    phone_number = fields.Char(required=True, index=True)
    first_name = fields.Char()
    last_name = fields.Char()
    email = fields.Char()
    vendor_code = fields.Char(string="Code lead")
    state = fields.Selection(
        [
            ("new", "Nouveau"),
            ("in_hopper", "Dans hopper"),
            ("called", "Appelé"),
            ("failed", "Échec"),
        ],
        default="new",
    )
    vicidial_lead_id = fields.Integer(string="Lead ID VICIdial", readonly=True)
    error_message = fields.Char()

    # Dashboard opérationnel (Phase 2)
    operational_status = fields.Selection(
        [
            ("success", "Succès"),
            ("callback", "Décroché – à relancer"),
            ("voicemail", "Messagerie"),
            ("error", "Erreur"),
            ("in_progress", "En cours"),
        ],
        string="Statut opérationnel",
        compute="_compute_operational_fields",
        store=True,
    )
    last_attempt_date = fields.Datetime(
        string="Dernière tentative",
        compute="_compute_operational_fields",
        store=True,
    )
    last_duration = fields.Integer(
        string="Durée dernière tentative (s)",
        compute="_compute_operational_fields",
        store=True,
    )
    ai_note = fields.Text(string="Note IA")
    ai_score = fields.Float(string="Score IA")
    ai_tags = fields.Char(string="Tags IA")
    attempt_count = fields.Integer(
        string="Tentatives",
        compute="_compute_operational_fields",
        store=True,
    )
    crm_lead_id = fields.Many2one("crm.lead", string="Lead Odoo", index=True)
    ia_agent_id = fields.Many2one(
        "doorway.agent.profile",
        string="Agent IA",
        related="campaign_id.ia_agent_id",
        store=True,
    )

    @api.depends(
        "campaign_id",
        "state",
        "phone_number",
    )
    def _compute_operational_fields(self):
        Log = self.env["doorway.call.log"]
        for rec in self:
            phone = (rec.phone_number or "").strip()
            logs = Log.search(
                [
                    ("campaign_id", "=", rec.campaign_id.id),
                    ("phone_number", "=", phone),
                ],
                order="call_date desc",
                limit=50,
            )
            rec.attempt_count = len(logs)
            latest = logs[:1]
            if latest:
                log = latest[0]
                rec.last_attempt_date = log.call_date
                rec.last_duration = log.duration or 0
                rec.operational_status = rec._status_from_log(log)
            elif rec.state == "in_hopper":
                rec.operational_status = "in_progress"
                rec.last_attempt_date = False
                rec.last_duration = 0
            elif rec.state == "failed":
                rec.operational_status = "error"
                rec.last_attempt_date = False
                rec.last_duration = 0
            else:
                rec.operational_status = "callback"
                rec.last_attempt_date = False
                rec.last_duration = 0

    def _status_from_log(self, log):
        disp = (log.disposition or "").upper()
        amd = log.amd_result or ""
        if disp in ("VENTE", "INTERET"):
            return "success"
        if amd in ("answering_machine", "amd_hangup") or disp == "REPONDEUR":
            return "voicemail"
        if amd in ("no_answer", "busy") or disp == "RAPPEL":
            return "callback"
        if amd == "invalid" or disp == "INVALIDE":
            return "error"
        if amd == "human":
            return "success"
        return "callback"
