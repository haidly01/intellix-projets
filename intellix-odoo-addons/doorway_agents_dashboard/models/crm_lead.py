# -*- coding: utf-8 -*-
import logging

from odoo import _, api, fields, models
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)

TEAM_PIPELINE_MAP = {
    "rénovation": "renovation",
    "renovation": "renovation",
    "immobilier": "immobilier",
    "marketing": "marketing",
    "driven": "driven",
    "assurance": "assurance",
    "doorway clients": "doorway",
    "doorway": "doorway",
}


class CrmLead(models.Model):
    _inherit = "crm.lead"

    doorway_pipeline_key = fields.Selection(
        [
            ("renovation", "Rénovation"),
            ("immobilier", "Immobilier"),
            ("marketing", "Marketing"),
            ("driven", "Driven (B2B)"),
            ("assurance", "Assurance"),
            ("doorway", "Doorway Clients"),
        ],
        string="Pipeline agents IA",
        compute="_compute_doorway_pipeline_key",
        store=True,
    )
    doorway_agent_profile_id = fields.Many2one(
        "doorway.agent.profile",
        string="Agent IA pour l'appel",
        tracking=True,
        domain="[('status', '=', 'active')]",
        help="Agent ElevenLabs / Twilio qui appellera le contact.",
    )
    doorway_call_volet = fields.Selection(
        [
            ("reception", "Réception"),
            ("qualification", "Lead qualification"),
            ("cold_call", "Appel à froid"),
        ],
        string="Volet agent IA",
    )
    vicidial_campaign_id = fields.Char(string="Campagne VICIdial", index=True)
    doorway_call_session_ids = fields.One2many(
        "doorway.call.session", "lead_id", string="Sessions d'appel IA"
    )

    @api.depends("team_id", "team_id.name")
    def _compute_doorway_pipeline_key(self):
        for lead in self:
            lead.doorway_pipeline_key = lead._doorway_pipeline_key_from_team()

    def _doorway_pipeline_key_from_team(self):
        self.ensure_one()
        name = (self.team_id.name or "").lower()
        for token, key in TEAM_PIPELINE_MAP.items():
            if token in name:
                return key
        return "doorway"

    @api.onchange("team_id")
    def _onchange_team_id_doorway_agent(self):
        for lead in self:
            if lead.doorway_agent_profile_id:
                continue
            lead.doorway_agent_profile_id = lead._default_doorway_agent_for_pipeline()

    def _default_doorway_agent_for_pipeline(self):
        self.ensure_one()
        pipeline = self._doorway_pipeline_key_from_team()
        Profile = self.env["doorway.agent.profile"]
        if pipeline == "immobilier":
            maison = Profile.get_maison_immo_qualification_profile()
            if maison:
                return maison
        return Profile.search(
            [
                ("status", "=", "active"),
                ("pipeline", "in", [pipeline, "doorway"]),
            ],
            order="agent_type desc, id",
            limit=1,
        )

    def _doorway_call_to_number(self):
        self.ensure_one()
        lead = self
        partner = lead.partner_id
        return (
            lead.phone
            or getattr(lead, "mobile", None)
            or partner.phone
            or getattr(partner, "mobile", None)
        )

    def action_call_contact_via_agent_ia(self):
        """Lance un appel sortant via l'agent IA sélectionné (ElevenLabs + Twilio ou n8n)."""
        self.ensure_one()
        to_number = (self._doorway_call_to_number() or "").strip()
        if not to_number:
            raise UserError(_("Aucun numéro de téléphone n'est renseigné sur cette opportunité."))

        agent = self.doorway_agent_profile_id
        if not agent:
            agent = self._default_doorway_agent_for_pipeline()
            if agent:
                self.doorway_agent_profile_id = agent
        if not agent:
            raise UserError(
                _(
                    "Sélectionnez un agent IA sur l'opportunité, "
                    "ou configurez un agent actif pour ce pipeline."
                )
            )

        from odoo.addons.doorway_agents_dashboard.wizard.test_call_wizard import (
            _twilio_from_number,
        )

        phone_line = agent.default_phone_number_id
        if agent.agent_type == "outbound" and agent.phone_number_ids:
            outbound_line = agent.phone_number_ids.filtered(
                lambda p: p.active and p.usage == "outbound"
            )[:1]
            if outbound_line:
                phone_line = outbound_line
        volet = agent._resolve_volet(self.doorway_call_volet or agent.default_volet)
        from_number = (
            phone_line.phone_number if phone_line else _twilio_from_number(self.env)
        )
        if not from_number:
            raise UserError(
                _(
                    "Numéro émetteur Twilio manquant. "
                    "Configurez TWILIO_FROM_NUMBER ou un numéro sur l'agent."
                )
            )

        session = self.env["doorway.call.session"].create(
            {
                "lead_id": self.id,
                "agent_id": agent.id,
                "to_number": to_number,
                "from_number": from_number,
                "call_status": "initiated",
            }
        )

        external_id = ""
        try:
            if agent.provider == "elevenlabs":
                from odoo.addons.doorway_agents_dashboard.services.elevenlabs_client import (
                    ElevenLabsClient,
                )

                body = ElevenLabsClient(self.env).start_phone_call(
                    agent.external_agent_id,
                    to_number,
                    from_number,
                    dynamic_variables={
                        "lead_name": self.contact_name or self.name,
                        "property_address": self.street or "",
                        "selling_timeline": self.immo_selling_timeline or "",
                        "lead_id_odoo": str(self.id),
                    },
                    agent_profile=agent,
                )
                external_id = (
                    body.get("conversation_id")
                    or body.get("call_id")
                    or body.get("conversation_id")
                    or body.get("id")
                    or ""
                )
            elif agent.provider in ("n8n", "retell"):
                from odoo.addons.doorway_agents_dashboard.services.n8n_client import (
                    N8NClient,
                )

                test_call = self.env["doorway.agent.test.call"].create(
                    {
                        "agent_id": agent.id,
                        "call_mode": "phone",
                        "phone_number": to_number,
                        "call_volet": volet,
                        "scenario_hint": _("Appel opportunité %s") % (self.name or self.id),
                        "state": "in_progress",
                        "tested_by": self.env.uid,
                    }
                )
                result = N8NClient(self.env).start_test_call(test_call)
                if not result.get("ok"):
                    raise UserError(result.get("message") or _("Échec démarrage appel n8n."))
                external_id = result.get("external_call_id") or ""
            else:
                raise UserError(_("Fournisseur d'agent non supporté : %s") % agent.provider)
        except UserError:
            session.write({"call_status": "failed"})
            raise
        except Exception as exc:  # noqa: BLE001
            _logger.exception("Appel Agent IA opportunité %s", self.id)
            session.write({"call_status": "failed"})
            raise UserError(_("Erreur lors de l'appel Agent IA : %s") % exc) from exc

        session.write(
            {
                "twilio_call_sid": external_id or session.twilio_call_sid,
                "call_status": "ringing",
            }
        )

        vals = {"lead_provenance": "retell"}
        if not self.team_id:
            default_team = self.env.ref(
                "renovation_conciergerie.crm_team_renovation", raise_if_not_found=False
            )
            if default_team:
                vals["team_id"] = default_team.id
        self.write(vals)

        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": _("Appel Agent IA"),
                "message": _("Appel lancé avec %(agent)s vers %(phone)s.")
                % {"agent": agent.name, "phone": to_number},
                "type": "success",
                "sticky": False,
            },
        }

    def action_assign_vicidial_campaign(self):
        """Assigne le lead à la campagne VICIdial selon le pipeline."""
        Campaign = self.env["doorway.campaign"]
        from odoo.addons.doorway_agents_dashboard.services.vicidial_coaching_service import (
            VicidialService as VS,
        )

        pipeline_map = {
            "Rénovation": "renovation",
            "Driven": "driven",
            "Marketing": "marketing",
            "Assurance": "assurance",
        }
        svc = VS(self.env)
        for lead in self:
            pipeline = pipeline_map.get(lead.team_id.name or "", "renovation")
            campaign = Campaign.search(
                [("pipeline", "=", pipeline), ("active", "=", True)], limit=1
            )
            if not campaign:
                continue
            lead_data = {
                "phone": lead.phone or lead.mobile or "",
                "first_name": lead.contact_name or lead.name or "",
                "last_name": "",
                "vendor_code": "LEAD-%s" % lead.id,
            }
            if svc.assign_lead_to_campaign(lead_data, campaign.vicidial_campaign_id):
                lead.vicidial_campaign_id = campaign.vicidial_campaign_id
