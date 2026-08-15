"""
levels/sample_room.py — 内置测试关卡（阶段3-5 用；阶段6 起由 rooms/*.json 读取）

room001 布局（25×19 网格）：
    * 底部地板第 17-18 行，第 21-23 列为缺口（掉下去即死）
    * 平台 A（第 14 行）、平台 B（第 12 行，需二段跳）
    * 墙柱（col 18, 第 12-16 行）
    * 尖刺：地板上的上尖刺（col 15-16，第 16 行，需跳过）、
      平台 B 底部的下尖刺（col 13）、墙柱左侧的左尖刺（col 18）
    * Checkpoint：地板 col 12（按 S 存档）
    * 出口：col 24 平台上方（走到右侧尽头 → room002）

room002 布局：
    * 完整地板 + 中部台阶 + Checkpoint（col 8）
    * 终点（col 22，end.png，碰到即通关）
    * 出口：左下角回到 room001
"""

import config
from levels.room import Room


def create_room001():
    room = Room(name="room001")

    # 底部地板：第 17-18 行，第 21-23 列为缺口
    for ty in (17, 18):
        for tx in range(config.GRID_COLS):
            if 21 <= tx <= 23:
                continue
            room.set_tile(tx, ty, "block_0")

    # 平台 A：第 14 行（x=224..352）
    for tx in range(7, 11):
        room.set_tile(tx, 14, "block_1")
    # 平台 B：第 12 行（x=384..448）
    for tx in range(12, 14):
        room.set_tile(tx, 12, "block_2")
    # 墙柱：col 18，第 12-16 行
    for ty in range(12, 17):
        room.set_tile(18, ty, "block_3")

    # 尖刺：地板上的上尖刺（第 16 行空气格，立在砖上，需跳过）
    room.spikes[(15, 16)] = "up"
    room.spikes[(16, 16)] = "up"
    # 平台 B 底部的下尖刺（挂在平台下，尖朝下）
    room.spikes[(13, 13)] = "down"
    # 墙柱左侧的左尖刺（插在墙柱上，尖朝左）
    room.spikes[(18, 15)] = "left"

    # Checkpoint：地板 col 12（站在上面按 S 存档）
    room.checkpoints.append((12, 17))

    # 添加水区域用于测试（就在起点旁边，一启动就能看到！）
    # 一段水（浅蓝色）- 减慢下落，不刷新跳跃
    room.add_water(6, 17, "first")
    room.add_water(7, 17, "first")
    room.add_water(8, 17, "first")

    # 二段水（蓝色）- 减慢下落，刷新跳跃
    room.add_water(9, 17, "second")
    room.add_water(10, 17, "second")
    room.add_water(11, 17, "second")

    # 零段水（浅灰色）- 减慢下落，禁止跳跃
    room.add_water(13, 17, "zero")
    room.add_water(14, 17, "zero")
    room.add_water(15, 17, "zero")

    # 出口：col 24 平台上方，走到右侧尽头切到 room002
    room.exits.append({"tile": (24, 16), "target": "room002"})

    # 出生点：地板左端
    room.start = (4 * config.TILE_SIZE + 4.0,
                  17 * config.TILE_SIZE - config.KID_HEIGHT)
    return room


def create_room002():
    room = Room(name="room002", bg_color=(110, 195, 235))

    # 完整地板第 17-18 行
    for ty in (17, 18):
        for tx in range(config.GRID_COLS):
            room.set_tile(tx, ty, "block_0")

    # 中部台阶（col 10-12 的第 16 行）
    for tx in range(10, 13):
        room.set_tile(tx, 16, "block_1")

    # Checkpoint：地板 col 8
    room.checkpoints.append((8, 17))

    # 添加更多水区域用于测试
    # 一段水区域
    room.add_water(5, 16, "first")
    room.add_water(6, 16, "first")
    # 二段水区域
    room.add_water(16, 16, "second")
    room.add_water(17, 16, "second")
    # 零段水区域
    room.add_water(20, 16, "zero")
    room.add_water(21, 16, "zero")

    # 终点：col 22（end.png，碰到即通关）
    room.end = (22, 16)

    # 出口：左下角回到 room001
    room.exits.append({"tile": (2, 16), "target": "room001"})

    # 出生点：地板左端
    room.start = (4 * config.TILE_SIZE + 4.0,
                  17 * config.TILE_SIZE - config.KID_HEIGHT)
    return room


# 兼容旧名称（阶段3-4 时代叫 create_test_room）
create_test_room = create_room001
