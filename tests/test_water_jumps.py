"""tests/test_water_jumps.py — 水跳跃语义回归测试（无头运行）

规则：
  · 水中跳跃不消耗跳跃次数（所有水）
  · 一段水：不刷新（入水不重置）；离开水（空中）补记一段 → 只剩一次跳（1→2）
  · 二段水：进入重置跳跃次数；接触地面（落地/贴板）刷新 → 泳池无限跳；
    离开水（空中）补记一段 → 只剩一次跳（1→2）
  · 零段水：禁止跳跃（保留次数）；离开水不补记（水里没跳，次数真实保留）
  · 陆地逻辑不受影响（落地重置 / 走落台记一段）

用法：python tests/test_water_jumps.py
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
from levels.room import Room

# ---- 真实按键伪装：pygame.key.get_pressed() 由 FakeKeys 提供 ----
HELD = set()


class FakeKeys:
    def __init__(self):
        self._arr = [False] * 512

    def __getitem__(self, k):
        return self._arr[k & 0x1FF]

    def rebuild(self):
        self._arr = [False] * 512
        for k in HELD:
            self._arr[k & 0x1FF] = True


fk = FakeKeys()
pygame.key.get_pressed = lambda: fk.rebuild() or fk


def hold(*keys):
    HELD.clear()
    for k in keys:
        HELD.add(k)


def frames(scene, n, *keys):
    for _ in range(n):
        hold(*keys)
        scene.update()


def build_scene():
    """受控房间：完整地板 + 悬空水池（一段 x4-5 / 二段 x10-11 / 零段 x16-17，row10，
    自由落体可掉穿）+ 贴地二段水池（x18-19，row16，测落地刷新）。"""
    room = Room(name="water_jump_test", bg_color=config.BG_COLOR)
    for ty in (17, 18):
        for tx in range(config.GRID_COLS):
            room.set_tile(tx, ty, "block_0")
    for tx in range(4, 6):
        room.add_water(tx, 10, "first")      # 悬空一段水
    for tx in range(10, 12):
        room.add_water(tx, 10, "second")     # 悬空二段水
    for tx in range(16, 18):
        room.add_water(tx, 10, "zero")       # 悬空零段水
    for tx in range(18, 20):
        room.add_water(tx, 16, "second")     # 贴地二段水
    room.start = (96.0, 17 * config.TILE_SIZE - config.KID_HEIGHT)
    return GameScene(AssetManager(), room=room)


T = config.TILE_SIZE
KID_Y = 17 * T - config.KID_HEIGHT   # 站在地板上的 y（碰撞箱顶）


def put_kid(scene, tx, y=None):
    """把 kid 放到某格正上方（默认站地板）；顺带清掉场景上一帧的水状态残留
    （否则传送后第一帧会被误判为"离开二段水"，凭空记一段）。"""
    scene.kid.reset(tx * T + 8.0, y if y is not None else KID_Y)
    scene.in_water = None


def drop_into(scene, tx, expect):
    """把 kid 放到水池上方自由落体，直到进入 expect 类型的水。"""
    put_kid(scene, tx, 280.0)
    scene.kid.vsp = 0.0
    for _ in range(30):
        frames(scene, 1)
        if scene.in_water == expect:
            return True
    return False


def main():
    save.clear_save()
    scene = build_scene()
    kid = scene.kid
    frames(scene, 5)                     # 稳定落地（陆地）

    # ---- 测试 1：二段水进入重置 + 水中空中跳不消耗 ----
    assert drop_into(scene, 10, "second"), "应掉入悬空二段水"
    assert kid.jump_count == 0, f"进入二段水应重置 0，实际 {kid.jump_count}"
    frames(scene, 1, pygame.K_LSHIFT)    # 水中空中跳
    assert kid.jump_count == 0 and kid.vsp < 0, \
        f"水中跳不应消耗次数（保持 0），实际 jump={kid.jump_count} vsp={kid.vsp:.2f}"
    print("PASS 1 二段水：进入重置 0，水中跳不消耗")

    # ---- 测试 2：掉穿二段水（空中出水）→ 记一段，空中只剩一次跳 ----
    put_kid(scene, 10, 280.0)            # 重新从悬空二段水上方落下
    kid.vsp = 0.0
    kid.jump_count = 0
    for _ in range(60):                  # 掉穿：入水(重置0) → 出水(记1)
        frames(scene, 1)
        if scene.in_water != "second" and kid.y > 10 * T:
            break
    assert scene.in_water != "second", "应已掉穿二段水"
    assert kid.jump_count == 1, \
        f"出水（空中）应记一段=1，实际 {kid.jump_count}"
    frames(scene, 20, pygame.K_RIGHT)    # 横向远离水池（再按跳上升不会穿回水层）
    assert scene.in_water != "second", "应已远离二段水池"
    assert kid.jump_count == 1, f"远离水池后 jump 应保持 1，实际 {kid.jump_count}"
    assert not kid.on_ground, "应仍在空中"
    frames(scene, 1)                     # 松开
    frames(scene, 1, pygame.K_LSHIFT)    # 空中唯一一次跳 1→2
    assert kid.jump_count == 2 and kid.vsp < -6.0, \
        f"出水后应能跳一次(1→2)，实际 jump={kid.jump_count} vsp={kid.vsp:.2f}"
    frames(scene, 1)
    frames(scene, 1, pygame.K_LSHIFT)    # 用完后再按 → 被挡
    assert kid.jump_count == 2, \
        f"出水后只有一次跳，用完不应再跳，实际 {kid.jump_count}"
    print(f"PASS 2 掉穿二段水（空中出水）记一段：只剩一次跳 1→2，用完被挡 vsp={kid.vsp:.2f}")

    # ---- 测试 2b：贴地二段水：落地刷新跳跃次数 ----
    put_kid(scene, 18)                   # 贴地二段水池
    frames(scene, 2)
    assert scene.in_water == "second", f"应在贴地二段水中，实际 {scene.in_water}"
    assert kid.jump_count == 0, "进入二段水应重置 0"
    frames(scene, 1, pygame.K_LSHIFT)    # 起跳（水里地面跳记 1）
    assert kid.jump_count == 1
    for _ in range(60):                  # 落回（水里落地 → 刷新 0）
        frames(scene, 1)
        if kid.on_ground:
            break
    assert kid.on_ground and kid.jump_count == 0, \
        f"二段水接触地面应刷新 0，实际 jump={kid.jump_count} on_ground={kid.on_ground}"
    print("PASS 2b 二段水落地刷新跳跃次数（泳池无限跳）")

    # ---- 测试 3：一段水：不刷新、跳不消耗、出水（空中）补记一段 ----
    assert drop_into(scene, 4, "first"), "应掉入悬空一段水"
    assert kid.jump_count == 0, "一段水入水不应重置（保持 0）"
    frames(scene, 1, pygame.K_LSHIFT)    # 一段水中空中跳 → 不消耗
    assert kid.jump_count == 0 and kid.vsp < 0, \
        f"一段水中跳不应消耗，实际 jump={kid.jump_count}"
    put_kid(scene, 4, 280.0)             # 重新掉穿一段水
    kid.vsp = 0.0
    kid.jump_count = 0
    for _ in range(60):
        frames(scene, 1)
        if scene.in_water != "first" and kid.y > 10 * T:
            break
    assert scene.in_water != "first", "应已掉穿一段水"
    assert kid.jump_count == 1, \
        f"一段水出水（空中）应补记一段=1，实际 {kid.jump_count}"
    frames(scene, 1)
    frames(scene, 1, pygame.K_LSHIFT)    # 空中一次跳 1→2
    assert kid.jump_count == 2, \
        f"一段水出水后只剩一次跳（1→2），实际 {kid.jump_count}"
    frames(scene, 1)
    frames(scene, 1, pygame.K_LSHIFT)    # 用完被挡
    assert kid.jump_count == 2, \
        f"一段水出水后用尽不应再跳，实际 {kid.jump_count}"
    print("PASS 3 一段水：不刷新、跳不消耗、出水（空中）补记一段（只剩一次跳）")

    # ---- 测试 4：零段水：禁止跳跃（保留次数），掉穿出水后正常跳 ----
    assert drop_into(scene, 16, "zero"), "应掉入悬空零段水"
    assert kid.jump_count == 0, "零段水应保留次数"
    frames(scene, 2, pygame.K_LSHIFT)    # 零段水按跳 → 跳不起来
    assert kid.vsp >= 0, \
        f"零段水应禁止跳跃，实际 vsp={kid.vsp:.2f}（不应向上）"
    assert kid.jump_count == 0, f"零段水跳被挡不应消耗，实际 {kid.jump_count}"
    put_kid(scene, 16, 280.0)            # 重新掉穿零段水
    kid.vsp = 0.0
    kid.jump_count = 0
    for _ in range(60):
        frames(scene, 1)
        if scene.in_water != "zero" and kid.y > 10 * T:
            break
    assert scene.in_water != "zero", "应已掉穿零段水"
    assert kid.jump_count == 0, f"零段水出水不应记段，实际 {kid.jump_count}"
    frames(scene, 1)
    frames(scene, 1, pygame.K_LSHIFT)    # 出水后正常起跳（保留 0 → 0→1）
    assert kid.jump_count == 1 and kid.vsp < 0, \
        f"零段水出水后应能正常跳（0→1），实际 jump={kid.jump_count} vsp={kid.vsp:.2f}"
    print("PASS 4 零段水：禁止跳跃、保留次数，出水后正常跳")

    # ---- 测试 5：陆地回归：正常落地重置 + 二段跳 ----
    put_kid(scene, 0)
    frames(scene, 3)
    assert scene.in_water is None and kid.on_ground and kid.jump_count == 0
    frames(scene, 1, pygame.K_LSHIFT)    # 一段跳
    assert kid.jump_count == 1
    for _ in range(6):
        frames(scene, 1)
    frames(scene, 1, pygame.K_LSHIFT)    # 二段跳
    assert kid.jump_count == 2 and kid.vsp < -6.0, \
        f"陆地二段跳失败 jump={kid.jump_count} vsp={kid.vsp:.2f}"
    print("PASS 5 陆地逻辑不受影响（落地重置 / 二段跳）")

    print("\n全部 PASS：水中跳不消耗；二段水出水只剩一次跳；一段水保留；零段水禁跳")
    return 0


if __name__ == "__main__":
    sys.exit(main())
