# Water Entity System Implementation

## Overview
Added a complete water entity system with three types of water, each with unique physics properties and visual characteristics.

## Files Created/Modified

### New Files:
1. `entities/water.py` - Water entity class
2. `create_water_textures.py` - Script to generate water textures
3. `levels/room_with_water.py` - Example room with water zones
4. `WATER_IMPLEMENTATION.md` - This documentation

### Modified Files:
1. `core/assets.py` - Added water texture loading and placeholder generation
2. `levels/room.py` - Added water support to room data structure
3. `core/game.py` - Added water physics and rendering
4. `levels/sample_room.py` - Added water examples for testing

## Water Types

### 1. First Stage Water (浅蓝色)
- **Color**: Light blue (semi-transparent)
- **Physics**: 
  - Fall speed reduced to 2.4 px/frame
  - Normal horizontal movement speed
  - Does NOT refresh jump count
- **Image**: `assets/objects/water_first.png`

### 2. Second Stage Water (水蓝色)
- **Color**: Blue (semi-transparent)
- **Physics**:
  - Fall speed reduced to 2.4 px/frame
  - Normal horizontal movement speed
  - Refreshes jump count when player touches ground
- **Image**: `assets/objects/water_second.png`

### 3. Zero Stage Water (浅灰色)
- **Color**: Light gray (semi-transparent)
- **Physics**:
  - Fall speed reduced to 2.4 px/frame
  - Normal horizontal movement speed
  - Prevents jumping (but preserves jump count)
- **Image**: `assets/objects/water_zero.png`

## Implementation Details

### Entity Structure
- Each water tile is 32×32 pixels (same as standard tiles)
- Water entities are stored in the room data structure as a dictionary: `(tx, ty) -> water_type`
- Water tiles are rendered above the player character

### Physics Implementation
- Water physics are applied when the player's collision box overlaps with a water tile
- All water types cap fall speed at `config.WATER_FALL_SPEED` (2.4 px/frame)
- Jumping while in water does **not** consume a jump (all water types)
- First stage water: does not refresh jump count; **exiting while airborne records one jump used** (only the double jump remains)
- Second stage water: resets jump count when entering **and** when touching ground (infinite jumps in the pool); **exiting while airborne records one jump used**, so only one air jump remains
- Zero stage water blocks jump input while preserving jump count; exiting does **not** record a jump (you couldn't jump inside, so nothing was gained)
- Land physics are unchanged (edge-triggered reset on landing, walk-off records one jump)

### Integration with Existing Systems
- Water tiles work alongside existing entities (spikes, platforms, vines, checkpoints)
- Water collision detection is separate from solid collision detection
- Debug mode (F1) shows water hitboxes with labels
- Water tiles are loaded from room JSON files

## Usage Example

### Adding Water to a Room:
```python
# In a room definition
room = Room("my_room")

# Add first stage water at grid position (10, 15)
room.add_water(10, 15, "first")

# Add second stage water
room.add_water(12, 15, "second")

# Add zero stage water
room.add_water(14, 15, "zero")
```

### JSON Format (for room files):
```json
{
  "name": "my_room",
  "water": [
    {"tx": 10, "ty": 15, "type": "first"},
    {"tx": 12, "ty": 15, "type": "second"},
    {"tx": 14, "ty": 15, "type": "zero"}
  ],
  // ... other room data
}
```

## Testing

The system includes water in `sample_room.py` for testing:
- First stage water at positions (15, 17) and (16, 17)
- Second stage water at positions (18, 17) and (19, 17)
- Zero stage water at positions (21, 17) and (22, 17)

To test the water physics:
1. Run the game
2. Navigate to areas with different water types
3. Test jumping and falling in each type
4. Verify that zero stage water prevents jumping while others allow it

## Technical Notes

- Water physics are implemented by temporarily modifying global config values
- The system preserves jump count for all water types
- Water tiles render above the player character
- Water collision is detected per-frame and applied immediately