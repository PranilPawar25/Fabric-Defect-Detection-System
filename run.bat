@echo off
REM Launch script for AI-Based Fabric Defect Detection System (Windows)

echo ==========================================
echo Fabric Defect Detection System
echo ==========================================
echo.

REM Check if virtual environment exists
if not exist "venv\" (
    echo Virtual environment not found. Creating one...
    python -m venv venv
    echo Virtual environment created.
    echo.
)

REM Activate virtual environment
echo Activating virtual environment...
call venv\Scripts\activate.bat

REM Check if dependencies are installed
python -c "import fastapi" 2>nul
if errorlevel 1 (
    echo Dependencies not installed. Installing from requirements.txt...
    python -m pip install --upgrade pip
    pip install -r requirements.txt
    echo Dependencies installed.
    echo.
)

REM Launch the FastAPI server
echo Starting FastAPI server...
echo Server will be available at: http://localhost:8000
echo Press Ctrl+C to stop the server
echo.

cd backend
python -m uvicorn main:app --host 0.0.0.0 --port 8000 --reload
