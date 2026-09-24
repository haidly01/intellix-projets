# -*- coding: utf-8 -*-
import importlib.util
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1] / "models"


def _load(name, filename, package="reno_immobilier.models"):
    spec = importlib.util.spec_from_file_location(
        "%s.%s" % (package, name),
        ROOT / filename,
        submodule_search_locations=[str(ROOT)],
    )
    mod = importlib.util.module_from_spec(spec)
    import sys

    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


_region = _load("region_map", "region_map.py")
_labels = _load("service_label_map", "service_label_map.py")
# partner_match imports relative — load as package child
import sys

sys.modules["reno_immobilier"] = type(sys)("reno_immobilier")
sys.modules["reno_immobilier.models"] = type(sys)("reno_immobilier.models")
sys.modules["reno_immobilier.models.region_map"] = _region
sys.modules["reno_immobilier.models.service_label_map"] = _labels
pm = _load("partner_match", "partner_match.py")


class PartnerMatchTest(unittest.TestCase):
    def test_longueuil_covered_by_rive_sud(self):
        self.assertTrue(
            pm.partner_covers_city("Longueuil", "Hemmingford", "rive sud et estrie", "radius")
        )
        self.assertTrue(
            pm.partner_covers_city(
                "Longueuil",
                "Sainte-Anne-de-Sabrevois",
                "st jean et rive sud",
                "radius",
            )
        )
        self.assertTrue(
            pm.partner_covers_city(
                "Longueuil",
                "Sherbrooke",
                "Longueuil Brossard Saint-Hubert",
                "city",
            )
        )

    def test_toiture_matches_exterieur(self):
        self.assertTrue(pm.services_overlap(["Toiture"], ["Renovation exterieure"]))
        self.assertTrue(pm.services_overlap(["Toiture"], ["rénovation extérieure"]))
        self.assertFalse(pm.services_overlap(["Toiture"], ["Thermopompe"]))

    def test_infer_toiture_from_source(self):
        names = pm.infer_category_names(
            source_label="Soumission Toiture",
            description="Type de toit: pente | Service: Diagnostic de toiture",
            lead_name="Site web — Steeve Côté",
        )
        self.assertIn("Toiture", names)
        self.assertNotIn("Paysagement", names)


if __name__ == "__main__":
    unittest.main()
