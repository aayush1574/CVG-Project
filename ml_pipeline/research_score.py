"""Transparent educational composite; not an event probability or medical score."""
from __future__ import annotations
from .prevent_calculator import calculate_prevent_10y

REFERENCES = {"systolic_bp": 120, "total_cholesterol": 180, "hdl": 50,
              "bmi": 25, "ldl": 100, "triglycerides": 120,
              "fasting_blood_sugar": 90, "hba1c": 5.4, "creatinine": 0.9,
              "smoking_status": "never", "physical_activity_mins_per_week": 150,
              "sleep_hours": 7.5, "stress_level": 3, "diet_quality_score": 8}


def _bounded(value, low=0., high=1.):
    return max(low, min(high, value))


def _numeric(clinical, key, fallback):
    try:
        return float(clinical.get(key, fallback))
    except (ValueError, TypeError):
        return float(fallback)


def calculate_research_score(clinical: dict, disease_probabilities: dict | None = None) -> dict:
    """Return an uncalibrated index assembled from explicit, fixed components."""
    try:
        prevent = calculate_prevent_10y(clinical)
    except ValueError:
        prevent = None
    baseline = prevent["risk_percent"] if prevent else None
    # Display scale only: PREVENT remains a separate, genuine 10-year estimate.
    prevent_index = _bounded((baseline or 0) / 30) * 100 if baseline is not None else 0
    diagnostic = 0.
    if disease_probabilities:
        abnormal = [float(v) for k, v in disease_probabilities.items() if k != "NORM"]
        diagnostic = 100 * (_bounded(max(abnormal)) if abnormal else 0)
    lab = 100 * sum((
        _bounded((_numeric(clinical, "ldl", 100) - 100) / 100),
        _bounded((_numeric(clinical, "triglycerides", 120) - 150) / 250),
        _bounded((_numeric(clinical, "hba1c", 5.4) - 5.7) / 4),
        _bounded((_numeric(clinical, "fasting_blood_sugar", 90) - 100) / 150),
    )) / 4
    lifestyle = 100 * sum((
        float(str(clinical.get("smoking_status", "never")).lower() == "current"),
        _bounded((150 - _numeric(clinical, "physical_activity_mins_per_week", 150)) / 150),
        _bounded(abs(_numeric(clinical, "sleep_hours", 7.5) - 7.5) / 5),
        _bounded((_numeric(clinical, "stress_level", 3) - 3) / 7),
        _bounded((8 - _numeric(clinical, "diet_quality_score", 8)) / 8),
    )) / 5
    weights = ((.55 if baseline is not None else 0, prevent_index),
               (.25 if disease_probabilities else 0, diagnostic), (.10, lab), (.10, lifestyle))
    total_weight = sum(w for w, _ in weights)
    index = sum(w * score for w, score in weights) / total_weight if total_weight else 0
    return {"cvd_risk_score": round(index, 1), "health_score": round(100 - index, 1),
            "prevent_10y_cvd_percent": baseline,
            "prevent_quality": prevent,
            "components": {"prevent_display_index": round(prevent_index, 1) if prevent else None,
                           "ecg_diagnostic_index": round(diagnostic, 1) if disease_probabilities else None,
                           "lab_heuristic_index": round(lab, 1),
                           "lifestyle_heuristic_index": round(lifestyle, 1)},
            "score_type": "uncalibrated educational composite index; not a probability"}


def attribute_score(clinical: dict, disease_probabilities: dict | None = None) -> list[dict]:
    base = calculate_research_score(clinical, disease_probabilities)["cvd_risk_score"]
    output = []
    for key, reference in REFERENCES.items():
        if key not in clinical or clinical[key] in (None, ""):
            continue
        changed = {**clinical, key: reference}
        changed_score = calculate_research_score(changed, disease_probabilities)["cvd_risk_score"]
        delta = round(base - changed_score, 2)
        if abs(delta) >= .01:
            output.append({"feature": key, "reference_value": reference,
                           "score_points_vs_reference": delta,
                           "direction": "raises index" if delta > 0 else "lowers index"})
    return sorted(output, key=lambda item: abs(item["score_points_vs_reference"]), reverse=True)[:8]


def action_plan(clinical: dict, disease_probabilities: dict | None = None) -> list[dict]:
    items = []
    if _numeric(clinical, "systolic_bp", 120) >= 130:
        items.append({"topic": "Blood pressure", "observation": "Entered systolic BP is elevated", "suggestion": "Confirm readings with a clinician."})
    if str(clinical.get("smoking_status", "never")).lower() == "current":
        items.append({"topic": "Smoking", "observation": "Current smoking reported", "suggestion": "Discuss cessation support with a clinician."})
    if _numeric(clinical, "ldl", 100) >= 130:
        items.append({"topic": "LDL cholesterol", "observation": "Entered LDL is above the reference used by this simulation", "suggestion": "Review the lipid report and overall risk with a clinician."})
    if _numeric(clinical, "physical_activity_mins_per_week", 150) < 150:
        items.append({"topic": "Activity", "observation": "Entered weekly activity is below 150 minutes", "suggestion": "Discuss a safe activity plan appropriate to your health."})
    if disease_probabilities and max(float(v) for k, v in disease_probabilities.items() if k != "NORM") >= .5:
        items.append({"topic": "Condition model", "observation": "At least one diagnosis-group research output is elevated", "suggestion": "Review the supplied evidence and clinical context with a qualified clinician."})
    return items
