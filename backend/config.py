"""
Configuration file for fabric defect detection system.
Contains all tunable parameters for detection, classification, and system behavior.
"""

import os
from pathlib import Path

# ============================================================================
# PATH CONFIGURATION
# ============================================================================

# Project root directory
PROJECT_ROOT = Path(__file__).parent.parent.absolute()

# Data directories
DATA_DIR = PROJECT_ROOT / "data"
CLEAN_FABRIC_DIR = DATA_DIR / "clean_fabric_videos"
PATCHES_DIR = DATA_DIR / "patches"
VALIDATION_PATCHES_DIR = DATA_DIR / "validation_patches"

# Model directory
MODELS_DIR = PROJECT_ROOT / "trained_models"
AUTOENCODER_PATH = MODELS_DIR / "autoencoder.pt"
THRESHOLD_STATS_PATH = MODELS_DIR / "threshold_stats.json"

# Database
DB_PATH = PROJECT_ROOT / "defect_log.db"

# Ensure directories exist
for directory in [DATA_DIR, CLEAN_FABRIC_DIR, PATCHES_DIR, 
                  VALIDATION_PATCHES_DIR, MODELS_DIR]:
    directory.mkdir(parents=True, exist_ok=True)

# ============================================================================
# PATCH EXTRACTION CONFIGURATION
# ============================================================================

# Patch size for training and inference (must be square)
PATCH_SIZE = 64

# Frame extraction interval for training data (seconds)
FRAME_INTERVAL = 0.5

# Train/validation split ratio
VALIDATION_SPLIT = 0.15

# ============================================================================
# AUTOENCODER MODEL CONFIGURATION
# ============================================================================

# Model architecture parameters
LATENT_DIM = 128  # Bottleneck dimension
INPUT_CHANNELS = 3  # RGB images

# Training hyperparameters
LEARNING_RATE = 0.001
BATCH_SIZE = 32
NUM_EPOCHS = 50
EARLY_STOPPING_PATIENCE = 10

# Loss function weights (if using combined MSE + SSIM)
MSE_WEIGHT = 0.7
SSIM_WEIGHT = 0.3

# ============================================================================
# INFERENCE & DETECTION CONFIGURATION
# ============================================================================

# Anomaly detection threshold
# Patches with reconstruction error > (mean + K_SIGMA * std) are flagged
K_SIGMA = 2.5

# Minimum confidence threshold to report a defect (0-100)
MIN_CONFIDENCE = 30.0

# Bounding box merging parameters
# Maximum distance between patches to merge them into one bounding box
MAX_MERGE_DISTANCE = 1.5  # In patch units (1.5 means patches 1.5x patch size apart can merge)

# Minimum number of flagged patches to form a valid defect region
MIN_PATCHES_PER_DEFECT = 1

# ============================================================================
# DEFECT CLASSIFICATION HEURISTICS
# ============================================================================

# Aspect ratio thresholds for broken thread detection
BROKEN_THREAD_ASPECT_RATIO_MIN = 2.4  # Very elongated (height >> width)
BROKEN_THREAD_ASPECT_RATIO_MAX = 0.42  # Very elongated (width >> height)

# Patch count thresholds for defect type classification
SMALL_DEFECT_MAX_PATCHES = 2  # Knot
MEDIUM_DEFECT_MAX_PATCHES = 5  # Double knot
# Anything larger is considered stain or hole based on shape

# Circularity threshold (4π*area/perimeter²)
# Close to 1.0 = circular, lower = irregular
KNOT_CIRCULARITY_THRESHOLD = 0.6

# ============================================================================
# CLASSIFICATION THRESHOLDS - TUNABLE DIAGNOSTIC CONFIG
# ============================================================================
# All thresholds in one place for easy tuning based on real data.
# Use the calibration script (training/calibrate_classifier.py) to find
# optimal values for your specific fabric types.

CLASSIFICATION_THRESHOLDS = {
    # Broken Thread Detection (very elongated shapes)
    "broken_thread_aspect_min": 2.4,    # Aspect ratio > this → broken thread (tall)
    "broken_thread_aspect_max": 0.42,   # Aspect ratio < this → broken thread (wide)
    
    # Knot Detection (small + circular)
    "knot_max_patches": 2,              # Must be ≤ this many patches
    "knot_min_circularity": 0.6,        # Must be ≥ this circular (0-1, 1=perfect circle)
    "knot_max_aspect_dev": 0.5,         # Aspect ratio should be near 1.0 ± this
    
    # Double Knot Detection (medium + circular)
    "double_knot_min_patches": 3,       # Must be ≥ this many patches
    "double_knot_max_patches": 5,       # Must be ≤ this many patches
    "double_knot_min_circularity": 0.6, # Must be ≥ this circular
    "double_knot_max_aspect_dev": 0.5,  # Aspect ratio should be near 1.0 ± this
    
    # Stain Detection (large + irregular OR large + circular)
    "stain_min_patches": 6,             # Must be > double_knot_max_patches
    "stain_min_area_px": 6000,          # Minimum area in pixels
    
    # Hole Detection (catch-all, but prefer medium size + irregular)
    "hole_max_patches": 5,              # Typically ≤ this
    "hole_min_patches": 1,              # At least 1 patch
    "hole_max_circularity": 0.7,        # Typically less circular than knots
    
    # General thresholds
    "min_confidence": 30.0,             # Overall minimum confidence to report
    "brightness_weight": 0.4,           # Weight for brightness score in confidence
    "edge_weight": 0.3,                 # Weight for edge score in confidence
    "size_weight": 0.3,                 # Weight for size score in confidence
}

# ============================================================================
# WEIGHTED SCORING CONFIGURATION
# ============================================================================
# Scoring weights for multi-feature classification.
# Each defect type gets a score (0-100) based on how well the features match.
# The type with the highest score wins, unless all scores are below min_classification_score.

SCORING_WEIGHTS = {
    # Minimum score required to classify (prevents labeling unclear detections)
    "min_classification_score": 40.0,  # Below this → "unclassified"
    
    # Broken Thread Scoring Weights
    "broken_thread": {
        "aspect_weight": 0.8,           # Elongation is the strongest signal (increased from 0.7)
        "edge_weight": 0.1,             # Frayed edges support broken thread (decreased from 0.2)
        "size_weight": 0.1,             # Size matters less but penalize very large
        # Scoring curves (adjust based on calibration data)
        "aspect_optimal_high": 3.0,     # Perfect score at aspect > this
        "aspect_optimal_low": 0.35,     # Perfect score at aspect < this
        "aspect_moderate_high": 1.8,    # Moderate score at aspect > this
        "aspect_moderate_low": 0.55,    # Moderate score at aspect < this
        "size_penalize_above": 8,       # Penalize if patches > this (stain territory)
    },
    
    # Knot Scoring Weights
    "knot": {
        "size_weight": 0.4,             # Small size is key
        "circularity_weight": 0.4,      # Roundness is key
        "aspect_weight": 0.2,           # Should be square-ish
        # Scoring curves
        "size_optimal_max": 2,          # Perfect score if patches ≤ this
        "size_acceptable_max": 3,       # Moderate score if patches ≤ this
        "circularity_optimal_min": 0.7, # Perfect score if circ ≥ this
        "circularity_acceptable_min": 0.5, # Moderate score if circ ≥ this
        "aspect_dev_optimal": 0.3,      # Perfect score if |aspect-1| ≤ this
        "aspect_dev_acceptable": 0.6,   # Moderate score if |aspect-1| ≤ this
    },
    
    # Double Knot Scoring Weights
    "double_knot": {
        "size_weight": 0.5,             # Size range is most distinctive
        "circularity_weight": 0.3,      # Still somewhat round
        "aspect_weight": 0.2,           # Should be roughly square
        # Scoring curves
        "size_optimal_min": 3,          # Perfect score if patches ≥ this
        "size_optimal_max": 4,          # Perfect score if patches ≤ this
        "size_acceptable_min": 2,       # Moderate score if patches ≥ this (single tight cluster)
        "size_acceptable_max": 4,       # Moderate score if patches ≤ this (FIXED: no overlap with stain min=5)
        "circularity_optimal_min": 0.6,
        "circularity_acceptable_min": 0.4,
        "aspect_dev_optimal": 0.4,
        "aspect_dev_acceptable": 0.7,
    },
    
    # Stain Scoring Weights
    "stain": {
        "size_weight": 0.85,            # Large size is the main signal (INCREASED from 0.7 to dominate even with brightness_delta=0)
        "brightness_weight": 0.10,      # Discoloration matters but reduced since detector doesn't compute it reliably (REDUCED from 0.2)
        "circularity_weight": 0.05,     # Shape is less important (REDUCED from 0.1)
        # Scoring curves
        "size_optimal_min": 6,          # Perfect score if patches ≥ this (FIXED: clear gap after double_knot max=4)
        "size_acceptable_min": 5,       # Moderate score if patches ≥ this (FIXED: no overlap with double_knot max=4)
        "area_optimal_min_px": 8000,    # Perfect score if area ≥ this
        "area_acceptable_min_px": 5000, # Moderate score if area ≥ this
    },
    
    # Hole Scoring Weights
    "hole": {
        "brightness_weight": 0.4,       # Dark region (negative brightness)
        "edge_weight": 0.3,             # Sharp edge around gap
        "size_weight": 0.2,             # Medium size
        "circularity_weight": 0.1,      # Somewhat irregular
        # Scoring curves
        "size_optimal_min": 2,          # Perfect score if patches ≥ this
        "size_optimal_max": 5,          # Perfect score if patches ≤ this
        "brightness_dark_threshold": -0.3, # Score higher if darker than this
        "edge_high_threshold": 0.5,     # Score higher if edge delta > this
        "circularity_irregular_max": 0.6, # Score higher if less circular
    }
}

# ============================================================================
# FALLBACK HEURISTIC DETECTOR (OpenCV-based)
# ============================================================================

# Brightness z-score threshold for anomaly
FALLBACK_BRIGHTNESS_THRESHOLD = 2.5

# Edge density z-score threshold for anomaly
FALLBACK_EDGE_THRESHOLD = 2.0

# Combine brightness and edge scores with these weights
FALLBACK_BRIGHTNESS_WEIGHT = 0.5
FALLBACK_EDGE_WEIGHT = 0.5

# ============================================================================
# LENGTH TRACKING CONFIGURATION
# ============================================================================

# Default feed speed (meters per minute)
# User can override this via the API
DEFAULT_FEED_SPEED = 10.0  # m/min

# ============================================================================
# API & SERVER CONFIGURATION
# ============================================================================

# Server host and port
API_HOST = "0.0.0.0"
API_PORT = 8000

# Maximum file upload size (bytes)
MAX_UPLOAD_SIZE = 500 * 1024 * 1024  # 500 MB

# Video processing settings
VIDEO_PROCESSING_FPS = 10  # Process every Nth frame for performance
WEBSOCKET_FRAME_SKIP = 2  # Send every Nth processed frame over WebSocket

# ============================================================================
# RUNTIME STATE (can be updated via API)
# ============================================================================

class RuntimeConfig:
    """
    Mutable runtime configuration that can be updated via API endpoints.
    
    IMPORTANT LIMITATION - Feed Speed Assumption:
    The feed_speed parameter assumes CONSTANT speed throughout video processing.
    Real-world fabric manufacturing may have variable speeds (start/stop, acceleration).
    Without a physical encoder/sensor, software cannot detect these variations.
    Length estimates are only as accurate as this constant-speed assumption.
    """
    def __init__(self):
        self.k_sigma = K_SIGMA
        self.feed_speed = DEFAULT_FEED_SPEED
        self.min_confidence = MIN_CONFIDENCE
    
    def update(self, k_sigma=None, feed_speed=None, min_confidence=None):
        """
        Update runtime configuration parameters with validation.
        
        Args:
            k_sigma: Anomaly threshold multiplier (0.5-10.0)
            feed_speed: Feed speed in m/min (must be positive, max 1000 m/min)
            min_confidence: Minimum confidence percentage (0-100)
            
        Raises:
            ValueError: If any parameter is invalid
        """
        if k_sigma is not None:
            k_sigma = float(k_sigma)
            if k_sigma <= 0:
                raise ValueError("k_sigma must be positive")
            self.k_sigma = k_sigma
            
        if feed_speed is not None:
            feed_speed = float(feed_speed)
            if feed_speed <= 0:
                raise ValueError("Feed speed must be positive (cannot be zero or negative)")
            if feed_speed > 1000:
                raise ValueError("Feed speed exceeds reasonable limit (max 1000 m/min for fabric manufacturing)")
            self.feed_speed = feed_speed
            
        if min_confidence is not None:
            min_confidence = float(min_confidence)
            if min_confidence < 0 or min_confidence > 100:
                raise ValueError("Min confidence must be between 0 and 100")
            self.min_confidence = min_confidence
    
    def to_dict(self):
        """Return current configuration as dictionary."""
        return {
            "k_sigma": self.k_sigma,
            "feed_speed": self.feed_speed,
            "min_confidence": self.min_confidence
        }

# Global runtime config instance
runtime_config = RuntimeConfig()
