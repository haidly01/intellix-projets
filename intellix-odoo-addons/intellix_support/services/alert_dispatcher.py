# -*- coding: utf-8 -*-
import json
import logging
import urllib.error
import urllib.request

from odoo import _, api, fields, models

_logger = logging.getLogger(__name__)

_SERVER_RUNBOOK_CODES = frozenset({"calls_not_dialing", "lea_silent"})


class IntellixSupportAlertDispatcher(models.AbstractModel):
    _name = "intellix.support.alert.dispatcher"
    _description = "Alertes support Intellix (webhook + mail)"

    @api.model
    def _alerts_enabled(self):
        icp = self.env["ir.config_parameter"].sudo()
        return str(icp.get_param("intellix_support.alert_enabled", "False")) in (
            "1",
            "True",
            "true",
        )

    @api.model
    def _webhook_url(self):
        return (
            self.env["ir.config_parameter"]
            .sudo()
            .get_param("intellix_support.alert_webhook_url", "")
            .strip()
        )

    @api.model
    def _evaluate_triggers(self, ticket):
        """Retourne les codes de déclenchement actifs pour un ticket."""
        triggers = []
        if ticket.priority == "3":
            triggers.append("priority_urgent")
        elif ticket.priority == "2":
            triggers.append("priority_high")
        if ticket.sla_state == "breach" and not ticket.stage_id.is_closed:
            triggers.append("sla_breach")
        diag = ticket.last_diagnostic_id
        if (
            ticket.side_origin == "platform"
            and diag
            and diag.checks_failed > 0
        ):
            triggers.append("platform_diagnostic_fail")
        return triggers

    @api.model
    def _trigger_key(self, triggers):
        return ",".join(sorted(triggers))

    @api.model
    def _build_payload(self, ticket, triggers):
        base_url = (
            self.env["ir.config_parameter"].sudo().get_param("web.base.url", "")
        ).rstrip("/")
        priority_labels = dict(ticket._fields["priority"].selection)
        return {
            "event": "intellix_support.alert",
            "ticket_id": ticket.id,
            "ticket_ref": ticket.name,
            "subject": ticket.subject or "",
            "priority": ticket.priority,
            "priority_label": priority_labels.get(ticket.priority, ticket.priority),
            "partner": ticket.partner_id.display_name if ticket.partner_id else "",
            "side_origin": ticket.side_origin,
            "sla_state": ticket.sla_state,
            "diagnostic_summary": ticket.copilot_summary or "",
            "checks_failed": ticket.last_diagnostic_id.checks_failed
            if ticket.last_diagnostic_id
            else 0,
            "triggers": triggers,
            "link": (
                f"{base_url}/web#id={ticket.id}&model=intellix.support.ticket&view_type=form"
                if base_url
                else ""
            ),
        }

    @api.model
    def _post_webhook(self, url, payload):
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        req = urllib.request.Request(
            url,
            data=body,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=15) as resp:
            return resp.status, resp.read(4096).decode("utf-8", errors="replace")

    @api.model
    def _send_mail_fallback(self, ticket, payload):
        template = self.env.ref(
            "intellix_support.mail_template_support_alert",
            raise_if_not_found=False,
        )
        if template:
            template.send_mail(ticket.id, force_send=False)
            return True

        managers = self.env.ref(
            "intellix_support.group_intellix_support_manager",
            raise_if_not_found=False,
        )
        partner_ids = managers.users.partner_id.ids if managers else []
        if not partner_ids:
            _logger.warning(
                "Support alert: no webhook and no manager group for ticket %s",
                ticket.name,
            )
            return False

        subject = _("Alerte support — %(ref)s %(subject)s") % {
            "ref": ticket.name,
            "subject": ticket.subject or "",
        }
        body = _(
            "<p>Alerte ticket <strong>%(ref)s</strong> — %(subject)s</p>"
            "<p>Priorité : %(priority)s · SLA : %(sla)s</p>"
            "<p>%(summary)s</p>"
            "<p>Déclencheurs : %(triggers)s</p>"
        ) % {
            "ref": ticket.name,
            "subject": ticket.subject or "",
            "priority": payload.get("priority_label", ""),
            "sla": payload.get("sla_state", ""),
            "summary": payload.get("diagnostic_summary", "") or "—",
            "triggers": ", ".join(payload.get("triggers") or []),
        }
        self.env["mail.mail"].sudo().create(
            {
                "subject": subject,
                "body_html": body,
                "recipient_ids": [(6, 0, partner_ids)],
                "auto_delete": True,
            }
        ).send()
        return True

    @api.model
    def _karine_partner_ids(self):
        """Destinataires alerte produit (Karine Barmaki + config)."""
        icp = self.env["ir.config_parameter"].sudo()
        partner_ids = []
        configured = (icp.get_param("intellix_support.karine_partner_id") or "").strip()
        if configured.isdigit():
            partner_ids.append(int(configured))
        else:
            Users = self.env["res.users"].sudo()
            karine = Users.search(
                [
                    "|",
                    ("login", "ilike", "karine%barmaki%"),
                    ("partner_id.email", "ilike", "karine%"),
                ],
                limit=1,
            )
            if not karine:
                karine = Users.search(
                    [("partner_id.name", "ilike", "Karine%Barmaki%")],
                    limit=1,
                )
            if karine:
                partner_ids.append(karine.partner_id.id)
        email = (icp.get_param("intellix_support.karine_alert_email") or "").strip()
        if email:
            partner = self.env["res.partner"].sudo().search([("email", "=ilike", email)], limit=1)
            if partner and partner.id not in partner_ids:
                partner_ids.append(partner.id)
        return partner_ids

    @api.model
    def dispatch_karine_product_alert(self, ticket, force=False):
        """Alerte Karine pour demandes non-bug (feature, question, autre)."""
        ticket.ensure_one()
        if ticket.ticket_type == "bug":
            return False
        if ticket.stage_id.is_closed:
            return False

        trigger_key = f"karine_product:{ticket.ticket_type}"
        if not force and ticket.alert_last_trigger == trigger_key:
            return False

        partner_ids = self._karine_partner_ids()
        if not partner_ids:
            _logger.warning(
                "Karine product alert skipped ticket=%s — no recipient configured",
                ticket.name,
            )
            return False

        type_labels = dict(ticket._fields["ticket_type"].selection)
        type_label = type_labels.get(ticket.ticket_type, ticket.ticket_type)
        scope_labels = dict(ticket._fields["user_scope"].selection)
        scope_label = scope_labels.get(ticket.user_scope, ticket.user_scope)

        template = self.env.ref(
            "intellix_support.mail_template_support_karine_product",
            raise_if_not_found=False,
        )
        if template:
            template.send_mail(ticket.id, force_send=False)
        else:
            base_url = (
                self.env["ir.config_parameter"].sudo().get_param("web.base.url", "")
            ).rstrip("/")
            link = (
                f"{base_url}/web#id={ticket.id}&model=intellix.support.ticket&view_type=form"
                if base_url
                else ""
            )
            subject = _("Demande produit — %(ref)s %(subject)s") % {
                "ref": ticket.name,
                "subject": ticket.subject or "",
            }
            body = _(
                "<p>Demande <strong>%(type)s</strong> — ticket <strong>%(ref)s</strong></p>"
                "<p><strong>Organisation :</strong> %(partner)s</p>"
                "<p><strong>Module :</strong> %(module)s</p>"
                "<p><strong>Portée :</strong> %(scope)s</p>"
                "<p><strong>Sujet :</strong> %(subject)s</p>"
                "<p>%(link)s</p>"
            ) % {
                "type": type_label,
                "ref": ticket.name,
                "partner": ticket.partner_id.display_name if ticket.partner_id else "—",
                "module": ticket.category_id.name if ticket.category_id else "—",
                "scope": scope_label,
                "subject": ticket.subject or "",
                "link": (
                    f'<a href="{link}">{_("Ouvrir le ticket")}</a>' if link else ""
                ),
            }
            self.env["mail.mail"].sudo().create(
                {
                    "subject": subject,
                    "body_html": body,
                    "recipient_ids": [(6, 0, partner_ids)],
                    "auto_delete": True,
                }
            ).send()

        ticket.sudo().write(
            {
                "alert_last_trigger": trigger_key,
                "alert_last_sent_at": fields.Datetime.now(),
            }
        )
        ticket.activity_schedule(
            "mail.mail_activity_data_todo",
            user_id=self.env["res.users"]
            .sudo()
            .search([("partner_id", "in", partner_ids)], limit=1)
            .id
            or self.env.uid,
            summary=_("Demande produit — %(type)s") % {"type": type_label},
            note=_(
                "Ticket %(ref)s — %(subject)s. Type : %(type)s, module %(module)s.",
                ref=ticket.name,
                subject=ticket.subject or "",
                type=type_label,
                module=ticket.category_id.name if ticket.category_id else "—",
            ),
        )
        ticket.message_post(
            body=_(
                "<p><em>Alerte Karine</em> — demande %(type)s transmise au responsable produit.</p>",
                type=type_label,
            ),
            partner_ids=partner_ids,
            subtype_xmlid="mail.mt_comment",
        )
        _logger.info(
            "Karine product alert ticket=%s type=%s partners=%s",
            ticket.name,
            ticket.ticket_type,
            partner_ids,
        )
        return True

    @api.model
    def dispatch_for_ticket(self, ticket, force=False):
        """Envoie une alerte si les conditions sont remplies (sans doublon)."""
        ticket.ensure_one()
        if not self._alerts_enabled():
            return False
        if ticket.stage_id.is_closed:
            return False

        triggers = self._evaluate_triggers(ticket)
        if not triggers:
            return False

        trigger_key = self._trigger_key(triggers)
        if not force and ticket.alert_last_trigger == trigger_key:
            return False

        payload = self._build_payload(ticket, triggers)
        webhook_url = self._webhook_url()
        delivery = "none"

        if webhook_url:
            try:
                status, _raw = self._post_webhook(webhook_url, payload)
                delivery = f"webhook:{status}"
                _logger.info(
                    "Support alert webhook ticket=%s triggers=%s status=%s",
                    ticket.name,
                    trigger_key,
                    status,
                )
            except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError) as err:
                delivery = f"webhook_error:{err}"
                _logger.warning(
                    "Support alert webhook failed ticket=%s: %s",
                    ticket.name,
                    err,
                )
                self._send_mail_fallback(ticket, payload)
                delivery += "+mail_fallback"
        else:
            self._send_mail_fallback(ticket, payload)
            delivery = "mail_fallback"
            _logger.info(
                "Support alert mail fallback ticket=%s triggers=%s",
                ticket.name,
                trigger_key,
            )

        ticket.sudo().write(
            {
                "alert_last_trigger": trigger_key,
                "alert_last_sent_at": fields.Datetime.now(),
            }
        )
        ticket.message_post(
            body=_(
                "<p><em>Alerte support</em> — %(triggers)s (%(delivery)s)</p>",
                triggers=", ".join(triggers),
                delivery=delivery,
            ),
            subtype_xmlid="mail.mt_note",
        )
        return True

    @api.model
    def cron_check_sla_alerts(self):
        """Cron — recompute SLA ouvert + alertes breach."""
        tickets = self.env["intellix.support.ticket"].search(
            [("stage_id.is_closed", "=", False)]
        )
        tickets._compute_sla_state()
        for ticket in tickets.filtered(lambda t: t.sla_state == "breach"):
            self.dispatch_for_ticket(ticket)
