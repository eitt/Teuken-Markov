"""Offline integrity tests for ENSO aggregation and source-year boundaries."""

from pathlib import Path
import json
import sys
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from americas_markov import climate


def oni_fixture(years, values=None, ndj_value=9999.0):
    """Sentinel fixture for boundary tests; never a research-data fallback."""
    values = list(range(11)) if values is None else values
    lines = ["SEAS YR TOTAL ANOM"]
    for year in years:
        lines.extend(f"{season} {year} 27.0 {value}" for season, value in zip(climate.INCLUDED_SEASONS, values))
        lines.append(f"NDJ {year} 27.0 {ndj_value}")
    return ("\n".join(lines) + "\n").encode()


def cache_fixture(root, content):
    folder = Path(root) / "data" / "raw"
    folder.mkdir(parents=True, exist_ok=True)
    (folder / climate.RAW_FILENAME).write_bytes(content)


class ClimateIntegrity(unittest.TestCase):
    def test_ndj_next_january_is_excluded_from_all_three_statistics(self):
        with TemporaryDirectory() as folder:
            cache_fixture(folder, oni_fixture([2000, 2001], list(range(-5, 6)), ndj_value=9999.0))
            annual = climate.load_climate(Path(folder))
            self.assertEqual(list(annual.columns), ["year", "enso_mean", "enso_abs_mean", "enso_max_abs"])
            self.assertTrue(np.allclose(annual.enso_mean, 0))
            self.assertTrue(np.allclose(annual.enso_abs_mean, 30 / 11))
            self.assertTrue(np.allclose(annual.enso_max_abs, 5))
            self.assertEqual(annual.attrs["included_seasons"], list(climate.INCLUDED_SEASONS))
            self.assertEqual(annual.attrs["excluded_seasons"], ["NDJ"])
            for year, max_event_year in annual.attrs["max_event_year_by_source_year"].items():
                self.assertLessEqual(max_event_year, year)
            # Changing only NDJ values must leave the preceding source-year
            # features unchanged, even though NDJ includes a future January.
            cache_fixture(folder, oni_fixture([2000, 2001], list(range(-5, 6)), ndj_value=-9999.0))
            changed = climate.load_climate(Path(folder))
            np.testing.assert_array_equal(annual.to_numpy(), changed.to_numpy())

    def test_historical_missing_window_cannot_be_silently_averaged(self):
        content = oni_fixture([2000, 2001]).decode()
        content = "\n".join(line for line in content.splitlines() if not line.startswith("MAM 2000"))
        with TemporaryDirectory() as folder:
            cache_fixture(folder, content.encode())
            with self.assertRaisesRegex(climate.ClimateDataError, "2000.*exactly 11"):
                climate.load_climate(Path(folder))

    def test_historical_nonfinite_window_cannot_be_silently_averaged(self):
        content = oni_fixture([2000, 2001]).replace(b"JFM 2000 27.0 1", b"JFM 2000 27.0 NaN")
        with TemporaryDirectory() as folder:
            cache_fixture(folder, content)
            with self.assertRaisesRegex(climate.ClimateDataError, "2000.*exactly 11"):
                climate.load_climate(Path(folder))

    def test_incomplete_terminal_year_is_explicitly_excluded(self):
        content = oni_fixture([2000]) + b"DJF 2001 27.0 1.0\nJFM 2001 27.0 2.0\n"
        with TemporaryDirectory() as folder:
            cache_fixture(folder, content)
            annual = climate.load_climate(Path(folder))
            self.assertEqual(annual.year.tolist(), [2000])
            self.assertEqual(annual.attrs["excluded_incomplete_terminal_years"], [2001])

    def test_missing_entire_internal_year_is_rejected(self):
        with TemporaryDirectory() as folder:
            cache_fixture(folder, oni_fixture([2000, 2002]))
            with self.assertRaisesRegex(climate.ClimateDataError, "2001"):
                climate.load_climate(Path(folder))

    def test_duplicate_window_and_roni_schema_are_rejected(self):
        for content in [oni_fixture([2000]) + b"DJF 2000 27.0 0\n", b"SEAS YR ANOM\nDJF 2000 1.0\n"]:
            with self.subTest(content=content[:40]), TemporaryDirectory() as folder:
                cache_fixture(folder, content)
                with self.assertRaises(climate.ClimateDataError):
                    climate.load_climate(Path(folder))

    def test_missing_input_does_not_trigger_implicit_download(self):
        with TemporaryDirectory() as folder, patch.object(climate, "urlopen", side_effect=AssertionError("network forbidden")):
            with self.assertRaisesRegex(climate.ClimateDataError, "explicitly"):
                climate.load_climate(Path(folder))

    def test_cache_download_and_loader_do_not_request_network(self):
        with TemporaryDirectory() as folder:
            cache_fixture(folder, oni_fixture([2000]))
            with patch.object(climate, "urlopen", side_effect=AssertionError("network forbidden")):
                first = climate.download_climate(Path(folder))
                second = climate.download_climate(Path(folder))
                climate.load_climate(Path(folder))
            a = first["sources"]["noaa_oni"]
            b = second["sources"]["noaa_oni"]
            self.assertTrue(a["cached"] and b["cached"])
            self.assertEqual(a["sha256"], b["sha256"])
            self.assertEqual(a["retrieved_at"], b["retrieved_at"])
            self.assertEqual(second["annual_coverage"]["complete_source_years"], 1)
            # Editing a cached source must be detected against the manifest.
            cache_fixture(folder, oni_fixture([2000], ndj_value=100.0))
            with self.assertRaisesRegex(climate.ClimateDataError, "SHA256"):
                climate.load_climate(Path(folder))

    def test_actual_cached_noaa_source_when_present(self):
        if not (ROOT / "data" / "raw" / climate.RAW_FILENAME).is_file():
            self.skipTest("No cached NOAA source supplied; this test never downloads it.")
        with patch.object(climate, "urlopen", side_effect=AssertionError("network forbidden")):
            annual = climate.load_climate(ROOT)
        self.assertLessEqual(int(annual.year.min()), 1960)
        self.assertGreaterEqual(int(annual.year.max()), 2023)
        self.assertTrue(annual.year.between(1960, 2023).sum() == 64)
        self.assertTrue(annual.enso_abs_mean.ge(annual.enso_mean.abs() - 1e-12).all())
        self.assertTrue(annual.enso_max_abs.ge(annual.enso_abs_mean - 1e-12).all())


if __name__ == "__main__":
    unittest.main()
