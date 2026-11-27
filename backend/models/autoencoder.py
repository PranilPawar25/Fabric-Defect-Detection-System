"""
Convolutional Autoencoder Model for Fabric Defect Detection

This autoencoder is trained on clean (defect-free) fabric patches.
During inference, it reconstructs input patches, and patches with high
reconstruction error are flagged as potential defects (anomaly detection).
"""

import torch
import torch.nn as nn
import torch.nn.functional as F


class FabricAutoencoder(nn.Module):
    """
    Convolutional autoencoder for learning normal fabric patterns.
    
    Architecture:
    - Encoder: Conv layers that compress the input to a latent representation
    - Decoder: Transposed conv layers that reconstruct the original image
    
    Input: RGB patches of size (3, PATCH_SIZE, PATCH_SIZE)
    Output: Reconstructed RGB patches of the same size
    """
    
    def __init__(self, input_channels=3, latent_dim=128, patch_size=64):
        """
        Initialize the autoencoder.
        
        Args:
            input_channels: Number of input channels (3 for RGB)
            latent_dim: Size of the bottleneck latent representation
            patch_size: Size of input patches (must be square)
        """
        super(FabricAutoencoder, self).__init__()
        
        self.input_channels = input_channels
        self.latent_dim = latent_dim
        self.patch_size = patch_size
        
        # ============================================================================
        # ENCODER: Compress input to latent representation
        # ============================================================================
        
        # Conv block 1: (3, 64, 64) -> (32, 32, 32)
        self.encoder_conv1 = nn.Sequential(
            nn.Conv2d(input_channels, 32, kernel_size=3, stride=2, padding=1),
            nn.BatchNorm2d(32),
            nn.ReLU(inplace=True)
        )
        
        # Conv block 2: (32, 32, 32) -> (64, 16, 16)
        self.encoder_conv2 = nn.Sequential(
            nn.Conv2d(32, 64, kernel_size=3, stride=2, padding=1),
            nn.BatchNorm2d(64),
            nn.ReLU(inplace=True)
        )
        
        # Conv block 3: (64, 16, 16) -> (128, 8, 8)
        self.encoder_conv3 = nn.Sequential(
            nn.Conv2d(64, 128, kernel_size=3, stride=2, padding=1),
            nn.BatchNorm2d(128),
            nn.ReLU(inplace=True)
        )
        
        # Conv block 4: (128, 8, 8) -> (256, 4, 4)
        self.encoder_conv4 = nn.Sequential(
            nn.Conv2d(128, 256, kernel_size=3, stride=2, padding=1),
            nn.BatchNorm2d(256),
            nn.ReLU(inplace=True)
        )
        
        # Flatten and compress to latent dimension
        # For 64x64 patches: 256 * 4 * 4 = 4096
        self.encoder_flatten_size = 256 * (patch_size // 16) * (patch_size // 16)
        self.encoder_fc = nn.Linear(self.encoder_flatten_size, latent_dim)
        
        # ============================================================================
        # DECODER: Reconstruct from latent representation
        # ============================================================================
        
        # Expand from latent dimension
        self.decoder_fc = nn.Linear(latent_dim, self.encoder_flatten_size)
        
        # Transposed conv block 1: (256, 4, 4) -> (128, 8, 8)
        self.decoder_conv1 = nn.Sequential(
            nn.ConvTranspose2d(256, 128, kernel_size=4, stride=2, padding=1),
            nn.BatchNorm2d(128),
            nn.ReLU(inplace=True)
        )
        
        # Transposed conv block 2: (128, 8, 8) -> (64, 16, 16)
        self.decoder_conv2 = nn.Sequential(
            nn.ConvTranspose2d(128, 64, kernel_size=4, stride=2, padding=1),
            nn.BatchNorm2d(64),
            nn.ReLU(inplace=True)
        )
        
        # Transposed conv block 3: (64, 16, 16) -> (32, 32, 32)
        self.decoder_conv3 = nn.Sequential(
            nn.ConvTranspose2d(64, 32, kernel_size=4, stride=2, padding=1),
            nn.BatchNorm2d(32),
            nn.ReLU(inplace=True)
        )
        
        # Transposed conv block 4: (32, 32, 32) -> (3, 64, 64)
        self.decoder_conv4 = nn.Sequential(
            nn.ConvTranspose2d(32, input_channels, kernel_size=4, stride=2, padding=1),
            nn.Sigmoid()  # Output in [0, 1] range
        )
    
    def encode(self, x):
        """
        Encode input to latent representation.
        
        Args:
            x: Input tensor of shape (batch, channels, height, width)
            
        Returns:
            Latent representation of shape (batch, latent_dim)
        """
        x = self.encoder_conv1(x)
        x = self.encoder_conv2(x)
        x = self.encoder_conv3(x)
        x = self.encoder_conv4(x)
        
        # Flatten
        x = x.view(x.size(0), -1)
        
        # Compress to latent dimension
        x = self.encoder_fc(x)
        
        return x
    
    def decode(self, z):
        """
        Decode latent representation to reconstructed image.
        
        Args:
            z: Latent representation of shape (batch, latent_dim)
            
        Returns:
            Reconstructed image of shape (batch, channels, height, width)
        """
        # Expand from latent dimension
        x = self.decoder_fc(z)
        
        # Reshape to spatial dimensions
        spatial_size = self.patch_size // 16
        x = x.view(x.size(0), 256, spatial_size, spatial_size)
        
        # Transposed convolutions
        x = self.decoder_conv1(x)
        x = self.decoder_conv2(x)
        x = self.decoder_conv3(x)
        x = self.decoder_conv4(x)
        
        return x
    
    def forward(self, x):
        """
        Forward pass: encode then decode.
        
        Args:
            x: Input tensor of shape (batch, channels, height, width)
            
        Returns:
            Reconstructed tensor of the same shape as input
        """
        z = self.encode(x)
        reconstructed = self.decode(z)
        return reconstructed
    
    def get_reconstruction_error(self, x, reduction='none'):
        """
        Compute reconstruction error (MSE) for input patches.
        
        Args:
            x: Input tensor of shape (batch, channels, height, width)
            reduction: 'none' returns per-sample error, 'mean' returns average
            
        Returns:
            Reconstruction error(s)
        """
        with torch.no_grad():
            reconstructed = self.forward(x)
            
            if reduction == 'none':
                # Return per-sample error (mean over spatial and channel dimensions)
                error = F.mse_loss(reconstructed, x, reduction='none')
                error = error.view(error.size(0), -1).mean(dim=1)
                return error
            elif reduction == 'mean':
                # Return single average error
                error = F.mse_loss(reconstructed, x, reduction='mean')
                return error
            else:
                raise ValueError(f"Unsupported reduction: {reduction}")


def create_autoencoder(input_channels=3, latent_dim=128, patch_size=64):
    """
    Factory function to create an autoencoder model.
    
    Args:
        input_channels: Number of input channels
        latent_dim: Size of latent representation
        patch_size: Size of input patches
        
    Returns:
        FabricAutoencoder model
    """
    model = FabricAutoencoder(
        input_channels=input_channels,
        latent_dim=latent_dim,
        patch_size=patch_size
    )
    return model


def count_parameters(model):
    """
    Count the number of trainable parameters in a model.
    
    Args:
        model: PyTorch model
        
    Returns:
        Number of trainable parameters
    """
    return sum(p.numel() for p in model.parameters() if p.requires_grad)


if __name__ == "__main__":
    # Test the model
    print("Testing FabricAutoencoder...")
    
    # Create model
    model = create_autoencoder(input_channels=3, latent_dim=128, patch_size=64)
    print(f"Model created with {count_parameters(model):,} trainable parameters")
    
    # Test forward pass
    batch_size = 4
    test_input = torch.randn(batch_size, 3, 64, 64)
    
    print(f"\nInput shape: {test_input.shape}")
    
    # Encode
    latent = model.encode(test_input)
    print(f"Latent shape: {latent.shape}")
    
    # Decode
    reconstructed = model.decode(latent)
    print(f"Reconstructed shape: {reconstructed.shape}")
    
    # Full forward pass
    output = model(test_input)
    print(f"Output shape: {output.shape}")
    
    # Reconstruction error
    error = model.get_reconstruction_error(test_input, reduction='none')
    print(f"Reconstruction error shape: {error.shape}")
    print(f"Reconstruction errors: {error.tolist()}")
    
    print("\nModel test passed!")
