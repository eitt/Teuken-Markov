"""Chronological sensitivity experiments, separate from the frozen main run."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd

from . import STATES
from .data import load_politics, load_wdi, load_prices
from .drivers import download_exposures, load_exposures, prepare_driver_features, model_specs, conditional_oil_scenario
from .features import prepare_features, make_transition_panel, NETWORK_NUM
from .models import rolling_evaluate, score_predictions, fit_model
from .network import eligible_on, network_for_year


def feature_panel(root, politics, wdi, prices):
    codes = sorted(politics.country_code.unique())
    eligible = {int(y): set(eligible_on(root, f"{int(y)}-01-01")) for y in politics.year.unique()}
    mask = np.array([r.country_code in eligible[int(r.year)] for r in politics.itertuples()])
    selected = politics.loc[mask].copy()
    networks = {int(y): network_for_year(root, codes, int(y)-1)[0] for y in sorted(selected.year.unique())}
    return prepare_features(selected, wdi, prices, networks), int((~mask).sum())


def period_scores(predictions):
    rows = []
    masks = {"all": np.ones(len(predictions), dtype=bool),
             "pre2000": predictions.year.lt(2000), "2000plus": predictions.year.ge(2000)}
    for period, mask in masks.items():
        for model, block in predictions.loc[mask].groupby("model", sort=False):
            for subset, part in [("all", block), ("changed", block[block.changed]), ("unchanged", block[~block.changed])]:
                if len(part): rows.append({"period": period, "model": model, "subset": subset, **score_predictions(part)})
    return pd.DataFrame(rows)


def write_evaluation(panel, specs, folder, start_year):
    folder.mkdir(parents=True, exist_ok=True)
    pred, metrics, folds = rolling_evaluate(panel, start_year=start_year, model_features=specs)
    metrics.to_csv(folder / "metrics.csv", index=False)
    folds.to_csv(folder / "folds.csv", index=False)
    period_scores(pred).to_csv(folder / "metrics_by_period.csv", index=False)
    pred.to_csv(folder / "predictions.csv", index=False)
    panel.to_csv(folder / "transition_panel.csv", index=False)
    first = pred.model.iloc[0]
    unique = pred[pred.model.eq(first)]
    info = {"panel_pairs": len(panel), "panel_changes": int(panel.changed.sum()),
            "evaluated_pairs": len(unique), "evaluated_changes": int(unique.changed.sum()),
            "first_origin": int(unique.year.min()), "last_origin": int(unique.year.max()),
            "last_target": int(unique.target_year.max()), "model_specs": specs,
            "interpretation": "Retrospective prediction with revised inputs; no causal effect or political direction imposed."}
    (folder / "run_info.json").write_text(json.dumps(info, ensure_ascii=False, indent=2) + "\n")
    return pred, metrics, info


def run_extensions(root, start_year=1985, history_start_year=1956, history_role="hog"):
    from .climate import load_climate
    from .history import load_gli, history_report
    root = Path(root)
    folder = root / "outputs/extensions"; folder.mkdir(parents=True, exist_ok=True)
    wdi, prices = load_wdi(root), load_prices(root)
    dpi = load_politics(root)
    original, dpi_excluded = feature_panel(root, dpi, wdi, prices)
    expanded = prepare_driver_features(original, wdi, load_exposures(root), load_climate(root))
    dpi_panel = make_transition_panel(expanded)
    print(f"DPI: {len(dpi_panel)} pairs; evaluation from {start_year}", flush=True)
    specs = model_specs()
    d_pred, d_metrics, d_info = write_evaluation(dpi_panel, specs, folder / "dpi_drivers", start_year)
    required = list(dict.fromkeys(c for cols in specs.values() for c in cols))
    dpi_panel[required].isna().mean().rename("missing_share").rename_axis("feature").reset_index().to_csv(
        folder / "dpi_drivers/feature_coverage.csv", index=False)
    coverage_year = dpi_panel.groupby("year")[required].agg(lambda s: s.notna().sum())
    coverage_year.to_csv(folder / "dpi_drivers/feature_known_count_by_year.csv")
    # Explicit one-step hypothetical price contrasts from the observed January2023
    # baseline. Not forecast winners, not an estimated effect of an historical war.
    fitted = fit_model(dpi_panel, "lean_oil", numeric_columns=specs["lean_oil"])
    snapshot = expanded[expanded.year.eq(int(expanded.year.max())) & expanded.state.isin(STATES)].copy()
    scenario_rows = []
    for growth in [0.0, -50.0, 50.0]:
        prob = conditional_oil_scenario(fitted, snapshot, growth)
        part = snapshot[["country_code", "year", "state", "fuel_import_share_prior", "fuel_export_share_prior"]].copy()
        part["scenario_oil_growth"] = growth
        part[["p_left", "p_center", "p_right"]] = prob
        scenario_rows.append(part)
    pd.concat(scenario_rows, ignore_index=True).to_csv(folder / "dpi_drivers/conditional_oil_scenarios.csv", index=False)

    print("Building separate GLI historical panel...", flush=True)
    history_report(root)
    gli = load_gli(root, role=history_role)
    historical, gli_excluded = feature_panel(root, gli, wdi, prices)
    h_panel = make_transition_panel(historical)
    # Early historical years are modelled using observed political state/duration
    # and geography; pre1960 macro values are NOT fabricated or imputed into X.
    h_specs = {"history_duration": ["state_duration"],
               "history_network": ["state_duration", *NETWORK_NUM]}
    print(f"GLI-{history_role}: {len(h_panel)} pairs; evaluation from {history_start_year}", flush=True)
    h_pred, h_metrics, h_info = write_evaluation(h_panel, h_specs, folder / f"gli_{history_role}", history_start_year)
    summary = {"dpi": d_info, "gli": h_info, "gli_role": history_role,
               "dpi_cow_membership_excluded": dpi_excluded, "gli_cow_membership_excluded": gli_excluded,
               "sources_not_spliced": True, "climate_measure": "ENSO variability (ONI), not anthropogenic climate change",
               "exposure_year": "origin-2", "economic_and_climate_year": "origin-1",
               "oil_proxy": "fuel import share and fuel export share; separate denominators, not net petroleum",
               "ukraine_effect_estimated": False,
               "prediction_limit": "No post2023 DPI labels; no realised2022 Ukraine indicator in origin2022 predictors."}
    (folder / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n")
    text = ["Exploratory extension; original outputs/main are preserved.",
            "DPI includes a wider evaluation window; GLI is a separate historical source.",
            "Oil interactions use prior import/export exposures, not a net-import proxy.",
            "ONI describes ENSO variability; no anthropogenic climate attribution is claimed.",
            "All years use currently revised source values, not historical release vintages.",
            "Year fixed effects are not included; global shocks would be absorbed by unrestricted year effects.",
            "No direction Left/Right is imposed by a shock. Results report probabilities.",
            "Conditional price scenarios exclude parameter uncertainty and have fixed national exposures."]
    for label, metrics in [("DPI", d_metrics), ("GLI", h_metrics)]:
        text.append("\n" + label + ":\n" + metrics[metrics.subset.eq("all")][["model", "n", "changes", "brier_multiclass", "accuracy"]].to_string(index=False))
    (folder / "RESULTS.txt").write_text("\n".join(text) + "\n")
    print(folder / "RESULTS.txt")
    return summary


def main(root):
    from .climate import download_climate
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--download", action="store_true", help="Fetch only optional WDI exposures and NOAA climate")
    parser.add_argument("--refresh", action="store_true")
    parser.add_argument("--offline", action="store_true")
    parser.add_argument("--run", action="store_true")
    parser.add_argument("--start-year", type=int, default=1985)
    parser.add_argument("--history-start-year", type=int, default=1956)
    parser.add_argument("--history-role", choices=["hog", "leader"], default="hog")
    args = parser.parse_args()
    if args.offline and (args.download or args.refresh): parser.error("--offline excludes downloads/refresh")
    if args.refresh and not args.download: parser.error("--refresh requires --download")
    if not args.download and not args.run: parser.print_help(); return
    if args.download:
        download_exposures(Path(root), refresh=args.refresh)
        download_climate(Path(root), refresh=args.refresh)
    if args.run:
        run_extensions(root, args.start_year, args.history_start_year, args.history_role)
