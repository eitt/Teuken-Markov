"""Reconcile publication evidence against frozen outputs, without fitting models.

These checks use stored public-source observations and original simulation
draws. They guard denominators, dates and the distinction between observed
cases, repeated model predictions, and conditional Monte Carlo uncertainty.
"""
from __future__ import annotations

from pathlib import Path
import sys
import unittest

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from americas_markov import STATES
from americas_markov.geographic import load_americas_geojson
from americas_markov.network import COUNTRY_METADATA
from americas_markov.publication_charts import oil_probability_contrasts
from americas_markov.publication_maps import state_table, transition_table


class FrozenPublicationEvidence(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.predictions = pd.read_csv(ROOT / "outputs/extensions/dpi_drivers/predictions.csv")
        cls.scenarios = pd.read_csv(ROOT / "outputs/extensions/dpi_drivers/conditional_oil_scenarios.csv")

    def test_six_models_repeat_the_same_1007_observed_cases(self):
        predictions = self.predictions
        self.assertEqual(len(predictions), 6042)
        self.assertEqual(predictions.model.nunique(), 6)
        self.assertFalse(predictions.duplicated(["country_code", "year", "model"]).any())
        reference = predictions.loc[predictions.model.eq("markov")].set_index(["country_code", "year"])
        self.assertEqual(len(reference), 1007)
        self.assertEqual(int(reference.changed.sum()), 93)
        self.assertEqual((reference.index.get_level_values("year").min(),
                          reference.index.get_level_values("year").max()), (1985, 2022))
        for model, frame in predictions.groupby("model"):
            with self.subTest(model=model):
                actual = frame.set_index(["country_code", "year"]).sort_index()
                pd.testing.assert_frame_equal(actual[["state", "target_state", "target_year", "changed"]],
                                              reference.sort_index()[["state", "target_state", "target_year", "changed"]])
                self.assertTrue(frame.target_year.eq(frame.year + 1).all())
                self.assertTrue(frame.train_max_origin.lt(frame.year).all())
                self.assertTrue(frame.train_max_target.le(frame.year).all())
        rates, pairs = transition_table(predictions)
        self.assertEqual(len(rates), 35)
        self.assertEqual((int(rates.n_pairs.sum()), int(rates.n_changes.sum())), (1007, 93))
        self.assertEqual(len(pairs), 1007)

    def test_evaluation_periods_partition_cases_without_counting_models_twice(self):
        cases = self.predictions.loc[self.predictions.model.eq("markov")]
        early = cases.loc[cases.year < 2000]
        late = cases.loc[cases.year >= 2000]
        self.assertEqual((len(early), int(early.changed.sum())), (403, 33))
        self.assertEqual((len(late), int(late.changed.sum())), (604, 60))
        self.assertEqual(len(early) + len(late), len(cases))
        self.assertEqual(int(early.changed.sum() + late.changed.sum()), 93)

    def test_primary_source_disagreement_uses_joint_classification_and_adjacent_dates(self):
        comparison = pd.read_csv(ROOT / "outputs/history/dpi_gli_hog_aligned_comparison.csv")
        self.assertEqual((len(comparison), comparison.country_code.nunique()), (1645, 35))
        self.assertFalse(comparison.duplicated(["country_code", "year"]).any())
        self.assertEqual((comparison.year.min(), comparison.year.max()), (1975, 2021))
        known = comparison.dpi_state.isin(STATES) & comparison.gli_state.isin(STATES)
        self.assertEqual(int(known.sum()), 1019)
        self.assertTrue(comparison.both_classified.eq(known).all())
        disagreement = known & comparison.dpi_state.ne(comparison.gli_state)
        self.assertEqual(int(disagreement.sum()), 230)
        self.assertTrue(comparison.loc[known, "disagree"].eq(disagreement.loc[known]).all())
        # Disagreement is undefined when either ideology is unavailable.
        self.assertTrue(comparison.loc[~known, "disagree"].isna().all())
        recorded = comparison.loc[comparison.source_year.notna()]
        self.assertTrue(recorded.year.eq(recorded.source_year + 1).all())
        source_dates = pd.to_datetime(recorded.gli_observation_date)
        aligned_dates = pd.to_datetime(recorded.gli_aligned_date)
        self.assertTrue(aligned_dates.sub(source_dates).eq(pd.Timedelta(days=1)).all())
        self.assertTrue(aligned_dates.eq(pd.to_datetime(recorded.dpi_observation_date)).all())

    def test_fixed_35_country_coverage_distinguishes_absent_and_unclassified(self):
        dpi = pd.read_csv(ROOT / "data/processed/dpi_americas.csv")
        states = state_table(dpi).set_index("country_code")
        self.assertEqual(set(states.index), set(COUNTRY_METADATA))
        self.assertEqual(states.map_state.value_counts().to_dict(),
                         {"Left": 18, "Right": 10, "NoDPI": 4, "Center": 2, "Unknown": 1})
        self.assertEqual(states.loc["CAN", "map_state"], "Right")
        self.assertEqual(states.loc["PAN", "map_state"], "Unknown")
        self.assertEqual(states.loc["HTI", "map_state"], "Center")
        self.assertEqual(set(states.index[states.map_state.eq("NoDPI")]), {"ATG", "DMA", "KNA", "VCT"})
        for role, classified_countries in [("hog", 27), ("leader", 29)]:
            coverage = pd.read_csv(ROOT / f"outputs/history/gli_{role}_coverage_35_countries.csv")
            self.assertEqual(set(coverage.country_code), set(COUNTRY_METADATA))
            self.assertEqual(len(coverage), 35)
            self.assertEqual(int(coverage.classified_rows.gt(0).sum()), classified_countries)

    def test_real_map_units_never_inherit_sovereign_parent_observations(self):
        document = load_americas_geojson(ROOT)
        national = [f for f in document["features"] if f["properties"]["IS_MODEL_COUNTRY"]]
        context = [f for f in document["features"] if not f["properties"]["IS_MODEL_COUNTRY"]]
        self.assertEqual((len(document["features"]), len(national), len(context)), (56, 36, 20))
        self.assertEqual({f["properties"]["MODEL_ISO3"] for f in national}, set(COUNTRY_METADATA))
        self.assertTrue(all(f["properties"]["MODEL_ISO3"] is None for f in context))
        self.assertTrue(all(f["properties"]["MODEL_ISO3"] == f["properties"]["ISO_A3_EH"] for f in national))
        self.assertEqual(sum(f["properties"]["MODEL_ISO3"] == "ATG" for f in national), 2)
        contexts = {f["properties"]["ISO_A3_EH"] for f in context}
        self.assertTrue({"PRI", "VIR", "GUF", "GLP", "MTQ"}.issubset(contexts))

    def test_optional_driver_dates_and_products_match_frozen_panel(self):
        panel = pd.read_csv(ROOT / "outputs/extensions/dpi_drivers/transition_panel.csv")
        self.assertEqual((len(panel), int(panel.changed.sum())), (1207, 108))
        self.assertTrue(panel.economic_year.eq(panel.year - 1).all())
        self.assertTrue(panel.climate_source_year.eq(panel.year - 1).all())
        self.assertTrue(panel.exposure_source_year.eq(panel.year - 2).all())
        np.testing.assert_allclose(panel.oil_x_import_prior, panel.oil_growth * panel.fuel_import_share_prior / 100,
                                   equal_nan=True)
        np.testing.assert_allclose(panel.oil_x_export_prior, panel.oil_growth * panel.fuel_export_share_prior / 100,
                                   equal_nan=True)
        np.testing.assert_allclose(panel.enso_x_agriculture_prior, panel.enso_mean * panel.agriculture_share_prior / 100,
                                   equal_nan=True)

    def test_oil_contrast_is_country_paired_probability_point_difference(self):
        scenarios = self.scenarios
        self.assertEqual((len(scenarios), scenarios.country_code.nunique()), (90, 30))
        self.assertEqual(set(scenarios.scenario_oil_growth), {-50, 0, 50})
        self.assertTrue(scenarios.year.eq(2023).all())
        self.assertFalse(scenarios.duplicated(["country_code", "year", "scenario_oil_growth"]).any())
        for column in ["state", "fuel_import_share_prior", "fuel_export_share_prior"]:
            self.assertTrue(scenarios.groupby("country_code")[column].nunique(dropna=False).eq(1).all())
        contrasts = oil_probability_contrasts(scenarios)
        self.assertEqual(len(contrasts), 60)
        for row in contrasts.itertuples():
            base = scenarios.loc[scenarios.country_code.eq(row.country_code) & scenarios.scenario_oil_growth.eq(0)].iloc[0]
            scenario = scenarios.loc[scenarios.country_code.eq(row.country_code) &
                                     scenarios.scenario_oil_growth.eq(row.scenario_oil_growth)].iloc[0]
            column = {"Left": "p_left", "Center": "p_center", "Right": "p_right"}[row.state]
            expected_pp = 100 * (base[column] - scenario[column])
            self.assertAlmostEqual(row.delta_change_pp, expected_pp, places=10)

    def test_simulation_bands_reconcile_to_500_fixed_parameter_draws(self):
        summary = pd.read_csv(ROOT / "outputs/main/escenarios_resumen.csv")
        self.assertEqual(len(summary), 63)
        self.assertTrue(summary.runs.eq(500).all())
        self.assertTrue(summary.active_countries.eq(30).all())
        for path in sorted((ROOT / "outputs/main").glob("escenario_*.csv.gz")):
            draws = pd.read_csv(path)
            with self.subTest(scenario=path.name):
                self.assertEqual((len(draws), draws.path.nunique(), draws.country_code.nunique()), (105000, 500, 30))
                self.assertEqual(set(draws.year), set(range(2023, 2030)))
                self.assertFalse(draws.duplicated(["path", "year", "country_code"]).any())
                self.assertTrue(draws.initial_observed.eq(draws.year.eq(2023)).all())
                self.assertTrue(draws.groupby(["path", "year"]).country_code.nunique().eq(30).all())
                index = pd.MultiIndex.from_product([range(500), range(2023, 2030), STATES],
                                                   names=["path", "year", "state"])
                counts = draws.groupby(["path", "year", "state"]).size().reindex(index, fill_value=0)
                scenario = draws.scenario.iloc[0]
                reported = summary.loc[summary.scenario.eq(scenario)].set_index(["year", "state"])
                for year in range(2023, 2030):
                    for state in STATES:
                        values = counts.xs((year, state), level=["year", "state"]).to_numpy()
                        row = reported.loc[(year, state)]
                        self.assertAlmostEqual(row.mean_countries, values.mean(), places=10)
                        np.testing.assert_allclose([row.q05, row.q95], np.quantile(values, [.05, .95]))
                initial = reported.loc[2023].mean_countries.to_dict()
                self.assertEqual(initial, {"Left": 18.0, "Center": 2.0, "Right": 10.0})

    def test_stored_brier_scores_and_change_probabilities_reconcile(self):
        metrics = pd.read_csv(ROOT / "outputs/extensions/dpi_drivers/metrics.csv")
        for name, frame in self.predictions.groupby("model"):
            with self.subTest(model=name):
                probability = frame[["p_left", "p_center", "p_right"]].to_numpy()
                truth = np.column_stack([frame.target_state.eq(s) for s in STATES])
                np.testing.assert_allclose(probability.sum(axis=1), 1)
                self.assertTrue(np.isfinite(probability).all())
                self.assertTrue((probability >= 0).all())
                current = np.array([STATES.index(s) for s in frame.state])
                risk = 1 - probability[np.arange(len(frame)), current]
                np.testing.assert_allclose(frame.p_change, risk, atol=1e-14)
                row = metrics.loc[metrics.model.eq(name) & metrics.subset.eq("all")].iloc[0]
                self.assertEqual((int(row.n), int(row.changes)), (1007, 93))
                self.assertAlmostEqual(row.brier_multiclass, ((probability - truth) ** 2).sum(axis=1).mean(), places=10)
                self.assertAlmostEqual(row.brier_change, ((risk - frame.changed.to_numpy()) ** 2).mean(), places=10)


if __name__ == "__main__":
    unittest.main()
