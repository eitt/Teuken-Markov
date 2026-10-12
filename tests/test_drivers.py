"""Date and provenance invariants for optional observed drivers, entirely offline.

Sentinel-valued fixtures test joins and conditional prediction mechanics. They
are not simulated empirical evidence and no test estimates a causal effect.
"""
from __future__ import annotations

from pathlib import Path
import sys
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from americas_markov import drivers
from americas_markov.data import DataSourceError


def driver_fixture():
    features = pd.DataFrame([
        {"country_code": code, "year": year, "state": "Left", "oil_growth": 10.0 + year - 2002}
        for year in [2002, 2003] for code in ["ARG", "BRA"]
    ])
    wdi = pd.DataFrame([
        {"country_code": code, "year": year, "fuel_import_share": 20.0 + year - 2000 + i}
        for year in range(2000, 2005) for i, code in enumerate(["ARG", "BRA", "WLD"])
    ])
    exposures = pd.DataFrame([
        {"country_code": code, "year": year, "fuel_export_share": 40.0 + year - 2000 + i,
         "agriculture_share": 15.0 + year - 2000 + i}
        for year in range(2000, 2005) for i, code in enumerate(["ARG", "BRA"])
    ])
    climate = pd.DataFrame({"year": [2000, 2001, 2002, 2003, 2004],
                            "enso_mean": [-9.0, -0.5, 0.75, 9.0, 99.0]})
    return features, wdi, exposures, climate


class ObservedDriverIntegrity(unittest.TestCase):
    def test_different_dates_and_denominators_are_kept_separate(self):
        result = drivers.prepare_driver_features(*driver_fixture()).set_index(["country_code", "year"])
        row = result.loc[("ARG", 2002)]
        self.assertEqual(row.exposure_source_year, 2000)
        self.assertEqual(row.climate_source_year, 2001)
        self.assertEqual(row.fuel_import_share_prior, 20.0)
        self.assertEqual(row.fuel_export_share_prior, 40.0)
        self.assertEqual(row.agriculture_share_prior, 15.0)
        self.assertEqual(row.enso_mean, -0.5)
        self.assertAlmostEqual(row.oil_x_import_prior, 2.0)
        self.assertAlmostEqual(row.oil_x_export_prior, 4.0)
        self.assertAlmostEqual(row.enso_x_agriculture_prior, -0.075)
        # Percent of imports and percent of exports cannot become net exposure.
        self.assertFalse(any("net" in c.lower() for c in result.columns))

    def test_future_exposure_and_climate_observations_cannot_change_past_origin(self):
        features, wdi, exposures, climate = driver_fixture()
        before = drivers.prepare_driver_features(features, wdi, exposures, climate)
        wdi.loc[wdi.year >= 2001, "fuel_import_share"] = 1e8
        exposures.loc[exposures.year >= 2001, ["fuel_export_share", "agriculture_share"]] = 1e8
        climate.loc[climate.year >= 2002, "enso_mean"] = 1e8
        after = drivers.prepare_driver_features(features, wdi, exposures, climate)
        pd.testing.assert_frame_equal(before.loc[before.year == 2002].reset_index(drop=True),
                                      after.loc[after.year == 2002].reset_index(drop=True))

    def test_missing_observations_remain_missing_without_temporal_fill(self):
        features, wdi, exposures, climate = driver_fixture()
        wdi = wdi.loc[~(wdi.country_code.eq("ARG") & wdi.year.eq(2000))]
        exposures = exposures.loc[~(exposures.country_code.eq("ARG") & exposures.year.eq(2000))]
        climate = climate.loc[climate.year != 2001]
        result = drivers.prepare_driver_features(features, wdi, exposures, climate).set_index(["country_code", "year"])
        row = result.loc[("ARG", 2002)]
        self.assertTrue(row[["fuel_import_share_prior", "fuel_export_share_prior", "agriculture_share_prior",
                             "enso_mean", "oil_x_import_prior", "oil_x_export_prior",
                             "enso_x_agriculture_prior"]].isna().all())
        self.assertEqual(row.exposure_source_year, 2000)
        self.assertEqual(row.climate_source_year, 2001)
        self.assertTrue(np.isfinite(result.loc[("ARG", 2003), "oil_x_import_prior"]))

    def test_joins_preserve_political_support_and_do_not_mutate_inputs(self):
        fixture = driver_fixture()
        originals = [f.copy(deep=True) for f in fixture]
        result = drivers.prepare_driver_features(*fixture)
        self.assertEqual(set(zip(result.country_code, result.year)), {("ARG", 2002), ("BRA", 2002),
                                                                       ("ARG", 2003), ("BRA", 2003)})
        self.assertEqual(len(result), 4)
        for original, actual in zip(originals, fixture):
            pd.testing.assert_frame_equal(original, actual)
        shuffled = drivers.prepare_driver_features(*(f.sample(frac=1, random_state=17) for f in fixture))
        keys = ["country_code", "year"]
        pd.testing.assert_frame_equal(result.sort_values(keys).reset_index(drop=True),
                                      shuffled.sort_values(keys).reset_index(drop=True))

    def test_duplicate_keys_are_rejected_instead_of_multiplying_political_rows(self):
        for index in range(4):
            with self.subTest(input_index=index):
                fixture = list(driver_fixture())
                fixture[index] = pd.concat([fixture[index], fixture[index].iloc[[0]]], ignore_index=True)
                with self.assertRaises(ValueError):
                    drivers.prepare_driver_features(*fixture)

    def test_missing_optional_cache_fails_without_requesting_internet(self):
        with TemporaryDirectory() as temporary, patch.object(drivers, "urlopen") as request:
            with self.assertRaises(DataSourceError):
                drivers.load_exposures(Path(temporary))
            request.assert_not_called()

    def test_oil_contrast_updates_only_declared_shock_products(self):
        snapshot = drivers.prepare_driver_features(*driver_fixture())
        original = snapshot.copy(deep=True)
        expected = np.tile([0.2, 0.3, 0.5], (len(snapshot), 1))
        with patch("americas_markov.models.predict_probabilities", return_value=expected) as predict:
            result = drivers.conditional_oil_scenario({"kind": "fixture"}, snapshot, -20)
        passed = predict.call_args.args[1]
        self.assertTrue(passed.oil_growth.eq(-20).all())
        np.testing.assert_allclose(passed.oil_x_import_prior, -20 * snapshot.fuel_import_share_prior / 100)
        np.testing.assert_allclose(passed.oil_x_export_prior, -20 * snapshot.fuel_export_share_prior / 100)
        unchanged = [c for c in snapshot if c not in ["oil_growth", "oil_x_import_prior", "oil_x_export_prior"]]
        pd.testing.assert_frame_equal(passed[unchanged], snapshot[unchanged])
        pd.testing.assert_frame_equal(snapshot, original)
        np.testing.assert_array_equal(result, expected)


if __name__ == "__main__":
    unittest.main()
