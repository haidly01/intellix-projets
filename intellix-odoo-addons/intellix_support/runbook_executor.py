# -*- coding: utf-8 -*-
import logging
import secrets
import string

from odoo import _, api, fields, models
from odoo.exceptions import UserError
from odoo.tools import format_datetime
from odoo import SUPERUSER_ID

_logger = logging.getLogger(__name__)


class IntellixSupportRunbookExecutor(models.AbstractModel):
    _name = "intellix.support.runbook.executor"
    _description = "Exécuteur runbooks support Intellix"

    @api.model
    def execute_proposal(self, proposal):
        proposal.ensure_one()
        code = proposal.runbook_id.code
        dispatch = {
            "access_denied": self._execute_access_denied,
        }
        handler = dispatch.get(code)
        if not handler:
            raise UserError(
                _("Aucun exécuteur pour le runbook « %(code)s ».")
                % {"code": code}
            )
        return handler(proposal)

    @api.model
    def _execute_access_denied(self, proposal):
        """Réinitialise le mot de passe Odoo de l'utilisateur concerné."""
        ticket = proposal.ticket_id
        user = ticket.contact_user_id
        if not user:
            if ticket.partner_id:
                user = ticket.partner_id.user_ids.filtered("active")[:1]
            if not user:
                user = ticket.partner_id.user_ids[:1] if ticket.partner_id else user
        if not user:
            raise UserError(
                _("Renseignez l'utilisateur concerné sur le ticket avant d'exécuter ce correctif.")
            )
        if user.id == SUPERUSER_ID or user._is_superuser() or user.login in ("__system__",):
            raise UserError(
                _("Impossible de réinitialiser le mot de passe d'un compte système Odoo.")
            )

        now = fields.Datetime.now()
        executor = self.env.user
        actions = []

        if not user.active:
            user.sudo().write({"active": True})
            actions.append(_("Compte réactivé"))

        temp_password = self._generate_temp_password()
        ctx = user._crypt_context()
        user.sudo()._set_encrypted_password(user.id, ctx.hash(temp_password))
        actions.append(_("Mot de passe réinitialisé"))

        log_lines = [
            _("Runbook : %(code)s") % {"code": proposal.runbook_id.code},
            _("Utilisateur : %(login)s (id=%(uid)s)") % {"login": user.login, "uid": user.id},
            _("Exécuté par : %(user)s") % {"user": executor.name},
            _("Date : %(dt)s") % {
                "dt": format_datetime(self.env, now, dt_format="dd/MM/yyyy HH:mm"),
            },
            _("Actions : %(actions)s") % {"actions": ", ".join(actions)},
        ]
        execution_log = "\n".join(log_lines)

        _logger.info(
            "Support runbook access_denied ticket=%s user=%s proposal=%s executor=%s",
            ticket.name,
            user.login,
            proposal.name,
            executor.login,
        )

        ticket.message_post(
            body=_(
                "<p><em>Correctif exécuté</em> — mot de passe Odoo réinitialisé pour "
                "<strong>%(login)s</strong> (proposition %(prop)s).</p>",
                login=user.login,
                prop=proposal.name,
            ),
            subtype_xmlid="mail.mt_note",
        )

        return {
            "log": execution_log,
            "notify": {
                "title": _("Correctif exécuté"),
                "message": _(
                    "Mot de passe temporaire pour %(login)s : %(password)s — "
                    "communiquez-le au client par canal sécurisé.",
                    login=user.login,
                    password=temp_password,
                ),
                "type": "warning",
                "sticky": True,
            },
        }

    @api.model
    def _generate_temp_password(self, length=14):
        alphabet = string.ascii_letters + string.digits
        while True:
            password = "".join(secrets.choice(alphabet) for _ in range(length))
            if (
                any(c.islower() for c in password)
                and any(c.isupper() for c in password)
                and any(c.isdigit() for c in password)
            ):
                return password
