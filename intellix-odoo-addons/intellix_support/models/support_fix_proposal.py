# -*- coding: utf-8 -*-
import logging

from odoo import _, api, fields, models
from odoo.exceptions import AccessError, UserError

_logger = logging.getLogger(__name__)

_PROPOSAL_STATES = [
    ("draft", "Brouillon"),
    ("pending_approval", "En attente d'approbation"),
    ("approved", "Approuvé"),
    ("rejected", "Rejeté"),
    ("executed", "Exécuté"),
    ("failed", "Échec"),
]


class IntellixSupportFixProposal(models.Model):
    _name = "intellix.support.fix.proposal"
    _description = "Proposition de correctif support"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "create_date desc, id desc"

    name = fields.Char(
        string="Référence",
        required=True,
        copy=False,
        readonly=True,
        default=lambda self: _("Nouveau"),
    )
    ticket_id = fields.Many2one(
        "intellix.support.ticket",
        string="Ticket",
        required=True,
        ondelete="cascade",
        index=True,
    )
    runbook_id = fields.Many2one(
        "intellix.support.runbook",
        string="Runbook",
        required=True,
        index=True,
    )
    diagnostic_id = fields.Many2one(
        "intellix.support.diagnostic",
        string="Diagnostic source",
    )
    steps_html = fields.Html(string="Étapes proposées")
    state = fields.Selection(
        _PROPOSAL_STATES,
        default="draft",
        required=True,
        tracking=True,
    )
    approved_by = fields.Many2one("res.users", string="Approuvé par", readonly=True)
    approved_date = fields.Datetime(string="Date approbation", readonly=True)
    execution_log = fields.Text(string="Journal d'exécution", readonly=True)
    error_message = fields.Text(string="Message d'erreur", readonly=True)
    company_id = fields.Many2one(
        related="ticket_id.company_id",
        store=True,
        readonly=True,
    )

    @api.model_create_multi
    def create(self, vals_list):
        seq = self.env["ir.sequence"]
        for vals in vals_list:
            if vals.get("name", _("Nouveau")) == _("Nouveau"):
                vals["name"] = (
                    seq.next_by_code("intellix.support.fix.proposal") or _("Nouveau")
                )
        return super().create(vals_list)

    def _check_manager(self):
        if not self.env.user.has_group(
            "intellix_support.group_intellix_support_manager"
        ):
            raise AccessError(_("Seuls les responsables support peuvent approuver ou exécuter un correctif."))

    def action_submit_for_approval(self):
        for proposal in self:
            if proposal.state not in ("draft", "rejected"):
                raise UserError(_("Cette proposition ne peut pas être soumise."))
            proposal.state = "pending_approval"
        return True

    def action_approve(self):
        self._check_manager()
        now = fields.Datetime.now()
        bridge = self.env["intellix.support.cursor.bridge"]
        for proposal in self:
            if proposal.state != "pending_approval":
                raise UserError(_("Seules les propositions en attente peuvent être approuvées."))
            proposal.write(
                {
                    "state": "approved",
                    "approved_by": self.env.user.id,
                    "approved_date": now,
                    "error_message": False,
                }
            )
            proposal.ticket_id.message_post(
                body=_(
                    "Correctif <strong>%(name)s</strong> approuvé par %(user)s.",
                    name=proposal.name,
                    user=self.env.user.name,
                ),
                subtype_xmlid="mail.mt_note",
            )
            bridge.maybe_dispatch_on_proposal_approved(proposal)
        return True

    def action_reject(self):
        self._check_manager()
        for proposal in self:
            if proposal.state != "pending_approval":
                raise UserError(_("Seules les propositions en attente peuvent être rejetées."))
            proposal.state = "rejected"
        return True

    def action_execute(self):
        self._check_manager()
        executor = self.env["intellix.support.runbook.executor"]
        bridge = self.env["intellix.support.cursor.bridge"]
        results = []
        for proposal in self:
            if proposal.state != "approved":
                raise UserError(_("Le correctif doit être approuvé avant exécution."))
            if proposal.runbook_id.phase != "ready":
                raise UserError(
                    _("Le runbook « %(name)s » n'est pas prêt à l'exécution.")
                    % {"name": proposal.runbook_id.name}
                )
            try:
                result = executor.execute_proposal(proposal)
                log = result.get("log", "")
                stub_log = bridge.execution_stub_for_proposal(proposal)
                if stub_log:
                    log = (log + stub_log) if log else stub_log.lstrip("\n")
                proposal.write(
                    {
                        "state": "executed",
                        "execution_log": log,
                        "error_message": False,
                    }
                )
                results.append(result)
            except UserError as err:
                proposal.write(
                    {
                        "state": "failed",
                        "error_message": str(err),
                        "execution_log": proposal.execution_log or "",
                    }
                )
                raise
            except Exception as err:
                _logger.exception("Runbook execution failed proposal=%s", proposal.id)
                proposal.write(
                    {
                        "state": "failed",
                        "error_message": str(err),
                    }
                )
                raise UserError(_("Échec d'exécution : %s") % err) from err
        if len(results) == 1 and results[0].get("notify"):
            return results[0]["notify"]
        return True
