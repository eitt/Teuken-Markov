"""Publication maps from frozen DPI and COW results, with real GeoJSON outlines.

No model is refitted. Lambert azimuthal equal-area is implemented on a sphere
(radius 6371 km), centred at 90 W, 10 N; the Caribbean uses 75 W, 18 N.
National data join MODEL_ISO3, not territorial sovereign-parent fields.
"""
from __future__ import annotations

import argparse
from hashlib import sha256
import json
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib import patheffects
from matplotlib.colors import Normalize
from matplotlib.lines import Line2D
from matplotlib.path import Path as MplPath
from matplotlib.patches import PathPatch, Patch, Polygon
import numpy as np
import pandas as pd

from .geographic import load_americas_geojson, polygon_rings
from .network import COUNTRY_METADATA, build_network

WIDTH_MM, HEIGHT_MM = 160, 185
COLORS = {"Left": "#0072B2", "Center": "#777777", "Right": "#D55E00",
          "Unknown": "#fafafa", "NoDPI": "#ffffff", "Context": "#e1e5e8"}
LETTER = {"Left": "L", "Center": "C", "Right": "R", "Unknown": "?", "NoDPI": "–"}
STATE_EN = {"Left": "Left", "Center": "Center", "Right": "Right",
            "Unknown": "Unclassified", "NoDPI": "No DPI coverage"}
MAIN_CODES = ["CAN", "USA", "MEX", "COL", "VEN", "GUY", "SUR", "ECU", "PER", "BRA", "BOL", "PRY", "CHL", "ARG", "URY"]
SMALL_CODES = {"ATG", "BRB", "DMA", "GRD", "KNA", "LCA", "VCT", "TTO"}
# Callout positions only; country geometry and node positions are never moved.
CARIB_LABELS = {
    "GTM": (-92, 16.1), "BLZ": (-89.4, 20), "HND": (-84.7, 16.5),
    "SLV": (-91.5, 11.8), "NIC": (-83.5, 13), "CRI": (-88, 8.9),
    "PAN": (-78.8, 7.2), "CUB": (-78.5, 23.2), "BHS": (-76.8, 28.1),
    "JAM": (-78.7, 16.7), "HTI": (-74.0, 21.1), "DOM": (-67.4, 21.8),
    "ATG": (-57, 23.8), "KNA": (-57, 21.7), "DMA": (-57, 19.6),
    "LCA": (-57, 17.5), "VCT": (-57, 15.4), "BRB": (-57, 13.3),
    "GRD": (-64.7, 10.2), "TTO": (-60.7, 8.1),
}


def project(lon, lat, lon0=-90.0, lat0=10.0):
    """Spherical LAEA forward projection (longitude, latitude -> km)."""
    lon, lat = np.deg2rad(np.asarray(lon)), np.deg2rad(np.asarray(lat))
    p0 = np.deg2rad(lat0)
    d = (lon - np.deg2rad(lon0) + np.pi) % (2 * np.pi) - np.pi
    denom = 1 + np.sin(p0) * np.sin(lat) + np.cos(p0) * np.cos(lat) * np.cos(d)
    if np.any(denom <= 1e-12):
        raise ValueError("LAEA antipode is outside the supported Americas domain")
    k = np.sqrt(2 / denom)
    return (6371 * k * np.cos(lat) * np.sin(d),
            6371 * k * (np.cos(p0) * np.sin(lat) - np.sin(p0) * np.cos(lat) * np.cos(d)))


def country_names(features: list[dict]) -> dict[str, str]:
    """Full English country names from Natural Earth NAME_EN.

    The two source map units Antigua/Barbuda share one national observation;
    their NAME_EN values are joined into the national name for the data export.
    """
    names = {}
    for feature in features:
        p = feature["properties"]
        if p["MODEL_ISO3"]:
            names[p["MODEL_ISO3"]] = p["NAME_EN"]
    names["ATG"] = "Antigua and Barbuda"
    if set(names) != set(COUNTRY_METADATA):
        raise ValueError("Missing English country names in verified cartography")
    return names


def state_table(dpi: pd.DataFrame) -> pd.DataFrame:
    """Exactly one country row; source unknown and absent coverage are distinct."""
    required = {"country_code", "year", "state", "ideology_raw"}
    if not required.issubset(dpi.columns):
        raise ValueError("Missing required DPI state columns")
    current = dpi.loc[dpi.year.eq(2023)].copy()
    if current.country_code.duplicated().any():
        raise ValueError("Duplicate January 2023 country observation")
    if not current.country_code.isin(COUNTRY_METADATA).all():
        raise ValueError("DPI country is outside the 35-country map universe")
    if not current.state.dropna().isin(["Left", "Center", "Right"]).all():
        raise ValueError("Unexpected DPI state label")
    universe = pd.DataFrame({"country_code": sorted(COUNTRY_METADATA)})
    states = universe.merge(current[["country_code", "state", "ideology_raw"]],
                            on="country_code", how="left", validate="one_to_one", indicator=True)
    states["map_state"] = np.where(states._merge.eq("left_only"), "NoDPI", states.state.fillna("Unknown"))
    states["state_label"] = states.map_state.map(STATE_EN)
    states["symbol"] = states.map_state.map(LETTER)
    states["observation_date"] = "2023-01-01"
    return states.drop(columns="_merge")


def transition_table(predictions: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Observed changes on unique Markov evaluation pairs, never pooled models."""
    required = {"model", "country_code", "year", "target_year", "state", "target_state", "changed"}
    if not required.issubset(predictions.columns):
        raise ValueError("Missing required evaluated-transition columns")
    pairs = predictions.loc[predictions.model.eq("markov")].copy()
    if pairs.empty:
        raise ValueError("No Markov evaluation pairs available")
    if pairs.duplicated(["country_code", "year"]).any():
        raise ValueError("Duplicate Markov country/origin; models must not be pooled")
    if not pairs.country_code.isin(COUNTRY_METADATA).all():
        raise ValueError("Evaluation country is outside the 35-country map universe")
    for column in ["year", "target_year"]:
        numeric = pd.to_numeric(pairs[column], errors="raise")
        if numeric.isna().any() or not numeric.eq(numeric.astype(int)).all():
            raise ValueError("Noninteger transition year")
        pairs[column] = numeric.astype(int)
    if not pairs.target_year.eq(pairs.year + 1).all():
        raise ValueError("Expected consecutive January observations")
    if not all(pairs[col].isin(["Left", "Center", "Right"]).all() for col in ["state", "target_state"]):
        raise ValueError("Evaluation pairs must have both observed states")
    truth = pairs.state.ne(pairs.target_state)
    supplied = pairs.changed.map({True: True, False: False, "True": True, "False": False,
                                  "true": True, "false": False})
    if supplied.isna().any() or not supplied.eq(truth).all():
        raise ValueError("Changed flag must match the two observed states")
    pairs["changed"] = truth
    rates = pairs.groupby("country_code", as_index=False).agg(
        n_pairs=("changed", "size"), n_changes=("changed", "sum"),
        first_origin=("year", "min"), last_origin=("year", "max"))
    universe = pd.DataFrame({"country_code": sorted(COUNTRY_METADATA)})
    rates = universe.merge(rates, on="country_code", how="left", validate="one_to_one")
    for column in ["n_pairs", "n_changes", "first_origin", "last_origin"]:
        rates[column] = rates[column].astype("Int64")
    rates["change_pct"] = (100 * rates.n_changes / rates.n_pairs).astype(float)
    rates["low_coverage"] = rates.n_pairs.lt(10).fillna(False)
    rates["map_state"] = np.where(rates.n_pairs.isna(), "NoPairs", "Observed")
    return rates, pairs.sort_values(["country_code", "year"])


def undirected_edges(edges: pd.DataFrame) -> pd.DataFrame:
    """One verified link per unordered pair; no invented island connections."""
    edges = edges.copy()
    if not {"src", "dst", "type", "distancecategory"}.issubset(edges.columns):
        raise ValueError("Missing COW edge schema")
    if not edges.type.isin(["land", "water"]).all() or edges.src.eq(edges.dst).any():
        raise ValueError("Invalid COW connection type or self-edge")
    edges["pair_a"] = edges[["src", "dst"]].min(axis=1)
    edges["pair_b"] = edges[["src", "dst"]].max(axis=1)
    for column in ["type", "distancecategory"]:
        if edges.groupby(["pair_a", "pair_b"])[column].nunique().gt(1).any():
            raise ValueError("Contradictory COW connection category")
    return edges.drop_duplicates(["pair_a", "pair_b"]).sort_values(["pair_a", "pair_b"]).reset_index(drop=True)


def map_tables(root: Path):
    states = state_table(pd.read_csv(root / "data/processed/dpi_americas.csv"))
    rates, pairs = transition_table(pd.read_csv(root / "outputs/extensions/dpi_drivers/predictions.csv"))
    codes = states.loc[states.map_state.ne("NoDPI"), "country_code"].tolist()
    _, directed = build_network(root, codes, snapshot_year=2016, include_water=True)
    return states, rates, undirected_edges(directed), pairs


def polygon_path(rings, lon0=-90, lat0=10):
    """Compound path with opposite hole winding; preserves all source rings."""
    vertices, codes = [], []
    for idx, ring in enumerate(rings):
        p = np.asarray(ring, dtype=float)
        x, y = project(p[:, 0], p[:, 1], lon0, lat0)
        xy = np.column_stack([x, y])
        area = np.sum(xy[:-1, 0] * xy[1:, 1] - xy[1:, 0] * xy[:-1, 1])
        if (idx == 0 and area < 0) or (idx > 0 and area > 0):
            xy = xy[::-1]
        vertices.extend(xy)
        codes.extend([MplPath.MOVETO] + [MplPath.LINETO] * (len(xy) - 2) + [MplPath.CLOSEPOLY])
    return MplPath(vertices, codes)


def label_points(features):
    """Natural Earth label coordinates; first map unit per sovereign country."""
    points = {}
    for f in features:
        p = f["properties"]
        if p["MODEL_ISO3"] and p["MODEL_ISO3"] not in points:
            points[p["MODEL_ISO3"]] = (p["LABEL_X"], p["LABEL_Y"])
    return points


def base_axes(fig, features):
    ax = fig.add_axes([.012, .175, .975, .805])
    pts = np.array([q for f in features for p in polygon_rings(f) for q in p[0]])
    x, y = project(pts[:, 0], pts[:, 1])
    ax.set_xlim(x.min() - 180, x.max() + 180)
    ax.set_ylim(y.min() - 140, y.max() + 140)
    ax.set_aspect("equal")
    ax.axis("off")
    # Geographic inset in the unoccupied southeast Pacific; same in every map.
    inset = fig.add_axes([.014, .195, .445, .345], facecolor="white")
    inset.set_xlim(-2150, 2250)
    inset.set_ylim(-1300, 1320)
    inset.set_aspect("equal", adjustable="box")
    inset.set_xticks([]); inset.set_yticks([])
    for spine in inset.spines.values():
        spine.set_color("#69737c"); spine.set_linewidth(.5)
    inset.text(.025, 1.015, "Caribbean inset", transform=inset.transAxes,
               fontsize=8, va="bottom", color="#343b42")
    # Show extent on the main map, using a densified geographic rectangle.
    lon = np.r_[np.linspace(-94, -54, 80), np.repeat(-54, 45),
                np.linspace(-54, -94, 80), np.repeat(-94, 45)]
    lat = np.r_[np.repeat(7, 80), np.linspace(7, 30, 45),
                np.repeat(30, 80), np.linspace(30, 7, 45)]
    xx, yy = project(lon, lat)
    ax.add_patch(Polygon(np.c_[xx, yy], fill=False, ec="#6b747c", lw=.5, ls=(0, (3, 3)), zorder=7))
    return ax, inset


def draw_land(ax, features, records, mode, lon0=-90, lat0=10, rate_max=25):
    norm = Normalize(0, rate_max)
    for feature in features:
        code = feature["properties"]["MODEL_ISO3"]
        rec = records.get(code)
        hatch, edge = None, "#4e575f"
        if not code:
            face, edge = COLORS["Context"], "#9ba3aa"
        elif mode == "state":
            category = rec["map_state"]
            face = COLORS[category]
            hatch = "////" if category == "Unknown" else ("xx" if category == "NoDPI" else None)
        elif mode == "rate":
            face = COLORS["NoDPI"] if rec["map_state"] != "Observed" else plt.colormaps["cividis"](norm(rec["change_pct"]))
            hatch = "xx" if rec["map_state"] != "Observed" else ("////" if rec["low_coverage"] else None)
        else:
            face = "#f1f3f4" if code in records else "#ffffff"
            hatch = "xx" if code not in records else None
        for rings in polygon_rings(feature):
            ax.add_patch(PathPatch(polygon_path(rings, lon0, lat0), fc=face, ec=edge,
                                   lw=.35 if mode != "network" else .3, hatch=hatch, zorder=2))


def draw_labels(ax, points, records, mode, inset=False):
    origin = (-75, 18) if inset else (-90, 10)
    codes = CARIB_LABELS if inset else MAIN_CODES
    halo = [patheffects.withStroke(linewidth=1.6, foreground="white")]
    for code in codes:
        if code not in points:
            continue
        if mode == "network" and code not in records:
            continue
        point = points[code]
        anchor = CARIB_LABELS[code] if inset else point
        if mode == "rate" and inset and code in {"ATG", "KNA", "DMA", "LCA", "VCT", "BRB"}:
            anchor = (-58.5, anchor[1])
        if not inset and code == "CHL":
            anchor = (-80, -36)
        if not inset and code == "GUY":
            anchor = (-52, 11) if mode == "rate" else (-53, 8.4)
        if not inset and code == "SUR":
            anchor = (-47, 3) if mode == "rate" else (-49, 4.8)
        if not inset and code == "URY":
            anchor = (-47, -34.5)
        px, py = project(*point, *origin)
        tx, ty = project(*anchor, *origin)
        if inset or anchor != point:
            ax.plot([px, tx], [py, ty], color="#626c73", lw=.45, zorder=8)
        text = code
        if mode == "state":
            text += " " + LETTER[records[code]["map_state"]]
        elif mode == "rate":
            rec = records[code]
            separator = " " if inset and code in {"ATG", "KNA", "DMA", "LCA", "VCT", "BRB", "PAN"} else "\n"
            text += separator + (f"{rec['change_pct']:.1f}%" + ("*" if rec["low_coverage"] else "") if rec["map_state"] == "Observed" else "–")
        ax.text(tx, ty, text, ha="center", va="center", fontsize=7 if inset else 7.3,
                weight="normal", color="#19242d", path_effects=halo, zorder=10)


def island_markers(ax, points, records, mode, rate_max=25):
    for code in SMALL_CODES:
        px, py = project(*points[code], -75, 18)
        if mode == "state":
            face = COLORS[records[code]["map_state"]]
        elif mode == "rate":
            rec = records[code]
            face = "white" if rec["map_state"] != "Observed" else plt.colormaps["cividis"](rec["change_pct"] / rate_max)
        else:
            continue
        ax.plot(px, py, "o", markersize=2.5, mfc=face, mec="#26323b", mew=.35, zorder=8)


def connection_curves(edges, points, lon0, lat0):
    """Densified great-circle links; topology from COW, no inferred new edges."""
    for e in edges.itertuples():
        a, b = np.deg2rad(points[e.pair_a]), np.deg2rad(points[e.pair_b])
        v = [np.array([np.cos(p[1])*np.cos(p[0]), np.cos(p[1])*np.sin(p[0]), np.sin(p[1])]) for p in (a, b)]
        omega = np.arccos(np.clip(v[0] @ v[1], -1, 1))
        t = np.linspace(0, 1, 40)
        q = (np.sin((1-t)*omega)[:, None]*v[0] + np.sin(t*omega)[:, None]*v[1]) / np.sin(omega)
        lon = np.rad2deg(np.arctan2(q[:, 1], q[:, 0]))
        lat = np.rad2deg(np.arctan2(q[:, 2], np.hypot(q[:, 0], q[:, 1])))
        x, y = project(lon, lat, lon0, lat0)
        yield e.type, x, y


def draw_network(ax, edges, points, lon0=-90, lat0=10):
    for kind, x, y in connection_curves(edges, points, lon0, lat0):
        ax.plot(x, y, color="#274a66" if kind == "land" else "#8b6195",
                lw=.65 if kind == "land" else .5, alpha=.85,
                ls="-" if kind == "land" else (0, (2.4, 2)), zorder=5)
    nodes = sorted(set(edges.pair_a) | set(edges.pair_b))
    x, y = project(*np.array([points[c] for c in nodes]).T, lon0, lat0)
    ax.scatter(x, y, s=11, facecolors="white", edgecolors="#26323b", linewidths=.55, zorder=9)


def build_maps(root: str | Path, folder: str | Path, publication: bool = True) -> list[dict]:
    """Render three English publication maps from existing observed outputs.

    Outputs are confined to the supplied folder. This function never refits a
    model, downloads geometry, inherits sovereign-parent labels, or crops the
    physical canvas. Metadata contains a self-contained caption for each map.
    """
    root, folder = Path(root).resolve(), Path(folder).resolve()
    features = load_americas_geojson(root)["features"]
    states, rates, edges, pairs = map_tables(root)
    names, points = country_names(features), label_points(features)
    states["country_name"] = states.country_code.map(names)
    rates["country_name"] = rates.country_code.map(names)
    folder.mkdir(parents=True, exist_ok=True)
    states.to_csv(folder / "Figure_01_data.csv", index=False)
    rates.to_csv(folder / "Figure_03_data.csv", index=False)
    edge_export = edges.copy()
    edge_export["country_a_name"] = edge_export.pair_a.map(names)
    edge_export["country_b_name"] = edge_export.pair_b.map(names)
    edge_export.to_csv(folder / "Supplement_01_data.csv", index=False)
    node_codes = sorted(states.loc[states.map_state.ne("NoDPI"), "country_code"])
    pd.DataFrame([{"country_code": c, "country_name": names[c], "label_lon": points[c][0],
                   "label_lat": points[c][1], "coordinate_definition": "Natural Earth LABEL_X/LABEL_Y; not a capital"}
                  for c in node_codes]).to_csv(folder / "Supplement_01_nodes.csv", index=False)
    plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 8, "svg.fonttype": "none",
                         "pdf.fonttype": 42, "hatch.linewidth": .35, "savefig.facecolor": "white"})
    n_changes, n_pairs = int(pairs.changed.sum()), len(pairs)
    first, last = int(pairs.year.min()), int(pairs.year.max())
    count = states.map_state.value_counts().to_dict()
    low = rates.loc[rates.low_coverage, ["country_code", "n_changes", "n_pairs"]]
    low_detail = "; ".join(f"{r.country_code} {r.n_changes}/{r.n_pairs}" for r in low.itertuples()) or "none"
    rate_max = max(5, 5 * np.ceil(rates.change_pct.max() / 5))
    land, water = int(edges.type.eq("land").sum()), int(edges.type.eq("water").sum())
    metadata = [
        {"id": "Figure_01", "stem": "Figure_01", "role": "main", "width_mm": WIDTH_MM, "height_mm": HEIGHT_MM,
         "title": "Executive-party economic orientation on 1 January 2023",
         "caption": f"Figure 1. DPI classification on 1 January 2023 for all 35 sovereign countries in the Americas: {count.get('Left', 0)} Left (L), {count.get('Center', 0)} Center (C), {count.get('Right', 0)} Right (R), {count.get('Unknown', 0)} unclassified (?) and {count.get('NoDPI', 0)} without DPI coverage (–). Panama has an observation but no ideological classification. Dependent territories are neutral context. Caribbean circles locate eight small countries; marker size does not encode population or area. Source map units are preserved, including two units for Antigua and Barbuda sharing one national observation. The map shows the source's executive-party coding at the stated date. Canada is shown as Right because that is its DPI classification on 1 January 2023; source coding is preserved. Natural Earth v5.1.1 provides a generalized base map, not annual boundary reconstructions.",
         "source": "DPI 2023; Natural Earth Admin 0 Map Units 1:50m, layer v5.1.1, repository release v5.1.2."},
        {"id": "Figure_03", "stem": "Figure_03", "role": "main", "width_mm": WIDTH_MM, "height_mm": HEIGHT_MM,
         "title": f"Observed ideological-transition frequency, origins {first}–{last}",
         "caption": f"Figure 3. Observed annual changes in DPI class as a percentage of each country's available evaluated transitions: {n_changes} changes across {n_pairs} unique country-origin pairs, origins {first}–{last} and target years {first+1}–{last+1}. The calculation uses the Markov model's evaluation rows once, without pooling models; values are observed change frequencies, not predicted probabilities or forecasting accuracy. Country denominators are provided in Figure_03_data.csv. Hatching and an asterisk indicate fewer than ten observed pairs: {low_detail}. Cross-hatching marks no available evaluated pairs; dependent territories are neutral context. Coverage marks are descriptive, not tests of significance. Natural Earth v5.1.1 provides a generalized base map; the origin-year range does not indicate reconstructed historical boundaries.",
         "source": "outputs/extensions/dpi_drivers/predictions.csv, model=markov; Natural Earth Admin 0 Map Units v5.1.1."},
        {"id": "Supplement_01", "stem": "Supplement_01", "role": "supplement", "width_mm": WIDTH_MM, "height_mm": HEIGHT_MM,
         "title": "Geographic model connections in the 2016 COW snapshot",
         "caption": f"Supplementary Figure 1. COW Direct Contiguity v3.2 supplies {len(edges)} unique undirected pairs among {len(node_codes)} DPI-covered countries: {land} land connections (solid) and {water} water connections (dashed). All source water-distance categories up to 400 miles are included; links represent contiguity categories, not displayed line length. Natural Earth label points locate nodes and are not capitals. One great-circle link is drawn per pair without arrows; equal line widths within each type do not encode intensity. The source ends in 2016: historical evaluation uses min(t−1, 2016), and later graphs carry forward that snapshot. Connectivity is a model exposure assumption and does not establish causal diffusion. Countries without DPI coverage are outside this graph; territories remain neutral context. Natural Earth v5.1.1 provides a generalized base map, not a reconstruction of 2016 boundaries.",
         "source": "COW Direct Contiguity v3.2, 2016 snapshot; Natural Earth Admin 0 Map Units v5.1.1."},
    ]
    for meta, mode, data in zip(metadata, ["state", "rate", "network"],
                                [states, rates, states.loc[states.map_state.ne("NoDPI")]]):
        records = data.set_index("country_code").to_dict("index")
        fig = plt.figure(figsize=(WIDTH_MM / 25.4, HEIGHT_MM / 25.4))
        ax, inset = base_axes(fig, features)
        draw_land(ax, features, records, mode, rate_max=rate_max)
        draw_land(inset, features, records, mode, -75, 18, rate_max)
        if mode == "network":
            draw_network(ax, edges, points)
            draw_network(inset, edges, points, -75, 18)
        else:
            island_markers(inset, points, records, mode, rate_max)
        draw_labels(ax, points, records, mode)
        draw_labels(inset, points, records, mode, inset=True)
        if mode == "state":
            handles = [Patch(fc=COLORS[c], ec="#4e575f", hatch="////" if c == "Unknown" else ("xx" if c == "NoDPI" else None), label=STATE_EN[c] + " (" + LETTER[c] + ")") for c in ["Left", "Center", "Right", "Unknown", "NoDPI"]]
            handles.append(Patch(fc=COLORS["Context"], ec="#9ba3aa", label="Territorial context"))
            fig.legend(handles=handles, loc="lower left", bbox_to_anchor=(.03, .035), ncol=2,
                       frameon=False, fontsize=7.5, handlelength=1.6, columnspacing=1.2, labelspacing=.8)
            summary = f"{count.get('Left', 0)} Left · {count.get('Center', 0)} Center · {count.get('Right', 0)} Right · {count.get('Unknown', 0)} unclassified"
            fig.text(.04, .151, "1 January 2023 | " + summary, fontsize=7.4)
        elif mode == "rate":
            cax = fig.add_axes([.10, .12, .8, .018])
            cb = fig.colorbar(plt.cm.ScalarMappable(norm=Normalize(0, rate_max), cmap="cividis"),
                             cax=cax, orientation="horizontal", ticks=np.linspace(0, rate_max, 6))
            cb.ax.tick_params(labelsize=7, length=2, pad=2)
            cb.outline.set_linewidth(.45)
            cax.set_xlabel("Observed changes / available annual pairs (%)", fontsize=8, labelpad=3)
            fig.legend(handles=[Patch(fc="white", ec="#4e575f", hatch="////", label="n < 10 (*)"), Patch(fc="white", ec="#4e575f", hatch="xx", label="No evaluated pairs"), Patch(fc=COLORS["Context"], ec="#9ba3aa", label="Context")], loc="lower center", bbox_to_anchor=(.5, .005), ncol=3, fontsize=7.4, frameon=False, handlelength=1.6)
            fig.text(.04, .173, f"Origins {first}–{last} | {n_changes} changes / {n_pairs:,} observed pairs", fontsize=7.4)
        else:
            handles = [Line2D([0], [0], color="#274a66", lw=.9, label=f"Land: {land} pairs"), Line2D([0], [0], color="#8b6195", lw=.9, ls="--", label=f"Water: {water} pairs"), Line2D([0], [0], marker="o", color="none", mec="#26323b", mfc="white", ms=3.2, label=f"Model country: {len(node_codes)} nodes"), Patch(fc="white", ec="#4e575f", hatch="xx", label="No DPI: outside the graph")]
            fig.legend(handles=handles, loc="lower left", bbox_to_anchor=(.03, .045), ncol=2, fontsize=7.5, frameon=False, handlelength=2.1, labelspacing=.9, columnspacing=1)
            fig.text(.04, .151, f"COW 2016 | {len(node_codes)} countries · {len(edges)} undirected connections", fontsize=7.4)
        fig.text(.04, .014 if mode != "rate" else .153,
                 "Natural Earth 1:50m | Spherical equal-area LAEA projection", fontsize=7, color="#606972")
        stem = meta["stem"]
        for ext in ["svg", "pdf"]:
            fig.savefig(folder / f"{stem}_master.{ext}")
        fig.savefig(folder / f"{stem}_300dpi.png", dpi=300)
        if publication:
            fig.savefig(folder / f"{stem}_600dpi.png", dpi=600)
        plt.close(fig)
        (folder / f"{stem}_caption.txt").write_text(meta["caption"] + "\n" + meta["source"] + "\n", encoding="utf-8")
    inputs = ["data/processed/dpi_americas.csv", "outputs/extensions/dpi_drivers/predictions.csv",
              "data/raw/cow_contdird_v3.2.csv", "data/raw/cow_states_v2024.csv",
              "data/cartography/americas_map_units_50m.geojson.gz"]
    manifest = {"width_mm": WIDTH_MM, "height_mm": HEIGHT_MM,
                "projection": "Spherical LAEA, R=6371 km; main lon0=-90 lat0=10; Caribbean lon0=-75 lat0=18",
                "join": "Natural Earth ISO_A3_EH -> MODEL_ISO3 -> country_code; no territorial inheritance",
                "inputs": {p: sha256((root / p).read_bytes()).hexdigest() for p in inputs},
                "states_2023": count, "evaluated_pairs": n_pairs, "observed_changes": n_changes,
                "origins": [first, last], "low_coverage": low.country_code.tolist(),
                "edges": {"pairs": len(edges), "land": land, "water": water, "nodes": len(node_codes)},
                "source_geometry_unchanged": True, "sovereign_countries": 35,
                "source_map_units": len(features), "territorial_context_units": 20,
                "filters_and_aggregations": {
                    "Figure_01": "DPI year==2023; explicit 35-country outer join; source absence and unknown classification remain distinct",
                    "Figure_03": "model==markov; unique country/year consecutive observed pairs; pct=100*sum(changed)/count(changed); n<10 flag",
                    "Supplement_01": "verified COW 2016; DPI-covered nodes; one unordered edge per pair with unique type/distance category"},
                "raster_dpi": [300, 600] if publication else [300],
                "raster_pixels": {"300": [1889, 2185], "600": [3779, 4370]},
                "uncertainty": "Descriptive observed frequencies; no confidence interval or causal effect inferred"}
    (folder / "map_mapping_manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n")
    return metadata


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[2])
    parser.add_argument("--folder", type=Path)
    parser.add_argument("--review-only", action="store_true")
    args = parser.parse_args()
    folder = args.folder or args.root / "outputs/publication_figures"
    print(json.dumps(build_maps(args.root, folder, not args.review_only), indent=2))


if __name__ == "__main__":
    main()
