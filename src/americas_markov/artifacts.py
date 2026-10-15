"""English artifact names with read compatibility for archived project runs.

Writers use English names. Readers prefer a canonical file and fall back to an
older filename only when the canonical file is absent. Raw source datasets and
their field values are never translated by these helpers.
"""
from __future__ import annotations

from pathlib import Path
import pandas as pd


SCENARIO_ALIASES = {
    "condiciones_constantes": "constant_conditions",
    "recesion_hipotetica": "hypothetical_recession",
    "energia_alimentos_hipotetico": "hypothetical_energy_food",
}
LEGACY_STEMS = {
    "annual_prices": "precios_anuales",
    "unknown_ideologies": "ideologias_desconocidas",
    "features": "caracteristicas",
    "transition_panel": "panel_transiciones",
    "feature_coverage": "cobertura_covariables",
    "transition_counts": "transiciones_conteos",
    "descriptive_transition_probabilities": "transiciones_probabilidades_descriptivas",
    "predictions": "predicciones_fuera_muestra",
    "metrics": "metricas",
    "metrics_by_year": "metricas_por_ano",
    "descriptive_coefficients": "coeficientes_descriptivos",
    "network_weights_2016": "pesos_red_2016",
    "network_edges_2016": "aristas_red_2016",
    "scenario_summary": "escenarios_resumen",
    "calibration": "calibracion",
    "model_comparison": "comparacion_modelos",
    "performance_by_year": "desempeno_por_ano",
    "scenarios": "escenarios",
    "RESULTS": "RESULTADOS",
}


def canonical_scenario(name: str) -> str:
    """Accept archived scenario identifiers while emitting English identifiers."""
    return SCENARIO_ALIASES.get(name, name)


def resolve_artifact(path: str | Path) -> Path:
    """Prefer an English path; use an archived filename without modifying it."""
    path = Path(path)
    if path.is_file():
        return path
    name = path.name
    for canonical, legacy in LEGACY_STEMS.items():
        if name.startswith(canonical + "."):
            candidate = path.with_name(legacy + name[len(canonical):])
            if candidate.is_file():
                return candidate
    if name.startswith("scenario_"):
        for legacy, canonical in SCENARIO_ALIASES.items():
            prefix = "scenario_" + canonical
            if name.startswith(prefix + "."):
                candidate = path.with_name("escenario_" + legacy + name[len(prefix):])
                if candidate.is_file():
                    return candidate
    return path


def normalize_scenario_columns(frame: pd.DataFrame) -> pd.DataFrame:
    """Return English scenario IDs without altering other columns or the input."""
    columns = [name for name in ("scenario", "scenario_id", "Scenario ID") if name in frame]
    if not columns:
        return frame
    result = frame.copy()
    for name in columns:
        result[name] = result[name].map(lambda value: SCENARIO_ALIASES.get(value, value))
    return result


def read_artifact_csv(path: str | Path, **kwargs) -> pd.DataFrame:
    """Read a canonical or archived CSV and normalize only scenario identifiers."""
    return normalize_scenario_columns(pd.read_csv(resolve_artifact(path), **kwargs))
