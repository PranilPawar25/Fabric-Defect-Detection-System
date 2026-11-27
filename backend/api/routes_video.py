"""
Video Analysis API Routes

Handles video upload and real-time streaming analysis via WebSocket.
"""

from fastapi import APIRouter, UploadFile, File, WebSocket, WebSocketDisconnect, HTTPException, BackgroundTasks
from fastapi.responses import JSONResponse
import cv2
import numpy as np
import json
import tempfile
import uuid
from pathlib import Path
from typing import Optional, Dict, List
import asyncio
import base64
import traceback
import logging
from datetime import datetime

from inference import (
    get_detector, 
    classify_detections, 
    VideoLengthTracker
)
from db import get_log_store
from config import runtime_config, VIDEO_PROCESSING_FPS, WEBSOCKET_FRAME_SKIP

router = APIRouter(prefix="/analyze", tags=["analysis"])
logger = logging.getLogger(__name__)

# In-memory job storage (use Redis/database in production)
video_jobs: Dict[str, Dict] = {}


def format_timestamp(seconds: float) -> str:
    """
    Format seconds into MM:SS display format.
    
    Args:
        seconds: Time in seconds
        
    Returns:
        Formatted string like "01:23" or "12:05"
    """
    if seconds is None:
        return None
    minutes = int(seconds // 60)
    secs = int(seconds % 60)
    return f"{minutes:02d}:{secs:02d}"


def downscale_frame(frame: np.ndarray, max_width: int = 800) -> tuple:
    """
    Downscale frame for faster processing while maintaining aspect ratio.
    
    Args:
        frame: Input frame
        max_width: Maximum width for processing
        
    Returns:
        Tuple of (downscaled_frame, scale_factor)
    """
    height, width = frame.shape[:2]
    
    if width <= max_width:
        return frame, 1.0
    
    scale_factor = max_width / width
    new_width = max_width
    new_height = int(height * scale_factor)
    
    downscaled = cv2.resize(frame, (new_width, new_height), interpolation=cv2.INTER_AREA)
    return downscaled, scale_factor


def scale_detections(detections: List[Dict], scale_factor: float) -> List[Dict]:
    """
    Scale detection bounding boxes back to original resolution.
    
    Args:
        detections: List of detection dictionaries
        scale_factor: Scale factor used for downscaling
        
    Returns:
        Detections with scaled bounding boxes
    """
    if scale_factor == 1.0:
        return detections
    
    for det in detections:
        det['x'] = int(det['x'] / scale_factor)
        det['y'] = int(det['y'] / scale_factor)
        det['w'] = int(det['w'] / scale_factor)
        det['h'] = int(det['h'] / scale_factor)
    
    return detections


async def process_video_background(
    job_id: str,
    tmp_path: str,
    feed_speed: float,
    save_to_log: bool,
    sample_interval: float = 0.3
):
    """
    Background task to process video with progress tracking.
    
    Args:
        job_id: Job identifier
        tmp_path: Path to temporary video file
        feed_speed: Feed speed in m/min
        save_to_log: Whether to save to database
        sample_interval: Sample frames every N seconds (default 0.3s)
    """
    try:
        # Update job status
        video_jobs[job_id]['status'] = 'processing'
        video_jobs[job_id]['started_at'] = datetime.utcnow().isoformat()
        
        # Open video with validation
        cap = cv2.VideoCapture(tmp_path)
        if not cap.isOpened():
            raise ValueError(f"Could not open video file. The file may be corrupted or use an unsupported codec.")
        
        # Get video properties with validation
        fps = cap.get(cv2.CAP_PROP_FPS)
        if fps <= 0:
            raise ValueError(f"Invalid FPS: {fps}. Video metadata may be corrupted.")
        
        total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        if total_frames <= 0:
            raise ValueError(f"Invalid frame count: {total_frames}. Video may be corrupted.")
        
        width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        duration = total_frames / fps
        
        logger.info(f"Job {job_id}: Processing video - {width}x{height}, {fps} fps, {total_frames} frames, {duration:.2f}s")
        
        # Calculate frame sampling - process every N frames based on sample_interval
        frame_skip = max(1, int(fps * sample_interval))
        frames_to_process = list(range(0, total_frames, frame_skip))
        total_to_process = len(frames_to_process)
        
        logger.info(f"Job {job_id}: Sampling every {frame_skip} frames ({sample_interval}s), processing {total_to_process}/{total_frames} frames")
        
        # Initialize components
        detector = get_detector()
        tracker = VideoLengthTracker(fps=fps, feed_speed=feed_speed)
        session_id = str(uuid.uuid4())
        
        all_detections = []
        all_frame_data = []  # Store per-frame detection data for playback
        processed_count = 0
        
        # Update job info
        video_jobs[job_id].update({
            'total_frames': total_frames,
            'frames_to_process': total_to_process,
            'video_info': {
                'fps': fps,
                'width': width,
                'height': height,
                'duration': round(duration, 2)
            }
        })
        
        # Process frames
        for frame_idx in frames_to_process:
            # Set position and read frame
            cap.set(cv2.CAP_PROP_POS_FRAMES, frame_idx)
            ret, frame = cap.read()
            
            if not ret or frame is None:
                logger.warning(f"Job {job_id}: Failed to read frame {frame_idx}, skipping")
                continue
            
            # Validate frame dimensions
            if frame.shape[0] == 0 or frame.shape[1] == 0:
                logger.warning(f"Job {job_id}: Invalid frame dimensions at {frame_idx}, skipping")
                continue
            
            try:
                # ═══════════════════════════════════════════════════════════════
                # TIMESTAMP EXTRACTION - CRITICAL FOR LENGTH ACCURACY
                # ═══════════════════════════════════════════════════════════════
                # Get ACTUAL video timestamp from OpenCV (in milliseconds).
                # 
                # WHY THIS MATTERS:
                # - Frames are sampled at intervals (not every frame processed)
                # - frame_idx jumps: 0, 15, 30, 45... (based on VIDEO_PROCESSING_FPS)
                # - Using frame_idx/fps would give wrong elapsed time
                # - CAP_PROP_POS_MSEC gives the REAL timestamp from video file
                #
                # Example with 30 fps video, sampling every 15 frames:
                # - frame_idx=30, fps=30 → frame_idx/fps = 1.0s (WRONG)
                # - timestamp_ms=1000 → actual_time = 1.0s (CORRECT)
                # 
                # ⚠️ Length calculation still assumes CONSTANT feed speed.
                # See length_tracker.py module docstring for limitations.
                # ═══════════════════════════════════════════════════════════════
                timestamp_ms = cap.get(cv2.CAP_PROP_POS_MSEC)
                elapsed_seconds = timestamp_ms / 1000.0  # Convert to seconds
                
                # Downscale for faster processing
                downscaled_frame, scale_factor = downscale_frame(frame, max_width=800)
                
                # Get position info using ACTUAL elapsed time, not frame-based calculation
                position_info = tracker.get_position_info(
                    elapsed_seconds=elapsed_seconds,
                    frame_number=frame_idx,
                    fps=fps
                )
                
                # Detect defects on downscaled frame
                detections = detector.detect(downscaled_frame)
                
                # Check for edge cases in detection
                if detections is None:
                    detections = []
                
                classified = classify_detections(detections)
                
                # Scale bounding boxes back to original resolution
                classified = scale_detections(classified, scale_factor)
                
                # Add metadata to each detection
                for det in classified:
                    det['frame_number'] = frame_idx
                    det['elapsed_time_s'] = position_info['elapsed_time']
                    det['timestamp_seconds'] = position_info['elapsed_time']
                    det['timestamp_display'] = format_timestamp(position_info['elapsed_time'])
                    det['source_type'] = 'video'
                    det['fabric_length_m'] = position_info['length_m']
                    det['feed_speed'] = feed_speed
                    det['session_id'] = session_id
                
                all_detections.extend(classified)
                
                # Store frame data for playback visualization
                if classified:  # Only store frames with detections
                    all_frame_data.append({
                        'frame_number': frame_idx,
                        'timestamp_seconds': position_info['elapsed_time'],
                        'detections': classified
                    })
                
                processed_count += 1
                
                # Update progress
                progress_percent = int((processed_count / total_to_process) * 100)
                video_jobs[job_id].update({
                    'progress_percent': progress_percent,
                    'frames_processed': processed_count
                })
                
                # Log progress every 10%
                if progress_percent % 10 == 0 and processed_count > 0:
                    logger.info(f"Job {job_id}: Progress {progress_percent}% ({processed_count}/{total_to_process} frames)")
            
            except Exception as frame_error:
                logger.error(f"Job {job_id}: Error processing frame {frame_idx}: {str(frame_error)}")
                logger.error(traceback.format_exc())
                # Continue processing other frames
                continue
        
        cap.release()
        Path(tmp_path).unlink(missing_ok=True)
        
        # Save to log if requested
        if save_to_log and len(all_detections) > 0:
            log_store = await get_log_store()
            await log_store.log_defects_batch(all_detections, session_id=session_id)
        
        # Mark job as complete
        video_jobs[job_id].update({
            'status': 'complete',
            'progress_percent': 100,
            'completed_at': datetime.utcnow().isoformat(),
            'session_id': session_id,
            'detections': all_detections,
            'frame_data': all_frame_data,
            'count': len(all_detections),
            'mode': detector.mode
        })
        
        logger.info(f"Job {job_id}: Complete - {len(all_detections)} defects found")
    
    except Exception as e:
        error_msg = str(e)
        error_trace = traceback.format_exc()
        
        logger.error(f"Job {job_id}: FATAL ERROR - {error_msg}")
        logger.error(error_trace)
        
        video_jobs[job_id].update({
            'status': 'error',
            'error': error_msg,
            'error_trace': error_trace,
            'completed_at': datetime.utcnow().isoformat()
        })
        
        # Cleanup temp file
        if tmp_path and Path(tmp_path).exists():
            Path(tmp_path).unlink(missing_ok=True)


@router.post("/video")
async def analyze_video(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    feed_speed: Optional[float] = None,
    save_to_log: bool = True
):
    """
    Analyze a fabric video for defects (async background processing).
    
    This endpoint returns immediately with a job_id. Use GET /analyze/video/status/{job_id}
    to check progress and retrieve results.
    
    Parameters:
    - file: Video file upload
    - feed_speed: Feed speed in m/min (uses config default if not provided)
    - save_to_log: Whether to save detections to database
    
    Returns:
    JSON with:
    - job_id: Job identifier for tracking progress
    - message: Status message
    """
    tmp_path = None
    
    try:
        # Validate file type
        if not file.content_type or not file.content_type.startswith('video/'):
            raise HTTPException(
                status_code=400, 
                detail=f"File must be a video (received content-type: {file.content_type})"
            )
        
        logger.info(f"Received video upload: {file.filename}, content-type: {file.content_type}")
        
        # Save uploaded video to temporary file
        with tempfile.NamedTemporaryFile(delete=False, suffix='.mp4') as tmp:
            contents = await file.read()
            
            if len(contents) == 0:
                raise HTTPException(status_code=400, detail="Uploaded file is empty")
            
            tmp.write(contents)
            tmp_path = tmp.name
        
        logger.info(f"Saved video to temp file: {tmp_path} ({len(contents)} bytes)")
        
        # Quick validation - can we open the file?
        test_cap = cv2.VideoCapture(tmp_path)
        if not test_cap.isOpened():
            test_cap.release()
            Path(tmp_path).unlink(missing_ok=True)
            raise HTTPException(
                status_code=400, 
                detail="Could not open video file. The file may be corrupted or use an unsupported codec (try converting to H.264 MP4)"
            )
        test_cap.release()
        
        # Use provided feed speed or default
        if feed_speed is None:
            feed_speed = runtime_config.feed_speed
        
        # Create job
        job_id = str(uuid.uuid4())
        video_jobs[job_id] = {
            'job_id': job_id,
            'status': 'queued',
            'progress_percent': 0,
            'frames_processed': 0,
            'created_at': datetime.utcnow().isoformat(),
            'filename': file.filename
        }
        
        logger.info(f"Created job {job_id} for video {file.filename}")
        
        # Start background processing
        background_tasks.add_task(
            process_video_background,
            job_id=job_id,
            tmp_path=tmp_path,
            feed_speed=feed_speed,
            save_to_log=save_to_log,
            sample_interval=0.4  # Process every 0.4 seconds
        )
        
        return JSONResponse({
            "success": True,
            "job_id": job_id,
            "message": "Video processing started. Use GET /analyze/video/status/{job_id} to check progress."
        })
    
    except HTTPException:
        # Re-raise HTTP exceptions as-is
        if tmp_path and Path(tmp_path).exists():
            Path(tmp_path).unlink(missing_ok=True)
        raise
    
    except Exception as e:
        # Log full traceback for debugging
        error_trace = traceback.format_exc()
        logger.error(f"Error starting video analysis: {str(e)}")
        logger.error(error_trace)
        
        # Cleanup temp file
        if tmp_path and Path(tmp_path).exists():
            Path(tmp_path).unlink(missing_ok=True)
        
        # Return detailed error
        raise HTTPException(
            status_code=500, 
            detail=f"Error starting video processing: {str(e)}\n\nIf this persists, check server logs for full traceback."
        )


@router.get("/video/status/{job_id}")
async def get_video_status(job_id: str):
    """
    Get status and progress of a video analysis job.
    
    Parameters:
    - job_id: Job identifier returned from POST /analyze/video
    
    Returns:
    JSON with:
    - status: "queued" | "processing" | "complete" | "error"
    - progress_percent: 0-100
    - frames_processed: Number of frames analyzed so far
    - total_frames: Total frames in video (if known)
    - detections: List of detections (only when status="complete")
    - error: Error message (only when status="error")
    """
    if job_id not in video_jobs:
        raise HTTPException(status_code=404, detail=f"Job {job_id} not found")
    
    job = video_jobs[job_id]
    
    response = {
        'job_id': job_id,
        'status': job['status'],
        'progress_percent': job.get('progress_percent', 0),
        'frames_processed': job.get('frames_processed', 0)
    }
    
    # Add video info if available
    if 'video_info' in job:
        response['video_info'] = job['video_info']
    
    # Add total frames if available
    if 'frames_to_process' in job:
        response['frames_to_process'] = job['frames_to_process']
    
    if 'total_frames' in job:
        response['total_frames'] = job['total_frames']
    
    # Include results if complete
    if job['status'] == 'complete':
        response.update({
            'session_id': job['session_id'],
            'detections': job['detections'],
            'frame_data': job['frame_data'],
            'count': job['count'],
            'mode': job['mode']
        })
    
    # Include error if failed
    if job['status'] == 'error':
        response['error'] = job.get('error', 'Unknown error')
        # Optionally include trace for debugging (remove in production)
        if 'error_trace' in job:
            response['error_trace'] = job['error_trace']
    
    return JSONResponse(response)


@router.delete("/video/job/{job_id}")
async def delete_video_job(job_id: str):
    """
    Delete a completed or failed video job from memory.
    
    Parameters:
    - job_id: Job identifier
    
    Returns:
    JSON with success message
    """
    if job_id not in video_jobs:
        raise HTTPException(status_code=404, detail=f"Job {job_id} not found")
    
    del video_jobs[job_id]
    
    return JSONResponse({
        "success": True,
        "message": f"Job {job_id} deleted"
    })


@router.websocket("/video/stream")
async def stream_video_analysis(websocket: WebSocket):
    """
    WebSocket endpoint for real-time video frame analysis.
    
    Protocol:
    1. Client connects
    2. Client sends video file as binary data
    3. Server processes frames and streams back results
    4. Each result contains: frame_number, detections, position_info, preview_frame
    
    Message format (JSON):
    {
        "type": "result",
        "frame_number": int,
        "detections": [...],
        "position_info": {...},
        "frame_preview": "base64_encoded_jpg"
    }
    
    Or on completion:
    {
        "type": "complete",
        "total_detections": int,
        "session_id": str
    }
    """
    await websocket.accept()
    
    try:
        # Receive initial config message
        config_msg = await websocket.receive_text()
        config = json.loads(config_msg)
        
        feed_speed = config.get('feed_speed', runtime_config.feed_speed)
        save_to_log = config.get('save_to_log', True)
        send_previews = config.get('send_previews', True)
        
        # Receive video data
        video_data = await websocket.receive_bytes()
        
        # Save to temporary file
        with tempfile.NamedTemporaryFile(delete=False, suffix='.mp4') as tmp:
            tmp.write(video_data)
            tmp_path = tmp.name
        
        # Open video
        cap = cv2.VideoCapture(tmp_path)
        if not cap.isOpened():
            await websocket.send_json({
                "type": "error",
                "message": "Could not open video file"
            })
            Path(tmp_path).unlink()
            return
        
        # Get video properties
        fps = cap.get(cv2.CAP_PROP_FPS)
        total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        
        # Send video info
        await websocket.send_json({
            "type": "video_info",
            "fps": fps,
            "total_frames": total_frames,
            "duration": total_frames / fps if fps > 0 else 0
        })
        
        # Initialize components
        detector = get_detector()
        tracker = VideoLengthTracker(fps=fps, feed_speed=feed_speed)
        session_id = str(uuid.uuid4())
        
        all_detections = []
        frame_number = 0
        frames_sent = 0
        
        # Process frames
        while True:
            ret, frame = cap.read()
            if not ret:
                break
            
            # Process every Nth frame
            if frame_number % VIDEO_PROCESSING_FPS == 0:
                # Get actual video timestamp - see timestamp extraction notes
                # in background job processing above for detailed explanation
                timestamp_ms = cap.get(cv2.CAP_PROP_POS_MSEC)
                elapsed_seconds = timestamp_ms / 1000.0
                
                # Get position info using actual elapsed time
                position_info = tracker.get_position_info(
                    elapsed_seconds=elapsed_seconds,
                    frame_number=frame_number,
                    fps=fps
                )
                
                # Detect defects
                detections = detector.detect(frame)
                classified = classify_detections(detections)
                
                # Add position info
                for det in classified:
                    det['frame_number'] = frame_number
                    det['elapsed_time_s'] = position_info['elapsed_time']
                    det['timestamp_seconds'] = position_info['elapsed_time']
                    det['timestamp_display'] = format_timestamp(position_info['elapsed_time'])
                    det['source_type'] = 'video'
                    det['fabric_length_m'] = position_info['length_m']
                    det['feed_speed'] = feed_speed
                    det['session_id'] = session_id
                
                all_detections.extend(classified)
                
                # Send result every WEBSOCKET_FRAME_SKIP frames
                if frames_sent % WEBSOCKET_FRAME_SKIP == 0:
                    result = {
                        "type": "result",
                        "frame_number": frame_number,
                        "detections": classified,
                        "position_info": position_info
                    }
                    
                    # Include frame preview if requested
                    if send_previews:
                        # Draw detections on frame
                        from inference import draw_detections
                        annotated = draw_detections(frame, classified)
                        
                        # Resize for preview (smaller for faster transfer)
                        preview = cv2.resize(annotated, (640, 480))
                        _, buffer = cv2.imencode('.jpg', preview, [cv2.IMWRITE_JPEG_QUALITY, 70])
                        
                        # Base64 encode
                        preview_b64 = base64.b64encode(buffer).decode('utf-8')
                        result["frame_preview"] = preview_b64
                    
                    await websocket.send_json(result)
                
                frames_sent += 1
            
            frame_number += 1
            
            # Small delay to prevent overwhelming the client
            await asyncio.sleep(0.01)
        
        cap.release()
        Path(tmp_path).unlink()
        
        # Save to log if requested
        if save_to_log and len(all_detections) > 0:
            log_store = await get_log_store()
            await log_store.log_defects_batch(all_detections, session_id=session_id)
        
        # Send completion message
        await websocket.send_json({
            "type": "complete",
            "total_detections": len(all_detections),
            "session_id": session_id,
            "mode": detector.mode
        })
    
    except WebSocketDisconnect:
        print("Client disconnected")
    except Exception as e:
        try:
            await websocket.send_json({
                "type": "error",
                "message": str(e)
            })
        except:
            pass
        print(f"Error in WebSocket: {e}")
    finally:
        if 'tmp_path' in locals() and Path(tmp_path).exists():
            Path(tmp_path).unlink()


@router.post("/live")
async def analyze_live_stream(
    stream_url: str,
    feed_speed: Optional[float] = None,
    duration_seconds: int = 60
):
    """
    Analyze a live video stream (e.g., from IP Webcam app).
    
    Parameters:
    - stream_url: URL of the video stream (e.g., http://192.168.1.100:8080/video)
    - feed_speed: Feed speed in m/min
    - duration_seconds: How long to capture (default: 60 seconds)
    
    Returns:
    JSON with detections found during the capture period.
    
    Note: This captures for a fixed duration. For true live streaming,
    use the WebSocket endpoint with a client that feeds frames continuously.
    """
    
    if feed_speed is None:
        feed_speed = runtime_config.feed_speed
    
    try:
        # Open stream
        cap = cv2.VideoCapture(stream_url)
        if not cap.isOpened():
            raise HTTPException(status_code=400, detail=f"Could not open stream: {stream_url}")
        
        # Get stream properties
        fps = cap.get(cv2.CAP_PROP_FPS)
        if fps == 0:
            fps = 30.0  # Default FPS for streams
        
        # Initialize components
        detector = get_detector()
        tracker = VideoLengthTracker(fps=fps, feed_speed=feed_speed)
        session_id = str(uuid.uuid4())
        
        all_detections = []
        frame_number = 0
        max_frames = int(duration_seconds * fps)
        
        # Capture and process frames
        while frame_number < max_frames:
            ret, frame = cap.read()
            if not ret:
                break
            
            # Process every Nth frame
            if frame_number % VIDEO_PROCESSING_FPS == 0:
                # Get actual timestamp - see detailed timestamp extraction notes above
                timestamp_ms = cap.get(cv2.CAP_PROP_POS_MSEC)
                elapsed_seconds = timestamp_ms / 1000.0
                
                # Get position info using actual elapsed time
                position_info = tracker.get_position_info(
                    elapsed_seconds=elapsed_seconds,
                    frame_number=frame_number,
                    fps=fps
                )
                
                # Detect defects
                detections = detector.detect(frame)
                classified = classify_detections(detections)
                
                # Add position info
                for det in classified:
                    det['frame_number'] = frame_number
                    det['elapsed_time_s'] = position_info['elapsed_time']
                    det['timestamp_seconds'] = position_info['elapsed_time']
                    det['timestamp_display'] = format_timestamp(position_info['elapsed_time'])
                    det['source_type'] = 'live'
                    det['fabric_length_m'] = position_info['length_m']
                    det['feed_speed'] = feed_speed
                    det['session_id'] = session_id
                
                all_detections.extend(classified)
            
            frame_number += 1
        
        cap.release()
        
        # Save to log
        if len(all_detections) > 0:
            log_store = await get_log_store()
            await log_store.log_defects_batch(all_detections, session_id=session_id)
        
        return JSONResponse({
            "success": True,
            "session_id": session_id,
            "detections": all_detections,
            "count": len(all_detections),
            "stream_info": {
                "url": stream_url,
                "fps": fps,
                "duration": duration_seconds,
                "frames_captured": frame_number
            },
            "mode": detector.mode
        })
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error processing stream: {str(e)}")
