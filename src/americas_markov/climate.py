"""Retrospective NOAA ONI covariates, with explicit event-time boundaries.

ONI measures ENSO climate variability, not anthropogenic climate change or
national physical exposure. Its three-month windows overlap. The annual
summaries below average exactly eleven windows, DJF through OND. NDJ of source
year Y is always excluded because it includes January of Y+1. DJF of Y includes
December of Y-1; every included window ends within Y.

These are researcher-defined summaries of revised ONI observations, not NOAA
annual indices or eleven independent monthly observations. Event-time lagging
does not recreate historical publication vintages: OND is published after its
December observations and historical anomalies/climatologies can be revised.
The current documented ONI is ERSSTv6; NOAA's operational switch to RONI in
2026 does not change the product selected here. RONI is never downloaded or
substituted. Call download_climate explicitly; load_climate always runs offline.
"""

from __future__ import annotations

from datetime import datetime, timezone
from hashlib import sha256
from pathlib import Path
from urllib.request import Request, urlopen
import io
import json
import math
import time

import pandas as pd

from .data import DataSourceError


ONI_URL = "https://www.cpc.ncep.noaa.gov/data/indices/oni.ascii.txt"
ONI_DOCUMENTATION_URL = "https://www.cpc.ncep.noaa.gov/products/analysis_monitoring/enso/oni/v6/"
INCLUDED_SEASONS = ("DJF", "JFM", "FMA", "MAM", "AMJ", "MJJ", "JJA", "JAS", "ASO", "SON", "OND")
EXCLUDED_SEASONS = ("NDJ",)
RAW_FILENAME = "noaa_oni.txt"
MANIFEST_FILENAME = "climate_manifest.json"


class ClimateDataError(DataSourceError):
    """Missing, malformed or temporally incomplete NOAA ONI source data."""


def _raw_folder(root: Path) -> Path:
    return Path(root).expanduser().resolve() / "data" / "raw"


def _timestamp() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _read_manifest(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        manifest = json.loads(path.read_text(encoding="utf-8"))
    except (ValueError, OSError) as exc:
        raise ClimateDataError(f"Cannot read ONI cache manifest {path}: {exc}") from exc
    if not isinstance(manifest, dict):
        raise ClimateDataError(f"ONI cache manifest {path} must contain a dictionary.")
    return manifest


def _parse_raw(content: bytes) -> pd.DataFrame:
    try:
        frame = pd.read_csv(io.StringIO(content.decode("utf-8-sig")), sep=r"\s+")
    except (ValueError, UnicodeError, pd.errors.ParserError) as exc:
        raise ClimateDataError(f"Cannot parse NOAA ONI text: {exc}") from exc
    if list(frame.columns) != ["SEAS", "YR", "TOTAL", "ANOM"]:
        raise ClimateDataError(
            f"Unexpected NOAA ONI schema {list(frame.columns)}; expected SEAS YR TOTAL ANOM. "
            "Do not substitute the different RONI schema."
        )
    if frame.empty:
        raise ClimateDataError("NOAA ONI source contains no seasonal observations.")
    frame["SEAS"] = frame["SEAS"].astype(str).str.strip()
    unknown = set(frame["SEAS"]) - set(INCLUDED_SEASONS + EXCLUDED_SEASONS)
    if unknown:
        raise ClimateDataError(f"Unknown NOAA ONI seasons: {sorted(unknown)}")
    years = pd.to_numeric(frame["YR"], errors="coerce")
    if years.isna().any() or not years.mod(1).eq(0).all():
        raise ClimateDataError("NOAA ONI contains invalid source-year values.")
    frame["YR"] = years.astype(int)
    if frame.duplicated(["YR", "SEAS"]).any():
        raise ClimateDataError("NOAA ONI contains duplicate source-year/season observations.")
    frame["ANOM"] = pd.to_numeric(frame["ANOM"], errors="coerce")
    frame["ANOM"] = frame["ANOM"].where(frame["ANOM"].map(lambda x: pd.notna(x) and math.isfinite(float(x))))
    return frame.sort_values(["YR", "SEAS"]).reset_index(drop=True)


def _annual_summary(frame: pd.DataFrame) -> pd.DataFrame:
    retained = frame.loc[frame["SEAS"].isin(INCLUDED_SEASONS)].copy()
    first_year, last_year = int(frame["YR"].min()), int(frame["YR"].max())
    complete_years, excluded_years, window_counts = [], [], {}
    expected = set(INCLUDED_SEASONS)
    for year in range(first_year, last_year + 1):
        observations = retained.loc[retained["YR"].eq(year)]
        valid_count = int(observations["ANOM"].notna().sum())
        window_counts[year] = valid_count
        complete = set(observations["SEAS"]) == expected and valid_count == 11
        if complete:
            complete_years.append(year)
        elif year == last_year:
            # The current unfinished calendar year is not an annual observation.
            excluded_years.append(year)
        else:
            raise ClimateDataError(
                f"NOAA ONI source year {year} has {valid_count} valid retained windows; "
                "exactly 11 unique DJF-through-OND windows are required. "
                "Historical gaps are not interpolated or silently dropped."
            )
    if not complete_years:
        raise ClimateDataError("NOAA ONI has no complete source year with 11 valid retained windows.")
    retained = retained.loc[retained["YR"].isin(complete_years)]
    # DJF,...,OND all end in source year Y; NDJ ends in Y+1 and is excluded.
    retained["max_event_year"] = retained["YR"]
    if not retained["max_event_year"].le(retained["YR"]).all():
        raise ClimateDataError("An ONI window includes events after its assigned source year.")
    result = retained.groupby("YR")["ANOM"].agg(
        enso_mean="mean",
        enso_abs_mean=lambda x: x.abs().mean(),
        enso_max_abs=lambda x: x.abs().max(),
    ).reset_index().rename(columns={"YR": "year"})
    result = result[["year", "enso_mean", "enso_abs_mean", "enso_max_abs"]]
    result["year"] = result["year"].astype(int)
    result.attrs.update({
        "source_url": ONI_URL,
        "documentation_url": ONI_DOCUMENTATION_URL,
        "product": "ONI; never RONI",
        "units": "degrees Celsius (SST anomaly)",
        "included_seasons": list(INCLUDED_SEASONS),
        "excluded_seasons": list(EXCLUDED_SEASONS),
        "aggregation": "11 overlapping three-month ONI means, DJF through OND; not an official annual NOAA index",
        "max_event_year_by_source_year": {year: year for year in complete_years},
        "valid_window_counts": window_counts,
        "excluded_incomplete_terminal_years": excluded_years,
        "timing_note": (
            "Source year Y contains no physical event after December Y; DJF includes December Y-1. "
            "Join source Y to political origin Y+1. OND publication is later than December; "
            "current revised data do not establish information availability exactly at January 1."
        ),
        "interpretation": "ENSO variability common to all countries; not national exposure, damage, anthropogenic warming or an automatically exogenous shock",
    })
    return result


def _write_manifest(path: Path, manifest: dict) -> None:
    temporary = path.with_name(path.name + ".part")
    temporary.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)


def download_climate(root: Path, refresh: bool = False) -> dict:
    """Explicitly download/cache NOAA ONI and return its SHA256/source manifest.

    Three attempts use a 30-second timeout. Valid cached inputs are reused
    without any request. A failed refresh raises; there is no synthetic fallback
    and no substitution of RONI. Files reside in ``root/data/raw``.
    """
    raw = _raw_folder(root)
    raw.mkdir(parents=True, exist_ok=True)
    destination = raw / RAW_FILENAME
    manifest_path = raw / MANIFEST_FILENAME
    previous = _read_manifest(manifest_path)
    old_source = previous.get("sources", {}).get("noaa_oni", {})
    base = {
        "source_id": "noaa_oni", "url": ONI_URL,
        "documentation_url": ONI_DOCUMENTATION_URL,
        "raw_path": f"data/raw/{RAW_FILENAME}",
        "product": "Oceanic Nino Index (ONI)",
        "documented_version": "ERSSTv6; document and preserve the downloaded snapshot",
        "units": "degrees Celsius, three-month mean SST anomaly in Nino3.4",
        "notes": (
            "Current revised ONI history; NOAA uses RONI operationally from February 2026, "
            "but this source and aggregation remain ONI. No historical publication vintage is reconstructed."
        ),
    }
    errors = []
    if destination.is_file() and not refresh:
        content = destination.read_bytes()
        digest = sha256(content).hexdigest()
        if old_source.get("sha256") and old_source["sha256"] != digest:
            raise ClimateDataError(
                f"Cached NOAA ONI SHA256 differs from {manifest_path}. "
                "Inspect the input or explicitly refresh; load does not silently replace it."
            )
        annual = _annual_summary(_parse_raw(content))
        retrieved_at = old_source.get("retrieved_at") or datetime.fromtimestamp(
            destination.stat().st_mtime, timezone.utc
        ).isoformat(timespec="seconds")
        source = dict(base, status="ok", cached=True, sha256=digest, bytes=len(content),
                      retrieved_at=retrieved_at, retrieved_date=retrieved_at[:10],
                      resolved_url=old_source.get("resolved_url", ONI_URL), attempts=0)
    else:
        for attempt in range(1, 4):
            try:
                request = Request(ONI_URL, headers={"User-Agent": "Teuken-Markov/0.2 public-climate-research"})
                with urlopen(request, timeout=30) as response:
                    content = response.read()
                    resolved_url = response.geturl()
                    status = getattr(response, "status", 200)
                if status != 200:
                    raise ClimateDataError(f"NOAA ONI returned HTTP {status}")
                annual = _annual_summary(_parse_raw(content))
                temporary = destination.with_name(destination.name + ".part")
                temporary.write_bytes(content)
                temporary.replace(destination)
                retrieved_at = _timestamp()
                source = dict(base, status="ok", cached=False, sha256=sha256(content).hexdigest(),
                              bytes=len(content), retrieved_at=retrieved_at,
                              retrieved_date=retrieved_at[:10], resolved_url=resolved_url,
                              attempts=attempt, retry_errors=errors)
                break
            except Exception as exc:
                errors.append(f"Attempt {attempt}: {type(exc).__name__}: {exc}")
                if attempt < 3:
                    time.sleep(attempt)
        else:
            source = dict(base, status="error", cached=False, attempts=3,
                          error=errors[-1], retry_errors=errors)
            manifest = {"schema_version": 1, "created_at": _timestamp(), "status": "error",
                        "sources": {"noaa_oni": source}, "errors": errors}
            _write_manifest(manifest_path, manifest)
            raise ClimateDataError(
                f"NOAA ONI download failed. See {manifest_path}: {errors[-1]}", manifest
            )
    manifest = {
        "schema_version": 1, "created_at": _timestamp(), "status": "ok",
        "sources": {"noaa_oni": source}, "errors": [],
        "annual_aggregation": dict(annual.attrs),
        "annual_coverage": {"first_year": int(annual.year.min()), "last_year": int(annual.year.max()),
                            "complete_source_years": int(len(annual))},
        "country_scope": (
            "Single ENSO index may be joined as a common covariate to all 35 American countries. "
            "These are not 35 national temperature/exposure observations."
        ),
    }
    _write_manifest(manifest_path, manifest)
    return manifest


def load_climate(root: Path) -> pd.DataFrame:
    """Offline loader: year, enso_mean, enso_abs_mean, enso_max_abs.

    A missing file or a historical incomplete year raises ClimateDataError.
    The unfinished terminal year is explicitly recorded in DataFrame.attrs and
    excluded. No network call is performed, including when inputs are missing.
    """
    raw = _raw_folder(root)
    path = raw / RAW_FILENAME
    if not path.is_file():
        raise ClimateDataError(f"Missing NOAA ONI input {path}. Call download_climate(root) explicitly first.")
    content = path.read_bytes()
    manifest = _read_manifest(raw / MANIFEST_FILENAME)
    source = manifest.get("sources", {}).get("noaa_oni", {})
    expected = source.get("sha256")
    if expected and sha256(content).hexdigest() != expected:
        raise ClimateDataError(f"Cached NOAA ONI SHA256 differs from {raw / MANIFEST_FILENAME}.")
    result = _annual_summary(_parse_raw(content))
    result.attrs["sha256"] = sha256(content).hexdigest()
    result.attrs["retrieved_at"] = source.get("retrieved_at")
    return result
