from datetime import timedelta

from odoo import api, fields, models
from odoo.exceptions import ValidationError

CONTACT_METHODS = [
    ("phone", "Téléphone"),
    ("email", "Courriel"),
    ("sms", "SMS / Texto"),
    ("voicemail", "Messagerie vocale"),
    ("other", "Autre"),
]


class RenovationLeadServiceAssignment(models.Model):
    _name = "renovation.lead.service.assignment"
    _description = "Attribution lead par service"
    _order = "lead_id, service_category_id"

    lead_id = fields.Many2one(
        "crm.lead",
        string="Lead",
        required=True,
        ondelete="cascade",
    )
    service_category_id = fields.Many2one(
        "renovation.service.category",
        string="Service demandé",
        required=True,
    )
    partner_id = fields.Many2one(
        "res.partner",
        string="Partenaire assigné",
    )
    status = fields.Selection([
        ("pending", "En attente"),
        ("assigned", "Assigné"),
        ("accepted", "Accepté"),
        ("credit_requested", "Crédit demandé"),
        ("credited", "Crédité"),
        ("refused", "Refusé"),
        ("refused_changed_mind", "Refusé - changé d'idée"),
        ("postponed", "Reporté"),
        ("no_match", "Aucun partenaire"),
    ], default="pending", string="Statut")
    assignment_date = fields.Datetime(
        string="Date d'attribution",
        readonly=True,
    )
    contact_attempt_1_date = fields.Datetime(string="Tentative 1 — date")
    contact_attempt_1_method = fields.Selection(CONTACT_METHODS, string="Tentative 1 — moyen")
    contact_attempt_2_date = fields.Datetime(string="Tentative 2 — date")
    contact_attempt_2_method = fields.Selection(CONTACT_METHODS, string="Tentative 2 — moyen")
    contact_attempt_3_date = fields.Datetime(string="Tentative 3 — date")
    contact_attempt_3_method = fields.Selection(CONTACT_METHODS, string="Tentative 3 — moyen")
    refusal_reason = fields.Text(string="Motif / précisions")
    lead_consumed = fields.Boolean(string="Lead consommé du forfait", default=False, copy=False)
    credit_request_date = fields.Datetime(string="Demande de crédit le", readonly=True, copy=False)
    credit_validated_by = fields.Many2one("res.users", string="Crédit validé par", readonly=True, copy=False)
    credit_decision_date = fields.Datetime(string="Décision crédit le", readonly=True, copy=False)

    def _has_three_attempts(self, require_method=False):
        self.ensure_one()
        dates_ok = bool(
            self.contact_attempt_1_date
            and self.contact_attempt_2_date
            and self.contact_attempt_3_date
        )
        if not require_method:
            return dates_ok
        methods_ok = bool(
            self.contact_attempt_1_method
            and self.contact_attempt_2_method
            and self.contact_attempt_3_method
        )
        return dates_ok and methods_ok

    @api.constrains(
        "status",
        "contact_attempt_1_date",
        "contact_attempt_2_date",
        "contact_attempt_3_date",
    )
    def _check_refusal_attempts(self):
        for rec in self:
            if rec.status in ("refused", "credit_requested", "credited"):
                if not rec._has_three_attempts():
                    raise ValidationError(
                        "3 tentatives de contact datées sont obligatoires pour cette opération."
                    )

    def write(self, vals):
        previous_by_id = {
            rec.id: {
                "status": rec.status,
                "partner_id": rec.partner_id.id,
                "lead_id": rec.lead_id.id,
            }
            for rec in self
        }
        res = super().write(vals)

        if "status" in vals:
            for rec in self:
                previous = previous_by_id.get(rec.id, {})
                old_status = previous.get("status")
                if old_status != rec.status:
                    rec._update_partner_quota(old_status, rec.status)

            leads = self.mapped("lead_id")
            if leads:
                leads._recompute_partner_assignment_status()
        return res

    def _update_partner_quota(self, old_status, new_status):
        self.ensure_one()
        if not self.partner_id:
            return

        package = self.partner_id.active_package_id
        if not package:
            return

        # Attribution (ou acceptation) : une seule consommation par ligne
        if new_status in ("assigned", "accepted") and not self.lead_consumed:
            if package._has_available_leads():
                package.action_consume_lead()
                self.lead_consumed = True

        # Remboursement uniquement quand crédité (validé) ou refusé
        if new_status in ("credited", "refused", "refused_changed_mind") and self.lead_consumed:
            if package.leads_used > 0:
                package.leads_used -= 1
                package.alert_sent = False
                if package.state == "expired" and package.leads_remaining > 0:
                    package.state = "active"
            self.lead_consumed = False

    def action_accept(self):
        self.write({
            "status": "accepted",
            "assignment_date": fields.Datetime.now(),
        })
        return True

    def action_postpone(self):
        self.write({
            "status": "postponed",
        })
        return True

    # ------------------------------------------------------------------
    # Demande de crédit (partenaire) + validation (admin)
    # ------------------------------------------------------------------
    def action_request_credit(self):
        """Le partenaire déclare 3 tentatives infructueuses et demande un crédit."""
        self.ensure_one()
        if not self._has_three_attempts(require_method=True):
            raise ValidationError(
                "Pour demander un crédit, renseignez les 3 tentatives de contact "
                "(date ET moyen de contact pour chacune)."
            )
        self.write({
            "status": "credit_requested",
            "credit_request_date": fields.Datetime.now(),
        })
        self._notify_admin_credit_request()
        return True

    def _notify_admin_credit_request(self):
        self.ensure_one()
        lead = self.lead_id
        attempts = []
        labels = dict(CONTACT_METHODS)
        for i in (1, 2, 3):
            d = self["contact_attempt_%s_date" % i]
            m = self["contact_attempt_%s_method" % i]
            if d:
                attempts.append("Tentative %s : %s — %s" % (i, d, labels.get(m, "?")))
        body = (
            "<p><b>Demande de crédit</b> du partenaire <b>%s</b> pour le service "
            "<b>%s</b> (lead %s).</p><p>3 tentatives de contact non rejointes :</p><ul>%s</ul>"
            "<p>À valider dans <b>Rénovation → Demandes de crédit</b>.</p>"
        ) % (
            self.partner_id.name or "",
            self.service_category_id.name or "",
            lead.name or "",
            "".join("<li>%s</li>" % a for a in attempts),
        )
        admins = self.env["crm.team"]._get_agence_doorway_admin_users()

        # Notifie tous les admins via le fil du lead (ajout comme abonnés)
        if admins.partner_id:
            lead.message_subscribe(partner_ids=admins.partner_id.ids)
        lead.message_post(
            body=body,
            subject="Demande de crédit lead",
            partner_ids=admins.partner_id.ids,
        )

        # Une activité « À faire » pour chaque administrateur
        for admin in admins:
            try:
                lead.activity_schedule(
                    "mail.mail_activity_data_todo",
                    summary="Valider une demande de crédit lead",
                    note=body,
                    user_id=admin.id,
                )
            except Exception:
                pass

    def action_validate_credit(self):
        """L'admin approuve la demande : le lead est recrédité au forfait."""
        for rec in self:
            if rec.status != "credit_requested":
                continue
            rec.write({
                "status": "credited",
                "credit_validated_by": self.env.user.id,
                "credit_decision_date": fields.Datetime.now(),
            })
            rec.lead_id.message_post(
                body="Crédit <b>approuvé</b> pour %s — lead recrédité au forfait." % (
                    rec.partner_id.name or ""),
            )
        return True

    def action_reject_credit(self):
        """L'admin refuse la demande : le lead reste accepté/consommé."""
        for rec in self:
            if rec.status != "credit_requested":
                continue
            rec.write({
                "status": "accepted",
                "credit_validated_by": self.env.user.id,
                "credit_decision_date": fields.Datetime.now(),
            })
            rec.lead_id.message_post(
                body="Demande de crédit <b>refusée</b> pour %s — le lead reste à sa charge." % (
                    rec.partner_id.name or ""),
            )
        return True

    @api.model
    def _cron_auto_accept_24h(self):
        """Auto-accepte les attributions sans réponse du partenaire après 24 h."""
        limit = fields.Datetime.now() - timedelta(hours=24)
        stale = self.search([
            ("status", "=", "assigned"),
            ("partner_id", "!=", False),
            ("assignment_date", "<=", limit),
        ])
        for rec in stale:
            rec.action_accept()
            rec.lead_id.message_post(
                body="Lead <b>auto-accepté</b> : aucune réponse du partenaire %s sous 24 h." % (
                    rec.partner_id.name or ""),
            )
        return True
