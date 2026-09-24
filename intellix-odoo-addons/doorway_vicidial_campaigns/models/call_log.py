# -*- coding: utf-8 -*-
import logging
from datetime import timedelta

from odoo import _, api, fields, models
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)

try:
    from dateutil.relativedelta import relativedelta
except ImportError:  # pragma: no cover
    relativedelta = None


class CallLog(models.Model):
    _name = "doorway.call.log"
    _description = "Log appel VICIdial temps réel"
    _order = "call_date desc"

    RENOFACILE_CAMPAIGNS = {"DW_FRB2C"}
    RENOFACILE_AGENT_IDS = {"marenofacile", "sofia_renofacile_fr"}

    campaign_id = fields.Many2one(
        "doorway.campaign", required=True, ondelete="cascade"
    )
    phone_number = fields.Char(string="Numéro appelé")
    call_date = fields.Datetime(string="Heure appel")
    duration = fields.Integer(string="Durée (sec)")
    amd_result = fields.Selection(
        [
            ("human", "Humain détecté"),
            ("answering_machine", "Répondeur — message laissé"),
            ("amd_hangup", "Répondeur — raccroché"),
            ("no_answer", "Pas de réponse"),
            ("busy", "Occupé"),
            ("invalid", "Numéro invalide"),
        ],
        string="Résultat AMD",
    )
    disposition = fields.Selection(
        [
            ("VENTE", "Vente"),
            ("INTERET", "Intérêt"),
            ("RAPPEL", "Rappel"),
            ("REFUS", "Refus"),
            ("REPONDEUR", "Répondeur"),
            ("INVALIDE", "Invalide"),
        ],
        string="Disposition agent",
    )
    agent_name = fields.Char(string="Agent (IA ou humain)")
    human_agent_id = fields.Many2one(
        "doorway.campaign.agent.user",
        string="Agent humain",
        index=True,
        ondelete="set null",
    )
    vicidial_call_id = fields.Char(string="ID appel VICIdial", index=True)
    recording_url = fields.Char(string="URL enregistrement")
    lead_id = fields.Many2one(
        "crm.lead", string="Opportunité", index=True, ondelete="set null"
    )

    consent_captured = fields.Boolean(string="Consentement capturé")
    recording_retention_until = fields.Date(
        string="Conservation enregistrement jusqu'au"
    )
    recording_legal_hold = fields.Boolean(
        string="Conservation légale (3 ans)",
        default=False,
    )
    consent_notes = fields.Text(string="Notes consentement")

    _sql_constraints = [
        (
            "vicidial_call_id_uniq",
            "unique(vicidial_call_id)",
            "Cet appel VICIdial est déjà enregistré.",
        ),
    ]

    def _is_renofacile_call(self):
        self.ensure_one()
        vicidial_id = ""
        if self.campaign_id:
            vicidial_id = (self.campaign_id.vicidial_campaign_id or "")[:8]
        if vicidial_id in self.RENOFACILE_CAMPAIGNS:
            return True
        agent_key = (self.agent_name or "").lower()
        return any(token in agent_key for token in self.RENOFACILE_AGENT_IDS)

    def _apply_recording_retention_policy(self):
        """RénoFacile FR B2C : conservation 3 ans des enregistrements."""
        for rec in self:
            if not rec._is_renofacile_call():
                continue
            base = (
                fields.Datetime.to_datetime(rec.call_date).date()
                if rec.call_date
                else fields.Date.today()
            )
            if relativedelta:
                retention_until = base + relativedelta(years=3)
            else:
                retention_until = base + timedelta(days=365 * 3)
            rec.write(
                {
                    "recording_retention_until": retention_until,
                    "recording_legal_hold": True,
                }
            )
        return True

    def unlink(self):
        today = fields.Date.today()
        blocked = self.filtered(
            lambda r: r.recording_legal_hold
            and r.recording_retention_until
            and r.recording_retention_until >= today
        )
        if blocked:
            raise UserError(
                _(
                    "Suppression impossible : cet enregistrement est conservé "
                    "jusqu'au %(date)s pour preuve réglementaire (RénoFacile)."
                )
                % {"date": blocked[:1].recording_retention_until}
            )
        return super().unlink()

    def action_open_recording(self):
        self.ensure_one()
        if not self.recording_url:
            raise UserError(_("Aucun enregistrement disponible pour cet appel."))
        return {
            "type": "ir.actions.act_url",
            "url": self.recording_url,
            "target": "new",
        }

    @api.model
    def cron_enrich_recent_call_logs(self, limit=150):
        """Filet de sécurité : complète lead/durée/coaching si le postcommit a échoué."""
        from odoo.addons.doorway_vicidial_campaigns.services.vicidial_service import (
            VicidialService,
        )

        cutoff = fields.Datetime.now() - timedelta(hours=8)
        logs = self.sudo().search(
            [
                ("recording_url", "!=", False),
                ("call_date", ">=", cutoff),
                "|",
                ("lead_id", "=", False),
                ("duration", "<=", 0),
            ],
            limit=int(limit or 150),
            order="call_date desc",
        )
        svc = VicidialService(self.env(su=True))
        for log in logs:
            try:
                svc._enrich_call_log_recording(log.id, {})
            except Exception as exc:
                _logger.warning("cron enrich call log %s: %s", log.id, exc)
        return len(logs)
