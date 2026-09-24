# -*- coding: utf-8 -*-
from odoo import _, api, fields, models
from odoo.exceptions import UserError


class PeCelebrationManualWizard(models.TransientModel):
    _name = "pe.celebration.manual.wizard"
    _description = "Déclencher une félicitation manuelle"

    employee_id = fields.Many2one(
        "hr.employee",
        string="Employé",
        required=True,
        domain=[("active", "=", True)],
    )
    profile_id = fields.Many2one(
        "pe.employee.profile",
        compute="_compute_profile_id",
    )
    from_profile = fields.Boolean(
        string="Depuis profil RH",
        default=lambda self: bool(self.env.context.get("default_from_profile")),
    )
    template_id = fields.Many2one(
        "pe.celebration.template",
        string="Utiliser un modèle",
        domain=[("active", "=", True)],
    )
    subject = fields.Char(
        string="Titre / sujet",
        help="Optionnel — affiché dans la note interne et comme sujet d'e-mail.",
    )
    message = fields.Html(
        string="Votre message",
        sanitize_attributes=False,
        help="Rédigez votre message de félicitation.",
    )
    occasion_date = fields.Date(
        string="Date de l'occasion",
        default=fields.Date.context_today,
        required=True,
    )
    detail = fields.Text(
        string="Message / détail (modèle équipe)",
        help="Texte libre injecté dans {{detail}} pour les envois équipe via modèle.",
    )
    send_employee_email = fields.Boolean(
        string="Envoyer un e-mail à l'employé",
        default=False,
    )
    send_team_email = fields.Boolean(
        string="Envoyer un e-mail à l'équipe",
        default=False,
    )
    force_resend = fields.Boolean(
        string="Forcer l'envoi",
        help="Ignore l'anti-doublon pour les félicitations planifiées (anniversaire, etc.).",
    )

    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        profile_id = self.env.context.get("default_profile_id")
        if profile_id and "employee_id" in fields_list and not res.get("employee_id"):
            profile = self.env["pe.employee.profile"].browse(profile_id)
            if profile.employee_id:
                res["employee_id"] = profile.employee_id.id
        if self.env.context.get("default_from_profile"):
            res.setdefault("from_profile", True)
            res.setdefault("send_team_email", False)
        return res

    @api.depends("employee_id")
    def _compute_profile_id(self):
        Profile = self.env["pe.employee.profile"]
        for wizard in self:
            wizard.profile_id = Profile.search(
                [("employee_id", "=", wizard.employee_id.id)],
                limit=1,
            )

    @api.onchange("template_id")
    def _onchange_template_id(self):
        if not self.template_id or not self.employee_id:
            return
        service = self.env["pe.celebration.service"]
        profile = self.profile_id
        if not profile:
            profile = self.env["pe.employee.profile"].search(
                [("employee_id", "=", self.employee_id.id)],
                limit=1,
            )
        extra = service._build_extra_values(
            self.employee_id,
            profile,
            self.occasion_date or fields.Date.context_today(self),
            detail=self.detail or "",
            anniversary_years=self.template_id.anniversary_years or 0,
        )
        self.message = service._render_content(
            self.template_id.email_body,
            profile,
            self.occasion_date or fields.Date.context_today(self),
            extra,
        )
        self.subject = service._render_content(
            self.template_id.email_subject,
            profile,
            self.occasion_date or fields.Date.context_today(self),
            extra,
        )
        if self.template_id.occasion_type in ("custom", "performance"):
            self.detail = self.detail or ""

    def action_send_celebration(self):
        self.ensure_one()
        service = self.env["pe.celebration.service"].sudo()
        message = (self.message or "").strip()

        if message:
            sent = service.send_on_demand_praise(
                self.employee_id,
                message,
                profile=self.profile_id,
                subject=self.subject,
                template=self.template_id,
                occasion_date=self.occasion_date,
                send_employee_email=self.send_employee_email,
                send_team_email=self.send_team_email,
                force=self.force_resend,
            )
            if not sent:
                raise UserError(
                    _(
                        "La félicitation n'a pas pu être envoyée "
                        "(employé introuvable ou doublon)."
                    )
                )
            if self.profile_id:
                self.env["pe.action.log"].log_action(
                    self.profile_id,
                    "praise_sent",
                    _("Félicitations envoyées par %s") % self.env.user.name,
                    actor_type="hr"
                    if self.env.user.has_group("people_engine.group_hr")
                    else "manager",
                )
            return {
                "type": "ir.actions.client",
                "tag": "display_notification",
                "params": {
                    "title": _("Félicitation envoyée"),
                    "message": _(
                        "La note interne a été publiée sur le profil"
                        + (
                            " et l'employé a été notifié."
                            if self.profile_id and self.employee_id.user_id
                            else "."
                        )
                    ),
                    "type": "success",
                    "sticky": False,
                },
            }

        if not self.template_id:
            raise UserError(_("Veuillez saisir votre message ou choisir un modèle."))

        occasion_type = self.template_id.occasion_type
        if occasion_type in ("custom", "performance") and not (self.detail or "").strip():
            raise UserError(
                _("Veuillez saisir un message / détail pour ce type de félicitation.")
            )

        sent = service.trigger_celebration(
            self.employee_id,
            occasion_type,
            occasion_date=self.occasion_date,
            detail=self.detail or "",
            template=self.template_id,
            anniversary_years=self.template_id.anniversary_years or 0,
            force=self.force_resend,
        )
        if not sent:
            raise UserError(
                _(
                    "La félicitation n'a pas pu être envoyée "
                    "(modèle manquant, opt-out ou doublon)."
                )
            )
        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": _("Félicitation envoyée"),
                "message": _("L'e-mail équipe et la notification ont été déclenchés."),
                "type": "success",
                "sticky": False,
            },
        }


class PeCelebrationSettings(models.TransientModel):
    _name = "pe.celebration.settings"
    _description = "Paramètres félicitations RH"

    enabled_birthday = fields.Boolean(string="Anniversaires")
    enabled_anniversary_1y = fields.Boolean(string="Ancienneté 1 an")
    enabled_anniversary_3y = fields.Boolean(string="Ancienneté 3 ans")
    enabled_anniversary_5y = fields.Boolean(string="Ancienneté 5 ans")
    enabled_anniversary_10y = fields.Boolean(string="Ancienneté 10 ans+")
    enabled_anniversary_other = fields.Boolean(string="Paliers personnalisés")
    enabled_performance = fields.Boolean(string="Performance")
    enabled_promotion = fields.Boolean(string="Promotions")
    enabled_custom = fields.Boolean(string="Personnalisé (manuel)")
    exclude_honoree_email = fields.Boolean(
        string="Exclure l'employé des e-mails équipe",
        default=True,
    )

    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        ICP = self.env["ir.config_parameter"].sudo()
        mapping = {
            "enabled_birthday": "people_engine.celebration.enabled.birthday",
            "enabled_anniversary_1y": "people_engine.celebration.enabled.anniversary_1y",
            "enabled_anniversary_3y": "people_engine.celebration.enabled.anniversary_3y",
            "enabled_anniversary_5y": "people_engine.celebration.enabled.anniversary_5y",
            "enabled_anniversary_10y": "people_engine.celebration.enabled.anniversary_10y",
            "enabled_anniversary_other": "people_engine.celebration.enabled.anniversary_other",
            "enabled_performance": "people_engine.celebration.enabled.performance",
            "enabled_promotion": "people_engine.celebration.enabled.promotion",
            "enabled_custom": "people_engine.celebration.enabled.custom",
            "exclude_honoree_email": "people_engine.celebration.exclude_honoree_email",
        }
        for field, key in mapping.items():
            if field in fields_list:
                res[field] = ICP.get_param(key, "True").lower() in (
                    "1",
                    "true",
                    "yes",
                    "on",
                )
        return res

    def action_save(self):
        self.ensure_one()
        ICP = self.env["ir.config_parameter"].sudo()
        mapping = {
            "enabled_birthday": "people_engine.celebration.enabled.birthday",
            "enabled_anniversary_1y": "people_engine.celebration.enabled.anniversary_1y",
            "enabled_anniversary_3y": "people_engine.celebration.enabled.anniversary_3y",
            "enabled_anniversary_5y": "people_engine.celebration.enabled.anniversary_5y",
            "enabled_anniversary_10y": "people_engine.celebration.enabled.anniversary_10y",
            "enabled_anniversary_other": "people_engine.celebration.enabled.anniversary_other",
            "enabled_performance": "people_engine.celebration.enabled.performance",
            "enabled_promotion": "people_engine.celebration.enabled.promotion",
            "enabled_custom": "people_engine.celebration.enabled.custom",
            "exclude_honoree_email": "people_engine.celebration.exclude_honoree_email",
        }
        for field, key in mapping.items():
            ICP.set_param(key, "True" if getattr(self, field) else "False")
        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": "Paramètres enregistrés",
                "message": "Les types d'occasions ont été mis à jour.",
                "type": "success",
                "sticky": False,
            },
        }
