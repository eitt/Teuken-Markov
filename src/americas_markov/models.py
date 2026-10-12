"""Baselines y logit multinomial con regularización L2 y validación cronológica."""
from __future__ import annotations

import numpy as np
import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import average_precision_score, roc_auc_score
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler

from . import STATES
from .features import DOMESTIC_NUM, NETWORK_NUM, SHOCK_NUM, CATEGORICAL

MODEL_FEATURES = {
    "domestic": DOMESTIC_NUM,
    "network": DOMESTIC_NUM + NETWORK_NUM,
    "shocks": DOMESTIC_NUM + SHOCK_NUM,
    "network_shocks": DOMESTIC_NUM + NETWORK_NUM + SHOCK_NUM,
}
MODEL_ORDER = ["persistence", "markov", *MODEL_FEATURES]


def fit_model(train: pd.DataFrame, name: str):
    if not len(train): raise ValueError("Conjunto de entrenamiento vacío")
    if name == "persistence": return {"kind": name}
    if name == "markov":
        counts = pd.crosstab(train.state, train.target_state).reindex(index=STATES, columns=STATES, fill_value=0).astype(float)
        counts += 1.0  # suavizado de Laplace declarado; nunca usa el test
        return {"kind": name, "matrix": counts.div(counts.sum(axis=1), axis=0)}
    columns = MODEL_FEATURES[name]
    numeric = Pipeline([("impute", SimpleImputer(strategy="median", add_indicator=True, keep_empty_features=True)),
                        ("scale", StandardScaler())])
    preprocess = ColumnTransformer([("numeric", numeric, columns),
                                    ("categorical", OneHotEncoder(handle_unknown="ignore", sparse_output=False), CATEGORICAL)])
    if train.target_state.nunique() < 2:
        return {"kind": "constant", "label": train.target_state.iloc[0], "name": name}
    estimator = Pipeline([("preprocess", preprocess),
                          ("classifier", LogisticRegression(C=1.0, solver="lbfgs", max_iter=3000, random_state=2026))])
    estimator.fit(train, train.target_state)
    return {"kind": "logit", "name": name, "estimator": estimator, "numeric_columns": columns}


def predict_probabilities(model, frame: pd.DataFrame) -> np.ndarray:
    kind = model["kind"]
    if kind == "persistence":
        p = np.column_stack([frame.state.eq(s).to_numpy(dtype=float) for s in STATES])
    elif kind == "markov": p = model["matrix"].loc[frame.state].to_numpy(dtype=float)
    elif kind == "constant":
        p = np.zeros((len(frame), len(STATES)));p[:, STATES.index(model["label"])] = 1
    else:
        raw = model["estimator"].predict_proba(frame)
        p = np.zeros((len(frame), len(STATES)))
        for j, label in enumerate(model["estimator"].named_steps["classifier"].classes_):
            p[:, STATES.index(label)] = raw[:, j]
    if np.any(~np.isfinite(p)) or np.any(p < 0) or not np.allclose(p.sum(axis=1), 1):
        raise ValueError("Probabilidades inválidas o estados de entrada desconocidos")
    return p


def score_predictions(frame: pd.DataFrame) -> dict:
    p = frame[["p_left", "p_center", "p_right"]].to_numpy(dtype=float)
    y = np.column_stack([frame.target_state.eq(s).to_numpy(dtype=float) for s in STATES])
    actual_p = (p*y).sum(axis=1)
    initial_index = np.asarray([STATES.index(s) for s in frame.state])
    change_p = 1-p[np.arange(len(p)), initial_index]
    change_y = frame.changed.astype(int).to_numpy()
    # Persistencia es degenerada: el log-loss sin truncamiento sería infinito
    # cuando hay alternancia. Esta métrica documenta la cota numérica utilizada.
    logloss = -np.log(np.clip(actual_p, 1e-12, 1)).mean()
    return {"n": len(frame), "changes": int(frame.changed.sum()),
            "log_loss_clipped": float(logloss),
            "brier_multiclass": float(((p-y)**2).sum(axis=1).mean()),
            "brier_change": float(((change_p-change_y)**2).mean()),
            "roc_auc_change": float(roc_auc_score(change_y,change_p)) if np.unique(change_y).size==2 else np.nan,
            "average_precision_change": float(average_precision_score(change_y,change_p)) if np.unique(change_y).size==2 else np.nan,
            "accuracy": float(frame.predicted_state.eq(frame.target_state).mean()),
            "zero_probability_outcomes": int((actual_p == 0).sum())}


def rolling_evaluate(panel: pd.DataFrame, start_year=2000):
    outputs, fold_rows = [], []
    for origin in sorted(panel.loc[panel.year >= start_year, "year"].unique()):
        train, test = panel.loc[panel.year < origin], panel.loc[panel.year == origin]
        if len(train) < 40 or train.target_state.nunique() < 2: continue
        # Al 1 de enero del origen, sólo hay resultados observados hasta ese año.
        if int(train.target_year.max()) > origin: raise AssertionError("Fuga temporal")
        for name in MODEL_ORDER:
            fitted = fit_model(train, name)
            prob = predict_probabilities(fitted, test)
            keep = ["country_code", "year", "target_year", "state", "target_state", "changed"]
            result = test[keep].copy();result["model"] = name
            result[["p_left", "p_center", "p_right"]] = prob
            initial_index = np.asarray([STATES.index(s) for s in test.state])
            result["p_change"] = 1-prob[np.arange(len(test)), initial_index]
            result["predicted_state"] = np.asarray(STATES)[prob.argmax(axis=1)]
            result["train_max_origin"] = int(train.year.max())
            result["train_max_target"] = int(train.target_year.max())
            outputs.append(result)
            fold_rows.append({"model": name, "origin_year": int(origin), "train_n": len(train), **score_predictions(result)})
    if not outputs: raise ValueError("No hay folds con entrenamiento suficiente")
    predictions = pd.concat(outputs, ignore_index=True)
    metrics = []
    for name in MODEL_ORDER:
        subset = predictions.loc[predictions.model == name]
        for label, mask in [("all", np.ones(len(subset), dtype=bool)),
                            ("changed", subset.changed.to_numpy()), ("unchanged", ~subset.changed.to_numpy())]:
            part = subset.loc[mask]
            if len(part):metrics.append({"model": name, "subset": label, **score_predictions(part)})
    return predictions, pd.DataFrame(metrics), pd.DataFrame(fold_rows)


def coefficients(model) -> pd.DataFrame:
    if model["kind"] != "logit": return pd.DataFrame()
    est = model["estimator"]
    names = est.named_steps["preprocess"].get_feature_names_out()
    classifier = est.named_steps["classifier"]
    if classifier.coef_.shape[0] != len(classifier.classes_):
        return pd.DataFrame()  # caso binario: no inventar tres ecuaciones
    rows = [{"state": state, "feature": feature, "coefficient": float(value)}
            for state, values in zip(classifier.classes_, classifier.coef_)
            for feature, value in zip(names, values)]
    return pd.DataFrame(rows)
