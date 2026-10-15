"""Integrity of local model specifications and expanding evaluation, offline."""
from __future__ import annotations

from copy import deepcopy
from pathlib import Path
import sys
import unittest

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from americas_markov import STATES, drivers, models


def model_fixture():
    numeric = list(dict.fromkeys([c for columns in models.MODEL_FEATURES.values() for c in columns]
                                + drivers.OIL_COLUMNS + drivers.CLIMATE_COLUMNS))
    rows = []
    for year in range(1990, 2009):
        for index, country in enumerate(["ARG", "BRA", "URY"]):
            state = STATES[(year + index) % 3]
            target = STATES[(year + index + int(year % 5 == 0)) % 3]
            row = {"country_code": country, "year": year, "target_year": year + 1,
                   "state": state, "target_state": target, "changed": state != target}
            row.update({column: float((year - 1990) / 10 + index / 5 + offset / 100)
                        for offset, column in enumerate(numeric)})
            rows.append(row)
    return pd.DataFrame(rows)


class LocalExtensionModels(unittest.TestCase):
    def test_explicit_columns_fit_without_changing_original_registry(self):
        order, registry = list(models.MODEL_ORDER), deepcopy(models.MODEL_FEATURES)
        panel = model_fixture()
        fitted = models.fit_model(panel.loc[panel.year < 2005], "external_spec", numeric_columns=["gdp_growth"])
        self.assertEqual(fitted["numeric_columns"], ["gdp_growth"])
        self.assertEqual(models.MODEL_ORDER, order)
        self.assertEqual(models.MODEL_FEATURES, registry)
        self.assertNotIn("external_spec", models.MODEL_FEATURES)
        self.assertEqual(fitted["estimator"].named_steps["preprocess"].transformers_[0][2], ["gdp_growth"])

    def test_imputation_and_scaling_are_fitted_only_to_training_values(self):
        train = pd.DataFrame({"gdp_growth": [0.0, 2.0, np.nan], "state": list(STATES),
                              "country_code": ["ARG"] * 3, "target_state": list(STATES)})
        fitted = models.fit_model(train, "sentinel", numeric_columns=["gdp_growth"])
        numeric = fitted["estimator"].named_steps["preprocess"].named_transformers_["numeric"]
        self.assertEqual(numeric.named_steps["impute"].statistics_[0], 1.0)
        self.assertAlmostEqual(numeric.named_steps["scale"].mean_[0], 1.0)
        self.assertAlmostEqual(numeric.named_steps["scale"].var_[0], 2 / 3)
        test = pd.DataFrame({"gdp_growth": [1e9, np.nan], "state": ["Left", "Right"],
                             "country_code": ["NEW", "ARG"]})
        before = numeric.named_steps["scale"].mean_.copy()
        probability = models.predict_probabilities(fitted, test)
        np.testing.assert_allclose(probability.sum(axis=1), 1)
        np.testing.assert_array_equal(numeric.named_steps["scale"].mean_, before)
        self.assertEqual(numeric.named_steps["impute"].statistics_[0], 1.0)

    def test_all_missing_training_predictor_does_not_discard_test_rows(self):
        train = model_fixture().iloc[:15].copy()
        train["enso_mean"] = np.nan
        fitted = models.fit_model(train, "missing_climate", numeric_columns=["enso_mean"])
        test = model_fixture().iloc[-3:].copy()
        test.loc[test.index[0], "enso_mean"] = np.nan
        probability = models.predict_probabilities(fitted, test)
        self.assertEqual(probability.shape, (3, 3))
        self.assertTrue(np.isfinite(probability).all())
        np.testing.assert_allclose(probability.sum(axis=1), 1)
        numeric = fitted["estimator"].named_steps["preprocess"].named_transformers_["numeric"]
        self.assertEqual(numeric.named_steps["impute"].statistics_[0], 0)

    def test_absent_training_class_has_zero_probability_in_fixed_label_order(self):
        train = model_fixture()
        train = train.loc[train.target_state != "Center"]
        fitted = models.fit_model(train, "two_classes", numeric_columns=["gdp_growth"])
        test = model_fixture().iloc[-3:].copy()
        test["country_code"] = "UNSEEN"
        probability = models.predict_probabilities(fitted, test)
        np.testing.assert_array_equal(probability[:, STATES.index("Center")], 0)
        np.testing.assert_allclose(probability.sum(axis=1), 1)
        self.assertEqual(probability.shape, (3, 3))

    def test_local_rolling_models_share_cases_and_obey_origin_target_dates(self):
        panel = model_fixture()
        specs = {"lean": ["gdp_growth", "inflation"], "lean_enso": ["gdp_growth", "inflation", "enso_mean"]}
        predictions, metrics, folds = models.rolling_evaluate(panel, start_year=2005, model_features=specs)
        self.assertEqual(list(predictions.model.unique()), ["persistence", "markov", "lean", "lean_enso"])
        support = set(zip(panel.loc[panel.year >= 2005, "country_code"], panel.loc[panel.year >= 2005, "year"]))
        for name, frame in predictions.groupby("model"):
            with self.subTest(model=name):
                self.assertEqual(set(zip(frame.country_code, frame.year)), support)
                self.assertFalse(frame.duplicated(["country_code", "year"]).any())
                self.assertTrue(frame.train_max_origin.lt(frame.year).all())
                self.assertTrue(frame.train_max_target.le(frame.year).all())
                self.assertTrue(frame.target_year.eq(frame.year + 1).all())
        self.assertTrue(metrics.loc[metrics.subset == "all", "n"].eq(len(support)).all())
        self.assertTrue(folds.groupby("origin_year").train_n.nunique().eq(1).all())

    def test_training_target_after_origin_is_rejected(self):
        panel = model_fixture()
        panel.loc[(panel.country_code == "ARG") & (panel.year == 2004), "target_year"] = 2007
        with self.assertRaisesRegex(AssertionError, "Temporal leakage"):
            models.rolling_evaluate(panel, start_year=2005, model_features={"lean": ["gdp_growth"]})

    def test_original_default_predictions_are_unchanged_after_extension_evaluation(self):
        panel = model_fixture()
        order, registry = list(models.MODEL_ORDER), deepcopy(models.MODEL_FEATURES)
        original = models.rolling_evaluate(panel, start_year=2007)
        models.rolling_evaluate(panel, start_year=2007, model_features=drivers.model_specs())
        repeated = models.rolling_evaluate(panel, start_year=2007)
        for before, after in zip(original, repeated):
            pd.testing.assert_frame_equal(before, after)
        self.assertEqual(models.MODEL_ORDER, order)
        self.assertEqual(models.MODEL_FEATURES, registry)


if __name__ == "__main__":
    unittest.main()
