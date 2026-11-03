"""Live PDF extraction and clinical-only prediction audit for six synthetic fixtures."""
from __future__ import annotations

import argparse
import json
import math
from pathlib import Path

import requests


EXPECTED = {
    "medical-report-upload-test.pdf": (58, "male", 128, 78, 72, .90, 113),
    "sysdag-synthetic-medical-report-upload-test-002.pdf": (46, "female", 116, 72, 58, .79, 96),
    "sysdag-synthetic-medical-report-upload-test-003.pdf": (67, "male", 134, 82, 84, 1.10, 101),
    "sysdag-synthetic-medical-report-upload-test-004.pdf": (35, "female", 122, 76, 108, .71, 90),
    "sysdag-synthetic-medical-report-upload-test-005.pdf": (74, "male", 142, 86, 62, 1.16, 99),
    "sysdag-synthetic-medical-report-upload-test-006.pdf": (59, "female", 130, 80, 76, .85, 95),
}
FIELDS = ("age", "sex", "systolic_bp", "diastolic_bp", "resting_hr", "creatinine", "glucose")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="https://cardioscope-research.pages.dev")
    parser.add_argument("--directory", type=Path, default=Path.home() / "OneDrive/Desktop")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    base = args.base_url.rstrip("/")
    rows = []
    with requests.Session() as session:
        for filename, expected in EXPECTED.items():
            path = args.directory / filename
            with path.open("rb") as stream:
                response = session.post(base + "/api/parse-report",
                                        files={"report": (filename, stream, "application/pdf")}, timeout=90)
            response.raise_for_status()
            values = response.json()["values"]
            for key, wanted in zip(FIELDS, expected):
                actual = values.get(key)
                if isinstance(wanted, str):
                    assert actual == wanted, (filename, key, actual, wanted)
                else:
                    assert actual is not None and math.isclose(float(actual), wanted, abs_tol=.001), (filename, key, actual, wanted)
            prediction = session.post(base + "/api/predict", data={"clinical_json": json.dumps(values)}, timeout=90)
            prediction.raise_for_status()
            result = prediction.json()
            assert result["diagnostic_modality"] == "clinical_only"
            probabilities = result["disease_probabilities"]
            assert len(probabilities) == 5 and all(math.isfinite(value) and 0 <= value <= 1 for value in probabilities.values())
            assert result["health_score"] is not None and result["disclaimer"] == "Research & Educational Simulation Only"
            row = {"file": filename, "parse_status": response.status_code, "predict_status": prediction.status_code,
                   "extracted_values": values, "diagnostic_modality": result["diagnostic_modality"],
                   "disease_probabilities": probabilities, "health_score": result["health_score"],
                   "prevent_10y_cvd_percent": result["prevent_10y_cvd_percent"]}
            rows.append(row)
            print(f"{filename}: parsed {len(values)} fields; predict {prediction.status_code}; health index {result['health_score']}", flush=True)
    assert len({tuple(round(value, 4) for value in row["disease_probabilities"].values()) for row in rows}) == len(rows), "Predictions are identical across distinct reports"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps({"base_url": base, "results": rows}, indent=2), encoding="utf-8")
    print("PASS: six report values match source tables, six distinct clinical-only predictions returned")


if __name__ == "__main__":
    main()
