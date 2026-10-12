"""Resultados descriptivos y diagnósticos; no inferencia causal automática."""
from __future__ import annotations

import json
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from . import STATES, STATE_ES
from .models import MODEL_ORDER

MODEL_NAMES = {"persistence": "Persistencia", "markov": "Markov",
               "domestic": "Doméstico", "network": "Doméstico + red",
               "shocks": "Doméstico + choques", "network_shocks": "Doméstico + red + choques"}
COLORS = {"Left": "#0072B2", "Center": "#777777", "Right": "#D55E00"}


def save_figure(fig, folder: Path, name: str):
    for suffix in ["png", "svg"]: fig.savefig(folder / f"{name}.{suffix}", dpi=300, bbox_inches="tight")
    plt.close(fig)


def render_results(predictions, metrics, folds, politics, panel, weights,
                   scenario_summary, folder: Path, info: dict):
    folder.mkdir(parents=True, exist_ok=True)
    plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 9, "svg.fonttype": "none"})
    fig, axes = plt.subplots(1, 2, figsize=(10, 4.3))
    for ax, subset, label in zip(axes, ["all", "changed"], ["Todas las transiciones", "Cambios ideológicos observados"]):
        m = metrics.loc[metrics.subset == subset].set_index("model").reindex(MODEL_ORDER)
        ax.barh(np.arange(len(m)), m.brier_multiclass, color="#0072B2")
        ax.set_yticks(np.arange(len(m)), [MODEL_NAMES[n] for n in m.index]);ax.invert_yaxis()
        ax.set_xlabel("Brier multiclase (menor es mejor)");ax.set_title(label)
        for j, value in enumerate(m.brier_multiclass):ax.text(value + .01, j, f"{value:.3f}", va="center", fontsize=8)
        ax.set_xlim(0, max(m.brier_multiclass)*1.22)
        ax.spines[["top", "right"]].set_visible(False)
    fig.tight_layout();save_figure(fig, folder, "comparacion_modelos")

    # Curvas por clase, agrupando probabilidades con los mismos cortes fijos.
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
        ax.plot([0,1],[0,1],"k:",lw=.8);ax.set_title(STATE_ES[state]);ax.set_xlabel("Probabilidad predicha")
    axes[0].set_ylabel("Fracción observada");axes[-1].legend(fontsize=7, loc="upper left")
    fig.tight_layout();save_figure(fig, folder, "calibracion")
    pd.DataFrame(calibration_rows).to_csv(folder / "calibracion.csv", index=False)

    fig, ax = plt.subplots(figsize=(9, 3.5))
    for name in ["markov", "domestic", "network", "shocks", "network_shocks"]:
        f = folds.loc[folds.model == name]
        ax.plot(f.origin_year, f.brier_multiclass, label=MODEL_NAMES[name], lw=1.1)
    ax.set_xlabel("Año de origen (estado objetivo: enero del año siguiente)")
    ax.set_ylabel("Brier multiclase");ax.legend(fontsize=7, ncol=2)
    fig.tight_layout();save_figure(fig, folder, "desempeno_por_ano")

    if scenario_summary is not None and len(scenario_summary):
        scenario_summary.to_csv(folder / "escenarios_resumen.csv", index=False)
        fig, axes = plt.subplots(1, 3, figsize=(11, 3.6), sharex=True, sharey=True)
        for ax, (scenario, block) in zip(axes, scenario_summary.groupby("scenario", sort=False)):
            for state in STATES:
                s = block.loc[block.state == state].sort_values("year")
                ax.plot(s.year, s.mean_countries, label=STATE_ES[state], color=COLORS[state])
                ax.fill_between(s.year, s.q05, s.q95, color=COLORS[state], alpha=.12)
            ax.set_title(scenario.replace("_", "\n"), fontsize=8);ax.set_xlabel("Año simulado")
        axes[0].set_ylabel("Número de países activos");axes[-1].legend(fontsize=7)
        fig.tight_layout();save_figure(fig, folder, "escenarios")

    all_scores = metrics.loc[metrics.subset == "all"].set_index("model")
    best = all_scores.brier_multiclass.idxmin()
    base, combined = all_scores.loc["domestic"], all_scores.loc["network_shocks"]
    changed_scores = metrics.loc[metrics.subset=="changed"]
    correct_changed = "; ".join(f"{MODEL_NAMES[r.model]}: {int(round(r.accuracy*r.n))}/{int(r.n)}"
                                for r in changed_scores.itertuples())
    report = [
        "EJECUCIÓN DEL PROTOTIPO: TRANSICIONES IDEOLÓGICAS EN LAS AMÉRICAS",
        "", f"Países presentes en DPI: {info['countries']}; observaciones políticas: {info['political_rows']}.",
        f"Estados políticos desconocidos: {info['unknown_states']}; no fueron convertidos en centro.",
        f"Filas anteriores a pertenencia COW al 1 de enero excluidas: {info['membership_excluded']}.",
        f"Transiciones consecutivas con estados observados: {len(panel)}; cambios: {int(panel.changed.sum())}.",
        f"Orígenes de evaluación: {int(predictions.year.min())}–{int(predictions.year.max())}; última etiqueta: enero {int(predictions.target_year.max())}.",
        "Evaluación expansiva: en cada origen se ajustan nuevamente imputación, escalado y modelo sólo con el pasado.",
        "Covariables macro t-1; estados vecinales t; topología anual COW t-1, con continuidad de 2016 después del final de la fuente.",
        "", "RESULTADOS FUERA DEL ENTRENAMIENTO",
    ]
    for name in MODEL_ORDER:
        row = all_scores.loc[name]
        report.append(f"{MODEL_NAMES[name]}: N={int(row.n)}, Brier={row.brier_multiclass:.6f}, log-loss truncado={row.log_loss_clipped:.6f}, exactitud={row.accuracy:.3%}.")
    report += ["", f"Menor Brier observado: {MODEL_NAMES[best]}.",
               f"Diferencia Brier (red+choques menos doméstico): {combined.brier_multiclass-base.brier_multiclass:+.6f}. Un valor negativo favorece el modelo combinado en esta ejecución.",
               "Esta comparación no estima significación estadística ni demuestra contagio político.",
               "La exactitud general está influida por la persistencia. Consultar el subconjunto changed en metricas.csv.",
               f"Aciertos en alternancias observadas al seleccionar la clase de máxima probabilidad: {correct_changed}. La exactitud general no equivale a anticipar alternancias.",
               "El riesgo de alternancia se calcula como uno menos la probabilidad del estado inicial. Brier binario, AUC-ROC y precisión promedio evalúan ese riesgo sobre todas las observaciones; no se elige un umbral con el test.",
               "", "ALCANCE Y LÍMITES",
               "Las probabilidades proceden de modelos regulares multinomiales, no de una matriz universal que describa todas las instituciones.",
               "Con duración ideológica como predictor, el estado efectivo incluye memoria; puede interpretarse como extensión de duración/estado ampliado de Markov.",
               "DPI termina en enero de 2023: con rezago t-1 no existe variación de Ucrania en el panel estimable. No se estimó un efecto de la guerra.",
               "COVID es un indicador de episodio y no mortalidad; sólo aparece en los orígenes 2021–2022. Es evidencia escasa de un choque global.",
               "Las series macroeconómicas son revisadas, no sus publicaciones históricas disponibles en tiempo real. No tratar el resultado como pronóstico operativo.",
               "La mediana y los indicadores de ausencia de covariables se aprenden en cada entrenamiento; los estados políticos y etiquetas faltantes se excluyen.",
               "El índice de importaciones de combustibles es participación en importaciones, no importación neta ni un instrumento causal.",
               "La red es geográfica; todavía no se construyó una red de comercio bilateral.",
               "La calibración es descriptiva y no incluye intervalos que supongan independencia entre países-años.",
               "No se identifican efectos causales; no se generan valores p; no se garantiza novedad editorial.",
               "", "SIMULACIÓN",
               "Los escenarios comienzan en el último estado DPI observado (enero de 2023), no en los gobiernos actuales de 2026.",
               "Sólo se activan países con estado observado en esa fecha; los desconocidos no se inicializan por imputación.",
               "Actualización simultánea anual de todos los nodos. No reproduce fechas electorales ni votantes individuales.",
               "Condiciones constantes: tasas de cambio de precios cero, COVID cero; crecimiento mundial y covariables nacionales fijos en valores base.",
               "Recesión hipotética: crecimiento mundial -2 % durante dos pasos, después vuelve a la base.",
               "Energía/alimentos hipotético: cambios +50 %/+20 % durante dos pasos; no representa una predicción ni efecto estimado de Ucrania.",
               "Bandas 5–95 %: dispersión Monte Carlo condicionada a parámetros ajustados; no incluyen incertidumbre de parámetros ni de medición.",
               "Los modelos finales usan todo el panel para escenarios; sus métricas proceden de ajustes separados por fold, no del ajuste final."]
    (folder / "RESULTADOS.txt").write_text("\n".join(report)+"\n", encoding="utf-8")
    (folder / "run_info.json").write_text(json.dumps(info, ensure_ascii=False, indent=2), encoding="utf-8")
