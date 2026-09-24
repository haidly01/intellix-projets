# -*- coding: utf-8 -*-
"""Helpers portail propriétaire — Performance, Réservations, Facturation."""

from odoo import _, fields, models


class IntellixRiadEstablishmentPortalDash(models.Model):
    _inherit = "intellix.riad.establishment"

    coins_commission_direct_pct = fields.Float(
        string="Commission Coins — direct (%)",
        default=15.0,
        help="Ex. 15 % réservations directes via Coins Marocain.",
    )
    coins_commission_ota_pct = fields.Float(
        string="Commission Coins — OTA (%)",
        default=10.0,
        help="Ex. 10 % réservations canaux connectés.",
    )
    coins_monthly_fee = fields.Monetary(
        string="Forfait mensuel Coins (MAD)",
        currency_field="tourist_tax_currency_id",
        help="Ex. 750 MAD HT pour Djemanna — 0 si modèle % uniquement.",
    )
    ota_review_snapshot_ids = fields.One2many(
        "intellix.riad.ota.review.snapshot",
        "establishment_id",
        string="Snapshots avis OTA",
    )

    # ------------------------------------------------------------------
    # Performance
    # ------------------------------------------------------------------
    def portal_performance_payload(self):
        self.ensure_one()
        Thread = self.env["intellix.riad.experience.thread"].sudo()
        avg_sec = Thread.average_response_seconds(self, days=30)
        if avg_sec is None:
            response_block = {
                "available": False,
                "label": _("Temps de réponse moyen (30 j)"),
                "value": None,
                "display": _("Pas encore de données"),
                "context": _(
                    "Ce délai compte pour le ranking Airbnb (Superhost) et Booking.com "
                    "(taux / vitesse de réponse dans l’algorithme de visibilité)."
                ),
            }
        else:
            minutes = avg_sec / 60.0
            response_block = {
                "available": True,
                "label": _("Temps de réponse moyen (30 j)"),
                "value": avg_sec,
                "display": (
                    _("%(m).0f min") % {"m": minutes}
                    if minutes >= 1
                    else _("%(s)s s") % {"s": avg_sec}
                ),
                "context": _(
                    "Ce délai compte pour le ranking Airbnb (Superhost) et Booking.com "
                    "(taux / vitesse de réponse dans l’algorithme de visibilité)."
                ),
            }

        reviews = []
        Snap = self.env["intellix.riad.ota.review.snapshot"].sudo()
        # Afficher une section par OTA « concernée » (connectée ou avec snapshot).
        platforms = []
        try:
            has_booking_snap = bool(
                Snap.search_count(
                    [("establishment_id", "=", self.id), ("platform", "=", "booking")]
                )
            )
            has_airbnb_snap = bool(
                Snap.search_count(
                    [("establishment_id", "=", self.id), ("platform", "=", "airbnb")]
                )
            )
        except Exception:  # noqa: BLE001
            has_booking_snap = has_airbnb_snap = False
        if (self.ota_booking_status or "") == "connected" or has_booking_snap:
            platforms.append("booking")
        if (self.ota_airbnb_status or "") == "connected" or has_airbnb_snap:
            platforms.append("airbnb")
        # Toujours montrer les deux structures officielles (état vide honnête).
        if not platforms:
            platforms = ["booking", "airbnb"]

        for plat in platforms:
            snap = Snap.search(
                [("establishment_id", "=", self.id), ("platform", "=", plat)],
                order="captured_at desc, id desc",
                limit=1,
            )
            if snap:
                reviews.append(snap.category_rows())
            else:
                if plat == "booking":
                    reviews.append(
                        {
                            "platform": "booking",
                            "platform_label": "Booking.com",
                            "overall": None,
                            "overall_label": "Note globale Booking",
                            "overall_note": "Score global fiche (souvent /10).",
                            "categories": [
                                {
                                    "code": c,
                                    "label": lab,
                                    "score": None,
                                    "scale": 10,
                                    "display": "—",
                                }
                                for c, lab in [
                                    ("personnel", "Personnel"),
                                    ("proprete", "Propreté"),
                                    ("emplacement", "Emplacement"),
                                    ("confort", "Confort"),
                                    ("equipements", "Équipements"),
                                    ("rapport_qualite_prix", "Rapport qualité-prix"),
                                    ("wifi", "Wifi gratuit"),
                                ]
                            ],
                            "empty": True,
                            "empty_note": _(
                                "Aucun snapshot encore — structure officielle Booking "
                                "(7 sous-scores /10). Saisie manuelle ou sync future."
                            ),
                        }
                    )
                else:
                    reviews.append(
                        {
                            "platform": "airbnb",
                            "platform_label": "Airbnb",
                            "overall": None,
                            "overall_label": "Note globale Airbnb (distincte)",
                            "overall_note": _(
                                "Ce n’est PAS une moyenne des 6 catégories."
                            ),
                            "categories": [
                                {
                                    "code": c,
                                    "label": lab,
                                    "score": None,
                                    "scale": 5,
                                    "display": "—",
                                    "weight_hint": (
                                        "Pondération plus forte"
                                        if c in ("exactitude", "proprete", "valeur")
                                        else "Pondération plus légère"
                                    ),
                                }
                                for c, lab in [
                                    ("proprete", "Propreté"),
                                    ("exactitude", "Exactitude"),
                                    ("checkin", "Check-in"),
                                    ("communication", "Communication"),
                                    ("emplacement", "Emplacement"),
                                    ("valeur", "Valeur"),
                                ]
                            ],
                            "empty": True,
                            "empty_note": _(
                                "Aucun snapshot encore — 6 catégories /5 + note globale "
                                "distincte. Pas de moyenne inventée."
                            ),
                        }
                    )

        ranking = []
        if "booking" in platforms or True:
            ranking.append(
                {
                    "platform": "Booking.com",
                    "factors": [
                        _("Score avis (global + sous-scores)"),
                        _("Taux / vitesse de réponse aux messages"),
                        _("Complétude de fiche (photos, description)"),
                    ],
                    "note": _(
                        "Facteurs bruts — pas de score composite inventé par Coins."
                    ),
                }
            )
        if "airbnb" in platforms or True:
            ranking.append(
                {
                    "platform": "Airbnb",
                    "factors": [
                        _(
                            "Les 6 catégories (exactitude / propreté / valeur pèsent "
                            "plus lourd que check-in / communication / emplacement "
                            "sur la note globale Airbnb)"
                        ),
                        _("Taux de réponse"),
                        _("Taux d’annulation hôte"),
                        _('Éligibilité badge « Guest Favorite »'),
                    ],
                    "note": _(
                        "Facteurs bruts — pas de score unique opaque."
                    ),
                }
            )

        return {
            "response": response_block,
            "reviews": reviews,
            "ranking": ranking,
        }

    # ------------------------------------------------------------------
    # Réservations
    # ------------------------------------------------------------------
    def _portal_reservations(self, date_from=None, date_to=None):
        self.ensure_one()
        if not self.property_id:
            return self.env["coins.reservation"].browse()
        domain = [("property_id", "=", self.property_id.id)]
        if date_from:
            domain.append(("check_out", ">=", date_from))
        if date_to:
            domain.append(("check_in", "<=", date_to))
        return (
            self.env["coins.reservation"]
            .sudo()
            .search(domain, order="check_in desc, id desc", limit=300)
        )

    def portal_reservation_groups(self, date_from=None, date_to=None):
        """Groupes sur les états existants — pas de nouveaux state."""
        self.ensure_one()
        today = fields.Date.context_today(self)
        resas = self._portal_reservations(date_from=date_from, date_to=date_to)

        def _row(r):
            guest = r.client_nom or (r.traveler_id.name if r.traveler_id else "") or "—"
            pay = r.payment_status or "unpaid"
            return {
                "id": r.id,
                "name": r.name or ("#%s" % r.id),
                "guest": guest,
                "check_in": fields.Date.to_string(r.check_in) if r.check_in else False,
                "check_out": fields.Date.to_string(r.check_out) if r.check_out else False,
                "state": r.state,
                "state_label": dict(r._fields["state"].selection).get(r.state) or r.state,
                "source": r.source,
                "source_label": dict(r._fields["source"].selection).get(r.source)
                or r.source
                or "—",
                "amount": r.amount_total or 0.0,
                "payment_status": pay,
                "payment_label": dict(r._fields["payment_status"].selection).get(pay)
                or pay,
                "police_pending": bool(getattr(r, "riad_police_pending", 0)),
                "checkin_url": (
                    "/checkin/%s" % r.riad_checkin_token
                    if getattr(r, "riad_checkin_token", None)
                    else False
                ),
            }

        pending = []
        confirmed = []
        in_stay = []
        done = []
        cancelled = []

        for r in resas:
            row = _row(r)
            if r.state == "draft" or (
                r.state == "confirmed" and getattr(r, "riad_police_pending", 0)
            ):
                pending.append(row)
                continue
            if r.state == "cancelled":
                cancelled.append(row)
            elif r.state == "done":
                done.append(row)
            elif r.state == "in_progress" or (
                r.state == "confirmed"
                and r.check_in
                and r.check_out
                and r.check_in <= today < r.check_out
            ):
                in_stay.append(row)
            elif r.state == "confirmed":
                confirmed.append(row)
            else:
                confirmed.append(row)

        return [
            {
                "key": "pending",
                "label": _("En attente de validation"),
                "hint": _(
                    "Brouillons ou confirmées avec fiches de police étrangères "
                    "incomplètes — même logique module hébergement."
                ),
                "rows": pending,
                "count": len(pending),
                "actions": True,
            },
            {
                "key": "confirmed",
                "label": _("Confirmées (à venir)"),
                "hint": "",
                "rows": confirmed,
                "count": len(confirmed),
                "actions": False,
            },
            {
                "key": "in_stay",
                "label": _("En cours de séjour"),
                "hint": "",
                "rows": in_stay,
                "count": len(in_stay),
                "actions": False,
            },
            {
                "key": "done",
                "label": _("Terminées"),
                "hint": "",
                "rows": done,
                "count": len(done),
                "actions": False,
            },
            {
                "key": "cancelled",
                "label": _("Annulées"),
                "hint": "",
                "rows": cancelled,
                "count": len(cancelled),
                "actions": False,
            },
        ]

    def portal_payment_tabs(self, date_from=None, date_to=None):
        """Onglets paiement (statuts existants unpaid/partial/paid)."""
        self.ensure_one()
        resas = self._portal_reservations(date_from=date_from, date_to=date_to).filtered(
            lambda r: r.state != "cancelled"
        )
        buckets = {
            "unpaid": {"key": "unpaid", "label": _("Non payées"), "rows": [], "count": 0},
            "partial": {"key": "partial", "label": _("Partiellement payées"), "rows": [], "count": 0},
            "paid": {"key": "paid", "label": _("Payées"), "rows": [], "count": 0},
        }
        for r in resas:
            pay = r.payment_status or "unpaid"
            if pay not in buckets:
                pay = "unpaid"
            guest = r.client_nom or (r.traveler_id.name if r.traveler_id else "") or "—"
            buckets[pay]["rows"].append(
                {
                    "id": r.id,
                    "name": r.name or ("#%s" % r.id),
                    "guest": guest,
                    "check_in": fields.Date.to_string(r.check_in) if r.check_in else False,
                    "check_out": fields.Date.to_string(r.check_out) if r.check_out else False,
                    "amount": r.amount_total or 0.0,
                    "payment_status": pay,
                    "payment_label": dict(r._fields["payment_status"].selection).get(pay),
                    "state_label": dict(r._fields["state"].selection).get(r.state) or r.state,
                    "source_label": dict(r._fields["source"].selection).get(r.source)
                    or r.source
                    or "—",
                }
            )
        for b in buckets.values():
            b["count"] = len(b["rows"])
        return [buckets["unpaid"], buckets["partial"], buckets["paid"]]

    def portal_reservation_nudge(self, reservation_id, kind="relance"):
        """Relance / message voyageur — crée un tour agent (canal whatsapp) isolé."""
        self.ensure_one()
        Resa = self.env["coins.reservation"].sudo().browse(int(reservation_id))
        if not Resa.exists() or Resa.property_id.id != self.property_id.id:
            raise PermissionError("reservation/property mismatch")
        guest = Resa.client_nom or (Resa.traveler_id.name if Resa.traveler_id else "")
        text = (
            _("Relance propriétaire : merci de compléter votre check-in / fiches.")
            if kind == "relance"
            else _("Message propriétaire concernant votre séjour.")
        )
        self.env["intellix.riad.experience.thread"].sudo().create(
            {
                "establishment_id": self.id,
                "channel": "whatsapp",
                "reservation_id": Resa.id,
                "guest_name": guest or "Voyageur",
                "inbound_text": text,
                "intent": "escalate_human",
                "decision": "escalate",
                "state": "open",
            }
        )
        Resa.message_post(
            body=_("Relance portail propriétaire (%s) — suivi Messages.") % kind
        )
        return True

    # ------------------------------------------------------------------
    # Facturation
    # ------------------------------------------------------------------
    def portal_billing_payload(self):
        self.ensure_one()
        resas = self._portal_reservations().filtered(
            lambda r: r.state in ("confirmed", "in_progress", "done")
        )
        ota_sources = ("booking", "airbnb", "expedia", "channex")
        by_ota = {
            "booking": {"label": "Booking.com", "expected": 0.0, "received": 0.0, "n": 0},
            "airbnb": {"label": "Airbnb", "expected": 0.0, "received": 0.0, "n": 0},
            "expedia": {"label": "Expedia", "expected": 0.0, "received": 0.0, "n": 0},
            "agoda": {"label": "Agoda", "expected": 0.0, "received": 0.0, "n": 0},
        }
        direct = {"label": _("Direct Coins Marocain"), "expected": 0.0, "received": 0.0, "n": 0}
        gaps = []

        for r in resas:
            amount = r.amount_total or 0.0
            received = amount if r.payment_status == "paid" else (
                amount * 0.5 if r.payment_status == "partial" else 0.0
            )
            src = r.source or "direct"
            if src in ("booking", "airbnb", "expedia"):
                bucket = by_ota[src]
            elif src == "channex":
                # Canal OTA générique — ventilé sous Booking faute de détail
                bucket = by_ota["booking"]
            elif src in ("direct", "referral", "ads", "viator") or not src:
                bucket = direct
            else:
                bucket = direct
            bucket["expected"] += amount
            bucket["received"] += received
            bucket["n"] += 1
            if abs(amount - received) > 0.01:
                gaps.append(
                    {
                        "resa": r.name or ("#%s" % r.id),
                        "source": src,
                        "expected": amount,
                        "received": received,
                        "gap": amount - received,
                        "payment_status": r.payment_status,
                    }
                )

        # Agoda : pas de source dans le modèle actuel — état vide honnête
        ota_rows = list(by_ota.values())
        ota_rows[-1]["empty_note"] = _(
            "Aucune réservation Agoda dans le modèle actuel (source absente) — "
            "ligne prête dès que des résas Agoda arriveront."
        )

        direct_pct = self.coins_commission_direct_pct or 15.0
        ota_pct = self.coins_commission_ota_pct or 10.0
        monthly = self.coins_monthly_fee or 0.0
        coins_share_direct = direct["expected"] * direct_pct / 100.0
        coins_share_ota = sum(
            b["expected"] * ota_pct / 100.0
            for k, b in by_ota.items()
            if k != "agoda"
        )
        return {
            "ota_rows": ota_rows,
            "direct": direct,
            "gaps": gaps[:50],
            "commission": {
                "direct_pct": direct_pct,
                "ota_pct": ota_pct,
                "monthly_fee": monthly,
                "coins_from_direct": coins_share_direct,
                "coins_from_ota": coins_share_ota,
                "coins_total_est": coins_share_direct + coins_share_ota + monthly,
                "note": _(
                    "Estimation sur montant réservation × taux commercial du lieu "
                    "(pas encore un bordereau comptable définitif)."
                ),
            },
            "currency": "MAD",
        }
