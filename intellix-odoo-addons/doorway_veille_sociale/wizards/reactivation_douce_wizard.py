# -*- coding: utf-8 -*-
from odoo import _, api, fields, models
from odoo.exceptions import UserError


class ReactivationDouceWizard(models.TransientModel):
    _name = "doorway.reactivation.douce.wizard"
    _description = "Réactivation douce d'un signal veille"

    signal_id = fields.Many2one(
        "doorway.veille.signal", required=True, ondelete="cascade"
    )
    titre = fields.Char(related="signal_id.titre", readonly=True)
    source = fields.Selection(related="signal_id.source", readonly=True)
    temperature = fields.Selection(related="signal_id.temperature", readonly=True)
    reactivation_statut = fields.Selection(
        related="signal_id.reactivation_statut", readonly=True
    )
    automation_id = fields.Many2one(
        "doorway.veille.reactivation.automation",
        string="Règle d'automatisation",
    )
    action_type = fields.Selection(
        [
            ("reponse_douce", "Réponse douce (commentaire)"),
            ("like", "Like / Upvote"),
            ("tache", "Créer une tâche"),
            ("notification", "Me notifier"),
        ],
        string="Action",
        default="reponse_douce",
        required=True,
    )
    message = fields.Text(string="Message")
    mode_api_disponible = fields.Boolean(
        compute="_compute_mode_api_disponible",
        string="API disponible",
    )
    hint_reactivation = fields.Char(compute="_compute_mode_api_disponible")

    @api.depends("signal_id", "signal_id.source", "signal_id.url", "action_type")
    def _compute_mode_api_disponible(self):
        for wiz in self:
            sig = wiz.signal_id
            api = False
            hint = ""
            if wiz.action_type == "like":
                if sig.source == "reddit":
                    api = bool(sig.url)
                    hint = _("Upvote Reddit si OAuth configuré.")
                elif sig.source in ("facebook", "instagram"):
                    api = bool(sig._get_external_object_id())
                    hint = _("Like Meta si token et ID post configurés.")
                else:
                    hint = _("Like non disponible — ouvrez la source manuellement.")
            elif wiz.action_type == "reponse_douce":
                sig._ensure_conversation_for_reply()
                api = sig.can_reply_api and sig._has_reply_target()
                if api:
                    hint = _("La réponse sera publiée via l'API.")
                elif sig.source == "google_alerts":
                    hint = _(
                        "Article presse — réponse enregistrée dans Odoo, "
                        "à publier manuellement sur le site."
                    )
                else:
                    hint = _(
                        "Pas d'API disponible — message enregistré, "
                        "publiez via le lien source."
                    )
            else:
                api = True
            wiz.mode_api_disponible = api
            wiz.hint_reactivation = hint

    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        signal = self.env["doorway.veille.signal"].browse(
            self.env.context.get("default_signal_id")
        )
        if signal:
            automations = signal._ensure_default_reactivation_automations()
            auto = signal.reactivation_automation_id
            if not auto:
                auto = signal._default_automation_for_signal(signal, automations)
            if auto:
                res.setdefault("automation_id", auto.id)
                res.setdefault("action_type", auto.action_type)
                res.setdefault("message", auto.message_modele)
            elif signal.source == "google_alerts":
                res.setdefault("action_type", "tache")
            if signal.reactivation_statut in (False, "none"):
                signal.action_assigner_automatisation()
        return res

    @api.onchange("automation_id")
    def _onchange_automation_id(self):
        if self.automation_id:
            self.action_type = self.automation_id.action_type
            if self.automation_id.message_modele:
                self.message = self.automation_id.message_modele

    def action_executer(self):
        self.ensure_one()
        automation = self.automation_id
        if not automation:
            Automation = self.env["doorway.veille.reactivation.automation"].sudo()
            automation = Automation.create(
                {
                    "name": _("Réactivation manuelle — %s") % (self.signal_id.titre or self.signal_id.id),
                    "action_type": self.action_type,
                    "message_modele": self.message or "",
                    "source_filtre": self.source or "all",
                }
            )
        elif self.action_type != automation.action_type:
            automation = automation.copy(
                default={
                    "name": _("%s (manuel)") % automation.name,
                    "action_type": self.action_type,
                    "auto_executer": False,
                }
            )
        self.signal_id._executer_reactivation(
            automation, message_override=self.message
        )
        return {"type": "ir.actions.act_window_close"}

    def action_planifier(self):
        self.ensure_one()
        from datetime import timedelta

        days = self.automation_id.delay_jours if self.automation_id else 3
        self.signal_id.write(
            {
                "reactivation_statut": "planifie",
                "reactivation_planifiee": fields.Datetime.now()
                + timedelta(days=days),
                "reactivation_automation_id": self.automation_id.id
                if self.automation_id
                else False,
            }
        )
        self.signal_id.message_post(
            body=_("Réactivation douce planifiée dans %s jour(s).") % days,
            subtype_xmlid="mail.mt_note",
        )
        return {"type": "ir.actions.act_window_close"}
