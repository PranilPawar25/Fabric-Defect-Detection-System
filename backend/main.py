"""
FastAPI Main Application

Entry point for the Fabric Defect Detection System backend server.
Serves the web UI and provides API endpoints for defect detection.
"""

from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
from pathlib import Path
import sys

# Add current directory to path
sys.path.insert(0, str(Path(__file__).parent))

from config import API_HOST, API_PORT, PROJECT_ROOT
from db import get_log_store
from inference import get_detector

# Import routers
from api.routes_image import router as image_router
from api.routes_video import router as video_router
from api.routes_log import router as log_router
from api.routes_config import router as config_router
from api.routes_livestream import router as livestream_router
from api.routes_live import router as live_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Application lifespan manager.
    Handles startup and shutdown tasks.
    """
    # Startup
    print("=" * 70)
    print("Fabric Defect Detection System - Starting Up")
    print("=" * 70)
    
    # Initialize database
    print("Initializing database...")
    log_store = await get_log_store()
    print(f"Database ready: {log_store.db_path}")
    
    # Initialize detector (loads model if available)
    print("Initializing detector...")
    detector = get_detector()
    print(f"Detector ready in {detector.mode} mode")
    
    # Auto-create live session for immediate phone access
    from inference.live_session import ensure_startup_session
    await ensure_startup_session()
    
    print()
    print("Server is ready!")
    print(f"Web UI: http://localhost:{API_PORT}")
    print(f"API Docs: http://localhost:{API_PORT}/docs")
    print("=" * 70)
    print()
    
    yield
    
    # Shutdown
    print("\nShutting down...")


# Create FastAPI application
app = FastAPI(
    title="Fabric Defect Detection API",
    description="AI-based fabric quality inspection system with autoencoder anomaly detection",
    version="1.0.0",
    lifespan=lifespan
)

# CORS middleware (allows frontend to call API)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include API routers
app.include_router(image_router)
app.include_router(video_router)
app.include_router(log_router)
app.include_router(config_router)
app.include_router(livestream_router)
app.include_router(live_router)


# Health check endpoint
@app.get("/health")
async def health_check():
    """
    Health check endpoint to verify the server is running.
    """
    detector = get_detector()
    
    return JSONResponse({
        "status": "healthy",
        "mode": detector.mode,
        "version": "1.0.0"
    })


# Root endpoint - serve the web UI
@app.get("/")
async def root():
    """
    Serve the main web UI page.
    """
    frontend_dir = PROJECT_ROOT / "frontend"
    index_path = frontend_dir / "index.html"
    
    if index_path.exists():
        return FileResponse(index_path)
    else:
        return JSONResponse({
            "message": "Fabric Defect Detection API",
            "version": "1.0.0",
            "docs": "/docs",
            "health": "/health"
        })


# Mobile camera page endpoint
@app.get("/mobile-camera/{session_id}")
async def mobile_camera(session_id: str):
    """
    Serve the mobile camera page for a specific session.
    """
    frontend_dir = PROJECT_ROOT / "frontend"
    mobile_page = frontend_dir / "mobile-camera.html"
    
    if mobile_page.exists():
        return FileResponse(mobile_page)
    else:
        return JSONResponse({
            "error": "Mobile camera page not found"
        }, status_code=404)


# Mount static files directory (for CSS, JS, etc.)
frontend_dir = PROJECT_ROOT / "frontend"
if frontend_dir.exists():
    app.mount("/static", StaticFiles(directory=str(frontend_dir)), name="static")


# Error handlers
@app.exception_handler(404)
async def not_found_handler(request: Request, exc):
    """Handle 404 errors."""
    return JSONResponse(
        status_code=404,
        content={"error": "Not found", "path": str(request.url)}
    )


@app.exception_handler(500)
async def internal_error_handler(request: Request, exc):
    """Handle 500 errors."""
    return JSONResponse(
        status_code=500,
        content={"error": "Internal server error", "detail": str(exc)}
    )


if __name__ == "__main__":
    import uvicorn
    
    # Run the server
    uvicorn.run(
        "main:app",
        host=API_HOST,
        port=API_PORT,
        reload=True,
        log_level="info"
    )
