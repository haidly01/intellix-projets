# -*- coding: utf-8 -*-
from odoo import api, fields, models, _
from odoo.exceptions import UserError


class CrmLead(models.Model):
    _inherit = "crm.lead"

    coins_show_envoyer_signature = fields.Boolean(
        string="Afficher Envoyer pour signature",
        compute="_compute_coins_show_envoyer_signature",
    )

    def _coins_is_hebergement_standard(self):
        """Modèle standard = catégorie Hébergement uniquement (pas resto / spa)."""
        self.ensure_one()
        cat = self.coins_categorie_etab or self.coins_type_partenaire
        return cat in ("hebergement", "riad", "villa", "hotel", "apartment")

    def _coins_lead_is_frozen_djemanna(self):
        self.ensure_one()
        blob = " ".join(
            [
                self.coins_etablissement or "",
                self.name or "",
                self.partner_name or "",
            ]
        ).lower()
        if "djemanna" in blob:
            return True
        if self.coins_sale_order_id and self.coins_sale_order_id.name == "S00021":
            return True
        if self.coins_entente_id and self.coins_entente_id._coins_is_frozen_djemanna():
            return True
        return False

    @api.depends(
        "coins_is_partner_lead",
        "coins_categorie_etab",
        "coins_type_partenaire",
        "coins_etablissement",
        "name",
        "coins_entente_id",
        "coins_sale_order_id",
    )
    def _compute_coins_show_envoyer_signature(self):
        for lead in self:
            lead.coins_show_envoyer_signature = bool(
                lead.coins_is_partner_lead
                and lead._coins_is_hebergement_standard()
                and not lead._coins_lead_is_frozen_djemanna()
                and not (hasattr(lead, "_coins_is_quebec_market") and lead._coins_is_quebec_market())
            )

    def _coins_lead_wants_visibilite_only(self):
        """Sans Channel Manager / shooting au devis : modèle visibilité 15 % seule."""
        self.ensure_one()
        order = self.coins_sale_order_id
        if order and hasattr(order, "_coins_quote_is_visibilite_only"):
            return bool(order._coins_quote_is_visibilite_only())
        if self.coins_interet_channel_manager:
            return False
        return True

    def _coins_ensure_standard_hebergement_entente(self):
        """Crée ou rafraîchit l'entente : visibilité 15 % par défaut, pack hébergement si digitalisation."""
        self.ensure_one()
        if self._coins_lead_is_frozen_djemanna():
            return self.coins_entente_id
        if not self._coins_is_hebergement_standard():
            raise UserError(
                _("Le modèle standard d'entente ne s'applique qu'à la catégorie Hébergement.")
            )
        if not (self.coins_etablissement or self.partner_name or self.name):
            raise UserError(_("Indiquez l'établissement avant de créer l'entente."))
        partner = self._coins_ensure_partner()
        Entente = self.env["coins.entente"].sudo()
        entente = self.coins_entente_id
        visibilite = self._coins_lead_wants_visibilite_only()
        vals = {
            "type_partenaire": "hebergement",
            "partenaire_nom": self.contact_name or partner.name,
            "etablissement": (
                self.coins_etablissement or self.partner_name or self.name
            ),
            "contact_partenaire": self._coins_partner_email()
            or self.coins_whatsapp
            or self.phone,
            "partner_id": partner.id,
            "pourcentage_commission": self.coins_commission_pct or 15.0,
            "shooting_souhaite": False if visibilite else bool(self.coins_interet_shooting),
            "statut_entente": "en_attente_signature",
            "type_remuneration": "commission",
        }
        render = (
            Entente._coins_render_visibilite_cm
            if visibilite
            else Entente._coins_render_standard_hebergement
        )
        if entente:
            if entente.date_signature or entente._coins_is_frozen_djemanna():
                return entente
            if entente._coins_clauses_are_visibilite_cm() and visibilite:
                update = {k: v for k, v in vals.items() if k != "statut_entente"}
                if "{{" in (entente.clauses_html or ""):
                    update["clauses_html"] = entente._coins_fill_placeholders(
                        entente.clauses_html, vals
                    )
                entente.write(update)
                order = self.coins_sale_order_id
                if order and not order.coins_entente_id:
                    order.sudo().write({"coins_entente_id": entente.id})
                return entente
            update = {k: v for k, v in vals.items() if k != "statut_entente"}
            if visibilite or entente._coins_should_refresh_standard_clauses() or not entente.clauses_html:
                update["clauses_html"] = render(vals)
            elif "{{" in (entente.clauses_html or ""):
                update["clauses_html"] = entente._coins_fill_placeholders(
                    entente.clauses_html, vals
                )
            entente.write(update)
        else:
            vals["clauses_html"] = render(vals)
            entente = Entente.create(vals)
            self.coins_entente_id = entente.id
        order = self.coins_sale_order_id
        if order and not order.coins_entente_id:
            order.sudo().write({"coins_entente_id": entente.id})
        return entente

    def action_coins_creer_entente(self):
        self.ensure_one()
        if (
            self._coins_is_hebergement_standard()
            and not self._coins_lead_is_frozen_djemanna()
            and not self._coins_is_quebec_market()
        ):
            self._coins_ensure_standard_hebergement_entente()
        return super().action_coins_creer_entente()

    def action_envoyer_pour_signature(self):
        """Bouton distinct : token OTP + email Karine (pas la prospection / suivi)."""
        self.ensure_one()
        if not self.coins_is_partner_lead:
            raise UserError(_("Cette action est réservée au pipeline Coins Marocain."))
        if not self._coins_is_hebergement_standard():
            raise UserError(
                _("Le modèle standard d'entente ne s'applique qu'à la catégorie Hébergement.")
            )
        if self._coins_lead_is_frozen_djemanna():
            raise UserError(
                _("Riad Djemanna (S00021) reste sur son entente d'origine — ne pas renvoyer.")
            )
        email = self._coins_partner_email()
        if not email:
            raise UserError(_("Ajoutez l'email du contact sur la fiche avant d'envoyer."))
        entente = self._coins_ensure_standard_hebergement_entente()
        return entente._coins_envoyer_signature_karine()

    def _cm_intro_offer_blocks(self):
        blocks = super()._cm_intro_offer_blocks()
        if not self._coins_is_hebergement_standard():
            return blocks
        visib = (
            "Présence sur la carte Coins Marocain. "
            "Commission de <strong>15&nbsp;%</strong> sur une réservation directe "
            "via Coins Marocain, ou <strong>10&nbsp;%</strong> sur une réservation "
            "via un canal connecté (Booking/Airbnb), en plus de la commission "
            "plateforme — jamais les deux sur la même réservation. "
            "Engagement d'un an, indépendant de Channex."
        )
        digital = (
            "Channel Manager Channex, connecté à plus de 200 plateformes "
            "(Booking, Airbnb, Expedia et autres). "
            "Engagement d'un an, indépendant de la visibilité Coins Marocain. "
            "Les conditions tarifaires figurent au devis le cas échéant."
        )
        blocks["visibility"] = self._cm_intro_pillar_html(
            "Visibilité Coins Marocain", visib
        )
        blocks["digital"] = self._cm_intro_pillar_html(
            "Channel Manager / digitalisation", digital
        )
        return blocks
