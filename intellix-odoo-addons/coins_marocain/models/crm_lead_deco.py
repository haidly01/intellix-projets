# -*- coding: utf-8 -*-
from odoo import _, api, fields, models
from odoo.exceptions import UserError


class CrmLeadDeco(models.Model):
    _inherit = "crm.lead"

    coins_is_deco_lead = fields.Boolean(
        string="Lead pipeline Coins Marocain (déco)",
        compute="_compute_coins_is_deco_lead",
        store=True,
        help="Équipe Coins Marocain (partenariats) uniquement. "
        "Pas Réno, pas CQ, pas voyageurs.",
    )
    coins_deco_prestataire_id = fields.Many2one(
        "coins.deco.prestataire",
        string="Prestataire déco",
        ondelete="set null",
        index=True,
        help="Lien optionnel vers la fiche déco — parallèle à Prestataires CRM, ne les remplace pas.",
    )
    coins_deco_lien = fields.Char(
        string="Lien fiche déco",
        compute="_compute_coins_deco_lien",
    )

    @api.depends("team_id")
    def _compute_coins_is_deco_lead(self):
        team = self.env.ref(
            "coins_marocain_partenariats.crm_team_coins_marocain",
            raise_if_not_found=False,
        )
        team_id = team.id if team else False
        for lead in self:
            lead.coins_is_deco_lead = bool(team_id and lead.team_id.id == team_id)

    @api.depends("coins_deco_prestataire_id", "coins_deco_prestataire_id.portal_token")
    def _compute_coins_deco_lien(self):
        for lead in self:
            deco = lead.coins_deco_prestataire_id
            lead.coins_deco_lien = deco._deco_public_url() if deco else ""

    def _coins_ensure_deco_prestataire(self):
        """Trouve ou crée le coins.deco.prestataire, génère le token au premier clic."""
        self.ensure_one()
        deco = self.coins_deco_prestataire_id
        if deco:
            deco._ensure_portal_token()
            return deco
        name = (
            (self.partner_name or self.contact_name or self.name or "").strip()
        )
        if not name:
            raise UserError(
                _("Indiquez le nom du prestataire (ou du contact) avant d’envoyer le lien.")
            )
        Deco = self.env["coins.deco.prestataire"].sudo()
        vals = {
            "name": name,
            "contact_name": (self.contact_name or self.partner_name or "").strip()
            or False,
            "phone": (self.phone or self.mobile or "").strip() or False,
            "email": (self.email_from or "").strip() or False,
            "onboarding_status": "brouillon",
        }
        deco = Deco.create(vals)
        deco._ensure_portal_token()
        self.coins_deco_prestataire_id = deco.id
        return deco

    def action_coins_envoyer_lien_deco_email(self):
        self.ensure_one()
        if not self.coins_is_deco_lead:
            raise UserError(
                _("Le lien fiche déco est réservé aux fiches Coins Marocain.")
            )
        email = (self.email_from or "").strip()
        if not email:
            raise UserError(_("Renseignez l’email sur la fiche avant d’envoyer."))
        deco = self._coins_ensure_deco_prestataire()
        template = self.env.ref(
            "coins_marocain.mail_template_lien_deco_prestataire_onboarding",
            raise_if_not_found=False,
        )
        if not template:
            raise UserError(_("Modèle d’email du lien prestataire déco introuvable."))
        email_values = {"email_to": email, "auto_delete": False}
        template.send_mail(
            self.id,
            force_send=True,
            raise_exception=True,
            email_values=email_values,
        )
        deco.write({"onboarding_status": "lien_envoye"})
        self.message_post(
            body=_("Lien prestataire déco envoyé par email à %s — %s")
            % (email, deco._deco_public_url())
        )
        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": _("Lien déco envoyé"),
                "message": _("Email envoyé à %s") % email,
                "type": "success",
                "sticky": False,
            },
        }
