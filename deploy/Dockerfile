FROM python:3.11-slim
WORKDIR /service
RUN apt-get update && apt-get install -y --no-install-recommends tesseract-ocr && rm -rf /var/lib/apt/lists/*
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY ml_pipeline ./ml_pipeline
COPY app/backend ./app/backend
COPY models ./models
ENV CVG_PROJECT_ROOT=/service CVG_MODELS_DIR=/service/models CVG_ENABLE_RISK_OUTPUT=1
EXPOSE 7860
CMD ["uvicorn","app.backend.main:app","--host","0.0.0.0","--port","7860"]
