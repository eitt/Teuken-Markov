"""Public-source acquisition and transparent loaders for the Americas panel.

All downloads use urllib. Input files are cached in ``root/data/raw`` together
with a URL/date/SHA256 manifest. The loaders preserve reported missing values;
they neither classify unknown ideologies as centrist nor impute observations.
Annual WDI and price observations are unlagged here: temporal alignment belongs
to the feature builder. Current downloads may contain retrospective revisions.
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from hashlib import sha256
from pathlib import Path
from typing import Any
from urllib.request import Request, urlopen
import csv
import io
import json
import time
import warnings

import pandas as pd


AMERICAS_ISO3 = (
    "ATG", "ARG", "BHS", "BRB", "BLZ", "BOL", "BRA", "CAN", "CHL",
    "COL", "CRI", "CUB", "DMA", "DOM", "ECU", "SLV", "GRD", "GTM",
    "GUY", "HTI", "HND", "JAM", "MEX", "NIC", "PAN", "PRY", "PER",
    "KNA", "LCA", "VCT", "SUR", "TTO", "USA", "URY", "VEN",
)

# Explicit aliases from the downloaded DPI2023 CSV, rather than fuzzy matching.
DPI_COUNTRY_MAP = {
    "Argentina": "ARG", "Bahamas": "BHS", "Barbados": "BRB",
    "Belize": "BLZ", "Bolivia": "BOL", "Brazil": "BRA", "Canada": "CAN",
    "Chile": "CHL", "Colombia": "COL", "Costa Rica": "CRI", "Cuba": "CUB",
    "Dom. Rep.": "DOM", "Ecuador": "ECU", "El Salvador": "SLV",
    "Grenada": "GRD", "Guatemala": "GTM", "Guyana": "GUY", "Haiti": "HTI",
    "Honduras": "HND", "Jamaica": "JAM", "Mexico": "MEX", "Nicaragua": "NIC",
    "Panama": "PAN", "Paraguay": "PRY", "Peru": "PER", "St. Lucia": "LCA",
    "Suriname": "SUR", "Trinidad-Tobago": "TTO", "USA": "USA",
    "Uruguay": "URY", "Venezuela": "VEN",
}

DPI_URL = "https://data.iadb.org/files/download/30f45628-8608-4c0c-ad55-bc4c870dd62d"
DPI_CODEBOOK_URL = "https://data.iadb.org/files/download/7d23d94b-dfec-4c84-b50e-174320432521"
GLI_URL = (
    "https://raw.githubusercontent.com/bastianherre/global-leader-ideologies/"
    "1552fa731866baf6c1fe8cc9da53d0dd483bac7b/global_leader_ideologies.csv"
)
PINK_SHEET_URL = (
    "https://thedocs.worldbank.org/en/doc/"
    "74e8be41ceb20fa0da750cda2f6b9e4e-0050012026/related/"
    "CMO-Historical-Data-Monthly.xlsx"
)
WDI_INDICATORS = {
    "gdp_growth": ("NY.GDP.MKTP.KD.ZG", "annual percent change in real GDP"),
    "inflation": ("FP.CPI.TOTL.ZG", "annual percent change in consumer prices"),
    "trade_open": ("NE.TRD.GNFS.ZS", "exports plus imports, percent of GDP"),
    "fuel_import_share": ("TM.VAL.FUEL.ZS.UN", "fuel imports, percent of merchandise imports"),
    "tourism_exports_share": (
        "ST.INT.RCPT.XP.ZS", "international tourism receipts, percent of total exports"
    ),
    "population": ("SP.POP.TOTL", "persons"),
}


class DataSourceError(RuntimeError):
    """A requested public source could not be downloaded or parsed."""

    def __init__(self, message: str, manifest: dict | None = None):
        super().__init__(message)
        self.manifest = manifest


def _raw_dir(root: Path) -> Path:
    return Path(root).resolve() / "data" / "raw"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _wdi_url(indicator: str) -> str:
    countries = ";".join((*AMERICAS_ISO3, "WLD"))
    return (
        f"https://api.worldbank.org/v2/country/{countries}/indicator/{indicator}"
        "?source=2&date=1960:2025&format=json&per_page=20000&page=1"
    )


def _wdi_payload(content: bytes, label: str) -> tuple[dict, list[dict]]:
    try:
        payload = json.loads(content.decode("utf-8-sig"))
    except (ValueError, UnicodeError) as exc:
        raise DataSourceError(f"{label}: response is not valid JSON: {exc}") from exc
    if not (
        isinstance(payload, list) and len(payload) == 2
        and isinstance(payload[0], dict) and isinstance(payload[1], list)
    ):
        raise DataSourceError(f"{label}: unexpected World Bank response: {str(payload)[:350]}")
    metadata, rows = payload
    if int(metadata.get("pages", 0)) != 1 or len(rows) != int(metadata.get("total", -1)):
        raise DataSourceError(f"{label}: incomplete/paginated World Bank response: {metadata}")
    if not rows:
        raise DataSourceError(f"{label}: API returned no observations")
    return metadata, rows


def _validate_content(content: bytes, kind: str, label: str) -> None:
    if not content:
        raise DataSourceError(f"{label}: downloaded file is empty")
    if kind == "wdi":
        _wdi_payload(content, label)
    elif kind == "xlsx":
        if not content.startswith(b"PK"):
            raise DataSourceError(f"{label}: response is not an XLSX archive")
    elif kind == "csv":
        text = content.decode("utf-8-sig")
        first = next(csv.reader(io.StringIO(text)), [])
        required = "countryname" if label == "dpi2023" else "country_name"
        if required not in first or "year" not in first:
            raise DataSourceError(f"{label}: CSV schema missing {required!r} or 'year'")


def _download(
    raw: Path, source_id: str, filename: str, url: str, kind: str,
    refresh: bool, previous: dict, notes: str, units: str | dict,
    required: bool = True,
) -> dict[str, Any]:
    path = raw / filename
    entry: dict[str, Any] = {
        "source_id": source_id, "url": url,
        "raw_path": f"data/raw/{filename}", "required": required,
        "notes": notes, "units": units,
    }
    old = previous.get(source_id, {})
    if path.exists() and not refresh:
        try:
            content = path.read_bytes()
            _validate_content(content, kind, source_id)
            digest = sha256(content).hexdigest()
            if old.get("sha256") and old["sha256"] != digest:
                raise DataSourceError(f"{source_id}: cached file SHA256 changed")
            retrieved_at = old.get("retrieved_at") or datetime.fromtimestamp(
                path.stat().st_mtime, timezone.utc
            ).isoformat(timespec="seconds")
            entry.update(
                status="ok", cached=True, sha256=digest, bytes=len(content),
                retrieved_at=retrieved_at, retrieved_date=retrieved_at[:10],
                resolved_url=old.get("resolved_url", url), attempts=0,
            )
            return entry
        except (OSError, ValueError, UnicodeError, DataSourceError) as exc:
            entry["cache_issue"] = str(exc)

    errors = []
    for attempt in range(1, 4):
        try:
            request = Request(url, headers={"User-Agent": "AmericasMarkov/0.1 public-data-research"})
            with urlopen(request, timeout=45) as response:
                content = response.read()
                resolved_url = response.geturl()
                status = getattr(response, "status", 200)
            if status != 200:
                raise DataSourceError(f"HTTP {status}")
            _validate_content(content, kind, source_id)
            temporary = path.with_name(path.name + ".part")
            temporary.write_bytes(content)
            temporary.replace(path)
            timestamp = _now()
            entry.update(
                status="ok", cached=False, sha256=sha256(content).hexdigest(),
                bytes=len(content), retrieved_at=timestamp, retrieved_date=timestamp[:10],
                resolved_url=resolved_url, attempts=attempt,
            )
            if errors:
                entry["retry_errors"] = errors
            return entry
        except Exception as exc:
            errors.append(f"Attempt {attempt}: {type(exc).__name__}: {exc}")
            if attempt < 3:
                time.sleep(attempt)
    entry.update(status="error", cached=False, attempts=3, error=errors[-1], retry_errors=errors)
    return entry


def download_all(root: Path, refresh: bool = False, include_who: bool = False) -> dict:
    """Download/cache DPI, WDI, Pink Sheet, and optional raw GLI sensitivity data.

    A required-source failure writes the manifest and raises DataSourceError.
    Raw GLI is supplementary and never substituted for DPI. WHO is outside the
    core model; explicitly requesting its unconfigured connector is reported.
    """
    raw = _raw_dir(root)
    raw.mkdir(parents=True, exist_ok=True)
    manifest_path = raw / "download_manifest.json"
    previous = {}
    if manifest_path.exists():
        try:
            previous = json.loads(manifest_path.read_text(encoding="utf-8")).get("sources", {})
        except (OSError, ValueError) as exc:
            warnings.warn(f"Cannot read previous download manifest: {exc}", RuntimeWarning)
    specs = [
        ("dpi2023", "dpi2023.csv", DPI_URL, "csv",
         "DPI2023 release 2026; chief executive's economic orientation at January 1; "
         "31 of 35 sovereign American countries. Blank/-999 are missing; 0 is unclassified, "
         "not center. EXELEC describes elections during the labelled calendar year. "
         f"Codebook: {DPI_CODEBOOK_URL}",
         {"state": "nominal Left/Center/Right", "eiec": "ordinal executive electoral competitiveness (1–7)",
          "election_held": "0/1; EXELEC during year", "years_in_office": "years"}, True),
        ("pink_sheet", "pink_sheet_monthly.xlsx", PINK_SHEET_URL, "xlsx",
         "World Bank monthly Pink Sheet, October 2026 workbook. Load Monthly Prices and "
         "Monthly Indices; calendar-year arithmetic means require 12 valid months per series. "
         "Growth = 100*(annual_mean/previous_year_annual_mean - 1); partial years excluded.",
         {"oil_price": "Crude oil, average; nominal USD per barrel", "food_index": "nominal USD index; 2010=100",
          "oil_growth": "annual percent change", "food_growth": "annual percent change"}, True),
        ("gli_sensitivity", "global_leader_ideologies.csv", GLI_URL, "csv",
         "Author's CSV pinned to commit 1552fa731866baf6c1fe8cc9da53d0dd483bac7b. "
         "1945–2020, December 31 snapshot; 29 American leader series, 27 heads-of-government "
         "series. Retained for sensitivity; not merged into DPI.", "nominal economic ideology", False),
    ]
    for feature, (indicator, unit) in WDI_INDICATORS.items():
        specs.append((
            f"wdi_{feature}", f"wdi_{indicator}.json", _wdi_url(indicator), "wdi",
            f"WDI source 2; {indicator}; all 35 sovereign American ISO3 countries plus WLD; "
            "1960–2025 requested. Null values remain missing. Download contains currently "
            "revised historical observations, not real-time vintages.", unit, True,
        ))
    entries = {}
    with ThreadPoolExecutor(max_workers=4) as pool:
        futures = {
            pool.submit(_download, raw, sid, filename, url, kind, refresh,
                        previous, notes, units, required): sid
            for sid, filename, url, kind, notes, units, required in specs
        }
        for future in as_completed(futures):
            sid = futures[future]
            entries[sid] = future.result()
    errors = [dict(source_id=sid, required=e["required"], error=e["error"])
              for sid, e in entries.items() if e["status"] == "error"]
    optional = {"who": {"requested": include_who, "status": "not_requested"}}
    if include_who:
        message = "WHO connector is not configured; no WHO observations were downloaded or fabricated."
        optional["who"].update(status="not_configured", error=message)
        errors.append(dict(source_id="who", required=False, error=message))
    manifest = {
        "created_at": _now(), "schema_version": 1,
        "sources": dict(sorted(entries.items())), "errors": errors, "optional": optional,
        "countries": list(AMERICAS_ISO3), "wdi_aggregate": "WLD",
        "dpi_missing_country_codes": sorted(set(AMERICAS_ISO3) - set(DPI_COUNTRY_MAP.values())),
        "notes": [
            "State labels are nominal; numeric category codes are never treated as distances.",
            "These loaders do not lag features. The model must impose its documented timing convention.",
            "The complete 35-country registry does not imply complete political or economic observations.",
        ],
    }
    manifest["status"] = "error" if any(e["required"] for e in errors) else ("ok_with_optional_errors" if errors else "ok")
    manifest_temp = manifest_path.with_name(manifest_path.name + ".part")
    manifest_temp.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    manifest_temp.replace(manifest_path)
    required_errors = [e for e in errors if e["required"]]
    if required_errors:
        detail = "; ".join(f"{e['source_id']}: {e['error']}" for e in required_errors)
        raise DataSourceError(f"Required public-source downloads failed. See {manifest_path}: {detail}", manifest)
    for error in errors:
        warnings.warn(f"Optional source failure: {error['source_id']}: {error['error']}", RuntimeWarning)
    return manifest


def _require_file(root: Path, filename: str) -> Path:
    path = _raw_dir(root) / filename
    if not path.is_file():
        raise DataSourceError(f"Missing public-source input {path}. Run download_all(root) first.")
    manifest_path = _raw_dir(root) / "download_manifest.json"
    if not manifest_path.exists():
        raise DataSourceError("Falta el manifiesto de las fuentes; ejecute run.py --download.")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    entry = next((item for item in manifest.get("sources", {}).values()
                  if Path(item.get("raw_path", "")).name == filename), None)
    payload = path.read_bytes()
    verified = entry is not None and sha256(payload).hexdigest() == entry.get("sha256")
    # Legacy GitHub uploads normalised this CSV from CRLF to LF. Accept that
    # ONE lossless transformation only when restoring CRLF recovers the exact
    # original recorded SHA256. Any changed cell/whitespace still fails.
    if not verified and entry is not None and filename == "dpi2023.csv" and b"\r" not in payload:
        restored = payload.replace(b"\n", b"\r\n")
        verified = sha256(restored).hexdigest() == entry.get("sha256")
        if verified:
            warnings.warn("DPI CSV has Git-normalised LF endings; exact original SHA256 verified after CRLF restoration.", RuntimeWarning)
    if not verified:
        raise DataSourceError(f"El hash de {filename} no coincide con el manifiesto; no se usa como fuente verificada.")
    return path


def _numeric(column: pd.Series) -> pd.Series:
    return pd.to_numeric(column, errors="coerce").mask(lambda x: x == -999)


def load_politics(root: Path) -> pd.DataFrame:
    """Load all31 American DPI series, preserving unclassified/missing state rows."""
    source = _require_file(root, "dpi2023.csv")
    frame = pd.read_csv(source, dtype=str, keep_default_na=False)
    required = {"countryname", "year", "execrlc", "execme", "exelec", "eiec", "system", "yrsoffc"}
    missing = required - set(frame.columns)
    if missing:
        raise DataSourceError(f"DPI CSV is missing required columns: {sorted(missing)}")
    selected = frame.loc[frame["countryname"].isin(DPI_COUNTRY_MAP)].copy()
    if selected["countryname"].nunique() != 31:
        raise DataSourceError("DPI American country aliases changed; expected 31 source countries.")
    parsed_year = pd.to_datetime(selected["year"], errors="coerce")
    if parsed_year.isna().any():
        raise DataSourceError("DPI contains unparseable observation dates.")
    labels = selected["execrlc"].str.strip()
    invalid = sorted(set(labels) - {"Left", "Center", "Right", "0", "0.0", "-999", "-999.0", "", "NA"})
    if invalid:
        raise DataSourceError(f"Unexpected DPI ideology labels: {invalid}; explicit recoding required.")
    result = pd.DataFrame({
        "country_code": selected["countryname"].map(DPI_COUNTRY_MAP),
        "country_name": selected["countryname"],
        "year": parsed_year.dt.year.astype(int),
        "state": labels.where(labels.isin(["Left", "Center", "Right"]), pd.NA),
        "ideology_raw": labels,
        "executive_party": selected["execme"].replace({"": pd.NA, "-999": pd.NA, "-999.0": pd.NA}),
        "election_held": _numeric(selected["exelec"]),
        "eiec": _numeric(selected["eiec"]),
        "system": selected["system"].replace({"": pd.NA, "-999": pd.NA, "-999.0": pd.NA}),
        "years_in_office": _numeric(selected["yrsoffc"]),
    })
    if result.duplicated(["country_code", "year"]).any():
        raise DataSourceError("DPI has duplicate American country-year observations.")
    if not result["election_held"].dropna().isin([0, 1]).all():
        raise DataSourceError("Unexpected EXELEC values; only 0/1 or missing are permitted.")
    result = result.sort_values(["country_code", "year"]).reset_index(drop=True)
    result.attrs["observation_date"] = "January 1"
    result.attrs["coverage"] = "31 of 35 sovereign American countries, 1975–2023"
    result.attrs["missing_countries"] = sorted(set(AMERICAS_ISO3) - set(result["country_code"]))
    result.attrs["source_url"] = DPI_URL
    return result


def load_wdi(root: Path) -> pd.DataFrame:
    """Return unlagged annual WDI observations in wide form; nulls remain NaN."""
    records = []
    metadata_by_feature = {}
    for feature, (indicator, _) in WDI_INDICATORS.items():
        path = _require_file(root, f"wdi_{indicator}.json")
        metadata, rows = _wdi_payload(path.read_bytes(), indicator)
        metadata_by_feature[feature] = metadata
        for row in rows:
            code = row.get("countryiso3code")
            if code not in (*AMERICAS_ISO3, "WLD"):
                raise DataSourceError(f"Unexpected WDI country code {code!r} in {indicator}")
            if row.get("indicator", {}).get("id") != indicator:
                raise DataSourceError(f"Unexpected WDI indicator in {path}")
            records.append(dict(country_code=code, year=int(row["date"]), feature=feature, value=row["value"]))
    long = pd.DataFrame(records)
    if long.duplicated(["country_code", "year", "feature"]).any():
        raise DataSourceError("WDI contains duplicate country-year-indicator observations.")
    wide = long.pivot(index=["country_code", "year"], columns="feature", values="value")
    # Reindex only the observation grid, never the values, so absent observations
    # remain visibly missing and every requested sovereign state is represented.
    grid = pd.MultiIndex.from_product([(*AMERICAS_ISO3, "WLD"), range(1960, 2026)], names=["country_code", "year"])
    wide = wide.reindex(grid).reset_index()
    wide.columns.name = None
    wide = wide[["country_code", "year", *WDI_INDICATORS]]
    for feature in WDI_INDICATORS:
        wide[feature] = pd.to_numeric(wide[feature], errors="coerce")
    wide.attrs["units"] = {feature: unit for feature, (_, unit) in WDI_INDICATORS.items()}
    wide.attrs["api_metadata"] = metadata_by_feature
    wide.attrs["vintage_note"] = "Currently revised history; not information vintages as originally known."
    return wide.sort_values(["country_code", "year"]).reset_index(drop=True)


def load_prices(root: Path) -> pd.DataFrame:
    """Annual changes in global oil prices and the Food index, using full years."""
    path = _require_file(root, "pink_sheet_monthly.xlsx")
    try:
        prices = pd.read_excel(path, sheet_name="Monthly Prices", header=4, engine="openpyxl")
        indices = pd.read_excel(path, sheet_name="Monthly Indices", header=None, engine="openpyxl")
    except Exception as exc:
        raise DataSourceError(f"Cannot read official Pink Sheet workbook {path}: {exc}") from exc
    oil_column = "Crude oil, average"
    if oil_column not in prices.columns:
        raise DataSourceError(f"Pink Sheet oil header changed; expected {oil_column!r}")
    food_columns = {
        col for col in range(indices.shape[1])
        if any(str(x).strip().strip(" *").lower() == "food" for x in indices.iloc[:10, col])
    }
    if len(food_columns) != 1:
        raise DataSourceError(f"Pink Sheet Food header ambiguous/absent: columns {food_columns}")
    food_column = next(iter(food_columns))
    period_pattern = r"^\d{4}M\d{2}$"
    oil_period = prices.iloc[:, 0].astype(str).str.strip()
    food_period = indices.iloc[:, 0].astype(str).str.strip()
    oil = pd.DataFrame({"period": oil_period, "oil_price": pd.to_numeric(prices[oil_column], errors="coerce")})
    food = pd.DataFrame({"period": food_period, "food_index": pd.to_numeric(indices.iloc[:, food_column], errors="coerce")})
    oil = oil.loc[oil["period"].str.match(period_pattern)]
    food = food.loc[food["period"].str.match(period_pattern)]
    if oil["period"].duplicated().any() or food["period"].duplicated().any():
        raise DataSourceError("Pink Sheet contains duplicate monthly periods.")
    monthly = oil.merge(food, on="period", how="outer", validate="one_to_one")
    monthly["year"] = monthly["period"].str[:4].astype(int)
    if (monthly[["oil_price", "food_index"]].dropna() <= 0).any().any():
        raise DataSourceError("Pink Sheet contains nonpositive oil/Food observations.")
    grouped = monthly.groupby("year")
    annual = grouped[["oil_price", "food_index"]].mean()
    counts = grouped[["oil_price", "food_index"]].count()
    annual.loc[counts["oil_price"] != 12, "oil_price"] = float("nan")
    annual.loc[counts["food_index"] != 12, "food_index"] = float("nan")
    full_years = annual.index[(counts["oil_price"] == 12) | (counts["food_index"] == 12)]
    if len(full_years) < 2:
        raise DataSourceError("Pink Sheet has fewer than two complete annual observations.")
    annual = annual.reindex(range(int(annual.index.min()), int(annual.index.max()) + 1))
    annual["oil_growth"] = 100 * (annual["oil_price"] / annual["oil_price"].shift(1) - 1)
    annual["food_growth"] = 100 * (annual["food_index"] / annual["food_index"].shift(1) - 1)
    annual["monthly_count_oil"] = counts["oil_price"]
    annual["monthly_count_food"] = counts["food_index"]
    # Drop incomplete terminal years; an incomplete internal series stays NaN.
    annual = annual.loc[annual.index <= max(full_years)].reset_index(names="year")
    annual = annual[["year", "oil_growth", "food_growth", "oil_price", "food_index", "monthly_count_oil", "monthly_count_food"]]
    annual.attrs["source_url"] = PINK_SHEET_URL
    annual.attrs["units"] = {
        "oil_price": "nominal USD/barrel", "food_index": "nominal USD index, 2010=100",
        "oil_growth": "percent change in annual arithmetic mean",
        "food_growth": "percent change in annual arithmetic mean",
    }
    annual.attrs["timing_note"] = "Full calendar years only; lagging is the caller's responsibility."
    return annual
