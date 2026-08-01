@echo off
set PYTHONUTF8=1
title Danfer Industrial OS Web
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  echo Preparando o ambiente pela primeira vez...
  py -3 -m venv .venv
  .venv\Scripts\python.exe -m pip install -e .
)
start "" http://127.0.0.1:8000
set DANFER_SEED_DEMO=1
.venv\Scripts\python.exe -m uvicorn danfer_os.main:app --host 127.0.0.1 --port 8000
pause
