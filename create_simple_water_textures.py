#!/usr/bin/env python3
"""
Create simple water texture images - pure color with transparency only.
"""

import pygame
import os

# Initialize pygame for image creation
pygame.init()

# Constants
TILE_SIZE = 32
OUTPUT_DIR = "assets/objects"

# Create output directory if it doesn't exist
os.makedirs(OUTPUT_DIR, exist_ok=True)

# Water colors with transparency (simple semi-transparent colors)
COLORS = {
    "first": (135, 206, 235, 128),    # Light blue, semi-transparent
    "second": (0, 119, 190, 128),     # Blue, semi-transparent
    "zero": (192, 192, 192, 128)      # Light gray, semi-transparent
}

def create_simple_water_texture(water_type, filename):
    """Create a simple water texture - just pure color with transparency"""
    # Create surface with per-pixel alpha
    surf = pygame.Surface((TILE_SIZE, TILE_SIZE), pygame.SRCALPHA)

    # Fill with base color - simple pure color
    surf.fill(COLORS[water_type])

    # Save the image
    filepath = os.path.join(OUTPUT_DIR, filename)
    pygame.image.save(surf, filepath)
    print(f"Created simple water texture: {filepath}")

# Create all three water textures
for water_type in ["first", "second", "zero"]:
    filename = f"water_{water_type}.png"
    create_simple_water_texture(water_type, filename)

pygame.quit()
print("\nSimple water texture generation complete!")