#!/usr/bin/env python3
"""
Fabric Length Measurement Verification Tool

This script verifies the accuracy of fabric length estimation by comparing
the system's calculated length against a known, physically-measured reference.

USAGE:
    python verify_length_accuracy.py <video_file> --real-length <meters> --feed-speed <m/min>

PURPOSE:
    Since there is no physical encoder/sensor to validate length measurements,
    this tool provides a way to test accuracy using controlled test footage
    where the actual fabric length is known by manual measurement.

EXAMPLE:
    # You physically measured 2.0 meters of fabric passing through
    # at 10 m/min feed speed and recorded the video:
    python verify_length_accuracy.py test_2m_fabric.mp4 --real-length 2.0 --feed-speed 10.0

OUTPUT:
    - System's estimated total length
    - Your provided real length
    - Absolute error (meters)
    - Percentage error
    - Detailed frame-by-frame analysis (with --verbose)
"""

import sys
import argparse
from pathlib import Path
import cv2
from typing import Optional

# Add backend to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from inference.length_tracker import LengthTracker


def verify_length_accuracy(
    video_path: Path,
    real_length_m: float,
    feed_speed: float,
    verbose: bool = False
) -> dict:
    """
    Verify length measurement accuracy against known real length.
    
    Args:
        video_path: Path to test video
        real_length_m: Actual measured fabric length in meters
        feed_speed: Feed speed in m/min used during recording
        verbose: Print frame-by-frame details
        
    Returns:
        Dictionary with verification results
    """
    # Open video
    cap = cv2.VideoCapture(str(video_path))
    if not cap.isOpened():
        raise ValueError(f"Could not open video: {video_path}")
    
    # Get video properties
    fps = cap.get(cv2.CAP_PROP_FPS)
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    
    if fps <= 0:
        raise ValueError(f"Invalid FPS: {fps}")
    
    if total_frames <= 0:
        raise ValueError(f"Invalid frame count: {total_frames}")
    
    # Calculate duration using frame count (as fallback)
    duration_from_frames = total_frames / fps
    
    print("=" * 70)
    print("VIDEO INFORMATION")
    print("=" * 70)
    print(f"File: {video_path.name}")
    print(f"FPS: {fps:.2f}")
    print(f"Total frames: {total_frames}")
    print(f"Duration (from frame count): {duration_from_frames:.2f}s")
    print()
    
    # Initialize tracker
    tracker = LengthTracker(feed_speed=feed_speed)
    
    # Method 1: Calculate from last frame using actual timestamp
    # This is the CORRECT method that matches what the system now uses
    cap.set(cv2.CAP_PROP_POS_FRAMES, total_frames - 1)
    ret, _ = cap.read()
    
    if ret:
        timestamp_ms = cap.get(cv2.CAP_PROP_POS_MSEC)
        actual_duration = timestamp_ms / 1000.0
        estimated_length_from_timestamp = tracker.compute_length_from_time(actual_duration)
        
        print("=" * 70)
        print("METHOD 1: Using Actual Video Timestamp (CURRENT SYSTEM METHOD)")
        print("=" * 70)
        print(f"Video timestamp at last frame: {timestamp_ms:.0f} ms ({actual_duration:.2f}s)")
        print(f"Estimated length: {estimated_length_from_timestamp:.3f} m")
        print()
    else:
        print("⚠️  Could not read last frame to get actual timestamp")
        actual_duration = None
        estimated_length_from_timestamp = None
    
    # Method 2: Calculate from frame count (OLD/WRONG method for comparison)
    estimated_length_from_frames = tracker.compute_length_from_time(duration_from_frames)
    
    print("=" * 70)
    print("METHOD 2: Using Frame Count Assumption (OLD METHOD - for comparison)")
    print("=" * 70)
    print(f"Duration from frame count: {duration_from_frames:.2f}s")
    print(f"Estimated length: {estimated_length_from_frames:.3f} m")
    print()
    
    # Sample frames throughout video if verbose
    if verbose and actual_duration is not None:
        print("=" * 70)
        print("FRAME-BY-FRAME ANALYSIS (Sampling)")
        print("=" * 70)
        
        # Sample every 10% of the video
        sample_points = [int(total_frames * p / 100) for p in range(0, 101, 10)]
        
        print(f"{'Frame':>8} {'Time (s)':>10} {'Length (m)':>12}")
        print("-" * 70)
        
        for frame_idx in sample_points:
            cap.set(cv2.CAP_PROP_POS_FRAMES, frame_idx)
            ret, _ = cap.read()
            
            if ret:
                ts_ms = cap.get(cv2.CAP_PROP_POS_MSEC)
                ts_sec = ts_ms / 1000.0
                length = tracker.compute_length_from_time(ts_sec)
                print(f"{frame_idx:8d} {ts_sec:10.2f} {length:12.3f}")
        
        print()
    
    cap.release()
    
    # Compare with real length
    print("=" * 70)
    print("ACCURACY VERIFICATION")
    print("=" * 70)
    print(f"Feed speed used: {feed_speed:.2f} m/min")
    print(f"Real measured length: {real_length_m:.3f} m")
    print()
    
    if estimated_length_from_timestamp is not None:
        print("Using Current System Method (timestamp-based):")
        error_m = estimated_length_from_timestamp - real_length_m
        error_percent = (error_m / real_length_m * 100) if real_length_m > 0 else 0
        
        print(f"  Estimated length: {estimated_length_from_timestamp:.3f} m")
        print(f"  Absolute error: {error_m:+.3f} m")
        print(f"  Percentage error: {error_percent:+.2f}%")
        
        # Accuracy assessment
        abs_error_percent = abs(error_percent)
        if abs_error_percent < 1:
            assessment = "✅ EXCELLENT (< 1% error)"
        elif abs_error_percent < 3:
            assessment = "✅ GOOD (< 3% error)"
        elif abs_error_percent < 5:
            assessment = "⚠️  ACCEPTABLE (< 5% error)"
        elif abs_error_percent < 10:
            assessment = "⚠️  MODERATE (< 10% error)"
        else:
            assessment = "❌ POOR (≥ 10% error)"
        
        print(f"  Assessment: {assessment}")
        print()
    
    print("Using Old Method (frame-count based - for comparison):")
    error_m_old = estimated_length_from_frames - real_length_m
    error_percent_old = (error_m_old / real_length_m * 100) if real_length_m > 0 else 0
    
    print(f"  Estimated length: {estimated_length_from_frames:.3f} m")
    print(f"  Absolute error: {error_m_old:+.3f} m")
    print(f"  Percentage error: {error_percent_old:+.2f}%")
    print()
    
    if actual_duration is not None and duration_from_frames != actual_duration:
        print("⚠️  NOTE: Actual video duration differs from frame-count assumption!")
        print(f"  Frame-count duration: {duration_from_frames:.2f}s")
        print(f"  Actual timestamp: {actual_duration:.2f}s")
        print(f"  Difference: {actual_duration - duration_from_frames:.2f}s")
        print()
    
    print("=" * 70)
    print("IMPORTANT LIMITATIONS")
    print("=" * 70)
    print("This measurement assumes:")
    print("  1. CONSTANT feed speed throughout the entire video")
    print("  2. No acceleration, deceleration, or stops")
    print("  3. Video playback speed matches recording speed (1x)")
    print()
    print("Error sources:")
    print("  - Variable feed speed (not detectable without encoder)")
    print("  - Video codec compression artifacts")
    print("  - Manual measurement error in real length")
    print("  - Timestamp precision in video file")
    print("=" * 70)
    
    return {
        'video_path': str(video_path),
        'fps': fps,
        'total_frames': total_frames,
        'real_length_m': real_length_m,
        'feed_speed': feed_speed,
        'estimated_length_timestamp': estimated_length_from_timestamp,
        'estimated_length_frames': estimated_length_from_frames,
        'error_m': error_m if estimated_length_from_timestamp else None,
        'error_percent': error_percent if estimated_length_from_timestamp else None,
        'duration_actual': actual_duration,
        'duration_from_frames': duration_from_frames
    }


def main():
    parser = argparse.ArgumentParser(
        description="Verify fabric length measurement accuracy against known reference",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
EXAMPLE USAGE:
  # You measured 2.0 meters of fabric and recorded it at 10 m/min:
  python verify_length_accuracy.py test_2m.mp4 --real-length 2.0 --feed-speed 10.0
  
  # With detailed frame-by-frame analysis:
  python verify_length_accuracy.py test_2m.mp4 -r 2.0 -s 10.0 --verbose

CREATING TEST FOOTAGE:
  1. Physically measure a known length of fabric (e.g., 2.0 meters)
  2. Mark the start and end points on the fabric
  3. Set your feed speed (e.g., 10 m/min)
  4. Start recording video
  5. Run the fabric through until both marks have passed
  6. Stop recording
  7. Use this script to verify the system's estimate
        """
    )
    
    parser.add_argument(
        'video_file',
        type=Path,
        help="Path to test video file"
    )
    
    parser.add_argument(
        '--real-length', '-r',
        type=float,
        required=True,
        help="Actual measured fabric length in meters"
    )
    
    parser.add_argument(
        '--feed-speed', '-s',
        type=float,
        required=True,
        help="Feed speed in meters per minute"
    )
    
    parser.add_argument(
        '--verbose', '-v',
        action='store_true',
        help="Show frame-by-frame analysis"
    )
    
    args = parser.parse_args()
    
    # Validate inputs
    if not args.video_file.exists():
        print(f"❌ Error: Video file not found: {args.video_file}")
        return 1
    
    if args.real_length <= 0:
        print(f"❌ Error: Real length must be positive (got {args.real_length})")
        return 1
    
    if args.feed_speed <= 0:
        print(f"❌ Error: Feed speed must be positive (got {args.feed_speed})")
        return 1
    
    # Run verification
    try:
        results = verify_length_accuracy(
            video_path=args.video_file,
            real_length_m=args.real_length,
            feed_speed=args.feed_speed,
            verbose=args.verbose
        )
        
        return 0
    
    except Exception as e:
        print(f"\n❌ Error during verification: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
