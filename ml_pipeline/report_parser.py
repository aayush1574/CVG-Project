"""Conservative report extraction; ambiguous values require human review."""
from __future__ import annotations
import csv
import io
import json
import re
from pathlib import Path

ALIASES = {
    "total_cholesterol": (r"total\s+cholesterol", r"cholesterol,?\s+total"),
    "hdl": (r"hdl(?:\s+cholesterol)?",), "ldl": (r"ldl(?:\s+cholesterol)?",),
    "triglycerides": (r"triglycerides?",), "fasting_blood_sugar": (r"fasting\s+(?:blood\s+)?(?:glucose|sugar)",),
    "hba1c": (r"(?:hba1c|hemoglobin\s+a1c)",), "creatinine": (r"(?:serum\s+)?creatinine",),
    "glucose": (r"(?<!fasting\s)glucose",),
    "egfr": (r"e[- ]?gfr",), "troponin": (r"(?:high[- ]?sensitivity\s+)?troponin",),
    "systolic_bp": (r"systolic(?:\s+blood\s+pressure)?",),
    "diastolic_bp": (r"diastolic(?:\s+blood\s+pressure)?",),
    "resting_hr": (r"(?:resting\s+)?heart\s+rate",),
}


def extract_text(text: str) -> dict:
    result = {}
    for key, patterns in ALIASES.items():
        values = set()
        for pattern in patterns:
            regex = rf"(?im)\b(?:{pattern})\b\s*(?::|=|[-–])?\s*(\d+(?:\.\d+)?)\b"
            values.update(float(m.group(1)) for m in re.finditer(regex, text))
        if len(values) == 1:
            result[key] = values.pop()
    # Structured reports can repeat time-series measurements and then state a
    # single, explicit aggregate. Read that row rather than choosing an
    # arbitrary measurement from a repeated label.
    section = re.search(r"(?is)\bAggregate model fields\b(.*?)(?:\b12-lead ECG summary\b|\bUpload verification checklist\b|\Z)", text)
    if section:
        for key, label in (("creatinine", "creatinine"), ("glucose", "glucose")):
            rows = re.findall(rf"(?im)^\s*{label}\s+(\d+(?:\.\d+)?)\s+\d+(?:\.\d+)?\s+\d+(?:\.\d+)?\s+\d+\s*$", section.group(1))
            if len(rows) == 1:
                result[key] = float(rows[0])
    # The fitted MIMIC transform used the last available creatinine/glucose
    # measurement. For a clearly labeled time series, take its final column.
    timed = re.search(r"(?is)\bLab family\b\s+(?:\d+\s*h\s+){2,}\bUnit\b(.*?)(?:\bAggregate model fields\b|\b12-lead ECG summary\b|\Z)", text)
    if timed:
        for key, label in (("creatinine", "creatinine"), ("glucose", "glucose")):
            rows = re.findall(rf"(?im)^\s*{label}\s+((?:\d+(?:\.\d+)?\s+){{3,}})\S+\s*$", timed.group(1))
            if len(rows) == 1:
                measurements = re.findall(r"\d+(?:\.\d+)?", rows[0])
                if measurements:
                    result[key] = float(measurements[-1])
    age = re.findall(r"(?im)\bAge\s+(\d{1,3})\s+years?\b", text)
    if len(set(age)) == 1 and age:
        result["age"] = int(age[0])
    sex = re.findall(r"(?im)\b(?:Recorded\s+sex|Sex)\s+(Male|Female)\b", text)
    if len(set(value.lower() for value in sex)) == 1 and sex:
        result["sex"] = sex[0].lower()
    pressure = re.findall(r"(?im)\b(?:Blood\s+pressure|BP)\s+(\d{2,3})\s*/\s*(\d{2,3})\s*mmHg\b", text)
    if len(set(pressure)) == 1 and pressure:
        result["systolic_bp"], result["diastolic_bp"] = map(int, pressure[0])
    return result


def parse_report(data: bytes, filename: str, content_type: str = "", include_evidence: bool = False) -> dict:
    if len(data) > 10_000_000:
        raise ValueError("Report exceeds 10 MB")
    suffix = Path(filename).suffix.lower()
    if suffix == ".pdf":
        import pdfplumber
        with pdfplumber.open(io.BytesIO(data)) as pdf:
            text = "\n".join(page.extract_text() or "" for page in pdf.pages[:20])
    elif suffix in {".png", ".jpg", ".jpeg", ".tif", ".tiff"}:
        from PIL import Image
        import numpy as np
        import shutil
        picture = Image.open(io.BytesIO(data)).convert("RGB")
        if shutil.which("tesseract"):
            import pytesseract
            text = pytesseract.image_to_string(picture)
        else:
            from rapidocr_onnxruntime import RapidOCR
            lines, _ = RapidOCR()(np.asarray(picture))
            text = "\n".join(line[1] for line in (lines or []))
    elif suffix == ".json":
        obj = json.loads(data)
        if not isinstance(obj, dict):
            raise ValueError("JSON report must be an object")
        values = {key: value for key, value in obj.items() if key in ALIASES and isinstance(value, (int, float))}
        return {"values":values,"fields":[{"field":key,"value":value,"source_text":f'{key}: {value}',"unit_status":"canonical API units assumed; confirm source","reference_interval":None} for key,value in values.items()]} if include_evidence else values
    elif suffix == ".csv":
        rows = list(csv.DictReader(io.StringIO(data.decode("utf-8-sig"))))
        if len(rows) != 1:
            raise ValueError("CSV report must have one data row with biomarker column names")
        values = {key: float(value) for key, value in rows[0].items() if key in ALIASES and value}
        return {"values":values,"fields":[{"field":key,"value":value,"source_text":f'{key}: {value}',"unit_status":"canonical column units assumed; confirm source","reference_interval":None} for key,value in values.items()]} if include_evidence else values
    else:
        raise ValueError("Supported reports: PDF, image, CSV, JSON")
    values=extract_text(text)
    evidence=[]
    from .evidence_report import UNITS
    for key,value in list(values.items()):
        matches=[]
        for line in text.splitlines():
            for pattern in ALIASES.get(key,()):
                match=re.search(rf'(?i)\b(?:{pattern})\b\s*(?::|=|[-–])?\s*(\d+(?:\.\d+)?)\s*([^\n]*)',line)
                if match and float(match.group(1))==float(value):matches.append((line,match.group(2)))
        unique=list(dict.fromkeys(matches))
        source=unique[0][0] if len(unique)==1 else None
        tail=unique[0][1].strip() if len(unique)==1 else ''
        unit_match=re.match(r'(?i)(mg\s*/\s*d[lL]|mmol\s*/\s*[lL]|(?:u|µ|μ)mol\s*/\s*[lL]|mmHg|g\s*/\s*d[lL]|%)',tail)
        original_unit=unit_match.group(0) if unit_match else None
        normalized=re.sub(r'\s+','',original_unit or '').lower()
        factor=None
        if normalized=='mmol/l':
            if key in {'total_cholesterol','hdl','ldl'}:factor=38.67
            elif key=='triglycerides':factor=88.57
            elif key in {'glucose','fasting_blood_sugar'}:factor=18.018
        elif normalized in {'umol/l','µmol/l','μmol/l'} and key=='creatinine':factor=1/88.4
        if factor is not None:values[key]=round(value*factor,4)
        reference=None
        ref=re.search(r'(?i)(?:reference|ref\.?\s*range|reference\s*range)\s*[:=]?\s*(\d+(?:\.\d+)?)\s*[-–]\s*(\d+(?:\.\d+)?)',tail)
        if ref:reference={'low':float(ref.group(1)),'high':float(ref.group(2)),'unit':original_unit,'source':'explicit labeled report interval; not a model decision threshold'}
        evidence.append({'field':key,'value':values[key],'original_value':value,'original_unit':original_unit,
                         'canonical_unit':UNITS.get(key),'source_text':source,'conversion_factor':factor,
                         'unit_status':'converted from explicit unit' if factor else 'explicit source unit; review' if original_unit else 'unit not extracted; confirm before assessment',
                         'reference_interval':reference,'confirmed':False})
    return {"values":values,"fields":evidence} if include_evidence else values
