"""Offline geography and observed-map invariants for the English publication set."""
from __future__ import annotations

from copy import deepcopy
import gzip
from hashlib import sha256
import json
from pathlib import Path
import shutil
import sys
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from americas_markov import geographic, publication_maps as maps


def evaluated_fixture():
    rows = [
        {"country_code": "ARG", "year": 2000, "target_year": 2001,
         "state": "Left", "target_state": "Right", "changed": True, "model": "markov"},
        {"country_code": "ARG", "year": 2001, "target_year": 2002,
         "state": "Right", "target_state": "Right", "changed": False, "model": "markov"},
        {"country_code": "BRA", "year": 2000, "target_year": 2001,
         "state": "Center", "target_state": "Left", "changed": True, "model": "markov"},
    ]
    return pd.DataFrame(rows + [{**row, "model": "persistence"} for row in rows])


class PublicationMapIntegrity(unittest.TestCase):
    def test_offline_geography_retains_all_countries_context_and_atg_units(self):
        with patch.object(geographic, "urlopen") as request:
            doc = geographic.load_americas_geojson(ROOT)
        request.assert_not_called()
        features = doc["features"]
        model = [f for f in features if f["properties"]["IS_MODEL_COUNTRY"]]
        context = [f for f in features if not f["properties"]["IS_MODEL_COUNTRY"]]
        self.assertEqual(len(features), 56)
        self.assertEqual(len(model), 36)
        self.assertEqual(len(context), 20)
        self.assertEqual(len({f["properties"]["MODEL_ISO3"] for f in model}), 35)
        self.assertEqual(sum(f["properties"]["MODEL_ISO3"] == "ATG" for f in model), 2)
        guiana = next(f for f in context if f["properties"]["ISO_A3_EH"] == "GUF")
        self.assertEqual(guiana["properties"]["SOVEREIGNT"], "France")
        self.assertIsNone(guiana["properties"]["MODEL_ISO3"])
        self.assertEqual(len(geographic.load_americas_geojson(ROOT, include_context=False)["features"]), 36)

    def test_lossless_compressed_asset_is_anchored_to_original_subset_sha(self):
        folder = ROOT / "data/cartography"
        manifest = json.loads((folder / "cartography_manifest.json").read_text())
        payload = (folder / geographic.COMPRESSED_NAME).read_bytes()
        self.assertEqual(sha256(payload).hexdigest(), manifest["derived_subset"]["sha256"])
        self.assertEqual(sha256(gzip.decompress(payload)).hexdigest(), geographic.SUBSET_SHA256)
        self.assertEqual(manifest["assets"]["ne_50m_admin_0_map_units.geojson"]["sha256"],
                         "b8d421aca6e9e08e8cdf09cc26af111cc3e0deba4fe915611d58ade71e8a4db0")

    def test_missing_and_corrupt_assets_fail_without_network_fallback(self):
        with TemporaryDirectory() as temporary, patch.object(geographic, "urlopen") as request:
            root = Path(temporary)
            with self.assertRaises(FileNotFoundError):
                geographic.load_americas_geojson(root)
            folder = root / "data/cartography"
            folder.mkdir(parents=True)
            shutil.copyfile(ROOT / "data/cartography/cartography_manifest.json", folder / "cartography_manifest.json")
            (folder / geographic.COMPRESSED_NAME).write_bytes(b"corrupted")
            with self.assertRaisesRegex(RuntimeError, "Compressed cartography SHA256"):
                geographic.load_americas_geojson(root)
            request.assert_not_called()

    def test_country_export_names_are_full_english_national_names(self):
        names = maps.country_names(geographic.load_americas_geojson(ROOT)["features"])
        self.assertEqual(len(names), 35)
        self.assertEqual(names["ATG"], "Antigua and Barbuda")
        self.assertEqual(names["KNA"], "Saint Kitts and Nevis")
        self.assertEqual(names["VCT"], "Saint Vincent and the Grenadines")
        self.assertEqual(names["USA"], "United States of America")

    def test_source_unknown_and_absent_country_coverage_are_not_collapsed(self):
        dpi = pd.DataFrame({"country_code": ["ARG", "PAN", "ARG"], "year": [2023, 2023, 2022],
                            "state": ["Left", np.nan, "Right"], "ideology_raw": ["Left", "0", "Right"]})
        result = maps.state_table(dpi).set_index("country_code")
        self.assertEqual(len(result), 35)
        self.assertEqual(result.loc["ARG", "map_state"], "Left")
        self.assertEqual(result.loc["PAN", "map_state"], "Unknown")
        self.assertEqual(result.loc["ATG", "map_state"], "NoDPI")
        self.assertEqual(result.loc["ARG", "symbol"], "L")
        self.assertEqual(result.loc["PAN", "symbol"], "?")
        self.assertEqual(result.loc["ATG", "symbol"], "–")
        self.assertTrue(result.observation_date.eq("2023-01-01").all())
        with self.assertRaisesRegex(ValueError, "Duplicate"):
            maps.state_table(pd.concat([dpi, dpi.iloc[[0]]]))

    def test_transition_denominator_uses_one_model_and_country_specific_support(self):
        result, pairs = maps.transition_table(evaluated_fixture())
        rows = result.set_index("country_code")
        self.assertEqual(len(result), 35)
        self.assertEqual(len(pairs), 3)
        self.assertEqual(int(pairs.changed.sum()), 2)
        self.assertEqual(rows.loc["ARG", "n_pairs"], 2)
        self.assertEqual(rows.loc["ARG", "change_pct"], 50.0)
        self.assertEqual(rows.loc["BRA", "change_pct"], 100.0)
        self.assertTrue(rows.loc["ARG", "low_coverage"])
        self.assertEqual(rows.loc["ATG", "map_state"], "NoPairs")
        self.assertTrue(pd.isna(rows.loc["ATG", "change_pct"]))
        self.assertFalse(rows.loc["ATG", "low_coverage"])

    def test_duplicate_nonconsecutive_and_incorrect_change_flags_are_rejected(self):
        fixture = evaluated_fixture()
        cases = []
        cases.append(pd.concat([fixture, fixture.iloc[[0]]]))
        changed = fixture.copy(); changed.loc[0, "changed"] = False; cases.append(changed)
        nonconsecutive = fixture.copy(); nonconsecutive.loc[0, "target_year"] = 2002; cases.append(nonconsecutive)
        unknown = fixture.copy(); unknown.loc[0, "target_state"] = np.nan; cases.append(unknown)
        fractional = fixture.copy(); fractional["year"] = fractional.year.astype(float); fractional.loc[0, "year"] = 2000.5; cases.append(fractional)
        for frame in cases:
            with self.subTest(frame=frame.iloc[0].to_dict()), self.assertRaises(ValueError):
                maps.transition_table(frame)

    def test_network_reciprocal_edges_count_once_and_conflicts_fail(self):
        edges = pd.DataFrame({"src": ["ARG", "BRA"], "dst": ["BRA", "ARG"],
                              "type": ["land", "land"], "distancecategory": [1, 1]})
        result = maps.undirected_edges(edges)
        self.assertEqual(len(result), 1)
        self.assertEqual(result.iloc[0].pair_a, "ARG")
        altered = edges.copy(); altered.loc[1, "distancecategory"] = 2
        with self.assertRaisesRegex(ValueError, "Contradictory"):
            maps.undirected_edges(altered)

    def test_projection_and_render_path_preserve_every_polygon_ring(self):
        doc = geographic.load_americas_geojson(ROOT)
        before = deepcopy(doc)
        usa = next(f for f in doc["features"] if f["properties"]["MODEL_ISO3"] == "USA")
        self.assertEqual(usa["geometry"]["type"], "MultiPolygon")
        for rings in geographic.polygon_rings(usa):
            path = maps.polygon_path(rings)
            self.assertEqual(len(path.vertices), sum(len(ring) for ring in rings))
            self.assertTrue(np.isfinite(path.vertices).all())
        x, y = maps.project(np.array([179.9, -180.1]), np.array([52.0, 52.0]))
        self.assertAlmostEqual(x[0], x[1], places=7)
        self.assertAlmostEqual(y[0], y[1], places=7)
        self.assertEqual(doc, before)


if __name__ == "__main__":
    unittest.main()
