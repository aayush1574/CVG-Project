"""Published PREVENT base 10-year total-CVD equation (research use).

Coefficients and transforms follow the CDC KDSS implementation of the AHA
PREVENT base equation. BMI is not a predictor in the *total CVD base* model.
Inputs must use mg/dL for cholesterol and creatinine, mmHg for SBP.
"""
from __future__ import annotations

from math import exp, isfinite

COEFFICIENTS = {
    "female": (-3.307728, .7939329, .0305239, -.1606857, -.2394003,
               .360078, .8667604, .5360739, .6045917, .0433769,
               .3151672, -.1477655, -.0663612, .1197879, -.0819715,
               .0306769, -.0946348, -.27057, -.078715, -.1637806),
    "male": (-3.031168, .7688528, .0736174, -.0954431, -.4347345,
             .3362658, .7692857, .4386871, .5378979, .0164827,
             .288879, -.1337349, -.0475924, .150273, -.0517874,
             .0191169, -.1049477, -.2251948, -.0895067, -.1543702),
}
DEFAULTS = {"total_cholesterol": 180., "hdl": 50., "systolic_bp": 120.,
            "egfr": 90., "diabetes_status": "no", "smoking_status": "never",
            "hypertension_meds": "no", "statin_use": "no"}
RANGES = {"total_cholesterol": (130, 320), "hdl": (20, 100), "systolic_bp": (90, 200), "egfr": (1, 150)}


def egfr_2021(creatinine_mg_dl: float, age: float, sex: str) -> float:
    """CKD-EPI 2021 creatinine equation; assumes standardized creatinine."""
    if sex not in COEFFICIENTS or creatinine_mg_dl <= 0 or age < 18:
        raise ValueError("eGFR requires adult age, binary equation sex, and positive creatinine")
    k, alpha = (.7, -.241) if sex == "female" else (.9, -.302)
    ratio = creatinine_mg_dl / k
    return 142 * min(ratio, 1) ** alpha * max(ratio, 1) ** -1.2 * .9938 ** age * (1.012 if sex == "female" else 1)


def calculate_prevent_10y(clinical: dict) -> dict:
    """Return base 10-year total-CVD percentage and input-quality metadata."""
    sex = str(clinical.get("sex", "")).lower()
    try:
        age = float(clinical["age"])
    except (KeyError, TypeError, ValueError):
        raise ValueError("PREVENT requires age 30–79") from None
    if sex not in COEFFICIENTS or not 30 <= age <= 79:
        raise ValueError("PREVENT base equation requires female/male equation sex and age 30–79")
    values = dict(clinical)
    if values.get("egfr") is None and values.get("creatinine") is not None:
        values["egfr"] = egfr_2021(float(values["creatinine"]), age, sex)
    imputed, clamped = [], []
    for key, default in DEFAULTS.items():
        if values.get(key) in (None, ""):
            values[key] = default
            imputed.append(key)
    for key, (low, high) in RANGES.items():
        raw = float(values[key])
        if not isfinite(raw):
            raise ValueError(f"{key} must be finite")
        if raw < low or raw > high:
            values[key] = max(low, min(high, raw))
            clamped.append(key)
    tc, hdl, sbp, egfr = (float(values[key]) for key in ("total_cholesterol", "hdl", "systolic_bp", "egfr"))
    dm = int(str(values["diabetes_status"]).lower() in ("yes", "true", "1"))
    smoke = int(str(values["smoking_status"]).lower() == "current")
    bpmed = int(str(values["hypertension_meds"]).lower() in ("yes", "true", "1"))
    statin = int(str(values["statin_use"]).lower() in ("yes", "true", "1"))
    a = (age - 55) / 10
    n = (tc - hdl) * .02586 - 3.5
    h = (hdl * .02586 - 1.3) / .3
    s_low = (min(sbp, 110) - 110) / 20
    s_high = (max(sbp, 110) - 130) / 20
    g_low = (min(egfr, 60) - 60) / -15
    g_high = (max(egfr, 60) - 90) / -15
    terms = (1, a, n, h, s_low, s_high, dm, smoke, g_low, g_high,
             bpmed, statin, bpmed * s_high, statin * n, a * n, a * h,
             a * s_high, a * dm, a * smoke, a * g_low)
    log_odds = sum(c * t for c, t in zip(COEFFICIENTS[sex], terms, strict=True))
    risk = 100 / (1 + exp(-log_odds))
    return {"risk_percent": round(risk, 3), "imputed_fields": imputed,
            "clamped_fields": clamped, "complete": not imputed and not clamped,
            "confidence": "complete inputs" if not imputed and not clamped else "low: imputed or bounded inputs",
            "equation": "AHA PREVENT base 10-year total CVD"}
