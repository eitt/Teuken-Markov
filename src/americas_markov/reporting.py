"""English descriptive results and diagnostics; no automatic causal inference.

Source identifiers and historical output filenames stay unchanged so existing
analysis scripts can continue to consume the frozen scientific outputs.
"""
from __future__ import annotations

import json
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from . import STATES
from .models import MODEL_ORDER

MODEL_NAMES = {
    "persistence": "Persistence", "markov": "Markov",
    "domestic": "Domestic", "network": "Domestic + geographic network",
    "shocks": "Domestic + global shocks", "network_shocks": "Domestic + network + shocks",
    "lean": "Reduced controls", "lean_oil": "Reduced controls + oil",
    "lean_enso": "Reduced controls + ENSO", "lean_oil_enso": "Reduced controls + oil + ENSO",
    "history_duration": "Duration", "history_network": "Duration + geographic network",
}
SCENARIO_NAMES = {
    "condiciones_constantes": "Constant conditions",
    "recesion_hipotetica": "Hypothetical recession",
    "energia_alimentos_hipotetico": "Hypothetical energy and food shock",
}
COLORS = {"Left": "#0072B2", "Center": "#777777", "Right": "#D55E00"}


def save_figure(fig, folder: Path, name: str):
    for suffix in ["png", "svg"]: fig.savefig(folder / f"{name}.{suffix}", dpi=300, bbox_inches="tight")
    plt.close(fig)


def render_results(predictions, metrics, folds, politics, panel, weights,
                   scenario_summary, folder: Path, info: dict):
    folder.mkdir(parents=True, exist_ok=True)
    plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 9, "svg.fonttype": "none"})
    fig, axes = plt.subplots(1, 2, figsize=(10, 4.3))
    for ax, subset, label in zip(axes, ["all", "changed"], ["All transition cases", "Observed ideological changes"]):
        m = metrics.loc[metrics.subset == subset].set_index("model").reindex(MODEL_ORDER)
        ax.barh(np.arange(len(m)), m.brier_multiclass, color="#0072B2")
        ax.set_yticks(np.arange(len(m)), [MODEL_NAMES[n] for n in m.index]);ax.invert_yaxis()
        ax.set_xlabel("Multiclass Brier score (lower is better)");ax.set_title(label)
        for j, value in enumerate(m.brier_multiclass):ax.text(value + .01, j, f"{value:.3f}", va="center", fontsize=8)
        ax.set_xlim(0, max(m.brier_multiclass)*1.22)
        ax.spines[["top", "right"]].set_visible(False)
    fig.tight_layout();save_figure(fig, folder, "comparacion_modelos")

    # Classwise calibration, using the same fixed probability bins.
    calibration_rows = []
    fig, axes = plt.subplots(1, 3, figsize=(10, 3.5), sharex=True, sharey=True)
    for state, column, ax in zip(STATES, ["p_left", "p_center", "p_right"], axes):
        for name in ["markov", "domestic", "network_shocks"]:
            block = predictions.loc[predictions.model == name].copy()
            block["bin"] = np.clip(np.floor(block[column]*10).astype(int), 0, 9)
            x, y = [], []
            for bin_id, g in block.groupby("bin"):
                expected = float(g[column].mean());observed = float(g.target_state.eq(state).mean())
                calibration_rows.append({"model": name, "state": state, "bin": bin_id,
                                         "n": len(g), "mean_predicted": expected, "observed_fraction": observed})
                x.append(expected);y.append(observed)
            ax.plot(x, y, marker="o", ms=3, label=MODEL_NAMES[name], lw=1)
        ax.plot([0,1],[0,1],"k:",lw=.8);ax.set_title(state);ax.set_xlabel("Predicted probability")
    axes[0].set_ylabel("Observed fraction")
    handles, labels = axes[-1].get_legend_handles_labels()
    fig.legend(handles, labels, fontsize=7, loc="lower center", ncol=3, frameon=False)
    fig.tight_layout(rect=(0, .1, 1, 1));save_figure(fig, folder, "calibracion")
    pd.DataFrame(calibration_rows).to_csv(folder / "calibracion.csv", index=False)

    fig, ax = plt.subplots(figsize=(9, 3.5))
    for name in ["markov", "domestic", "network", "shocks", "network_shocks"]:
        f = folds.loc[folds.model == name]
        ax.plot(f.origin_year, f.brier_multiclass, label=MODEL_NAMES[name], lw=1.1)
    ax.set_xlabel("Origin year (target state: January of the following year)")
    ax.set_ylabel("Multiclass Brier score");ax.legend(fontsize=7, ncol=2)
    fig.tight_layout();save_figure(fig, folder, "desempeno_por_ano")

    if scenario_summary is not None and len(scenario_summary):
        scenario_summary.to_csv(folder / "escenarios_resumen.csv", index=False)
        fig, axes = plt.subplots(1, 3, figsize=(11, 3.6), sharex=True, sharey=True)
        for ax, (scenario, block) in zip(axes, scenario_summary.groupby("scenario", sort=False)):
            for state in STATES:
                s = block.loc[block.state == state].sort_values("year")
                ax.plot(s.year, s.mean_countries, label=state, color=COLORS[state])
                ax.fill_between(s.year, s.q05, s.q95, color=COLORS[state], alpha=.12)
            ax.set_title(SCENARIO_NAMES[scenario], fontsize=8);ax.set_xlabel("Simulated year")
        axes[0].set_ylabel("Number of active countries");axes[-1].legend(fontsize=7)
        fig.tight_layout();save_figure(fig, folder, "escenarios")

    all_scores = metrics.loc[metrics.subset == "all"].set_index("model")
    best = all_scores.brier_multiclass.idxmin()
    base, combined = all_scores.loc["domestic"], all_scores.loc["network_shocks"]
    changed_scores = metrics.loc[metrics.subset=="changed"]
    correct_changed = "; ".join(f"{MODEL_NAMES[r.model]}: {int(round(r.accuracy*r.n))}/{int(r.n)}"
                                for r in changed_scores.itertuples())
    report = [
        "PROTOTYPE RESULTS: IDEOLOGICAL TRANSITIONS IN THE AMERICAS",
        "", f"Countries present in DPI: {info['countries']}; political records: {info['political_rows']}.",
        f"Unknown political states: {info['unknown_states']}; these were not recoded as Center.",
        f"Records excluded before COW membership on January 1: {info['membership_excluded']}.",
        f"Consecutive transitions with observed states: {len(panel)}; changes: {int(panel.changed.sum())}.",
        f"Evaluation origins: {int(predictions.year.min())}–{int(predictions.year.max())}; last target: January {int(predictions.target_year.max())}.",
        "Expanding evaluation: imputation, scaling and models are fitted separately at each origin using only earlier outcomes.",
        "Macroeconomic covariates: t-1; neighboring states: t; annual COW topology: t-1, carrying the 2016 graph forward after source coverage ends.",
        "", "OUT-OF-SAMPLE RESULTS",
    ]
    for name in MODEL_ORDER:
        row = all_scores.loc[name]
        report.append(f"{MODEL_NAMES[name]}: N={int(row.n)}, Brier={row.brier_multiclass:.6f}, clipped log loss={row.log_loss_clipped:.6f}, accuracy={row.accuracy:.3%}.")
    report += ["", f"Lowest observed Brier score: {MODEL_NAMES[best]}.",
               f"Brier difference (network + shocks minus domestic): {combined.brier_multiclass-base.brier_multiclass:+.6f}. A negative value favors the combined model in this run.",
               "This comparison does not estimate statistical significance or establish political contagion.",
               "Overall accuracy is influenced by persistence. See the changed subset in metricas.csv.",
               f"Correct predictions among observed changes when selecting the highest-probability class: {correct_changed}. Overall accuracy does not measure anticipation of ideological change.",
               "Change risk is one minus the probability of the initial state. Binary Brier score, ROC AUC and average precision assess this risk across all cases; no decision threshold is selected on the test set.",
               "", "SCOPE AND LIMITATIONS",
               "Probabilities come from regularized multinomial models, rather than a universal transition matrix describing every institution.",
               "With ideological duration as a predictor, the effective state includes memory; this is a duration-augmented Markov specification.",
               "DPI ends in January 2023: the t-1 lag leaves no Ukraine indicator variation in the estimable panel. No war effect was estimated.",
               "COVID is an episode indicator, not mortality; it appears only at the 2021–2022 origins. Evidence for this global shock is sparse.",
               "Macroeconomic series are revised historical data, not their real-time publication vintages. Results are not operational forecasts.",
               "Medians and missingness indicators are learned within each training set; missing political states and targets are excluded.",
               "Fuel imports are a share of merchandise imports, not net imports or a causal instrument.",
               "The network is geographic; a bilateral trade network has not been constructed.",
               "Calibration is descriptive; no intervals assuming independent country-years are reported.",
               "No causal effects or p-values are estimated. Publication novelty has not been established.",
               "", "SIMULATION",
               "Scenarios begin at the last observed DPI snapshot (January 2023), not at the governments in office in 2026.",
               "Only countries classified on that date are active; unknown states are not initialized by imputation.",
               "All nodes update synchronously each year. The simulation does not reproduce election dates or individual voters.",
               "Constant conditions: zero price growth and zero COVID indicator; global growth and domestic covariates remain at baseline values.",
               "Hypothetical recession: global GDP growth is set to -2% for two steps, then returns to baseline.",
               "Hypothetical energy and food shock: price changes of +50%/+20% for two steps; this is neither a prediction nor an estimated Ukraine effect.",
               "The 5–95% bands show Monte Carlo dispersion conditional on fitted parameters; parameter and measurement uncertainty are excluded.",
               "Final models use the full panel for scenarios; evaluation metrics come from separate chronological fold fits, not the final fit."]
    (folder / "RESULTADOS.txt").write_text("\n".join(report)+"\n", encoding="utf-8")
    (folder / "run_info.json").write_text(json.dumps(info, ensure_ascii=False, indent=2), encoding="utf-8")
