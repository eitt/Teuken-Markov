"""Temporal alignment and measurement integrity of separate historical inputs."""

from hashlib import sha256
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

import pandas as pd

from americas_markov import history
from americas_markov.data import DataSourceError


def fixture(rows):
    records = []
    for values in rows:
        record = {
            "country_name": "Argentina", "country_code_cow": "160", "year": "1945",
            "hog": "Executive A", "hog_ideology": "leftist", "hog_party": "Party A",
            "hog_party_id": "17", "hog_party_abbr": "PA", "hog_title": "President",
            "leader": "Leader B", "leader_ideology": "rightist", "leader_party": "Party B",
            "leader_party_id": "18", "leader_party_abbr": "PB", "leader_position": "President",
        }
        record.update(values)
        records.append(record)
    return pd.DataFrame(records)


def write_verified_gli(root, frame):
    raw = Path(root) / "data/raw"
    raw.mkdir(parents=True)
    path = raw / "global_leader_ideologies.csv"
    frame.to_csv(path, index=False)
    manifest = {"sources": {"gli_sensitivity": {
        "raw_path": "data/raw/global_leader_ideologies.csv", "sha256": sha256(path.read_bytes()).hexdigest(),
    }}}
    (raw / "download_manifest.json").write_text(json.dumps(manifest))


class HistoricalIntegrity(unittest.TestCase):
    def test_actual_source_date_is_retained_and_shifted_exactly_once(self):
        result = history._normalize_gli(fixture([{"year": "1945"}, {"year": "2020"}]), "hog")
        self.assertEqual(result.source_year.tolist(), [1945, 2020])
        self.assertEqual(result.year.tolist(), [1946, 2021])
        self.assertEqual(result.observation_date.tolist(), ["1945-12-31", "2020-12-31"])
        self.assertEqual(result.aligned_date.tolist(), ["1946-01-01", "2021-01-01"])

    def test_role_choice_is_explicit_and_missing_hog_never_falls_back(self):
        frame = fixture([{"hog": "", "hog_ideology": "not applicable"}])
        hog = history._normalize_gli(frame, "hog")
        leader = history._normalize_gli(frame, "leader")
        self.assertTrue(hog.state.isna().all())
        self.assertFalse(hog.role_present.any())
        self.assertEqual(leader.state.iloc[0], "Right")
        with self.assertRaisesRegex(ValueError, "no automatic role fallback"):
            history._normalize_gli(frame, "prefer_hog_else_leader")

    def test_all_unknown_categories_remain_unclassified(self):
        frame = fixture([{"year": str(1945 + i), "hog_ideology": value}
                         for i, value in enumerate(["none", "no information", "not applicable", ""])])
        result = history._normalize_gli(frame, "hog")
        self.assertTrue(result.state.isna().all())
        self.assertEqual(result.ideology_raw.tolist(), ["none", "no information", "not applicable", ""])
        self.assertTrue(result.state_duration.isna().all())

    def test_cow_crosswalk_is_not_confused_with_iso_abbreviations(self):
        frame = fixture([{"country_name": "Haiti", "country_code_cow": "41"}])
        result = history._normalize_gli(frame, "hog")
        self.assertEqual(result.country_code.iloc[0], "HTI")

    def test_fractional_timestamp_future_and_duplicate_records_fail(self):
        for year in ["1945.5", "1945-12-31", "2021"]:
            with self.subTest(year=year), self.assertRaises(DataSourceError):
                history._normalize_gli(fixture([{"year": year}]), "hog")
        with self.assertRaisesRegex(DataSourceError, "duplicate"):
            history._normalize_gli(fixture([{}, {}]), "hog")

    def test_unexpected_ideology_is_not_implicitly_recoded(self):
        with self.assertRaisesRegex(DataSourceError, "Unexpected GLI"):
            history._normalize_gli(fixture([{"hog_ideology": "progressive"}]), "hog")

    def test_exact_office_elections_and_competitiveness_are_not_invented(self):
        result = history._normalize_gli(fixture([{}]), "hog")
        for field in ["eiec", "election_held", "system", "years_in_office"]:
            self.assertTrue(result[field].isna().all(), field)

    def test_snapshot_runs_reset_at_missing_state_and_nonconsecutive_years(self):
        frame = fixture([
            {"year": "1945"}, {"year": "1946"},
            {"year": "1947", "hog_ideology": "no information"},
            {"year": "1948"}, {"year": "1950"},
        ])
        result = history._normalize_gli(frame, "hog")
        self.assertEqual(result.state_duration.iloc[:2].tolist(), [1.0, 2.0])
        self.assertTrue(pd.isna(result.state_duration.iloc[2]))
        self.assertEqual(result.state_duration.iloc[3:].tolist(), [1.0, 1.0])
        self.assertEqual(result.leader_snapshot_duration.tolist(), [1.0, 2.0, 3.0, 4.0, 1.0])

    def test_party_none_is_preserved_without_manufacturing_a_party_run(self):
        frame = fixture([{"hog_party": "none", "hog_party_id": ""},
                         {"year": "1946", "hog_party": "none", "hog_party_id": ""}])
        result = history._normalize_gli(frame, "hog")
        self.assertEqual(result.executive_party.tolist(), ["none", "none"])
        self.assertTrue(result.party_snapshot_duration.isna().all())

    def test_future_records_do_not_rewrite_earlier_durations(self):
        frame = fixture([{"year": "1945"}, {"year": "1946"}, {"year": "1947"}])
        before = history._normalize_gli(frame, "hog")
        frame.loc[2, ["hog", "hog_ideology", "hog_party", "hog_party_id"]] = ["Other", "rightist", "Party Z", "99"]
        after = history._normalize_gli(frame, "hog")
        pd.testing.assert_frame_equal(before.iloc[:2], after.iloc[:2])

    def test_public_loader_requires_verified_hash_and_does_not_assume_eligibility(self):
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            write_verified_gli(root, fixture([{}]))
            result = history.load_gli(root)
            self.assertTrue(result.eligible_cow_jan1.isna().all())
            self.assertFalse(result.attrs["cow_membership_available"])
            path = root / "data/raw/global_leader_ideologies.csv"
            path.write_text(path.read_text() + "\n")
            with self.assertRaisesRegex(DataSourceError, "hash"):
                history.load_gli(root)

    def test_comparison_uses_previous_december_not_same_source_year(self):
        gli = history._normalize_gli(fixture([{"year": "2000", "hog_ideology": "rightist"},
                                             {"year": "2001", "hog_ideology": "leftist"}]), "hog")
        gli["eligible_cow_jan1"] = True
        dpi = pd.DataFrame({"country_code": ["ARG"], "year": [2001], "state": ["Right"],
                            "ideology_raw": ["Right"], "executive_party": ["Party A"]})
        comparison = history._comparison(dpi, gli)
        arg = comparison.loc[comparison.country_code.eq("ARG")].iloc[0]
        self.assertEqual(arg.gli_observation_date, "2000-12-31")
        self.assertEqual(arg.dpi_observation_date, "2001-01-01")
        self.assertEqual(arg.comparison_status, "both_known_agree")
        self.assertEqual(len(comparison), 35)

    def test_absence_and_unknown_are_distinct_and_denominator_conditions_on_known(self):
        gli = history._normalize_gli(fixture([{"year": "2000", "hog_ideology": "none"}]), "hog")
        gli["eligible_cow_jan1"] = True
        dpi = pd.DataFrame({"country_code": ["ARG"], "year": [2001], "state": ["Center"],
                            "ideology_raw": ["Center"], "executive_party": ["Party A"]})
        comparison = history._comparison(dpi, gli).set_index("country_code")
        self.assertTrue(comparison.loc["ARG", "gli_record_present"])
        self.assertFalse(comparison.loc["BRA", "gli_record_present"])
        self.assertFalse(comparison.both_classified.any())
        self.assertTrue(comparison.disagree.isna().all())

    def test_report_writes_only_history_and_conditions_disagreement_denominator(self):
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            write_verified_gli(root, fixture([
                {"year": "2000", "hog_ideology": "rightist"},
                {"year": "2001", "hog_ideology": "none"},
            ]))
            original = root / "outputs/main/metricas.csv"
            original.parent.mkdir(parents=True)
            original.write_text("unchanged original metrics\n")
            dpi = pd.DataFrame({
                "country_code": ["ARG", "ARG"], "year": [2001, 2002],
                "state": ["Left", "Center"], "ideology_raw": ["Left", "Center"],
                "executive_party": ["Party X", "Party Y"],
            })
            dpi_path = root / "data/raw/dpi2023.csv"
            dpi.to_csv(dpi_path, index=False)
            manifest_path = root / "data/raw/download_manifest.json"
            manifest = json.loads(manifest_path.read_text())
            manifest["sources"]["dpi2023"] = {
                "raw_path": "data/raw/dpi2023.csv", "sha256": sha256(dpi_path.read_bytes()).hexdigest(),
            }
            manifest_path.write_text(json.dumps(manifest))
            with patch("americas_markov.history.load_politics", return_value=dpi):
                report = history.history_report(root)
            self.assertEqual(report["roles"]["hog"]["jointly_classified"], 1)
            self.assertEqual(report["roles"]["hog"]["disagreements"], 1)
            self.assertEqual(report["roles"]["hog"]["disagreement_rate"], 1.0)
            self.assertEqual(original.read_text(), "unchanged original metrics\n")
            self.assertTrue(all(path.startswith("outputs/history/") for path in report["files"]))
            coverage = pd.read_csv(root / "outputs/history/gli_hog_coverage_35_countries.csv")
            self.assertEqual(len(coverage), 35)
            self.assertEqual(int(coverage.source_rows.sum()), 2)


class CachedHistoricalSource(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.root = Path(__file__).resolve().parents[1]
        if not (cls.root / "data/raw/global_leader_ideologies.csv").exists():
            raise unittest.SkipTest("Verified GLI cache not supplied")
        cls.hog = history.load_gli(cls.root)
        cls.leader = history.load_gli(cls.root, role="leader")

    def test_verified_release_coverage_and_explicit_role_differences(self):
        self.assertEqual((len(self.hog), self.hog.country_code.nunique()), (2060, 29))
        self.assertEqual((self.hog.source_year.min(), self.hog.source_year.max()), (1945, 2020))
        self.assertEqual((self.hog.year.min(), self.hog.year.max()), (1946, 2021))
        self.assertEqual(int(self.hog.state.isin(history.STATES).sum()), 1932)
        self.assertEqual(int(self.leader.state.isin(history.STATES).sum()), 2047)
        self.assertTrue(self.hog.loc[self.hog.country_code.isin(["BHS", "BLZ"]), "state"].isna().all())
        self.assertEqual(set(self.hog.attrs["missing_series"]), {"ATG", "DMA", "GRD", "KNA", "LCA", "VCT"})

    def test_existing_transition_interface_never_invents_competitiveness(self):
        from americas_markov.features import make_transition_panel
        panel = make_transition_panel(self.hog)
        self.assertGreater(len(panel), 0)
        self.assertEqual(int(panel.year.max()), 2020)
        self.assertEqual(int(panel.target_year.max()), 2021)
        self.assertTrue(panel.target_year.eq(panel.year + 1).all())
        self.assertEqual(len(make_transition_panel(self.hog, competitive_only=True)), 0)

    def test_canada_terminal_observation_remains_2020_not_a_new_2021_source(self):
        row = self.hog.loc[self.hog.country_code.eq("CAN") & self.hog.source_year.eq(2020)].iloc[0]
        self.assertEqual(row.state, "Left")
        self.assertEqual(row.year, 2021)
        self.assertEqual(row.observation_date, "2020-12-31")
        self.assertEqual(row.aligned_date, "2021-01-01")


if __name__ == "__main__":
    unittest.main()
