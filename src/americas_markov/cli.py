from __future__ import annotations

import argparse
import json
from pathlib import Path
import platform
import sys

import numpy as np
import pandas as pd
import sklearn

from . import STATES
from .data import download_all, load_politics, load_wdi, load_prices
from .network import download_contiguity, build_network, network_for_year, eligible_on
from .features import prepare_features, make_transition_panel, DOMESTIC_NUM, NETWORK_NUM, SHOCK_NUM
from .models import rolling_evaluate, fit_model, coefficients, MODEL_ORDER
from .simulation import simulate, SCENARIOS
from .reporting import render_results


def main(root: Path):
    parser = argparse.ArgumentParser(description="Descargas públicas, transiciones ideológicas y simulación condicional sobre redes.")
    parser.add_argument("--download", action="store_true")
    parser.add_argument("--refresh", action="store_true")
    parser.add_argument("--offline", action="store_true")
    parser.add_argument("--run", action="store_true")
    parser.add_argument("--simulate", action="store_true")
    parser.add_argument("--competitive-only", action="store_true", help="Sensibilidad: sólo orígenes EIEC>=6")
    parser.add_argument("--land-only", action="store_true", help="Sensibilidad: excluir conexiones marítimas")
    parser.add_argument("--start-year", type=int, default=2000)
    parser.add_argument("--runs", type=int, default=500)
    parser.add_argument("--horizon", type=int, default=6)
    parser.add_argument("--seed", type=int, default=2026)
    args = parser.parse_args()
    if args.offline and (args.download or args.refresh):parser.error("--offline no permite --download ni --refresh")
    if args.refresh and not args.download:parser.error("--refresh requiere --download")
    if not any([args.download,args.run,args.simulate]):parser.print_help();return
    root = Path(root)
    if args.download:
        print("Descargando/verificando datos públicos...", flush=True)
        download_all(root, refresh=args.refresh)
        download_contiguity(root, refresh=args.refresh)
    if not (args.run or args.simulate):print("Descargas completadas.");return
    # No descarga implícita: todos los loaders exigen archivos locales.
    politics = load_politics(root)
    wdi, prices = load_wdi(root), load_prices(root)
    codes = sorted(politics.country_code.unique())
    eligibility = {y:set(eligible_on(root, f"{y}-01-01")) for y in politics.year.unique()}
    accepted = np.asarray([r.country_code in eligibility[r.year] for r in politics.itertuples()])
    membership_excluded = int((~accepted).sum())
    modeled_politics = politics.loc[accepted].copy()
    networks = {}
    for year in sorted(modeled_politics.year.unique()):
        # COW anual puede registrar una relación nacida durante ese año:
        # emplear t-1 garantiza una topología anterior al origen del 1 de enero.
        networks[int(year)] = network_for_year(root, codes, int(year)-1,
                                             include_water=not args.land_only)[0]
    features = prepare_features(modeled_politics, wdi, prices, networks)
    panel = make_transition_panel(features, competitive_only=args.competitive_only)
    suffix = "land_only" if args.land_only else "main"
    if args.competitive_only:suffix += "_competitive"
    folder = root / "outputs" / suffix
    folder.mkdir(parents=True, exist_ok=True)
    processed = root / "data" / "processed";processed.mkdir(parents=True, exist_ok=True)
    politics.to_csv(processed / "dpi_americas.csv", index=False)
    wdi.to_csv(processed / "wdi_americas_world.csv", index=False)
    prices.to_csv(processed / "precios_anuales.csv", index=False)
    features.to_csv(folder / "caracteristicas.csv", index=False)
    panel.to_csv(folder / "panel_transiciones.csv", index=False)
    unknown = politics.loc[~politics.state.isin(STATES)]
    unknown.to_csv(processed / "ideologias_desconocidas.csv", index=False)
    missing = panel[DOMESTIC_NUM+NETWORK_NUM+SHOCK_NUM].isna().mean().rename("missing_share").rename_axis("feature").reset_index()
    missing.to_csv(folder / "cobertura_covariables.csv", index=False)
    matrix = pd.crosstab(panel.state, panel.target_state).reindex(index=STATES, columns=STATES, fill_value=0)
    matrix.to_csv(folder / "transiciones_conteos.csv")
    matrix.div(matrix.sum(axis=1),axis=0).to_csv(folder / "transiciones_probabilidades_descriptivas.csv")
    print(f"Panel: {len(panel)} transiciones, {int(panel.changed.sum())} cambios; {len(codes)} países.", flush=True)
    print("Evaluación temporal expansiva de seis modelos...", flush=True)
    predictions, metrics, folds = rolling_evaluate(panel, start_year=args.start_year)
    predictions.to_csv(folder / "predicciones_fuera_muestra.csv", index=False)
    metrics.to_csv(folder / "metricas.csv", index=False)
    folds.to_csv(folder / "metricas_por_ano.csv", index=False)
    fitted = {name:fit_model(panel,name) for name in MODEL_ORDER}
    coef = coefficients(fitted["network_shocks"])
    coef.to_csv(folder / "coeficientes_descriptivos.csv", index=False)
    final_year = int(features.year.max())
    weights, edges = build_network(root, codes, snapshot_year=2016, include_water=not args.land_only)
    weights.to_csv(folder / "pesos_red_2016.csv")
    edges.to_csv(folder / "aristas_red_2016.csv", index=False)
    initial = features.loc[(features.year==final_year) & features.state.isin(STATES)].copy()
    if args.competitive_only:initial = initial.loc[initial.eiec.ge(6)].copy()
    scenario_summary = None
    if args.simulate:
        summaries = []
        print(f"Simulando {args.runs} trayectorias por escenario desde enero de {final_year}...", flush=True)
        for scenario in SCENARIOS:
            draws, summary = simulate(fitted["network_shocks"], initial, weights,
                                      horizon=args.horizon, runs=args.runs, seed=args.seed,
                                      scenario=scenario)
            draws.to_csv(folder / f"escenario_{scenario}.csv.gz", index=False, compression="gzip")
            summaries.append(summary)
        scenario_summary = pd.concat(summaries, ignore_index=True)
    info = {"countries": len(codes), "political_rows": len(politics), "unknown_states": len(unknown),
            "membership_excluded": membership_excluded, "panel_n":len(panel),"panel_changes":int(panel.changed.sum()),
            "origin_min":int(panel.year.min()),"origin_max":int(panel.year.max()),"last_target_year":int(panel.target_year.max()),
            "network_directed_edges":len(edges),"simulation_active_countries":len(initial),
            "python":sys.version,"numpy":np.__version__,"pandas":pd.__version__,"sklearn":sklearn.__version__,
            "platform":platform.platform(),"options":vars(args),
            "regression_C":1.0,"laplace_alpha":1.0,"logloss_floor":1e-12,
            "forecast_claim":"Retrospective chronological evaluation using revised series; not real-time vintages",
            "ukraine_estimated":False,"annual_updates":"synchronous; no election schedule gating"}
    render_results(predictions, metrics, folds, politics, panel, weights, scenario_summary, folder, info)
    print(metrics.loc[metrics.subset=="all",["model","n","brier_multiclass","log_loss_clipped","accuracy"]].to_string(index=False))
    print(f"Resultados: {folder.resolve()}")
