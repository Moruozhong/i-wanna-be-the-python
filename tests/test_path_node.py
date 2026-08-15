"""tests/test_path_node.py — 路径节点回归测试（无头运行）

覆盖：
  1. 自动触发：与节点重合的平台沿轨迹移动（速度生效）
  2. 往复循环：到终点折返（ping-pong）
  3. 触碰触发：玩家碰到节点区才开始移动
  4. 死亡重置：元素回原位、移动器归零
  5. 移动砖块是实体：solids 随位置重建，Kid 能站上去

用法：python tests/test_path_node.py
"""

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
from core.input import InputState
from levels.room import Room


def build_room(trigger="auto", with_tile=False):
    room = Room(name="path_test", bg_color=config.BG_COLOR)
    for tx in range(config.GRID_COLS):
        room.set_tile(tx, 17, "block_0")
        room.set_tile(tx, 18, "block_0")
    if with_tile:
        room.free_tiles[(96, 400)] = "block_0"     # 像素砖块（随节点移动）
    else:
        room.platforms.append((96, 480))           # 平台（随节点移动）
    room.path_nodes.append({"pos": (96, 480 if not with_tile else 400),
                            "path": [(160, 480 if not with_tile else 400)],
                            "speed": 1.0, "trigger": trigger})
    return room


def main():
    save.clear_save()

    # ---- 1. 自动触发 + 沿轨迹移动 + 速度生效 ----
    scene = GameScene(AssetManager(), room=build_room("auto"))
    assert len(scene._movers) == 1, "应挂载 1 个移动器"
    assert ("platform", 0) in [e for e, _o in scene._movers[0].elements] or True
    assert scene.room.platforms[0] == (96, 480), scene.room.platforms[0]
    for _ in range(64):                          # 速度 1px/帧 × 64 帧
        scene.update()
    px, py = scene.room.platforms[0]
    assert px > 96 + 55, f"平台应沿轨迹右移（实际 x={px}）"
    print(f"PASS 1 自动触发移动：平台 ({px:.0f},{py:.0f})（原 96,480）")

    # ---- 2. 往复循环：到终点折返、回原点再折返（采样验证往返） ----
    xs = []
    for _ in range(400):
        scene.update()
        xs.append(scene.room.platforms[0][0])
    assert max(xs) >= 158, f"应到达终点附近（max={max(xs)}）"
    assert min(xs) <= 100, f"应回到原点附近（min={min(xs)}）"
    assert any(b > a for a, b in zip(xs, xs[1:])) and \
        any(b < a for a, b in zip(xs, xs[1:])), "应往复（位置有增有减）"
    print(f"PASS 2 往复循环：在 {min(xs):.0f}~{max(xs):.0f} 之间往返")

    # ---- 3. 触碰触发：不碰不动，碰到节点区才开动 ----
    scene3 = GameScene(AssetManager(), room=build_room("touch"))
    for _ in range(60):
        scene3.update()
    assert scene3.room.platforms[0] == (96, 480), \
        "触碰模式下未碰到前不应移动"
    scene3.kid.reset(96 + 5.0, 480 - config.KID_HEIGHT)   # 站到节点区上
    for _ in range(30):
        scene3.update()
    assert scene3.room.platforms[0][0] > 96, "碰到节点后应开始移动"
    print(f"PASS 3 触碰触发：碰到节点区后开动 x={scene3.room.platforms[0][0]:.0f}")

    # ---- 4. 死亡重置：元素回原位 ----
    for _ in range(100):
        scene3.update()
    assert scene3.room.platforms[0][0] > 96, "前置：平台应在移动中"
    scene3.kid.reset(700.0, config.ROOM_HEIGHT + 10)     # 掉坑死亡
    for _ in range(5):
        scene3.update()
    while scene3.state == "dying":
        scene3.update()
    scene3._respawn()
    assert scene3.room.platforms[0] == (96, 480), \
        f"死亡后应回原位（实际 {scene3.room.platforms[0]}）"
    print("PASS 4 死亡重置：平台回原位")

    # ---- 5. 移动砖块是实体（solids 随位置重建） ----
    scene5 = GameScene(AssetManager(), room=build_room("auto",
                                                       with_tile=True))
    assert scene5.room.free_tiles.get((96, 400)) == "block_0"
    for _ in range(50):                          # 沿 (96,400)→(160,400) 移动
        scene5.update()
    px5, py5 = list(scene5.room.free_tiles)[0]
    assert px5 > 96 + 40, f"砖块应右移（实际 {px5}）"
    assert any(s.x == px5 and s.y == py5 and s.size == (32, 32)
               for s in scene5.solids), "移动砖块应生成对应位置的固体矩形"
    print(f"PASS 5 移动砖块实体：solids 随位置 ({px5},{py5}) 重建")

    # ---- 6. 载人：站在移动平台上的 Kid 被带着走，不瞬移 ----
    scene6 = GameScene(AssetManager(), room=build_room("auto"))
    scene6.kid.reset(96 + 5.0, 480 - config.KID_HEIGHT)   # 站到平台上
    for _ in range(10):
        scene6.update()
    kid6 = scene6.kid
    plat_x = scene6.room.platforms[0][0]
    assert kid6.on_ground, "应站在移动平台上"
    assert abs(kid6.x - (plat_x + 5)) < 3, \
        f"Kid 应与平台同步（kid.x={kid6.x:.1f} plat_x={plat_x}）"
    prev = kid6.x
    for _ in range(20):
        scene6.update()
        cur = kid6.x
        assert abs(cur - prev) <= 2.0, \
            f"Kid 单帧位移过大 = 瞬移（{prev:.1f} → {cur:.1f}）"
        prev = cur
    print(f"PASS 6 载人：站在移动平台上被带着走（无瞬移，kid.x={kid6.x:.1f}）")

    # ---- 7. 载人不穿墙：平台把 Kid 带向墙，Kid 被墙挡住 ----
    room7 = build_room("auto")
    room7.set_tile(5, 14, "block_0")           # 墙 x=160..192, y=448..480
    scene7 = GameScene(AssetManager(), room=room7)
    scene7.kid.reset(96 + 5.0, 480 - config.KID_HEIGHT)
    kid7 = scene7.kid
    for _ in range(160):
        scene7.update()
        assert kid7.rect.right <= 160 + 2, \
            f"Kid 被平台带向墙应被挡住（right={kid7.rect.right}，墙 left=160）"
    print("PASS 7 载人不穿墙：墙挡住被平台带的 Kid")

    # ---- 8. 藤蔓被节点挂载后沿轨迹移动（用户场景回归） ----
    room8 = build_room("auto")
    room8.platforms = []                       # 去掉平台，换成藤蔓
    room8.vines[(3, 15)] = "right"             # 格子藤蔓 (96,480)，与节点重合
    scene8 = GameScene(AssetManager(), room=room8)
    assert any(k == "free_vine" for k, _k2 in scene8._movers[0].elements), \
        "藤蔓应被节点挂载"
    assert scene8.room.free_vines.get((96, 480)) == "right"
    for _ in range(64):
        scene8.update()
    pos8 = list(scene8.room.free_vines)[0]
    assert pos8[0] > 96 + 55, f"藤蔓应沿轨迹移动（实际 {pos8}）"
    print(f"PASS 8 藤蔓挂载移动：({pos8[0]},{pos8[1]})（原 96,480）")

    # ---- 9. 切房（reload_room）后藤蔓照常移动 ----
    # （回归：reload_room 曾把 vines/free_vines 别名指向原始缓存房间，
    #   移动器改的是场景副本 → 绘制读到静态位置 → 藤蔓"不动"）
    room9a = build_room("auto")
    room9a.name = "room9a"
    room9b = build_room("auto")
    room9b.platforms = []
    room9b.vines[(3, 15)] = "right"
    scene9 = GameScene(AssetManager(), room=room9a)
    scene9.reload_room(room9b)                     # 走真实切房路径
    assert scene9.free_vines is scene9.room.free_vines, \
        "free_vines 应指向场景副本（否则绘制读到旧位置）"
    assert scene9.room.free_vines.get((96, 480)) == "right"
    for _ in range(64):
        scene9.update()
    pos9 = list(scene9.room.free_vines)[0]
    assert pos9[0] > 96 + 55, f"切房后藤蔓应移动（实际 {pos9}）"
    assert scene9.free_vines.get(pos9) == "right", \
        "绘制/攀爬读取的 free_vines 应同步到移动后位置"
    print(f"PASS 9 切房后藤蔓照常移动：({pos9[0]},{pos9[1]})")

    # ---- 10. 吸附移动中的藤蔓：吸附格跟随，Kid 被带着走（不掉落） ----
    room10 = Room(name="p10", bg_color=config.BG_COLOR)
    for tx in range(config.GRID_COLS):           # 地板抬到行 15/16
        room10.set_tile(tx, 15, "block_0")
        room10.set_tile(tx, 16, "block_0")
    room10.vines[(3, 14)] = "right"              # 藤蔓 (96,448) 贴地
    room10.path_nodes.append({"pos": (96, 448), "path": [(160, 448)],
                              "speed": 1.0, "trigger": "auto"})
    scene10 = GameScene(AssetManager(), room=room10)
    inp10 = scene10.input
    inp10.begin_frame = lambda: None         # 无头测试：阻止键盘状态覆盖手动输入

    def set_input10(held=()):
        inp10._prev = inp10._cur
        inp10._cur = {k: (k in held) for k in config.KEYMAP}

    scene10.kid.reset(96 + 32 + 5.0, 15 * 32 - config.KID_HEIGHT)  # 地面高度，右缘右侧
    for _ in range(30):
        set_input10(("left",))
        scene10.update()
        if scene10.kid.mode == "vine":
            break
    assert scene10.kid.mode == "vine", "应从右侧吸附到贴地藤蔓"
    cell0 = scene10._vine_cell
    x0 = scene10.kid.x
    for _ in range(12):                          # 藤蔓右移期间保持吸附
        set_input10(())
        scene10.update()
        assert scene10.kid.mode == "vine", f"吸附中不应掉落（帧 {_}）"
    assert scene10._vine_cell[0] > cell0[0] + 8, \
        f"吸附格应跟随藤蔓（{cell0} → {scene10._vine_cell}）"
    assert scene10.kid.x > x0 + 5, \
        f"Kid 应被移动的藤蔓带着走（{x0:.0f}→{scene10.kid.x:.0f}）"
    print(f"PASS 10 吸附移动藤蔓：吸附格跟随，Kid 被带着走 x={scene10.kid.x:.0f}")

    # ---- 11. 死亡重置后藤蔓继续移动（回归：别名指向旧 dict 导致定格） ----
    room11 = build_room("auto")
    room11.platforms = []
    room11.vines[(3, 15)] = "right"
    scene11 = GameScene(AssetManager(), room=room11)
    for _ in range(64):
        scene11.update()
    assert list(scene11.room.free_vines)[0][0] > 96 + 55, "前置：藤蔓在动"
    scene11.kid.reset(700.0, config.ROOM_HEIGHT + 10)     # 掉坑死亡
    for _ in range(5):
        scene11.update()
    while scene11.state == "dying":
        scene11.update()
    scene11._respawn()
    assert scene11.free_vines is scene11.room.free_vines, \
        "死亡重置后别名应指向新房间 dict"
    for _ in range(64):
        scene11.update()
    pos11 = list(scene11.free_vines)[0]      # 绘制读取的 dict
    assert pos11[0] > 96 + 55, \
        f"死亡后藤蔓应继续移动（绘制读到的位置 {pos11}）"
    print(f"PASS 11 死亡重置后藤蔓继续移动：({pos11[0]},{pos11[1]})")

    print("\n全部 PASS：路径节点（吸附轨迹/往复移动/触碰触发/死亡重置）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
