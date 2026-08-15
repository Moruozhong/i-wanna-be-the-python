#!/usr/bin/env python3
"""test_mini_spike.py — 小刺（16×16 四象限）冒烟测试（无头运行）

覆盖：
  · mini_spike_test_room JSON 加载（16 个小刺、四方向）
  · 小刺碰撞遮罩构建（数量与四象限位置换算）
  · 踩小刺立即死亡 + 按 R 复活
  · 出口切房回 room001

用法：python test_mini_spike.py
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.stdout.reconfigure(encoding="utf-8")
os.environ.setdefault("SDL_VIDEODRIVER", "dummy")

import pygame
pygame.init()

import config
from core import save
from core.assets import AssetManager
from core.game import GameScene
from levels.rooms_registry import load_room


def main():
    save.clear_save()   # 封闭性：不受磁盘存档影响
    print("=== 测试小刺功能（无头） ===")

    # 1. 房间加载：16 个小刺（4 方向 × 4 象限）
    room = load_room("mini_spike_test_room")
    assert room is not None, "无法加载 mini_spike_test_room"
    assert len(room.mini_spikes) == 16, \
        f"应有 16 个小刺，实际 {len(room.mini_spikes)}"
    print(f"PASS 1 房间加载：{room.name}，小刺 {len(room.mini_spikes)} 个")

    # 2. 场景构建：碰撞遮罩数量一致；四象限位置换算正确（16×16 在 32×32 内）
    scene = GameScene(AssetManager(), room=room)
    T = config.TILE_SIZE
    Q = T // 2
    assert len(scene.mini_spike_masks) == len(room.mini_spikes), \
        "mini_spike_masks 数量与房间小刺不一致"
    for (tx, ty, quad), _d in room.mini_spikes.items():
        exp_x = tx * T + (Q if quad in (1, 3) else 0)
        exp_y = ty * T + (Q if quad in (2, 3) else 0)
        # 碰撞遮罩列表里能找到对应位置（mask 左上角 = ox,oy）
        assert any(ox == exp_x and oy == exp_y
                   for _m, ox, oy in scene.mini_spike_masks), \
            f"小刺 ({tx},{ty}) quad={quad} 位置换算错误：期望 ({exp_x},{exp_y})"
    print("PASS 2 场景构建：mini_spike_masks 数量与四象限位置正确")

    # 3. 踩小刺立即死亡（(2,17) quad0=左上，站在其上方落下穿过即死）→ 按 R 复活
    scene.kid.reset(2 * T + 2.0, 17 * T - config.KID_HEIGHT)
    for _ in range(10):
        scene.update()
        if scene.state != "play":
            break
    assert scene.state == "dying", f"踩到小刺应死亡，实际 {scene.state}"
    while scene.state == "dying":
        scene.update()
    scene.handle_event(pygame.event.Event(
        pygame.KEYDOWN, key=config.KEYMAP["restart"][0]))
    scene.update()
    assert scene.state == "play", "按 R 应复活"
    print("PASS 3 踩小刺立即死亡 + 按 R 复活")

    # 4. 出口：右上角 (24,16) → room001
    scene.kid.reset(24 * T + 4.0, 16 * T + 4.0)
    for _ in range(3):
        scene.update()
    assert scene.room.name == "room001", \
        f"出口应切到 room001，实际 {scene.room.name}"
    print("PASS 4 出口切房到 room001")

    print("\n✅ 小刺测试全部通过")
    return 0


if __name__ == "__main__":
    sys.exit(main())
