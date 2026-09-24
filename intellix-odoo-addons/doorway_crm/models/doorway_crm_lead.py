# -*- coding: utf-8 -*-
from pathlib import Path

from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError


class DoorwayCrmLead(models.Model):
    _inherit = "crm.lead"

    @api.constrains("email_from")
    def _check_unique_email(self):
        """Autorise les doublons pour la réception mail ; contrôle manuel uniquement."""
        if self.env.context.get("doorway_skip_email_unique_check"):
            return
        if self.env.context.get("doorway_mailbox_sync"):
            return
        if self.env.context.get("default_fetchmail_server_id"):
            return
        for record in self:
            if not record.email_from or record.email_from == "email not available":
                continue
            duplicate = self.search([
                ("email_from", "=ilike", record.email_from),
                ("id", "!=", record.id),
                ("active", "=", True),
            ], limit=1)
            if duplicate:
                raise ValidationError(
                    _("Erreur : Cet email existe deja ! (piste #%s)")
                    % duplicate.id
                )

    nav_position = fields.Char(
        string="Position navigation",
        compute="_compute_nav_position",
    )
    doorway_activity_count = fields.Integer(
        string="Activités ouvertes",
        compute="_compute_doorway_activity_count",
    )
    doorway_coins_partner_lead = fields.Boolean(
        string="Lead partenaire Coins",
        compute="_compute_doorway_coins_partner_lead",
    )

    def _compute_doorway_coins_partner_lead(self):
        has_flag = "coins_is_partner_lead" in self._fields
        for rec in self:
            rec.doorway_coins_partner_lead = bool(rec.coins_is_partner_lead) if has_flag else False

    @api.depends("team_id", "stage_id", "user_id")
    def _compute_nav_position(self):
        for rec in self:
            rec.nav_position = rec._get_navigation_position()

    def _compute_doorway_activity_count(self):
        Activity = self.env["mail.activity"]
        for rec in self:
            if not rec.id:
                rec.doorway_activity_count = 0
                continue
            rec.doorway_activity_count = Activity.search_count([
                ("res_model", "=", "crm.lead"),
                ("res_id", "=", rec.id),
                ("active", "=", True),
            ])

    def _get_navigation_domain(self):
        """Domaine de navigation : pipeline + étape (+ filtre contexte kanban)."""
        ctx = self.env.context
        domain = [("type", "=", "opportunity"), ("active", "=", True)]
        team_id = ctx.get("doorway_nav_team_id") or (self.team_id.id if self.team_id else False)
        stage_id = ctx.get("doorway_nav_stage_id") or (self.stage_id.id if self.stage_id else False)
        if team_id:
            domain.append(("team_id", "=", team_id))
        if stage_id:
            domain.append(("stage_id", "=", stage_id))
        if ctx.get("doorway_nav_user_id"):
            domain.append(("user_id", "=", ctx["doorway_nav_user_id"]))
        return domain

    def _get_navigation_order(self):
        return "priority desc, date_deadline asc, id asc"

    def _get_navigation_position(self):
        self.ensure_one()
        if not self.id:
            return "— / —"
        leads = self.search(self._get_navigation_domain(), order=self._get_navigation_order())
        ids = leads.ids
        if self.id not in ids:
            return f"— / {len(ids)}"
        return f"{ids.index(self.id) + 1} / {len(ids)}"

    def _open_lead(self, lead_id):
        return {
            "type": "ir.actions.act_window",
            "res_model": "crm.lead",
            "res_id": lead_id,
            "view_mode": "form",
            "target": "current",
            "context": {
                **self.env.context,
                "doorway_nav_team_id": self.team_id.id if self.team_id else False,
                "doorway_nav_stage_id": self.stage_id.id if self.stage_id else False,
            },
        }

    def action_prev_lead(self):
        self.ensure_one()
        leads = self.search(self._get_navigation_domain(), order=self._get_navigation_order())
        ids = leads.ids
        if not ids:
            return self._open_lead(self.id)
        if self.id not in ids:
            return self._open_lead(ids[-1])
        idx = ids.index(self.id)
        prev_id = ids[idx - 1] if idx > 0 else ids[-1]
        return self._open_lead(prev_id)

    def action_next_lead(self):
        self.ensure_one()
        leads = self.search(self._get_navigation_domain(), order=self._get_navigation_order())
        ids = leads.ids
        if not ids:
            return self._open_lead(self.id)
        if self.id not in ids:
            return self._open_lead(ids[0])
        idx = ids.index(self.id)
        next_id = ids[idx + 1] if idx + 1 < len(ids) else ids[0]
        return self._open_lead(next_id)

    def action_doorway_schedule_activity(self):
        """Ouvre l'assistant natif de planification d'activité."""
        self.ensure_one()
        return {
            "name": _("Planifier une activité"),
            "type": "ir.actions.act_window",
            "res_model": "mail.activity.schedule",
            "view_mode": "form",
            "views": [(False, "form")],
            "target": "new",
            "context": {
                "active_model": "crm.lead",
                "active_id": self.id,
                "active_ids": [self.id],
                "default_res_model": "crm.lead",
                "default_res_id": self.id,
            },
        }

    def action_doorway_phone_call(self):
        self.ensure_one()
        phone = (self.phone or "").strip()
        if not phone:
            return {
                "type": "ir.actions.client",
                "tag": "display_notification",
                "params": {
                    "title": _("Téléphone"),
                    "message": _("Aucun numéro renseigné sur cette opportunité."),
                    "type": "warning",
                    "sticky": False,
                },
            }
        return {
            "type": "ir.actions.client",
            "tag": "vicidial_workstation_action",
            "params": {
                "doorway_vicidial_dial_phone": phone,
                "doorway_vicidial_lead_id": self.id,
            },
        }

    def action_doorway_send_email(self):
        self.ensure_one()
        if not self.email_from:
            return {
                "type": "ir.actions.client",
                "tag": "display_notification",
                "params": {
                    "title": _("Email"),
                    "message": _("Aucune adresse email sur cette opportunité."),
                    "type": "warning",
                    "sticky": False,
                },
            }
        ctx = {
            "default_model": "crm.lead",
            "default_res_ids": self.ids,
            "default_composition_mode": "comment",
            "default_partner_ids": self.partner_id.ids,
            "mail_post_autofollow": True,
        }
        hotel = self._coins_hotel_mail_template()
        if hotel:
            ctx["default_template_id"] = hotel.id
            ctx["default_use_template"] = True
        return {
            "type": "ir.actions.act_window",
            "name": _("Envoyer un email"),
            "res_model": "mail.compose.message",
            "view_mode": "form",
            "target": "new",
            "context": ctx,
        }

    def _coins_hotel_mail_template(self):
        if getattr(self, "coins_is_partner_lead", False):
            pass
        else:
            team = self.team_id
            name = (team.name or "").lower() if team else ""
            if "coins marocain" not in name:
                return self.env["mail.template"]
        template = self.env.ref(
            "coins_marocain_partenariats.mail_template_zakaria_channel_manager",
            raise_if_not_found=False,
        )
        if template:
            return template
        return self.env["mail.template"].sudo().search(
            [("model", "=", "crm.lead"), ("name", "ilike", "Entente Channel Manager")],
            limit=1,
        )

    PARTNER_WELCOME_XMLID = "doorway_crm.mail_template_partner_welcome_video"
    PARTNER_WELCOME_NAME = "Partenaire — Bienvenue + vidéo IntelliX"
    PARTNER_SOURCE_NAME = "Agent / Partenaire"

    def _ensure_partner_source(self):
        Source = self.env["utm.source"].sudo()
        source = Source.search([("name", "=ilike", self.PARTNER_SOURCE_NAME)], limit=1)
        if not source:
            source = Source.create({"name": self.PARTNER_SOURCE_NAME})
        return source

    def _ensure_partner_welcome_template(self):
        template = self.env.ref(self.PARTNER_WELCOME_XMLID, raise_if_not_found=False)
        if template:
            return template
        Template = self.env["mail.template"].sudo()
        template = Template.search([("name", "=", self.PARTNER_WELCOME_NAME)], limit=1)
        if not template:
            html_path = Path("/odoo/custom/addons/doorway_crm/data/email_partner_welcome.html")
            body = html_path.read_text(encoding="utf-8")
            model = self.env["ir.model"].sudo().search([("model", "=", "crm.lead")], limit=1)
            template = Template.create({
                "name": self.PARTNER_WELCOME_NAME,
                "model_id": model.id,
                "subject": "{{ (object.contact_name or object.partner_id.name or 'Bonjour').split()[0] }}, tes leads arrivent maintenant — IntelliX",
                "body_html": body,
                "use_default_to": True,
                "auto_delete": False,
            })
        if not self.env.ref(self.PARTNER_WELCOME_XMLID, raise_if_not_found=False):
            self.env["ir.model.data"].sudo()._update_xmlids([{
                "xml_id": self.PARTNER_WELCOME_XMLID,
                "record": template,
                "noupdate": True,
            }])
        return template

    def action_send_partner_welcome_email(self):
        self.ensure_one()
        if not self.email_from:
            raise UserError(_("Indiquez l'email du partenaire avant d'envoyer le modèle."))
        if not (self.city or self.state_id):
            raise UserError(_(
                "Validez la région du partenaire (ville ou province) avant d'envoyer l'email."
            ))
        template = self._ensure_partner_welcome_template()
        if not self.source_id:
            self.source_id = self._ensure_partner_source().id
        return {
            "type": "ir.actions.act_window",
            "name": _("Email partenaire — vidéo IntelliX"),
            "res_model": "mail.compose.message",
            "view_mode": "form",
            "target": "new",
            "context": {
                "default_model": "crm.lead",
                "default_res_ids": self.ids,
                "default_template_id": template.id,
                "default_use_template": True,
                "default_composition_mode": "comment",
                "default_partner_ids": self.partner_id.ids,
                "mail_post_autofollow": True,
            },
        }


    def action_send_coins_hotel_email(self):
        """Prospection hôtels Coins Marocain — vidéo + Channel Manager, avant l entente."""
        self.ensure_one()
        if not getattr(self, "coins_is_partner_lead", False):
            raise UserError(_(
                "L'email prospection hôtels est réservé aux fiches Coins Marocain."
            ))
        if not self.email_from:
            raise UserError(_("Indiquez l email de l hôtel avant d envoyer le modèle."))
        template = self.env.ref(
            "coins_marocain_partenariats.mail_template_zakaria_channel_manager",
            raise_if_not_found=False,
        )
        if not template:
            template = self.env["mail.template"].sudo().search(
                [
                    ("model", "=", "crm.lead"),
                    "|",
                    ("name", "ilike", "Prospection hôtels"),
                    ("name", "ilike", "Channel Manager"),
                ],
                limit=1,
            )
        if not template:
            raise UserError(_("Modèle de prospection hôtels introuvable."))
        return {
            "type": "ir.actions.act_window",
            "name": _("Email prospection hôtels — Channel Manager"),
            "res_model": "mail.compose.message",
            "view_mode": "form",
            "target": "new",
            "context": {
                "default_model": "crm.lead",
                "default_res_ids": self.ids,
                "default_template_id": template.id,
                "default_use_template": True,
                "default_composition_mode": "comment",
                "default_partner_ids": self.partner_id.ids,
                "mail_post_autofollow": True,
            },
        }

    def action_open_business_card_scan(self):
        self.ensure_one()
        return self.env["doorway.business.card"].action_open_scan_client(
            target_model="crm.lead",
            record_id=self.id,
            team_id=self.team_id.id if self.team_id else None,
        )

    @api.model
    def action_open_business_card_scan_new(self):
        team_id = self.env.context.get("default_team_id")
        return self.env["doorway.business.card"].action_open_scan_client(
            target_model="crm.lead",
            team_id=team_id,
        )
