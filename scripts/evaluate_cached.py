"""Evaluate the locked cached-feature checkpoint on the prepared test split."""
import ast
import json
from pathlib import Path
import joblib
import numpy as np
import pandas as pd
import torch
from sklearn.metrics import f1_score, roc_auc_score
from ml_pipeline.fusion_model import FusionModel

root = Path(r"D:\CVG Project")
artifact = root / "artifacts"
checkpoint = torch.load(root / "models/best_multimodal_cvd.pt", map_location="cpu", weights_only=False)
transform = joblib.load(root / "models/clinical_transform.joblib")
frame = pd.read_csv(artifact / "clinical-ext-icd-prepared-24k/manifest.csv")
features = np.load(artifact / "ecgfounder_ext_icd_features_24k/ecgfounder_features.npy", allow_pickle=False, mmap_mode="r")
metadata = json.loads((artifact / "ecgfounder_ext_icd_prepared_24k/metadata.json").read_text())
indices = [metadata["labels"].index(label) for label in checkpoint["labels"]]
test = np.flatnonzero(frame.split.to_numpy() == "test")
records = [{"age": row.age, "sex": "female" if row.gender == "F" else "male",
            "creatinine": row.creatinine_last, "fasting_blood_sugar": row.glucose_last}
           for row in frame.iloc[test].itertuples()]
tab = transform.transform(records)
y = np.array([[float(j in ast.literal_eval(value)) for j in indices]
              for value in frame.iloc[test].targets], dtype=np.float32)
model = FusionModel(checkpoint["ecg_dim"], checkpoint["tab_dim"], len(indices))
model.load_state_dict(checkpoint["state_dict"])
model.eval()


def score(with_ecg):
    outputs = []
    with torch.no_grad():
        for offset in range(0, len(test), 256):
            ix = test[offset:offset + 256]
            x = torch.from_numpy(np.asarray(features[ix]).copy()) if with_ecg else torch.zeros(len(ix), checkpoint["ecg_dim"])
            logits, _ = model(x, torch.from_numpy(tab[offset:offset + len(ix)]),
                              torch.full((len(ix), 1), float(with_ecg)), torch.ones(len(ix), 1))
            outputs.append(logits.sigmoid().numpy())
    p = np.concatenate(outputs)
    return {"macro_auroc": float(np.mean([roc_auc_score(y[:, j], p[:, j]) for j in range(len(indices)) if len(np.unique(y[:, j])) == 2])),
            "macro_f1_at_0_5": float(f1_score(y, p >= .5, average="macro", zero_division=0))}


result = {"labels": checkpoint["labels"], "test_rows": len(test),
          "ecg_and_clinical": score(True), "clinical_only": score(False),
          "limitations": "Internal held-out test only; not clinically validated or calibrated for individual use."}
(root / "models/research_metrics.json").write_text(json.dumps(result, indent=2))
print(json.dumps(result))
