"""
Live Session Manager for Real-Time Fabric Defect Detection

Handles:
- Single phone connection (one at a time)
- Frame reception, detection, classification
- Deduplication by screen position
- Length estimation from elapsed time
- Database logging with source_type="live"
- Back-pressure throttling
"""

import asyncio
import time
import uuid
import traceback
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set
import cv2
import numpy as np

from inference import get_detector, classify_detections
from inference.length_tracker import LengthTracker
from db import get_log_store
from config import runtime_config


@dataclass
class TrackedDefect:
    """A defect being tracked across frames for deduplication."""
    defect_type: str
    x: int
    y: int
    w: int
    h: int
    confidence: float
    first_frame: int
    last_seen_frame: int
    logged: bool = False
    
    def center(self):
        """Get center point of defect."""
        return (self.x + self.w // 2, self.y + self.h // 2)
    
    def distance_to(self, other) -> float:
        """Euclidean distance to another defect's center."""
        cx1, cy1 = self.center()
        cx2, cy2 = other.center()
        return ((cx1 - cx2) ** 2 + (cy1 - cy2) ** 2) ** 0.5


@dataclass
class LiveSession:
    """Manages a single live stream session."""
    session_id: str
    token: str
    created_at: float = field(default_factory=time.time)
    phone_connected: bool = False
    phone_ws: Optional[object] = None
    viewer_ws: Set[object] = field(default_factory=set)
    
    # Frame processing
    frame_count: int = 0
    defects_logged: int = 0
    processing_times: List[float] = field(default_factory=list)
    last_throttle_check: float = field(default_factory=time.time)
    min_interval_ms: int = 200  # Default: ~5 FPS
    
    # Deduplication
    tracked_defects: List[TrackedDefect] = field(default_factory=list)
    finalize_after_n_frames: int = 5  # Finalize if not seen for this many frames
    position_threshold_px: int = 50  # Max distance to consider same defect
    
    # Length tracking
    length_tracker: LengthTracker = field(default_factory=LengthTracker)
    
    # Client timing
    first_client_time_ms: Optional[float] = None
    
    def elapsed_seconds(self, client_time_ms: float) -> float:
        """
        Compute elapsed seconds from client timestamp.
        
        Args:
            client_time_ms: Client's timestamp in milliseconds
            
        Returns:
            Elapsed seconds since first frame
        """
        if self.first_client_time_ms is None:
            self.first_client_time_ms = client_time_ms
            return 0.0
        
        return (client_time_ms - self.first_client_time_ms) / 1000.0
    
    def update_stats(self, processing_time: float):
        """Update processing statistics."""
        self.processing_times.append(processing_time)
        
        # Keep last 20 samples
        if len(self.processing_times) > 20:
            self.processing_times = self.processing_times[-20:]
    
    def avg_processing_ms(self) -> float:
        """Get average processing time in milliseconds."""
        if not self.processing_times:
            return 0.0
        return sum(self.processing_times) * 1000 / len(self.processing_times)
    
    def should_throttle(self) -> bool:
        """Check if we should slow down the phone."""
        avg_ms = self.avg_processing_ms()
        return avg_ms > 500  # Throttle if processing takes > 500ms
    
    def find_matching_defect(self, det: Dict) -> Optional[TrackedDefect]:
        """
        Find an existing tracked defect that matches the new detection.
        
        Args:
            det: Detection dictionary with type, x, y, w, h
            
        Returns:
            TrackedDefect if match found, None otherwise
        """
        defect_type = det.get('type') or det.get('defect_type')
        
        # Create temporary defect for distance calculation
        temp_defect = TrackedDefect(
            defect_type=defect_type,
            x=det['x'],
            y=det['y'],
            w=det['w'],
            h=det['h'],
            confidence=det['confidence'],
            first_frame=self.frame_count,
            last_seen_frame=self.frame_count
        )
        
        # Find matches by type and proximity
        for tracked in self.tracked_defects:
            if tracked.defect_type == defect_type:
                distance = tracked.distance_to(temp_defect)
                if distance <= self.position_threshold_px:
                    return tracked
        
        return None
    
    def update_or_add_defect(self, det: Dict):
        """
        Update existing defect or add new one.
        
        Args:
            det: Detection dictionary
        """
        existing = self.find_matching_defect(det)
        
        if existing:
            # Update existing defect
            existing.last_seen_frame = self.frame_count
            
            # Update with better confidence
            if det['confidence'] > existing.confidence:
                existing.confidence = det['confidence']
                existing.x = det['x']
                existing.y = det['y']
                existing.w = det['w']
                existing.h = det['h']
        else:
            # Add new defect
            defect_type = det.get('type') or det.get('defect_type')
            tracked = TrackedDefect(
                defect_type=defect_type,
                x=det['x'],
                y=det['y'],
                w=det['w'],
                h=det['h'],
                confidence=det['confidence'],
                first_frame=self.frame_count,
                last_seen_frame=self.frame_count
            )
            self.tracked_defects.append(tracked)
    
    async def finalize_old_defects(self, log_store):
        """
        Finalize defects that haven't been seen recently.
        
        Args:
            log_store: Database log store
        """
        to_log = []
        
        for tracked in self.tracked_defects:
            if tracked.logged:
                continue
            
            frames_since_seen = self.frame_count - tracked.last_seen_frame
            
            if frames_since_seen >= self.finalize_after_n_frames:
                # This defect is stable, log it
                to_log.append(tracked)
                tracked.logged = True
        
        # Log to database
        for tracked in to_log:
            await self.log_defect(tracked, log_store)
    
    async def log_defect(self, tracked: TrackedDefect, log_store):
        """
        Log a defect to the database.
        
        Args:
            tracked: TrackedDefect to log
            log_store: Database log store
        """
        # Compute elapsed time and fabric length
        # Use the midpoint frame for timing
        mid_frame = (tracked.first_frame + tracked.last_seen_frame) // 2
        
        # Estimate elapsed time (assume constant frame rate)
        elapsed_s = mid_frame / max(self.frame_count, 1) * \
                   (time.time() - self.created_at) if self.frame_count > 0 else 0.0
        
        # Compute fabric length
        fabric_length_m = self.length_tracker.compute_length_from_time(elapsed_s)
        
        # Format timestamp display
        mins = int(elapsed_s // 60)
        secs = int(elapsed_s % 60)
        timestamp_display = f"{mins:02d}:{secs:02d}"
        
        # Prepare defect dict
        defect_dict = {
            'defect_type': tracked.defect_type,
            'type': tracked.defect_type,
            'x': tracked.x,
            'y': tracked.y,
            'w': tracked.w,
            'h': tracked.h,
            'confidence': tracked.confidence,
            'source_type': 'live',
            'frame_number': mid_frame,
            'timestamp_seconds': elapsed_s,
            'timestamp_display': timestamp_display,
            'fabric_length_m': fabric_length_m,
            'elapsed_time_s': elapsed_s,
            'feed_speed': self.length_tracker.get_feed_speed(),
            'mode': get_detector().mode,
        }
        
        await log_store.log_defect(defect_dict, session_id=self.session_id)
        self.defects_logged += 1


# Global session management
_active_session: Optional[LiveSession] = None
_session_lock = asyncio.Lock()
_startup_session_created = False


async def ensure_startup_session():
    """
    Ensure a session exists at startup.
    This allows phone links to work immediately without manual session creation.
    """
    global _active_session, _startup_session_created
    
    if _startup_session_created or _active_session is not None:
        return
    
    async with _session_lock:
        if _active_session is None:
            session_id = str(uuid.uuid4())
            token = str(uuid.uuid4())[:16]  # Short token
            
            _active_session = LiveSession(
                session_id=session_id,
                token=token
            )
            
            # Set feed speed from current config
            _active_session.length_tracker.set_feed_speed(runtime_config.feed_speed)
            
            _startup_session_created = True
            
            print(f"\n{'='*70}")
            print(f"📱 Live Stream Session Auto-Created")
            print(f"{'='*70}")
            print(f"Session ID: {session_id}")
            print(f"Token: {token}")
            print(f"{'='*70}\n")


async def create_session() -> LiveSession:
    """
    Create a new live session.
    
    Returns:
        LiveSession instance
        
    Raises:
        RuntimeError: If a session already exists
    """
    global _active_session
    
    async with _session_lock:
        if _active_session is not None:
            raise RuntimeError("A live session already exists")
        
        session_id = str(uuid.uuid4())
        token = str(uuid.uuid4())[:16]  # Short token
        
        _active_session = LiveSession(
            session_id=session_id,
            token=token
        )
        
        # Set feed speed from current config
        _active_session.length_tracker.set_feed_speed(runtime_config.feed_speed)
        
        return _active_session


async def get_session() -> Optional[LiveSession]:
    """Get the active session, if any."""
    return _active_session


async def end_session():
    """End the active session."""
    global _active_session
    
    async with _session_lock:
        if _active_session is not None:
            # Finalize any remaining defects
            if _active_session.tracked_defects:
                log_store = await get_log_store()
                for tracked in _active_session.tracked_defects:
                    if not tracked.logged:
                        await _active_session.log_defect(tracked, log_store)
            
            _active_session = None


async def process_frame(session: LiveSession, jpeg_data: bytes, client_time_ms: float) -> Dict:
    """
    Process a single frame from the phone.
    
    Args:
        session: LiveSession instance
        jpeg_data: JPEG image bytes
        client_time_ms: Client timestamp in milliseconds
        
    Returns:
        Dict with result data
    """
    start_time = time.time()
    
    try:
        # Decode JPEG
        nparr = np.frombuffer(jpeg_data, np.uint8)
        frame = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
        
        if frame is None:
            raise ValueError("Failed to decode JPEG")
        
        frame_h, frame_w = frame.shape[:2]
        
        # Get current config (re-read each frame so slider changes apply live)
        current_k_sigma = runtime_config.k_sigma
        current_min_conf = runtime_config.min_confidence
        current_feed_speed = runtime_config.feed_speed
        
        # Update feed speed in tracker
        session.length_tracker.set_feed_speed(current_feed_speed)
        
        # Run detection in executor to avoid blocking event loop
        loop = asyncio.get_event_loop()
        detector = get_detector()
        
        detections = await loop.run_in_executor(
            None,
            detector.detect,
            frame
        )
        
        # Classify detections
        classified_detections = classify_detections(detections)
        
        # Compute elapsed time
        elapsed_s = session.elapsed_seconds(client_time_ms)
        
        # Compute fabric length
        fabric_length_m = session.length_tracker.compute_length_from_time(elapsed_s)
        
        # Update frame count
        session.frame_count += 1
        
        # Update or add defects for deduplication
        for det in classified_detections:
            session.update_or_add_defect(det)
        
        # Finalize old defects
        log_store = await get_log_store()
        await session.finalize_old_defects(log_store)
        
        # Update processing stats
        processing_time = time.time() - start_time
        session.update_stats(processing_time)
        
        # Check throttling
        now = time.time()
        if now - session.last_throttle_check > 2.0:  # Check every 2 seconds
            session.last_throttle_check = now
            if session.should_throttle():
                session.min_interval_ms = 300  # Slow down to ~3 FPS
            else:
                session.min_interval_ms = 200  # Normal ~5 FPS
        
        # Prepare result
        result = {
            'detections': classified_detections,
            'frame_w': frame_w,
            'frame_h': frame_h,
            'frame_number': session.frame_count,
            'elapsed_s': elapsed_s,
            'est_length_m': fabric_length_m,
            'mode': detector.mode,
            'processing_ms': int(processing_time * 1000)
        }
        
        return result
        
    except Exception as e:
        # Log error but don't crash
        print(f"[LiveSession] Frame processing error: {e}")
        traceback.print_exc()
        raise
