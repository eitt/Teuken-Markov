"""Separate GLI historical panels and date-aware DPI/GLI measurement audits.

GLI records December 31 of source year y. Here ``year=y+1`` is the January 1
alignment proxy used by the existing feature interface, not a claim of another
year of source coverage. ``observation_date`` retains the actual GLI date and
``aligned_date`` retains the adjacent-day proxy. January 1 inaugurations can
cause legitimate disagreement with DPI; the two measurements remain separate.

The default role is ``hog`` (the author's head of government); ``leader`` is an
explicit sensitivity series. No role fallback, DPI splice, ideology imputation,
competitive-election score, election calendar, or exact office tenure is added.
Annual run lengths count consecutive identical snapshots, not uninterrupted
tenure or elapsed time since an inauguration. Missing observations and gaps
reset those runs. ``none`` ideology is unknown, whereas party ``none`` records
non-affiliation and is retained without inventing a party-tenure run.

Herre (2023), Identifying Ideologues: A Global Dataset on Political Leaders,
1945-2020. British Journal of Political Science 53(2), 740-748.
https://doi.org/10.1017/S0007123422000217
Source documentation: https://github.com/bastianherre/global-leader-ideologies
"""

from __future__ import annotations

from hashlib import sha256
import json
from pathlib import Path

import numpy as np
import pandas as pd

from . import STATES
from .data import DataSourceError, GLI_URL, _require_file, load_politics
from .network import COUNTRY_METADATA, membership_table


_IDEOLOGY_MAP = {"leftist": "Left", "centrist": "Center", "rightist": "Right"}
_UNKNOWN_IDEOLOGIES = {"", "none", "no information", "not applicable"}
_MISSING_IDENTITY = {"", "none", "no information", "not applicable", "n/a"}
_PARTY_UNKNOWN = {"", "no information", "not applicable", "n/a"}
_ALIGNMENT = (
    "GLI December 31 y is relabelled to adjacent January 1 y+1; "
    "no new observation is created. Inaugurations on January 1 may differ from DPI."
)


def _runs(values: pd.Series, years: pd.Series) -> tuple[list[float], list[bool]]:
    """Observed consecutive snapshot counts and left-censored-run indicators."""
    durations, censored = [], []
    previous_value, previous_year, count, left_censored = None, None, 0, True
    for value, year in zip(values, years):
        known = pd.notna(value)
        previous_known = previous_value is not None
        adjacent = previous_year is not None and int(year) == previous_year + 1
        if not known:
            count = 0
            durations.append(np.nan)
            censored.append(True)
            previous_value = None
        else:
            if adjacent and previous_known and value == previous_value:
                count += 1
            else:
                count = 1
                left_censored = not (adjacent and previous_known)
            durations.append(float(count))
            censored.append(bool(left_censored))
            previous_value = value
        previous_year = int(year)
    return durations, censored


def _normalize_gli(frame: pd.DataFrame, role: str) -> pd.DataFrame:
    if role not in {"hog", "leader"}:
        raise ValueError("role must be 'hog' or 'leader'; there is no automatic role fallback")
    role_title = "hog_title" if role == "hog" else "leader_position"
    required = {
        "country_name", "country_code_cow", "year", role, f"{role}_ideology",
        f"{role}_party", f"{role}_party_id", f"{role}_party_abbr", role_title,
    }
    missing = required - set(frame.columns)
    if missing:
        raise DataSourceError(f"GLI is missing required columns: {sorted(missing)}")
    raw = frame.copy().fillna("").astype(str)
    # Strict source-year validation prevents a date-string or fractional-year
    # parser from silently changing the observation time.
    if not raw["year"].str.fullmatch(r"\d{4}").all():
        raise DataSourceError("GLI year must be a four-digit integer source year")
    raw["source_year"] = raw["year"].astype(int)
    if not raw["source_year"].between(1945, 2020).all():
        raise DataSourceError("Pinned GLI source coverage is 1945-2020; no future source years are accepted")
    cow = pd.to_numeric(raw["country_code_cow"], errors="coerce")
    if cow.isna().any() or not cow.eq(np.floor(cow)).all():
        raise DataSourceError("GLI has missing or noninteger COW country identifiers")
    raw["cow_code"] = cow.astype(int)
    if raw.duplicated(["cow_code", "source_year"]).any():
        raise DataSourceError("GLI has duplicate COW country/source-year snapshots; no aggregation is permitted")
    crosswalk = {int(meta["cow_code"]): iso3 for iso3, meta in COUNTRY_METADATA.items()}
    selected = raw.loc[raw["cow_code"].isin(crosswalk)].copy()
    if selected.empty:
        raise DataSourceError("GLI contains no countries in the verified 35-country Americas crosswalk")
    labels = selected[f"{role}_ideology"].str.strip()
    invalid = set(labels) - set(_IDEOLOGY_MAP) - _UNKNOWN_IDEOLOGIES
    if invalid:
        raise DataSourceError(f"Unexpected GLI economic ideology labels: {sorted(invalid)}")
    names = selected[role].str.strip()
    officeholder = names.mask(names.str.lower().isin(_MISSING_IDENTITY))
    parties = selected[f"{role}_party"].str.strip()
    party = parties.mask(parties.str.lower().isin(_PARTY_UNKNOWN))
    party_ids = selected[f"{role}_party_id"].str.strip()
    party_ids = party_ids.mask(party_ids.str.lower().isin(_MISSING_IDENTITY))
    # Independent/unaligned officeholders do not constitute one continuous party.
    affiliated = party.notna() & party.str.lower().ne("none")
    party_key = party_ids.map(lambda x: f"id:{x}" if pd.notna(x) else pd.NA)
    party_key = party_key.where(party_ids.notna(), party.map(lambda x: f"name:{x}" if pd.notna(x) else pd.NA))
    party_key = party_key.where(affiliated, pd.NA)
    result = pd.DataFrame({
        "country_code": selected["cow_code"].map(crosswalk),
        "country_name": selected["country_name"],
        "cow_code": selected["cow_code"],
        "source_year": selected["source_year"],
        "year": selected["source_year"] + 1,
        "observation_date": selected["source_year"].astype(str) + "-12-31",
        "aligned_date": (selected["source_year"] + 1).astype(str) + "-01-01",
        "source_dataset": "GLI",
        "source_role": role,
        "state": labels.map(_IDEOLOGY_MAP).where(labels.isin(_IDEOLOGY_MAP), pd.NA),
        "ideology_raw": labels,
        "leader_name": officeholder,
        "leader_name_raw": names,
        "leader_title": selected[role_title],
        "role_present": officeholder.notna(),
        "executive_party": party,
        "executive_party_raw": parties,
        "executive_party_id": party_ids,
        "executive_party_abbr": selected[f"{role}_party_abbr"],
        "party_run_key": party_key,
        "eiec": np.nan,
        "election_held": np.nan,
        "system": pd.NA,
        "years_in_office": np.nan,
    }).sort_values(["country_code", "year"]).reset_index(drop=True)
    if "democracy" in selected:
        democracy_lookup = selected.assign(country_code=selected.cow_code.map(crosswalk)).set_index(["country_code", "source_year"])["democracy"]
        result["gli_democracy_raw"] = [democracy_lookup.loc[(row.country_code, row.source_year)] for row in result.itertuples()]
    if "match_hog_leader" in selected:
        match_lookup = selected.assign(country_code=selected.cow_code.map(crosswalk)).set_index(["country_code", "source_year"])["match_hog_leader"]
        result["gli_match_hog_leader"] = [match_lookup.loc[(row.country_code, row.source_year)] for row in result.itertuples()]
    for column, output in [
        ("state", "state_duration"),
        ("leader_name", "leader_snapshot_duration"),
        ("party_run_key", "party_snapshot_duration"),
    ]:
        result[output] = np.nan
        result[output + "_left_censored"] = True
        for _, block in result.groupby("country_code", sort=False):
            durations, censored = _runs(block[column], block["year"])
            result.loc[block.index, output] = durations
            result.loc[block.index, output + "_left_censored"] = censored
    if result.duplicated(["country_code", "year"]).any():
        raise DataSourceError("GLI alignment generated duplicate country-year observations")
    if not result.year.eq(result.source_year + 1).all():
        raise AssertionError("Invalid GLI annual alignment shift")
    return result


def load_gli(root: str | Path, role: str = "hog") -> pd.DataFrame:
    """Load a hash-verified GLI-only panel compatible with feature input columns.

    Actual source coverage is December 31 1945-2020 (aligned years 1946-2021).
    ``eligible_cow_jan1`` is a separate membership proxy when COW inputs exist;
    it never erases the source ideology. The caller must filter it explicitly.
    Without COW inputs it remains missing, never assumed eligible.
    """
    root = Path(root).resolve()
    source = _require_file(root, "global_leader_ideologies.csv")
    result = _normalize_gli(pd.read_csv(source, dtype=str, keep_default_na=False), role)
    cow_available = (root / "data/raw/cow_states_v2024.csv").exists() and (root / "data/raw/cow_contiguity_manifest.json").exists()
    result["eligible_cow_jan1"] = pd.Series(pd.NA, index=result.index, dtype="boolean")
    if cow_available:
        # Verify the membership cache once, then compare exact inclusive dates;
        # avoid rereading all COW ZIP/CSV assets for every historical year.
        periods = membership_table(root)
        flags = pd.Series(False, index=result.index, dtype="boolean")
        for period in periods.itertuples(index=False):
            flags |= (
                result.country_code.eq(period.iso3)
                & result.aligned_date.ge(period.cow_membership_start)
                & result.aligned_date.le(period.cow_membership_end)
            )
        result["eligible_cow_jan1"] = flags
    result.attrs.update({
        "source_dataset": "GLI", "source_role": role, "source_url": GLI_URL,
        "source_sha256": sha256(source.read_bytes()).hexdigest(),
        "observation_date": "December 31 of source_year",
        "alignment": _ALIGNMENT,
        "source_year_range": [int(result.source_year.min()), int(result.source_year.max())],
        "aligned_year_range": [int(result.year.min()), int(result.year.max())],
        "cow_membership_available": cow_available,
        "missing_series": sorted(set(COUNTRY_METADATA) - set(result.country_code)),
        "unavailable_fields": ["eiec", "election_held", "system", "years_in_office"],
        "duration_definition": "Consecutive identical annual snapshots; gaps/unknowns reset; not exact tenure.",
        "measurement_note": "GLI classifies the officeholder; DPI classifies the chief executive's economic orientation. GLI used DPI among its coding sources, so disagreement is not independent validation.",
    })
    return result


def _coverage(frame: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for code, meta in COUNTRY_METADATA.items():
        block = frame.loc[frame.country_code.eq(code)]
        known = block.loc[block.state.isin(STATES)]
        rows.append({
            "country_code": code, "country_name": meta["name"],
            "source_rows": len(block), "role_present_rows": int(block.role_present.sum()),
            "classified_rows": len(known), "unknown_rows": len(block) - len(known),
            "absent_series": block.empty,
            "first_source_year": int(block.source_year.min()) if len(block) else pd.NA,
            "last_source_year": int(block.source_year.max()) if len(block) else pd.NA,
            "first_aligned_year": int(block.year.min()) if len(block) else pd.NA,
            "last_aligned_year": int(block.year.max()) if len(block) else pd.NA,
            "cow_eligible_rows": int(block.eligible_cow_jan1.fillna(False).sum()),
            "cow_eligibility_unknown_rows": int(block.eligible_cow_jan1.isna().sum()),
        })
    return pd.DataFrame(rows).sort_values("country_code").reset_index(drop=True)


def _comparison(dpi: pd.DataFrame, gli: pd.DataFrame) -> pd.DataFrame:
    first = max(int(dpi.year.min()), int(gli.year.min()))
    last = min(int(dpi.year.max()), int(gli.year.max()))
    if first > last:
        raise ValueError("No aligned DPI/GLI temporal overlap")
    grid = pd.MultiIndex.from_product([sorted(COUNTRY_METADATA), range(first, last + 1)], names=["country_code", "year"]).to_frame(index=False)
    left = dpi.loc[dpi.year.between(first, last), ["country_code", "year", "state", "ideology_raw", "executive_party"]].copy()
    left = left.rename(columns={"state": "dpi_state", "ideology_raw": "dpi_ideology_raw", "executive_party": "dpi_executive_party"})
    left["dpi_record_present"] = True
    right = gli.loc[gli.year.between(first, last), [
        "country_code", "year", "source_year", "observation_date", "aligned_date",
        "state", "ideology_raw", "executive_party", "leader_name", "source_role", "eligible_cow_jan1",
    ]].copy().rename(columns={
        "state": "gli_state", "ideology_raw": "gli_ideology_raw", "executive_party": "gli_executive_party",
        "observation_date": "gli_observation_date", "aligned_date": "gli_aligned_date",
    })
    right["gli_record_present"] = True
    result = grid.merge(left, on=["country_code", "year"], how="left", validate="one_to_one").merge(right, on=["country_code", "year"], how="left", validate="one_to_one")
    result["source_year"] = pd.to_numeric(result["source_year"], errors="raise").astype("Int64")
    for field in ["dpi_record_present", "gli_record_present"]:
        result[field] = result[field].eq(True)
    result["dpi_observation_date"] = result.year.astype(str) + "-01-01"
    dpi_known = result.dpi_state.isin(STATES)
    gli_known = result.gli_state.isin(STATES)
    result["both_classified"] = dpi_known & gli_known
    result["disagree"] = pd.Series(pd.NA, index=result.index, dtype="boolean")
    result.loc[result.both_classified, "disagree"] = result.loc[result.both_classified, "dpi_state"].ne(result.loc[result.both_classified, "gli_state"])
    result["comparison_status"] = np.select(
        [result.both_classified & result.disagree.fillna(False), result.both_classified,
         dpi_known, gli_known],
        ["both_known_disagree", "both_known_agree", "dpi_only_known", "gli_only_known"],
        default="neither_known",
    )
    result["country_name"] = result.country_code.map({code: meta["name"] for code, meta in COUNTRY_METADATA.items()})
    return result


def history_report(root: str | Path) -> dict:
    """Write separate panels, 35-country coverage, and aligned disagreement CSVs.

    No original metric, raw source, processed DPI panel, or model is changed.
    Report rates use only jointly classified rows; absence has its own counts.
    The output dictionary also contains written relative paths for a caller.
    """
    root = Path(root).resolve()
    output = root / "outputs" / "history"
    output.mkdir(parents=True, exist_ok=True)
    dpi = load_politics(root)
    summary = {
        "alignment": _ALIGNMENT, "primary_role": "hog", "roles": {}, "files": [],
        "dpi_source_url": dpi.attrs.get("source_url"),
        "dpi_source_sha256": sha256(_require_file(root, "dpi2023.csv").read_bytes()).hexdigest(),
    }
    manifest = json.loads((root / "data/raw/download_manifest.json").read_text(encoding="utf-8"))
    summary["dpi_manifest_original_sha256"] = manifest.get("sources", {}).get("dpi2023", {}).get("sha256")
    summary["dpi_cached_bytes_differ_from_original_hash"] = summary["dpi_source_sha256"] != summary["dpi_manifest_original_sha256"]
    if summary["dpi_cached_bytes_differ_from_original_hash"]:
        summary["dpi_cache_note"] = (
            "The public DPI loader verified exact restoration of original CRLF bytes from Git-normalized LF. "
            "dpi_source_sha256 fingerprints the local cached bytes; dpi_manifest_original_sha256 fingerprints the original download."
        )
    for role in ["hog", "leader"]:
        gli = load_gli(root, role=role)
        coverage = _coverage(gli)
        comparison = _comparison(dpi, gli)
        known = comparison.loc[comparison.both_classified]
        eligible_known = known.loc[known.eligible_cow_jan1.eq(True).fillna(False)]
        gli_eligible_known = gli.loc[gli.state.isin(STATES) & gli.eligible_cow_jan1.eq(True).fillna(False)]
        matrix = pd.crosstab(known.dpi_state, known.gli_state).reindex(index=STATES, columns=STATES, fill_value=0)
        matrix.index.name = "dpi_state"
        by_country = comparison.groupby(["country_code", "country_name"], as_index=False).agg(
            aligned_country_years=("year", "size"), dpi_records=("dpi_record_present", "sum"),
            gli_records=("gli_record_present", "sum"), jointly_classified=("both_classified", "sum"),
            disagreements=("disagree", "sum"),
        )
        by_country["disagreement_rate"] = by_country.disagreements.div(by_country.jointly_classified.replace(0, np.nan))
        absent_grid = pd.MultiIndex.from_product([sorted(COUNTRY_METADATA), range(int(gli.year.min()), int(gli.year.max()) + 1)], names=["country_code", "year"]).to_frame(index=False)
        observed = gli[["country_code", "year", "role_present", "state", "ideology_raw"]].copy()
        observed["gli_record_present"] = True
        absent_grid = absent_grid.merge(observed, on=["country_code", "year"], how="left", validate="one_to_one")
        absent_grid["gli_record_present"] = absent_grid.gli_record_present.eq(True)
        absent_grid["availability"] = np.select(
            [~absent_grid.gli_record_present, absent_grid.state.isin(STATES)],
            ["absent_record", "classified"], default="record_unknown_ideology",
        )
        role_summary = {
            "source_year_range": gli.attrs["source_year_range"], "aligned_year_range": gli.attrs["aligned_year_range"],
            "source_rows": len(gli), "source_countries": int(gli.country_code.nunique()),
            "classified_rows": int(gli.state.isin(STATES).sum()),
            "classified_countries": int(gli.loc[gli.state.isin(STATES), "country_code"].nunique()),
            "unknown_rows": int((~gli.state.isin(STATES)).sum()),
            "missing_series": gli.attrs["missing_series"],
            "role_never_classified": sorted(coverage.loc[(coverage.source_rows > 0) & coverage.classified_rows.eq(0), "country_code"]),
            "source_sha256": gli.attrs["source_sha256"], "source_url": gli.attrs["source_url"],
            "comparison_year_range": [int(comparison.year.min()), int(comparison.year.max())],
            "jointly_classified": len(known), "disagreements": int(known.disagree.sum()),
            "disagreement_rate": float(known.disagree.mean()) if len(known) else None,
            "jointly_classified_cow_eligible": len(eligible_known),
            "disagreements_cow_eligible": int(eligible_known.disagree.sum()),
            "disagreement_rate_cow_eligible": float(eligible_known.disagree.mean()) if len(eligible_known) else None,
            "comparison_status_counts": {str(k): int(v) for k, v in comparison.comparison_status.value_counts().items()},
            "absence_status_counts": {str(k): int(v) for k, v in absent_grid.availability.value_counts().items()},
            "cow_membership_available": gli.attrs["cow_membership_available"],
            "cow_eligible_rows": int(gli.eligible_cow_jan1.fillna(False).sum()),
            "classified_cow_eligible_rows": len(gli_eligible_known),
            "classified_cow_eligible_countries": int(gli_eligible_known.country_code.nunique()),
            "method_notes": gli.attrs,
        }
        for filename, table, index in [
            (f"gli_{role}_aligned_panel.csv", gli, False),
            (f"gli_{role}_coverage_35_countries.csv", coverage, False),
            (f"gli_{role}_availability_grid.csv", absent_grid, False),
            (f"dpi_gli_{role}_aligned_comparison.csv", comparison, False),
            (f"dpi_gli_{role}_disagreements.csv", comparison.loc[comparison.disagree.fillna(False)], False),
            (f"dpi_gli_{role}_confusion.csv", matrix, True),
            (f"dpi_gli_{role}_comparison_by_country.csv", by_country, False),
        ]:
            table.to_csv(output / filename, index=index)
            summary["files"].append(str((output / filename).relative_to(root)))
        summary["roles"][role] = role_summary
    summary["method_notes"] = [
        "HOG is primary; leader is a separate sensitivity choice. No role fallback or GLI/DPI splice.",
        "1945-2020 are actual December 31 source years; 1946-2021 are aligned labels, not additional coverage.",
        "Retain source ideologies and explicitly filter eligible_cow_jan1 for historical analysis; COW membership is not legal independence.",
        "EIEC, EXELEC, government-system type and exact years in office are unavailable and remain missing. GLI democracy is not EIEC.",
        "Duration columns count consecutive identical snapshots; they cannot identify within-year exits/returns or exact tenure.",
        "Unknown/nonideological/not-applicable values remain distinct in ideology_raw; none is never Center.",
        "Disagreement rates condition on jointly classified observations and do not declare either source ground truth.",
        "GLI uses DPI among its source materials; this is a measurement sensitivity audit, not independent validation.",
        "January 1 inaugurations can differ from the preceding December 31 snapshot despite adjacent-date alignment.",
        "Fit historical persistence/Markov and parsimonious political models separately. Do not fabricate pre-1960 macro data or competitive-election filtering.",
    ]
    report_path = output / "history_report.json"
    report_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (output / "HISTORY_NOTES.txt").write_text("\n".join(summary["method_notes"]) + "\n", encoding="utf-8")
    return summary


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Separate GLI historical panels and date-aware DPI/GLI audit")
    parser.add_argument("--root", type=Path, default=Path.cwd())
    args = parser.parse_args()
    report = history_report(args.root)
    print(json.dumps({role: {key: value for key, value in result.items() if key != "method_notes"} for role, result in report["roles"].items()}, ensure_ascii=False, indent=2))
