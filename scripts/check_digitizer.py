"""Synthetic 3x4 trace image smoke check for experimental digitization."""
from pathlib import Path
from tempfile import TemporaryDirectory
import cv2
import numpy as np
from ml_pipeline.ecg_branch import digitize_ecg_image

height, width = 1200, 1600
image = np.full((height, width, 3), 255, np.uint8)
for row in range(3):
    for col in range(4):
        x = np.arange(col * 400 + 40, (col + 1) * 400 - 20)
        y = (row * 400 + 200 + 25 * np.sin((x - col * 400) / 20)).astype(int)
        cv2.polylines(image, [np.column_stack([x, y]).astype(np.int32)], False, (0, 0, 0), 2)
with TemporaryDirectory() as folder:
    path = Path(folder) / "synthetic.png"
    cv2.imwrite(str(path), image)
    signal, quality = digitize_ecg_image(path)
    assert signal.shape == (12, 5000) and np.isfinite(signal).all()
    print(signal.shape, quality)
