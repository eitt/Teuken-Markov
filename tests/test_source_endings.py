"""A checkout newline conversion must never weaken source-content verification."""
from hashlib import sha256
import json
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
import unittest
import warnings

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from americas_markov.data import _require_file, DataSourceError


class SourceEndings(unittest.TestCase):
    def fixture(self, root, payload, filename="dpi2023.csv"):
        raw = root / "data/raw"; raw.mkdir(parents=True)
        original = b"countryname,year,execrlc\r\nCanada,2023-01-01,Right\r\n"
        (raw / filename).write_bytes(payload)
        (raw / "download_manifest.json").write_text(json.dumps({"sources": {"source": {
            "raw_path": f"data/raw/{filename}", "sha256": sha256(original).hexdigest()}}}))

    def test_exact_original_and_lossless_git_lf_are_verified(self):
        original = b"countryname,year,execrlc\r\nCanada,2023-01-01,Right\r\n"
        for payload in [original, original.replace(b"\r\n", b"\n")]:
            with self.subTest(payload=payload), TemporaryDirectory() as temp:
                root = Path(temp); self.fixture(root, payload)
                with warnings.catch_warnings(record=True) as caught:
                    path = _require_file(root, "dpi2023.csv")
                self.assertEqual(path.read_bytes(), payload)
                self.assertEqual(len(caught), int(b"\r" not in payload))

    def test_changed_value_is_rejected_even_with_lf_endings(self):
        with TemporaryDirectory() as temp:
            root = Path(temp)
            self.fixture(root, b"countryname,year,execrlc\nCanada,2023-01-01,Left\n")
            with self.assertRaises(DataSourceError): _require_file(root, "dpi2023.csv")

    def test_other_source_has_no_newline_hash_exception(self):
        with TemporaryDirectory() as temp:
            root = Path(temp)
            self.fixture(root, b"countryname,year,execrlc\nCanada,2023-01-01,Right\n", "global_leader_ideologies.csv")
            with self.assertRaises(DataSourceError): _require_file(root, "global_leader_ideologies.csv")


if __name__ == "__main__": unittest.main()
