#!/usr/bin/env python3
"""
Quick test script for water functionality.
Loads the water test room directly.
"""

import sys
import os

# Add project root to path
project_root = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, project_root)

from core.app import App
from levels.room import Room
import json

def load_water_test_room():
    """Load water test room from JSON"""
    import config
    with open(os.path.join(config.ROOMS_DIR, "water_test_room.json"),
              "r", encoding="utf-8") as f:
        data = json.load(f)
    return Room.from_json(data)

def main():
    """Test water functionality"""
    print("Testing water system...")
    print("Controls:")
    print("- Arrow keys: Move")
    print("- Shift: Jump")
    print("- Z: Shoot")
    print("- S: Save checkpoint")
    print("- R: Restart")
    print("- F1: Show hitboxes")
    print("\nWater types:")
    print("- Light blue (first stage): Slows fall speed, no jump refresh")
    print("- Blue (second stage): Slows fall speed, refreshes jumps")
    print("- Light gray (zero stage): Slows fall speed, no jumping allowed")

    # Create custom app with water test room
    app = App()
    app.scene.room = load_water_test_room()
    app.scene.solids = app.scene.room.solid_rects()
    app.scene.spike_masks = app.scene._build_spike_masks()
    app.scene.end_rect = app.scene._build_end_rect()
    app.scene.platforms = app.scene._build_platform_rects()
    app.scene.vines = app.scene.room.vines
    app.scene.free_vines = app.scene.room.free_vines
    app.scene._vine_cell = None
    app.scene.vine_barriers = app.scene._build_vine_barriers()
    app.scene._build_water_tiles()
    app.scene.in_water = None

    # Reset player position
    app.scene.kid.reset(*app.scene.room.start)

    app.run()

if __name__ == "__main__":
    main()