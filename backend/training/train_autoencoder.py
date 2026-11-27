"""
Training Script for Fabric Defect Detection Autoencoder

This script trains the convolutional autoencoder on clean fabric patches
and computes threshold statistics for anomaly detection during inference.

Usage:
    python training/train_autoencoder.py
    python training/train_autoencoder.py --epochs 100 --batch-size 64 --lr 0.0001
"""

import argparse
import json
import sys
from pathlib import Path
import numpy as np
from tqdm import tqdm

import torch
import torch.nn as nn
import torch.optim as optim
from torch.utils.data import Dataset, DataLoader
from torchvision import transforms
from PIL import Image

# Add backend to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from config import (
    PATCH_SIZE,
    PATCHES_DIR,
    VALIDATION_PATCHES_DIR,
    AUTOENCODER_PATH,
    THRESHOLD_STATS_PATH,
    LEARNING_RATE,
    BATCH_SIZE,
    NUM_EPOCHS,
    EARLY_STOPPING_PATIENCE,
    LATENT_DIM,
    INPUT_CHANNELS
)
from models.autoencoder import create_autoencoder, count_parameters


class FabricPatchDataset(Dataset):
    """
    Dataset loader for fabric patches.
    """
    
    def __init__(self, patches_dir, transform=None):
        """
        Initialize dataset.
        
        Args:
            patches_dir: Directory containing patch images
            transform: Optional transform to apply to patches
        """
        self.patches_dir = Path(patches_dir)
        self.transform = transform
        
        # Find all patch images
        self.patch_files = sorted(list(self.patches_dir.glob("patch_*.png")))
        
        if len(self.patch_files) == 0:
            raise ValueError(f"No patch files found in {patches_dir}")
    
    def __len__(self):
        return len(self.patch_files)
    
    def __getitem__(self, idx):
        """
        Load and return a patch.
        
        Args:
            idx: Index of patch to load
            
        Returns:
            Transformed patch tensor
        """
        patch_path = self.patch_files[idx]
        
        # Load image
        image = Image.open(patch_path).convert('RGB')
        
        # Apply transforms
        if self.transform:
            image = self.transform(image)
        
        return image


def train_epoch(model, dataloader, criterion, optimizer, device):
    """
    Train the model for one epoch.
    
    Args:
        model: Autoencoder model
        dataloader: Training data loader
        criterion: Loss function
        optimizer: Optimizer
        device: Device to train on
        
    Returns:
        Average loss for the epoch
    """
    model.train()
    running_loss = 0.0
    
    pbar = tqdm(dataloader, desc="Training", leave=False)
    
    for batch in pbar:
        batch = batch.to(device)
        
        # Forward pass
        reconstructed = model(batch)
        loss = criterion(reconstructed, batch)
        
        # Backward pass
        optimizer.zero_grad()
        loss.backward()
        optimizer.step()
        
        # Track loss
        running_loss += loss.item()
        pbar.set_postfix({'loss': f'{loss.item():.6f}'})
    
    return running_loss / len(dataloader)


def validate_epoch(model, dataloader, criterion, device):
    """
    Validate the model for one epoch.
    
    Args:
        model: Autoencoder model
        dataloader: Validation data loader
        criterion: Loss function
        device: Device to validate on
        
    Returns:
        Average loss for the epoch
    """
    model.eval()
    running_loss = 0.0
    
    with torch.no_grad():
        pbar = tqdm(dataloader, desc="Validation", leave=False)
        
        for batch in pbar:
            batch = batch.to(device)
            
            # Forward pass
            reconstructed = model(batch)
            loss = criterion(reconstructed, batch)
            
            # Track loss
            running_loss += loss.item()
            pbar.set_postfix({'loss': f'{loss.item():.6f}'})
    
    return running_loss / len(dataloader)


def compute_threshold_statistics(model, dataloader, device):
    """
    Compute mean and std of reconstruction errors on validation set.
    These statistics are used to set the anomaly detection threshold.
    
    Args:
        model: Trained autoencoder model
        dataloader: Validation data loader
        device: Device to compute on
        
    Returns:
        Dictionary with mean and std of reconstruction errors
    """
    model.eval()
    all_errors = []
    
    with torch.no_grad():
        pbar = tqdm(dataloader, desc="Computing threshold stats", leave=False)
        
        for batch in pbar:
            batch = batch.to(device)
            
            # Get reconstruction errors
            errors = model.get_reconstruction_error(batch, reduction='none')
            all_errors.extend(errors.cpu().numpy())
    
    all_errors = np.array(all_errors)
    
    stats = {
        'mean': float(np.mean(all_errors)),
        'std': float(np.std(all_errors)),
        'min': float(np.min(all_errors)),
        'max': float(np.max(all_errors)),
        'median': float(np.median(all_errors)),
        'num_samples': len(all_errors)
    }
    
    return stats


def save_checkpoint(model, optimizer, epoch, train_loss, val_loss, filepath):
    """
    Save model checkpoint.
    
    Args:
        model: Model to save
        optimizer: Optimizer state to save
        epoch: Current epoch number
        train_loss: Training loss
        val_loss: Validation loss
        filepath: Path to save checkpoint
    """
    checkpoint = {
        'epoch': epoch,
        'model_state_dict': model.state_dict(),
        'optimizer_state_dict': optimizer.state_dict(),
        'train_loss': train_loss,
        'val_loss': val_loss
    }
    torch.save(checkpoint, filepath)


def main():
    parser = argparse.ArgumentParser(
        description="Train autoencoder on clean fabric patches"
    )
    
    parser.add_argument(
        "--patches-dir",
        type=str,
        default=str(PATCHES_DIR),
        help="Directory containing training patches"
    )
    
    parser.add_argument(
        "--val-dir",
        type=str,
        default=str(VALIDATION_PATCHES_DIR),
        help="Directory containing validation patches"
    )
    
    parser.add_argument(
        "--output",
        type=str,
        default=str(AUTOENCODER_PATH),
        help="Path to save trained model"
    )
    
    parser.add_argument(
        "--epochs",
        type=int,
        default=NUM_EPOCHS,
        help=f"Number of training epochs (default: {NUM_EPOCHS})"
    )
    
    parser.add_argument(
        "--batch-size",
        type=int,
        default=BATCH_SIZE,
        help=f"Batch size (default: {BATCH_SIZE})"
    )
    
    parser.add_argument(
        "--lr",
        type=float,
        default=LEARNING_RATE,
        help=f"Learning rate (default: {LEARNING_RATE})"
    )
    
    parser.add_argument(
        "--patience",
        type=int,
        default=EARLY_STOPPING_PATIENCE,
        help=f"Early stopping patience (default: {EARLY_STOPPING_PATIENCE})"
    )
    
    parser.add_argument(
        "--device",
        type=str,
        default=None,
        help="Device to train on (cpu/cuda/mps). Auto-detect if not specified."
    )
    
    args = parser.parse_args()
    
    # Device selection
    if args.device:
        device = torch.device(args.device)
    else:
        if torch.cuda.is_available():
            device = torch.device('cuda')
        elif torch.backends.mps.is_available():
            device = torch.device('mps')
        else:
            device = torch.device('cpu')
    
    print("=" * 70)
    print("Fabric Defect Detection - Autoencoder Training")
    print("=" * 70)
    print(f"Device: {device}")
    print(f"Training patches: {args.patches_dir}")
    print(f"Validation patches: {args.val_dir}")
    print(f"Epochs: {args.epochs}")
    print(f"Batch size: {args.batch_size}")
    print(f"Learning rate: {args.lr}")
    print(f"Early stopping patience: {args.patience}")
    print()
    
    # Check if patch directories exist and have data
    patches_dir = Path(args.patches_dir)
    val_dir = Path(args.val_dir)
    
    if not patches_dir.exists():
        print(f"Error: Training patches directory does not exist: {args.patches_dir}")
        print("Please run the patch extraction script first:")
        print("  python training/extract_patches.py --input <path_to_clean_fabric_video>")
        sys.exit(1)
    
    if not val_dir.exists():
        print(f"Error: Validation patches directory does not exist: {args.val_dir}")
        sys.exit(1)
    
    # Data transforms
    transform = transforms.Compose([
        transforms.ToTensor(),  # Convert to tensor and scale to [0, 1]
    ])
    
    # Create datasets
    print("Loading datasets...")
    try:
        train_dataset = FabricPatchDataset(patches_dir, transform=transform)
        val_dataset = FabricPatchDataset(val_dir, transform=transform)
    except ValueError as e:
        print(f"Error: {e}")
        print("\nPlease run the patch extraction script first:")
        print("  python training/extract_patches.py --input <path_to_clean_fabric_video>")
        sys.exit(1)
    
    print(f"Training samples: {len(train_dataset)}")
    print(f"Validation samples: {len(val_dataset)}")
    
    if len(train_dataset) == 0 or len(val_dataset) == 0:
        print("Error: Not enough training or validation data.")
        sys.exit(1)
    
    # Create data loaders
    train_loader = DataLoader(
        train_dataset,
        batch_size=args.batch_size,
        shuffle=True,
        num_workers=0,  # Set to 0 for Windows compatibility
        pin_memory=True if device.type == 'cuda' else False
    )
    
    val_loader = DataLoader(
        val_dataset,
        batch_size=args.batch_size,
        shuffle=False,
        num_workers=0,
        pin_memory=True if device.type == 'cuda' else False
    )
    
    # Create model
    print("\nCreating model...")
    model = create_autoencoder(
        input_channels=INPUT_CHANNELS,
        latent_dim=LATENT_DIM,
        patch_size=PATCH_SIZE
    )
    model = model.to(device)
    
    print(f"Model parameters: {count_parameters(model):,}")
    
    # Loss function and optimizer
    criterion = nn.MSELoss()
    optimizer = optim.Adam(model.parameters(), lr=args.lr)
    
    # Learning rate scheduler (reduce on plateau)
    scheduler = optim.lr_scheduler.ReduceLROnPlateau(
        optimizer, mode='min', factor=0.5, patience=5, verbose=True
    )
    
    # Training loop
    print("\n" + "=" * 70)
    print("Starting training...")
    print("=" * 70)
    
    best_val_loss = float('inf')
    epochs_without_improvement = 0
    
    history = {
        'train_loss': [],
        'val_loss': []
    }
    
    for epoch in range(args.epochs):
        print(f"\nEpoch {epoch + 1}/{args.epochs}")
        print("-" * 70)
        
        # Train
        train_loss = train_epoch(model, train_loader, criterion, optimizer, device)
        
        # Validate
        val_loss = validate_epoch(model, val_loader, criterion, device)
        
        # Update learning rate
        scheduler.step(val_loss)
        
        # Track history
        history['train_loss'].append(train_loss)
        history['val_loss'].append(val_loss)
        
        print(f"Train Loss: {train_loss:.6f} | Val Loss: {val_loss:.6f}")
        
        # Check for improvement
        if val_loss < best_val_loss:
            best_val_loss = val_loss
            epochs_without_improvement = 0
            
            # Save best model
            print(f"Validation loss improved! Saving model...")
            save_checkpoint(
                model, optimizer, epoch, train_loss, val_loss,
                args.output
            )
        else:
            epochs_without_improvement += 1
            print(f"No improvement for {epochs_without_improvement} epoch(s)")
        
        # Early stopping
        if epochs_without_improvement >= args.patience:
            print(f"\nEarly stopping triggered after {epoch + 1} epochs")
            break
    
    print("\n" + "=" * 70)
    print("Training complete!")
    print("=" * 70)
    print(f"Best validation loss: {best_val_loss:.6f}")
    print(f"Model saved to: {args.output}")
    
    # Load best model for threshold computation
    print("\nLoading best model for threshold computation...")
    checkpoint = torch.load(args.output, map_location=device)
    model.load_state_dict(checkpoint['model_state_dict'])
    
    # Compute threshold statistics
    print("Computing threshold statistics on validation set...")
    threshold_stats = compute_threshold_statistics(model, val_loader, device)
    
    print("\nThreshold Statistics:")
    print(f"  Mean error: {threshold_stats['mean']:.6f}")
    print(f"  Std error: {threshold_stats['std']:.6f}")
    print(f"  Min error: {threshold_stats['min']:.6f}")
    print(f"  Max error: {threshold_stats['max']:.6f}")
    print(f"  Median error: {threshold_stats['median']:.6f}")
    print(f"  Samples: {threshold_stats['num_samples']}")
    
    # Save threshold statistics
    stats_path = Path(args.output).parent / "threshold_stats.json"
    with open(stats_path, 'w') as f:
        json.dump(threshold_stats, f, indent=2)
    
    print(f"\nThreshold statistics saved to: {stats_path}")
    
    # Save training history
    history_path = Path(args.output).parent / "training_history.json"
    with open(history_path, 'w') as f:
        json.dump(history, f, indent=2)
    
    print(f"Training history saved to: {history_path}")
    
    print("\n" + "=" * 70)
    print("All done! The model is ready for inference.")
    print("You can now start the FastAPI server to run defect detection.")
    print("=" * 70)


if __name__ == "__main__":
    main()
