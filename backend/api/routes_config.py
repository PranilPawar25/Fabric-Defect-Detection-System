"""
Configuration API Routes

Handles runtime configuration updates for detection parameters.
"""

from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from typing import Optional

from config import runtime_config
from inference import get_detector

router = APIRouter(prefix="/config", tags=["config"])


class ConfigUpdate(BaseModel):
    """
    Model for configuration update request.
    
    Validation ensures:
    - k_sigma: Reasonable threshold multiplier
    - feed_speed: Positive, non-zero, and within realistic manufacturing limits
    - min_confidence: Valid percentage
    """
    k_sigma: Optional[float] = Field(
        None, 
        description="Anomaly threshold multiplier", 
        ge=0.5, 
        le=10.0,
        example=2.5
    )
    feed_speed: Optional[float] = Field(
        None, 
        description="Feed speed in meters per minute (constant assumption)", 
        gt=0.0,
        le=1000.0,  # Reasonable upper limit for fabric manufacturing
        example=10.0
    )
    min_confidence: Optional[float] = Field(
        None, 
        description="Minimum confidence percentage to report", 
        ge=0.0, 
        le=100.0,
        example=30.0
    )


@router.get("/")
async def get_config():
    """
    Get current runtime configuration.
    
    Returns:
    JSON with:
    - k_sigma: Current threshold multiplier
    - feed_speed: Current feed speed (m/min)
    - min_confidence: Minimum confidence threshold
    - detection_mode: Current detection mode (autoencoder or heuristic_fallback)
    """
    
    detector = get_detector()
    
    return JSONResponse({
        "success": True,
        "config": {
            **runtime_config.to_dict(),
            "detection_mode": detector.mode
        }
    })


@router.post("/")
async def update_config(update: ConfigUpdate):
    """
    Update runtime configuration parameters.
    
    Parameters (all optional):
    - k_sigma: Anomaly threshold multiplier (0.5-5.0)
    - feed_speed: Feed speed in meters per minute (> 0)
    - min_confidence: Minimum confidence to report defects (0-100)
    
    Returns:
    JSON with updated configuration
    """
    
    try:
        # Update runtime config
        runtime_config.update(
            k_sigma=update.k_sigma,
            feed_speed=update.feed_speed,
            min_confidence=update.min_confidence
        )
        
        return JSONResponse({
            "success": True,
            "message": "Configuration updated",
            "config": runtime_config.to_dict()
        })
    
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Error updating configuration: {str(e)}")


@router.post("/reset")
async def reset_config():
    """
    Reset configuration to default values.
    
    Returns:
    JSON with reset configuration
    """
    
    from config import K_SIGMA, DEFAULT_FEED_SPEED, MIN_CONFIDENCE
    
    runtime_config.update(
        k_sigma=K_SIGMA,
        feed_speed=DEFAULT_FEED_SPEED,
        min_confidence=MIN_CONFIDENCE
    )
    
    return JSONResponse({
        "success": True,
        "message": "Configuration reset to defaults",
        "config": runtime_config.to_dict()
    })
