"""Publication figures from frozen tables and predictions, without model fitting.

The public entry point is ``build_charts(root, folder, publication=True)``.
All marks derive from cached political snapshots or stored result CSVs. Figure
captions are returned as metadata for a separate page-layout/book assembler.
Exports retain fixed physical dimensions: SVG/PDF vector masters and PNGs at
300 dpi, plus 600 dpi when ``publication`` is true. No tight-bounding-box crop,
inferential confidence interval, synthetic observation or model refit is used.
"""

from __future__ import annotations

from pathlib import Path
import json

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D
from matplotlib.patches import Patch
from matplotlib.ticker import PercentFormatter
import numpy as np
import pandas as pd
from sklearn.metrics import precision_recall_curve

from . import STATES
from .artifacts import read_artifact_csv, resolve_artifact
from .data import load_politics
from .network import COUNTRY_METADATA


STATE_COLORS = {"Left": "#0072B2", "Center": "#777777", "Right": "#D55E00"}
STATE_MARKERS = {"Left": "o", "Center": "s", "Right": "^"}
MODEL_ORDER = ["persistence", "markov", "lean", "lean_oil", "lean_enso", "lean_oil_enso"]
MODEL_LABELS = {
    "persistence": "Persistence", "markov": "Markov", "lean": "Reduced controls",
    "lean_oil": "+ oil", "lean_enso": "+ ENSO", "lean_oil_enso": "+ oil + ENSO",
}
MODEL_COLORS = {"markov": "#555555", "lean_oil_enso": "#0072B2"}
SCENARIO_LABELS = {
    "constant_conditions": "Constant conditions",
    "hypothetical_recession": "Hypothetical recession",
    "hypothetical_energy_food": "Hypothetical energy and food shock",
}
_STYLE = {
    "font.family": "DejaVu Sans", "font.size": 8,
    "axes.labelsize": 8.5, "xtick.labelsize": 7.5, "ytick.labelsize": 7.5,
    "legend.fontsize": 7.5, "axes.titlesize": 9,
    "axes.spines.top": False, "axes.spines.right": False,
    "svg.fonttype": "none", "pdf.fonttype": 42, "savefig.bbox": None,
}


def _csv(root: Path, relative: str, required=()) -> pd.DataFrame:
    path = resolve_artifact(Path(root) / relative)
    if not path.is_file():
        raise FileNotFoundError(f"Frozen figure input is missing: {path}. Copy the stored results; do not refit to draw this figure.")
    result = read_artifact_csv(path)
    missing = set(required) - set(result.columns)
    if missing:
        raise ValueError(f"{relative}: required columns missing: {sorted(missing)}")
    return result


def _bool(values: pd.Series) -> pd.Series:
    if values.dtype == bool:
        return values
    labels = values.astype(str).str.lower().str.strip()
    if not labels.isin(["true", "false", "1", "0"]).all():
        raise ValueError("Boolean observation fields must contain True/False or 1/0.")
    return labels.isin(["true", "1"])


def _country_name(code: str) -> str:
    return str(COUNTRY_METADATA[code]["name"])


def _short_name(code: str) -> str:
    return {
        "USA": "United States", "TTO": "Trinidad & Tobago",
        "VCT": "St. Vincent & Grenadines", "KNA": "St. Kitts & Nevis",
    }.get(code, _country_name(code))


def history_composition(frame: pd.DataFrame, year_column: str = "year", dataset_label: str = "") -> pd.DataFrame:
    """State shares of a fixed 35-country registry, with unknown/absent counts."""
    needed = {"country_code", "state", year_column}
    if not needed.issubset(frame.columns):
        raise ValueError(f"History frame lacks {sorted(needed - set(frame.columns))}")
    selected = frame[["country_code", "state", year_column]].copy()
    selected = selected.rename(columns={year_column: "year"})
    if not selected.country_code.isin(COUNTRY_METADATA).all():
        raise ValueError("History frame contains countries outside the 35-country Americas registry.")
    if selected.duplicated(["country_code", "year"]).any():
        raise ValueError("History composition cannot pool duplicate country/year observations.")
    if not selected.state.dropna().isin(STATES).all():
        raise ValueError("History composition accepts only Left/Center/Right or explicit missing states.")
    rows = []
    for year, group in selected.groupby("year", sort=True):
        known = int(group.state.notna().sum())
        unknown = int(group.state.isna().sum())
        absent = len(COUNTRY_METADATA) - int(len(group))
        counts = {state: int(group.state.eq(state).sum()) for state in STATES}
        counts.update(Unknown=unknown, Absent=absent)
        for state, count in counts.items():
            rows.append({
                "dataset": dataset_label, "year": int(year), "state": state,
                "count": count, "share_registry": count / len(COUNTRY_METADATA),
                "classified_count": known, "unknown_count": unknown,
                "absent_count": absent, "coverage_classified": known / len(COUNTRY_METADATA),
            })
    return pd.DataFrame(rows)


def argmax_change_counts(predictions: pd.DataFrame) -> pd.DataFrame:
    """Exact counts from stored argmax states, not a new decision threshold."""
    required = {"model", "state", "target_state", "changed", "predicted_state"}
    if not required.issubset(predictions.columns):
        raise ValueError(f"Stored predictions lack {sorted(required - set(predictions.columns))}")
    data = predictions.copy()
    data["changed"] = _bool(data["changed"])
    rows = []
    for model, group in data.groupby("model", sort=False):
        changed = group.changed
        exact_correct = group.predicted_state.eq(group.target_state)
        predicted_change = group.predicted_state.ne(group.state)
        rows.append({
            "model_id": model, "n": int(len(group)), "observed_changes": int(changed.sum()),
            "correct_change_states": int((changed & exact_correct).sum()),
            "false_change_predictions": int((~changed & predicted_change).sum()),
        })
    return pd.DataFrame(rows)


def calibration_bins(predictions: pd.DataFrame, models=("markov", "lean_oil_enso"), n_bins: int = 10) -> pd.DataFrame:
    """Equal-width reliability bins; retain empty bins as n=0 and rates=NaN."""
    if n_bins < 1:
        raise ValueError("n_bins must be positive")
    required = {"model", "p_change", "changed"}
    if not required.issubset(predictions.columns):
        raise ValueError("Stored predictions lack model, p_change or changed.")
    rows = []
    for model in models:
        group = predictions.loc[predictions.model.eq(model)].copy()
        if group.empty:
            raise ValueError(f"Stored predictions contain no observations for {model}.")
        group["changed"] = _bool(group.changed)
        probability = pd.to_numeric(group.p_change, errors="raise")
        if probability.isna().any() or not probability.between(0, 1).all():
            raise ValueError("p_change must contain finite probabilities in [0,1].")
        bins = np.minimum(np.floor(probability.to_numpy() * n_bins).astype(int), n_bins - 1)
        for index in range(n_bins):
            part = group.loc[bins == index]
            rows.append({
                "model_id": model, "bin_index": index,
                "bin_lower": index / n_bins, "bin_upper": (index + 1) / n_bins,
                "n": int(len(part)),
                "mean_predicted_change_probability": float(part.p_change.mean()) if len(part) else np.nan,
                "observed_change_frequency": float(part.changed.mean()) if len(part) else np.nan,
            })
    return pd.DataFrame(rows)


def precision_recall_data(predictions: pd.DataFrame, models=("markov", "lean_oil_enso")) -> pd.DataFrame:
    """Descriptive precision/recall coordinates from frozen binary probabilities."""
    rows = []
    for model in models:
        group = predictions.loc[predictions.model.eq(model)]
        if group.empty:
            raise ValueError(f"Stored predictions contain no observations for {model}.")
        changed = _bool(group.changed).astype(int)
        precision, recall, threshold = precision_recall_curve(changed, group.p_change)
        for index, (p, r) in enumerate(zip(precision, recall)):
            rows.append({
                "model_id": model, "point_index": index, "precision": float(p),
                "recall": float(r), "probability_threshold": float(threshold[index]) if index < len(threshold) else np.nan,
                "n": int(len(group)), "observed_changes": int(changed.sum()),
            })
    return pd.DataFrame(rows)


def oil_probability_contrasts(scenarios: pd.DataFrame) -> pd.DataFrame:
    """Pair +/-50% with frozen 0% national baselines; return probability-point changes."""
    required = {"country_code", "year", "state", "scenario_oil_growth", "p_left", "p_center", "p_right",
                "fuel_import_share_prior", "fuel_export_share_prior"}
    if not required.issubset(scenarios.columns):
        raise ValueError(f"Conditional oil table lacks {sorted(required - set(scenarios.columns))}")
    data = scenarios.copy()
    if not data.state.isin(STATES).all():
        raise ValueError("Conditional scenarios require observed initial states.")
    if data.duplicated(["country_code", "year", "scenario_oil_growth"]).any():
        raise ValueError("Conditional oil table contains duplicate country/year/scenario rows.")
    complete = data.groupby(["country_code", "year"]).scenario_oil_growth.agg(lambda x: set(x) == {-50, 0, 50})
    if complete.empty or not complete.all():
        raise ValueError("Each country/year requires exactly -50%, 0% and +50% stored oil scenarios.")
    probabilities = data[["p_left", "p_center", "p_right"]].to_numpy(dtype=float)
    if not np.isfinite(probabilities).all() or (probabilities < 0).any() or (probabilities > 1).any():
        raise ValueError("Conditional oil probabilities are invalid.")
    if not np.allclose(probabilities.sum(axis=1), 1, atol=1e-8):
        raise ValueError("Conditional oil state probabilities must sum to one.")
    state_index = data.state.map({"Left": 0, "Center": 1, "Right": 2}).to_numpy()
    data["p_change"] = 1 - probabilities[np.arange(len(data)), state_index]
    baseline = data.loc[data.scenario_oil_growth.eq(0), ["country_code", "year", "state", "p_change"]]
    baseline = baseline.rename(columns={"p_change": "baseline_p_change"})
    contrasts = data.loc[data.scenario_oil_growth.isin([-50, 50])].merge(
        baseline, on=["country_code", "year", "state"], how="left", validate="many_to_one"
    )
    if contrasts.baseline_p_change.isna().any():
        raise ValueError("Every conditional oil contrast requires its stored 0% country baseline.")
    counts = contrasts.groupby(["country_code", "year"]).scenario_oil_growth.nunique()
    if not counts.eq(2).all():
        raise ValueError("Each country needs both -50% and +50% oil contrasts.")
    contrasts["delta_change_pp"] = 100 * (contrasts.p_change - contrasts.baseline_p_change)
    contrasts["exposure_missing"] = contrasts[["fuel_import_share_prior", "fuel_export_share_prior"]].isna().any(axis=1)
    contrasts["country_name"] = contrasts.country_code.map(_country_name)
    return contrasts.sort_values(["country_code", "scenario_oil_growth"]).reset_index(drop=True)


def export_figure(fig, folder: Path, stem: str, width_mm: float, height_mm: float, publication: bool = True) -> list[Path]:
    """Export fixed-size vector masters and true-resolution PNGs without cropping."""
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    fig.set_size_inches(width_mm / 25.4, height_mm / 25.4, forward=True)
    paths = []
    with plt.rc_context({"savefig.bbox": None, "svg.fonttype": "none", "pdf.fonttype": 42}):
        for extension in ("svg", "pdf"):
            path = folder / f"{stem}_master.{extension}"
            fig.savefig(path, format=extension, facecolor="white")
            paths.append(path)
        for dpi in ([300, 600] if publication else [300]):
            path = folder / f"{stem}_{dpi}dpi.png"
            fig.savefig(path, dpi=dpi, facecolor="white")
            paths.append(path)
    plt.close(fig)
    return paths


def _save_data(frame: pd.DataFrame, folder: Path, stem: str) -> None:
    Path(folder).mkdir(parents=True, exist_ok=True)
    frame.to_csv(Path(folder) / f"{stem}_data.csv", index=False)


def _metadata(identifier: str, title: str, caption: str, source: str, height: float, role="main") -> dict:
    stem = f"Figure_{identifier}" if role == "main" else f"Supplement_{identifier}"
    return dict(id=stem, title=title, caption=caption, source=source,
                width_mm=160.0, height_mm=float(height),
                stem=stem, role=role)


def _panel(ax, label: str) -> None:
    ax.text(0, 1.035, label, transform=ax.transAxes, va="bottom", ha="left", fontsize=9)


def _state_legend():
    return [Line2D([], [], color=STATE_COLORS[state], marker=STATE_MARKERS[state], lw=1.4, label=state) for state in STATES]


def _history_figure(root: Path, folder: Path, publication: bool) -> dict:
    dpi = load_politics(root)
    gli = _csv(root, "outputs/history/gli_hog_aligned_panel.csv", ["country_code", "state", "source_year"])
    compositions = [history_composition(dpi, "year", "DPI"), history_composition(gli, "source_year", "GLI HOG")]
    fig, axes = plt.subplots(2, 1, figsize=(160 / 25.4, 175 / 25.4))
    for ax, data, label, date_label in zip(axes, compositions,
        ["(a) DPI: January 1 snapshots", "(b) GLI HOG: December 31 snapshots"],
        ["DPI observation year", "GLI source year"]):
        pivot = data.pivot(index="year", columns="state", values="share_registry").sort_index()
        years = pivot.index.to_numpy()
        shares = [100 * pivot[state].to_numpy() for state in STATES]
        ax.stackplot(years, shares, colors=[STATE_COLORS[state] for state in STATES], linewidth=0, step="post")
        classified = sum(shares)
        present = classified + 100 * pivot["Unknown"].to_numpy()
        ax.fill_between(years, classified, present, color="#D7D7D7", linewidth=0, step="post")
        ax.fill_between(years, present, 100, facecolor="white", edgecolor="#A7A7A7", hatch="////", linewidth=0.25, step="post")
        ax.step(years, classified, color="#252525", ls="--", lw=1.1, where="post")
        ax.set_ylim(0, 100)
        ax.set_xlim(years[0], years[-1])
        ticks = sorted(set([int(years[0]), *[year for year in range(int(years[0]), int(years[-1]) + 1) if year % 10 == 0], int(years[-1])]))
        ax.set_xticks(ticks)
        ax.set_ylabel("Share of 35-country\nregistry (%)")
        ax.set_xlabel(date_label)
        ax.grid(axis="y", color="#E6E6E6", lw=0.5, alpha=0.6)
        _panel(ax, label)
        yearly = data.drop_duplicates("year").set_index("year")
        ax.text(.985, .05, f"Classified n: {int(yearly.iloc[0].classified_count)} → {int(yearly.iloc[-1].classified_count)}", transform=ax.transAxes,
                ha="right", va="bottom", fontsize=7.5, bbox=dict(facecolor="white", edgecolor="none", alpha=.9, pad=2))
    legend = [Patch(facecolor=STATE_COLORS[state], label=state) for state in STATES]
    legend.extend([Patch(facecolor="#D7D7D7", label="Recorded, unclassified"),
                   Patch(facecolor="white", edgecolor="#A7A7A7", hatch="////", label="No source record"),
                   Line2D([], [], color="#252525", ls="--", label="Classified coverage")])
    fig.legend(handles=legend, loc="upper center", ncol=3, frameon=False, bbox_to_anchor=(.5, .995))
    fig.subplots_adjust(left=.14, right=.98, bottom=.085, top=.875, hspace=.43)
    meta = _metadata("02", "Annual ideology composition and source coverage in the Americas",
        "State counts are divided by a fixed registry of 35 current sovereign American countries. "
        "DPI records snapshots on 1 January of each year from 1975 to 2023; GLI records head-of-government snapshots on 31 December of each year from 1945 to 2020. "
        "The dashed boundary marks the classified share; grey and hatched regions distinguish recorded but unclassified states from absent source records. "
        "Historical absence may reflect state-system entry or source coverage. No ideology imputation, date pooling, role fallback or interpolation of missing observations is used.",
        "Cached DPI 2023 source and frozen outputs/history/gli_hog_aligned_panel.csv; actual source dates are retained.", 175)
    _save_data(pd.concat(compositions, ignore_index=True), folder, meta["stem"])
    export_figure(fig, folder, meta["stem"], 160, 175, publication)
    return meta


def _disagreement_figure(root: Path, folder: Path, publication: bool) -> dict:
    data = _csv(root, "outputs/history/dpi_gli_hog_comparison_by_country.csv",
                ["country_code", "jointly_classified", "disagreements", "disagreement_rate"])
    data["country_name"] = data.country_code.map(_country_name)
    data["comparison_status"] = np.where(data.jointly_classified.gt(0), "Jointly classified", "No joint classification")
    data = data.sort_values(["disagreement_rate", "country_name"], ascending=[False, True], na_position="last").reset_index(drop=True)
    report_path = Path(root) / "outputs/history/history_report.json"
    if report_path.is_file():
        report = json.loads(report_path.read_text(encoding="utf-8"))["roles"]["hog"]
        if int(data.jointly_classified.sum()) != report["jointly_classified"] or int(data.disagreements.sum()) != report["disagreements"]:
            raise ValueError("Frozen HOG country disagreements do not reconcile with history_report.json.")
    fig, ax = plt.subplots(figsize=(160 / 25.4, 190 / 25.4))
    y = np.arange(len(data))
    for index, row in data.iterrows():
        if row.jointly_classified > 0:
            ax.plot(100 * row.disagreement_rate, index, "o", color="#0072B2", ms=4)
        else:
            ax.plot(0, index, "D", markerfacecolor="white", markeredgecolor="#8B8B8B", ms=4)
            ax.text(3, index, "No joint classification", va="center", fontsize=7, color="#777777")
        ax.text(1.035, index, str(int(row.jointly_classified)), transform=ax.get_yaxis_transform(), va="center", ha="right", fontsize=7.2)
    ax.text(1.035, -1.25, "Joint n", transform=ax.get_yaxis_transform(), ha="right", fontsize=7.5)
    ax.set_yticks(y, [_short_name(code) for code in data.country_code])
    ax.set_ylim(len(data) - .35, -1.85)
    ax.set_xlim(-2.5, 105)
    ax.set_xticks([0, 25, 50, 75, 100])
    ax.set_xlabel("Disagreement among jointly classified snapshots (%)")
    ax.grid(axis="x", color="#E6E6E6", lw=.6)
    ax.set_axisbelow(True)
    for label, count in zip(ax.get_yticklabels(), data.jointly_classified):
        if count == 0:
            label.set_color("#777777")
    fig.subplots_adjust(left=.31, right=.94, bottom=.085, top=.985)
    total, disagreements = int(data.jointly_classified.sum()), int(data.disagreements.sum())
    meta = _metadata("04", "DPI–GLI disagreement by country",
        f"Rates use only jointly classified country-years, with country denominators in the right-hand column. "
        f"The primary HOG comparison contains {disagreements} disagreements among {total} joint observations ({100 * disagreements / total:.1f}%). "
        "DPI snapshots on 1 January of year y are compared with GLI snapshots on 31 December of year y−1, for aligned years 1975–2021. Open diamonds flag countries with no joint classification; "
        "their rates are undefined, not zero. GLI used DPI among its coding sources, so this comparison is a measurement audit rather than independent validation. "
        "No confidence intervals or ranking uncertainty are estimated.",
        "Frozen outputs/history/dpi_gli_hog_comparison_by_country.csv and history_report.json; HOG is the primary role.", 190)
    _save_data(data, folder, meta["stem"])
    export_figure(fig, folder, meta["stem"], 160, 190, publication)
    return meta


def _performance_figure(root: Path, folder: Path, publication: bool) -> dict:
    metrics = _csv(root, "outputs/extensions/dpi_drivers/metrics.csv", ["model", "subset", "brier_multiclass", "n", "changes"])
    predictions = _csv(root, "outputs/extensions/dpi_drivers/predictions.csv",
                       ["model", "changed", "state", "target_state", "predicted_state", "year"])
    counts = argmax_change_counts(predictions)
    data = metrics.loc[metrics.subset.eq("all") & metrics.model.isin(MODEL_ORDER)].copy()
    data = data.rename(columns={"model": "model_id", "n": "evaluation_n", "changes": "evaluation_changes"})
    data = data.merge(counts, on="model_id", validate="one_to_one")
    if set(data.model_id) != set(MODEL_ORDER):
        raise ValueError("The frozen driver comparison must contain the six specified models.")
    if not data.evaluation_n.eq(data.n).all() or not data.evaluation_changes.eq(data.observed_changes).all():
        raise ValueError("Frozen model metrics and stored prediction denominators disagree.")
    data = data.set_index("model_id").loc[MODEL_ORDER].reset_index()
    data["model_label"] = data.model_id.map(MODEL_LABELS)
    fig, axes = plt.subplots(1, 2, figsize=(160 / 25.4, 130 / 25.4), sharey=True,
                             gridspec_kw={"width_ratios": [1.55, 1]})
    ax, table = axes
    y = np.arange(len(data))
    for index, row in data.iterrows():
        color = "#555555" if row.model_id in ["persistence", "markov"] else "#0072B2"
        ax.plot(row.brier_multiclass, index, "o", color=color, ms=5)
        ax.text(row.brier_multiclass + .0006, index, f"{row.brier_multiclass:.4f}", va="center", fontsize=7.5, color=color)
        table.text(.20, index, f"{int(row.correct_change_states)}/{int(row.observed_changes)}", ha="center", va="center", fontsize=8.5)
        table.text(.83, index, str(int(row.false_change_predictions)), ha="center", va="center", fontsize=8.5)
    ax.set_yticks(y, data.model_label)
    ax.set_ylim(len(data) - .35, -1)
    ax.set_xlim(.165, .198)
    ax.set_xticks([.17, .18, .19])
    ax.set_xlabel("Multiclass Brier score\n(lower is better)")
    ax.grid(axis="x", color="#E6E6E6", lw=.6)
    _panel(ax, "(a) Probability scores")
    table.set_xlim(0, 1)
    table.axis("off")
    table.text(.20, -.68, "Correct\nchanges", ha="center", va="center", fontsize=7.5)
    table.text(.83, -.68, "False\nchanges", ha="center", va="center", fontsize=7.5)
    _panel(table, "(b) Argmax decisions")
    fig.subplots_adjust(left=.24, right=.985, top=.88, bottom=.16, wspace=.17)
    post_counts = argmax_change_counts(predictions.loc[predictions.year.ge(2000)])
    if post_counts.observed_changes.nunique()!=1:
        raise ValueError("Post-2000 models do not share observed-change counts")
    post_changes=int(post_counts.observed_changes.iloc[0])
    low_hits,high_hits=int(post_counts.correct_change_states.min()),int(post_counts.correct_change_states.max())
    post_note=(f"All six models recover {low_hits}/{post_changes} changes for origins 2000–2022. "
               if low_hits==high_hits else
               f"Correct change counts range from {low_hits} to {high_hits} out of {post_changes} for origins 2000–2022. ")
    n, changes = int(data.n.iloc[0]), int(data.observed_changes.iloc[0])
    lean = data.loc[data.model_id.eq("lean")].iloc[0]
    markov_hits = int(data.loc[data.model_id.eq("markov"), "correct_change_states"].iloc[0])
    meta = _metadata("05", "Probability scores and recovery of observed ideological changes",
        f"The extended DPI evaluation covers origins 1985–2022: {n} country-year pairs and {changes} observed changes. "
        "Panel (a) reproduces the frozen multiclass Brier scores for six models; the displayed score axis is restricted to 0.165–0.198. "
        "Panel (b) counts correct destination states among observed changes and predicted changes among actually unchanged pairs, using stored argmax decisions. "
        f"Markov recovers {markov_hits}/{changes} changes; reduced controls recover {int(lean.correct_change_states)}/{changes}, with {int(lean.false_change_predictions)} false change prediction. "
        + post_note +
        "Regression labels add oil and/or ENSO to the same reduced controls. No new fitting or inferential intervals are used.",
        "Frozen outputs/extensions/dpi_drivers/metrics.csv and predictions.csv; all comparisons use stored chronological predictions.", 130)
    _save_data(data, folder, meta["stem"])
    export_figure(fig, folder, meta["stem"], 160, 130, publication)
    return meta


def _simulation_figure(root: Path, folder: Path, publication: bool) -> dict:
    data = _csv(root, "outputs/main/scenario_summary.csv",
                ["scenario", "year", "state", "mean_countries", "q05", "q95", "runs", "active_countries"])
    if set(data.scenario) != set(SCENARIO_LABELS):
        raise ValueError(f"Frozen Monte Carlo scenario identifiers changed: {sorted(set(data.scenario))}")
    if data.duplicated(["scenario", "year", "state"]).any():
        raise ValueError("Frozen simulation summaries contain duplicate scenario/year/state rows.")
    if not data.groupby(["scenario", "year"]).mean_countries.sum().round(8).eq(30).all():
        raise ValueError("Simulation mean counts must preserve the frozen 30-country active population.")
    if not data.runs.eq(500).all() or not data.active_countries.eq(30).all():
        raise ValueError("This figure expects the original 500-path, 30-country simulation.")
    fig, axes = plt.subplots(3, 1, figsize=(160 / 25.4, 180 / 25.4), sharex=True, sharey=True)
    for ax, (scenario, label), panel_letter in zip(axes, SCENARIO_LABELS.items(), "abc"):
        selected = data.loc[data.scenario.eq(scenario)]
        for state in STATES:
            part = selected.loc[selected.state.eq(state)].sort_values("year")
            ax.fill_between(part.year.to_numpy(), part.q05.to_numpy(), part.q95.to_numpy(), color=STATE_COLORS[state], alpha=.15, linewidth=0)
            ax.plot(part.year, part.mean_countries, color=STATE_COLORS[state], marker=STATE_MARKERS[state], ms=3.5, lw=1.5)
        _panel(ax, f"({panel_letter}) {label}")
        ax.set_ylabel("Country count")
        ax.set_ylim(0, 30)
        ax.set_yticks([0, 10, 20, 30])
        ax.grid(axis="y", color="#E6E6E6", lw=.5)
    axes[-1].set_xlim(2023, 2029)
    axes[-1].set_xticks([2023, 2025, 2027, 2029])
    axes[-1].set_xlabel("Conditional simulation year")
    fig.legend(handles=_state_legend(), frameon=False, ncol=3, loc="upper center", bbox_to_anchor=(.5, .998))
    fig.subplots_adjust(left=.12, right=.98, bottom=.08, top=.89, hspace=.37)
    meta = _metadata("06", "Conditional Monte Carlo paths under three hypothetical scenarios",
        "The original main-model simulation starts from 30 classified countries in January 2023 and uses 500 paths through 2029. "
        "Lines show mean country counts; shaded regions show the 5th–95th percentiles across simulated paths. "
        "The initial state composition is identical across scenarios. Conditions are fixed according to the stored constant, recession, or energy-and-food scenario; annual updates are synchronous. "
        "These bands describe conditional path variation, excluding parameter uncertainty. They are neither confidence intervals nor forecasts of realized governments, and no causal interpretation is assigned to scenario contrasts.",
        "Frozen outputs/main/scenario_summary.csv; original simulation outputs are used without rerunning paths or fitting parameters.", 180)
    export_data = data.rename(columns={"scenario": "scenario_id", "mean_countries": "mean_country_count", "q05": "path_quantile_05", "q95": "path_quantile_95", "runs": "simulation_paths"})
    export_data["scenario_label"] = export_data.scenario_id.map(SCENARIO_LABELS)
    _save_data(export_data, folder, meta["stem"])
    export_figure(fig, folder, meta["stem"], 160, 180, publication)
    return meta


def _calibration_figure(root: Path, folder: Path, publication: bool) -> dict:
    predictions = _csv(root, "outputs/extensions/dpi_drivers/predictions.csv", ["model", "changed", "p_change", "country_code", "year"])
    model_ids = ("markov", "lean_oil_enso")
    selected = predictions.loc[predictions.model.isin(model_ids)].copy()
    keys = ["country_code", "year"]
    a = selected.loc[selected.model.eq(model_ids[0])].set_index(keys)
    b = selected.loc[selected.model.eq(model_ids[1])].set_index(keys)
    if not a.index.equals(b.index) or not _bool(a.changed).equals(_bool(b.changed)):
        raise ValueError("Calibration models must use the identical frozen country-year evaluation pairs.")
    bins = calibration_bins(selected, model_ids, 10)
    curves = precision_recall_data(selected, model_ids)
    fig, axes = plt.subplots(2, 1, figsize=(160 / 25.4, 175 / 25.4))
    ax, pr = axes
    ax.plot([0, 1], [0, 1], color="#B0B0B0", ls=":", lw=1)
    for model in model_ids:
        part = bins.loc[bins.model_id.eq(model) & bins.n.gt(0)]
        marker = "s" if model == "markov" else "o"
        ax.plot(part.mean_predicted_change_probability, part.observed_change_frequency,
                color=MODEL_COLORS[model], marker=marker, ls="none", ms=4,
                label=MODEL_LABELS[model])
        for _, row in part.iterrows():
            offset_y = 7 if model == "markov" else -11
            x = float(row.mean_predicted_change_probability)
            y = float(row.observed_change_frequency)
            if y < .035 and model != "markov":
                offset_y = 7
            ax.annotate(str(int(row.n)), (x, y), xytext=(0, offset_y), textcoords="offset points",
                        ha="center", fontsize=7, color=MODEL_COLORS[model])
        curve = curves.loc[curves.model_id.eq(model)]
        pr.step(curve.recall, curve.precision, where="post", lw=1.4, color=MODEL_COLORS[model],
                ls="--" if model == "markov" else "-", label=MODEL_LABELS[model])
    prevalence = float(_bool(a.changed).mean())
    pr.axhline(prevalence, color="#999999", lw=1, ls=":", label=f"Observed change rate ({prevalence:.3f})")
    _panel(ax, "(a) Change-probability calibration")
    _panel(pr, "(b) Precision–recall curve")
    ax.set_xlabel("Mean predicted probability of change")
    ax.set_ylabel("Observed change frequency")
    pr.set_xlabel("Recall of observed changes")
    pr.set_ylabel("Precision of predicted changes")
    for panel in axes:
        panel.set_xlim(-.015, 1.015)
        panel.set_ylim(-.025, 1.045)
        panel.set_xticks([0, .25, .5, .75, 1])
        panel.set_yticks([0, .25, .5, .75, 1])
        panel.grid(color="#E6E6E6", lw=.5)
    ax.legend(frameon=False, loc="upper left", fontsize=7.5)
    pr.legend(frameon=False, loc="upper right", fontsize=7.5)
    fig.subplots_adjust(left=.13, right=.98, bottom=.085, top=.94, hspace=.44)
    n, changes = len(a), int(_bool(a.changed).sum())
    meta = _metadata("02", "Calibration and ranking of change probabilities",
        f"Markov and reduced controls + oil + ENSO use the same frozen extended evaluation: {n} country-year pairs and {changes} observed changes, origins 1985–2022. "
        "Panel (a) uses 10 equal-width probability bins. Only nonempty bins are drawn, and labels give each bin's observation count; empty bins remain n=0 with undefined frequencies in the accompanying data. "
        "The dotted diagonal denotes perfect calibration. Panel (b) shows descriptive precision–recall curves from all stored probabilities; the horizontal line is the observed change rate. "
        "There are no naive independent-observation confidence intervals, new thresholds chosen for reporting, model refits or causal claims.",
        "Frozen outputs/extensions/dpi_drivers/predictions.csv; descriptive bin summaries and precision–recall coordinates only.", 175, "supplement")
    export_data = pd.concat([
        bins.assign(panel="calibration"),
        curves.rename(columns={"n": "evaluation_n"}).assign(panel="precision_recall"),
    ], ignore_index=True)
    _save_data(export_data, folder, meta["stem"])
    export_figure(fig, folder, meta["stem"], 160, 175, publication)
    return meta


def _oil_figure(root: Path, folder: Path, publication: bool) -> dict:
    scenarios = _csv(root, "outputs/extensions/dpi_drivers/conditional_oil_scenarios.csv")
    data = oil_probability_contrasts(scenarios)
    if data.country_code.nunique() != 30 or not data.year.eq(2023).all():
        raise ValueError("Frozen conditional oil figure expects 30 classified countries at origin 2023.")
    rank = data.groupby("country_code").delta_change_pp.agg(lambda x: x.abs().max()).sort_values(ascending=False)
    order = rank.index.tolist()
    positions = {code: index for index, code in enumerate(order)}
    data["plot_order"] = data.country_code.map(positions)
    fig, axes = plt.subplots(1, 2, figsize=(160 / 25.4, 190 / 25.4), sharey=True, sharex=True)
    for ax, price, label in zip(axes, [-50, 50], ["(a) Oil change: −50%", "(b) Oil change: +50%"]):
        part = data.loc[data.scenario_oil_growth.eq(price)].sort_values("plot_order")
        for _, row in part.iterrows():
            color = STATE_COLORS[row.state]
            marker = STATE_MARKERS[row.state]
            ax.plot(row.delta_change_pp, row.plot_order, marker=marker, ls="none", ms=4.6,
                    markerfacecolor="white" if row.exposure_missing else color,
                    markeredgecolor=color, markeredgewidth=1)
        ax.axvline(0, color="#777777", lw=.8, ls=":")
        ax.grid(axis="x", color="#E6E6E6", lw=.5)
        ax.set_xlabel("ΔP(change)\n(percentage points)")
        ax.set_ylim(len(order) - .35, -1)
        _panel(ax, label)
    axes[0].set_yticks(np.arange(len(order)), [_short_name(code) for code in order])
    for tick, code in zip(axes[0].get_yticklabels(), order):
        state = data.loc[data.country_code.eq(code), "state"].iloc[0]
        tick.set_color(STATE_COLORS[state])
    limit = max(15, 5 * np.ceil(float(data.delta_change_pp.abs().max()) / 5))
    axes[0].set_xlim(-limit, limit)
    axes[0].set_xticks([-limit, 0, limit])
    legend = [Line2D([], [], color=STATE_COLORS[state], marker=STATE_MARKERS[state], ls="none", label=f"Initial {state}") for state in STATES]
    legend.append(Line2D([], [], color="#555555", marker="o", markerfacecolor="white", ls="none", label="Missing fuel exposure"))
    fig.legend(handles=legend, loc="upper center", bbox_to_anchor=(.5, .995), ncol=2, frameon=False, fontsize=7.5)
    fig.subplots_adjust(left=.31, right=.98, bottom=.09, top=.88, wspace=.13)
    missing = sorted(data.loc[data.exposure_missing, "country_code"].unique())
    missing_names = ", ".join(_country_name(code) for code in missing)
    meta = _metadata("03", "Conditional one-step oil contrasts by country",
        "The frozen reduced-controls + oil model changes only the hypothetical oil-price growth input to −50% or +50%, relative to a stored 0% reference, holding all other covariates at their stored origin-2023 values and the initial ideological states at their 1 January 2023 observations. "
        "Dots show the change in probability of leaving the initial state, in percentage points, for 30 classified countries. Colors and marker shapes identify initial Left, Center or Right states; countries are ordered by their largest absolute displayed contrast. "
        f"Open markers identify missing fuel-exposure inputs ({missing_names}); the model's stored probabilities use its training-time imputation and missingness indicators, not observed replacement exposures. "
        "Import and export shares have different denominators and are not net petroleum exposure. These are one-step conditional model contrasts, without parameter intervals, realized future outcomes or causal interpretation.",
        "Frozen outputs/extensions/dpi_drivers/conditional_oil_scenarios.csv; lean_oil probabilities, fixed national exposure year 2021 and origin 2023.", 190, "supplement")
    _save_data(data, folder, meta["stem"])
    export_figure(fig, folder, meta["stem"], 160, 190, publication)
    return meta


def build_charts(root: Path, folder: Path, publication: bool = True) -> list[dict]:
    """Build the requested main/supplement figures solely from frozen results."""
    root, folder = Path(root).resolve(), Path(folder).resolve()
    folder.mkdir(parents=True, exist_ok=True)
    with plt.rc_context(_STYLE):
        return [
            _history_figure(root, folder, publication),
            _disagreement_figure(root, folder, publication),
            _performance_figure(root, folder, publication),
            _simulation_figure(root, folder, publication),
            _calibration_figure(root, folder, publication),
            _oil_figure(root, folder, publication),
        ]
