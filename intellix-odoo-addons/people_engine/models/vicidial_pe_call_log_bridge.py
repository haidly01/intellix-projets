# -*- coding: utf-8 -*-
import logging

from odoo import api, fields, models

_logger = logging.getLogger(__name__)

QUALIFICATION_TO_OUTCOME = {
    "qualifie": "interesse",
    "rdv": "demo_bookee",
    "a_rappeler": "rappel",
    "pas_interesse": "pas_interesse",
    "deja_servi": "pas_interesse",
    "locataire": "pas_interesse",
    "dnc": "pas_interesse",
    "messagerie": "rappel",
    "hors_cible": "pas_interesse",
    "faux_num": "mauvais_num",
    "b2b_valide": "interesse",
}


class VicidialCallSyncPeBridge(models.Model):
    _inherit = "doorway.vicidial.call.sync"

    pe_call_log_id = fields.Many2one("pe.call.log", string="Journal PE", copy=False)

    def _resolve_pe_employee(self):
        self.ensure_one()
        if self.employee_id:
            return self.employee_id
        if self.user_id:
            profile = self.env["pe.employee.profile"].sudo().search(
                [("user_id", "=", self.user_id.id)], limit=1
            )
            if profile and profile.employee_id:
                return profile.employee_id
        return self.env["hr.employee"]

    def _resolve_pe_department(self, employee):
        profile = self.env["pe.employee.profile"].sudo().search(
            [("employee_id", "=", employee.id)], limit=1
        )
        if profile and profile.department_pe_id:
            return profile.department_pe_id
        return self.env["pe.department"].sudo().search(
            [("code", "in", ("CC-QC", "CC-TEMPLATE"))], limit=1
        )

    def _fetch_ai_score_for_sync(self):
        self.ensure_one()
        Coaching = self.env.get("pe.coaching.call")
        if Coaching and self.vicidial_call_id:
            call = Coaching.sudo().search(
                [("vicidial_call_id", "=", self.vicidial_call_id)], limit=1
            )
            if call and call.score_global:
                return float(call.score_global)
        if self.lead_id:
            return float(self.lead_id.score_qualification or 0)
        return 0.0

    def sync_pe_call_log(self, qualification_statut=None):
        self.ensure_one()
        qual = qualification_statut
        if qual is None and self.lead_id:
            qual = self.lead_id.qualification_statut
        if not qual or qual == "non_fait":
            return self.env["pe.call.log"]
        outcome = QUALIFICATION_TO_OUTCOME.get(qual)
        if not outcome:
            return self.env["pe.call.log"]

        employee = self._resolve_pe_employee()
        if not employee:
            return self.env["pe.call.log"]

        CallLog = self.env["pe.call.log"].sudo()
        log = self.pe_call_log_id
        if not log and self.vicidial_call_id:
            log = CallLog.search(
                [("vicidial_id", "=", self.vicidial_call_id)], limit=1
            )

        recording = False
        if self.vicidial_call_id:
            clog = self.env["doorway.call.log"].sudo().search(
                [("vicidial_call_id", "=", self.vicidial_call_id)], limit=1
            )
            recording = clog.recording_url if clog else False

        vals = {
            "employee_id": employee.id,
            "department_id": self._resolve_pe_department(employee).id,
            "lead_id": self.lead_id.id if self.lead_id else False,
            "date_call": self.date_debut or fields.Datetime.now(),
            "duration": self.duree_secondes or 0,
            "vicidial_id": self.vicidial_call_id,
            "outcome": outcome,
            "recording_url": recording,
            "ai_score": self._fetch_ai_score_for_sync(),
        }
        if not vals["department_id"]:
            vals.pop("department_id")

        try:
            if log:
                log.write({k: v for k, v in vals.items() if k != "employee_id"})
                self.pe_call_log_id = log.id
                return log
            log = CallLog.create(vals)
            self.pe_call_log_id = log.id
            return log
        except Exception as exc:
            _logger.warning("PE call log bridge: %s", exc)
            return CallLog

    def _marquer_termine(self, notify=False):
        super()._marquer_termine(notify=notify)
        for sync in self:
            if sync.lead_id and sync.lead_id.qualification_statut != "non_fait":
                sync.sync_pe_call_log(sync.lead_id.qualification_statut)


class CrmLeadPeCallLogBridge(models.Model):
    _inherit = "crm.lead"

    def _sync_pe_call_log_from_qualification(self):
        Sync = self.env["doorway.vicidial.call.sync"].sudo()
        for lead in self:
            if lead.qualification_statut == "non_fait":
                continue
            sync = Sync.search(
                [("lead_id", "=", lead.id)],
                order="date_debut desc",
                limit=1,
            )
            if sync:
                sync.sync_pe_call_log(lead.qualification_statut)
