"""Panel with explicit annual matching and lagged covariates.

DPI describes January 1 of year t. The state on January 1 of t+1 is
predicted using states from t and economic series from year t-1. These
are revised data; this does NOT reconstruct their real-time releases.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from . import STATES

DOMESTIC_NUM = ["gdp_growth", "inflation", "trade_open", "fuel_import_share",
                "tourism_exports_share", "state_duration", "eiec"]
NETWORK_NUM = ["neighbor_left", "neighbor_center", "neighbor_right",
               "neighbor_known_weight", "isolated"]
SHOCK_NUM = ["world_growth", "oil_growth", "food_growth", "covid_lag",
             "world_growth_x_trade", "oil_x_fuel", "food_x_trade",
             "covid_x_tourism"]
CATEGORICAL = ["state", "country_code"]


def valid_state(value):
    """Do not confuse an unknown state with Center."""
    return value if isinstance(value, str) and value in STATES else pd.NA


def neighbor_features(states: pd.Series, weights: pd.DataFrame) -> pd.DataFrame:
    """Proportions conditional on neighbors with observed ideology.

    With no known neighbors, return three zeros and zero coverage.
    An isolated row is not classified as a centrist neighborhood.
    """
    codes = list(weights.index)
    s = states.reindex(codes)
    w = weights.to_numpy(dtype=float).copy()
    np.fill_diagonal(w, 0.0)
    known = s.isin(STATES).to_numpy(dtype=float)
    coverage = w @ known
    proportions = []
    for label in STATES:
        total = w @ s.eq(label).fillna(False).to_numpy(dtype=float)
        proportions.append(np.divide(total, coverage, out=np.zeros_like(total), where=coverage > 0))
    return pd.DataFrame({
        "neighbor_left": proportions[0], "neighbor_center": proportions[1],
        "neighbor_right": proportions[2], "neighbor_known_weight": coverage,
        "isolated": (w.sum(axis=1) == 0).astype(float),
    }, index=codes)


def shock_interactions(frame: pd.DataFrame) -> pd.DataFrame:
    frame = frame.copy()
    # Percentages are converted to proportions only in these interactions.
    frame["world_growth_x_trade"] = frame["world_growth"] * frame["trade_open"] / 100
    frame["oil_x_fuel"] = frame["oil_growth"] * frame["fuel_import_share"] / 100
    frame["food_x_trade"] = frame["food_growth"] * frame["trade_open"] / 100
    frame["covid_x_tourism"] = frame["covid_lag"] * frame["tourism_exports_share"] / 100
    return frame


def prepare_features(politics: pd.DataFrame, wdi: pd.DataFrame,
                     prices: pd.DataFrame, networks: dict[int, pd.DataFrame]) -> pd.DataFrame:
    p = politics.copy().sort_values(["country_code", "year"])
    if p.duplicated(["country_code", "year"]).any():
        raise ValueError("DPI contains duplicate country-years; they are not silently aggregated.")
    for col in ["years_in_office", "eiec"]:
        if col not in p: p[col] = np.nan
    durations = []
    for _, block in p.groupby("country_code", sort=False):
        previous_state, previous_year, count = None, None, 0
        for row in block.itertuples():
            if not isinstance(row.state, str) or row.state not in STATES:
                count = 0; durations.append(np.nan)
            else:
                count = count + 1 if row.state == previous_state and row.year == previous_year + 1 else 1
                durations.append(float(count))
            previous_state, previous_year = row.state if isinstance(row.state, str) else None, row.year
    p["state_duration"] = durations
    economies = wdi.loc[wdi.country_code != "WLD"].copy()
    if economies.duplicated(["country_code", "year"]).any():
        raise ValueError("WDI contains duplicate country-years.")
    economies["economic_year"] = economies["year"]
    economies["year"] += 1
    f = p.merge(economies, on=["country_code", "year"], how="left", validate="one_to_one")
    f["economic_year"] = f["year"] - 1
    world = wdi.loc[wdi.country_code == "WLD", ["year", "gdp_growth"]].rename(columns={"gdp_growth": "world_growth"})
    global_data = world.merge(prices[["year", "oil_growth", "food_growth"]], on="year", how="outer", validate="one_to_one")
    global_data["year"] += 1
    f = f.merge(global_data, on="year", how="left", validate="many_to_one")
    f["covid_lag"] = f["economic_year"].between(2020, 2021).astype(float)
    # Documentation flag, deliberately excluded from SHOCK_NUM:
    # DPI2023 has no observation with origin 2023 and outcome 2024.
    f["ukraine_lag_not_estimable"] = (f["economic_year"] >= 2022).astype(float)
    chunks = []
    for year, block in f.groupby("year", sort=True):
        if int(year) not in networks: raise ValueError(f"Missing network for {year}")
        s = block.set_index("country_code")["state"]
        nf = neighbor_features(s, networks[int(year)])
        b = block.join(nf, on="country_code")
        b["network_snapshot_year"] = networks[int(year)].attrs.get("snapshot_year", min(int(year), 2016))
        chunks.append(b)
    return shock_interactions(pd.concat(chunks, ignore_index=True))


def make_transition_panel(features: pd.DataFrame, competitive_only=False) -> pd.DataFrame:
    # Matching before excluding missing states avoids skipping empty years.
    nxt = features[["country_code", "year", "state"]].copy()
    nxt["target_year"] = nxt["year"]
    nxt["year"] -= 1
    nxt = nxt.rename(columns={"state": "target_state"})
    panel = features.merge(nxt, on=["country_code", "year"], how="left", validate="one_to_one")
    valid = panel.state.isin(STATES) & panel.target_state.isin(STATES)
    if competitive_only: valid &= panel.eiec.ge(6)
    panel = panel.loc[valid].copy()
    panel["target_year"] = panel["target_year"].astype(int)
    panel["changed"] = panel.state.ne(panel.target_state)
    if not panel.target_year.eq(panel.year + 1).all(): raise AssertionError("Invalid temporal matching")
    return panel.sort_values(["year", "country_code"]).reset_index(drop=True)
