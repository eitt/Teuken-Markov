"""Compatibility of archived outputs and English scenario identifiers."""
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

import numpy as np
import pandas as pd

from americas_markov.artifacts import SCENARIO_ALIASES, read_artifact_csv, resolve_artifact
from americas_markov.publication_charts import _csv
from americas_markov.publication_tables import _human_export
from americas_markov.simulation import simulate, SCENARIOS


class EnglishOutputCompatibility(unittest.TestCase):
    def test_english_file_wins_when_both_names_exist(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "metricas.csv").write_text("n\n1\n")
            (root / "metrics.csv").write_text("n\n2\n")
            self.assertEqual(resolve_artifact(root / "metrics.csv"), root / "metrics.csv")
            self.assertEqual(read_artifact_csv(root / "metrics.csv").n.tolist(), [2])

    def test_archived_figure_inputs_remain_readable_without_mutation(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            path = root / "escenarios_resumen.csv"
            payload = b"scenario,mean_countries\nrecesion_hipotetica,1.23456789012345\n"
            path.write_bytes(payload)
            frame = _csv(root, "scenario_summary.csv", ["scenario", "mean_countries"])
            self.assertEqual(frame.scenario.tolist(), ["hypothetical_recession"])
            self.assertEqual(frame.mean_countries.iloc[0], 1.23456789012345)
            self.assertEqual(path.read_bytes(), payload)
            self.assertFalse((root / "scenario_summary.csv").exists())

    def test_presentation_export_uses_english_ids_for_archived_labels(self):
        original = pd.DataFrame({"scenario": list(SCENARIO_ALIASES), "mean_countries": [1.25, 2.5, 3.75]})
        export = _human_export(original)
        self.assertEqual(export["Scenario ID"].tolist(), list(SCENARIOS))
        self.assertEqual(export["Mean countries"].tolist(), original.mean_countries.tolist())
        self.assertEqual(original.scenario.tolist(), list(SCENARIO_ALIASES))

    def test_archived_and_canonical_scenarios_produce_identical_seeded_paths(self):
        initial = pd.DataFrame({"country_code": ["ARG", "BRA"], "year": [2023, 2023],
                                "state": ["Left", "Right"], "state_duration": [2, 3],
                                "world_growth": [3., 3.]})
        weights = pd.DataFrame([[0., 1.], [1., 0.]], index=["ARG", "BRA"], columns=["ARG", "BRA"])
        def probabilities(model, frame):
            return np.tile([.3, .2, .5], (len(frame), 1))
        with patch("americas_markov.simulation.predict_probabilities", side_effect=probabilities), \
             patch("americas_markov.simulation.shock_interactions", side_effect=lambda frame: frame):
            for archived, canonical in SCENARIO_ALIASES.items():
                with self.subTest(scenario=canonical):
                    old = simulate({}, initial, weights, horizon=3, runs=5, seed=17, scenario=archived)
                    new = simulate({}, initial, weights, horizon=3, runs=5, seed=17, scenario=canonical)
                    pd.testing.assert_frame_equal(old[0], new[0])
                    pd.testing.assert_frame_equal(old[1], new[1])
                    self.assertEqual(set(new[0].scenario), {canonical})


if __name__ == "__main__":
    unittest.main()
