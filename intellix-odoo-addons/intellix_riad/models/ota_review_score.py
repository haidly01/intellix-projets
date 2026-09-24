# -*- coding: utf-8 -*-
"""Snapshots d'avis OTA — catégories réelles Booking / Airbnb uniquement."""

from odoo import fields, models


# Catégories officielles — ne pas fusionner ni inventer.
BOOKING_CATEGORIES = [
    ("personnel", "Personnel"),
    ("proprete", "Propreté"),
    ("emplacement", "Emplacement"),
    ("confort", "Confort"),
    ("equipements", "Équipements"),
    ("rapport_qualite_prix", "Rapport qualité-prix"),
    ("wifi", "Wifi gratuit"),
]

AIRBNB_CATEGORIES = [
    ("proprete", "Propreté"),
    ("exactitude", "Exactitude"),
    ("checkin", "Check-in"),
    ("communication", "Communication"),
    ("emplacement", "Emplacement"),
    ("valeur", "Valeur"),
]


class IntellixRiadOtaReviewSnapshot(models.Model):
    _name = "intellix.riad.ota.review.snapshot"
    _description = "Snapshot avis OTA (catégories plateforme)"
    _order = "captured_at desc, id desc"

    establishment_id = fields.Many2one(
        "intellix.riad.establishment",
        required=True,
        ondelete="cascade",
        index=True,
    )
    platform = fields.Selection(
        [
            ("booking", "Booking.com"),
            ("airbnb", "Airbnb"),
        ],
        required=True,
        index=True,
    )
    captured_at = fields.Datetime(
        string="Date du snapshot",
        default=fields.Datetime.now,
        required=True,
    )
    # Booking : sous-scores /10. Airbnb : catégories /5.
    score_personnel = fields.Float()
    score_proprete = fields.Float()
    score_emplacement = fields.Float()
    score_confort = fields.Float()
    score_equipements = fields.Float()
    score_rapport_qualite_prix = fields.Float()
    score_wifi = fields.Float()
    score_exactitude = fields.Float()
    score_checkin = fields.Float()
    score_communication = fields.Float()
    score_valeur = fields.Float()
    # Airbnb : note globale DISTINCTE — saisie séparée, jamais une moyenne des 6.
    airbnb_overall = fields.Float(
        string="Note globale Airbnb",
        help="Note distincte donnée par le voyageur — pas une moyenne des 6 catégories.",
    )
    booking_overall = fields.Float(
        string="Note globale Booking",
        help="Score global Booking affiché sur la fiche (souvent /10).",
    )
    source_note = fields.Char(
        string="Source",
        help="ex. saisie manuelle extranet, import CSV, API future",
    )

    def category_rows(self):
        """Liste affichable fidèle à la plateforme — pas de fusion."""
        self.ensure_one()
        if self.platform == "booking":
            mapping = [
                ("personnel", self.score_personnel, 10),
                ("proprete", self.score_proprete, 10),
                ("emplacement", self.score_emplacement, 10),
                ("confort", self.score_confort, 10),
                ("equipements", self.score_equipements, 10),
                ("rapport_qualite_prix", self.score_rapport_qualite_prix, 10),
                ("wifi", self.score_wifi, 10),
            ]
            labels = dict(BOOKING_CATEGORIES)
            rows = [
                {
                    "code": code,
                    "label": labels[code],
                    "score": score or None,
                    "scale": scale,
                    "display": ("%.1f / %s" % (score, scale)) if score else "—",
                }
                for code, score, scale in mapping
            ]
            return {
                "platform": "booking",
                "platform_label": "Booking.com",
                "overall": self.booking_overall or None,
                "overall_label": "Note globale Booking",
                "overall_note": "Score global fiche (souvent /10).",
                "categories": rows,
                "captured_at": self.captured_at,
            }
        mapping = [
            ("proprete", self.score_proprete, 5),
            ("exactitude", self.score_exactitude, 5),
            ("checkin", self.score_checkin, 5),
            ("communication", self.score_communication, 5),
            ("emplacement", self.score_emplacement, 5),
            ("valeur", self.score_valeur, 5),
        ]
        labels = dict(AIRBNB_CATEGORIES)
        rows = [
            {
                "code": code,
                "label": labels[code],
                "score": score or None,
                "scale": scale,
                "display": ("%.2f / %s" % (score, scale)) if score else "—",
                "weight_hint": (
                    "Pondération plus forte sur la note globale Airbnb"
                    if code in ("exactitude", "proprete", "valeur")
                    else "Pondération plus légère"
                ),
            }
            for code, score, scale in mapping
        ]
        return {
            "platform": "airbnb",
            "platform_label": "Airbnb",
            "overall": self.airbnb_overall or None,
            "overall_label": "Note globale Airbnb (distincte)",
            "overall_note": (
                "Ce n’est PAS une moyenne des 6 catégories — note séparée du voyageur."
            ),
            "categories": rows,
            "captured_at": self.captured_at,
        }
