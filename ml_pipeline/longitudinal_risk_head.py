"""Research 10-year CHD model from a public Framingham teaching subset.

The outcome is coronary heart disease (TenYearCHD), not total CVD. The public
subset has no HDL, LDL, or activity measurements; those variables are not
silently fabricated or claimed as predictors.
"""
from __future__ import annotations

import os
os.environ["OMP_NUM_THREADS"] = "2"
os.environ["MKL_NUM_THREADS"] = "2"
os.environ["OPENBLAS_NUM_THREADS"] = "2"

import argparse
import json
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from scipy.optimize import minimize
from scipy.special import expit, logit
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import brier_score_loss, roc_auc_score
from sklearn.model_selection import train_test_split
from sklearn.preprocessing import StandardScaler

FIELDS = ("age", "sex_male", "systolic_bp", "diastolic_bp", "total_cholesterol",
          "bmi", "glucose", "current_smoker", "bp_meds", "diabetes")
MONOTONE = (1, 0, 1, 0, 1, 0, 0, 1, 0, 1)


def _priority():
    try:
        import ctypes
        kernel = ctypes.windll.kernel32
        kernel.SetPriorityClass(kernel.GetCurrentProcess(), 0x00004000)
    except (AttributeError, OSError):
        pass


def ece(y: np.ndarray, p: np.ndarray, bins: int = 10) -> float:
    result = 0.0
    for lo, hi in zip(np.linspace(0, 1, bins + 1)[:-1], np.linspace(0, 1, bins + 1)[1:]):
        mask = (p >= lo) & ((p < hi) if hi < 1 else (p <= hi))
        if mask.any():
            result += mask.mean() * abs(y[mask].mean() - p[mask].mean())
    return float(result)


def _clinical_row(record: dict) -> list[float]:
    def value(key):
        try:
            result = float(record.get(key, np.nan))
            return result if np.isfinite(result) else np.nan
        except (TypeError, ValueError):
            return np.nan
    sex = str(record.get("sex", "")).lower()
    smoke = str(record.get("smoking_status", "")).lower()
    bpmed = str(record.get("hypertension_meds", "")).lower()
    diabetes = str(record.get("diabetes_status", "")).lower()
    return [value("age"), 1.0 if sex in {"male", "m"} else 0.0 if sex in {"female", "f"} else np.nan,
            value("systolic_bp"), value("diastolic_bp"), value("total_cholesterol"), value("bmi"),
            value("glucose") if np.isfinite(value("glucose")) else value("fasting_blood_sugar"),
            1.0 if smoke == "current" else 0.0 if smoke in {"never", "former"} else np.nan,
            1.0 if bpmed in {"yes", "true", "1"} else 0.0 if bpmed in {"no", "false", "0"} else np.nan,
            1.0 if diabetes in {"yes", "true", "1"} else 0.0 if diabetes in {"no", "false", "0"} else np.nan]


def predict_risk(bundle: dict, clinical: dict) -> dict:
    raw = np.asarray([_clinical_row(clinical)], dtype=np.float64)
    missing = [key for key, is_missing in zip(FIELDS, ~np.isfinite(raw[0])) if is_missing]
    filled = bundle["imputer"].transform(raw)
    normalized = bundle["scaler"].transform(filled)
    gb = bundle["gb"].predict_proba(raw)[:, 1]
    linear = expit(normalized @ bundle["logistic_coef"] + bundle["logistic_intercept"])
    blended = (1 - bundle["alpha"]) * linear + bundle["alpha"] * gb
    probability = bundle["calibrator"].predict_proba(logit(np.clip(blended, 1e-5, 1 - 1e-5)).reshape(-1, 1))[:, 1]
    return {"percent": round(float(probability[0] * 100), 3),
            "outcome": "10-year coronary heart disease event (CHD), not total CVD",
            "input_quality": "complete" if not missing else "estimated missing inputs",
            "missing_fields": missing}


def train(root: Path) -> dict:
    _priority()
    data = pd.read_csv(root / "data/longitudinal_cohort.csv")
    if not set(FIELDS + ("chd_event_10y",)).issubset(data.columns):
        raise ValueError("Framingham CSV needs the declared fields and CHD outcome")
    x = data[list(FIELDS)].to_numpy(np.float64)
    y = data.chd_event_10y.to_numpy(np.int32)
    if len(x) < 4000 or not set(np.unique(y)).issubset({0, 1}):
        raise ValueError("Unexpected Framingham cohort")
    development, test = train_test_split(np.arange(len(y)), test_size=.2, stratify=y, random_state=42)
    train_idx, val_idx = train_test_split(development, test_size=.25, stratify=y[development], random_state=43)
    imputer = SimpleImputer(strategy="median").fit(x[train_idx])
    scaler = StandardScaler().fit(imputer.transform(x[train_idx]))
    z_train = scaler.transform(imputer.transform(x[train_idx]))
    gb = HistGradientBoostingClassifier(max_iter=160, learning_rate=.04,
                                        max_leaf_nodes=15, l2_regularization=5,
                                        monotonic_cst=MONOTONE, random_state=42)
    gb.fit(x[train_idx], y[train_idx])
    # Bounded logistic coefficients give the same requested risk direction for
    # observed age, SBP, total cholesterol, smoking, and diabetes.
    bounds = [(None, None)] + [(0, None) if direction == 1 else (None, None) for direction in MONOTONE]
    def objective(weights):
        pred = expit(weights[0] + z_train @ weights[1:])
        loss = -(y[train_idx] * np.log(pred + 1e-12) + (1 - y[train_idx]) * np.log(1 - pred + 1e-12)).mean()
        loss += .001 * np.sum(weights[1:] ** 2)
        residual = pred - y[train_idx]
        gradient = np.r_[residual.mean(), z_train.T @ residual / len(residual) + .002 * weights[1:]]
        return loss, gradient
    optimized = minimize(objective, np.r_[logit(y[train_idx].mean()), np.zeros(len(FIELDS))],
                         jac=True, bounds=bounds, method="L-BFGS-B", options={"maxiter": 500})
    if not optimized.success:
        raise RuntimeError(f"Constrained logistic fit failed: {optimized.message}")
    def raw_probs(indices):
        linear = expit(optimized.x[0] + scaler.transform(imputer.transform(x[indices])) @ optimized.x[1:])
        tree = gb.predict_proba(x[indices])[:, 1]
        return linear, tree
    val_linear, val_tree = raw_probs(val_idx)
    alpha = min(np.linspace(0, 1, 21), key=lambda a: brier_score_loss(y[val_idx], (1 - a) * val_linear + a * val_tree))
    val_blend = (1 - alpha) * val_linear + alpha * val_tree
    calibrator = LogisticRegression(C=10, random_state=42).fit(
        logit(np.clip(val_blend, 1e-5, 1 - 1e-5)).reshape(-1, 1), y[val_idx])
    test_linear, test_tree = raw_probs(test)
    test_blend = (1 - alpha) * test_linear + alpha * test_tree
    test_prob = calibrator.predict_proba(logit(np.clip(test_blend, 1e-5, 1 - 1e-5)).reshape(-1, 1))[:, 1]
    metrics = {"outcome": "10-year CHD event, not total CVD", "source_rows": len(y),
               "train_rows": len(train_idx), "validation_rows": len(val_idx), "test_rows": len(test),
               "positive_test_rows": int(y[test].sum()), "alpha_gbdt": float(alpha),
               "test_auroc": float(roc_auc_score(y[test], test_prob)),
               "test_brier": float(brier_score_loss(y[test], test_prob)),
               "test_ece": ece(y[test], test_prob),
               "test_event_rate": float(y[test].mean()),
               "limitations": "Public teaching subset lacks HDL, LDL, and activity; no external clinical validation."}
    bundle = {"fields": FIELDS, "imputer": imputer, "scaler": scaler,
              "gb": gb, "logistic_coef": optimized.x[1:], "logistic_intercept": optimized.x[0],
              "alpha": float(alpha), "calibrator": calibrator, "metrics": metrics}
    output = root / "models/longitudinal_10y_head.pkl"
    temporary = output.with_name("longitudinal_10y_head.tmp.pkl")
    joblib.dump(bundle, temporary)
    os.replace(temporary, output)
    metrics_path = root / "models/research_metrics.json"
    all_metrics = json.loads(metrics_path.read_text())
    all_metrics["longitudinal_chd_head_v2"] = metrics
    temp = metrics_path.with_name("research_metrics.tmp.json")
    temp.write_text(json.dumps(all_metrics, indent=2))
    os.replace(temp, metrics_path)
    return metrics


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--project-root", type=Path, default=Path(r"D:\CVG Project"))
    args = parser.parse_args()
    print(json.dumps(train(args.project_root), indent=2))
