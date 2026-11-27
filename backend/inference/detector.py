"""
Defect Detection Engine - Core Inference Module

This module performs defect detection on fabric images using either:
1. Trained autoencoder model (primary method)
2. OpenCV-based heuristic fallback (when no trained model exists)

The detector splits images into patches, computes anomaly scores,
flags anomalous patches, and merges them into bounding boxes.
"""

import json
import numpy as np
import cv2
import torch
from pathlib import Path
from typing import List, Tuple, Dict, Optional
import sys

# Add backend to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from config import (
    PATCH_SIZE,
    AUTOENCODER_PATH,
    THRESHOLD_STATS_PATH,
    LATENT_DIM,
    INPUT_CHANNELS,
    MAX_MERGE_DISTANCE,
    MIN_PATCHES_PER_DEFECT,
    FALLBACK_BRIGHTNESS_THRESHOLD,
    FALLBACK_EDGE_THRESHOLD,
    FALLBACK_BRIGHTNESS_WEIGHT,
    FALLBACK_EDGE_WEIGHT,
    runtime_config
)
from models.autoencoder import create_autoencoder


class DefectDetector:
    """
    Core defect detection engine with autoencoder and fallback modes.
    """
    
    def __init__(self, device=None):
        """
        Initialize the detector.
        
        Args:
            device: PyTorch device (cpu/cuda/mps). Auto-detect if None.
        """
        # Device selection
        if device is None:
            if torch.cuda.is_available():
                device = torch.device('cuda')
            elif torch.backends.mps.is_available():
                device = torch.device('mps')
            else:
                device = torch.device('cpu')
        
        self.device = device
        self.mode = None  # Will be 'autoencoder' or 'heuristic_fallback'
        
        # Try to load trained model
        self.model = None
        self.threshold_stats = None
        
        if AUTOENCODER_PATH.exists() and THRESHOLD_STATS_PATH.exists():
            try:
                self._load_autoencoder()
                self.mode = 'autoencoder'
                print(f"[Detector] Loaded autoencoder model (device: {self.device})")
            except Exception as e:
                print(f"[Detector] Failed to load autoencoder: {e}")
                print("[Detector] Falling back to heuristic mode")
                self.mode = 'heuristic_fallback'
        else:
            print("[Detector] No trained model found. Using heuristic fallback mode.")
            self.mode = 'heuristic_fallback'
    
    def _load_autoencoder(self):
        """Load trained autoencoder model and threshold statistics."""
        # Load model
        self.model = create_autoencoder(
            input_channels=INPUT_CHANNELS,
            latent_dim=LATENT_DIM,
            patch_size=PATCH_SIZE
        )
        
        checkpoint = torch.load(AUTOENCODER_PATH, map_location=self.device)
        self.model.load_state_dict(checkpoint['model_state_dict'])
        self.model.to(self.device)
        self.model.eval()
        
        # Load threshold statistics
        with open(THRESHOLD_STATS_PATH, 'r') as f:
            self.threshold_stats = json.load(f)
    
    def extract_patches(self, image: np.ndarray) -> Tuple[List[np.ndarray], List[Tuple[int, int]]]:
        """
        Split image into a grid of non-overlapping patches.
        
        Args:
            image: Input image (BGR format)
            
        Returns:
            Tuple of (patches, positions)
            - patches: List of patch images
            - positions: List of (row, col) grid positions for each patch
        """
        height, width = image.shape[:2]
        
        # Calculate grid dimensions
        num_patches_h = height // PATCH_SIZE
        num_patches_w = width // PATCH_SIZE
        
        patches = []
        positions = []
        
        for i in range(num_patches_h):
            for j in range(num_patches_w):
                y_start = i * PATCH_SIZE
                x_start = j * PATCH_SIZE
                
                patch = image[
                    y_start:y_start + PATCH_SIZE,
                    x_start:x_start + PATCH_SIZE
                ]
                
                if patch.shape[0] == PATCH_SIZE and patch.shape[1] == PATCH_SIZE:
                    patches.append(patch)
                    positions.append((i, j))
        
        return patches, positions
    
    def compute_autoencoder_scores(self, patches: List[np.ndarray]) -> np.ndarray:
        """
        Compute anomaly scores using the trained autoencoder.
        
        Args:
            patches: List of patch images (BGR format)
            
        Returns:
            Array of reconstruction error scores
        """
        if self.model is None:
            raise RuntimeError("Autoencoder model not loaded")
        
        # Convert patches to tensors
        patch_tensors = []
        for patch in patches:
            # Convert BGR to RGB and normalize to [0, 1]
            patch_rgb = cv2.cvtColor(patch, cv2.COLOR_BGR2RGB)
            patch_tensor = torch.from_numpy(patch_rgb).float() / 255.0
            # Reorder to CHW format
            patch_tensor = patch_tensor.permute(2, 0, 1)
            patch_tensors.append(patch_tensor)
        
        # Stack into batch
        batch = torch.stack(patch_tensors).to(self.device)
        
        # Compute reconstruction errors
        with torch.no_grad():
            errors = self.model.get_reconstruction_error(batch, reduction='none')
        
        return errors.cpu().numpy()
    
    def compute_heuristic_scores(self, patches: List[np.ndarray]) -> np.ndarray:
        """
        Compute anomaly scores using OpenCV heuristics (fallback mode).
        
        This uses brightness and edge density deviations from the mean.
        
        Args:
            patches: List of patch images (BGR format)
            
        Returns:
            Array of anomaly scores
        """
        # Compute brightness and edge features for all patches
        brightness_values = []
        edge_densities = []
        
        for patch in patches:
            # Brightness: mean intensity
            gray = cv2.cvtColor(patch, cv2.COLOR_BGR2GRAY)
            brightness = np.mean(gray)
            brightness_values.append(brightness)
            
            # Edge density: ratio of edge pixels to total pixels
            edges = cv2.Canny(gray, 50, 150)
            edge_density = np.sum(edges > 0) / edges.size
            edge_densities.append(edge_density)
        
        brightness_values = np.array(brightness_values)
        edge_densities = np.array(edge_densities)
        
        # Compute z-scores (standardized deviations from mean)
        brightness_mean = np.mean(brightness_values)
        brightness_std = np.std(brightness_values)
        
        edge_mean = np.mean(edge_densities)
        edge_std = np.std(edge_densities)
        
        # Avoid division by zero
        if brightness_std < 1e-6:
            brightness_std = 1.0
        if edge_std < 1e-6:
            edge_std = 1.0
        
        # Compute z-scores (absolute deviation)
        brightness_z = np.abs((brightness_values - brightness_mean) / brightness_std)
        edge_z = np.abs((edge_densities - edge_mean) / edge_std)
        
        # Combined anomaly score (weighted sum)
        scores = (FALLBACK_BRIGHTNESS_WEIGHT * brightness_z + 
                 FALLBACK_EDGE_WEIGHT * edge_z)
        
        return scores
    
    def flag_anomalous_patches(self, scores: np.ndarray) -> np.ndarray:
        """
        Flag patches as anomalous based on scores and threshold.
        
        Args:
            scores: Array of anomaly scores
            
        Returns:
            Boolean array indicating which patches are anomalous
        """
        if self.mode == 'autoencoder':
            # Use statistical threshold from training
            mean = self.threshold_stats['mean']
            std = self.threshold_stats['std']
            threshold = mean + runtime_config.k_sigma * std
        else:
            # Use fixed threshold for heuristic mode
            threshold = max(FALLBACK_BRIGHTNESS_THRESHOLD, FALLBACK_EDGE_THRESHOLD)
        
        return scores > threshold
    
    def merge_patches_to_boxes(self, flagged_positions: List[Tuple[int, int]], 
                               scores: np.ndarray,
                               all_patches: List[np.ndarray],
                               all_positions: List[Tuple[int, int]]) -> List[Dict]:
        """
        Merge adjacent flagged patches into bounding boxes using flood fill.
        
        Args:
            flagged_positions: List of (row, col) positions of flagged patches
            scores: Array of all patch scores (for computing confidence)
            all_patches: List of all patches (for computing brightness/edge stats)
            all_positions: List of all patch positions
            
        Returns:
            List of bounding box dictionaries with keys:
                - x, y, w, h: Box coordinates in pixels
                - grid_positions: List of (row, col) patch positions in this box
                - avg_score: Average anomaly score
                - brightness_delta: Brightness deviation from mean
                - edge_delta: Edge density deviation from mean
        """
        if len(flagged_positions) == 0:
            return []
        
        # Compute global brightness and edge statistics for reference
        brightness_values = []
        edge_values = []
        
        for patch in all_patches:
            gray = cv2.cvtColor(patch, cv2.COLOR_BGR2GRAY)
            brightness = np.mean(gray) / 255.0  # Normalize to [0, 1]
            brightness_values.append(brightness)
            
            edges = cv2.Canny(gray, 50, 150)
            edge_density = np.sum(edges > 0) / edges.size
            edge_values.append(edge_density)
        
        global_brightness_mean = np.mean(brightness_values)
        global_edge_mean = np.mean(edge_values)
        
        # Create a grid to track which patches have been visited
        max_row = max(pos[0] for pos in flagged_positions) + 1
        max_col = max(pos[1] for pos in flagged_positions) + 1
        
        grid = np.zeros((max_row, max_col), dtype=bool)
        for row, col in flagged_positions:
            grid[row, col] = True
        
        visited = np.zeros_like(grid, dtype=bool)
        boxes = []
        
        # Flood fill to find connected components
        def flood_fill(start_row, start_col):
            """Flood fill to find all connected flagged patches."""
            stack = [(start_row, start_col)]
            component = []
            
            while stack:
                row, col = stack.pop()
                
                if (row < 0 or row >= max_row or 
                    col < 0 or col >= max_col or
                    visited[row, col] or not grid[row, col]):
                    continue
                
                visited[row, col] = True
                component.append((row, col))
                
                # Check 8-connected neighbors (including diagonals)
                for dr in [-1, 0, 1]:
                    for dc in [-1, 0, 1]:
                        if dr == 0 and dc == 0:
                            continue
                        stack.append((row + dr, col + dc))
            
            return component
        
        # Find all connected components
        for row, col in flagged_positions:
            if not visited[row, col]:
                component = flood_fill(row, col)
                
                # Only keep components with minimum patch count
                if len(component) >= MIN_PATCHES_PER_DEFECT:
                    # Compute bounding box
                    rows = [pos[0] for pos in component]
                    cols = [pos[1] for pos in component]
                    
                    min_row, max_row = min(rows), max(rows)
                    min_col, max_col = min(cols), max(cols)
                    
                    # Convert to pixel coordinates
                    x = min_col * PATCH_SIZE
                    y = min_row * PATCH_SIZE
                    w = (max_col - min_col + 1) * PATCH_SIZE
                    h = (max_row - min_row + 1) * PATCH_SIZE
                    
                    # Compute average score for this box
                    box_indices = [all_positions.index(pos) for pos in component]
                    avg_score = np.mean([scores[idx] for idx in box_indices])
                    
                    # Compute average brightness and edge density for THIS defect region
                    region_brightness = np.mean([brightness_values[idx] for idx in box_indices])
                    region_edge = np.mean([edge_values[idx] for idx in box_indices])
                    
                    # Compute deltas (deviation from global mean)
                    brightness_delta = region_brightness - global_brightness_mean
                    edge_delta = region_edge - global_edge_mean
                    
                    boxes.append({
                        'x': int(x),
                        'y': int(y),
                        'w': int(w),
                        'h': int(h),
                        'grid_positions': component,
                        'avg_score': float(avg_score),
                        'brightness_delta': float(brightness_delta),
                        'edge_delta': float(edge_delta)
                    })
        
        return boxes
    
    def compute_confidence(self, avg_score: float) -> float:
        """
        Convert anomaly score to confidence percentage (0-100).
        
        Args:
            avg_score: Average anomaly score for a defect region
            
        Returns:
            Confidence score in range [0, 100]
        """
        if self.mode == 'autoencoder':
            # Normalize based on how far above threshold
            mean = self.threshold_stats['mean']
            std = self.threshold_stats['std']
            threshold = mean + runtime_config.k_sigma * std
            
            # Linear scaling: threshold = 0%, 2*threshold = 100%
            if avg_score <= threshold:
                return 0.0
            
            confidence = ((avg_score - threshold) / threshold) * 100
            confidence = min(confidence, 100.0)
            
        else:
            # Heuristic mode: simpler scaling
            threshold = max(FALLBACK_BRIGHTNESS_THRESHOLD, FALLBACK_EDGE_THRESHOLD)
            confidence = ((avg_score / threshold) - 1.0) * 100
            confidence = max(0.0, min(confidence, 100.0))
        
        return confidence
    
    def detect(self, image: np.ndarray) -> List[Dict]:
        """
        Detect defects in an image.
        
        Args:
            image: Input image (BGR format)
            
        Returns:
            List of defect dictionaries with keys:
                - x, y, w, h: Bounding box coordinates
                - confidence: Confidence score (0-100)
                - mode: Detection mode used ('autoencoder' or 'heuristic_fallback')
        """
        # Extract patches
        patches, positions = self.extract_patches(image)
        
        if len(patches) == 0:
            return []
        
        # Compute anomaly scores
        if self.mode == 'autoencoder':
            scores = self.compute_autoencoder_scores(patches)
        else:
            scores = self.compute_heuristic_scores(patches)
        
        # Flag anomalous patches
        is_anomalous = self.flag_anomalous_patches(scores)
        
        # Get positions of flagged patches
        flagged_positions = [pos for i, pos in enumerate(positions) if is_anomalous[i]]
        flagged_scores = scores[is_anomalous]
        
        if len(flagged_positions) == 0:
            return []
        
        # Merge into bounding boxes
        boxes = self.merge_patches_to_boxes(flagged_positions, scores, patches, positions)
        
        # Convert to output format
        detections = []
        for box in boxes:
            confidence = self.compute_confidence(box['avg_score'])
            
            # Apply minimum confidence threshold
            if confidence >= runtime_config.min_confidence:
                detections.append({
                    'x': box['x'],
                    'y': box['y'],
                    'w': box['w'],
                    'h': box['h'],
                    'confidence': round(confidence, 2),
                    'mode': self.mode,
                    'brightness_delta': round(box['brightness_delta'], 3),
                    'edge_delta': round(box['edge_delta'], 3),
                    'avg_score': round(box['avg_score'], 3)
                })
        
        return detections


# Global detector instance (initialized on first use)
_detector_instance = None


def get_detector() -> DefectDetector:
    """
    Get or create the global detector instance (singleton pattern).
    
    Returns:
        DefectDetector instance
    """
    global _detector_instance
    if _detector_instance is None:
        _detector_instance = DefectDetector()
    return _detector_instance


if __name__ == "__main__":
    # Test the detector
    print("Testing DefectDetector...")
    
    detector = DefectDetector()
    print(f"Detector mode: {detector.mode}")
    
    # Create a test image
    test_image = np.random.randint(0, 255, (512, 512, 3), dtype=np.uint8)
    
    # Add a simulated defect (bright spot)
    cv2.rectangle(test_image, (200, 200), (250, 250), (255, 255, 255), -1)
    
    print(f"\nRunning detection on test image...")
    detections = detector.detect(test_image)
    
    print(f"Found {len(detections)} defect(s):")
    for i, det in enumerate(detections):
        print(f"  {i+1}. Box: ({det['x']}, {det['y']}, {det['w']}, {det['h']}), "
              f"Confidence: {det['confidence']:.2f}%, Mode: {det['mode']}")
    
    print("\nDetector test complete!")
