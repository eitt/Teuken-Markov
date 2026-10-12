"""Offline reporting invariants for publication figures, without model fitting.

Small hand-calculated fixtures distinguish calibration from classification,
pair scenario references by country and year, and keep unknown source records
separate from countries absent from the fixed 35-country registry.
"""
from pathlib import Path
import sys
import unittest

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from americas_markov.publication_charts import (
    argmax_change_counts,
    calibration_bins,
    history_composition,
    oil_probability_contrasts,
)


def calibration_fixture():
    rows = []
    values = {
        "markov": ([0.0, .24, .24, .75, 1.0], [False, True, False, False, True]),
        "lean_oil_enso": ([.04, .14, .14, .54, .94], [False, False, True, True, True]),
    }
    for model, (probabilities, changes) in values.items():
        for i, (probability, changed) in enumerate(zip(probabilities, changes)):
            rows.append({
                "country_code": "ARG", "year": 2000 + i, "target_year": 2001 + i,
                "state": "Left", "target_state": "Right" if changed else "Left",
                "changed": changed, "model": model, "p_change": probability,
                "p_left": 1 - probability, "p_center": 0.0, "p_right": probability,
                "predicted_state": "Right" if probability > .5 else "Left",
            })
    return pd.DataFrame(rows)


def classification_fixture():
    # The last row has P(change) > .5 but Left remains the winning category.
    cases = [
        ("Left", "Left", [.90, .05, .05]),
        ("Left", "Right", [.10, .20, .70]),
        ("Left", "Right", [.10, .80, .10]),
        ("Right", "Right", [.55, .10, .35]),
        ("Center", "Left", [.10, .80, .10]),
        ("Center", "Center", [.10, .15, .75]),
        ("Left", "Right", [.45, .30, .25]),
    ]
    states = ["Left", "Center", "Right"]
    rows = []
    for model in ["markov", "lean_oil_enso"]:
        for i, (state, target, probabilities) in enumerate(cases):
            p = probabilities if model == "markov" else [
                .8 if s == target else .1 for s in states
            ]
            rows.append({
                "country_code": "ARG", "year": 2000 + i, "target_year": 2001 + i,
                "state": state, "target_state": target, "changed": state != target,
                "model": model, "p_left": p[0], "p_center": p[1], "p_right": p[2],
                "p_change": 1 - p[states.index(state)],
                "predicted_state": states[int(np.argmax(p))],
            })
    return pd.DataFrame(rows)


def oil_fixture():
    rows = []
    cases = [
        ("ARG", 2023, "Left", 20., 10., {
            0.: [.8, .1, .1], -50.: [.6, .2, .2], 50.: [.9, .05, .05],
        }),
        ("BRA", 2023, "Right", 10., np.nan, {
            0.: [.1, .2, .7], -50.: [.3, .2, .5], 50.: [.05, .05, .9],
        }),
        ("CAN", 2023, "Center", np.nan, np.nan, {
            0.: [.25, .5, .25], -50.: [.4, .2, .4], 50.: [.2, .6, .2],
        }),
        # A second ARG reference must not be paired with its 2023 baseline.
        ("ARG", 2024, "Right", 20., 10., {
            0.: [.2, .2, .6], -50.: [.1, .1, .8], 50.: [.35, .35, .3],
        }),
    ]
    for code, year, state, imports, exports, scenarios in cases:
        for growth, p in scenarios.items():
            rows.append({
                "country_code": code, "year": year, "state": state,
                "fuel_import_share_prior": imports, "fuel_export_share_prior": exports,
                "scenario_oil_growth": growth,
                "p_left": p[0], "p_center": p[1], "p_right": p[2],
            })
    return pd.DataFrame(rows)


class PublicationReportingFixtures(unittest.TestCase):
    def test_default_calibration_keeps_empty_bins_and_probability_endpoints(self):
        source = calibration_fixture()
        result = calibration_bins(source)
        self.assertEqual(len(result), 20)
        self.assertEqual(set(result.model_id), {"markov", "lean_oil_enso"})
        for model, block in result.groupby("model_id"):
            self.assertEqual(len(block), 10)
            self.assertEqual(block.bin_index.nunique(), 10)
            self.assertEqual(int(block.n.sum()), 5)
            self.assertAlmostEqual(float(block.bin_lower.min()), 0.)
            self.assertAlmostEqual(float(block.bin_upper.max()), 1.)
            empty = block[block.n.eq(0)]
            self.assertGreater(len(empty), 0)
            self.assertTrue(empty.mean_predicted_change_probability.isna().all())
            self.assertTrue(empty.observed_change_frequency.isna().all())
        markov = result[result.model_id.eq("markov")].sort_values("bin_index")
        self.assertEqual(int(markov.iloc[0].n), 1)
        self.assertEqual(float(markov.iloc[0].mean_predicted_change_probability), 0.)
        self.assertEqual(float(markov.iloc[0].observed_change_frequency), 0.)
        self.assertEqual(int(markov.iloc[-1].n), 1)
        self.assertEqual(float(markov.iloc[-1].mean_predicted_change_probability), 1.)
        self.assertEqual(float(markov.iloc[-1].observed_change_frequency), 1.)

    def test_calibration_uses_events_and_preserves_unequal_bin_weights(self):
        source = calibration_fixture()
        result = calibration_bins(source, n_bins=2)
        expected = {
            "markov": [(3, .16, 1 / 3), (2, .875, .5)],
            "lean_oil_enso": [(3, .32 / 3, 1 / 3), (2, .74, 1.)],
        }
        for model, values in expected.items():
            block = result[result.model_id.eq(model)].sort_values("bin_index")
            for row, (n, mean, observed) in zip(block.itertuples(), values):
                self.assertEqual(row.n, n)
                self.assertAlmostEqual(row.mean_predicted_change_probability, mean)
                self.assertAlmostEqual(row.observed_change_frequency, observed)
            original = source[source.model.eq(model)]
            self.assertAlmostEqual(
                float((block.n * block.observed_change_frequency).sum()),
                float(original.changed.sum()),
            )
            self.assertAlmostEqual(
                float((block.n * block.mean_predicted_change_probability).sum()),
                float(original.p_change.sum()),
            )

    def test_argmax_distinguishes_correct_direction_wrong_direction_and_false_change(self):
        result = argmax_change_counts(classification_fixture()).set_index("model_id")
        for model in ["markov", "lean_oil_enso"]:
            self.assertEqual(result.loc[model, "n"], 7)
            self.assertEqual(result.loc[model, "observed_changes"], 4)
        self.assertEqual(result.loc["markov", "correct_change_states"], 1)
        self.assertEqual(result.loc["markov", "false_change_predictions"], 2)
        self.assertEqual(result.loc["lean_oil_enso", "correct_change_states"], 4)
        self.assertEqual(result.loc["lean_oil_enso", "false_change_predictions"], 0)

    def test_oil_contrasts_pair_each_country_year_and_keep_both_missingness_types(self):
        source = oil_fixture().sample(frac=1, random_state=17).reset_index(drop=True)
        result = oil_probability_contrasts(source)
        self.assertEqual(len(result), 8)
        self.assertEqual(set(result.scenario_oil_growth), {-50., 50.})
        keys = ["country_code", "year", "scenario_oil_growth"]
        self.assertFalse(result.duplicated(keys).any())
        actual = result.set_index(keys)
        expected = {
            ("ARG", 2023, -50.): ("Left", .4, .2, 20., False),
            ("ARG", 2023, 50.): ("Left", .1, .2, -10., False),
            ("BRA", 2023, -50.): ("Right", .5, .3, 20., True),
            ("BRA", 2023, 50.): ("Right", .1, .3, -20., True),
            ("CAN", 2023, -50.): ("Center", .8, .5, 30., True),
            ("CAN", 2023, 50.): ("Center", .4, .5, -10., True),
            ("ARG", 2024, -50.): ("Right", .2, .4, -20., False),
            ("ARG", 2024, 50.): ("Right", .7, .4, 30., False),
        }
        for key, (state, probability, baseline, difference, missing) in expected.items():
            row = actual.loc[key]
            self.assertEqual(row.state, state)
            self.assertAlmostEqual(row.p_change, probability)
            self.assertAlmostEqual(row.baseline_p_change, baseline)
            self.assertAlmostEqual(row.delta_change_pp, difference)
            self.assertEqual(bool(row.exposure_missing), missing)

    def test_composition_keeps_fixed_registry_and_separates_unknown_from_absent(self):
        source = pd.DataFrame({
            "country_code": ["ARG", "BRA", "CAN", "CUB", "DOM", "URY", "ARG", "BRA"],
            "year": [2000] * 6 + [2001] * 2,
            "state": ["Left", "Center", "Right", None, pd.NA, np.nan, "Left", None],
        })
        result = history_composition(source, dataset_label="Fixture")
        self.assertEqual(len(result), 10)
        for year, values in {2000: (3, 3, 29), 2001: (1, 1, 33)}.items():
            classified, unknown, absent = values
            block = result[result.year.eq(year)].set_index("state")
            self.assertEqual(set(block.index), {"Left", "Center", "Right", "Unknown", "Absent"})
            self.assertEqual(int(block["count"].sum()), 35)
            self.assertEqual(int(block.loc["Unknown", "count"]), unknown)
            self.assertEqual(int(block.loc["Absent", "count"]), absent)
            self.assertTrue(block.classified_count.eq(classified).all())
            self.assertTrue(block.unknown_count.eq(unknown).all())
            self.assertTrue(block.absent_count.eq(absent).all())
            np.testing.assert_allclose(block.share_registry, block["count"] / 35)
            np.testing.assert_allclose(block.coverage_classified, classified / 35)
        second = result[result.year.eq(2001)].set_index("state")
        self.assertEqual(int(second.loc["Center", "count"]), 0)
        self.assertEqual(int(second.loc["Right", "count"]), 0)

    def test_composition_honours_source_year_and_rejects_duplicate_country_year(self):
        frame = pd.DataFrame({"country_code": ["ARG", "BRA"],
                              "source_year": [1945, 1945], "state": ["Left", None]})
        result = history_composition(frame, year_column="source_year")
        self.assertEqual(set(result.year), {1945})
        self.assertEqual(int(result.loc[result.state.eq("Absent"), "count"].iloc[0]), 33)
        duplicate = pd.concat([frame, frame.iloc[[0]]], ignore_index=True)
        with self.assertRaises(ValueError):
            history_composition(duplicate, year_column="source_year")

    def test_oil_contrasts_reject_missing_reference_or_unpaired_scenario(self):
        source = oil_fixture()
        missing_reference = source.loc[~(source.country_code.eq("CAN") &
                                         source.scenario_oil_growth.eq(0))]
        missing_contrast = source.loc[~(source.country_code.eq("BRA") &
                                        source.scenario_oil_growth.eq(50))]
        for frame in [missing_reference, missing_contrast]:
            with self.subTest(rows=len(frame)), self.assertRaises(ValueError):
                oil_probability_contrasts(frame)

    def test_helpers_do_not_mutate_or_depend_on_source_row_order(self):
        fixtures = [(calibration_bins, calibration_fixture()),
                    (argmax_change_counts, classification_fixture()),
                    (oil_probability_contrasts, oil_fixture())]
        for helper, source in fixtures:
            with self.subTest(helper=helper.__name__):
                before = source.copy(deep=True)
                result = helper(source)
                shuffled = helper(source.sample(frac=1, random_state=23))
                pd.testing.assert_frame_equal(source, before)
                keys = [c for c in ["model_id", "bin_index", "country_code", "year",
                                    "scenario_oil_growth"] if c in result]
                pd.testing.assert_frame_equal(
                    result.sort_values(keys).reset_index(drop=True),
                    shuffled.sort_values(keys).reset_index(drop=True),
                )


class FrozenPublicationInputs(unittest.TestCase):
    def test_frozen_history_uses_actual_source_dates_and_registry_denominator(self):
        path = ROOT / "outputs/history/gli_hog_aligned_panel.csv"
        if not path.exists():
            self.skipTest("Frozen HOG history panel not supplied")
        source = pd.read_csv(path)
        result = history_composition(source, year_column="source_year", dataset_label="GLI HOG")
        self.assertEqual((int(result.year.min()), int(result.year.max())), (1945, 2020))
        self.assertEqual(len(result), 76 * 5)
        self.assertTrue(result.groupby("year")["count"].sum().eq(35).all())
        yearly = result.drop_duplicates("year")
        self.assertEqual(int(yearly.classified_count.sum()), 1932)
        self.assertEqual(int(yearly.unknown_count.sum()), 128)
        self.assertEqual(int(yearly.absent_count.sum()), 600)
        np.testing.assert_allclose(result.share_registry, result["count"] / 35)

    def test_frozen_calibration_preserves_all_evaluated_pairs_and_changes(self):
        path = ROOT / "outputs/extensions/dpi_drivers/predictions.csv"
        if not path.exists():
            self.skipTest("Frozen extension predictions not supplied")
        source = pd.read_csv(path)
        result = calibration_bins(source)
        for model in ["markov", "lean_oil_enso"]:
            block = result[result.model_id.eq(model)]
            self.assertEqual(int(block.n.sum()), 1007)
            self.assertAlmostEqual(float((block.n * block.observed_change_frequency).sum()), 93.)
        counts = argmax_change_counts(source).set_index("model_id")
        self.assertEqual(int(counts.loc["markov", "correct_change_states"]), 0)
        self.assertEqual(int(counts.loc["markov", "false_change_predictions"]), 0)
        self.assertEqual(int(counts.loc["lean_oil_enso", "correct_change_states"]), 2)
        self.assertEqual(int(counts.loc["lean_oil_enso", "false_change_predictions"]), 2)

    def test_frozen_oil_contrasts_preserve_all_countries_and_unknown_exposures(self):
        path = ROOT / "outputs/extensions/dpi_drivers/conditional_oil_scenarios.csv"
        if not path.exists():
            self.skipTest("Frozen conditional scenarios not supplied")
        result = oil_probability_contrasts(pd.read_csv(path))
        self.assertEqual((len(result), result.country_code.nunique()), (60, 30))
        self.assertEqual(set(result.year), {2023})
        self.assertEqual(set(result.scenario_oil_growth), {-50., 50.})
        missing = result[result.exposure_missing]
        self.assertEqual(set(missing.country_code), {"HTI", "LCA", "VEN"})
        self.assertEqual(len(missing), 6)
        indexed = result.set_index(["country_code", "scenario_oil_growth"])
        self.assertAlmostEqual(indexed.loc[("GUY", -50.), "delta_change_pp"], 14.016221, places=5)
        self.assertAlmostEqual(indexed.loc[("COL", 50.), "delta_change_pp"], -6.013912, places=5)


if __name__ == "__main__":
    unittest.main()
