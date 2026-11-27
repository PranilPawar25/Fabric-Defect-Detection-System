"""
Live Stream Routes - Real-time defect detection from mobile camera

This module provides endpoints for:
1. Generating session URLs for mobile camera access
2. Receiving frames from mobile devices via WebSocket
3. Processing frames in real-time and returning annotated results
"""

import asyncio
import base64
import io
import json
import uuid
from datetime import datetime
from typing import Dict, Set

import cv2
import numpy as np
from fastapi import APIRouter, WebSocket, WebSocketDisconnect, HTTPException
from fastapi.responses import JSONResponse, HTMLResponse
from PIL import Image

from inference.detector import get_detector
from inference.classifier import DefectClassifier, classify_detections
from db.log_store import get_log_store
from config import runtime_config

router = APIRouter(prefix="/api/livestream", tags=["livestream"])

# Store active sessions
active_sessions: Dict[str, dict] = {}

# Store connected websockets per session
websocket_connections: Dict[str, Set[WebSocket]] = {}


@router.post("/create-session")
async def create_session():
    """
    Create a new live stream session and return URL for mobile access.
    
    Returns:
        session_id: Unique session identifier
        mobile_url: URL to open on mobile device
        desktop_url: URL to view on desktop
        qr_code_data: Base64 encoded QR code image
    """
    # Generate unique session ID
    session_id = str(uuid.uuid4())
    
    # Create session metadata
    session = {
        "id": session_id,
        "created_at": datetime.now().isoformat(),
        "status": "active",
        "frame_count": 0,
        "defect_count": 0
    }
    
    active_sessions[session_id] = session
    websocket_connections[session_id] = set()
    
    # Generate URLs
    mobile_url = f"/mobile-camera/{session_id}"
    desktop_url = f"/desktop-viewer/{session_id}"
    
    # Generate QR code
    try:
        import qrcode
        qr = qrcode.QRCode(version=1, box_size=10, border=4)
        qr.add_data(mobile_url)
        qr.make(fit=True)
        
        img = qr.make_image(fill_color="black", back_color="white")
        
        # Convert to base64
        buffered = io.BytesIO()
        img.save(buffered, format="PNG")
        qr_code_data = base64.b64encode(buffered.getvalue()).decode()
    except ImportError:
        qr_code_data = None
    
    return JSONResponse({
        "session_id": session_id,
        "mobile_url": mobile_url,
        "desktop_url": desktop_url,
        "qr_code_data": qr_code_data,
        "status": "success"
    })


@router.get("/session/{session_id}/status")
async def get_session_status(session_id: str):
    """Get the status of a live stream session."""
    if session_id not in active_sessions:
        raise HTTPException(status_code=404, detail="Session not found")
    
    session = active_sessions[session_id]
    connected_clients = len(websocket_connections.get(session_id, set()))
    
    return JSONResponse({
        "session_id": session_id,
        "status": session["status"],
        "frame_count": session["frame_count"],
        "defect_count": session["defect_count"],
        "connected_clients": connected_clients,
        "created_at": session["created_at"]
    })


@router.delete("/session/{session_id}")
async def end_session(session_id: str):
    """End a live stream session and clean up resources."""
    if session_id not in active_sessions:
        raise HTTPException(status_code=404, detail="Session not found")
    
    # Close all websocket connections
    if session_id in websocket_connections:
        for ws in list(websocket_connections[session_id]):
            try:
                await ws.close()
            except:
                pass
        del websocket_connections[session_id]
    
    # Remove session
    del active_sessions[session_id]
    
    return JSONResponse({
        "session_id": session_id,
        "status": "ended",
        "message": "Session ended successfully"
    })


@router.websocket("/ws/{session_id}")
async def websocket_endpoint(websocket: WebSocket, session_id: str):
    """
    WebSocket endpoint for real-time frame processing.
    
    Mobile sends: { "type": "frame", "data": "base64_image_data" }
    Server responds: { "type": "result", "detections": [...], "annotated_frame": "base64" }
    """
    # Verify session exists
    if session_id not in active_sessions:
        await websocket.close(code=1008, reason="Session not found")
        return
    
    # Accept connection
    await websocket.accept()
    
    # Add to connections
    if session_id not in websocket_connections:
        websocket_connections[session_id] = set()
    websocket_connections[session_id].add(websocket)
    
    # Get detector
    detector = get_detector()
    log_store = await get_log_store()
    
    try:
        # Send welcome message
        await websocket.send_json({
            "type": "connected",
            "session_id": session_id,
            "message": "Connected to defect detection system"
        })
        
        while True:
            # Receive message from client
            data = await websocket.receive_json()
            
            if data.get("type") == "ping":
                await websocket.send_json({"type": "pong"})
                continue
            
            if data.get("type") != "frame":
                continue
            
            # Decode frame
            try:
                frame_data = data.get("data", "")
                
                # Remove data URL prefix if present
                if "," in frame_data:
                    frame_data = frame_data.split(",")[1]
                
                # Decode base64 to image
                img_bytes = base64.b64decode(frame_data)
                img = Image.open(io.BytesIO(img_bytes))
                frame = cv2.cvtColor(np.array(img), cv2.COLOR_RGB2BGR)
                
            except Exception as e:
                await websocket.send_json({
                    "type": "error",
                    "message": f"Failed to decode frame: {str(e)}"
                })
                continue
            
            # Process frame
            try:
                # Run detection
                detections = detector.detect(frame)
                
                # Create classifier instance
                classifier = DefectClassifier()
                
                # Classify each defect
                classified_detections = []
                for det in detections:
                    # Classify using the proper method
                    defect_type, reasoning, diagnostics = classifier.classify_with_diagnostics(det)
                    
                    # Extract confidence from reasoning if available
                    confidence = diagnostics.get('best_score', 50.0)
                    
                    classified_det = {
                        "x": det["x"],
                        "y": det["y"],
                        "w": det["w"],
                        "h": det["h"],
                        "type": defect_type,
                        "confidence": float(confidence),
                        "detection_confidence": det["confidence"]
                    }
                    classified_detections.append(classified_det)
                    
                    # Save to database
                    await log_store.add_defect(
                        defect_type=defect_type,
                        confidence=confidence,
                        x=det["x"],
                        y=det["y"],
                        width=det["w"],
                        height=det["h"],
                        timestamp_m=0.0,  # Live stream doesn't have timeline
                        frame_number=active_sessions[session_id]["frame_count"],
                        source=f"livestream_{session_id}",
                        metadata={
                            "session_id": session_id,
                            **diagnostics
                        }
                    )
                
                # Draw bounding boxes on frame
                annotated_frame = frame.copy()
                
                # Define colors for each defect type (BGR format)
                colors = {
                    "hole": (255, 0, 0),          # Blue
                    "stain": (255, 165, 0),       # Orange
                    "knot": (0, 255, 0),          # Green
                    "double_knot": (0, 255, 255), # Yellow
                    "broken_thread": (255, 0, 255) # Magenta
                }
                
                for det in classified_detections:
                    color = colors.get(det["type"], (0, 0, 255))
                    
                    # Draw rectangle
                    cv2.rectangle(
                        annotated_frame,
                        (det["x"], det["y"]),
                        (det["x"] + det["w"], det["y"] + det["h"]),
                        color,
                        2
                    )
                    
                    # Draw label
                    label = f"{det['type'].replace('_', ' ').title()} {det['confidence']:.0f}%"
                    label_size, _ = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.5, 2)
                    
                    cv2.rectangle(
                        annotated_frame,
                        (det["x"], det["y"] - label_size[1] - 10),
                        (det["x"] + label_size[0], det["y"]),
                        color,
                        -1
                    )
                    
                    cv2.putText(
                        annotated_frame,
                        label,
                        (det["x"], det["y"] - 5),
                        cv2.FONT_HERSHEY_SIMPLEX,
                        0.5,
                        (255, 255, 255),
                        2
                    )
                
                # Encode annotated frame to base64
                _, buffer = cv2.imencode('.jpg', annotated_frame, [cv2.IMWRITE_JPEG_QUALITY, 85])
                annotated_base64 = base64.b64encode(buffer).decode()
                
                # Update session stats
                active_sessions[session_id]["frame_count"] += 1
                active_sessions[session_id]["defect_count"] += len(classified_detections)
                
                # Send result back to client
                await websocket.send_json({
                    "type": "result",
                    "detections": classified_detections,
                    "annotated_frame": f"data:image/jpeg;base64,{annotated_base64}",
                    "frame_count": active_sessions[session_id]["frame_count"],
                    "defect_count": active_sessions[session_id]["defect_count"]
                })
                
            except Exception as e:
                await websocket.send_json({
                    "type": "error",
                    "message": f"Processing error: {str(e)}"
                })
    
    except WebSocketDisconnect:
        pass
    except Exception as e:
        print(f"WebSocket error: {e}")
    finally:
        # Remove from connections
        if session_id in websocket_connections:
            websocket_connections[session_id].discard(websocket)
