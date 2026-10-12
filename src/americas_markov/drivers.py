"""Optional observed exposures, separately cached from the original inputs.

Two fuel shares have DIFFERENT denominators and are never subtracted into a
net-import measure. For an origin t, shocks describe t-1, exposures t-2.
These revised series support retrospective prediction, not causal effects.
"""
from __future__ import annotations

from datetime import datetime, timezone
from hashlib import sha256
import json
from pathlib import Path
import time
from urllib.request import Request, urlopen

import numpy as np
import pandas as pd

from .data import AMERICAS_ISO3, DataSourceError, _wdi_payload

EXPOSURES = {
    "fuel_export_share": ("TX.VAL.FUEL.ZS.UN", "percent of merchandise exports"),
    "agriculture_share": ("NV.AGR.TOTL.ZS", "agriculture, forestry and fishing; percent of GDP"),
}
OIL_COLUMNS = ["oil_growth", "fuel_import_share_prior", "fuel_export_share_prior",
               "oil_x_import_prior", "oil_x_export_prior"]
CLIMATE_COLUMNS = ["enso_mean", "agriculture_share_prior", "enso_x_agriculture_prior"]
LEAN_COLUMNS = ["gdp_growth", "inflation", "state_duration", "eiec"]


def exposure_url(indicator):
    return (f"https://api.worldbank.org/v2/country/{';'.join(AMERICAS_ISO3)}/indicator/{indicator}"
            "?source=2&date=1960:2025&format=json&per_page=20000&page=1")


def _fetch_exposure(indicator):
    errors = []
    for attempt in range(3):
        try:
            with urlopen(Request(exposure_url(indicator), headers={"User-Agent": "Teuken-Markov research"}), timeout=45) as response:
                payload = response.read()
            _wdi_payload(payload, indicator)
            return payload
        except (OSError, TimeoutError, DataSourceError) as exc:
            errors.append(str(exc))
            if attempt < 2:
                time.sleep(attempt + 1)
    raise DataSourceError(f"Cannot download optional exposure {indicator}: {errors[-1]}")


def download_exposures(root: Path, refresh=False):
    root = Path(root); raw = root / "data/raw"; raw.mkdir(parents=True, exist_ok=True)
    manifest_path = raw / "driver_exposures_manifest.json"
    old = json.loads(manifest_path.read_text()) if manifest_path.exists() else {"sources": {}}
    records = {}
    for name, (indicator, unit) in EXPOSURES.items():
        path = raw / f"driver_wdi_{indicator}.json"
        prior = old.get("sources", {}).get(name, {})
        if path.exists() and not refresh:
            payload = path.read_bytes()
            if not prior or prior.get("sha256") != sha256(payload).hexdigest():
                raise DataSourceError(f"Unverified optional exposure cache {path.name}; use --download --refresh")
            timestamp = prior["retrieved_at"]
        else:
            payload = _fetch_exposure(indicator)
            path.write_bytes(payload)
            timestamp = datetime.now(timezone.utc).isoformat()
        metadata, rows = _wdi_payload(payload, indicator)
        if any(row.get("indicator", {}).get("id") != indicator for row in rows):
            raise DataSourceError(f"Unexpected optional indicator {indicator}")
        records[name] = {"indicator": indicator, "url": exposure_url(indicator), "raw_path": str(path.relative_to(root)),
                         "sha256": sha256(payload).hexdigest(), "retrieved_at": timestamp,
                         "units": unit, "api_last_updated": metadata.get("lastupdated"), "rows": len(rows)}
    manifest = {"sources": records, "note": "Revised historical values; not real-time release vintages. Missing values retained."}
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n")
    return manifest


def load_exposures(root: Path):
    raw = Path(root) / "data/raw"
    manifest = raw / "driver_exposures_manifest.json"
    if not manifest.exists():
        raise DataSourceError("Missing optional exposure manifest; run run_extensions.py --download")
    entries = json.loads(manifest.read_text())["sources"]
    frames = []
    for name, (indicator, _) in EXPOSURES.items():
        path = raw / f"driver_wdi_{indicator}.json"
        if not path.exists() or sha256(path.read_bytes()).hexdigest() != entries.get(name, {}).get("sha256"):
            raise DataSourceError(f"Missing or changed optional source {path.name}")
        _, rows = _wdi_payload(path.read_bytes(), indicator)
        if any(r.get("countryiso3code") not in AMERICAS_ISO3 or r.get("indicator", {}).get("id") != indicator for r in rows):
            raise DataSourceError("Optional WDI source changed country/indicator schema")
        f = pd.DataFrame([{"country_code": r["countryiso3code"], "year": int(r["date"]), name: r["value"]} for r in rows])
        if f.duplicated(["country_code", "year"]).any():
            raise DataSourceError("Duplicate optional country/year observations")
        f[name] = pd.to_numeric(f[name], errors="coerce")
        frames.append(f)
    return frames[0].merge(frames[1], on=["country_code", "year"], how="outer", validate="one_to_one")


def prepare_driver_features(features, wdi, exposures, climate):
    """Join observed t-1 climate and t-2 exposures without forward filling."""
    f = features.copy()
    if f.duplicated(["country_code", "year"]).any():
        raise ValueError("Duplicate political feature rows")
    national = wdi.loc[wdi.country_code.ne("WLD"), ["country_code", "year", "fuel_import_share"]].merge(
        exposures, on=["country_code", "year"], how="outer", validate="one_to_one")
    national["exposure_source_year"] = national.year
    national["year"] += 2
    national = national.rename(columns={c: c + "_prior" for c in ["fuel_import_share", *EXPOSURES]})
    f = f.merge(national, on=["country_code", "year"], how="left", validate="one_to_one")
    # Intended source year is exposed even when a country's reported value is missing.
    f["exposure_source_year"] = f.year - 2
    c = climate[["year", "enso_mean"]].copy()
    if c.year.duplicated().any():
        raise ValueError("Duplicate annual climate index")
    c["climate_source_year"] = c.year
    c["year"] += 1
    f = f.merge(c, on="year", how="left", validate="many_to_one")
    f["climate_source_year"] = f.year - 1
    f["oil_x_import_prior"] = f.oil_growth * f.fuel_import_share_prior / 100
    f["oil_x_export_prior"] = f.oil_growth * f.fuel_export_share_prior / 100
    f["enso_x_agriculture_prior"] = f.enso_mean * f.agriculture_share_prior / 100
    return f


def model_specs():
    return {"lean": LEAN_COLUMNS.copy(),
            "lean_oil": LEAN_COLUMNS + OIL_COLUMNS,
            "lean_enso": LEAN_COLUMNS + CLIMATE_COLUMNS,
            "lean_oil_enso": LEAN_COLUMNS + OIL_COLUMNS + CLIMATE_COLUMNS}


def conditional_oil_scenario(fitted, snapshot, oil_growth):
    """One-step probability contrast; national exposures and other features fixed."""
    from .models import predict_probabilities
    frame = snapshot.copy()
    frame["oil_growth"] = float(oil_growth)
    frame["oil_x_import_prior"] = frame.oil_growth * frame.fuel_import_share_prior / 100
    frame["oil_x_export_prior"] = frame.oil_growth * frame.fuel_export_share_prior / 100
    return predict_probabilities(fitted, frame)
