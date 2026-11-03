@echo off
setlocal
py -m uv --version >nul 2>&1
if errorlevel 1 py -m pip install --user uv
if errorlevel 1 exit /b 1
py -m uv venv .venv --python 3.11
if errorlevel 1 exit /b 1
py -m uv pip install --python .venv\Scripts\python.exe -r requirements.txt
if errorlevel 1 exit /b 1
echo Image report OCR uses RapidOCR when Tesseract is unavailable.
echo Run: .venv\Scripts\python -m uvicorn app.backend.main:app --reload
