"""
Patch Extraction Pipeline for Training Data Generation

This script extracts fixed-size patches from clean fabric videos or images
to create a training dataset for the autoencoder. Only clean (defect-free)
fabric should be used as input.

Usage:
    python training/extract_patches.py --input data/clean_fabric_videos/sample.mp4
    python training/extract_patches.py --input data/clean_fabric_videos/ --patch-size 64 --interval 0.5
"""

import argparse
import cv2
import numpy as np
from pathlib import Path
from tqdm import tqdm
import json
import sys
import os

# Add backend to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from config import (
    PATCH_SIZE,
    FRAME_INTERVAL,
    PATCHES_DIR,
    VALIDATION_PATCHES_DIR,
    VALIDATION_SPLIT,
    CLEAN_FABRIC_DIR
)


class PatchExtractor:
    """
    Extracts fixed-size patches from video frames or images for training.
    """
    
    def __init__(self, patch_size=PATCH_SIZE, frame_interval=FRAME_INTERVAL,
                 validation_split=VALIDATION_SPLIT):
        """
        Initialize the patch extractor.
        
        Args:
            patch_size: Size of square patches to extract (default from config)
            frame_interval: Time interval between frames in seconds (video only)
            validation_split: Fraction of patches to reserve for validation
        """
        self.patch_size = patch_size
        self.frame_interval = frame_interval
        self.validation_split = validation_split
        
        # Statistics tracking
        self.total_frames = 0
        self.total_patches = 0
        self.train_patches = 0
        self.val_patches = 0
    
    def extract_patches_from_frame(self, frame):
        """
        Split a single frame into a grid of non-overlapping patches.
        
        Args:
            frame: BGR image (numpy array)
            
        Returns:
            List of patch images (numpy arrays)
        """
        height, width = frame.shape[:2]
        patches = []
        
        # Calculate how many complete patches fit in each dimension
        num_patches_h = height // self.patch_size
        num_patches_w = width // self.patch_size
        
        # Extract patches in a grid pattern
        for i in range(num_patches_h):
            for j in range(num_patches_w):
                y_start = i * self.patch_size
                x_start = j * self.patch_size
                
                patch = frame[
                    y_start:y_start + self.patch_size,
                    x_start:x_start + self.patch_size
                ]
                
                # Only keep patches that are exactly the right size
                if patch.shape[0] == self.patch_size and patch.shape[1] == self.patch_size:
                    patches.append(patch)
        
        return patches
    
    def process_video(self, video_path, output_train_dir, output_val_dir):
        """
        Extract patches from a video file at specified intervals.
        
        Args:
            video_path: Path to video file
            output_train_dir: Directory to save training patches
            output_val_dir: Directory to save validation patches
            
        Returns:
            Number of patches extracted
        """
        print(f"\nProcessing video: {video_path}")
        
        cap = cv2.VideoCapture(str(video_path))
        if not cap.isOpened():
            print(f"Error: Could not open video {video_path}")
            return 0
        
        # Get video properties
        fps = cap.get(cv2.CAP_PROP_FPS)
        total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        duration = total_frames / fps if fps > 0 else 0
        
        print(f"  FPS: {fps:.2f}, Total frames: {total_frames}, Duration: {duration:.2f}s")
        
        # Calculate frame interval in frame numbers
        frame_interval_frames = int(fps * self.frame_interval)
        if frame_interval_frames < 1:
            frame_interval_frames = 1
        
        frame_count = 0
        extracted_count = 0
        
        # Progress bar for video processing
        pbar = tqdm(total=total_frames, desc="  Extracting frames", unit="frame")
        
        while True:
            ret, frame = cap.read()
            if not ret:
                break
            
            # Extract patches from this frame if it's at the right interval
            if frame_count % frame_interval_frames == 0:
                patches = self.extract_patches_from_frame(frame)
                
                # Save patches
                for patch in patches:
                    # Randomly assign to train or validation set
                    is_validation = np.random.random() < self.validation_split
                    
                    if is_validation:
                        output_dir = output_val_dir
                        self.val_patches += 1
                    else:
                        output_dir = output_train_dir
                        self.train_patches += 1
                    
                    # Generate unique filename
                    filename = f"patch_{self.total_patches:06d}.png"
                    filepath = output_dir / filename
                    
                    cv2.imwrite(str(filepath), patch)
                    self.total_patches += 1
                    extracted_count += 1
                
                self.total_frames += 1
            
            frame_count += 1
            pbar.update(1)
        
        pbar.close()
        cap.release()
        
        print(f"  Extracted {extracted_count} patches from {self.total_frames} frames")
        return extracted_count
    
    def process_image(self, image_path, output_train_dir, output_val_dir):
        """
        Extract patches from a single image file.
        
        Args:
            image_path: Path to image file
            output_train_dir: Directory to save training patches
            output_val_dir: Directory to save validation patches
            
        Returns:
            Number of patches extracted
        """
        print(f"\nProcessing image: {image_path}")
        
        frame = cv2.imread(str(image_path))
        if frame is None:
            print(f"Error: Could not read image {image_path}")
            return 0
        
        patches = self.extract_patches_from_frame(frame)
        
        # Save patches
        extracted_count = 0
        for patch in patches:
            # Randomly assign to train or validation set
            is_validation = np.random.random() < self.validation_split
            
            if is_validation:
                output_dir = output_val_dir
                self.val_patches += 1
            else:
                output_dir = output_train_dir
                self.train_patches += 1
            
            # Generate unique filename
            filename = f"patch_{self.total_patches:06d}.png"
            filepath = output_dir / filename
            
            cv2.imwrite(str(filepath), patch)
            self.total_patches += 1
            extracted_count += 1
        
        self.total_frames += 1
        print(f"  Extracted {extracted_count} patches")
        return extracted_count
    
    def process_directory(self, input_dir, output_train_dir, output_val_dir):
        """
        Process all videos and images in a directory.
        
        Args:
            input_dir: Directory containing videos/images
            output_train_dir: Directory to save training patches
            output_val_dir: Directory to save validation patches
            
        Returns:
            Total number of patches extracted
        """
        input_path = Path(input_dir)
        
        # Supported file extensions
        video_extensions = ['.mp4', '.avi', '.mov', '.mkv', '.flv', '.wmv']
        image_extensions = ['.jpg', '.jpeg', '.png', '.bmp', '.tiff']
        
        # Find all media files
        video_files = []
        image_files = []
        
        for ext in video_extensions:
            video_files.extend(input_path.glob(f"*{ext}"))
            video_files.extend(input_path.glob(f"*{ext.upper()}"))
        
        for ext in image_extensions:
            image_files.extend(input_path.glob(f"*{ext}"))
            image_files.extend(input_path.glob(f"*{ext.upper()}"))
        
        total_files = len(video_files) + len(image_files)
        
        if total_files == 0:
            print(f"No media files found in {input_dir}")
            return 0
        
        print(f"\nFound {len(video_files)} video(s) and {len(image_files)} image(s)")
        
        # Process videos
        for video_file in video_files:
            self.process_video(video_file, output_train_dir, output_val_dir)
        
        # Process images
        for image_file in image_files:
            self.process_image(image_file, output_train_dir, output_val_dir)
        
        return self.total_patches
    
    def save_metadata(self, output_dir):
        """
        Save extraction metadata for reference.
        
        Args:
            output_dir: Directory to save metadata file
        """
        metadata = {
            "patch_size": self.patch_size,
            "frame_interval": self.frame_interval,
            "validation_split": self.validation_split,
            "total_frames_processed": self.total_frames,
            "total_patches": self.total_patches,
            "train_patches": self.train_patches,
            "validation_patches": self.val_patches
        }
        
        metadata_path = output_dir / "extraction_metadata.json"
        with open(metadata_path, 'w') as f:
            json.dump(metadata, f, indent=2)
        
        print(f"\nMetadata saved to {metadata_path}")


def main():
    parser = argparse.ArgumentParser(
        description="Extract training patches from clean fabric videos or images"
    )
    
    parser.add_argument(
        "--input",
        type=str,
        required=True,
        help="Input video file, image file, or directory containing media files"
    )
    
    parser.add_argument(
        "--patch-size",
        type=int,
        default=PATCH_SIZE,
        help=f"Size of square patches to extract (default: {PATCH_SIZE})"
    )
    
    parser.add_argument(
        "--interval",
        type=float,
        default=FRAME_INTERVAL,
        help=f"Frame extraction interval in seconds for videos (default: {FRAME_INTERVAL})"
    )
    
    parser.add_argument(
        "--output-train",
        type=str,
        default=str(PATCHES_DIR),
        help="Output directory for training patches"
    )
    
    parser.add_argument(
        "--output-val",
        type=str,
        default=str(VALIDATION_PATCHES_DIR),
        help="Output directory for validation patches"
    )
    
    parser.add_argument(
        "--validation-split",
        type=float,
        default=VALIDATION_SPLIT,
        help=f"Fraction of patches to use for validation (default: {VALIDATION_SPLIT})"
    )
    
    parser.add_argument(
        "--clear",
        action="store_true",
        help="Clear existing patches before extraction"
    )
    
    args = parser.parse_args()
    
    # Create output directories
    output_train_dir = Path(args.output_train)
    output_val_dir = Path(args.output_val)
    output_train_dir.mkdir(parents=True, exist_ok=True)
    output_val_dir.mkdir(parents=True, exist_ok=True)
    
    # Clear existing patches if requested
    if args.clear:
        print("Clearing existing patches...")
        for patch_file in output_train_dir.glob("patch_*.png"):
            patch_file.unlink()
        for patch_file in output_val_dir.glob("patch_*.png"):
            patch_file.unlink()
        print("Existing patches cleared.")
    
    # Initialize extractor
    extractor = PatchExtractor(
        patch_size=args.patch_size,
        frame_interval=args.interval,
        validation_split=args.validation_split
    )
    
    print("=" * 60)
    print("Fabric Defect Detection - Patch Extraction Pipeline")
    print("=" * 60)
    print(f"Patch size: {args.patch_size}x{args.patch_size}")
    print(f"Frame interval: {args.interval}s (videos only)")
    print(f"Validation split: {args.validation_split * 100:.1f}%")
    print(f"Output (train): {output_train_dir}")
    print(f"Output (validation): {output_val_dir}")
    
    # Determine input type and process
    input_path = Path(args.input)
    
    if not input_path.exists():
        print(f"\nError: Input path does not exist: {args.input}")
        sys.exit(1)
    
    if input_path.is_file():
        # Single file (video or image)
        if input_path.suffix.lower() in ['.mp4', '.avi', '.mov', '.mkv', '.flv', '.wmv']:
            extractor.process_video(input_path, output_train_dir, output_val_dir)
        elif input_path.suffix.lower() in ['.jpg', '.jpeg', '.png', '.bmp', '.tiff']:
            extractor.process_image(input_path, output_train_dir, output_val_dir)
        else:
            print(f"\nError: Unsupported file format: {input_path.suffix}")
            sys.exit(1)
    elif input_path.is_dir():
        # Directory containing multiple files
        extractor.process_directory(input_path, output_train_dir, output_val_dir)
    else:
        print(f"\nError: Invalid input path: {args.input}")
        sys.exit(1)
    
    # Print summary
    print("\n" + "=" * 60)
    print("EXTRACTION COMPLETE")
    print("=" * 60)
    print(f"Total frames processed: {extractor.total_frames}")
    print(f"Total patches extracted: {extractor.total_patches}")
    print(f"  Training patches: {extractor.train_patches}")
    print(f"  Validation patches: {extractor.val_patches}")
    
    # Save metadata
    extractor.save_metadata(output_train_dir.parent)
    
    print("\nPatches are ready for training!")
    print("Next step: Run the training script to train the autoencoder model.")


if __name__ == "__main__":
    main()
