# -*- coding: utf-8 -*-
"""Dashboard global Coins Marocain — agrégats multi-modules.

Contrat de données restauré depuis la décompilation du .pyc d'origine
(_coins_rebuild/recover_full/models/coins_overview.py). Le front OWL d'origine
a été perdu lors de la recovery du 31/07/2026 ; le template/JS consomme ce
même contrat.
"""
from datetime import timedelta

from odoo import api, fields, models


class CoinsOverview(models.Model):
    _name = "coins.overview"
    _description = "Tableau de bord global Coins Marocain"
    _auto = False

    @api.model
    def get_dashboard_data(self):
        today = fields.Date.context_today(self)
        month_start = today.replace(day=1)
        week_start = today - timedelta(days=today.weekday())
        currency = self.env.company.currency_id

        Property = self.env["coins.property"].sudo()
        Reservation = self.env["coins.reservation"].sudo()
        Driver = self.env["coins.driver"].sudo()
        DetenteBooking = self.env["coins.detente_booking"].sudo()
        DetentePartner = self.env["coins.detente_partner"].sudo()
        Activite = self.env["coins.activite"].sudo()
        ActiviteBooking = self.env["coins.activite_booking"].sudo()

        props_active = Property.search_count([("state", "=", "active")])
        props_pool = Property.search_count(
            [("property_type", "=", "pool_hammam"), ("state", "=", "active")]
        )
        res_month = Reservation.search_count(
            [
                ("state", "in", ("confirmed", "in_progress", "done")),
                ("check_in", ">=", month_start),
            ]
        )
        res_confirmed = Reservation.search_count([("state", "=", "confirmed")])
        drivers_active = Driver.search_count([("state", "=", "active")])

        detente_domain_month = [
            ("status", "in", ("confirme", "realise", "depot_recu", "prospect")),
            "|",
            ("service_date", ">=", month_start),
            "&",
            ("service_date", "=", False),
            ("booking_date", ">=", month_start),
        ]
        detente_month = DetenteBooking.read_group(
            detente_domain_month, ["total_margin:sum"], []
        )
        detente_margin_month = float(
            (detente_month[0].get("total_margin") if detente_month else 0) or 0
        )
        detente_confirmed = DetenteBooking.search_count([("status", "=", "confirme")])
        detente_realized = DetenteBooking.search_count([("status", "=", "realise")])
        partners_prio = DetentePartner.search_count([("verdict", "=", "prioritaire")])

        act_catalog = Activite.search_count([("active", "=", True)])
        act_privatif = Activite.search_count(
            [
                ("active", "=", True),
                ("activity_type", "in", ("privatif_operee", "privatif_partenaire")),
            ]
        )
        act_viator = Activite.search_count(
            [("active", "=", True), ("activity_type", "=", "viator_reference")]
        )
        act_bookings_month = ActiviteBooking.search_count(
            [
                ("status", "in", ("confirme", "realise", "depot_recu", "prospect")),
                "|",
                ("service_date", ">=", month_start),
                "&",
                ("service_date", "=", False),
                ("booking_date", ">=", month_start),
            ]
        )
        act_margin_rows = ActiviteBooking.read_group(
            [
                ("status", "in", ("confirme", "realise")),
                "|",
                ("service_date", ">=", month_start),
                "&",
                ("service_date", "=", False),
                ("booking_date", ">=", month_start),
            ],
            ["total_margin:sum"],
            [],
        )
        act_margin_month = float(
            (act_margin_rows[0].get("total_margin") if act_margin_rows else 0) or 0
        )

        months_fr = (
            "",
            "janvier",
            "février",
            "mars",
            "avril",
            "mai",
            "juin",
            "juillet",
            "août",
            "septembre",
            "octobre",
            "novembre",
            "décembre",
        )
        month_label = "%s %s" % (months_fr[month_start.month], month_start.year)

        return {
            "currency_symbol": currency.symbol or "MAD",
            "month_label": month_label,
            "week_start": str(week_start),
            "biens": {
                "active": props_active,
                "pool_hammam": props_pool,
                "reservations_month": res_month,
                "reservations_confirmed": res_confirmed,
            },
            "chauffeurs": {"active": drivers_active},
            "detente": {
                "margin_month": detente_margin_month,
                "confirmed": detente_confirmed,
                "realized": detente_realized,
                "partners_prioritaire": partners_prio,
            },
            "activites": {
                "catalog": act_catalog,
                "privatif": act_privatif,
                "viator_ref": act_viator,
                "bookings_month": act_bookings_month,
                "margin_month": act_margin_month,
            },
            "total_margin_month": detente_margin_month + act_margin_month,
        }
