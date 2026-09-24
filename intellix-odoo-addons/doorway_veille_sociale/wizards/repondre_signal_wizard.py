# -*- coding: utf-8 -*-
from odoo import _, api, fields, models
from odoo.exceptions import UserError


class DoorwayRepondreSignalWizard(models.TransientModel):
    _name = "doorway.repondre.signal.wizard"
    _description = "Répondre à un signal de veille"

    signal_id = fields.Many2one("doorway.veille.signal", required=True, ondelete="cascade")
    source = fields.Selection(related="signal_id.source", readonly=True)
    plateforme = fields.Char(related="signal_id.plateforme", readonly=True)
    url = fields.Char(related="signal_id.url", readonly=True)
    titre = fields.Char(related="signal_id.titre", readonly=True)
    resume = fields.Char(related="signal_id.resume", readonly=True)
    texte_original = fields.Text(related="signal_id.texte", readonly=True)
    action_suggeree = fields.Char(related="signal_id.action_suggeree", readonly=True)
    can_reply_api = fields.Boolean(related="signal_id.can_reply_api", readonly=True)
    reply_api_source = fields.Selection(related="signal_id.reply_api_source", readonly=True)
    reply_channel_hint = fields.Char(related="signal_id.reply_channel_hint", readonly=True)
    conversation_synced_at = fields.Datetime(
        related="signal_id.conversation_synced_at", readonly=True
    )
    conversation_message_ids = fields.One2many(
        related="signal_id.conversation_message_ids",
        readonly=True,
        string="Fil de conversation",
    )
    reponse_brouillon = fields.Text(string="Votre réponse")

    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        signal = self.env["doorway.veille.signal"].browse(
            self.env.context.get("default_signal_id")
        )
        if signal:
            try:
                signal.action_sync_conversation()
            except UserError:
                pass
        return res

    def action_actualiser_conversation(self):
        self.ensure_one()
        self.signal_id.action_sync_conversation()
        return {
            "type": "ir.actions.act_window",
            "name": _("Répondre au signal"),
            "res_model": "doorway.repondre.signal.wizard",
            "view_mode": "form",
            "res_id": self.id,
            "target": "new",
        }

    def action_ouvrir_source(self):
        """Ouvre le post / alerte dans un nouvel onglet."""
        self.ensure_one()
        if not self.url:
            raise UserError(
                _(
                    "Aucun lien enregistré pour ce signal. "
                    "Vérifiez la connexion n8n (Facebook, Instagram, Google Alerts)."
                )
            )
        return {"type": "ir.actions.act_url", "url": self.signal_id._get_open_url(), "target": "new"}

    def action_envoyer_reponse(self):
        """Publie la réponse via Meta (Facebook / Instagram)."""
        self.ensure_one()
        if not self.reponse_brouillon:
            raise UserError(_("Rédigez votre réponse avant d'envoyer."))
        self.signal_id.action_send_reply(self.reponse_brouillon)
        return {"type": "ir.actions.act_window_close"}

    def action_enregistrer_reponse(self):
        """Enregistre le brouillon (réponse manuelle sur la plateforme)."""
        self.ensure_one()
        self.signal_id.action_marquer_repondu()
        body = _("<p><b>Réponse enregistrée (manuelle)</b></p><p>%s</p>") % (
            self.reponse_brouillon or _("(réponse sur la plateforme)")
        )
        if self.url:
            body += '<p><a href="%s" target="_blank">Lien source</a></p>' % self.url
        self.signal_id.message_post(body=body, subtype_xmlid="mail.mt_note")
        if self.reponse_brouillon:
            self.env["doorway.veille.conversation.message"].sudo().create(
                {
                    "signal_id": self.signal_id.id,
                    "direction": "outbound",
                    "author_name": self.env.user.name,
                    "body": self.reponse_brouillon,
                    "posted_at": fields.Datetime.now(),
                    "platform": self.source,
                }
            )
        if self.signal_id.odoo_lead_id:
            self.signal_id.odoo_lead_id.message_post(
                body=_("<p><b>Veille — réponse manuelle</b></p><p>%s</p>")
                % (self.reponse_brouillon or ""),
                subtype_xmlid="mail.mt_note",
            )
        return {"type": "ir.actions.act_window_close"}

    def action_planifier_tache(self):
        """Crée une tâche projet avec le lien et le brouillon."""
        self.ensure_one()
        if self.reponse_brouillon:
            self.signal_id.message_post(
                body=_("<p><b>Brouillon :</b> %s</p>") % self.reponse_brouillon,
                subtype_xmlid="mail.mt_note",
            )
        return self.signal_id.action_planifier_reponse()

    def action_creer_lead(self):
        """Ouvre le wizard lead CRM (optionnel — indépendant de la réponse)."""
        self.ensure_one()
        return self.signal_id.action_creer_lead()
