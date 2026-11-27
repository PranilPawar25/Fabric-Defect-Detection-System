"""
Defect Type Classifier

This module classifies detected defects into specific types based on
shape heuristics and geometric properties of the bounding boxes.

Defect Types:
- Hole: Small to medium irregular defects
- Stain: Large irregular blobs, roughly circular or irregular
- Knot: Small, roughly circular defects (1-2 patches)
- Double Knot: Small to medium circular defects (3-5 patches)
- Broken Thread: Very elongated defects (high or low aspect ratio)

DIAGNOSTIC MODE:
All classification now includes raw diagnostic data (patch_count, aspect_ratio,
circularity, brightness_delta, etc.) to enable tuning thresholds based on real data.
"""

import numpy as np
import cv2
from typing import Dict, List, Tuple
import sys
from pathlib import Path

# Add backend to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from config import (
    PATCH_SIZE,
    CLASSIFICATION_THRESHOLDS,
    SCORING_WEIGHTS
)


class DefectClassifier:
    """
    Classifies defects into specific types based on geometric features.
    
    Now includes full diagnostic output for every detection to enable
    threshold tuning based on real fabric data.
    """
    
    def __init__(self):
        """Initialize classifier with thresholds from config."""
        self.thresholds = CLASSIFICATION_THRESHOLDS
        self.scoring_weights = SCORING_WEIGHTS
        self.min_score = SCORING_WEIGHTS['min_classification_score']
    
    @staticmethod
    def compute_aspect_ratio(w: int, h: int) -> float:
        """
        Compute aspect ratio (height / width).
        
        Args:
            w: Width of bounding box
            h: Height of bounding box
            
        Returns:
            Aspect ratio
        """
        if w == 0:
            return float('inf')
        return h / w
    
    @staticmethod
    def compute_circularity(w: int, h: int, num_patches: int) -> float:
        """
        Estimate circularity of a defect region.
        
        Circularity = 4π * area / perimeter²
        For a perfect circle, circularity = 1.0
        For irregular shapes, circularity < 1.0
        
        Args:
            w: Width of bounding box
            h: Height of bounding box
            num_patches: Number of patches in the defect region
            
        Returns:
            Circularity score (0-1)
        """
        # Approximate area from number of patches
        area = num_patches * (PATCH_SIZE ** 2)
        
        # Approximate perimeter from bounding box
        # This is a rough estimate; actual perimeter would need contour analysis
        perimeter = 2 * (w + h)
        
        if perimeter == 0:
            return 0.0
        
        circularity = (4 * np.pi * area) / (perimeter ** 2)
        
        # Clamp to [0, 1] range
        return min(circularity, 1.0)
    
    @staticmethod
    def estimate_patch_count(w: int, h: int) -> int:
        """
        Estimate number of patches in a bounding box.
        
        Args:
            w: Width of bounding box
            h: Height of bounding box
            
        Returns:
            Estimated number of patches
        """
        patches_w = max(1, w // PATCH_SIZE)
        patches_h = max(1, h // PATCH_SIZE)
        return patches_w * patches_h
    
    def compute_diagnostic_features(self, detection: Dict) -> Dict:
        """
        Compute all diagnostic features for a detection.
        
        This is the core diagnostic function that extracts raw feature values
        used in classification decisions.
        
        Args:
            detection: Detection dictionary with keys x, y, w, h, confidence
            
        Returns:
            Dictionary with diagnostic features:
                - patch_count: Number of patches in bounding box
                - aspect_ratio: Height/width ratio
                - circularity: 0-1, how circular the defect is
                - area_px: Bounding box area in pixels
                - brightness_delta: Brightness deviation (if available from detector)
                - edge_density_delta: Edge pattern deviation (if available)
                - avg_anomaly_score: Average anomaly score (if available)
        """
        w = detection['w']
        h = detection['h']
        
        # Geometric features
        patch_count = self.estimate_patch_count(w, h)
        aspect_ratio = self.compute_aspect_ratio(w, h)
        circularity = self.compute_circularity(w, h, patch_count)
        area_px = w * h
        
        # Anomaly scores (may be provided by detector)
        avg_anomaly_score = detection.get('avg_score', 0.0)
        brightness_delta = detection.get('brightness_delta', 0.0)
        edge_density_delta = detection.get('edge_delta', 0.0)
        
        return {
            'patch_count': patch_count,
            'aspect_ratio': round(aspect_ratio, 3),
            'circularity': round(circularity, 3),
            'area_px': area_px,
            'brightness_delta': round(brightness_delta, 3),
            'edge_density_delta': round(edge_density_delta, 3),
            'avg_anomaly_score': round(avg_anomaly_score, 3)
        }
    
    def score_broken_thread(self, diag: Dict) -> Tuple[float, str]:
        """
        Compute broken thread score based on elongation and edge features.
        
        Args:
            diag: Diagnostic features dictionary
            
        Returns:
            Tuple of (score 0-100, reasoning string)
        """
        weights = self.scoring_weights['broken_thread']
        aspect_ratio = diag['aspect_ratio']
        edge_delta = diag['edge_density_delta']
        patch_count = diag['patch_count']
        
        # Aspect ratio score (0-100) - PRIMARY signal for broken thread
        if aspect_ratio >= weights['aspect_optimal_high']:
            aspect_score = 100.0
        elif aspect_ratio <= weights['aspect_optimal_low']:
            aspect_score = 100.0
        elif aspect_ratio >= weights['aspect_moderate_high']:
            # Linear interpolation between moderate and optimal (high)
            aspect_score = 50.0 + 50.0 * (aspect_ratio - weights['aspect_moderate_high']) / \
                          (weights['aspect_optimal_high'] - weights['aspect_moderate_high'])
        elif aspect_ratio <= weights['aspect_moderate_low']:
            # Linear interpolation between moderate and optimal (low)
            aspect_score = 50.0 + 50.0 * (weights['aspect_moderate_low'] - aspect_ratio) / \
                          (weights['aspect_moderate_low'] - weights['aspect_optimal_low'])
        else:
            # Between moderate thresholds - low score (not elongated enough)
            aspect_score = 0.0
        
        # Edge score (high edge delta = frayed/irregular edge)
        edge_score = min(100.0, abs(edge_delta) * 100.0)
        
        # Size score - broken threads are usually small to medium
        # Penalize very large sizes (those are more likely stains)
        if patch_count <= weights['size_penalize_above']:
            size_score = 100.0
        else:
            # Exponential decay for sizes above threshold
            size_score = max(0, 100.0 * (0.7 ** (patch_count - weights['size_penalize_above'])))
        
        # Weighted total
        total_score = (aspect_score * weights['aspect_weight'] +
                      edge_score * weights['edge_weight'] +
                      size_score * weights['size_weight'])
        
        reason = f"aspect={aspect_ratio:.2f} (score:{aspect_score:.0f}), edge_Δ={edge_delta:.2f} (score:{edge_score:.0f}), size={patch_count} ({size_score:.0f})"
        return total_score, reason
    
    def score_knot(self, diag: Dict) -> Tuple[float, str]:
        """
        Compute knot score based on small size, high circularity, square aspect.
        
        Args:
            diag: Diagnostic features dictionary
            
        Returns:
            Tuple of (score 0-100, reasoning string)
        """
        weights = self.scoring_weights['knot']
        patch_count = diag['patch_count']
        circularity = diag['circularity']
        aspect_ratio = diag['aspect_ratio']
        aspect_dev = abs(aspect_ratio - 1.0)
        
        # Size score (smaller is better for knot)
        if patch_count <= weights['size_optimal_max']:
            size_score = 100.0
        elif patch_count <= weights['size_acceptable_max']:
            size_score = 50.0
        else:
            # Exponential decay for larger sizes
            size_score = max(0, 50.0 * (0.7 ** (patch_count - weights['size_acceptable_max'])))
        
        # Circularity score
        if circularity >= weights['circularity_optimal_min']:
            circ_score = 100.0
        elif circularity >= weights['circularity_acceptable_min']:
            # Linear between acceptable and optimal
            circ_score = 50.0 + 50.0 * (circularity - weights['circularity_acceptable_min']) / \
                        (weights['circularity_optimal_min'] - weights['circularity_acceptable_min'])
        else:
            # Below acceptable - exponential decay
            circ_score = max(0, 50.0 * (circularity / weights['circularity_acceptable_min']))
        
        # Aspect score (should be close to 1.0 = square)
        if aspect_dev <= weights['aspect_dev_optimal']:
            aspect_score = 100.0
        elif aspect_dev <= weights['aspect_dev_acceptable']:
            aspect_score = 50.0 + 50.0 * (weights['aspect_dev_acceptable'] - aspect_dev) / \
                          (weights['aspect_dev_acceptable'] - weights['aspect_dev_optimal'])
        else:
            # Aggressive penalty for very elongated shapes (they're not knots!)
            aspect_score = max(0, 25.0 * (1.0 - (aspect_dev - weights['aspect_dev_acceptable'])))
        
        # Weighted total
        total_score = (size_score * weights['size_weight'] +
                      circ_score * weights['circularity_weight'] +
                      aspect_score * weights['aspect_weight'])
        
        reason = f"patches={patch_count} ({size_score:.0f}), circ={circularity:.2f} ({circ_score:.0f}), aspect={aspect_ratio:.2f} ({aspect_score:.0f})"
        return total_score, reason
    
    def score_double_knot(self, diag: Dict) -> Tuple[float, str]:
        """
        Compute double knot score based on medium size range, moderate circularity.
        
        Args:
            diag: Diagnostic features dictionary
            
        Returns:
            Tuple of (score 0-100, reasoning string)
        """
        weights = self.scoring_weights['double_knot']
        patch_count = diag['patch_count']
        circularity = diag['circularity']
        aspect_ratio = diag['aspect_ratio']
        aspect_dev = abs(aspect_ratio - 1.0)
        
        # Size score (medium range is optimal)
        if weights['size_optimal_min'] <= patch_count <= weights['size_optimal_max']:
            size_score = 100.0
        elif weights['size_acceptable_min'] <= patch_count <= weights['size_acceptable_max']:
            # In acceptable range
            if patch_count < weights['size_optimal_min']:
                size_score = 50.0 + 50.0 * (patch_count - weights['size_acceptable_min']) / \
                            (weights['size_optimal_min'] - weights['size_acceptable_min'])
            else:
                size_score = 50.0 + 50.0 * (weights['size_acceptable_max'] - patch_count) / \
                            (weights['size_acceptable_max'] - weights['size_optimal_max'])
        else:
            # Outside acceptable range
            size_score = 0.0
        
        # Circularity score
        if circularity >= weights['circularity_optimal_min']:
            circ_score = 100.0
        elif circularity >= weights['circularity_acceptable_min']:
            circ_score = 50.0 + 50.0 * (circularity - weights['circularity_acceptable_min']) / \
                        (weights['circularity_optimal_min'] - weights['circularity_acceptable_min'])
        else:
            circ_score = max(0, 50.0 * (circularity / weights['circularity_acceptable_min']))
        
        # Aspect score
        if aspect_dev <= weights['aspect_dev_optimal']:
            aspect_score = 100.0
        elif aspect_dev <= weights['aspect_dev_acceptable']:
            aspect_score = 50.0 + 50.0 * (weights['aspect_dev_acceptable'] - aspect_dev) / \
                          (weights['aspect_dev_acceptable'] - weights['aspect_dev_optimal'])
        else:
            # Aggressive penalty for very elongated shapes
            aspect_score = max(0, 25.0 * (1.0 - (aspect_dev - weights['aspect_dev_acceptable'])))
        
        # Weighted total
        total_score = (size_score * weights['size_weight'] +
                      circ_score * weights['circularity_weight'] +
                      aspect_score * weights['aspect_weight'])
        
        reason = f"patches={patch_count} ({size_score:.0f}), circ={circularity:.2f} ({circ_score:.0f}), aspect={aspect_ratio:.2f} ({aspect_score:.0f})"
        return total_score, reason
    
    def score_stain(self, diag: Dict) -> Tuple[float, str]:
        """
        Compute stain score based on large size and brightness deviation.
        
        Args:
            diag: Diagnostic features dictionary
            
        Returns:
            Tuple of (score 0-100, reasoning string)
        """
        weights = self.scoring_weights['stain']
        patch_count = diag['patch_count']
        area_px = diag['area_px']
        brightness_delta = diag['brightness_delta']
        
        # Size score (larger is better) - use BOTH patch count AND area
        if patch_count >= weights['size_optimal_min']:
            size_score_patches = 100.0
        elif patch_count >= weights['size_acceptable_min']:
            size_score_patches = 50.0 + 50.0 * (patch_count - weights['size_acceptable_min']) / \
                                (weights['size_optimal_min'] - weights['size_acceptable_min'])
        else:
            size_score_patches = max(0, 50.0 * (patch_count / weights['size_acceptable_min']))
        
        # Area-based size score
        if area_px >= weights['area_optimal_min_px']:
            size_score_area = 100.0
        elif area_px >= weights['area_acceptable_min_px']:
            size_score_area = 50.0 + 50.0 * (area_px - weights['area_acceptable_min_px']) / \
                             (weights['area_optimal_min_px'] - weights['area_acceptable_min_px'])
        else:
            size_score_area = max(0, 50.0 * (area_px / weights['area_acceptable_min_px']))
        
        # Use AVERAGE of patch-based and area-based scores (both must be large)
        # This prevents a few large patches from scoring as stain
        size_score = (size_score_patches + size_score_area) / 2.0
        
        # Brightness score (stains show color/brightness deviation)
        brightness_score = min(100.0, abs(brightness_delta) * 100.0)
        
        # Weighted total
        total_score = (size_score * weights['size_weight'] +
                      brightness_score * weights['brightness_weight'])
        
        reason = f"patches={patch_count}, area={area_px}px (avg_score={size_score:.0f}), brightness_Δ={brightness_delta:.2f} ({brightness_score:.0f})"
        return total_score, reason
    
    def score_hole(self, diag: Dict) -> Tuple[float, str]:
        """
        Compute hole score based on dark region, sharp edges, medium size.
        
        Args:
            diag: Diagnostic features dictionary
            
        Returns:
            Tuple of (score 0-100, reasoning string)
        """
        weights = self.scoring_weights['hole']
        patch_count = diag['patch_count']
        brightness_delta = diag['brightness_delta']
        edge_delta = diag['edge_density_delta']
        circularity = diag['circularity']
        
        # Size score (medium range)
        if weights['size_optimal_min'] <= patch_count <= weights['size_optimal_max']:
            size_score = 100.0
        elif patch_count < weights['size_optimal_min']:
            size_score = 50.0 * (patch_count / weights['size_optimal_min'])
        else:
            # Exponential decay for larger sizes
            size_score = max(0, 100.0 * (0.8 ** (patch_count - weights['size_optimal_max'])))
        
        # Brightness score (holes are dark - negative delta)
        if brightness_delta <= weights['brightness_dark_threshold']:
            brightness_score = 100.0
        elif brightness_delta < 0:
            # Between threshold and 0
            brightness_score = 50.0 + 50.0 * abs(brightness_delta) / abs(weights['brightness_dark_threshold'])
        else:
            # Positive (lighter) - not typical for holes
            brightness_score = max(0, 50.0 * (1.0 - brightness_delta))
        
        # Edge score (holes have sharp edges at boundary)
        if edge_delta >= weights['edge_high_threshold']:
            edge_score = 100.0
        elif edge_delta > 0:
            edge_score = 50.0 + 50.0 * (edge_delta / weights['edge_high_threshold'])
        else:
            edge_score = 50.0
        
        # Circularity score (holes are somewhat irregular)
        if circularity <= weights['circularity_irregular_max']:
            circ_score = 100.0
        else:
            circ_score = max(0, 100.0 * (1.0 - circularity))
        
        # Weighted total
        total_score = (brightness_score * weights['brightness_weight'] +
                      edge_score * weights['edge_weight'] +
                      size_score * weights['size_weight'] +
                      circ_score * weights['circularity_weight'])
        
        reason = f"patches={patch_count} ({size_score:.0f}), brightness={brightness_delta:.2f} ({brightness_score:.0f}), edge={edge_delta:.2f} ({edge_score:.0f})"
        return total_score, reason
    
    def classify_with_diagnostics(self, detection: Dict) -> Tuple[str, str, Dict]:
        """
        Classify a detected defect using weighted multi-feature scoring.
        
        NEW APPROACH: Computes a match score (0-100) for EVERY defect type based on
        how well the features match that type's characteristics. Classifies as the
        highest-scoring type, or "unclassified" if all scores are below minimum threshold.
        
        This replaces the old if/elif chain that defaulted to "Hole" for borderline cases.
        
        Args:
            detection: Detection dictionary with keys x, y, w, h, confidence
            
        Returns:
            Tuple of (defect_type, classification_reason, diagnostic_features)
        """
        # Compute all diagnostic features
        diag = self.compute_diagnostic_features(detection)
        
        # Score against ALL defect types
        scores = {}
        reasons = {}
        
        scores['broken_thread'], reasons['broken_thread'] = self.score_broken_thread(diag)
        scores['knot'], reasons['knot'] = self.score_knot(diag)
        scores['double_knot'], reasons['double_knot'] = self.score_double_knot(diag)
        scores['stain'], reasons['stain'] = self.score_stain(diag)
        scores['hole'], reasons['hole'] = self.score_hole(diag)
        
        # Find highest score
        best_type = max(scores, key=scores.get)
        best_score = scores[best_type]
        
        # Check if score meets minimum threshold
        if best_score < self.min_score:
            # All scores too low - don't default to Hole, be honest
            reason = (f"All scores below threshold (min={self.min_score:.0f}): "
                     f"broken_thread={scores['broken_thread']:.0f}, "
                     f"knot={scores['knot']:.0f}, "
                     f"double_knot={scores['double_knot']:.0f}, "
                     f"stain={scores['stain']:.0f}, "
                     f"hole={scores['hole']:.0f} → unclassified")
            return 'unclassified', reason, diag
        
        # Classify as best match
        reason = (f"{best_type.upper()} (score={best_score:.0f}): {reasons[best_type]} | "
                 f"Runners-up: " + ", ".join([f"{t}={scores[t]:.0f}" for t in sorted(scores, key=scores.get, reverse=True)[1:3]]))
        
        return best_type, reason, diag
    
    def classify(self, detection: Dict) -> str:
        """
        Classify a detected defect (legacy interface, returns only type).
        
        Args:
            detection: Detection dictionary with keys x, y, w, h, confidence
            
        Returns:
            Defect type string: 'hole', 'stain', 'knot', 'double_knot', 'broken_thread'
        """
        defect_type, _, _ = self.classify_with_diagnostics(detection)
        return defect_type
    
    def classify_batch(self, detections: List[Dict]) -> List[Dict]:
        """
        Classify a batch of detections and add diagnostic fields to each.
        
        This is the main entry point used by the detection pipeline.
        
        Args:
            detections: List of detection dictionaries
            
        Returns:
            List of detection dictionaries with added fields:
                - type: Defect type (or 'unclassified' if score too low)
                - classification_reason: Human-readable explanation with scores
                - diagnostic_*: All raw feature values
        """
        classified = []
        
        for detection in detections:
            defect_type, reason, diagnostics = self.classify_with_diagnostics(detection)
            
            # Create new dict with all diagnostic info added
            classified_detection = {
                **detection,
                'type': defect_type,
                'classification_reason': reason,
                # Add all diagnostic fields with diagnostic_ prefix
                'diagnostic_patch_count': diagnostics['patch_count'],
                'diagnostic_aspect_ratio': diagnostics['aspect_ratio'],
                'diagnostic_circularity': diagnostics['circularity'],
                'diagnostic_area_px': diagnostics['area_px'],
                'diagnostic_brightness_delta': diagnostics['brightness_delta'],
                'diagnostic_edge_density_delta': diagnostics['edge_density_delta'],
                'diagnostic_avg_anomaly_score': diagnostics['avg_anomaly_score']
            }
            classified.append(classified_detection)
        
        return classified
    
    @staticmethod
    def get_defect_color(defect_type: str) -> tuple:
        """
        Get color code for visualization based on defect type.
        
        Args:
            defect_type: Type of defect
            
        Returns:
            BGR color tuple
        """
        color_map = {
            'hole': (0, 0, 255),          # Red
            'stain': (0, 165, 255),       # Orange
            'knot': (0, 255, 0),          # Green
            'double_knot': (255, 255, 0), # Cyan
            'broken_thread': (255, 0, 255), # Magenta
            'unclassified': (128, 128, 128) # Gray
        }
        return color_map.get(defect_type, (255, 255, 255))  # White default
    
    @staticmethod
    def get_defect_display_name(defect_type: str) -> str:
        """
        Get human-readable display name for defect type.
        
        Args:
            defect_type: Type of defect
            
        Returns:
            Display name string
        """
        display_map = {
            'hole': 'Hole',
            'stain': 'Stain',
            'knot': 'Knot',
            'double_knot': 'Double Knot',
            'broken_thread': 'Broken Thread',
            'unclassified': 'Unclassified'
        }
        return display_map.get(defect_type, 'Unknown')


# Global classifier instance
_classifier_instance = None


def get_classifier() -> DefectClassifier:
    """
    Get or create the global classifier instance (singleton pattern).
    
    Returns:
        DefectClassifier instance
    """
    global _classifier_instance
    if _classifier_instance is None:
        _classifier_instance = DefectClassifier()
    return _classifier_instance


def classify_detections(detections: List[Dict]) -> List[Dict]:
    """
    Convenience function to classify detections using the global classifier.
    
    Args:
        detections: List of detection dictionaries
        
    Returns:
        List of classified detection dictionaries
    """
    classifier = get_classifier()
    return classifier.classify_batch(detections)


def draw_detections(image: np.ndarray, detections: List[Dict], 
                   show_labels: bool = True, 
                   show_confidence: bool = True) -> np.ndarray:
    """
    Draw bounding boxes and labels on an image.
    
    Args:
        image: Input image (will be copied, not modified)
        detections: List of detection dictionaries with 'type' field
        show_labels: Whether to show defect type labels
        show_confidence: Whether to show confidence scores
        
    Returns:
        Image with drawn bounding boxes and labels
    """
    output = image.copy()
    classifier = get_classifier()
    
    for detection in detections:
        x = detection['x']
        y = detection['y']
        w = detection['w']
        h = detection['h']
        confidence = detection.get('confidence', 0)
        defect_type = detection.get('type', 'unknown')
        
        # Get color for this defect type
        color = classifier.get_defect_color(defect_type)
        
        # Draw bounding box
        cv2.rectangle(output, (x, y), (x + w, y + h), color, 2)
        
        # Prepare label text
        label_parts = []
        if show_labels:
            display_name = classifier.get_defect_display_name(defect_type)
            label_parts.append(display_name)
        if show_confidence:
            label_parts.append(f"{confidence:.1f}%")
        
        if label_parts:
            label = " - ".join(label_parts)
            
            # Draw label background
            font = cv2.FONT_HERSHEY_SIMPLEX
            font_scale = 0.5
            thickness = 1
            (label_w, label_h), baseline = cv2.getTextSize(
                label, font, font_scale, thickness
            )
            
            # Position label above box (or below if at top of image)
            label_y = y - 10 if y > 30 else y + h + 20
            
            cv2.rectangle(
                output,
                (x, label_y - label_h - baseline),
                (x + label_w, label_y + baseline),
                color,
                -1
            )
            
            # Draw label text
            cv2.putText(
                output,
                label,
                (x, label_y - baseline),
                font,
                font_scale,
                (255, 255, 255),  # White text
                thickness,
                cv2.LINE_AA
            )
    
    return output


if __name__ == "__main__":
    # Test the classifier
    print("Testing DefectClassifier...")
    
    classifier = DefectClassifier()
    
    # Test cases
    test_detections = [
        {'x': 10, 'y': 10, 'w': 64, 'h': 64, 'confidence': 85.5},    # Square - likely knot
        {'x': 100, 'y': 10, 'w': 64, 'h': 256, 'confidence': 90.2},  # Elongated - broken thread
        {'x': 200, 'y': 10, 'w': 192, 'h': 192, 'confidence': 75.8}, # Large - stain
        {'x': 10, 'y': 300, 'w': 128, 'h': 128, 'confidence': 70.3}, # Medium - double knot or hole
        {'x': 200, 'y': 300, 'w': 96, 'h': 80, 'confidence': 65.1},  # Medium irregular - hole
    ]
    
    print("\nClassifying test detections:")
    for i, det in enumerate(test_detections):
        defect_type = classifier.classify(det)
        display_name = classifier.get_defect_display_name(defect_type)
        color = classifier.get_defect_color(defect_type)
        
        print(f"  {i+1}. Box: ({det['w']}x{det['h']}) → "
              f"Type: {display_name} (color: {color})")
    
    # Test batch classification
    classified = classifier.classify_batch(test_detections)
    print(f"\nBatch classified {len(classified)} detections")
    
    # Test visualization
    test_image = np.ones((400, 400, 3), dtype=np.uint8) * 200
    annotated = draw_detections(test_image, classified)
    print(f"Drew annotations on {annotated.shape} image")
    
    print("\nClassifier test complete!")
