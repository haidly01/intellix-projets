# -*- coding: utf-8 -*-
import sys
import unittest
from pathlib import Path

try:
    from odoo.addons.coins_quebec.data.clauses_visibilite_quebec import (
        cq_visibilite_clauses_html,
    )
except ImportError:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from data.clauses_visibilite_quebec import cq_visibilite_clauses_html


class EntenteClausesTest(unittest.TestCase):
    def test_quebec_markers_resto(self):
        html = cq_visibilite_clauses_html("Restaurant / Gourmand", 10)
        self.assertIn("Agence Doorway", html)
        self.assertIn("Coins Québec", html)
        self.assertIn("10", html)
        self.assertNotIn("Channel Manager", html)
        self.assertNotIn("Booking.com", html)
