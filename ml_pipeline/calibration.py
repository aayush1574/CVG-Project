"""Validation-fitted modality-specific probability and decision calibration."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import numpy as np


def load_calibration(path: Path, checkpoint: Path) -> dict:
    bundle = json.loads(path.read_text())
    digest = hashlib.sha256(checkpoint.read_bytes()).hexdigest()
    if bundle["checkpoint_sha256"] != digest:
        raise ValueError("Calibration does not match the active diagnostic checkpoint")
    return bundle


def apply_calibration(logits: np.ndarray, bundle: dict, modality: str) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Return calibrated probabilities, threshold-centered scores, and decisions."""
    params = bundle["modalities"][modality]
    slopes = np.asarray(params["platt_slope"], dtype=np.float64)
    intercepts = np.asarray(params["platt_intercept"], dtype=np.float64)
    thresholds = np.asarray(params["thresholds"], dtype=np.float64)
    z = np.clip(logits * slopes + intercepts, -50, 50)
    probabilities = 1 / (1 + np.exp(-z))
    threshold_logits = np.log(thresholds / (1 - thresholds))
    decision_scores = 1 / (1 + np.exp(-np.clip(z - threshold_logits, -50, 50)))
    decisions = probabilities >= thresholds
    return probabilities, decision_scores, decisions
