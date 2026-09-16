@echo off
setlocal
if not exist ".venv\Scripts\python.exe" (
  echo ADVI virtual environment not found.
  echo Run these commands first:
  echo   py -3.13 -m venv .venv
  echo   .\.venv\Scripts\python.exe -m pip install -e .
  pause
  exit /b 1
)
call ".venv\Scripts\activate.bat"
python -m advi.app
