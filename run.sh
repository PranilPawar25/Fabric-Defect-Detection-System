#!/bin/bash
# Launch script for AI-Based Fabric Defect Detection System (Unix/Linux/Mac)

echo "=========================================="
echo "Fabric Defect Detection System"
echo "=========================================="
echo ""

# Check if virtual environment exists
if [ ! -d "venv" ]; then
    echo "Virtual environment not found. Creating one..."
    python3 -m venv venv
    echo "Virtual environment created."
    echo ""
fi

# Activate virtual environment
echo "Activating virtual environment..."
source venv/bin/activate

# Check if dependencies are installed
if ! python -c "import fastapi" 2>/dev/null; then
    echo "Dependencies not installed. Installing from requirements.txt..."
    pip install --upgrade pip
    pip install -r requirements.txt
    echo "Dependencies installed."
    echo ""
fi

# Launch the FastAPI server
echo "Starting FastAPI server..."
echo "Server will be available at: http://localhost:8000"
echo "Press Ctrl+C to stop the server"
echo ""

cd backend
python -m uvicorn main:app --host 0.0.0.0 --port 8000 --reload
