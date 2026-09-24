# -*- coding: utf-8 -*-
from odoo import api, fields, models, _
from odoo.exceptions import UserError


class CoinsDevisEntenteWizard(models.TransientModel):
    _name = "coins.devis.entente.wizard"
    _description = "Choisir le modèle de devis partenaire Coins"

    lead_id = fields.Many2one("crm.lead", string="Fiche partenaire", required=True)
    type_etablissement = fields.Char(
        string="Type d'établissement",
        compute="_compute_type_etablissement",
    )
    marche = fields.Char(
        string="Marché",
        compute="_compute_type_etablissement",
    )
    template_id = fields.Many2one(
        "sale.order.template",
        string="Modèle de devis",
        required=True,
        domain="[('id', 'in', allowed_template_ids)]",
    )
    allowed_template_ids = fields.Many2many(
        "sale.order.template",
        compute="_compute_type_etablissement",
    )
    recommandation = fields.Char(
        string="Suggestion selon la fiche",
        compute="_compute_type_etablissement",
    )

    @api.depends(
        "lead_id",
        "lead_id.team_id",
        "lead_id.coins_type_partenaire",
        "lead_id.coins_categorie_etab",
        "lead_id.coins_interet_channel_manager",
        "lead_id.coins_xsell_site_web",
        "lead_id.coins_xsell_reseaux",
        "lead_id.coins_property_id",
        "lead_id.coins_property_id.property_type",
    )
    def _compute_type_etablissement(self):
        type_labels = {
            "riad": "Riad",
            "villa": "Villa",
            "apartment": "Appartement",
            "hotel": "Hôtel",
            "hebergement": "Hôtel / Riad / Villa",
        }
        Template = self.env["sale.order.template"]
        for wiz in self:
            lead = wiz.lead_id
            quebec = bool(lead and lead._coins_is_quebec_market())
            prop = lead.coins_property_id
            key = (prop.property_type if prop else "") or (
                lead.coins_type_partenaire or lead.coins_categorie_etab or ""
            )
            wiz.type_etablissement = type_labels.get(key, key or "—")
            wiz.marche = (
                "Coins Québec ($ CAD, TPS/TVQ, Interac comptabilite@agencedoorway.com)"
                if quebec
                else "Coins Marocain (DH, virement Attijari)"
            )
            if quebec:
                allowed = Template.search(
                    [("ix_template_code", "like", "coins_quebec_")]
                )
            else:
                allowed = Template.search(
                    [
                        ("ix_template_code", "like", "coins_"),
                        ("ix_template_code", "not like", "coins_quebec_"),
                    ]
                )
            wiz.allowed_template_ids = allowed
            if lead.coins_xsell_site_web or lead.coins_xsell_reseaux:
                wiz.recommandation = (
                    "Présence complète Coins Québec (site / réseaux)"
                    if quebec
                    else "Présence complète (site / réseaux cochés)"
                )
            elif lead.coins_interet_channel_manager:
                wiz.recommandation = (
                    "Digitalisation Coins Québec (channel manager)"
                    if quebec
                    else "Digitalisation (channel manager)"
                )
            elif quebec:
                wiz.recommandation = "Visibilité Coins Québec"
            elif key in type_labels:
                wiz.recommandation = "Visibilité Coins Marocain (hébergement)"
            else:
                wiz.recommandation = "Visibilité Coins Marocain"

    def action_create_quote(self):
        self.ensure_one()
        lead = self.lead_id
        if not lead:
            raise UserError(_("Fiche partenaire introuvable."))
        partner = lead._coins_ensure_partner()
        template = self.template_id
        quebec = bool(lead._coins_is_quebec_market())
        code = (getattr(template, "ix_template_code", "") or "")
        is_cq = code.startswith("coins_quebec")
        if quebec and not is_cq:
            raise UserError(
                _(
                    "Cette fiche Coins Québec n’accepte que les modèles CQ_ "
                    "(coins_quebec_…). Les catalogues CM_ et CQ_ ne se mélangent pas."
                )
            )
        if not quebec and is_cq:
            raise UserError(
                _(
                    "Cette fiche Coins Marocain n’accepte que les modèles CM_ "
                    "(coins_visibilite / digitalisation / présence). "
                    "Les catalogues CM_ et CQ_ ne se mélangent pas."
                )
            )
        entity = "agence_doorway" if quebec else "digital_doorway"
        client_type = "international" if quebec else "local"
        company_needle = "Agence Doorway" if quebec else "Digital Doorway"
        Sale = self.env["sale.order"].with_context(
            default_sale_order_template_id=template.id,
            default_partner_id=partner.id,
            default_ix_client_type=client_type,
            default_ix_entity=entity,
        )
        fields_list = [
            "partner_id",
            "opportunity_id",
            "sale_order_template_id",
            "ix_client_type",
            "ix_entity",
            "ix_tax_mode",
            "ix_template_code",
            "order_line",
            "validity_date",
            "note",
            "company_id",
            "pricelist_id",
            "fiscal_position_id",
        ]
        defaults = Sale.default_get(fields_list)
        defaults.pop("pricelist_id", None)
        defaults.pop("fiscal_position_id", None)
        defaults.update(
            {
                "partner_id": partner.id,
                "sale_order_template_id": template.id,
                "ix_client_type": client_type,
                "ix_entity": entity,
                "origin": lead.coins_etablissement or lead.name,
                "client_order_ref": lead.coins_etablissement or lead.name,
            }
        )
        company = self.env["res.company"].sudo().search(
            [("name", "ilike", company_needle)], limit=1
        )
        if company:
            defaults["company_id"] = company.id
        if not lead.company_id or (company and lead.company_id == company):
            defaults["opportunity_id"] = lead.id
        else:
            defaults.pop("opportunity_id", None)
        if template.number_of_days:
            defaults["validity_date"] = fields.Date.add(
                fields.Date.today(), days=template.number_of_days
            )
        if getattr(template, "ix_template_code", False):
            defaults["ix_template_code"] = template.ix_template_code
        order = Sale.create(defaults)
        if not order.order_line and hasattr(order, "_onchange_sale_order_template_id"):
            order._onchange_sale_order_template_id()
        if hasattr(order, "_coins_apply_template_currency"):
            order._coins_apply_template_currency()
        # Ne pas appeler _apply_ix_entity : ça change la société et casse opportunity_id.
        if hasattr(order, "_ix_pricelist_for_entity"):
            pricelist = order._ix_pricelist_for_entity()
            if pricelist:
                order.pricelist_id = pricelist.id
        if hasattr(order, "_ix_fiscal_position_for_entity"):
            fpos = order._ix_fiscal_position_for_entity()
            if fpos:
                order.fiscal_position_id = fpos.id
        if hasattr(order, "_apply_ix_entity_prices"):
            order._apply_ix_entity_prices()
        if hasattr(order, "_apply_ix_tax_mode"):
            order._apply_ix_tax_mode()
        lead.coins_sale_order_id = order.id
        return {
            "type": "ir.actions.act_window",
            "res_model": "sale.order",
            "res_id": order.id,
            "view_mode": "form",
            "target": "current",
        }
