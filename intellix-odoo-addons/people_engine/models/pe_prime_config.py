# -*- coding: utf-8 -*-
from odoo import fields, models


class PePrimeConfig(models.Model):
    _name = "pe.prime.config"
    _description = "Configuration prime variable"
    _order = "type_prime, sequence, id"

    department_id = fields.Many2one(
        "pe.department", required=True, ondelete="cascade", index=True
    )
    sequence = fields.Integer(default=10)
    name = fields.Char(string="Nom de la prime", required=True)
    actif = fields.Boolean(default=True)
    type_prime = fields.Selection(
        [
            ("plateau_leads", "Plateau leads qualifiés (par bloc)"),
            ("upsell_lead", "Upsell lead supplémentaire"),
            ("conversion_ia", "Prime taux conversion leads IA"),
            ("rendement_mensuel", "Prime rendement mensuel global"),
            ("presence", "Prime présence / ponctualité"),
            ("coaching_valide", "Prime coaching validé"),
            ("plateau_demos", "Plateau démos bookées"),
            ("vente_unitaire", "Prime vente conclue"),
        ],
        required=True,
    )
    montant_par_unite = fields.Float(
        string="Montant par unité",
        help="Ex: 500 MAD par bloc de 10 leads, ou 5 EUR par lead upsell.",
    )
    devise = fields.Selection(
        [
            ("MAD", "MAD — Dirham"),
            ("EUR", "EUR — Euro"),
            ("CAD", "CAD — Dollar canadien"),
        ],
        default="MAD",
    )
    taille_bloc = fields.Integer(
        string="Taille d'un bloc",
        default=10,
    )
    seuil_declenchement = fields.Float(
        string="Seuil de déclenchement (%)",
        help="Ex: 70 → prime conversion IA uniquement si taux >= 70%.",
    )
    plafond_mois = fields.Float(string="Plafond mensuel (0 = illimité)")
    appliquer_chute = fields.Boolean(string="Appliquer tolérance chute")
    chute_pct_max = fields.Float(string="Chute max tolérée (%)", default=25.0)
    notes = fields.Text()

    def calculer_prime_employe(self, employee_id, periode_debut, periode_fin):
        self.ensure_one()
        dispatch = {
            "plateau_leads": self._calc_plateau,
            "upsell_lead": self._calc_upsell,
            "conversion_ia": self._calc_conversion_ia,
            "plateau_demos": self._calc_plateau_demos,
            "vente_unitaire": self._calc_vente_unitaire,
        }
        fn = dispatch.get(self.type_prime)
        if not fn:
            return {
                "montant": 0.0,
                "devise": self.devise,
                "detail": "Type non calculé",
                "blocs": 0,
            }
        return fn(employee_id, periode_debut, periode_fin)

    def _calc_plateau(self, employee_id, debut, fin):
        leads_confirmes = self.env["crm.lead"].search_count(
            [
                ("user_id.employee_ids", "in", [employee_id]),
                ("stage_id.name", "ilike", "confirm"),
                ("date_closed", ">=", debut),
                ("date_closed", "<=", fin),
            ]
        )
        bloc = self.taille_bloc or 10
        nb_blocs = leads_confirmes // bloc if bloc else 0
        montant = nb_blocs * self.montant_par_unite
        if self.plafond_mois and montant > self.plafond_mois:
            montant = self.plafond_mois
        return {
            "montant": montant,
            "devise": self.devise,
            "detail": "%s leads → %s blocs × %s %s"
            % (leads_confirmes, nb_blocs, self.montant_par_unite, self.devise),
            "blocs": nb_blocs,
            "leads_comptes": leads_confirmes,
        }

    def _calc_upsell(self, employee_id, debut, fin):
        upsells = self.env["pe.prime.upsell.log"].search(
            [
                ("employee_id", "=", employee_id),
                ("date", ">=", debut),
                ("date", "<=", fin),
                ("valide_par_manager", "=", True),
            ]
        )
        nb_upsells = len(upsells)
        montant = nb_upsells * self.montant_par_unite
        return {
            "montant": montant,
            "devise": self.devise,
            "detail": "%s leads upsell × %s %s"
            % (nb_upsells, self.montant_par_unite, self.devise),
            "blocs": 0,
            "upsells": nb_upsells,
        }

    def _calc_conversion_ia(self, employee_id, debut, fin):
        assignments = self.env["pe.agent.assignment"].search(
            [
                ("employee_id", "=", employee_id),
                ("date_attribution", ">=", debut),
                ("date_attribution", "<=", fin),
            ]
        )
        if not assignments:
            return {
                "montant": 0.0,
                "devise": self.devise,
                "detail": "Aucun lead IA attribué",
                "blocs": 0,
            }
        convertis = assignments.filtered(lambda r: r.statut == "converti")
        taux_reel = len(convertis) / len(assignments) * 100
        seuil = self.seuil_declenchement or 70.0
        if taux_reel < seuil:
            return {
                "montant": 0.0,
                "devise": self.devise,
                "detail": "Taux %.1f%% < seuil %.1f%%"
                % (taux_reel, seuil),
                "blocs": 0,
                "taux_reel": taux_reel,
            }
        ratio = taux_reel / 100.0
        montant = self.montant_par_unite * ratio
        return {
            "montant": montant,
            "devise": self.devise,
            "detail": "Taux %.1f%% ≥ %.1f%% → %.2f %s"
            % (taux_reel, seuil, montant, self.devise),
            "blocs": 0,
            "taux_reel": taux_reel,
            "nb_convertis": len(convertis),
            "nb_total": len(assignments),
        }

    def _calc_plateau_demos(self, employee_id, debut, fin):
        demos = self.env["pe.call.log"].search_count(
            [
                ("employee_id", "=", employee_id),
                ("outcome", "=", "demo_bookee"),
                ("date_call", ">=", debut),
                ("date_call", "<=", fin),
            ]
        )
        bloc = self.taille_bloc or 10
        nb_blocs = demos // bloc if bloc else 0
        montant = nb_blocs * self.montant_par_unite
        if self.plafond_mois and montant > self.plafond_mois:
            montant = self.plafond_mois
        return {
            "montant": montant,
            "devise": self.devise,
            "detail": "%s démos → %s paliers" % (demos, nb_blocs),
            "blocs": nb_blocs,
        }

    def _calc_vente_unitaire(self, employee_id, debut, fin):
        ventes = self.env["pe.call.log"].search_count(
            [
                ("employee_id", "=", employee_id),
                ("outcome", "=", "vendu"),
                ("date_call", ">=", debut),
                ("date_call", "<=", fin),
            ]
        )
        montant = ventes * self.montant_par_unite
        return {
            "montant": montant,
            "devise": self.devise,
            "detail": "%s ventes × %s %s" % (ventes, self.montant_par_unite, self.devise),
            "blocs": 0,
        }
