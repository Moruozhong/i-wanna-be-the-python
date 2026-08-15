"""
entities/water.py — Water entities (32×32px transparent tiles)

Three types of water with different properties:
- First stage water: light blue, slows fall speed to 2.4, normal movement, doesn't refresh jumps
- Second stage water: blue color, slows fall speed to 2.4, normal movement, refreshes jumps
- Zero stage water: light gray, no jumping allowed (but preserves jump count), normal movement

Water tiles are rendered above the player character.
"""

import pygame
import config


class Water:
    def __init__(self, x, y, water_type):
        """
        Initialize water entity.

        Args:
            x: Pixel X coordinate
            y: Pixel Y coordinate
            water_type: "first", "second", or "zero" (first/second/zero stage water)
        """
        self.x = float(x)
        self.y = float(y)
        self.w = config.TILE_SIZE
        self.h = config.TILE_SIZE
        self.water_type = water_type

        # Water colors with transparency
        self.colors = {
            "first": (135, 206, 235, 128),   # Light blue (sky blue), semi-transparent
            "second": (0, 119, 190, 128),     # Blue color, semi-transparent
            "zero": (192, 192, 192, 128)      # Light gray, semi-transparent
        }

        # Physics properties
        # 下落减速由 Kid 统一处理（config.WATER_FALL_SPEED = 2.4，所有类型一致），
        # 这里只保留水类型的语义差异：
        self.refreshes_jumps = water_type == "second"
        self.allows_jumping = water_type != "zero"

    @property
    def rect(self):
        """Collision rectangle for water (32×32)."""
        return pygame.Rect(round(self.x), round(self.y), self.w, self.h)

    def draw(self, screen):
        """Draw water tile with transparency above player character."""
        color = self.colors[self.water_type]

        # Create a surface with per-pixel alpha for transparency
        water_surface = pygame.Surface((self.w, self.h), pygame.SRCALPHA)
        water_surface.fill(color)

        # Draw water surface
        screen.blit(water_surface, (round(self.x), round(self.y)))

        # Optional: Add some visual texture to make water more recognizable
        # You could add wave patterns or bubbles here if desired