@echo off
echo Starting AI Clone Backend...
cd /d %~dp0backend
if not exist "venv\" (
    echo Creating virtual environment...
    python -m venv venv
    call venv\Scripts\activate.bat
    echo Installing dependencies...
    pip install -r ..\requirements.txt
) else (
    call venv\Scripts\activate.bat
)
if not exist "..\.env" (
    echo Copying .env.example to .env...
    copy ..\.env.example ..\.env
    echo Please edit .env with your API keys before using real LLM!
)
echo Starting uvicorn server on http://127.0.0.1:8000
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
pause
