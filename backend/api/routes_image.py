"""
Image Analysis API Routes

Handles single image upload and defect detection.
"""

from fastapi import APIRouter, UploadFile, File, HTTPException
from fastapi.responses import JSONResponse, StreamingResponse
import cv2
import numpy as np
from io import BytesIO
from typing import Optional
import uuid

from inference import get_detector, classify_detections, draw_detections
from db import get_log_store
from config import runtime_config

router = APIRouter(prefix="/analyze", tags=["analysis"])


@router.post("/image")
async def analyze_image(
    file: UploadFile = File(...),
    save_to_log: bool = True,
    return_annotated: bool = False
):
    """
    Analyze a single fabric image for defects.
    
    Parameters:
    - file: Image file upload
    - save_to_log: Whether to save detections to the database (default: True)
    - return_annotated: Whether to return annotated image (default: False)
    
    Returns:
    JSON with:
    - detections: List of detected defects with type, position, confidence
    - mode: Detection mode used (autoencoder or heuristic_fallback)
    - config: Current configuration (k_sigma, min_confidence)
    - session_id: Session identifier for this analysis
    
    If return_annotated=true, returns the annotated image instead.
    """
    
    # Validate file type
    if not file.content_type.startswith('image/'):
        raise HTTPException(status_code=400, detail="File must be an image")
    
    try:
        # Read image
        contents = await file.read()
        nparr = np.frombuffer(contents, np.uint8)
        image = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
        
        if image is None:
            raise HTTPException(status_code=400, detail="Could not decode image")
        
        # Run detection
        detector = get_detector()
        detections = detector.detect(image)
        
        # Classify defects
        classified_detections = classify_detections(detections)
        
        # Generate session ID
        session_id = str(uuid.uuid4())
        
        # Save to log if requested
        if save_to_log and len(classified_detections) > 0:
            log_store = await get_log_store()
            
            # Add session info and image source tracking to each detection
            for det in classified_detections:
                det['session_id'] = session_id
                det['feed_speed'] = runtime_config.feed_speed
                det['frame_number'] = 1  # Static image = frame 1
                det['timestamp_seconds'] = None  # No video timestamp for images
                det['timestamp_display'] = None
                det['source_type'] = 'image'
            
            await log_store.log_defects_batch(classified_detections, session_id=session_id)
        
        # Return annotated image if requested
        if return_annotated:
            annotated = draw_detections(image, classified_detections)
            
            # Encode to JPEG
            _, buffer = cv2.imencode('.jpg', annotated)
            io_buf = BytesIO(buffer)
            
            return StreamingResponse(io_buf, media_type="image/jpeg")
        
        # Return JSON response
        return JSONResponse({
            "success": True,
            "session_id": session_id,
            "detections": classified_detections,
            "count": len(classified_detections),
            "mode": detector.mode,
            "config": runtime_config.to_dict(),
            "image_shape": {
                "height": image.shape[0],
                "width": image.shape[1]
            }
        })
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error processing image: {str(e)}")
