"""tests/room_audit.py — 关卡审计（无头运行）

对 rooms/*.json 逐个检查：
  · 出生点安全：从 start 自然下落，N 帧内必须落地且不死亡（不踩刺/不掉出屏）
  · 出口目标存在：exits[].target 能被 load_room 解析
  · Checkpoint 可站立：spawn_pos（站在格顶）下方 2 行内有实体
  · 终点/水/星星/跳跃球 数量统计

用法：python tests/room_audit.py
"""

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.stdout.reconfigure(encoding="utf-8")
os.environ.setdefault("SDL_VIDEODRIVER", "dummy")

import pygame
pygame.init()

import config
from core import save
from core.assets import AssetManager
from core.game import GameScene
from levels.room import Room
from levels.rooms_registry import load_room

ROOMS_DIR = config.ROOMS_DIR
MAX_FRAMES = 300


def solid_at(solids, x, y):
    """点 (x,y) 是否落在任一固体矩形内。"""
    return any(s.left < x < s.right and s.top < y < s.bottom for s in solids)


def audit(name):
    path = os.path.join(ROOMS_DIR, f"{name}.json")
    if not os.path.isfile(path):
        print(f"[skip] {name}: 无 JSON 文件")
        return True
    with open(path, "r", encoding="utf-8") as f:
        room = Room.from_json(json.load(f))

    issues = []
    T = config.TILE_SIZE

    # ---- 1. 出生点安全 ----
    save.clear_save()
    scene = GameScene(AssetManager(), room=room)
    kid = scene.kid
    landed_y = None
    state = "play"
    for _ in range(MAX_FRAMES):
        scene.update()
        if scene.state != "play":
            state = scene.state
            break
        if kid.on_ground:
            landed_y = kid.y
            break
    if state != "play":
        issues.append(f"出生点死亡：{state}（start={room.start}）")
    elif landed_y is None:
        issues.append(f"出生点 {MAX_FRAMES} 帧内未落地（start={room.start}）")
    else:
        # 落地位置不能踩在尖刺上（已在 state 检查覆盖）；只报告落点
        print(f"  start=({room.start[0]:.0f},{room.start[1]:.0f}) 落地 y={landed_y:.0f}")

    # ---- 2. 出口目标存在 ----
    for ex in room.exits:
        target = ex["target"]
        if load_room(target) is None:
            issues.append(f"出口 ({ex['tile']}) 目标房间 {target} 不存在")
    for ex in room.free_exits:
        target = ex["target"]
        if load_room(target) is None:
            issues.append(f"出口 ({ex['pos']}) 目标房间 {target} 不存在")

    # ---- 3. Checkpoint 可站立 ----
    solids = room.solid_rects()
    for (tx, ty) in room.checkpoints:
        # 复活点：站在 checkpoint 格顶（spawn 逻辑同 _do_save）
        stand_x = tx * T + (T - config.KID_WIDTH) // 2 + 5   # 碰撞箱中部
        stand_y = ty * T + 1
        if not any(solid_at(solids, stand_x, stand_y + k) for k in range(0, 2 * T, T // 2)):
            issues.append(f"Checkpoint ({tx},{ty}) 下方 2 行内无实体（复活会悬空）")
    for (px, py) in room.free_checkpoints:
        stand_x = px + (T - config.KID_WIDTH) // 2 + 5
        stand_y = py + 1
        if not any(solid_at(solids, stand_x, stand_y + k) for k in range(0, 2 * T, T // 2)):
            issues.append(f"Checkpoint ({px},{py}) 下方 2 行内无实体（复活会悬空）")

    # ---- 4. 统计 ----
    n_water = {}
    for _w, wt in room.water.items():
        n_water[wt] = n_water.get(wt, 0) + 1
    for _w, wt in room.free_water.items():
        n_water[wt] = n_water.get(wt, 0) + 1
    print(f"  tiles={len(room.tiles)}+{len(room.free_tiles)}"
          f"+{len(room.small_tiles)}(小砖) spikes="
          f"{len(room.spikes)}+{len(room.free_spikes)} "
          f"mini_spikes={len(room.mini_spikes)} platforms={len(room.platforms)} "
          f"vines={len(room.vines)}+{len(room.free_vines)} "
          f"checkpoints={len(room.checkpoints)}+{len(room.free_checkpoints)} "
          f"water={n_water} stars={len(room.stars)}+{len(room.free_stars)} "
          f"plus_jumps={len(room.plus_jumps)}+{len(room.free_plus_jumps)} "
          f"exits={[(e['tile'], e['target']) for e in room.exits]}"
          f"{[(e['pos'], e['target']) for e in room.free_exits]} "
          f"end={room.end} free_end={room.free_end} "
          f"textures={room.textures} path_nodes={len(room.path_nodes)}")

    if issues:
        print(f"[FAIL] {name}:")
        for i in issues:
            print(f"    - {i}")
        return False
    print(f"[OK]   {name}")
    return True


def main():
    print("== 关卡审计 ==")
    files = sorted(f for f in os.listdir(ROOMS_DIR) if f.endswith(".json"))
    ok = True
    for f in files:
        ok = audit(f[:-5]) and ok
    print("== 完成 ==" if ok else "== 存在问题 ==")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
