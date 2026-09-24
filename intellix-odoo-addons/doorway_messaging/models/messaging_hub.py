# -*- coding: utf-8 -*-
from odoo import api, models


class DoorwayMessagingHub(models.AbstractModel):
    _name = "doorway.messaging.hub"
    _description = "API tableau de bord Messaging Hub"

    @api.model
    def get_hub_data(self):
        """Données sérialisées pour le dashboard OWL Messaging Hub."""
        icp = self.env["ir.config_parameter"].sudo()
        Channel = self.env["doorway.channel.config"].sudo()
        Log = self.env["doorway.message.log"].sudo()
        Campaign = self.env["doorway.message.campaign"].sudo()

        twilio_sid = icp.get_param("doorway_messaging.twilio_account_sid") or icp.get_param(
            "doorway_agents_dashboard.twilio_account_sid"
        )
        twilio_token = icp.get_param("doorway_messaging.twilio_auth_token") or icp.get_param(
            "doorway_agents_dashboard.twilio_auth_token"
        )
        twilio_ok = bool(twilio_sid and twilio_token)
        smtp_ok = bool(self.env["ir.mail_server"].sudo().search([], limit=1))

        canal_defs = [
            ("email", "Email", "fa-envelope", "#6366f1"),
            ("sms", "SMS", "fa-comment", "#1d9e75"),
            ("whatsapp", "WhatsApp", "fa-whatsapp", "#25d366"),
            ("linkedin", "LinkedIn", "fa-linkedin", "#0a66c2"),
            ("gmb", "Google & Business", "fa-google", "#4285f4"),
        ]

        channels = []
        for canal, title, icon, color in canal_defs:
            configs = Channel.search([("canal", "=", canal)])
            active_configs = configs.filtered("actif")
            if canal in ("email",):
                connected = smtp_ok or bool(active_configs)
                status_label = "Connecté" if connected else "Non configuré"
            elif canal in ("sms", "whatsapp"):
                connected = twilio_ok or bool(active_configs)
                status_label = "Twilio OK" if connected else "Twilio manquant"
            else:
                connected = bool(active_configs.filtered("access_token"))
                status_label = "OAuth actif" if connected else "OAuth requis"

            sent = Log.search_count([("canal", "=", canal), ("statut", "in", ("envoye", "lu"))])
            errors = Log.search_count([("canal", "=", canal), ("statut", "=", "erreur")])
            config_id = active_configs[:1].id or configs[:1].id or False

            channels.append(
                {
                    "canal": canal,
                    "title": title,
                    "icon": icon,
                    "color": color,
                    "connected": connected,
                    "status_label": status_label,
                    "sent_count": sent,
                    "error_count": errors,
                    "config_id": config_id,
                    "config_name": (active_configs[:1] or configs[:1]).name or "",
                    "config_count": len(configs),
                }
            )

        campaign_total = Campaign.search_count([])
        campaign_active = Campaign.search_count(
            [("statut", "in", ("planifie", "en_cours"))]
        )
        campaign_draft = Campaign.search_count([("statut", "=", "brouillon")])

        return {
            "channels": channels,
            "campaign_stats": {
                "total": campaign_total,
                "active": campaign_active,
                "draft": campaign_draft,
            },
            "features": {
                "social_inbox": bool(
                    self.env["ir.model"].sudo().search([("model", "=", "doorway.social.inbox")], limit=1)
                ),
            },
        }

    @api.model
    def disconnect_channel(self, canal):
        configs = self.env["doorway.channel.config"].sudo().search(
            [("canal", "=", canal), ("actif", "=", True)]
        )
        configs.write({"actif": False})
        return True
