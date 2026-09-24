# -*- coding: utf-8 -*-
from odoo import api, fields, models


class CoinsOverview(models.Model):
    _inherit = "coins.overview"

    @api.model
    def get_dashboard_data(self):
        data = super().get_dashboard_data()
        data["pipeline_voyageurs"] = self._coins_pipeline_voyageurs_stats()
        data["pipeline_partenariats"] = self._coins_pipeline_partenariats_stats()
        return data

    def _coins_pipeline_voyageurs_stats(self):
        Lead = self.env["crm.lead"].sudo()
        team = self.env.ref(
            "coins_marocain_partenariats.crm_team_coins_voyageurs",
            raise_if_not_found=False,
        )
        domain = [("coins_fiche_type", "=", "voyageur")]
        if team:
            domain = ["|", ("team_id", "=", team.id), ("coins_fiche_type", "=", "voyageur")]
        leads = Lead.search(domain)
        month_start = fields.Date.context_today(self).replace(day=1)

        def in_month(val):
            if not val:
                return False
            return fields.Date.to_date(val) >= month_start

        nouveaux = leads.filtered(lambda l: (l.stage_id.name or "") == "Nouveau")
        chauds = leads.filtered(
            lambda l: l.coins_urgence or (l.stage_id.name or "") == "Transfert à chaud"
        )
        reserves = leads.filtered(
            lambda l: l.stage_id.is_won and in_month(l.date_closed or l.write_date)
        )
        sans = leads.filtered(lambda l: not l.coins_has_coordonnees)
        return {
            "nouveaux": len(nouveaux),
            "chauds": len(chauds),
            "reserves": len(reserves),
            "sans_coordonnees": len(sans),
        }

    def _coins_pipeline_partenariats_stats(self):
        Lead = self.env["crm.lead"].sudo()
        team = self.env.ref(
            "coins_marocain_partenariats.crm_team_coins_marocain",
            raise_if_not_found=False,
        )
        domain = [("coins_fiche_type", "!=", "voyageur")]
        if team:
            domain = [
                ("team_id", "=", team.id),
                ("coins_fiche_type", "!=", "voyageur"),
            ]
        leads = Lead.search(domain)
        prospect_names = {"Prospection", "Nouveau", "Contacté"}
        nego_names = {
            "Négociation",
            "Attribué",
            "Relance",
        }
        prospection = leads.filtered(lambda l: (l.stage_id.name or "") in prospect_names)
        nego = leads.filtered(lambda l: (l.stage_id.name or "") in nego_names)
        actifs = leads.filtered(lambda l: l.stage_id.is_won)
        margin = 0.0
        Entente = self.env["coins.entente"].sudo()
        if "commission_calculee" in Entente._fields:
            margin = sum(
                Entente.search([("statut_entente", "=", "active")]).mapped(
                    "commission_calculee"
                )
            )
        return {
            "prospection": len(prospection),
            "negociation": len(nego),
            "actifs": len(actifs),
            "marge": margin,
        }
