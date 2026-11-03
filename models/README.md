# Frozen model artifacts

manifest.json records existing staged model filenames, byte sizes, SHA-256 hashes and immutable Hugging Face download URLs. Download each artifact to this directory and verify its checksum before inference. Set CVG_MODELS_DIR to this directory and CVG_PROJECT_ROOT to the repository root. Install requirements and run python -m uvicorn app.backend.main:app --port 8000.

No model training or inference behavior was changed. The API uses PyTorch and joblib; ONNX is a reference export. clinical_stack.joblib was not promoted. Raw datasets and embedding caches are excluded. Research verification scripts with absolute dataset paths require the original research workspace.
