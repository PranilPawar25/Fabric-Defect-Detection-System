"""
Fabric Length Tracker

This module estimates the fabric length at which defects occur based on:
- Elapsed time in video
- Feed speed (meters per minute) set by the user
- Frame number and video FPS

This allows defects to be logged with estimated fabric position for
easier physical location and quality control tracking.

⚠️ CRITICAL LIMITATION - CONSTANT SPEED ASSUMPTION:
=======================================================
This is an ESTIMATE, not a physical measurement. The calculation assumes:

1. CONSTANT FEED SPEED throughout the entire video
   - No starts/stops
   - No acceleration/deceleration
   - No operator adjustments mid-run

2. NO PHYSICAL SENSOR to verify actual fabric movement
   - Cannot detect if fabric actually stopped
   - Cannot detect speed variations
   - Relies entirely on user-provided feed speed parameter

Formula: length_meters = (feed_speed_m_per_min / 60) × elapsed_seconds

Accuracy depends entirely on feed speed stability:
- Constant speed (ideal): <1% error (timestamp calculation is correct)
- Variable speed (real-world): Error proportional to speed variation

For true measurement accuracy, physical hardware is required:
- Rotary encoder on feed roller
- Proximity sensor counting fabric markings
- Vision-based fabric motion tracking

See verify_length_accuracy.py to measure accuracy for your setup.
"""

import sys
from pathlib import Path
from typing import Optional

# Add backend to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from config import DEFAULT_FEED_SPEED, runtime_config


class LengthTracker:
    """
    Tracks and computes fabric length based on time and feed speed.
    """
    
    def __init__(self, feed_speed: Optional[float] = None):
        """
        Initialize the length tracker.
        
        Args:
            feed_speed: Feed speed in meters per minute.
                       If None, uses the runtime config default.
        """
        self.feed_speed = feed_speed if feed_speed is not None else runtime_config.feed_speed
    
    def set_feed_speed(self, feed_speed: float):
        """
        Update the feed speed.
        
        Args:
            feed_speed: New feed speed in meters per minute
        """
        if feed_speed <= 0:
            raise ValueError("Feed speed must be positive")
        self.feed_speed = feed_speed
    
    def get_feed_speed(self) -> float:
        """
        Get current feed speed.
        
        Returns:
            Feed speed in meters per minute
        """
        return self.feed_speed
    
    def compute_length_from_time(self, elapsed_seconds: float) -> float:
        """
        Compute fabric length from elapsed time.
        
        ⚠️ IMPORTANT: This assumes CONSTANT feed speed throughout!
        
        Formula: length (m) = (feed_speed m/min / 60 s/min) × elapsed_seconds
        
        This calculation is mathematically correct IF and ONLY IF:
        - Fabric moves at exactly the configured feed_speed
        - No stops, starts, or speed variations occur
        - elapsed_seconds accurately reflects video timestamp
        
        The system cannot detect speed variations without physical sensors.
        Accuracy depends entirely on feed speed stability in your setup.
        
        Args:
            elapsed_seconds: Time elapsed since start of recording
            
        Returns:
            Estimated fabric length in meters (may differ from actual
            if feed speed varied during recording)
        """
        if elapsed_seconds < 0:
            return 0.0
        
        # Convert feed speed from m/min to m/s
        feed_speed_per_second = self.feed_speed / 60.0
        
        # Compute length
        length_meters = feed_speed_per_second * elapsed_seconds
        
        return length_meters
    
    def compute_length_from_frame(self, frame_number: int, fps: float) -> float:
        """
        Compute fabric length from frame number and FPS.
        
        Args:
            frame_number: Current frame number (0-indexed)
            fps: Frames per second of the video
            
        Returns:
            Estimated fabric length in meters
        """
        if frame_number < 0 or fps <= 0:
            return 0.0
        
        # Convert frame number to elapsed time
        elapsed_seconds = frame_number / fps
        
        return self.compute_length_from_time(elapsed_seconds)
    
    def format_length(self, length_meters: float, precision: int = 2) -> str:
        """
        Format length for display.
        
        Args:
            length_meters: Length in meters
            precision: Decimal places for formatting
            
        Returns:
            Formatted string (e.g., "12.34 m")
        """
        return f"{length_meters:.{precision}f} m"
    
    def format_length_with_units(self, length_meters: float) -> str:
        """
        Format length with appropriate units (cm for < 1m, m otherwise).
        
        Args:
            length_meters: Length in meters
            
        Returns:
            Formatted string with appropriate units
        """
        if length_meters < 1.0:
            # Show in centimeters
            length_cm = length_meters * 100
            return f"{length_cm:.1f} cm"
        else:
            # Show in meters
            return f"{length_meters:.2f} m"
    
    def get_position_info(self, elapsed_seconds: float, 
                         frame_number: Optional[int] = None,
                         fps: Optional[float] = None) -> dict:
        """
        Get comprehensive position information.
        
        Args:
            elapsed_seconds: Time elapsed since start
            frame_number: Optional frame number
            fps: Optional video FPS
            
        Returns:
            Dictionary with position information:
                - length_m: Length in meters
                - length_formatted: Formatted length string
                - elapsed_time: Time in seconds
                - frame_number: Frame number (if provided)
                - feed_speed: Current feed speed
        """
        length_m = self.compute_length_from_time(elapsed_seconds)
        
        info = {
            'length_m': round(length_m, 3),
            'length_formatted': self.format_length_with_units(length_m),
            'elapsed_time': round(elapsed_seconds, 2),
            'feed_speed': self.feed_speed
        }
        
        if frame_number is not None:
            info['frame_number'] = frame_number
        
        if fps is not None:
            info['fps'] = fps
        
        return info
    
    def estimate_time_to_length(self, target_length_meters: float) -> float:
        """
        Estimate time needed to reach a target fabric length.
        
        Args:
            target_length_meters: Target length in meters
            
        Returns:
            Estimated time in seconds
        """
        if target_length_meters <= 0:
            return 0.0
        
        # Convert feed speed from m/min to m/s
        feed_speed_per_second = self.feed_speed / 60.0
        
        # Time = distance / speed
        time_seconds = target_length_meters / feed_speed_per_second
        
        return time_seconds
    
    def estimate_frame_at_length(self, target_length_meters: float, fps: float) -> int:
        """
        Estimate frame number at which a target length is reached.
        
        Args:
            target_length_meters: Target length in meters
            fps: Frames per second of the video
            
        Returns:
            Estimated frame number
        """
        time_seconds = self.estimate_time_to_length(target_length_meters)
        frame_number = int(time_seconds * fps)
        return frame_number


class VideoLengthTracker(LengthTracker):
    """
    Extended length tracker specifically for video processing.
    Maintains state for the current video being processed.
    """
    
    def __init__(self, fps: float, feed_speed: Optional[float] = None):
        """
        Initialize video length tracker.
        
        Args:
            fps: Frames per second of the video
            feed_speed: Feed speed in meters per minute
        """
        super().__init__(feed_speed)
        self.fps = fps
        self.current_frame = 0
    
    def reset(self):
        """Reset tracker to start of video."""
        self.current_frame = 0
    
    def advance_frame(self, num_frames: int = 1):
        """
        Advance the current frame counter.
        
        Args:
            num_frames: Number of frames to advance
        """
        self.current_frame += num_frames
    
    def set_frame(self, frame_number: int):
        """
        Set the current frame number.
        
        Args:
            frame_number: Frame number to set
        """
        self.current_frame = max(0, frame_number)
    
    def get_current_length(self) -> float:
        """
        Get fabric length at current frame.
        
        Returns:
            Length in meters
        """
        return self.compute_length_from_frame(self.current_frame, self.fps)
    
    def get_current_time(self) -> float:
        """
        Get elapsed time at current frame.
        
        Returns:
            Time in seconds
        """
        return self.current_frame / self.fps if self.fps > 0 else 0.0
    
    def get_current_info(self) -> dict:
        """
        Get comprehensive info for current position.
        
        Returns:
            Dictionary with position information
        """
        elapsed_seconds = self.get_current_time()
        return self.get_position_info(
            elapsed_seconds=elapsed_seconds,
            frame_number=self.current_frame,
            fps=self.fps
        )


# Global length tracker instance
_tracker_instance = None


def get_tracker() -> LengthTracker:
    """
    Get or create the global length tracker instance (singleton pattern).
    
    Returns:
        LengthTracker instance
    """
    global _tracker_instance
    if _tracker_instance is None:
        _tracker_instance = LengthTracker()
    return _tracker_instance


def compute_length(elapsed_seconds: float, feed_speed: Optional[float] = None) -> float:
    """
    Convenience function to compute length using the global tracker.
    
    Args:
        elapsed_seconds: Time elapsed in seconds
        feed_speed: Optional feed speed override
        
    Returns:
        Length in meters
    """
    tracker = get_tracker()
    if feed_speed is not None:
        old_speed = tracker.get_feed_speed()
        tracker.set_feed_speed(feed_speed)
        length = tracker.compute_length_from_time(elapsed_seconds)
        tracker.set_feed_speed(old_speed)  # Restore
        return length
    else:
        return tracker.compute_length_from_time(elapsed_seconds)


if __name__ == "__main__":
    # Test the length tracker
    print("Testing LengthTracker...")
    print("=" * 60)
    
    # Create tracker with feed speed of 10 m/min
    tracker = LengthTracker(feed_speed=10.0)
    
    print(f"Feed speed: {tracker.get_feed_speed()} m/min")
    print()
    
    # Test various time points
    test_times = [0, 6, 30, 60, 120, 300]  # seconds
    
    print("Time-based length computation:")
    print("-" * 60)
    for t in test_times:
        length = tracker.compute_length_from_time(t)
        formatted = tracker.format_length_with_units(length)
        print(f"  {t:3d} seconds → {formatted}")
    
    print()
    
    # Test frame-based computation
    fps = 30.0
    test_frames = [0, 180, 900, 1800, 3600, 9000]  # frame numbers
    
    print(f"Frame-based length computation (FPS={fps}):")
    print("-" * 60)
    for frame in test_frames:
        length = tracker.compute_length_from_frame(frame, fps)
        formatted = tracker.format_length_with_units(length)
        elapsed = frame / fps
        print(f"  Frame {frame:4d} ({elapsed:5.1f}s) → {formatted}")
    
    print()
    
    # Test video tracker
    print("Testing VideoLengthTracker...")
    print("-" * 60)
    
    video_tracker = VideoLengthTracker(fps=30.0, feed_speed=10.0)
    
    for i in range(5):
        video_tracker.set_frame(i * 300)  # Every 300 frames (10 seconds)
        info = video_tracker.get_current_info()
        print(f"  Frame {info['frame_number']:4d}: "
              f"{info['length_formatted']:>8s} "
              f"({info['elapsed_time']:.1f}s)")
    
    print()
    
    # Test reverse computation
    print("Reverse computation (length → time):")
    print("-" * 60)
    target_lengths = [0.5, 1.0, 5.0, 10.0, 50.0]  # meters
    
    for length in target_lengths:
        time = tracker.estimate_time_to_length(length)
        frame = tracker.estimate_frame_at_length(length, fps)
        print(f"  {length:5.1f} m → {time:6.1f}s (frame {frame:5d})")
    
    print()
    print("=" * 60)
    print("LengthTracker test complete!")
