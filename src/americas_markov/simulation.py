"""Conditional annual probabilistic automaton, not a current election forecast.

Synchronous updating: all countries use states from the previous step.
The annual clock reproduces the model's unit; it does not invent election dates.
Domestic covariates and the graph remain fixed, except for ideological state
duration and explicitly specified shocks.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from . import STATES
from .artifacts import canonical_scenario
from .features import neighbor_features, shock_interactions
from .models import predict_probabilities

SCENARIOS = {
    "constant_conditions": {"world_growth": None, "oil_growth": 0.0, "food_growth": 0.0},
    "hypothetical_recession": {"world_growth": -2.0, "oil_growth": 0.0, "food_growth": 0.0},
    "hypothetical_energy_food": {"world_growth": None, "oil_growth": 50.0, "food_growth": 20.0},
}


def simulate(model, initial: pd.DataFrame, weights: pd.DataFrame,
             horizon=6, runs=500, seed=2026, scenario="constant_conditions",
             shock_duration=2):
    scenario = canonical_scenario(scenario)
    if scenario not in SCENARIOS: raise ValueError("Unknown scenario")
    if horizon < 1 or runs < 1 or shock_duration < 1: raise ValueError("Nonpositive simulation parameters")
    base = initial.copy().sort_values("country_code").reset_index(drop=True)
    if base.country_code.duplicated().any() or not base.state.isin(STATES).all():
        raise ValueError("Simulation requires one unique observed initial state per country")
    codes = list(base.country_code)
    w = weights.reindex(index=codes, columns=codes, fill_value=0).to_numpy(dtype=float)
    # Preserve weights toward excluded countries as missing coverage;
    # normalize proportions only among observed active neighbors.
    denom = w.sum(axis=1)
    w = np.divide(w, denom[:, None], out=np.zeros_like(w), where=denom[:, None] > 0)
    n = len(codes)
    geographically_isolated = weights.reindex(index=codes).fillna(0).sum(axis=1).eq(0).to_numpy(dtype=float)
    labels = np.asarray(STATES)
    current = np.tile([STATES.index(s) for s in base.state], (runs, 1))
    duration = np.tile(base.state_duration.fillna(1).to_numpy(dtype=float), (runs, 1))
    generator = np.random.default_rng(seed)
    start_year = int(base.year.max())
    rows = []
    for path in range(runs):
        for k, code in enumerate(codes):
            rows.append({"scenario": scenario, "path": path, "year": start_year,
                         "country_code": code, "state": labels[current[path,k]], "initial_observed": True})
    for step in range(1, horizon + 1):
        block = pd.concat([base] * runs, ignore_index=True)
        block["state"] = labels[current.ravel()]
        block["state_duration"] = duration.ravel()
        for j, column in enumerate(["neighbor_left", "neighbor_center", "neighbor_right"]):
            totals = (current == j).astype(float) @ w.T
            block[column] = totals.ravel()
        block["neighbor_known_weight"] = np.tile(denom, runs)
        block["isolated"] = np.tile(geographically_isolated, runs)
        # The baseline assumes constant prices rather than indefinitely repeating
        # the growth observed in 2022. The pandemic does not persist.
        block["oil_growth"] = 0.0;block["food_growth"] = 0.0;block["covid_lag"] = 0.0
        if step <= shock_duration:
            for key, value in SCENARIOS[scenario].items():
                if value is not None: block[key] = value
        block = shock_interactions(block)
        p = predict_probabilities(model, block).reshape(runs, n, 3)
        u = generator.random((runs, n))
        nxt = (u[..., None] > p.cumsum(axis=2)).sum(axis=2).clip(0, 2)
        duration = np.where(nxt == current, duration + 1, 1)
        current = nxt
        for path in range(runs):
            for k, code in enumerate(codes):
                rows.append({"scenario": scenario, "path": path, "year": start_year + step,
                             "country_code": code, "state": labels[current[path,k]], "initial_observed": False})
    draws = pd.DataFrame(rows)
    counts = draws.groupby(["scenario", "path", "year", "state"]).size().unstack("state", fill_value=0).reindex(columns=STATES, fill_value=0)
    summary = []
    for (scenario_name, year), block in counts.groupby(level=["scenario", "year"]):
        for state in STATES:
            values = block[state].to_numpy()
            summary.append({"scenario": scenario_name, "year": int(year), "state": state,
                            "mean_countries": float(values.mean()), "q05": float(np.quantile(values,.05)),
                            "q95": float(np.quantile(values,.95)), "runs": runs, "active_countries": n})
    return draws, pd.DataFrame(summary)
