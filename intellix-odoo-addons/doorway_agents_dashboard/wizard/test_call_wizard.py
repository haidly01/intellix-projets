# -*- coding: utf-8 -*-
import logging

from odoo import _, api, fields, models
from odoo.exceptions import UserError
from odoo.addons.doorway_agents_dashboard.services.config_loader import get_secret

_logger = logging.getLogger(__name__)


def _twilio_from_number(env):
    return get_secret(
        env,
        "TWILIO_FROM_NUMBER",
        "doorway_agents_dashboard.elevenlabs_from_number",
        [
            "doorway_agents_dashboard.twilio_phone_number",
            "renovation_conciergerie.retell_from_number",
        ],
    )


class TestCallWizard(models.TransientModel):
    _name = "doorway.test.call.wizard"
    _description = "Wizard — Lancer appel test agent IA"

    agent_id = fields.Many2one(
        "doorway.agent.profile",
        string="Agent",
        required=True,
    )
    call_mode = fields.Selection(
        [
            ("phone", "Appel téléphonique"),
            ("browser_mic", "Micro navigateur"),
        ],
        string="Mode test",
        required=True,
        default="phone",
    )
    phone_number = fields.Char(string="Numéro à appeler (ex: +15141234567)")
    call_volet = fields.Selection(
        [
            ("reception", "Réception"),
            ("qualification", "Lead qualification"),
            ("cold_call", "Appel à froid"),
        ],
        string="Volet",
    )
    scenario_hint = fields.Text(
        string="Scénario (optionnel)",
        help="Ex: Lead toiture urgent, budget 15 000$",
    )
    test_send_email = fields.Boolean(string="Tester action e-mail")
    test_send_sms = fields.Boolean(string="Tester action SMS")
    test_availability_check = fields.Boolean(string="Tester disponibilité")
    test_human_transfer = fields.Boolean(string="Tester transfert humain")
    expected_action_result = fields.Text(string="Résultat attendu")

    @api.onchange("agent_id")
    def _onchange_agent_id(self):
        for rec in self:
            if rec.agent_id:
                rec.call_volet = rec.agent_id.default_volet
                if rec.agent_id.default_phone_number_id:
                    rec.phone_number = rec.agent_id.default_phone_number_id.phone_number

    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        default_phone = (
            self.env["ir.config_parameter"]
            .sudo()
            .get_param("doorway_agents_dashboard.default_test_phone")
            or ""
        )
        if "phone_number" in fields_list and not res.get("phone_number"):
            partner = self.env.user.partner_id
            user_phone = partner.phone or ""
            res["phone_number"] = default_phone or user_phone or ""
        agent_id = res.get("agent_id")
        if agent_id and "phone_number" in fields_list and not res.get("phone_number"):
            agent = self.env["doorway.agent.profile"].browse(agent_id)
            if agent.default_phone_number_id:
                res["phone_number"] = agent.default_phone_number_id.phone_number
        return res

    def _create_test_call_vals(self):
        self.ensure_one()
        return {
            "agent_id": self.agent_id.id,
            "call_mode": self.call_mode,
            "phone_number": self.phone_number,
            "call_volet": self.call_volet or self.agent_id.default_volet,
            "scenario_hint": self.scenario_hint,
            "test_send_email": self.test_send_email,
            "test_send_sms": self.test_send_sms,
            "test_availability_check": self.test_availability_check,
            "test_human_transfer": self.test_human_transfer,
            "expected_action_result": self.expected_action_result,
            "state": "pending",
            "tested_by": self.env.uid,
        }

    def action_start_web_call(self):
        """Lance le test agent en appel web (navigateur)."""
        self.ensure_one()
        if self.agent_id.provider not in ("n8n", "retell", "elevenlabs"):
            raise UserError(_("Fournisseur non supporté pour le test web."))
        test_call = self.env["doorway.agent.test.call"].create(
            dict(self._create_test_call_vals(), call_mode="browser_mic")
        )
        return {
            "type": "ir.actions.client",
            "tag": "agent_web_call_action",
            "name": _("Test web — %s") % self.agent_id.name,
            "params": {"test_call_id": test_call.id},
        }

    def action_start_call(self):
        self.ensure_one()
        if self.call_mode == "browser_mic":
            return self.action_start_web_call()
        if self.call_mode == "phone" and not (self.phone_number or "").strip():
            raise UserError(_("Veuillez entrer un numéro de téléphone."))
        self.env["doorway.agent.test.call"]._ensure_call_window()

        test_call = self.env["doorway.agent.test.call"].create(
            dict(self._create_test_call_vals(), state="in_progress")
        )

        try:
            if self.agent_id.provider == "elevenlabs":
                from odoo.addons.doorway_agents_dashboard.services.elevenlabs_client import (
                    ElevenLabsClient,
                )

                from_number = _twilio_from_number(self.env)
                if not from_number:
                    raise UserError(_("Numéro émetteur Twilio manquant (TWILIO_FROM_NUMBER)."))
                test_call_pre = self.env["doorway.agent.test.call"].new(
                    {
                        "agent_id": self.agent_id.id,
                        "call_volet": self.call_volet or self.agent_id.default_volet,
                    }
                )
                result = ElevenLabsClient(self.env).start_phone_call(
                    self.agent_id.external_agent_id,
                    self.phone_number,
                    from_number,
                    dynamic_variables=test_call_pre._elevenlabs_dynamic_variables(),
                    agent_profile=self.agent_id,
                )
                test_call.write(
                    {
                        "external_call_id": result.get("conversation_id")
                        or result.get("call_id")
                        or result.get("id")
                        or "",
                    }
                )
            elif self.agent_id.provider in ("n8n", "retell"):
                agent = self.agent_id
                if agent.provider == "n8n" and agent.pipeline == "renovation":
                    from odoo.addons.doorway_agents_dashboard.services.telephony_adapter_service import (
                        TelephonyAdapterService,
                    )

                    raw = TelephonyAdapterService(self.env).initiate_outbound_call(
                        self.phone_number,
                        nombre=agent.name,
                        campaign=agent.external_agent_id,
                    )
                    result = {
                        "ok": raw.get("ok"),
                        "state": "in_progress",
                        "external_call_id": "",
                    }
                else:
                    from odoo.addons.doorway_agents_dashboard.services.n8n_client import (
                        N8NClient,
                    )

                    result = N8NClient(self.env).start_test_call(test_call)
                test_call.write(
                    {"external_call_id": result.get("external_call_id") or ""}
                )
            else:
                test_call.write({"state": "failed"})
                raise UserError(_("Fournisseur non supporté."))
        except UserError:
            raise
        except Exception as exc:  # noqa: BLE001
            _logger.exception("Erreur démarrage appel test")
            test_call.write({"state": "failed"})
            raise UserError(_("Erreur démarrage appel: %s") % exc) from exc

        return {
            "type": "ir.actions.act_window",
            "name": _("Appel test en cours"),
            "res_model": "doorway.agent.test.call",
            "res_id": test_call.id,
            "views": [[False, "form"]],
            "target": "new",
        }

    def action_launch(self):
        """Alias rétrocompatibilité."""
        return self.action_start_call()
