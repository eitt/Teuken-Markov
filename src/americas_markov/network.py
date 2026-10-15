"""Observed COW land/water contiguity networks for the Americas.

``build_network`` selects actual COW annual observations for the requested
snapshot, defaulting to 2016, the source's last year. ``network_for_year`` uses
historical annual topology through 2016 and explicitly carries 2016 forward for
later political years. Only that post-2016 carry-forward is a temporal modeling
assumption; no future political outcomes determine edges. Countries outside the
COW state system in a historical year have zero rows and are identified
separately from geographic isolates. COW records membership/contiguity present
during any part of a year, so first-entry years require additional date alignment
when a political observation is taken on January 1.

Water edges follow COW's closest-border categories, not invented island links or
great-circle distances. By default, all observed land and water neighbors receive
equal binary adjacency before row normalization. A zero row remains zero; it
must never be interpreted as a politically centrist neighborhood.

Sources:
https://correlatesofwar.org/data-sets/direct-contiguity/
https://correlatesofwar.org/data-sets/state-system-membership/
"""

from __future__ import annotations

from datetime import date, datetime, timezone
from hashlib import sha256
from io import BytesIO
import json
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
import zipfile

import numpy as np
import pandas as pd


CONTIGUITY_URL = "https://correlatesofwar.org/wp-content/uploads/DirectContiguity320.zip"
STATES_URL = "https://correlatesofwar.org/wp-content/uploads/States2024.zip"
CONTIGUITY_SOURCE_PAGE = "https://correlatesofwar.org/data-sets/direct-contiguity/"
STATE_SOURCE_PAGE = "https://correlatesofwar.org/data-sets/state-system-membership/"

# ISO3 crosswalk checked against the actual official States2024/statelist2024.csv.
# COW abbreviations differ from ISO3 and must not be used as ISO3 identifiers.
COUNTRY_METADATA: dict[str, dict[str, object]] = {
    "USA": {"name": "United States of America", "cow_code": 2, "cow_abbreviation": "USA"},
    "CAN": {"name": "Canada", "cow_code": 20, "cow_abbreviation": "CAN"},
    "BHS": {"name": "Bahamas", "cow_code": 31, "cow_abbreviation": "BHM"},
    "CUB": {"name": "Cuba", "cow_code": 40, "cow_abbreviation": "CUB"},
    "HTI": {"name": "Haiti", "cow_code": 41, "cow_abbreviation": "HAI"},
    "DOM": {"name": "Dominican Republic", "cow_code": 42, "cow_abbreviation": "DOM"},
    "JAM": {"name": "Jamaica", "cow_code": 51, "cow_abbreviation": "JAM"},
    "TTO": {"name": "Trinidad and Tobago", "cow_code": 52, "cow_abbreviation": "TRI"},
    "BRB": {"name": "Barbados", "cow_code": 53, "cow_abbreviation": "BAR"},
    "DMA": {"name": "Dominica", "cow_code": 54, "cow_abbreviation": "DMA"},
    "GRD": {"name": "Grenada", "cow_code": 55, "cow_abbreviation": "GRN"},
    "LCA": {"name": "St. Lucia", "cow_code": 56, "cow_abbreviation": "SLU"},
    "VCT": {"name": "St. Vincent and the Grenadines", "cow_code": 57, "cow_abbreviation": "SVG"},
    "ATG": {"name": "Antigua & Barbuda", "cow_code": 58, "cow_abbreviation": "AAB"},
    "KNA": {"name": "St. Kitts and Nevis", "cow_code": 60, "cow_abbreviation": "SKN"},
    "MEX": {"name": "Mexico", "cow_code": 70, "cow_abbreviation": "MEX"},
    "BLZ": {"name": "Belize", "cow_code": 80, "cow_abbreviation": "BLZ"},
    "GTM": {"name": "Guatemala", "cow_code": 90, "cow_abbreviation": "GUA"},
    "HND": {"name": "Honduras", "cow_code": 91, "cow_abbreviation": "HON"},
    "SLV": {"name": "El Salvador", "cow_code": 92, "cow_abbreviation": "SAL"},
    "NIC": {"name": "Nicaragua", "cow_code": 93, "cow_abbreviation": "NIC"},
    "CRI": {"name": "Costa Rica", "cow_code": 94, "cow_abbreviation": "COS"},
    "PAN": {"name": "Panama", "cow_code": 95, "cow_abbreviation": "PAN"},
    "COL": {"name": "Colombia", "cow_code": 100, "cow_abbreviation": "COL"},
    "VEN": {"name": "Venezuela", "cow_code": 101, "cow_abbreviation": "VEN"},
    "GUY": {"name": "Guyana", "cow_code": 110, "cow_abbreviation": "GUY"},
    "SUR": {"name": "Suriname", "cow_code": 115, "cow_abbreviation": "SUR"},
    "ECU": {"name": "Ecuador", "cow_code": 130, "cow_abbreviation": "ECU"},
    "PER": {"name": "Peru", "cow_code": 135, "cow_abbreviation": "PER"},
    "BRA": {"name": "Brazil", "cow_code": 140, "cow_abbreviation": "BRA"},
    "BOL": {"name": "Bolivia", "cow_code": 145, "cow_abbreviation": "BOL"},
    "PRY": {"name": "Paraguay", "cow_code": 150, "cow_abbreviation": "PAR"},
    "CHL": {"name": "Chile", "cow_code": 155, "cow_abbreviation": "CHL"},
    "ARG": {"name": "Argentina", "cow_code": 160, "cow_abbreviation": "ARG"},
    "URY": {"name": "Uruguay", "cow_code": 165, "cow_abbreviation": "URU"},
}

# First COW-system entry is not synonymous with independence or sovereignty.
# Values checked in the downloaded official States2024 archive.
_COW_FIRST_ENTRY_YEARS = {
    "USA": 1816, "CAN": 1920, "BHS": 1973, "CUB": 1902, "HTI": 1859,
    "DOM": 1894, "JAM": 1962, "TTO": 1962, "BRB": 1966, "DMA": 1978,
    "GRD": 1974, "LCA": 1979, "VCT": 1979, "ATG": 1981, "KNA": 1983,
    "MEX": 1831, "BLZ": 1981, "GTM": 1868, "HND": 1899, "SLV": 1875,
    "NIC": 1900, "CRI": 1920, "PAN": 1903, "COL": 1831, "VEN": 1841,
    "GUY": 1966, "SUR": 1975, "ECU": 1854, "PER": 1839, "BRA": 1822,
    "BOL": 1848, "PRY": 1846, "CHL": 1839, "ARG": 1841, "URY": 1882,
}
for _iso3, _entry in _COW_FIRST_ENTRY_YEARS.items():
    COUNTRY_METADATA[_iso3]["cow_first_entry_year"] = _entry

COW_DISTANCE_CATEGORIES = {
    1: {"type": "land", "description": "land or river boundary"},
    2: {"type": "water", "description": "water separation <= 12 miles"},
    3: {"type": "water", "description": "water separation > 12 and <= 24 miles"},
    4: {"type": "water", "description": "water separation > 24 and <= 150 miles"},
    5: {"type": "water", "description": "water separation > 150 and <= 400 miles"},
}

_EXTRACTS = {
    "contiguity": {
        "url": CONTIGUITY_URL,
        "archive": "cow_direct_contiguity_v3.2.zip",
        "members": {
            "DirectContiguity320/contdird.csv": "cow_contdird_v3.2.csv",
            "DirectContiguity320/contdir.csv": "cow_contdir_v3.2.csv",
            "DirectContiguity320/Direct Contiguity Codebook.pdf": "cow_direct_contiguity_codebook_v3.2.pdf",
        },
    },
    "states": {
        "url": STATES_URL,
        "archive": "cow_states_v2024.zip",
        "members": {"States2024/statelist2024.csv": "cow_states_v2024.csv"},
    },
}


def _download_archive(url: str) -> bytes:
    request = Request(url, headers={"User-Agent": "AmericasMarkovResearch/0.1 (public-data download)"})
    try:
        with urlopen(request, timeout=60) as response:
            payload = response.read()
    except (HTTPError, URLError, TimeoutError, OSError) as exc:
        raise RuntimeError(f"Cannot download official COW data from {url}: {exc}") from exc
    if not zipfile.is_zipfile(BytesIO(payload)):
        raise RuntimeError(f"Official COW download is not a ZIP archive: {url}")
    return payload


def download_contiguity(root: str | Path, refresh: bool = False) -> dict:
    """Download official ZIPs, verify cached hashes, and extract only known files.

    ``root`` is the project root, not ``data/raw``. The return value contains the
    main archive's URL/SHA256/cached status plus per-source and per-member hashes.
    Errors are raised; there is no synthetic or alternative-topology fallback.
    With a valid cache this function needs no network connection.
    """
    root = Path(root).resolve()
    raw = root / "data" / "raw"
    raw.mkdir(parents=True, exist_ok=True)
    manifest_path = raw / "cow_contiguity_manifest.json"
    previous = {}
    if manifest_path.exists():
        try:
            previous = json.loads(manifest_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            if not refresh:
                raise RuntimeError(f"Invalid COW cache manifest: {manifest_path}; use refresh=True") from exc
    sources = {}
    observed_at = datetime.now(timezone.utc).isoformat()
    for key, definition in _EXTRACTS.items():
        archive = raw / definition["archive"]
        cached = archive.exists() and not refresh
        payload = archive.read_bytes() if cached else _download_archive(definition["url"])
        digest = sha256(payload).hexdigest()
        old = previous.get("sources", {}).get(key, {})
        if cached and old.get("sha256") and old["sha256"] != digest:
            raise RuntimeError(f"COW cached archive SHA256 mismatch: {archive}; use refresh=True")
        if not zipfile.is_zipfile(BytesIO(payload)):
            raise RuntimeError(f"Invalid cached COW ZIP: {archive}; use refresh=True")
        members = {}
        with zipfile.ZipFile(BytesIO(payload)) as zipped:
            available = set(zipped.namelist())
            for member, local_name in definition["members"].items():
                if member not in available:
                    raise RuntimeError(f"COW ZIP schema changed: required member {member!r} missing")
                data = zipped.read(member)  # selected files only; no extractall/path traversal
                local_path = raw / local_name
                if not local_path.exists() or local_path.read_bytes() != data:
                    local_path.write_bytes(data)
                members[local_name] = {
                    "archive_member": member,
                    "path": str(local_path.relative_to(root)),
                    "sha256": sha256(data).hexdigest(),
                    "bytes": len(data),
                }
        if not cached:
            temp = archive.with_name(archive.name + ".part")
            temp.write_bytes(payload)
            temp.replace(archive)
        sources[key] = {
            "url": definition["url"],
            "path": str(archive.relative_to(root)),
            "sha256": digest,
            "bytes": len(payload),
            "cached": cached,
            "downloaded_at_utc": old.get("downloaded_at_utc") if cached else observed_at,
            "members": members,
        }
    manifest = {
        "dataset": "COW Direct Contiguity",
        "version": "3.2",
        "coverage": [1816, 2016],
        "source_page": CONTIGUITY_SOURCE_PAGE,
        "state_codes_source_page": STATE_SOURCE_PAGE,
        "url": CONTIGUITY_URL,
        "sha256": sources["contiguity"]["sha256"],
        "cached": all(source["cached"] for source in sources.values()),
        "observed_at_utc": observed_at,
        "sources": sources,
        "citation": (
            "Stinnett, D. M., Tir, J., Schafer, P., Diehl, P. F., & Gochman, C. (2002). "
            "The Correlates of War Project Direct Contiguity Data, Version 3. "
            "Conflict Management and Peace Science, 19(2), 58-66. Dataset v3.2, 1816-2016."
        ),
    }
    manifest_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return manifest


def _load_and_validate(root: Path) -> tuple[pd.DataFrame, pd.DataFrame, dict]:
    raw = root / "data" / "raw"
    manifest_path = raw / "cow_contiguity_manifest.json"
    if not manifest_path.exists():
        raise RuntimeError("COW cache is missing. Run run.py --download first; the reader does not download implicitly.")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    for source_name, filename in [("contiguity", "cow_contdird_v3.2.csv"), ("states", "cow_states_v2024.csv")]:
        local_path = raw / filename
        if not local_path.exists():
            raise RuntimeError(f"Missing {filename}. Run run.py --download; offline mode does not download.")
        expected = manifest["sources"][source_name]["members"][filename]["sha256"]
        if sha256(local_path.read_bytes()).hexdigest() != expected:
            raise RuntimeError(f"COW SHA256 mismatch for {filename}; verify the file or download with --refresh.")
    edges = pd.read_csv(raw / "cow_contdird_v3.2.csv")
    states = pd.read_csv(raw / "cow_states_v2024.csv")
    required_edges = {"state1no", "state1ab", "state2no", "state2ab", "year", "conttype", "version"}
    required_states = {
        "stateabb", "ccode", "statenme", "styear", "stmonth", "stday",
        "endyear", "endmonth", "endday",
    }
    if not required_edges.issubset(edges.columns) or not required_states.issubset(states.columns):
        raise RuntimeError("Official COW CSV schema does not match the validated v3.2/v2024 schema")
    if not edges["conttype"].isin(COW_DISTANCE_CATEGORIES).all():
        raise RuntimeError("Unexpected COW contiguity category; refusing to infer edge types")
    if set(edges["version"].astype(str)) != {"3.2"}:
        raise RuntimeError("Unexpected COW Direct Contiguity version")
    if edges["year"].min() != 1816 or edges["year"].max() != 2016:
        raise RuntimeError("Unexpected COW Direct Contiguity temporal coverage")
    known = states[["ccode", "stateabb", "statenme"]].drop_duplicates()
    for iso3, meta in COUNTRY_METADATA.items():
        match = known.loc[known["ccode"] == meta["cow_code"]]
        if len(match) != 1:
            raise RuntimeError(f"COW code for {iso3} is absent or ambiguous in the official state list")
        source = match.iloc[0]
        if source["stateabb"] != meta["cow_abbreviation"] or source["statenme"] != meta["name"]:
            raise RuntimeError(f"COW country crosswalk mismatch for {iso3}: {source.to_dict()}")
        first_entry = int(states.loc[states["ccode"] == meta["cow_code"], "styear"].min())
        if first_entry != meta["cow_first_entry_year"]:
            raise RuntimeError(f"COW first-entry year mismatch for {iso3}")
    return edges, states, manifest


def build_network(
    root: str | Path,
    country_codes: list[str],
    snapshot_year: int = 2016,
    include_water: bool = True,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Return row-normalized ISO3 weights and a directed observed edge table.

    ``distancecategory`` contains original COW integer categories 1--5. It is
    not an exact distance. Edges have columns ``src,dst,type,distancecategory``.
    Weights retain the caller's country order. Metadata in ``weights.attrs``
    reports isolated and historically inactive nodes and the temporal assumption.
    Only neighbors in ``country_codes`` are retained before normalization.
    """
    if not isinstance(snapshot_year, (int, np.integer)) or isinstance(snapshot_year, bool):
        raise ValueError("snapshot_year must be an integer in COW coverage 1816-2016")
    snapshot_year = int(snapshot_year)
    if not 1816 <= snapshot_year <= 2016:
        raise ValueError("COW Direct Contiguity v3.2 covers 1816-2016; no newer topology will be fabricated")
    if not isinstance(include_water, (bool, np.bool_)):
        raise ValueError("include_water must be Boolean")
    codes = list(country_codes)
    if not codes:
        raise ValueError("country_codes must contain at least one ISO3 code")
    if len(codes) != len(set(codes)):
        raise ValueError("country_codes contains duplicate ISO3 identifiers")
    unknown = [code for code in codes if code not in COUNTRY_METADATA]
    if unknown:
        raise ValueError(f"Unsupported Americas ISO3 codes: {unknown}; use COUNTRY_METADATA keys")
    root = Path(root).resolve()
    raw_edges, states, manifest = _load_and_validate(root)
    lookup = {int(COUNTRY_METADATA[code]["cow_code"]): code for code in codes}
    subset = raw_edges.loc[
        (raw_edges["year"] == snapshot_year)
        & raw_edges["state1no"].isin(lookup)
        & raw_edges["state2no"].isin(lookup)
    ].copy()
    if not include_water:
        subset = subset.loc[subset["conttype"] == 1]
    if subset.duplicated(["state1no", "state2no"]).any():
        raise RuntimeError("Duplicate COW dyad-year observations; refusing to collapse inconsistent edges")
    triples = set(zip(subset["state1no"], subset["state2no"], subset["conttype"]))
    reversed_triples = set(zip(subset["state2no"], subset["state1no"], subset["conttype"]))
    if triples != reversed_triples:
        raise RuntimeError("Observed directed COW edges are not symmetric")
    result_edges = pd.DataFrame({
        "src": subset["state1no"].map(lookup),
        "dst": subset["state2no"].map(lookup),
        "type": subset["conttype"].map(lambda category: COW_DISTANCE_CATEGORIES[int(category)]["type"]),
        "distancecategory": subset["conttype"].astype(int),
    }).sort_values(["src", "dst"]).reset_index(drop=True)
    adjacency = pd.DataFrame(0.0, index=codes, columns=codes)
    adjacency.index.name = "iso3"
    adjacency.columns.name = "iso3"
    for edge in result_edges.itertuples(index=False):
        if edge.src == edge.dst:
            raise RuntimeError("Unexpected self-edge in COW contiguity data")
        adjacency.loc[edge.src, edge.dst] = 1.0
    degrees = adjacency.sum(axis=1)
    weights = adjacency.div(degrees.replace(0, np.nan), axis=0).fillna(0.0)
    active = states.loc[(states["styear"] <= snapshot_year) & (states["endyear"] >= snapshot_year), "ccode"]
    active_codes = set(active.astype(int))
    inactive = [code for code in codes if int(COUNTRY_METADATA[code]["cow_code"]) not in active_codes]
    if any(adjacency.loc[code].any() for code in inactive):
        raise RuntimeError("COW contiguity edge references a historically inactive state")
    weights.attrs = {
        "source": CONTIGUITY_SOURCE_PAGE,
        "source_url": CONTIGUITY_URL,
        "source_sha256": manifest["sha256"],
        "snapshot_year": snapshot_year,
        "include_water": bool(include_water),
        "normalization": "binary observed adjacency, row-normalized within requested country set",
        "isolated_codes": degrees.index[degrees.eq(0)].tolist(),
        "inactive_codes": inactive,
        "degree": {code: int(degrees.loc[code]) for code in codes},
        "is_isolated": {code: bool(degrees.loc[code] == 0) for code in codes},
        "topology_mode": "observed_annual",
        "temporal_assumption": (
            f"Observed COW annual contiguity for {snapshot_year}. A 2016 snapshot may be "
            "carried forward only for political years 2017+ with that assumption documented. "
            "COW's closest within-year contiguity is not an exact January 1 observation."
        ),
        "distancecategory_legend": COW_DISTANCE_CATEGORIES,
    }
    result_edges.attrs = {
        "directed": True,
        "snapshot_year": snapshot_year,
        "distancecategory_legend": COW_DISTANCE_CATEGORIES,
        "source_sha256": manifest["sha256"],
    }
    return weights, result_edges


def network_for_year(
    root: str | Path, country_codes: list[str], year: int, include_water: bool = True
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Use historical annual geography and explicit post-2016 carry-forward.

    Requested states not yet in the international system remain explicitly
    inactive zero rows. Years 2017+ retain the observed 2016 graph as a disclosed
    modeling assumption, rather than manufacturing new observations.
    """
    if not isinstance(year, (int, np.integer)) or isinstance(year, bool) or year < 1816:
        raise ValueError("year must be an integer >= 1816")
    year = int(year)
    weights, edges = build_network(root, country_codes, snapshot_year=min(year, 2016), include_water=include_water)
    weights.attrs["political_year"] = year
    edges.attrs["political_year"] = year
    if year > 2016:
        weights.attrs["topology_mode"] = "carry_forward_2016"
        weights.attrs["temporal_assumption"] = (
            f"Political year {year}: COW geography is observed only through 2016; "
            "the 2016 graph is carried forward explicitly. No post-2016 edges are observed."
        )
    return weights, edges


def membership_table(root: str | Path) -> pd.DataFrame:
    """Verified COW membership periods with dates, distinct from independence.

    Multiple periods are retained for states that exited and reentered the system.
    These dates permit a caller to check membership on January 1 specifically.
    """
    _, states, _ = _load_and_validate(Path(root).resolve())
    lookup = {int(meta["cow_code"]): code for code, meta in COUNTRY_METADATA.items()}
    result = states.loc[states["ccode"].isin(lookup)].copy()
    result.insert(0, "iso3", result["ccode"].map(lookup))
    for prefix, output in [("st", "cow_membership_start"), ("end", "cow_membership_end")]:
        dates = result[[f"{prefix}year", f"{prefix}month", f"{prefix}day"]].rename(
            columns={f"{prefix}year": "year", f"{prefix}month": "month", f"{prefix}day": "day"}
        )
        result[output] = pd.to_datetime(dates).dt.strftime("%Y-%m-%d")
    return result[["iso3", "ccode", "stateabb", "statenme", "cow_membership_start", "cow_membership_end"]].reset_index(drop=True)


def eligible_on(root: str | Path, dateISO_or_date: str | date) -> list[str]:
    """Americas ISO3 states in the official COW system on an exact date.

    This is a COW membership proxy, not an assertion of exact legal sovereignty
    or independence dates. Coverage ends on 2024-12-31; future membership is not
    silently extrapolated. Date intervals are inclusive at both ends. The return
    list follows ``COUNTRY_METADATA`` order, with at most one entry per country.
    """
    if isinstance(dateISO_or_date, datetime):
        when = dateISO_or_date.date()
    elif isinstance(dateISO_or_date, date):
        when = dateISO_or_date
    elif isinstance(dateISO_or_date, str):
        try:
            when = date.fromisoformat(dateISO_or_date)
        except ValueError as exc:
            raise ValueError("dateISO_or_date must be an ISO calendar date (YYYY-MM-DD)") from exc
    else:
        raise TypeError("dateISO_or_date must be a date object or ISO calendar-date string")
    if not date(1816, 1, 1) <= when <= date(2024, 12, 31):
        raise ValueError("COW State System Membership v2024 covers 1816-01-01..2024-12-31")
    periods = membership_table(root)
    iso_date = when.isoformat()
    present = set(periods.loc[
        (periods["cow_membership_start"] <= iso_date)
        & (periods["cow_membership_end"] >= iso_date),
        "iso3",
    ])
    return [code for code in COUNTRY_METADATA if code in present]


def isolation_flags(weights: pd.DataFrame) -> pd.Series:
    """Boolean zero-degree indicator; isolates are not assigned a neutral state."""
    return weights.abs().sum(axis=1).eq(0).rename("is_isolated")
