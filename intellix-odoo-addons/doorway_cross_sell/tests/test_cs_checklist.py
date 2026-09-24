# -*- coding: utf-8 -*-
import importlib.util
import unittest
from pathlib import Path

_SPEC = importlib.util.spec_from_file_location(
    "cs_checklist",
    Path(__file__).resolve().parents[1] / "models" / "cs_checklist.py",
)
cs = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(cs)


class InferOriginVerticalTest(unittest.TestCase):
    def test_meta_is_immobilier(self):
        self.assertEqual(cs.infer_origin_vertical(name="Site", is_meta=True), "immobilier")

    def test_source_toiture(self):
        self.assertEqual(
            cs.infer_origin_vertical(source_label="Soumission Toiture"),
            "toiture",
        )

    def test_source_thermopompe(self):
        self.assertEqual(
            cs.infer_origin_vertical(source_label="ICI Thermopompe"),
            "thermopompe",
        )

    def test_source_isolation(self):
        self.assertEqual(
            cs.infer_origin_vertical(source_label="Isolation QC"),
            "isolation",
        )

    def test_source_reno_generale(self):
        self.assertEqual(
            cs.infer_origin_vertical(source_label="Soumission Entrepreneurs"),
            "renovation_generale",
        )

    def test_facebook_immobilier_name(self):
        self.assertEqual(
            cs.infer_origin_vertical(name="Facebook Immobilier — Gaétane Fortin"),
            "immobilier",
        )

    def test_source_cuisine_not_immobilier(self):
        self.assertEqual(
            cs.infer_origin_vertical(
                name="Site web — Caroline Gendron",
                source_label="Cuisine",
                description="Site source: reseaucuisineqc.com",
            ),
            "cuisine",
        )

    def test_cuisine_source_wins_over_meta_flag(self):
        self.assertEqual(
            cs.infer_origin_vertical(
                source_label="Cuisine",
                is_meta=True,
            ),
            "cuisine",
        )

    def test_toiture_source_not_immobilier_copy(self):
        self.assertEqual(
            cs.infer_origin_vertical(source_label="Soumission Toiture"),
            "toiture",
        )
        self.assertNotIn(
            "travaux avant la vente",
            cs.checklist_copy("toiture")["q1"],
        )


class ChecklistCatalogTest(unittest.TestCase):
    def test_immobilier_unchanged_keys(self):
        items = cs.checklist_items("immobilier")
        self.assertEqual(
            [item["key"] for item in items],
            ["travaux_vente", "rachat_reno", "autre_propriete"],
        )
        self.assertTrue(all(item["target"] == "renovation_generale" for item in items))

    def test_toiture_targets(self):
        targets = [item["target"] for item in cs.checklist_items("toiture")]
        self.assertEqual(targets, ["immobilier", "portes_fenetres", "renovation_generale"])

    def test_reno_q3_is_courtier(self):
        q3 = cs.checklist_items("renovation_generale")[2]
        self.assertEqual(q3["target"], "courtier_hypothecaire")

    def test_reno_q2_variable_target(self):
        q2 = cs.checklist_items("renovation_generale")[1]
        self.assertIsNone(q2["target"])
        self.assertEqual(q2["target_field"], "cs_q_target_vertical")
        self.assertEqual(cs.resolve_item_target(q2, "toiture"), "toiture")
        self.assertFalse(cs.resolve_item_target(q2, None))

    def test_only_one_block_per_origin(self):
        for origin in (
            "toiture",
            "thermopompe",
            "isolation",
            "portes_fenetres",
            "renovation_generale",
            "immobilier",
            "cuisine",
        ):
            self.assertEqual(len(cs.checklist_items(origin)), 3)
            copy = cs.checklist_copy(origin)
            self.assertTrue(copy["q1"])
            self.assertTrue(copy["badge"])


if __name__ == "__main__":
    unittest.main()
