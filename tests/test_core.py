"""Scientific integrity tests using cached public sources and small fixtures.

Run offline from the project root with ``python -m unittest discover -s tests``.
No test downloads data, reconstructs missing political labels, or estimates
causal effects. Cached-source tests skip clearly if the source bundle is absent.
"""

from __future__ import annotations

import csv
import json
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from americas_markov import STATES, data, features, models, network, simulation


def small_feature_fixture(first=1990, last=2006):
    """Sentinel-valued economic history, not a fabricated research dataset."""
    codes = ["ARG", "BRA", "URY"]
    political_rows, economic_rows, price_rows = [], [], []
    for year in range(first, last + 1):
        for index, code in enumerate(codes):
            political_rows.append({
                "country_code": code, "year": year,
                "state": STATES[(year - first + index) % 3],
                "years_in_office": float((year - first) % 4 + 1), "eiec": 7.0,
                # An election during the forecast interval must not enter X.
                "election_held": float(year % 2),
            })
    for year in range(first - 1, last + 1):
        for index, code in enumerate(codes):
            economic_rows.append({
                "country_code": code, "year": year,
                "gdp_growth": float(year + index / 10),
                "inflation": float(year + 100 + index),
                "trade_open": 40.0 + index,
                "fuel_import_share": 5.0 + index,
                "tourism_exports_share": 10.0 + index,
            })
        economic_rows.append({"country_code": "WLD", "year": year, "gdp_growth": float(year + 200)})
        price_rows.append({"year": year, "oil_growth": float(year + 300), "food_growth": float(year + 400)})
    weights = pd.DataFrame(
        [[0.0, 1.0, 0.0], [0.5, 0.0, 0.5], [0.0, 1.0, 0.0]], index=codes, columns=codes
    )
    networks = {year: weights.copy() for year in range(first, last + 1)}
    for year, frame in networks.items():
        frame.attrs["snapshot_year"] = min(year, 2016)
    return pd.DataFrame(political_rows), pd.DataFrame(economic_rows), pd.DataFrame(price_rows), networks


class TemporalFeatures(unittest.TestCase):
    def test_unknown_state_validation_handles_missing_scalars(self):
        for value in [pd.NA, None, np.nan, "0", "-999", "unclassified"]:
            with self.subTest(value=repr(value)):
                self.assertTrue(pd.isna(features.valid_state(value)))
        for value in STATES:
            self.assertEqual(features.valid_state(value), value)

    def test_consecutive_year_join_cannot_bridge_unknown_or_absent_years(self):
        frame = pd.DataFrame([
            {"country_code": "ARG", "year": 2000, "state": "Left", "eiec": 7},
            {"country_code": "ARG", "year": 2001, "state": pd.NA, "eiec": 7},
            {"country_code": "ARG", "year": 2002, "state": "Right", "eiec": 7},
            {"country_code": "ARG", "year": 2003, "state": "Center", "eiec": 7},
            {"country_code": "BRA", "year": 2000, "state": "Left", "eiec": 7},
            {"country_code": "BRA", "year": 2002, "state": "Right", "eiec": 7},
            {"country_code": "BRA", "year": 2003, "state": "Left", "eiec": 7},
        ])
        panel = features.make_transition_panel(frame)
        self.assertEqual(set(zip(panel.country_code, panel.year, panel.target_year)), {
            ("ARG", 2002, 2003), ("BRA", 2002, 2003)
        })
        self.assertTrue(panel.target_year.eq(panel.year + 1).all())

    def test_macro_information_is_lagged_exactly_one_year(self):
        fixture = small_feature_fixture(first=2019, last=2023)
        frame = features.prepare_features(*fixture).set_index(["country_code", "year"])
        row = frame.loc[("ARG", 2022)]
        self.assertEqual(row.economic_year, 2021)
        self.assertEqual(row.gdp_growth, 2021.0)
        self.assertEqual(row.inflation, 2121.0)
        self.assertEqual(row.world_growth, 2221.0)
        self.assertEqual(row.oil_growth, 2321.0)
        self.assertEqual(row.food_growth, 2421.0)
        # Dates, rather than retrospectively observed ideology, define these flags.
        self.assertEqual(frame.loc[("ARG", 2020), "covid_lag"], 0)
        self.assertEqual(frame.loc[("ARG", 2021), "covid_lag"], 1)
        self.assertEqual(frame.loc[("ARG", 2022), "covid_lag"], 1)
        self.assertEqual(frame.loc[("ARG", 2023), "covid_lag"], 0)
        panel = features.make_transition_panel(frame.reset_index())
        self.assertTrue(panel.ukraine_lag_not_estimable.eq(0).all())
        self.assertFalse(any("ukraine" in name for name in features.SHOCK_NUM))
        self.assertFalse(any("election_held" in columns for columns in models.MODEL_FEATURES.values()))

    def test_future_data_changes_do_not_change_earlier_features(self):
        politics, economies, prices, networks = small_feature_fixture(2019, 2023)
        before = features.prepare_features(politics, economies, prices, networks)
        political_future = politics.copy()
        political_future.loc[political_future.year >= 2023, "state"] = "Right"
        economic_future = economies.copy()
        economic_future.loc[economic_future.year >= 2022, ["gdp_growth", "inflation"]] = 999999.0
        price_future = prices.copy()
        price_future.loc[price_future.year >= 2022, ["oil_growth", "food_growth"]] = 999999.0
        after = features.prepare_features(political_future, economic_future, price_future, networks)
        cols = ["country_code", "year", *features.DOMESTIC_NUM, *features.NETWORK_NUM, *features.SHOCK_NUM]
        pd.testing.assert_frame_equal(
            before.loc[before.year <= 2022, cols].reset_index(drop=True),
            after.loc[after.year <= 2022, cols].reset_index(drop=True),
        )

    def test_neighbors_ignore_self_and_unknown_without_assigning_center(self):
        codes = ["ARG", "BRA", "URY", "CUB"]
        weights = pd.DataFrame([
            [0.2, 0.4, 0.4, 0], [0.5, 0, 0.5, 0], [0.5, 0.5, 0, 0], [0, 0, 0, 0]
        ], index=codes, columns=codes)
        original = weights.copy()
        states = pd.Series({"ARG": "Left", "BRA": "Right", "URY": pd.NA, "CUB": pd.NA})
        result = features.neighbor_features(states, weights)
        self.assertEqual(result.loc["ARG", "neighbor_right"], 1.0)
        self.assertEqual(result.loc["ARG", "neighbor_left"], 0.0)
        self.assertEqual(result.loc["ARG", "neighbor_center"], 0.0)
        self.assertAlmostEqual(result.loc["ARG", "neighbor_known_weight"], 0.4)
        self.assertEqual(result.loc["CUB", "isolated"], 1.0)
        self.assertEqual(result.loc["CUB", "neighbor_known_weight"], 0.0)
        self.assertTrue(result.loc["CUB", ["neighbor_left", "neighbor_center", "neighbor_right"]].eq(0).all())
        changed_self = states.copy()
        changed_self.loc["ARG"] = "Center"
        repeat = features.neighbor_features(changed_self, weights)
        pd.testing.assert_series_equal(result.loc["ARG"], repeat.loc["ARG"])
        pd.testing.assert_frame_equal(weights, original)


class ModelIntegrity(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.panel = features.make_transition_panel(features.prepare_features(*small_feature_fixture()))

    def test_all_six_models_produce_fixed_label_order_and_normalized_probabilities(self):
        train = self.panel.loc[self.panel.year < 2004]
        test = self.panel.loc[self.panel.year == 2004]
        for name in models.MODEL_ORDER:
            with self.subTest(model=name):
                fitted = models.fit_model(train, name)
                probabilities = models.predict_probabilities(fitted, test)
                self.assertEqual(probabilities.shape, (len(test), 3))
                self.assertTrue(np.isfinite(probabilities).all())
                self.assertTrue((probabilities >= 0).all())
                np.testing.assert_allclose(probabilities.sum(axis=1), 1.0)
                if name == "persistence":
                    expected = np.column_stack([test.state.eq(state) for state in ("Left", "Center", "Right")])
                    np.testing.assert_array_equal(probabilities, expected)

    def test_markov_rows_use_training_transitions_not_target_column_order(self):
        train = pd.DataFrame({
            "state": ["Left", "Left", "Left", "Center", "Center", "Right"],
            "target_state": ["Right", "Right", "Left", "Left", "Left", "Right"],
        })
        test = pd.DataFrame({"state": ["Left", "Center", "Right"]})
        result = models.predict_probabilities(models.fit_model(train, "markov"), test)
        # Laplace adds one per destination to each independently observed row.
        np.testing.assert_allclose(result, [[2/6, 1/6, 3/6], [3/5, 1/5, 1/5], [1/4, 1/4, 2/4]])

    def test_one_class_training_has_an_explicit_constant_prediction(self):
        train = self.panel.iloc[:12].copy()
        train["target_state"] = "Right"
        result = models.predict_probabilities(models.fit_model(train, "domestic"), self.panel.iloc[-3:])
        np.testing.assert_array_equal(result, np.tile([0.0, 0.0, 1.0], (3, 1)))

    def test_missing_target_class_does_not_shift_probability_labels(self):
        train = self.panel.loc[self.panel.target_state.ne("Center")]
        test = self.panel.iloc[-3:].copy()
        fitted = models.fit_model(train, "domestic")
        result = models.predict_probabilities(fitted, test)
        np.testing.assert_array_equal(result[:, 1], 0.0)
        np.testing.assert_allclose(result.sum(axis=1), 1.0)
        raw = fitted["estimator"].predict_proba(test)
        self.assertEqual(list(fitted["estimator"].named_steps["classifier"].classes_), ["Left", "Right"])
        np.testing.assert_allclose(result[:, [0, 2]], raw)

    def test_imputer_scaler_and_encoder_are_fitted_only_on_training(self):
        train = self.panel.loc[self.panel.year < 2004].copy()
        train.loc[train.index[::3], "gdp_growth"] = np.nan
        test = self.panel.loc[self.panel.year == 2004].copy()
        test["gdp_growth"] = 1e12
        test["country_code"] = "UNSEEN_COUNTRY"
        fitted = models.fit_model(train, "domestic")
        preprocess = fitted["estimator"].named_steps["preprocess"]
        numeric = preprocess.named_transformers_["numeric"]
        imputer = numeric.named_steps["impute"]
        scaler = numeric.named_steps["scale"]
        encoder = preprocess.named_transformers_["categorical"]
        self.assertAlmostEqual(imputer.statistics_[0], float(train.gdp_growth.median()))
        filled_training = train.gdp_growth.fillna(train.gdp_growth.median())
        self.assertAlmostEqual(scaler.mean_[0], float(filled_training.mean()))
        self.assertNotIn("UNSEEN_COUNTRY", encoder.categories_[1])
        imputation_before, mean_before = imputer.statistics_.copy(), scaler.mean_.copy()
        probabilities = models.predict_probabilities(fitted, test)
        np.testing.assert_allclose(probabilities.sum(axis=1), 1.0)
        np.testing.assert_array_equal(imputer.statistics_, imputation_before)
        np.testing.assert_array_equal(scaler.mean_, mean_before)

    def test_expanding_folds_use_only_results_available_at_origin(self):
        predictions, metrics, folds = models.rolling_evaluate(self.panel, start_year=2004)
        self.assertEqual(set(predictions.model), set(models.MODEL_ORDER))
        self.assertTrue(predictions.train_max_origin.lt(predictions.year).all())
        self.assertTrue(predictions.train_max_target.le(predictions.year).all())
        self.assertTrue(predictions.target_year.eq(predictions.year + 1).all())
        self.assertFalse(predictions.duplicated(["model", "country_code", "year"]).any())
        counts = predictions.groupby("model").size()
        self.assertEqual(counts.nunique(), 1)
        np.testing.assert_allclose(predictions[["p_left", "p_center", "p_right"]].sum(axis=1), 1)
        expected_labels = np.asarray(["Left", "Center", "Right"])[
            predictions[["p_left", "p_center", "p_right"]].to_numpy().argmax(axis=1)
        ]
        np.testing.assert_array_equal(predictions.predicted_state.to_numpy(), expected_labels)
        self.assertTrue(np.isfinite(metrics.log_loss_clipped).all())
        self.assertTrue(np.isfinite(metrics.brier_multiclass).all())
        self.assertTrue(folds.groupby("model").train_n.apply(lambda x: x.is_monotonic_increasing).all())

    def test_degenerate_persistence_scores_disclose_zero_probability_outcomes(self):
        frame = pd.DataFrame({
            "p_left": [1.0, 0.0], "p_center": [0.0, 1.0], "p_right": [0.0, 0.0],
            "state": ["Left", "Center"],
            "target_state": ["Left", "Right"], "predicted_state": ["Left", "Center"],
            "changed": [False, True],
        })
        score = models.score_predictions(frame)
        self.assertEqual(score["zero_probability_outcomes"], 1)
        self.assertAlmostEqual(score["accuracy"], 0.5)
        self.assertAlmostEqual(score["brier_multiclass"], 1.0)
        self.assertAlmostEqual(score["log_loss_clipped"], -np.log(1e-12) / 2)
        self.assertAlmostEqual(score["brier_change"], 0.5)
        self.assertAlmostEqual(score["roc_auc_change"], 0.5)
        self.assertAlmostEqual(score["average_precision_change"], 0.5)

    def test_change_risk_uses_probability_of_leaving_the_actual_initial_state(self):
        frame = pd.DataFrame({
            "state": ["Left", "Center", "Right", "Left"],
            "target_state": ["Left", "Right", "Right", "Center"],
            "changed": [False, True, False, True],
            "p_left": [0.9, 0.1, 0.1, 0.2],
            "p_center": [0.05, 0.6, 0.1, 0.7],
            "p_right": [0.05, 0.3, 0.8, 0.1],
            "predicted_state": ["Left", "Center", "Right", "Center"],
        })
        score = models.score_predictions(frame)
        # Risks .1,.4,.2,.8: both changes rank above both non-changes.
        self.assertAlmostEqual(score["brier_change"], 0.1125)
        self.assertAlmostEqual(score["roc_auc_change"], 1.0)
        self.assertAlmostEqual(score["average_precision_change"], 1.0)
        self.assertAlmostEqual(score["accuracy"], 0.75)
        changes_only = models.score_predictions(frame.loc[frame.changed])
        self.assertTrue(np.isnan(changes_only["roc_auc_change"]))
        self.assertTrue(np.isnan(changes_only["average_precision_change"]))


class ConditionalSimulation(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        prepared = features.prepare_features(*small_feature_fixture())
        cls.initial = prepared.loc[prepared.year.eq(prepared.year.max())].copy()
        cls.panel = features.make_transition_panel(prepared)
        cls.weights = small_feature_fixture()[-1][2006]

    def test_persistence_simulation_preserves_initial_labels_and_country_counts(self):
        draws, summary = simulation.simulate(
            {"kind": "persistence"}, self.initial, self.weights,
            horizon=3, runs=5, seed=11,
        )
        self.assertEqual(len(draws), len(self.initial) * 5 * 4)
        self.assertFalse(draws.duplicated(["path", "year", "country_code"]).any())
        observed = self.initial.set_index("country_code").state.to_dict()
        self.assertTrue(draws.state.eq(draws.country_code.map(observed)).all())
        self.assertTrue(draws.loc[draws.year.eq(2006), "initial_observed"].all())
        self.assertFalse(draws.loc[draws.year.gt(2006), "initial_observed"].any())
        self.assertEqual(set(draws.scenario), {"condiciones_constantes"})
        np.testing.assert_allclose(summary.groupby("year").mean_countries.sum(), 3.0)
        np.testing.assert_allclose(summary.q05, summary.q95)
        self.assertTrue(summary.active_countries.eq(3).all())

    def test_markov_simulation_is_reproducible_with_an_explicit_seed(self):
        fitted = models.fit_model(self.panel, "markov")
        kwargs = dict(horizon=4, runs=20, seed=2026, scenario="recesion_hipotetica")
        first, first_summary = simulation.simulate(fitted, self.initial, self.weights, **kwargs)
        second, second_summary = simulation.simulate(fitted, self.initial, self.weights, **kwargs)
        pd.testing.assert_frame_equal(first, second)
        pd.testing.assert_frame_equal(first_summary, second_summary)
        self.assertEqual(set(first.state), {"Left", "Center", "Right"})
        self.assertEqual(set(first_summary.scenario), {"recesion_hipotetica"})
        np.testing.assert_allclose(first_summary.groupby("year").mean_countries.sum(), 3.0)
        self.assertTrue(first_summary.q05.le(first_summary.q95).all())

    def test_unknown_initial_states_cannot_be_simulated_as_center(self):
        initial = self.initial.copy()
        initial.iloc[0, initial.columns.get_loc("state")] = pd.NA
        with self.assertRaisesRegex(ValueError, "estado inicial"):
            simulation.simulate({"kind": "persistence"}, initial, self.weights, runs=1)

    def test_network_updates_use_the_previous_step_for_every_country(self):
        initial = self.initial.loc[self.initial.country_code.isin(["ARG", "BRA"])].copy()
        initial.loc[initial.country_code.eq("ARG"), "state"] = "Left"
        initial.loc[initial.country_code.eq("BRA"), "state"] = "Right"
        weights = pd.DataFrame([[0.0, 1.0], [1.0, 0.0]], index=["ARG", "BRA"], columns=["ARG", "BRA"])
        calls = []

        def deterministic_swap(model, block):
            calls.append(block.copy())
            destination = block.state.map({"Left": "Right", "Right": "Left", "Center": "Center"})
            return np.column_stack([destination.eq(label).astype(float) for label in STATES])

        with patch("americas_markov.simulation.predict_probabilities", side_effect=deterministic_swap):
            simulation.simulate({}, initial, weights, horizon=2, runs=1)
        self.assertEqual(len(calls), 2)
        first, second = [block.set_index("country_code") for block in calls]
        self.assertEqual(first.loc["ARG", "neighbor_right"], 1.0)
        self.assertEqual(first.loc["BRA", "neighbor_left"], 1.0)
        self.assertEqual(second.loc["ARG", "neighbor_left"], 1.0)
        self.assertEqual(second.loc["BRA", "neighbor_right"], 1.0)
        self.assertTrue(second.state_duration.eq(1.0).all())

    def test_excluded_neighbors_reduce_coverage_without_creating_geographic_isolates(self):
        initial = self.initial.loc[self.initial.country_code.isin(["ARG", "BRA"])].copy()
        codes = ["ARG", "BRA", "CUB"]
        weights = pd.DataFrame([[0, 0, 1], [0, 0, 1], [0.5, 0.5, 0]], index=codes, columns=codes, dtype=float)
        captured = []

        def persistence_capture(model, block):
            captured.append(block.copy())
            return np.column_stack([block.state.eq(label).astype(float) for label in STATES])

        with patch("americas_markov.simulation.predict_probabilities", side_effect=persistence_capture):
            simulation.simulate({}, initial, weights, horizon=1, runs=1)
        frame = captured[0]
        self.assertTrue(frame.neighbor_known_weight.eq(0).all())
        self.assertTrue(frame[["neighbor_left", "neighbor_center", "neighbor_right"]].eq(0).all().all())
        self.assertTrue(frame.isolated.eq(0).all(), "Missing neighbor ideology is not geographic isolation.")

    def test_scenario_shocks_have_declared_units_duration_and_baseline(self):
        captured = []

        def persistence_capture(model, block):
            captured.append(block.copy())
            return np.column_stack([block.state.eq(label).astype(float) for label in STATES])

        original = self.initial.copy(deep=True)
        weights_original = self.weights.copy(deep=True)
        with patch("americas_markov.simulation.predict_probabilities", side_effect=persistence_capture):
            draws, summary = simulation.simulate(
                {}, self.initial, self.weights, horizon=3, runs=1,
                scenario="energia_alimentos_hipotetico", shock_duration=2,
            )
        for step, block in enumerate(captured, start=1):
            self.assertTrue(block.oil_growth.eq(50.0 if step <= 2 else 0.0).all())
            self.assertTrue(block.food_growth.eq(20.0 if step <= 2 else 0.0).all())
            self.assertTrue(block.covid_lag.eq(0).all())
            np.testing.assert_allclose(block.oil_x_fuel, block.oil_growth * block.fuel_import_share / 100)
            np.testing.assert_allclose(block.food_x_trade, block.food_growth * block.trade_open / 100)
        self.assertEqual(set(draws.scenario), {"energia_alimentos_hipotetico"})
        self.assertEqual(set(summary.scenario), {"energia_alimentos_hipotetico"})
        pd.testing.assert_frame_equal(self.initial, original)
        pd.testing.assert_frame_equal(self.weights, weights_original)


class CachedPublicSources(unittest.TestCase):
    """Coverage and missing-value checks against independent raw records."""

    @classmethod
    def setUpClass(cls):
        path = ROOT / "data" / "raw" / "dpi2023.csv"
        if not path.is_file():
            raise unittest.SkipTest("Cached DPI source is absent; run the data download first.")
        cls.politics = data.load_politics(ROOT)

    def test_all_31_dpi_countries_remain_in_the_panel(self):
        self.assertEqual(self.politics.country_code.nunique(), 31)
        self.assertEqual(
            set(data.AMERICAS_ISO3) - set(self.politics.country_code),
            {"ATG", "DMA", "KNA", "VCT"},
        )
        self.assertEqual((self.politics.year.min(), self.politics.year.max()), (1975, 2023))
        self.assertFalse(self.politics.duplicated(["country_code", "year"]).any())

    def test_unclassified_and_missing_labels_are_never_centrist(self):
        unknown = self.politics.ideology_raw.isin(["0", "0.0", "-999", "-999.0", "", "NA"])
        self.assertGreater(int(unknown.sum()), 0)
        self.assertTrue(self.politics.loc[unknown, "state"].isna().all())
        self.assertEqual(set(self.politics.state.dropna()), {"Left", "Center", "Right"})
        known = ~unknown
        self.assertTrue(
            self.politics.loc[known, "state"].eq(self.politics.loc[known, "ideology_raw"]).all()
        )

    def test_wdi_missing_values_and_reported_values_survive_loading(self):
        path = ROOT / "data" / "raw" / "wdi_NY.GDP.MKTP.KD.ZG.json"
        if not path.exists():
            self.skipTest("Cached WDI sources are absent.")
        frame = data.load_wdi(ROOT).set_index(["country_code", "year"])
        self.assertEqual(frame.index.nunique(), 36 * 66)
        with path.open(encoding="utf-8-sig") as handle:
            raw = json.load(handle)[1]
        checked_missing = checked_reported = 0
        for row in raw:
            code = row["countryiso3code"]
            year = int(row["date"])
            if code not in data.AMERICAS_ISO3 or not 1975 <= year <= 2023:
                continue
            loaded = frame.loc[(code, year), "gdp_growth"]
            if row["value"] is None:
                self.assertTrue(pd.isna(loaded), (code, year))
                checked_missing += 1
            else:
                self.assertAlmostEqual(float(loaded), float(row["value"]), places=10)
                checked_reported += 1
        self.assertGreater(checked_missing, 0)
        self.assertGreater(checked_reported, 0)

    def test_pink_sheet_excludes_incomplete_terminal_years(self):
        if not (ROOT / "data" / "raw" / "pink_sheet_monthly.xlsx").exists():
            self.skipTest("Cached Pink Sheet source is absent.")
        prices = data.load_prices(ROOT)
        self.assertTrue(prices.year.is_unique)
        self.assertFalse((prices.year >= 2026).any())
        for value, count in [("oil_price", "monthly_count_oil"), ("food_index", "monthly_count_food")]:
            valid = prices[value].notna()
            self.assertTrue(prices.loc[valid, count].eq(12).all())
            self.assertTrue(prices.loc[prices[count].ne(12), value].isna().all())


class ObservedGeography(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        raw = ROOT / "data" / "raw"
        required = ["cow_contdird_v3.2.csv", "cow_states_v2024.csv", "cow_contiguity_manifest.json"]
        if not all((raw / name).exists() for name in required):
            raise unittest.SkipTest("Cached COW sources are absent; run the geography download first.")

    def test_known_land_dyads_and_probability_weight_rows(self):
        codes = ["CAN", "USA", "MEX", "CUB", "JAM"]
        weights, edges = network.build_network(ROOT, codes, include_water=False)
        self.assertEqual(list(weights.index), codes)
        self.assertEqual(list(weights.columns), codes)
        np.testing.assert_array_equal(np.diag(weights), np.zeros(len(codes)))
        self.assertAlmostEqual(weights.loc["USA", "CAN"], 0.5)
        self.assertAlmostEqual(weights.loc["USA", "MEX"], 0.5)
        self.assertAlmostEqual(weights.loc["CAN", "USA"], 1.0)
        self.assertAlmostEqual(weights.loc["MEX", "USA"], 1.0)
        self.assertEqual(set(zip(edges.src, edges.dst)), {
            ("CAN", "USA"), ("USA", "CAN"), ("USA", "MEX"), ("MEX", "USA")
        })
        self.assertTrue(edges.type.eq("land").all())
        self.assertEqual(network.isolation_flags(weights).to_dict(), {
            "CAN": False, "USA": False, "MEX": False, "CUB": True, "JAM": True
        })
        self.assertTrue(weights.loc[["CUB", "JAM"]].eq(0).all().all())

    def test_full_network_has_only_observed_symmetric_dyads(self):
        weights, edges = network.build_network(ROOT, list(data.DPI_COUNTRY_MAP.values()))
        self.assertFalse(edges.duplicated(["src", "dst"]).any())
        pairs = set(zip(edges.src, edges.dst))
        self.assertEqual(pairs, {(b, a) for a, b in pairs})
        self.assertFalse(any(a == b for a, b in pairs))
        self.assertTrue(edges.distancecategory.isin([1, 2, 3, 4, 5]).all())
        sums = weights.sum(axis=1).to_numpy()
        self.assertTrue(np.logical_or(np.isclose(sums, 1), np.isclose(sums, 0)).all())
        self.assertFalse(weights.lt(0).any().any())

    def test_network_rejects_unobserved_future_topology(self):
        with self.assertRaisesRegex(ValueError, "1816-2016"):
            network.build_network(ROOT, ["USA", "CAN"], snapshot_year=2023)
        with self.assertRaisesRegex(ValueError, "duplicate"):
            network.build_network(ROOT, ["USA", "USA"])

    def test_missing_geographic_cache_fails_without_internet_access(self):
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            with patch("urllib.request.urlopen") as urllib_open, \
                 patch("americas_markov.network.urlopen") as network_open, \
                 patch("americas_markov.network.download_contiguity") as download:
                with self.assertRaisesRegex(RuntimeError, "download"):
                    network.build_network(root, ["USA", "CAN"])
                urllib_open.assert_not_called()
                network_open.assert_not_called()
                download.assert_not_called()
                # A manifest without its CSVs must also fail, not refill a cache.
                raw = root / "data" / "raw"
                raw.mkdir(parents=True)
                (raw / "cow_contiguity_manifest.json").write_text(
                    (ROOT / "data" / "raw" / "cow_contiguity_manifest.json").read_text(),
                    encoding="utf-8",
                )
                with self.assertRaisesRegex(RuntimeError, "offline no descarga"):
                    network.build_network(root, ["USA", "CAN"])
                urllib_open.assert_not_called()
                network_open.assert_not_called()
                download.assert_not_called()


if __name__ == "__main__":
    unittest.main()
