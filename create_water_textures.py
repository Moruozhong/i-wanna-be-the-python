#!/usr/bin/env python3
"""
Create water texture images for the game.
Generates three water types: first (light blue), second (blue), zero (light gray)
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

# Water colors with transparency
COLORS = {
    "first": (135, 206, 235, 180),    # Light blue, semi-transparent
    "second": (0, 119, 190, 180),     # Blue, semi-transparent
    "zero": (192, 192, 192, 180)      # Light gray, semi-transparent
}

def create_water_texture(water_type, filename):
    """Create a water texture with wave-like pattern"""
    # Create surface with per-pixel alpha
    surf = pygame.Surface((TILE_SIZE, TILE_SIZE), pygame.SRCALPHA)

    # Fill with base color
    surf.fill(COLORS[water_type])

    # Add wave pattern
    for y in range(0, TILE_SIZE, 8):
        for x in range(0, TILE_SIZE, 4):
            # Create wave effect with sine-like pattern
            wave_offset = int(3 * pygame.math.Vector2(1, 0).rotate(y * 5).x)
            alpha = 40 + int(20 * pygame.math.Vector2(1, 0).rotate(y * 5).y)
            alpha = max(0, min(255, alpha))

            # Draw wave lines
            if (x + wave_offset) % 8 < 4:
                pygame.draw.line(surf, (*COLORS[water_type][:3], alpha),
                               (x, y), (x + 4, y + 4), 1)

    # Save the image
    filepath = os.path.join(OUTPUT_DIR, filename)
    pygame.image.save(surf, filepath)
    print(f"Created water texture: {filepath}")

# Create all three water textures
for water_type in ["first", "second", "zero"]:
    filename = f"water_{water_type}.png"
    create_water_texture(water_type, filename)

pygame.quit()
print("\nWater texture generation complete!")