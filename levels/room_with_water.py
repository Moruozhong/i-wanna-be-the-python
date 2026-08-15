"""
levels/room_with_water.py — 测试水物理的房间

包含三种不同类型的水：
- 一段水：浅蓝色，减慢下落速度，不刷新跳跃
- 二段水：蓝色，减慢下落速度，刷新跳跃
- 零段水：浅灰色，不允许跳跃
"""

import config
from levels.room import Room


def create_water_test_room():
    """创建包含水区域的测试房间"""
    room = Room(name="water_test")

    # 创建一个水池区域
    # 地板
    for ty in (17, 18):
        for tx in range(config.GRID_COLS):
            room.set_tile(tx, ty, "block_0")

    # 墙壁形成水池
    for ty in range(10, 18):
        room.set_tile(5, ty, "block_1")
        room.set_tile(19, ty, "block_1")

    # 一段水（浅蓝色） - 左边部分
    for tx in range(6, 10):
        room.add_water(tx, 16, "first")

    # 二段水（蓝色） - 中间部分
    for tx in range(10, 14):
        room.add_water(tx, 16, "second")

    # 零段水（浅灰色） - 右边部分
    for tx in range(14, 19):
        room.add_water(tx, 16, "zero")

    # 跳台
    for tx in range(7, 9):
        room.set_tile(tx, 9, "block_2")

    # 出生点在平台上
    room.start = (7 * config.TILE_SIZE + 4.0, 9 * config.TILE_SIZE - config.KID_HEIGHT)

    return room


# 注册到房间系统
rooms_registry = {
    "water_test": create_water_test_room,
}