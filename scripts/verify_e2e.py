"""Exercise live API in ECG+labs, lab-only, and manual-only modes."""
import csv
import json
from pathlib import Path
import requests

ROOT = Path(r"D:\CVG Project")
API = "http://127.0.0.1:8000/api"
manual = {"age": 55, "sex": "female", "systolic_bp": 132, "diastolic_bp": 82,
          "bmi": 28, "smoking_status": "current", "diabetes_status": "no",
          "physical_activity_mins_per_week": 90, "sleep_hours": 6.5,
          "hypertension_meds": "no", "statin_use": "no"}

with (ROOT / "ptb-xl-1.0.1/ptbxl_database.csv").open(newline="", encoding="utf-8") as stream:
    record = next(csv.DictReader(stream))["filename_hr"]
base = ROOT / "ptb-xl-1.0.1" / record
with base.with_suffix(".dat").open("rb") as dat, base.with_suffix(".hea").open("rb") as hea:
    response = requests.post(API + "/predict", data={"clinical_json": json.dumps({**manual, "total_cholesterol": 210, "hdl": 45, "creatinine": 1.0})},
                             files={"ecg": (base.name + ".dat", dat), "header": (base.name + ".hea", hea)}, timeout=240)
    response.raise_for_status()
    mode_a = response.json()

report = requests.post(API + "/parse-report", files={"report": ("labs.csv", b"total_cholesterol,hdl,creatinine,ldl\n210,45,1.0,135\n", "text/csv")}, timeout=30)
report.raise_for_status()
labs = report.json()["values"]
response = requests.post(API + "/predict", data={"clinical_json": json.dumps({**manual, **labs})}, timeout=90)
response.raise_for_status()
mode_b = response.json()

response = requests.post(API + "/predict", data={"clinical_json": json.dumps(manual)}, timeout=90)
response.raise_for_status()
mode_c = response.json()

scenario = requests.post(API + "/simulate", json={"clinical": {**manual, **labs},
    "changes": {"smoking_status": "former", "systolic_bp": 117, "bmi": 25,
                "physical_activity_mins_per_week": 150, "sleep_hours": 7.5, "ldl": 100},
    "disease_probabilities": mode_b["disease_probabilities"]}, timeout=30)
scenario.raise_for_status()

for name, result in (("A", mode_a), ("B", mode_b), ("C", mode_c)):
    assert 0 <= result["cvd_risk_score"] <= 100
    assert 0 <= result["health_score"] <= 100
    assert len(result["disease_probabilities"]) == 5
    assert all(0 < value < 1 for value in result["disease_probabilities"].values())
    assert max(result["disease_probabilities"].values()) > 1e-6
    assert len(result["clinical_icd_conditions"]) == 5
    assert len(result["disease_flags"]) == 5
    assert len(result["ecg_superclasses"]) == 5 if name == "A" else result["ecg_superclasses"] is None
    assert isinstance(result["feature_attribution"], list)
    assert isinstance(result["action_plan"], list)
    print(json.dumps({"mode": name, "status": 200, "labels": list(result["disease_probabilities"]),
                      "index": result["cvd_risk_score"], "prevent": result["prevent_10y_cvd_percent"],
                      "attributions": len(result["feature_attribution"]),
                      "waveform": bool(result["waveform"]),
                      "ptb_panel": bool(result["ecg_superclasses"]),
                      "flags": sum(result["disease_flags"].values())}))
print(json.dumps({"simulation_delta": scenario.json()["delta_index_points"]}))
