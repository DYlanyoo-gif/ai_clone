@echo off
echo Starting AI Clone Frontend...
cd /d %~dp0frontend
if not exist "node_modules\" (
    echo Installing frontend dependencies...
    call npm install
)
echo Starting Vite dev server on http://localhost:5173
call npm run dev
pause
