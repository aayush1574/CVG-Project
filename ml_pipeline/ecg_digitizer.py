"""Experimental 3x4 ECG scan digitization with measured paper-grid scale."""
from __future__ import annotations

from pathlib import Path
import cv2
import numpy as np

PANEL_NAMES = (("I", "aVR", "V1", "V4"),
               ("II", "aVL", "V2", "V5"),
               ("III", "aVF", "V3", "V6"))
LEADS = ("I", "II", "III", "aVR", "aVL", "aVF", "V1", "V2", "V3", "V4", "V5", "V6")


def _period(projection: np.ndarray, low: int = 3, high: int = 40) -> tuple[float | None, float]:
    centered = projection.astype(np.float64) - np.mean(projection)
    if np.std(centered) < 1e-3:
        return None, 0.0
    fft = np.fft.rfft(centered, n=2 * len(centered))
    corr = np.fft.irfft(fft * np.conj(fft))[:len(centered)]
    corr /= max(corr[0], 1e-9)
    candidates = [i for i in range(low, min(high, len(corr) - 1))
                  if corr[i] > corr[i - 1] and corr[i] >= corr[i + 1] and corr[i] > .12]
    if not candidates:
        return None, 0.0
    best = min(candidates, key=lambda i: i / max(corr[i], .01))
    return float(best), float(corr[best])


def estimate_grid(image: np.ndarray) -> dict:
    height, width = image.shape[:2]
    b, g, r = cv2.split(image.astype(np.int16))
    red = ((r - g > 12) & (r - b > 12) & (r > 100)).astype(np.uint8)
    red_fraction = float(red.mean())
    if red_fraction > .002:
        mask = red
        color = "red/pink"
    else:
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        dark = (gray < 180).astype(np.uint8) * 255
        horizontal = cv2.morphologyEx(dark, cv2.MORPH_OPEN,
                                      cv2.getStructuringElement(cv2.MORPH_RECT, (max(20, width // 10), 1)))
        vertical = cv2.morphologyEx(dark, cv2.MORPH_OPEN,
                                    cv2.getStructuringElement(cv2.MORPH_RECT, (1, max(20, height // 10))))
        mask = ((horizontal > 0) | (vertical > 0)).astype(np.uint8)
        color = "dark"
    x_period, x_strength = _period(mask.mean(axis=0))
    y_period, y_strength = _period(mask.mean(axis=1))
    periods = [p for p, s in ((x_period, x_strength), (y_period, y_strength)) if p and s >= .12]
    px_per_mm = float(np.median(periods)) if periods else None
    return {"px_per_mm": px_per_mm, "grid_color": color,
            "grid_strength": round(float(max(x_strength, y_strength)), 3),
            "grid_detected": bool(periods)}


def _remove_grid(image: np.ndarray, grid_color: str) -> np.ndarray:
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    if grid_color == "red/pink":
        b, g, r = cv2.split(image.astype(np.int16))
        red = ((r - g > 12) & (r - b > 12) & (r > 100)).astype(np.uint8) * 255
        return cv2.inpaint(gray, red, 2, cv2.INPAINT_TELEA)
    height, width = gray.shape
    dark = (gray < 160).astype(np.uint8) * 255
    horizontal = cv2.morphologyEx(dark, cv2.MORPH_OPEN,
                                  cv2.getStructuringElement(cv2.MORPH_RECT, (max(20, width // 10), 1)))
    vertical = cv2.morphologyEx(dark, cv2.MORPH_OPEN,
                                cv2.getStructuringElement(cv2.MORPH_RECT, (1, max(20, height // 10))))
    return cv2.inpaint(gray, cv2.bitwise_or(horizontal, vertical), 1, cv2.INPAINT_TELEA)


def _pulse_height(gray: np.ndarray, px_per_mm: float) -> float | None:
    """Find a 10-mm step in the left or right margin of any ECG row."""
    height, width = gray.shape
    expected = 10 * px_per_mm
    heights = []
    for row in range(3):
        y0, y1 = int(row * height / 3), int((row + 1) * height / 3)
        for x0, x1 in ((0, int(width * .03)), (int(width * .97), width)):
            crop = gray[y0:y1, x0:x1]
            if crop.size == 0:
                continue
            dark = (crop < 110).astype(np.uint8) * 255
            span = max(3, int(2 * px_per_mm))
            horizontal = cv2.morphologyEx(dark, cv2.MORPH_OPEN,
                                          cv2.getStructuringElement(cv2.MORPH_RECT, (span, 1)))
            rows = np.flatnonzero(horizontal.sum(axis=1) >= 255 * span)
            for upper in rows:
                delta = np.abs(rows - upper)
                candidates = rows[(delta >= .7 * expected) & (delta <= 1.3 * expected)]
                if len(candidates):
                    heights.append(float(abs(candidates[0] - upper)))
    return float(np.median(heights)) if heights else None


def digitize_image(path: str | Path) -> tuple[np.ndarray, dict]:
    """Return 500-Hz millivolt waveforms and scan-quality information.

    A 3x4 printout contains short simultaneous strips, not full 10-second
    recordings. Strips are repeated to fill the encoder's 10-second window;
    this is explicitly reported as a research-only approximation.
    """
    image = cv2.imread(str(path), cv2.IMREAD_COLOR)
    if image is None:
        raise ValueError("Cannot decode ECG image")
    height, width = image.shape[:2]
    if height < 600 or width < 800:
        raise ValueError("Image needs at least 800x600 pixels")
    grid = estimate_grid(image)
    if not grid["grid_detected"] or grid["px_per_mm"] is None:
        raise ValueError("Cannot measure ECG paper grid; millivolt and time scales are uncertain")
    px_per_mm = grid["px_per_mm"]
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    pulse = _pulse_height(gray, px_per_mm)
    px_per_mv = pulse if pulse else 10 * px_per_mm
    cleaned = _remove_grid(image, grid["grid_color"])
    traces = {}
    coverage = []
    durations = []
    for row, names in enumerate(PANEL_NAMES):
        for col, name in enumerate(names):
            panel = cleaned[int((row + .12) * height / 3):int((row + .88) * height / 3),
                            int((col + .12) * width / 4):int((col + .94) * width / 4)]
            if panel.size == 0:
                raise ValueError("ECG panel layout is incomplete")
            _, otsu = cv2.threshold(panel, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
            ink = (otsu > 0) & (panel < 160)
            middle = panel.shape[0] // 2
            path_y = np.full(panel.shape[1], np.nan, np.float32)
            previous = middle
            for x in range(panel.shape[1]):
                candidates = np.flatnonzero(ink[:, x])
                if len(candidates):
                    chosen = int(candidates[np.argmin(np.abs(candidates - previous))])
                    path_y[x] = chosen
                    previous = chosen
            valid = np.isfinite(path_y)
            coverage.append(float(valid.mean()))
            if valid.mean() < .5:
                raise ValueError(f"Too little trace ink in lead {name}")
            path_y = np.interp(np.arange(len(path_y)), np.flatnonzero(valid), path_y[valid])
            baseline = float(np.median(path_y))
            mv = (baseline - path_y) / px_per_mv
            duration = panel.shape[1] / (25 * px_per_mm)
            durations.append(duration)
            segment_samples = int(np.clip(round(duration * 500), 250, 5000))
            segment = np.interp(np.linspace(0, len(mv) - 1, segment_samples), np.arange(len(mv)), mv)
            traces[name] = np.tile(segment, int(np.ceil(5000 / len(segment))))[:5000].astype(np.float32)
    output = np.stack([traces[name] for name in LEADS])
    return output, {**grid, "method": "grid-calibrated 3x4 trace tracking",
                    "calibration_pulse_detected": pulse is not None,
                    "px_per_mv": round(float(px_per_mv), 3),
                    "mean_coverage": round(float(np.mean(coverage)), 3),
                    "mean_panel_duration_seconds": round(float(np.mean(durations)), 3),
                    "waveform_units": "mV at 500 Hz before encoder normalization",
                    "warning": "Experimental scanned-ECG extraction. Short strips were repeated to 10 seconds; grid scale and trace recovery require clinician review and are not equivalent to a digital ECG."}
