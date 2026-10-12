"""English publication tables derived only from cached scientific outputs.

This module does not download data, fit models, recode political observations,
or splice DPI and GLI. CSV exports retain numerical precision; Markdown tables
round values only for reading. Scientific identifiers remain in the complete
English exports alongside their presentation labels.
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

from . import STATES
from .network import COUNTRY_METADATA
from .reporting import MODEL_NAMES, SCENARIO_NAMES, render_results


DPI_MODELS = ["persistence", "markov", "lean", "lean_oil", "lean_enso", "lean_oil_enso"]
GLI_MODELS = ["persistence", "markov", "history_duration", "history_network"]
COUNTRY_NAMES = {code: str(values["name"]) for code, values in COUNTRY_METADATA.items()}
COUNTRY_NAMES.update({
    "ATG": "Antigua and Barbuda", "KNA": "Saint Kitts and Nevis",
    "LCA": "Saint Lucia", "VCT": "Saint Vincent and the Grenadines",
    "USA": "United States", "WLD": "World",
})
PERIOD_NAMES = {"all": "All origins", "pre2000": "Origins before 2000", "2000plus": "Origins from 2000"}
SUBSET_NAMES = {"all": "All cases", "changed": "Observed changes", "unchanged": "No observed change"}


def _read(root: Path, name: str) -> pd.DataFrame:
    path = root / name
    if not path.is_file():
        raise FileNotFoundError(f"Missing frozen source for publication tables: {name}")
    return pd.read_csv(path)


def _json(root: Path, name: str) -> dict:
    return json.loads((root / name).read_text(encoding="utf-8"))


def _year_range(values) -> str:
    return f"{int(values.min())}–{int(values.max())}"


def _period_mask(predictions: pd.DataFrame, period: str) -> pd.Series:
    if period == "all":
        return pd.Series(True, index=predictions.index)
    if period == "pre2000":
        return predictions.year < 2000
    if period == "2000plus":
        return predictions.year >= 2000
    raise ValueError(f"Unknown evaluation period: {period}")


def _validated_predictions(predictions: pd.DataFrame, models: list[str]) -> None:
    required = {"country_code", "year", "target_year", "state", "target_state", "changed", "model", "predicted_state"}
    if not required.issubset(predictions.columns):
        raise ValueError(f"Missing prediction columns: {sorted(required - set(predictions.columns))}")
    if set(predictions.model) != set(models):
        raise ValueError("Prediction models do not match the declared publication comparison")
    if predictions.duplicated(["country_code", "year", "model"]).any():
        raise ValueError("Duplicate country-origin-model prediction; cases cannot be counted twice")
    if not predictions.target_year.eq(predictions.year + 1).all():
        raise ValueError("Prediction targets must follow their origins by one year")
    if not predictions.state.isin(STATES).all() or not predictions.target_state.isin(STATES).all():
        raise ValueError("Unknown political states cannot enter classified evaluation cases")
    if not predictions.changed.eq(predictions.state.ne(predictions.target_state)).all():
        raise ValueError("Stored change labels disagree with observed initial and target states")
    columns = ["country_code", "year", "target_year", "state", "target_state", "changed"]
    reference = None
    for model in models:
        cases = predictions.loc[predictions.model.eq(model), columns].sort_values(["country_code", "year"]).reset_index(drop=True)
        if reference is not None and not cases.equals(reference):
            raise ValueError("Models must be evaluated on the same country-origin cases")
        reference = cases


def _performance_table(metrics: pd.DataFrame, predictions: pd.DataFrame,
                       models: list[str], periods: list[str]) -> pd.DataFrame:
    """Use each model's observed cases, never a sum over models or subsets."""
    _validated_predictions(predictions, models)
    if "period" not in metrics:
        metrics = metrics.assign(period="all")
    selected = metrics.loc[metrics.subset.eq("all")]
    if selected.duplicated(["period", "model"]).any():
        raise ValueError("Duplicate all-case model metric rows")
    rows = []
    for period in periods:
        for model in models:
            block = predictions.loc[predictions.model.eq(model) & _period_mask(predictions, period)]
            score = selected.loc[selected.period.eq(period) & selected.model.eq(model)]
            if len(score) != 1 or block.empty:
                raise ValueError(f"Missing model/period evaluation: {model}/{period}")
            score = score.iloc[0]
            changes = int(block.changed.sum())
            correct_changes = int((block.changed & block.predicted_state.eq(block.target_state)).sum())
            if int(score.n) != len(block) or int(score.changes) != changes:
                raise ValueError(f"Frozen metric counts disagree with predictions: {model}/{period}")
            if not np.isclose(float(score.accuracy), block.predicted_state.eq(block.target_state).mean(), atol=1e-12):
                raise ValueError(f"Frozen accuracy disagrees with predictions: {model}/{period}")
            rows.append({
                "Evaluation period": f"{PERIOD_NAMES[period]} ({_year_range(block.year)})",
                "Model": MODEL_NAMES[model], "Cases": len(block), "Observed changes": changes,
                "Correct change predictions": correct_changes,
                "Brier score": float(score.brier_multiclass),
                "Clipped log loss": float(score.log_loss_clipped),
                "Accuracy (%)": 100 * float(score.accuracy),
            })
    return pd.DataFrame(rows)


def _membership(dpi: pd.DataFrame) -> pd.DataFrame:
    latest = dpi.loc[dpi.year.eq(2023)]
    if latest.duplicated("country_code").any():
        raise ValueError("Duplicate January 2023 DPI country records")
    latest = latest.set_index("country_code")
    rows = []
    for code, country in sorted(COUNTRY_NAMES.items(), key=lambda item: item[1]):
        if code == "WLD":
            continue
        if code not in latest.index:
            state, status = "No DPI", "No DPI series"
        else:
            raw = latest.loc[code, "state"]
            state = raw if raw in STATES else "Unknown"
            status = "Classified" if state in STATES else "Record present; unclassified"
        rows.append({"Country": country, "Country code": code, "DPI state": state, "Coverage status": status})
    return pd.DataFrame(rows)


def _disagreement(hog: pd.DataFrame, leader: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for data in (hog, leader):
        if data.country_code.duplicated().any() or set(data.country_code) != set(COUNTRY_METADATA):
            raise ValueError("Source-disagreement input must contain exactly the 35 countries")
        if (data.disagreements > data.jointly_classified).any():
            raise ValueError("Disagreements exceed jointly classified country-years")
        rate = data.disagreements.div(data.jointly_classified.replace(0, np.nan))
        if not np.allclose(rate, data.disagreement_rate, equal_nan=True):
            raise ValueError("Source-disagreement rates disagree with their denominators")
    h, l = hog.set_index("country_code"), leader.set_index("country_code")
    for code in sorted(COUNTRY_METADATA, key=COUNTRY_NAMES.get):
        row = {"Country": COUNTRY_NAMES[code], "Country code": code}
        for label, data in (("HOG", h), ("Leader", l)):
            item = data.loc[code]
            n, disagreements = int(item.jointly_classified), int(item.disagreements)
            row.update({f"{label} paired records": n, f"{label} disagreements": disagreements,
                        f"{label} disagreement (%)": 100 * disagreements / n if n else np.nan})
        rows.append(row)
    overall = {"Country": "All countries (pooled)", "Country code": "ALL"}
    for label, data in (("HOG", hog), ("Leader", leader)):
        n, disagreements = int(data.jointly_classified.sum()), int(data.disagreements.sum())
        overall.update({f"{label} paired records": n, f"{label} disagreements": disagreements,
                        f"{label} disagreement (%)": 100 * disagreements / n if n else np.nan})
    return pd.DataFrame([*rows, overall])


def _coverage(root: Path, dpi: pd.DataFrame, hog: pd.DataFrame, leader: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for name, data, date, caveat in [
        ("DPI", dpi, "January 1 of source year", "Executive-party economic orientation; unknown records retained."),
        ("GLI: head of government", hog, "December 31; aligned to next January 1", "Leader orientation; separate historical panel, not a DPI splice."),
        ("GLI: leader role", leader, "December 31; aligned to next January 1", "Role sensitivity check; GLI partly draws on DPI coding."),
    ]:
        years = data.year if name == "DPI" else data.source_year
        rows.append({"Source": name, "Measure": "Political country-year records", "Source years": _year_range(years),
                     "Observation date": date, "Countries": str(data.country_code.nunique()), "Records": len(data),
                     "Classified records": int(data.state.isin(STATES).sum()), "Main caveat": caveat})
    wdi = _read(root, "data/processed/wdi_americas_world.csv")
    prices = _read(root, "data/processed/precios_anuales.csv")
    exposures = _json(root, "data/raw/driver_exposures_manifest.json")
    climate = _json(root, "data/raw/climate_manifest.json")["annual_coverage"]
    edges = _read(root, "outputs/main/aristas_red_2016.csv")
    pairs = {tuple(sorted((row.src, row.dst))) for row in edges.itertuples()}
    rows += [
        {"Source": "World Bank WDI: macroeconomy", "Measure": "Country-year grid", "Source years": _year_range(wdi.year),
         "Observation date": "Annual; revised historical series", "Countries": "35 + World", "Records": len(wdi),
         "Classified records": np.nan, "Main caveat": "Grid rows include missing values; not real-time release vintages."},
        {"Source": "World Bank WDI: driver exposures", "Measure": "Indicator-country-year grid", "Source years": "1960–2025 requested",
         "Observation date": "Annual; revised historical series", "Countries": "35",
         "Records": sum(int(source["rows"]) for source in exposures["sources"].values()), "Classified records": np.nan,
         "Main caveat": "Two indicators; missing values retained. Import and export shares have different denominators."},
        {"Source": "World Bank Pink Sheet", "Measure": "Complete annual global price aggregates", "Source years": _year_range(prices.year),
         "Observation date": "Annual aggregate of monthly observations", "Countries": "Global", "Records": len(prices),
         "Classified records": np.nan, "Main caveat": "Oil and food are common global indices, not country-specific exposure."},
        {"Source": "NOAA ONI (ERSSTv6)", "Measure": "Complete annual ENSO aggregates",
         "Source years": f"{climate['first_year']}–{climate['last_year']}", "Observation date": "11 overlapping windows: DJF–OND",
         "Countries": "Global", "Records": int(climate["complete_source_years"]), "Classified records": np.nan,
         "Main caveat": "Research aggregation, not an official annual NOAA index or anthropogenic climate measure."},
        {"Source": "COW Direct Contiguity v3.2", "Measure": "Undirected pairs in fitted 2016 snapshot", "Source years": "1816–2016",
         "Observation date": "Annual topology; model uses t-1", "Countries": str(len(pd.read_csv(root / "outputs/main/pesos_red_2016.csv", index_col=0))),
         "Records": len(pairs), "Classified records": np.nan,
         "Main caveat": "Land and water relations; 2016 carried forward after source coverage ends."},
    ]
    return pd.DataFrame(rows)


def _drivers() -> pd.DataFrame:
    rows = [
        ("Initial political state", "DPI / GLI (separate panels)", "January t; target January t+1", "Observed Left, Center or Right state", "Economic orientation coding; missing states excluded, not recoded as Center."),
        ("Ideological duration", "Derived within each political panel", "Consecutive classified years through t", "Memory of the same ideological state", "Not the leader's years in office; left-censored and interrupted by missing states."),
        ("Domestic growth and inflation", "World Bank WDI", "Annual t-1", "Domestic economic conditions", "Revised historical series; associations do not identify economic-voting effects."),
        ("Electoral competitiveness", "DPI EIEC", "Political snapshot t", "Executive election competitiveness code", "Not an annual election schedule; used by DPI domestic specifications only."),
        ("Trade and tourism exposure", "World Bank WDI", "Annual t-1 in legacy models", "Trade/GDP and tourism receipts/export shares", "Distinct denominators; exposure proxies are not bilateral trade links."),
        ("Geographic neighborhood", "COW Direct Contiguity / political panels", "Neighbor states t; topology t-1 (2016 carried forward)", "Known-neighbor ideological shares and coverage", "Undirected land/water proximity, not evidence of causal diffusion; unknown neighbors excluded from share denominators."),
        ("Global growth, oil and food prices", "WDI World / World Bank Pink Sheet", "Annual t-1", "Common macroeconomic and commodity variation", "Not country-specific shocks; legacy models interact with t-1 trade/import shares."),
        ("Oil × prior fuel-import share", "Pink Sheet / WDI TM.VAL.FUEL.ZS.UN", "Oil growth t-1 × import share t-2 / 100", "Import-side fuel exposure in driver extension", "Fuels are broader than petroleum; a share of merchandise imports, not net imports or energy dependence."),
        ("Oil × prior fuel-export share", "Pink Sheet / WDI TX.VAL.FUEL.ZS.UN", "Oil growth t-1 × export share t-2 / 100", "Export-side fuel exposure in driver extension", "Import and export share denominators differ; their difference is not net exposure."),
        ("ENSO × prior agriculture share", "NOAA ONI / WDI NV.AGR.TOTL.ZS", "ONI mean t-1 × agriculture/GDP t-2 / 100", "ENSO variability weighted by prior economic exposure", "11-window revised ONI aggregate; not national weather damage, anthropogenic warming or established January-1 information availability."),
        ("COVID episode", "Calendar indicator in legacy models", "1 when t-1 is 2020 or 2021", "Episode proxy at origins 2021–2022", "Not mortality; a new episode cannot be learned before it enters a training window."),
        ("Ukraine / oil counterfactuals", "Scenario assumptions", "Conditional scenario steps; not fitted Ukraine effects", "Specified commodity perturbations", "No estimable Ukraine indicator variation before the last DPI target; simulation is neither causal inference nor an operational forecast."),
    ]
    return pd.DataFrame(rows, columns=["Driver", "Source", "Time alignment", "Interpretation", "Main caveat"])


def _markdown_value(value, column: str) -> str:
    if pd.isna(value):
        return "—"
    if isinstance(value, (float, np.floating)):
        text = f"{value:.1f}" if "(%)" in column else f"{value:.4f}" if "score" in column or "loss" in column else f"{value:g}"
    else:
        text = str(value)
    return text.replace("|", "\\|").replace("\n", " ")


def _write_table(folder: Path, number: int, slug: str, title: str, caption: str,
                 source: str, data: pd.DataFrame, source_files: list[str]) -> dict:
    stem = f"Table_{number:02d}_{slug}"
    csv_path, md_path = folder / f"{stem}.csv", folder / f"{stem}.md"
    data.to_csv(csv_path, index=False)
    lines = [f"# Table {number}. {title}", "", caption, "",
             "| " + " | ".join(data.columns) + " |",
             "| " + " | ".join("---" for _ in data.columns) + " |"]
    lines += ["| " + " | ".join(_markdown_value(value, column) for column, value in zip(data.columns, row)) + " |"
              for row in data.itertuples(index=False, name=None)]
    lines += ["", "Source: " + source, "", "CSV values retain full numerical precision; Markdown values are rounded for display.", ""]
    md_path.write_text("\n".join(lines), encoding="utf-8")
    return {"id": f"Table_{number:02d}", "title": title, "caption": caption, "source": source,
            "stem": stem, "columns": list(data.columns), "row_count": len(data),
            "csv": str(csv_path), "markdown": str(md_path), "source_files": source_files,
            "language": "English"}


HUMAN_COLUMNS = {
    "country_code": "Country code", "country_name": "Country", "year": "Origin year",
    "source_year": "Source year", "target_year": "Target year", "origin_year": "Origin year",
    "state": "Initial state", "target_state": "Observed target state", "predicted_state": "Predicted state",
    "changed": "Observed change", "model": "Model", "period": "Evaluation period", "subset": "Evaluation subset",
    "n": "Cases", "changes": "Observed changes", "log_loss_clipped": "Clipped log loss",
    "brier_multiclass": "Multiclass Brier score", "brier_change": "Change-risk Brier score",
    "roc_auc_change": "Change-risk ROC AUC", "average_precision_change": "Change-risk average precision",
    "accuracy": "Accuracy (proportion)", "zero_probability_outcomes": "Zero-probability outcomes",
    "p_left": "Left probability", "p_center": "Center probability", "p_right": "Right probability",
    "p_change": "Change probability", "scenario": "Scenario", "mean_countries": "Mean countries",
    "q05": "5th percentile", "q95": "95th percentile", "bin": "Probability bin",
    "mean_predicted": "Mean predicted probability", "observed_fraction": "Observed fraction",
    "feature": "Feature ID", "coefficient": "Descriptive coefficient", "src": "Source country code",
    "dst": "Neighbor country code", "type": "Relationship", "distancecategory": "COW distance category",
    "scenario_oil_growth": "Oil change (%)", "missing_share": "Missing share (proportion)",
}


def _human_export(data: pd.DataFrame, *, political_snapshot: bool = False) -> pd.DataFrame:
    data = data.copy()
    for name, labels, identifier in [("model", MODEL_NAMES, "Model ID"), ("scenario", SCENARIO_NAMES, "Scenario ID"),
                                     ("period", PERIOD_NAMES, "Period ID"), ("subset", SUBSET_NAMES, "Subset ID")]:
        if name in data:
            unknown = set(data[name].dropna()) - set(labels)
            if unknown:
                raise ValueError(f"Missing English labels for {name}: {sorted(unknown)}")
            data[identifier] = data[name]
            data[name] = data[name].map(labels)
    if "country_code" in data:
        data["country_name"] = data.country_code.map(COUNTRY_NAMES)
    columns = {column: HUMAN_COLUMNS.get(column, column if " " in column or column in COUNTRY_NAMES else column.replace("_", " ").capitalize())
               for column in data.columns}
    if political_snapshot:
        columns.update({"year": "Political year", "state": "Observed state"})
        if "state" in data:
            data["state"] = data.state.where(data.state.isin(STATES), "Unknown")
    if "scenario" in data:
        columns.update({"year": "Simulated year", "state": "Simulated state"})
    return data.rename(columns=columns)


def _complete_exports(root: Path, folder: Path) -> None:
    """Human-facing copies; scientific files and their original IDs stay intact."""
    complete = folder / "complete"
    complete.mkdir(parents=True, exist_ok=True)
    exports = {
        "DPI_driver_metrics_by_period": "outputs/extensions/dpi_drivers/metrics_by_period.csv",
        "DPI_driver_predictions": "outputs/extensions/dpi_drivers/predictions.csv",
        "DPI_driver_feature_coverage": "outputs/extensions/dpi_drivers/feature_coverage.csv",
        "DPI_driver_conditional_oil_scenarios": "outputs/extensions/dpi_drivers/conditional_oil_scenarios.csv",
        "GLI_HOG_metrics": "outputs/extensions/gli_hog/metrics.csv",
        "GLI_HOG_predictions": "outputs/extensions/gli_hog/predictions.csv",
        "GLI_HOG_country_coverage": "outputs/history/gli_hog_coverage_35_countries.csv",
        "GLI_leader_country_coverage": "outputs/history/gli_leader_coverage_35_countries.csv",
    }
    for stem, source in exports.items():
        _human_export(_read(root, source)).to_csv(complete / f"{stem}.csv", index=False)
    _human_export(_read(root, "data/processed/dpi_americas.csv"), political_snapshot=True).to_csv(
        complete / "DPI_observed_states.csv", index=False)
    legacy = {
        "metricas.csv": "Model_metrics", "metricas_por_ano.csv": "Annual_model_metrics",
        "predicciones_fuera_muestra.csv": "Out_of_sample_predictions", "panel_transiciones.csv": "Transition_panel",
        "calibracion.csv": "Calibration", "escenarios_resumen.csv": "Scenario_summary",
        "cobertura_covariables.csv": "Covariate_coverage", "coeficientes_descriptivos.csv": "Descriptive_coefficients",
        "aristas_red_2016.csv": "Geographic_edges_2016", "caracteristicas.csv": "Feature_panel",
        "transiciones_conteos.csv": "Observed_transition_counts",
        "transiciones_probabilidades_descriptivas.csv": "Descriptive_transition_probabilities",
    }
    for run in sorted((root / "outputs").iterdir()):
        if not (run / "predicciones_fuera_muestra.csv").is_file():
            continue
        destination = complete / run.name
        destination.mkdir(exist_ok=True)
        for filename, stem in legacy.items():
            if (run / filename).is_file():
                _human_export(pd.read_csv(run / filename)).to_csv(destination / f"{stem}.csv", index=False)
        if (run / "pesos_red_2016.csv").is_file():
            weights = pd.read_csv(run / "pesos_red_2016.csv", index_col=0)
            weights.index.name = "country_code"
            _human_export(weights.reset_index()).to_csv(destination / "Geographic_weights_2016.csv", index=False)


def build_tables(root: str | Path, folder: str | Path) -> list[dict]:
    """Create six self-contained publication tables and full English CSV copies."""
    root, folder = Path(root).resolve(), Path(folder).resolve()
    folder.mkdir(parents=True, exist_ok=True)
    dpi_path = "data/processed/dpi_americas.csv"
    hog_path, leader_path = "outputs/history/gli_hog_aligned_panel.csv", "outputs/history/gli_leader_aligned_panel.csv"
    dpi, hog, leader = (_read(root, path) for path in (dpi_path, hog_path, leader_path))
    dpi_metrics_path = "outputs/extensions/dpi_drivers/metrics_by_period.csv"
    dpi_predictions_path = "outputs/extensions/dpi_drivers/predictions.csv"
    gli_metrics_path, gli_predictions_path = "outputs/extensions/gli_hog/metrics.csv", "outputs/extensions/gli_hog/predictions.csv"
    dpi_scores = _performance_table(_read(root, dpi_metrics_path), _read(root, dpi_predictions_path), DPI_MODELS, ["all", "pre2000", "2000plus"])
    gli_predictions = _read(root, gli_predictions_path)
    gli_scores = _performance_table(_read(root, gli_metrics_path), gli_predictions, GLI_MODELS, ["all"]).drop(columns="Evaluation period")
    h_compare = "outputs/history/dpi_gli_hog_comparison_by_country.csv"
    l_compare = "outputs/history/dpi_gli_leader_comparison_by_country.csv"
    tables = [
        _write_table(folder, 1, "source_coverage", "Source coverage and measurement units",
            "Coverage describes the cached source snapshot, not the evaluation sample. Records count the unit named in each row; political classifications and macroeconomic grids are not interchangeable denominators.",
            "DPI 2023; GLI; World Bank WDI and Pink Sheet; NOAA ONI; COW Direct Contiguity v3.2. Cached manifests preserve retrieval dates and hashes.",
            _coverage(root, dpi, hog, leader), [dpi_path, hog_path, leader_path, "data/raw/driver_exposures_manifest.json", "data/raw/climate_manifest.json"]),
        _write_table(folder, 2, "dpi_membership_2023", "Observed DPI classification on January 1, 2023",
            "All 35 sovereign countries in the Americas are listed. Unknown means a DPI record is present but unclassified; No DPI means no country series. Neither category is Center. Source classifications are retained without recoding and do not describe governments in 2026.",
            "DPI 2023, processed January 2023 records; 35-country project crosswalk.", _membership(dpi), [dpi_path]),
        _write_table(folder, 3, "aligned_source_disagreement", "DPI–GLI disagreement after date alignment",
            "GLI December 31 records are aligned to January 1 of the next year and compared with DPI over 1975–2021. Rates use jointly classified country-years only; an undefined rate is blank in CSV and shown as an em dash here. The pooled rate weights records, not countries. HOG denotes head of government. GLI partly uses DPI as a coding source; this is measurement sensitivity, not independent validation.",
            "Frozen DPI–GLI aligned comparison tables, head-of-government and leader roles.",
            _disagreement(_read(root, h_compare), _read(root, l_compare)), [h_compare, l_compare]),
        _write_table(folder, 4, "dpi_model_performance", "DPI driver-extension performance under chronological evaluation",
            "Periods are defined by prediction origin, not target year. Each row counts the same cases separately for one model; rows and overlapping periods must not be summed. Correct change predictions require the highest-probability class to equal the observed new state. Multiclass Brier scores sum squared error across three classes (range 0–2); lower scores and losses are better. Log loss uses a 10^-12 probability floor. Overall accuracy is dominated by persistence.",
            "Frozen DPI driver-extension predictions and period metrics; expanding training windows use only previous outcomes.",
            dpi_scores, [dpi_metrics_path, dpi_predictions_path]),
        _write_table(folder, 5, "gli_hog_model_performance", "GLI head-of-government historical-panel performance",
            f"Separate GLI panel; origins {_year_range(gli_predictions.year)}, aligned targets {_year_range(gli_predictions.target_year)}. The final aligned 2021 target represents the December 31, 2020 source observation. Correct change predictions use the highest-probability class. Brier range is 0–2; log-loss floor is 10^-12. All models share the same cases. This historical panel is not joined to DPI, and score levels from different samples do not constitute a controlled model comparison.",
            "Frozen GLI head-of-government predictions and metrics; chronological expanding evaluation.",
            gli_scores, [gli_metrics_path, gli_predictions_path]),
        _write_table(folder, 6, "driver_definitions", "Driver definitions, time alignment and interpretation",
            "t is the January prediction origin and t+1 the target. Driver extensions use prior exposure shares at t-2, whereas legacy interactions use t-1 shares. Revised sources support retrospective evaluation; they do not reconstruct real-time information sets. Coefficients and scenario responses are conditional model associations, not causal effects.",
            "Cached DPI/GLI, WDI, Pink Sheet, NOAA and COW sources; feature, driver and scenario definitions in the analysis code.",
            _drivers(), ["src/americas_markov/features.py", "src/americas_markov/drivers.py", "src/americas_markov/climate.py", "src/americas_markov/simulation.py"]),
    ]
    _complete_exports(root, folder)
    return tables


def rerender_cached_reports(root: str | Path) -> list[dict]:
    """Re-render existing legacy runs in English, with no downloads or model fits.

    Frozen scenario and calibration CSV bytes are restored after plotting to
    avoid unnecessary floating-point serialization changes in scientific files.
    The source metrics, predictions, panels and network weights are read only.
    """
    root = Path(root).resolve()
    politics = _read(root, "data/processed/dpi_americas.csv")
    outputs, rendered = root / "outputs", []
    required = ["predicciones_fuera_muestra.csv", "metricas.csv", "metricas_por_ano.csv",
                "panel_transiciones.csv", "pesos_red_2016.csv", "run_info.json"]
    for folder in sorted(outputs.iterdir()):
        if not folder.is_dir() or not all((folder / filename).is_file() for filename in required):
            continue
        scenario_path = folder / "escenarios_resumen.csv"
        scenario = pd.read_csv(scenario_path) if scenario_path.is_file() else None
        protected = {path: path.read_bytes() for path in [scenario_path, folder / "calibracion.csv", folder / "run_info.json"] if path.is_file()}
        try:
            render_results(pd.read_csv(folder / required[0]), pd.read_csv(folder / required[1]),
                           pd.read_csv(folder / required[2]), politics, pd.read_csv(folder / required[3]),
                           pd.read_csv(folder / required[4], index_col=0), scenario, folder,
                           json.loads((folder / required[5]).read_text(encoding="utf-8")))
        finally:
            for path, payload in protected.items():
                path.write_bytes(payload)
        rendered.append({"folder": str(folder), "report": str(folder / "RESULTADOS.txt"), "language": "English"})
    return rendered
