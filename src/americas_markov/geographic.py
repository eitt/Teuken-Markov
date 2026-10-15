"""Verified Natural Earth geography, separate from political observations.

Map units are required: the countries layer groups overseas France into a
country geometry. These units separate French Guiana/Guadeloupe/Martinique and
other territories, allowing neutral context without borrowing a parent state's
political observation. Geometries are the source's generalized, de facto base
map; they are not annual historical reconstructions or legal boundary claims.

The original GeoJSON is OGC CRS84: WGS84 longitude, latitude (x, y) in degrees.
The source's ``ISO_A3_EH`` covers all 35 sovereign American model countries.
Antigua and Barbuda has two map-unit features (Antigua and Barbuda); both have
ISO_A3=-99 and ISO_A3_EH=ATG and must receive the same country-level observation.
Do not join political data on ADMIN, SOVEREIGNT, or SOV_A3: those fields also
identify sovereign parents of unmodeled territories.

No geopandas, shapely, networkx, or pyproj dependency is required to load these
assets or iterate their source polygon rings. Projection/rendering belongs to
the plotting layer and must keep axis order longitude, latitude.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import gzip
from hashlib import sha256
import json
import math
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from .network import COUNTRY_METADATA


SOURCE_REPOSITORY = "https://github.com/nvkelso/natural-earth-vector"
REPOSITORY_RELEASE = "v5.1.2"
DATASET_VERSION = "5.1.1"
SOURCE_PAGE = "https://www.naturalearthdata.com/downloads/50m-cultural-vectors/50m-admin-0-countries-2/"
TERMS_URL = "https://www.naturalearthdata.com/about/terms-of-use/"
_BASE = f"https://raw.githubusercontent.com/nvkelso/natural-earth-vector/{REPOSITORY_RELEASE}"
_ASSETS = {
    "ne_50m_admin_0_map_units.geojson": (
        f"{_BASE}/geojson/ne_50m_admin_0_map_units.geojson",
        "b8d421aca6e9e08e8cdf09cc26af111cc3e0deba4fe915611d58ade71e8a4db0",
    ),
    "ne_50m_admin_0_map_units.VERSION.txt": (
        f"{_BASE}/50m_cultural/ne_50m_admin_0_map_units.VERSION.txt",
        "f9893302cd3158f3b5aea394dcd2a91574869e9e6ff69e9235b10a3bf8c983fb",
    ),
    "ne_50m_admin_0_map_units.README.html": (
        f"{_BASE}/50m_cultural/ne_50m_admin_0_map_units.README.html",
        "1f63a3454f4fd04acfa8758dc401bfc3e419a98909a7471480acbadc65955e3b",
    ),
    "natural_earth_LICENSE.md": (
        f"{_BASE}/LICENSE.md",
        "2631b5b39b6d1acc56de75235109b5af2dbb4b0ac5a127b6f06185977247fd4b",
    ),
}


def polygon_rings(feature: dict):
    """Yield source polygons as lists of rings (exterior first, then holes).

    Multipolygon components remain separate. Never concatenate them into one
    ring, which would introduce fabricated connecting boundaries.
    """
    geometry = feature.get("geometry") or {}
    kind = geometry.get("type")
    coordinates = geometry.get("coordinates", [])
    if kind == "Polygon":
        yield coordinates
    elif kind == "MultiPolygon":
        yield from coordinates
    else:
        raise ValueError(f"Expected Polygon or MultiPolygon, got {kind!r}")


def _validate_geojson(document: dict) -> dict:
    if document.get("type") != "FeatureCollection":
        raise RuntimeError("Natural Earth asset is not a GeoJSON FeatureCollection")
    crs = document.get("crs", {}).get("properties", {}).get("name")
    if crs != "urn:ogc:def:crs:OGC:1.3:CRS84":
        raise RuntimeError(f"Unverified source coordinate reference system: {crs!r}")
    features = document.get("features", [])
    if len(features) != 265:
        raise RuntimeError("Natural Earth pinned map-units feature count changed")
    counts = {code: 0 for code in COUNTRY_METADATA}
    selected = []
    fields = {"ISO_A3_EH", "ISO_A3", "ADM0_A3", "GU_A3", "ADMIN", "SOVEREIGNT", "NAME", "CONTINENT", "LABEL_X", "LABEL_Y"}
    for feature in features:
        properties = feature.get("properties", {})
        if not fields.issubset(properties):
            raise RuntimeError("Natural Earth map-units property schema changed")
        for polygon in polygon_rings(feature):
            if not polygon:
                raise RuntimeError("Empty source polygon")
            for ring in polygon:
                if len(ring) < 4 or ring[0] != ring[-1]:
                    raise RuntimeError("Source polygon ring is empty or unclosed")
                for point in ring:
                    if len(point) < 2 or not all(isinstance(value, (float, int)) and math.isfinite(value) for value in point[:2]):
                        raise RuntimeError("Nonfinite source coordinate")
                    if not -180 <= point[0] <= 180 or not -90 <= point[1] <= 90:
                        raise RuntimeError("Source coordinates exceed verified CRS84 longitude/latitude bounds")
        if properties["CONTINENT"] in {"North America", "South America"}:
            selected.append(feature)
            code = properties["ISO_A3_EH"]
            if code in counts:
                counts[code] += 1
    missing = [code for code, count in counts.items() if count == 0]
    if missing:
        raise RuntimeError(f"Natural Earth map units lack model-country polygons: {missing}")
    if counts["ATG"] != 2 or any(count != 1 for code, count in counts.items() if code != "ATG"):
        raise RuntimeError("Unexpected sovereign-country/map-unit crosswalk multiplicity")
    return {
        "global_features": len(features),
        "americas_features": len(selected),
        "model_country_count": len(counts),
        "model_features": sum(counts.values()),
        "context_features": len(selected) - sum(counts.values()),
        "country_feature_counts": counts,
        "missing_model_countries": missing,
        "context_iso3": sorted({feature["properties"]["ISO_A3_EH"] for feature in selected if feature["properties"]["ISO_A3_EH"] not in counts}),
    }


SUBSET_SHA256 = "b80f0f76c2fd24b3c5bb7ea84d63043ff2528e6ab6257aea7161d81d4c884680"
COMPRESSED_NAME = "americas_map_units_50m.geojson.gz"


def _americas_subset(document: dict) -> dict:
    selected = []
    for feature in document["features"]:
        if feature["properties"]["CONTINENT"] not in {"North America", "South America"}:
            continue
        feature = {**feature, "properties": dict(feature["properties"])}
        code = feature["properties"]["ISO_A3_EH"]
        feature["properties"]["MODEL_ISO3"] = code if code in COUNTRY_METADATA else None
        feature["properties"]["IS_MODEL_COUNTRY"] = code in COUNTRY_METADATA
        selected.append(feature)
    return {"type": "FeatureCollection", "name": "Natural Earth Americas map units",
            "crs": document["crs"], "features": selected}


def download_cartography(root: str | Path, refresh: bool = False) -> dict:
    """Explicitly download pinned source assets, retaining a compressed subset.

    The global source is verified in memory and its SHA256 is recorded. All
    Americas source properties/geometries are preserved exactly; two model join
    properties are appended. No network retrieval occurs in the loader.
    """
    root = Path(root).resolve()
    folder = root / "data" / "cartography"
    folder.mkdir(parents=True, exist_ok=True)
    if not refresh and (folder / COMPRESSED_NAME).exists():
        load_americas_geojson(root)
        return json.loads((folder / "cartography_manifest.json").read_text())
    assets, global_payload = {}, None
    for name, (url, expected) in _ASSETS.items():
        try:
            with urlopen(Request(url, headers={"User-Agent": "AmericasMarkovResearch/0.1"}), timeout=60) as response:
                payload = response.read()
        except (HTTPError, URLError, TimeoutError, OSError) as exc:
            raise RuntimeError(f"Cannot retrieve verified Natural Earth asset {url}: {exc}") from exc
        digest = sha256(payload).hexdigest()
        if digest != expected:
            raise RuntimeError(f"Natural Earth SHA256 mismatch for {name}")
        retain = not name.endswith(".geojson")
        if retain:
            (folder / name).write_bytes(payload)
        else:
            global_payload = payload
        assets[name] = {"url": url, "sha256": digest, "bytes": len(payload),
                        "path": str((folder / name).relative_to(root)), "retained": retain}
    document = json.loads(global_payload)
    coverage = _validate_geojson(document)
    subset = _americas_subset(document)
    raw = json.dumps(subset, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    if sha256(raw).hexdigest() != SUBSET_SHA256:
        raise RuntimeError("Pinned Americas subset bytes changed")
    compressed = gzip.compress(raw, compresslevel=9, mtime=0)
    (folder / COMPRESSED_NAME).write_bytes(compressed)
    manifest = {
        "dataset": "Natural Earth Admin 0 Map Units", "scale": "1:50,000,000",
        "repository": SOURCE_REPOSITORY, "repository_release": REPOSITORY_RELEASE,
        "dataset_version": DATASET_VERSION, "source_page": SOURCE_PAGE,
        "license": "Public domain", "license_url": TERMS_URL,
        "observed_at_utc": datetime.now(timezone.utc).isoformat(),
        "crs": "OGC:CRS84; WGS84 longitude, latitude in degrees",
        "join_field": "ISO_A3_EH -> MODEL_ISO3; never sovereign-parent inheritance",
        "coverage": coverage, "assets": assets,
        "derived_subset": {
            "path": str((folder / COMPRESSED_NAME).relative_to(root)),
            "sha256": sha256(compressed).hexdigest(), "bytes": len(compressed),
            "uncompressed_sha256": SUBSET_SHA256, "uncompressed_bytes": len(raw),
            "compression": "gzip; deterministic mtime=0", "geometry_unchanged": True},
        "boundary_convention": "Natural Earth de facto generalized cartography; not annual political-boundary reconstructions",
        "offline_loading": "Retrieval occurs only through explicit download_cartography or --download.",
        "limitations": ["Small Caribbean polygons require an inset or labels.",
                        "Antigua and Barbuda retains two map units with ISO_A3_EH=ATG.",
                        "Dependencies are neutral context, never inherited country observations.",
                        "Source de facto contours do not settle legal boundary claims."],
    }
    (folder / "cartography_manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n")
    load_americas_geojson(root)
    return manifest


def _validate_subset(document: dict) -> None:
    if document.get("type") != "FeatureCollection":
        raise RuntimeError("Expected Americas FeatureCollection")
    if document.get("crs", {}).get("properties", {}).get("name") != "urn:ogc:def:crs:OGC:1.3:CRS84":
        raise RuntimeError("Unverified subset coordinate reference system")
    features = document.get("features", [])
    if len(features) != 56:
        raise RuntimeError("Expected 56 Americas map units")
    counts = {code: 0 for code in COUNTRY_METADATA}
    for feature in features:
        p = feature.get("properties", {})
        source_code = p.get("ISO_A3_EH")
        expected = source_code if source_code in counts else None
        if p.get("MODEL_ISO3") != expected or p.get("IS_MODEL_COUNTRY") != (expected is not None):
            raise RuntimeError("Invalid territorial/model country join")
        if not p.get("NAME_EN"):
            raise RuntimeError("Natural Earth English name unavailable")
        if expected:
            counts[expected] += 1
        for polygon in polygon_rings(feature):
            if not polygon or any(len(ring) < 4 or ring[0] != ring[-1] for ring in polygon):
                raise RuntimeError("Invalid source polygon rings")
    if counts["ATG"] != 2 or any(n != 1 for code, n in counts.items() if code != "ATG"):
        raise RuntimeError("Expected 35 countries, including two Antigua/Barbuda map units")


def load_americas_geojson(root: str | Path, include_context: bool = True) -> dict:
    """Load the SHA256-verified compressed subset entirely offline.

    Absence or corruption fails loudly. Call download_cartography explicitly to
    obtain missing assets. Compression is lossless; uncompressed bytes match the
    original pinned Americas subset, whose geometry was compared to the source.
    """
    folder = Path(root).resolve() / "data" / "cartography"
    path, manifest_path = folder / COMPRESSED_NAME, folder / "cartography_manifest.json"
    if not path.exists() or not manifest_path.exists():
        raise FileNotFoundError("Verified offline cartography unavailable; run geographic --download explicitly")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if (manifest.get("repository_release"), manifest.get("dataset_version")) != (REPOSITORY_RELEASE, DATASET_VERSION):
        raise RuntimeError("Unverified Natural Earth release/layer version")
    source = manifest.get("assets", {}).get("ne_50m_admin_0_map_units.geojson", {})
    if source.get("sha256") != _ASSETS["ne_50m_admin_0_map_units.geojson"][1]:
        raise RuntimeError("Unverified global cartography source SHA256")
    compressed = path.read_bytes()
    subset = manifest.get("derived_subset", {})
    if sha256(compressed).hexdigest() != subset.get("sha256"):
        raise RuntimeError("Compressed cartography SHA256 mismatch")
    try:
        raw = gzip.decompress(compressed)
    except (OSError, EOFError) as exc:
        raise RuntimeError("Invalid compressed cartography") from exc
    if sha256(raw).hexdigest() != SUBSET_SHA256 or subset.get("uncompressed_sha256") != SUBSET_SHA256:
        raise RuntimeError("Uncompressed cartography SHA256 mismatch")
    document = json.loads(raw)
    _validate_subset(document)
    if not include_context:
        document["features"] = [f for f in document["features"] if f["properties"]["IS_MODEL_COUNTRY"]]
    return document


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[2])
    parser.add_argument("--download", action="store_true", help="Explicitly retrieve pinned public source files")
    parser.add_argument("--refresh", action="store_true")
    args = parser.parse_args()
    result = download_cartography(args.root, refresh=args.refresh) if args.download else {"features": len(load_americas_geojson(args.root)["features"])}
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
