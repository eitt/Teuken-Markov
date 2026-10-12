"""Audit publication denominators, labels and preservation of frozen inputs."""
from hashlib import sha256
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import numpy as np
import pandas as pd

from americas_markov.publication_tables import (
    DPI_MODELS, _disagreement, _human_export, _validated_predictions,
    build_tables, rerender_cached_reports,
)


ROOT = Path(__file__).resolve().parents[1]
FROZEN = ROOT / "outputs/extensions/dpi_drivers/predictions.csv"


def _prediction_fixture():
    cases = pd.DataFrame({"country_code": ["ARG", "BRA"], "year": [1999, 2000],
                          "target_year": [2000, 2001], "state": ["Left", "Right"],
                          "target_state": ["Right", "Right"], "changed": [True, False],
                          "predicted_state": ["Right", "Right"]})
    return pd.concat([cases.assign(model=name) for name in ["persistence", "markov"]], ignore_index=True)


class PublicationTableIntegrityTests(unittest.TestCase):
    def test_duplicate_predictions_and_unequal_model_samples_are_rejected(self):
        data = _prediction_fixture()
        with self.assertRaisesRegex(ValueError, "Duplicate"):
            _validated_predictions(pd.concat([data, data.iloc[[0]]]), ["persistence", "markov"])
        with self.assertRaisesRegex(ValueError, "same country-origin"):
            _validated_predictions(data.iloc[:-1], ["persistence", "markov"])

    def test_source_identifiers_survive_english_display_export(self):
        original = pd.DataFrame({"country_code": ["ATG"], "country_name": ["Antigua & Barbuda"],
                                 "model": ["network_shocks"], "scenario": ["recesion_hipotetica"],
                                 "state": ["Left"], "year": [2025], "mean_countries": [0.123456789012345]})
        result = _human_export(original)
        self.assertEqual(result.loc[0, "Country"], "Antigua and Barbuda")
        self.assertEqual(result.loc[0, "Model"], "Domestic + network + shocks")
        self.assertEqual(result.loc[0, "Model ID"], "network_shocks")
        self.assertEqual(result.loc[0, "Scenario"], "Hypothetical recession")
        self.assertEqual(result.loc[0, "Scenario ID"], "recesion_hipotetica")
        self.assertEqual(result.loc[0, "Mean countries"], original.loc[0, "mean_countries"])
        self.assertIn("Simulated year", result)
        self.assertIn("Simulated state", result)
        self.assertEqual(original.loc[0, "country_name"], "Antigua & Barbuda")

    @unittest.skipUnless(FROZEN.is_file(), "Frozen analysis outputs are required for the publication audit")
    def test_frozen_table_values_and_source_files_remain_intact(self):
        sources = [ROOT / "outputs/extensions/dpi_drivers/metrics_by_period.csv", FROZEN,
                   ROOT / "outputs/extensions/gli_hog/predictions.csv", ROOT / "data/processed/dpi_americas.csv"]
        before = {path: sha256(path.read_bytes()).hexdigest() for path in sources}
        with tempfile.TemporaryDirectory() as name:
            folder = Path(name)
            tables = build_tables(ROOT, folder)
            self.assertEqual(len(tables), 6)
            self.assertEqual([table["row_count"] for table in tables], [8, 35, 36, 18, 4, 12])
            for table in tables:
                self.assertEqual(pd.read_csv(table["csv"]).columns.tolist(), table["columns"])
                self.assertTrue(Path(table["markdown"]).is_file())
                self.assertEqual(table["language"], "English")
            membership = pd.read_csv(tables[1]["csv"]).set_index("Country code")
            self.assertEqual(membership.loc["PAN", "DPI state"], "Unknown")
            self.assertEqual(set(membership.loc[membership["DPI state"].eq("No DPI")].index), {"ATG", "DMA", "KNA", "VCT"})
            self.assertEqual(membership["DPI state"].value_counts().to_dict(),
                             {"Left": 18, "Right": 10, "No DPI": 4, "Center": 2, "Unknown": 1})
            disagreement = pd.read_csv(tables[2]["csv"]).set_index("Country code")
            self.assertTrue(np.isnan(disagreement.loc["ATG", "HOG disagreement (%)"]))
            self.assertEqual(disagreement.loc["ALL", "HOG paired records"], 1019)
            self.assertEqual(disagreement.loc["ALL", "HOG disagreements"], 230)
            self.assertAlmostEqual(disagreement.loc["ALL", "HOG disagreement (%)"], 230 / 1019 * 100)
            self.assertEqual(disagreement.loc["ALL", "Leader paired records"], 1109)
            self.assertEqual(disagreement.loc["ALL", "Leader disagreements"], 279)
            performance = pd.read_csv(tables[3]["csv"])
            periods = performance["Evaluation period"].drop_duplicates().tolist()
            for period, cases, changes, lean_hits in zip(periods, [1007, 403, 604], [93, 33, 60], [2, 2, 0]):
                block = performance.loc[performance["Evaluation period"].eq(period)]
                self.assertEqual(len(block), len(DPI_MODELS))
                self.assertEqual(block.Cases.unique().tolist(), [cases])
                self.assertEqual(block["Observed changes"].unique().tolist(), [changes])
                self.assertEqual(block["Correct change predictions"].tolist(), [0, 0, *[lean_hits] * 4])
            raw = pd.read_csv(ROOT / "outputs/extensions/dpi_drivers/metrics_by_period.csv")
            selected = raw.loc[raw.subset.eq("all")].set_index(["period", "model"])
            expected = [selected.loc[(period, model), "brier_multiclass"]
                        for period in ["all", "pre2000", "2000plus"] for model in DPI_MODELS]
            np.testing.assert_allclose(performance["Brier score"], expected, rtol=0, atol=1e-15)
            gli = pd.read_csv(tables[4]["csv"])
            self.assertEqual(gli.Cases.unique().tolist(), [1677])
            self.assertEqual(gli["Observed changes"].unique().tolist(), [167])
            self.assertEqual(gli["Correct change predictions"].tolist(), [0, 0, 0, 0])
            complete = pd.read_csv(folder / "complete/main/Scenario_summary.csv")
            self.assertEqual(set(complete["Scenario"]), {"Constant conditions", "Hypothetical recession", "Hypothetical energy and food shock"})
            self.assertIn("Scenario ID", complete)
            self.assertIn("Change-risk ROC AUC", pd.read_csv(folder / "complete/DPI_driver_metrics_by_period.csv"))
        self.assertEqual(before, {path: sha256(path.read_bytes()).hexdigest() for path in sources})

    def test_cached_rerender_restores_original_csv_and_info_bytes(self):
        with tempfile.TemporaryDirectory() as name:
            root = Path(name)
            (root / "data/processed").mkdir(parents=True)
            pd.DataFrame({"country_code": ["ARG"], "year": [2023], "state": ["Left"]}).to_csv(root / "data/processed/dpi_americas.csv", index=False)
            folder = root / "outputs/competitive_only"
            folder.mkdir(parents=True)
            for filename in ["predicciones_fuera_muestra.csv", "metricas.csv", "metricas_por_ano.csv", "panel_transiciones.csv"]:
                pd.DataFrame({"example": [1]}).to_csv(folder / filename, index=False)
            pd.DataFrame({"ARG": [0]}, index=["ARG"]).to_csv(folder / "pesos_red_2016.csv")
            (folder / "run_info.json").write_bytes(b'{"countries":1}\n')
            (folder / "escenarios_resumen.csv").write_bytes(b"scenario,state,year,mean_countries\ncondiciones_constantes,Left,2023,1.0000000000000000\n")
            (folder / "calibracion.csv").write_bytes(b"mean_predicted\n0.12345678901234500\n")
            before = {path: path.read_bytes() for path in folder.iterdir()}

            def render(*args):
                target = args[-2]
                (target / "escenarios_resumen.csv").write_text("rounded data\n")
                (target / "calibracion.csv").write_text("rounded data\n")
                (target / "run_info.json").write_text("{}")
                (target / "RESULTADOS.txt").write_text("English cached report\n")

            with patch("americas_markov.publication_tables.render_results", side_effect=render) as mocked:
                result = rerender_cached_reports(root)
            self.assertEqual(mocked.call_count, 1)
            self.assertEqual(result[0]["language"], "English")
            for path, payload in before.items():
                self.assertEqual(path.read_bytes(), payload)
            self.assertEqual((folder / "RESULTADOS.txt").read_text(), "English cached report\n")


if __name__ == "__main__":
    unittest.main()
