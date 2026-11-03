"""Shared schema and train-fitted tabular transform."""
from __future__ import annotations
import numpy as np
from sklearn.impute import SimpleImputer
from sklearn.preprocessing import StandardScaler
from .prevent_calculator import egfr_2021

NUMERIC = ("age", "systolic_bp", "diastolic_bp", "resting_hr", "total_cholesterol", "hdl", "ldl", "triglycerides", "fasting_blood_sugar", "hba1c", "creatinine", "egfr", "troponin", "bmi", "packs_per_day", "alcohol_intake", "physical_activity_mins_per_week", "diet_quality_score", "sleep_hours", "stress_level")
CATEGORICAL = ("sex", "smoking_status", "family_history_cvd", "hypertension_meds", "statin_use", "diabetes_status")
CATEGORIES = {"sex": ("female", "male", "other"), "smoking_status": ("never", "former", "current"), **{key: ("no", "yes") for key in CATEGORICAL[2:]}}
ENGINEERED = ("pulse_pressure", "mean_arterial_pressure", "non_hdl_cholesterol",
              "tg_to_hdl_ratio", "chol_to_hdl_ratio", "tyg_index", "egfr_ckd_epi_2021",
              "age_x_systolic_bp", "bmi_x_hba1c")


def engineer_record(record: dict) -> dict:
    """Compute ratios only when their source measurements exist and are valid.

    Missing source measurements remain NaN; they are never replaced with
    plausible-looking values before train-fitted imputation.
    """
    result = dict(record)
    def number(key):
        try:
            value = float(record.get(key))
            return value if np.isfinite(value) else np.nan
        except (TypeError, ValueError):
            return np.nan
    sbp, dbp = number("systolic_bp"), number("diastolic_bp")
    total, hdl, tg = number("total_cholesterol"), number("hdl"), number("triglycerides")
    glucose = number("fasting_blood_sugar")
    age, bmi, a1c, creatinine = (number(key) for key in ("age", "bmi", "hba1c", "creatinine"))
    result["pulse_pressure"] = sbp - dbp
    result["mean_arterial_pressure"] = dbp + (sbp - dbp) / 3
    result["non_hdl_cholesterol"] = total - hdl
    result["tg_to_hdl_ratio"] = tg / max(hdl, 1.0) if np.isfinite(hdl) else np.nan
    result["chol_to_hdl_ratio"] = total / max(hdl, 1.0) if np.isfinite(hdl) else np.nan
    result["tyg_index"] = np.log(tg * glucose / 2) if np.isfinite(tg * glucose) and tg > 0 and glucose > 0 else np.nan
    sex = str(record.get("sex", "")).lower()
    try:
        result["egfr_ckd_epi_2021"] = egfr_2021(creatinine, age, sex) if np.isfinite(creatinine) and np.isfinite(age) else np.nan
    except ValueError:
        result["egfr_ckd_epi_2021"] = np.nan
    result["age_x_systolic_bp"] = age * sbp
    result["bmi_x_hba1c"] = bmi * a1c
    return result


class ClinicalTransformV2:
    """Versioned transform so legacy 57-column serving checkpoints stay valid."""
    numeric_fields = NUMERIC + ENGINEERED

    def __init__(self):
        self.imputer = SimpleImputer(strategy="median", keep_empty_features=True)
        self.scaler = StandardScaler()

    def _numeric(self, records):
        return np.asarray([[float(engineer_record(record).get(key, np.nan))
                            for key in self.numeric_fields] for record in records], dtype=np.float32)

    def fit(self, records):
        self.scaler.fit(self.imputer.fit_transform(self._numeric(records)))
        return self

    def transform(self, records):
        raw = self._numeric(records)
        numeric = self.scaler.transform(self.imputer.transform(raw)).astype(np.float32)
        missing = np.isnan(raw).astype(np.float32)
        cats = np.array([[float(str(record.get(key, "")).lower() == value)
                          for key in CATEGORICAL for value in CATEGORIES[key]] for record in records], dtype=np.float32)
        return np.concatenate([numeric, missing, cats], axis=1)

    @property
    def output_dim(self):
        return 2 * len(self.numeric_fields) + sum(map(len, CATEGORIES.values()))


class ClinicalTransform:
    def __init__(self):
        self.imputer = SimpleImputer(strategy="median", keep_empty_features=True)
        self.scaler = StandardScaler()

    def _numeric(self, records):
        return np.array([[float(record[key]) if record.get(key) is not None else np.nan for key in NUMERIC] for record in records], dtype=np.float32)

    def fit(self, records):
        raw = self._numeric(records)
        self.scaler.fit(self.imputer.fit_transform(raw))
        return self

    def transform(self, records):
        raw = self._numeric(records)
        missing = np.isnan(raw).astype(np.float32)
        numeric = self.scaler.transform(self.imputer.transform(raw)).astype(np.float32)
        cats = np.array([[float(str(record.get(key, "")).lower() == value) for key in CATEGORICAL for value in CATEGORIES[key]] for record in records], dtype=np.float32)
        return np.concatenate([numeric, missing, cats], axis=1)

    @property
    def output_dim(self):
        return 2 * len(NUMERIC) + sum(map(len, CATEGORIES.values()))
