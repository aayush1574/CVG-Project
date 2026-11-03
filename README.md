# CVG-Project

CardioScope research application. Research and educational use only.

- model-backend: Python API, model pipeline, deployment configuration and frozen model manifest.
- frontend: redesigned standalone frontend-preview and original functional app/frontend.
- main: reserved for the tested integration.

Both branches start from the original main commit. Model weights remain in existing artifact storage; the backend branch records immutable download URLs and SHA-256 checksums. Datasets, environments and generated build output are excluded. See docs/BACKEND_BASELINE.md and frontend-preview/README.md on their respective branches.
