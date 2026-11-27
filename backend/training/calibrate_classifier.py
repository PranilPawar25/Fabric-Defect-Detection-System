#!/usr/bin/env python3
"""
Classifier Calibration Script

This script helps tune classification thresholds by running detections on
labeled test images/videos and comparing predicted types vs. actual types.

USAGE:
    python calibrate_classifier.py <test_folder>

TEST FOLDER STRUCTURE:
    test_data/
        hole_test1.jpg
        hole_test2.jpg
        stain_test1.jpg
        knot_test1.jpg
        broken_thread_test1.mp4
        ...

Filename format: <type>_<name>.<ext>
Supported types: hole, stain, knot, double_knot, broken_thread

OUTPUT:
    - Per-defect raw feature values
    - Per-type accuracy summary
    - Confusion matrix
    - Recommendations for threshold adjustments
"""

import sys
import argparse
from pathlib import Path
import cv2
import numpy as np
from collections import defaultdict
from typing import Dict, List, Tuple
import json

# Add backend to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from inference import get_detector, classify_detections
from config import CLASSIFICATION_THRESHOLDS


def parse_filename(filename: str) -> Tuple[str, str]:
    """
    Parse defect type from filename.
    
    Args:
        filename: Filename in format <type>_<name>.<ext>
        
    Returns:
        Tuple of (defect_type, base_name)
    """
    stem = Path(filename).stem
    parts = stem.split('_', 1)
    
    if len(parts) < 2:
        return None, stem
    
    defect_type = parts[0].lower()
    valid_types = ['hole', 'stain', 'knot', 'double_knot', 'broken_thread', 'unclassified']
    
    if defect_type in valid_types:
        return defect_type, parts[1]
    else:
        return None, stem


def analyze_image(image_path: Path, detector, expected_type: str) -> List[Dict]:
    """
    Analyze a single image and return all detections with diagnostics.
    
    Args:
        image_path: Path to image file
        detector: Detector instance
        expected_type: Expected defect type from filename
        
    Returns:
        List of detection dictionaries with diagnostics
    """
    # Read image
    image = cv2.imread(str(image_path))
    if image is None:
        print(f"  ⚠️  Could not read image: {image_path}")
        return []
    
    # Run detection
    detections = detector.detect(image)
    
    if len(detections) == 0:
        print(f"  ⚠️  No defects detected in {image_path.name}")
        return []
    
    # Classify detections
    classified = classify_detections(detections)
    
    # Add expected type for comparison
    for det in classified:
        det['expected_type'] = expected_type
        det['source_file'] = image_path.name
    
    return classified


def analyze_video(video_path: Path, detector, expected_type: str, 
                 max_frames: int = 30) -> List[Dict]:
    """
    Analyze a video and return detections from first few frames.
    
    Args:
        video_path: Path to video file
        detector: Detector instance
        expected_type: Expected defect type from filename
        max_frames: Maximum number of frames to process
        
    Returns:
        List of detection dictionaries with diagnostics
    """
    cap = cv2.VideoCapture(str(video_path))
    if not cap.isOpened():
        print(f"  ⚠️  Could not open video: {video_path}")
        return []
    
    all_detections = []
    frame_count = 0
    
    while frame_count < max_frames:
        ret, frame = cap.read()
        if not ret:
            break
        
        # Process every 5th frame for speed
        if frame_count % 5 == 0:
            detections = detector.detect(frame)
            classified = classify_detections(detections)
            
            for det in classified:
                det['expected_type'] = expected_type
                det['source_file'] = video_path.name
                det['frame_number'] = frame_count
            
            all_detections.extend(classified)
        
        frame_count += 1
    
    cap.release()
    
    if len(all_detections) == 0:
        print(f"  ⚠️  No defects detected in {video_path.name}")
    
    return all_detections


def print_detection_diagnostics(detection: Dict):
    """
    Print diagnostic information for a single detection.
    
    Args:
        detection: Detection dictionary with diagnostic fields
    """
    predicted = detection.get('type', 'unknown')
    expected = detection.get('expected_type', 'unknown')
    match = "✅" if predicted == expected else "❌"
    
    print(f"\n    {match} Predicted: {predicted.upper()} | Expected: {expected.upper()}")
    print(f"       Classification: {detection.get('classification_reason', 'N/A')}")
    print(f"       Diagnostics:")
    print(f"         - Patch count: {detection.get('diagnostic_patch_count', 'N/A')}")
    print(f"         - Aspect ratio: {detection.get('diagnostic_aspect_ratio', 'N/A')}")
    print(f"         - Circularity: {detection.get('diagnostic_circularity', 'N/A')}")
    print(f"         - Area: {detection.get('diagnostic_area_px', 'N/A')} px²")
    print(f"         - Brightness Δ: {detection.get('diagnostic_brightness_delta', 'N/A')}")
    print(f"         - Edge Δ: {detection.get('diagnostic_edge_density_delta', 'N/A')}")
    print(f"         - Anomaly score: {detection.get('diagnostic_avg_anomaly_score', 'N/A')}")


def compute_accuracy_stats(all_detections: List[Dict]) -> Dict:
    """
    Compute per-type accuracy statistics.
    
    Args:
        all_detections: List of all detection dictionaries
        
    Returns:
        Dictionary with accuracy stats per type
    """
    stats = defaultdict(lambda: {'correct': 0, 'total': 0, 'predictions': []})
    confusion_matrix = defaultdict(lambda: defaultdict(int))
    
    for det in all_detections:
        expected = det.get('expected_type', 'unknown')
        predicted = det.get('type', 'unknown')
        
        stats[expected]['total'] += 1
        stats[expected]['predictions'].append(predicted)
        
        if predicted == expected:
            stats[expected]['correct'] += 1
        
        confusion_matrix[expected][predicted] += 1
    
    return dict(stats), dict(confusion_matrix)


def print_accuracy_summary(stats: Dict, confusion_matrix: Dict):
    """
    Print accuracy summary and confusion matrix.
    
    Args:
        stats: Per-type statistics
        confusion_matrix: Confusion matrix dict
    """
    print("\n" + "=" * 70)
    print("ACCURACY SUMMARY")
    print("=" * 70)
    
    overall_correct = sum(s['correct'] for s in stats.values())
    overall_total = sum(s['total'] for s in stats.values())
    
    for defect_type in sorted(stats.keys()):
        s = stats[defect_type]
        accuracy = (s['correct'] / s['total'] * 100) if s['total'] > 0 else 0
        print(f"{defect_type.upper():15} {s['correct']:2}/{s['total']:2} correct ({accuracy:5.1f}%)")
    
    print(f"{'─' * 70}")
    overall_acc = (overall_correct / overall_total * 100) if overall_total > 0 else 0
    print(f"{'OVERALL':15} {overall_correct:2}/{overall_total:2} correct ({overall_acc:5.1f}%)")
    
    print("\n" + "=" * 70)
    print("CONFUSION MATRIX")
    print("=" * 70)
    print("Rows = Expected | Columns = Predicted")
    print()
    
    all_types = sorted(set(confusion_matrix.keys()) | 
                      set(pred for preds in confusion_matrix.values() for pred in preds.keys()))
    
    # Header
    print(f"{'Expected →':15}", end='')
    for t in all_types:
        print(f"{t[:12]:>12}", end='')
    print()
    print("─" * (15 + 12 * len(all_types)))
    
    # Rows
    for expected in all_types:
        print(f"{expected[:15]:15}", end='')
        for predicted in all_types:
            count = confusion_matrix.get(expected, {}).get(predicted, 0)
            print(f"{count:>12}", end='')
        print()


def suggest_threshold_adjustments(all_detections: List[Dict], stats: Dict):
    """
    Analyze misclassifications and suggest threshold adjustments.
    
    Args:
        all_detections: List of all detections
        stats: Accuracy statistics
    """
    print("\n" + "=" * 70)
    print("THRESHOLD ADJUSTMENT SUGGESTIONS")
    print("=" * 70)
    
    # Group misclassifications by (expected, predicted) pair
    misclassifications = defaultdict(list)
    
    for det in all_detections:
        expected = det.get('expected_type', 'unknown')
        predicted = det.get('type', 'unknown')
        
        if expected != predicted:
            misclassifications[(expected, predicted)].append(det)
    
    if not misclassifications:
        print("✅ No misclassifications! All detections were correct.")
        return
    
    for (expected, predicted), dets in misclassifications.items():
        print(f"\n{expected.upper()} → {predicted.upper()} ({len(dets)} cases)")
        
        # Compute average diagnostic values for this misclassification
        avg_patch_count = np.mean([d.get('diagnostic_patch_count', 0) for d in dets])
        avg_aspect = np.mean([d.get('diagnostic_aspect_ratio', 1) for d in dets])
        avg_circ = np.mean([d.get('diagnostic_circularity', 0) for d in dets])
        
        print(f"  Average features: patches={avg_patch_count:.1f}, aspect={avg_aspect:.2f}, circ={avg_circ:.2f}")
        
        # Suggest adjustments based on patterns
        if expected == 'knot' and predicted == 'hole':
            print(f"  💡 Try: Increase 'knot_max_patches' if these are small knots")
            print(f"       OR decrease 'knot_min_circularity' if they're less circular")
        
        elif expected == 'hole' and predicted == 'stain':
            print(f"  💡 Try: Increase 'stain_min_patches' threshold")
        
        elif expected == 'broken_thread' and predicted in ['hole', 'stain']:
            if avg_aspect < 2.4 and avg_aspect > 0.42:
                print(f"  💡 Try: Decrease 'broken_thread_aspect_min' or increase '_max'")
        
        elif expected == 'double_knot' and predicted == 'knot':
            print(f"  💡 Try: Adjust 'knot_max_patches' and 'double_knot_min_patches' boundaries")
        
        else:
            print(f"  💡 Review diagnostic values above and adjust thresholds in config.py")


def main():
    parser = argparse.ArgumentParser(
        description="Calibrate defect classifier thresholds using labeled test data"
    )
    parser.add_argument(
        'test_folder',
        type=Path,
        help="Folder containing test images/videos with format: <type>_<name>.<ext>"
    )
    parser.add_argument(
        '--verbose', '-v',
        action='store_true',
        help="Print detailed diagnostics for each detection"
    )
    parser.add_argument(
        '--max-frames',
        type=int,
        default=30,
        help="Maximum frames to process per video (default: 30)"
    )
    parser.add_argument(
        '--export-json',
        type=Path,
        help="Export all detection data to JSON file"
    )
    
    args = parser.parse_args()
    
    # Validate test folder
    if not args.test_folder.exists():
        print(f"❌ Test folder not found: {args.test_folder}")
        return 1
    
    # Find all test files
    test_files = []
    for pattern in ['*.jpg', '*.jpeg', '*.png', '*.mp4', '*.avi', '*.mov']:
        test_files.extend(args.test_folder.glob(pattern))
    
    if not test_files:
        print(f"❌ No test files found in {args.test_folder}")
        print("Expected filename format: <type>_<name>.<ext>")
        print("Example: hole_test1.jpg, stain_test1.jpg")
        return 1
    
    print("=" * 70)
    print("CLASSIFIER CALIBRATION TOOL")
    print("=" * 70)
    print(f"Test folder: {args.test_folder}")
    print(f"Test files found: {len(test_files)}")
    print()
    print("Current thresholds:")
    for key, value in sorted(CLASSIFICATION_THRESHOLDS.items()):
        print(f"  {key}: {value}")
    print("=" * 70)
    
    # Initialize detector
    print("\nInitializing detector...")
    detector = get_detector()
    print(f"✅ Detector ready (mode: {detector.mode})")
    
    # Process all test files
    all_detections = []
    
    for test_file in sorted(test_files):
        expected_type, name = parse_filename(test_file.name)
        
        if expected_type is None:
            print(f"\n⚠️  Skipping {test_file.name} (couldn't parse defect type)")
            continue
        
        print(f"\n📁 Processing: {test_file.name} (expected: {expected_type.upper()})")
        
        # Analyze based on file type
        if test_file.suffix.lower() in ['.mp4', '.avi', '.mov']:
            detections = analyze_video(test_file, detector, expected_type, args.max_frames)
        else:
            detections = analyze_image(test_file, detector, expected_type)
        
        print(f"  Found {len(detections)} detection(s)")
        
        # Print diagnostics if verbose
        if args.verbose and detections:
            for i, det in enumerate(detections, 1):
                print(f"  Detection {i}:")
                print_detection_diagnostics(det)
        
        all_detections.extend(detections)
    
    if not all_detections:
        print("\n❌ No detections found across all test files")
        return 1
    
    # Compute accuracy
    stats, confusion_matrix = compute_accuracy_stats(all_detections)
    
    # Print results
    print_accuracy_summary(stats, confusion_matrix)
    suggest_threshold_adjustments(all_detections, stats)
    
    # Export JSON if requested
    if args.export_json:
        with open(args.export_json, 'w') as f:
            json.dump(all_detections, f, indent=2, default=str)
        print(f"\n📄 Exported detection data to: {args.export_json}")
    
    print("\n" + "=" * 70)
    print("NEXT STEPS:")
    print("1. Review the accuracy summary and confusion matrix above")
    print("2. Check diagnostic values for misclassified defects")
    print("3. Update thresholds in backend/config.py CLASSIFICATION_THRESHOLDS")
    print("4. Re-run this script to verify improvements")
    print("=" * 70)
    
    return 0


if __name__ == "__main__":
    sys.exit(main())
