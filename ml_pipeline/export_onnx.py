"""Export the trained fusion head for CPU inference."""
import argparse
from pathlib import Path
import torch
from .fusion_model import FusionModel


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--models-dir", type=Path, default=Path(r"D:\CVG Project\models"))
    args = parser.parse_args()
    from onnxruntime.quantization import QuantType, quantize_dynamic
    checkpoint = torch.load(args.models_dir / "best_multimodal_cvd.pt", map_location="cpu", weights_only=False)
    model = FusionModel(checkpoint["ecg_dim"], checkpoint["tab_dim"], len(checkpoint["labels"]), checkpoint["risk_head"])
    model.load_state_dict(checkpoint["state_dict"])
    model.eval()
    torch.onnx.export(model, (torch.zeros(1, checkpoint["ecg_dim"]), torch.zeros(1, checkpoint["tab_dim"]), torch.ones(1, 1), torch.ones(1, 1)),
                      args.models_dir / "model.onnx", input_names=["ecg", "tab", "mask_ecg", "mask_tab"],
                      output_names=["disease_logits", "risk_logits"] if checkpoint["risk_head"] else ["disease_logits"], opset_version=18, dynamo=False)
    quantize_dynamic(args.models_dir / "model.onnx", args.models_dir / "model_quantized.onnx", weight_type=QuantType.QInt8)


if __name__ == "__main__":
    main()
