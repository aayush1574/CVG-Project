"""Exercise a staged Space API using fixtures generated entirely in memory."""
from __future__ import annotations

import argparse
import csv
import io
import json
import math

import requests
from PIL import Image, ImageDraw


def digital_ecg() -> bytes:
    stream = io.StringIO()
    writer = csv.writer(stream)
    writer.writerow(("I", "II", "III", "aVR", "aVL", "aVF", "V1", "V2", "V3", "V4", "V5", "V6"))
    for sample in range(5000):
        writer.writerow(f"{math.sin(sample * .02 + lead * .1):.5f}" for lead in range(12))
    return stream.getvalue().encode()


def scanned_ecg() -> bytes:
    image = Image.new("RGB", (1200, 900), "white")
    draw = ImageDraw.Draw(image)
    for row in range(3):
        for col in range(4):
            left, right = col * 300 + 10, (col + 1) * 300 - 10
            center = row * 300 + 150
            points = [(x, center + int(30 * math.sin((x - left) * .07 + row + col))) for x in range(left, right)]
            draw.line(points, fill="black", width=3)
    stream = io.BytesIO()
    image.save(stream, format="PNG")
    return stream.getvalue()


def report_pdf() -> bytes:
    content = b"BT /F1 14 Tf 50 750 Td (Total Cholesterol: 210) Tj 0 -24 Td (HDL: 48) Tj 0 -24 Td (LDL: 135) Tj 0 -24 Td (Creatinine: 1.1) Tj ET"
    objects = [b"<< /Type /Catalog /Pages 2 0 R >>",
               b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
               b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>",
               b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
               b"<< /Length " + str(len(content)).encode() + b" >>\nstream\n" + content + b"\nendstream"]
    result = bytearray(b"%PDF-1.4\n")
    offsets = [0]
    for index, body in enumerate(objects, 1):
        offsets.append(len(result))
        result.extend(f"{index} 0 obj\n".encode() + body + b"\nendobj\n")
    start = len(result)
    result.extend(f"xref\n0 {len(objects)+1}\n0000000000 65535 f \n".encode())
    for offset in offsets[1:]:
        result.extend(f"{offset:010d} 00000 n \n".encode())
    result.extend(f"trailer\n<< /Size {len(objects)+1} /Root 1 0 R >>\nstartxref\n{start}\n%%EOF".encode())
    return bytes(result)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", default="http://127.0.0.1:8001")
    args = parser.parse_args()
    base = args.url.rstrip("/")
    clinical = {"age": 62, "sex": "male", "systolic_bp": 135, "bmi": 27,
                "creatinine": 1.1, "total_cholesterol": 210, "hdl": 48,
                "smoking_status": "former", "physical_activity_mins_per_week": 120,
                "sleep_hours": 7}

    digital = requests.post(base + "/api/predict", data={"clinical_json": json.dumps(clinical), "sample_rate": "500"},
                            files={"ecg": ("synthetic.csv", digital_ecg(), "text/csv")}, timeout=120)
    digital.raise_for_status()
    digital_body = digital.json()
    assert len(digital_body["ecg_superclasses"]) == 5
    assert len(digital_body["clinical_icd_conditions"]) == 5
    assert digital_body["health_score"] is not None
    print("digital_ecg_predict", digital.status_code, digital_body["diagnostic_modality"])

    scan = requests.post(base + "/api/predict", data={"clinical_json": json.dumps(clinical)},
                         files={"ecg": ("scan.png", scanned_ecg(), "image/png")}, timeout=120)
    scan.raise_for_status()
    scan_body = scan.json()
    assert scan_body["waveform_quality"]["method"].startswith("experimental")
    assert len(scan_body["ecg_superclasses"]) == 5
    print("scanned_ecg_predict", scan.status_code, scan_body["waveform_quality"]["coverage"])

    report = requests.post(base + "/api/parse-report", files={"report": ("labs.pdf", report_pdf(), "application/pdf")}, timeout=30)
    report.raise_for_status()
    values = report.json()["values"]
    assert values["total_cholesterol"] == 210 and values["creatinine"] == 1.1
    print("pdf_parse", report.status_code, values)
    clinical_only = requests.post(base + "/api/predict", data={"clinical_json": json.dumps({**clinical, **values})}, timeout=30)
    clinical_only.raise_for_status()
    assert clinical_only.json()["diagnostic_modality"] == "clinical_only"
    print("clinical_only_predict", clinical_only.status_code)

    scenario = requests.post(base + "/api/simulate", json={"clinical": clinical,
                             "changes": {"smoking_status": "never", "systolic_bp": 120, "physical_activity_mins_per_week": 180}}, timeout=30)
    scenario.raise_for_status()
    assert "delta_index_points" in scenario.json()
    print("lifestyle_simulate", scenario.status_code, scenario.json()["delta_index_points"])


if __name__ == "__main__":
    main()
