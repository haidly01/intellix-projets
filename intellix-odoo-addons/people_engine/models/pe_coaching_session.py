# -*- coding: utf-8 -*-
from odoo import _, api, fields, models
from odoo.exceptions import UserError


class PeopleEngineCoachingSession(models.Model):
    _name = "pe.coaching.session"
    _description = "Session de coaching IA"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "create_date desc"

    profile_id = fields.Many2one(
        "pe.employee.profile", required=True, ondelete="cascade", index=True
    )
    employee_id = fields.Many2one(related="profile_id.employee_id", store=True)
    session_type = fields.Selection(
        [
            ("praise", "Félicitations"),
            ("coaching", "Coaching développement"),
            ("warning", "Avertissement informel"),
            ("formal_warn", "Avertissement formel"),
            ("pip", "Plan d'amélioration (PIP)"),
            ("termination", "Dossier mise à pied"),
        ],
        required=True,
        tracking=True,
    )
    trigger_type = fields.Selection(
        [
            ("score_drop", "Baisse de score"),
            ("score_high", "Score exceptionnel"),
            ("objective_miss", "Objectif manqué"),
            ("objective_hit", "Objectif atteint"),
            ("manual", "Initié manuellement"),
            ("pattern", "Pattern détecté par IA"),
        ],
        default="manual",
    )
    trigger_score = fields.Float()
    trigger_details = fields.Text()

    claude_analysis = fields.Text(string="Analyse Claude", readonly=True)
    claude_draft = fields.Text(string="Brouillon Claude", readonly=True)
    claude_legal_refs = fields.Text(string="Références légales suggérées", readonly=True)
    claude_action_plan = fields.Text(string="Plan d'action suggéré", readonly=True)
    claude_model_used = fields.Char(readonly=True)
    claude_generated_at = fields.Datetime(readonly=True)
    claude_tokens_used = fields.Integer(readonly=True)

    manager_id = fields.Many2one(
        "hr.employee", string="Gestionnaire responsable", required=True
    )
    manager_reviewed = fields.Boolean(default=False)
    manager_reviewed_at = fields.Datetime()
    manager_edits = fields.Text(string="Modifications du gestionnaire")
    manager_approved = fields.Boolean(default=False)
    manager_approval_date = fields.Datetime()

    hr_validation_required = fields.Boolean(
        compute="_compute_hr_required", store=True
    )
    hr_validator_id = fields.Many2one("hr.employee", string="Validateur RH")
    hr_validated = fields.Boolean(default=False)
    hr_validation_date = fields.Datetime()
    hr_comments = fields.Text()

    final_message = fields.Text(
        string="Message final",
        help="Version finale approuvée — peut différer du brouillon Claude.",
    )
    delivery_method = fields.Selection(
        [
            ("odoo_chat", "Chat Odoo interne"),
            ("email", "Email"),
            ("in_person", "Rencontre en personne"),
            ("written", "Document écrit signé"),
        ],
        default="odoo_chat",
    )
    delivered_at = fields.Datetime()
    employee_acknowledged = fields.Boolean(default=False)
    employee_acknowledged_date = fields.Datetime()

    compliance_ok = fields.Boolean(string="Conformité légale OK", readonly=True)
    compliance_blockers = fields.Text(readonly=True)
    compliance_warnings = fields.Text(readonly=True)

    status = fields.Selection(
        [
            ("generating", "Génération en cours"),
            ("draft", "Brouillon à réviser"),
            ("pending_manager", "En attente gestionnaire"),
            ("pending_hr", "En attente validation RH"),
            ("approved", "Approuvé"),
            ("delivered", "Communiqué"),
            ("acknowledged", "Accusé réception"),
            ("cancelled", "Annulé"),
        ],
        default="draft",
        tracking=True,
    )
    score = fields.Integer(string="Score session", default=0)
    coaching_call_id = fields.Many2one(
        "pe.coaching.call",
        string="Appel lié",
        ondelete="set null",
    )
    insights = fields.Text(string="Insights Claude")
    read_by_agent = fields.Boolean(string="Lu par l'agent", default=False)

    @api.model
    def get_coaching_list_header_data(self):
        """Stat cards header — Sessions coaching IA."""
        sessions = self.search([])
        scores = [s.score for s in sessions if s.score]
        unread = sessions.filtered(lambda s: not s.read_by_agent)
        pending = sessions.filtered(
            lambda s: s.status in ("pending_manager", "pending_hr", "generating")
        )
        return {
            "count": len(sessions),
            "avg_score": round(sum(scores) / len(scores)) if scores else 0,
            "unread": len(unread),
            "pending": len(pending),
            "done": len(sessions.filtered(lambda s: s.status in ("delivered", "acknowledged"))),
        }

    @api.model
    def action_create_manual_session(self):
        """Création rapide depuis empty state."""
        manager = self.env.user.employee_id
        if not manager:
            raise UserError(_("Aucun employé lié à votre utilisateur."))
        profile = self.env["pe.employee.profile"].search(
            [("employee_id", "=", manager.id)], limit=1
        )
        if not profile:
            raise UserError(_("Profil People Engine introuvable."))
        session = self.create(
            {
                "profile_id": profile.id,
                "session_type": "coaching",
                "trigger_type": "manual",
                "manager_id": manager.id,
                "status": "draft",
            }
        )
        return {
            "type": "ir.actions.act_window",
            "name": _("Session coaching"),
            "res_model": "pe.coaching.session",
            "res_id": session.id,
            "view_mode": "form",
            "target": "current",
        }

    @api.depends("session_type")
    def _compute_hr_required(self):
        formal = ("formal_warn", "pip", "termination")
        for session in self:
            session.hr_validation_required = session.session_type in formal

    def action_generate_claude(self):
        for session in self:
            session.write({"status": "generating"})
            compliance = self.env["pe.claude.coaching.service"].check_compliance(
                session
            )
            session.write(
                {
                    "compliance_ok": compliance.get("can_proceed", True),
                    "compliance_blockers": "\n".join(compliance.get("blockers", [])),
                    "compliance_warnings": "\n".join(compliance.get("warnings", [])),
                }
            )
            if not compliance.get("can_proceed", True):
                session.write(
                    {
                        "status": "draft",
                        "claude_legal_refs": session.compliance_blockers,
                    }
                )
                raise UserError(
                    _(
                        "Conditions légales non remplies. Consultez les blocages "
                        "affichés avant de poursuivre."
                    )
                )
            self.env["pe.claude.coaching.service"].generate_coaching_message(session)
        return True

    def action_manager_review(self):
        for session in self:
            if session.status not in ("pending_manager", "draft"):
                raise UserError(_("Cette session n'est pas en attente de révision."))
            final = session.manager_edits or session.claude_draft or ""
            session.write(
                {
                    "manager_reviewed": True,
                    "manager_reviewed_at": fields.Datetime.now(),
                    "final_message": final,
                    "status": "pending_hr"
                    if session.hr_validation_required
                    else "approved",
                }
            )

    def action_manager_approve(self):
        for session in self:
            if not session.manager_reviewed and not session.claude_draft:
                raise UserError(_("Générez ou révisez le brouillon avant approbation."))
            session.write(
                {
                    "manager_approved": True,
                    "manager_approval_date": fields.Datetime.now(),
                    "final_message": session.final_message
                    or session.manager_edits
                    or session.claude_draft,
                    "status": "pending_hr"
                    if session.hr_validation_required and not session.hr_validated
                    else "approved",
                }
            )

    def action_hr_validate(self):
        if not self.env.user.has_group("people_engine.group_hr"):
            raise UserError(_("Validation RH requise."))
        for session in self:
            session.write(
                {
                    "hr_validated": True,
                    "hr_validation_date": fields.Datetime.now(),
                    "hr_validator_id": self.env.user.employee_id.id,
                    "status": "approved",
                }
            )

    def action_deliver(self):
        for session in self:
            if session.status != "approved":
                raise UserError(
                    _("Le message doit être approuvé (et validé RH si requis) avant envoi.")
                )
            if not session.final_message:
                raise UserError(_("Le message final est vide."))
            employee = session.profile_id.employee_id
            partner = employee.user_id.partner_id if employee.user_id else False
            body = session.final_message
            if session.hr_validation_required:
                body += "\n\n---\n" + self.env["pe.legal.engine"].DISCLAIMER
            if partner and session.delivery_method == "odoo_chat":
                session.message_post(
                    body=body,
                    partner_ids=[partner.id],
                    subtype_xmlid="mail.mt_comment",
                )
            session.write(
                {
                    "delivered_at": fields.Datetime.now(),
                    "status": "delivered",
                }
            )
            session.profile_id.write({"pe_status": "coaching"})
            self.env["pe.action.log"].log_action(
                session.profile_id,
                "coaching_started",
                _("Session coaching communiquée (%s)") % session.session_type,
                actor_type="manager",
            )

    def action_acknowledge(self):
        self.write(
            {
                "employee_acknowledged": True,
                "employee_acknowledged_date": fields.Datetime.now(),
                "status": "acknowledged",
            }
        )

    def action_cancel(self):
        self.write({"status": "cancelled"})

    def action_create_manual(self):
        """Création manuelle sans IA (graceful degradation)."""
        self.ensure_one()
        self.write(
            {
                "status": "pending_manager",
                "claude_draft": self.trigger_details or "",
            }
        )
