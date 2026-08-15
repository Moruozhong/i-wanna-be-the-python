"""tests/test_vine_oneway.py — 藤蔓单向通道回归测试（无头运行）

藤蔓是**单向通道**（不再是双向实体）：
  · tengwan_right：攀爬面在右缘竖线 → 只从**右侧向左**撞上时吸附；
    从**左侧**经过/穿过不受阻挡（可穿到右侧）。
  · tengwan_left ：攀爬面在左缘竖线 → 只从**左侧向右**撞上时吸附；
    从**右侧**经过/穿过不受阻挡（可穿到左侧）。
  · 垂直范围放宽 ±16px：下落中撞上攀爬面也能吸附。
  · 原有行为回归：从攀爬面侧接近（含一步跨过竖线）仍吸附在攀爬面。

用法：python tests/test_vine_oneway.py
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
from levels.rooms_registry import clear_cache

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


def build(facing):
    room = Room("vine_oneway", bg_color=config.BG_COLOR)
    for ty in (17, 18):
        for tx in range(config.GRID_COLS):
            room.set_tile(tx, ty, "block_0")
    room.vines[(10, 14)] = facing
    room.start = (96.0, 17 * config.TILE_SIZE - config.KID_HEIGHT)
    return GameScene(AssetManager(), room=room)


T = config.TILE_SIZE
VY = 14 * T - config.KID_HEIGHT   # kid 底贴藤蔓顶（同高度水平接近）


def main():
    save.clear_save()
    clear_cache()

    # ---- tengwan_right：攀爬面右缘（x=10*32+32=352） ----
    s = build("right")
    k = s.kid
    frames(s, 5)

    # 1) 从左侧向右 → 穿过不吸附
    k.reset(9 * T + 8.0, VY)
    entered = False
    for _ in range(40):
        frames(s, 1, pygame.K_RIGHT)
        if k.mode == "vine":
            entered = True
            break
        if k.x > 12 * T:
            break
    assert not entered, "right 藤蔓从左侧穿过不应吸附"
    assert k.x > 11 * T, f"应已穿到藤蔓右侧，实际 x={k.x:.0f}"
    print("PASS 1 tengwan_right 左→右 穿过不吸附")

    # 2) 从右侧向左 → 吸附右缘 352
    k.reset(12 * T + 8.0, VY)
    entered = False
    for _ in range(25):
        frames(s, 1, pygame.K_LEFT)
        if k.mode == "vine":
            entered = True
            break
    assert entered, "right 藤蔓从右侧应吸附"
    assert k.x == 10 * T + T, f"应吸附右缘 352，实际 {k.x}"
    print(f"PASS 2 tengwan_right 右→左 吸附右缘 x={k.x}")

    # ---- tengwan_left：攀爬面左缘（x=10*32=320） ----
    s3 = build("left")
    k3 = s3.kid
    frames(s3, 5)

    # 3) 从右侧向左 → 穿过不吸附
    k3.reset(12 * T + 8.0, VY)
    entered = False
    for _ in range(40):
        frames(s3, 1, pygame.K_LEFT)
        if k3.mode == "vine":
            entered = True
            break
        if k3.x < 9 * T:
            break
    assert not entered, "left 藤蔓从右侧穿过不应吸附"
    assert k3.x < 10 * T, f"应已穿到藤蔓左侧，实际 x={k3.x:.0f}"
    print("PASS 3 tengwan_left 右→左 穿过不吸附")

    # 4) 从左侧向右 → 吸附左缘 309
    k3.reset(9 * T + 4.0, VY)
    entered = False
    for _ in range(25):
        frames(s3, 1, pygame.K_RIGHT)
        if k3.mode == "vine":
            entered = True
            break
    assert entered, "left 藤蔓从左侧应吸附"
    assert k3.x == 10 * T - config.KID_WIDTH, \
        f"应吸附左缘 {10*T-config.KID_WIDTH}，实际 {k3.x}"
    print(f"PASS 4 tengwan_left 左→右 吸附左缘 x={k3.x}")

    # ---- 5) 已穿过到另一侧不再错误吸附（PASS 24 场景回归） ----
    s5 = build("right")
    k5 = s5.kid
    frames(s5, 5)
    k5.reset(10 * T + 10.0, VY)         # 藤蔓内部左侧（x 330，右缘 341 < 352）
    entered = False
    for _ in range(10):
        frames(s5, 1, pygame.K_LEFT)    # 继续向左（右缘未越过攀爬面竖线）
        if k5.mode == "vine":
            entered = True
            break
    assert not entered, "右缘未越过攀爬面竖线不应吸附（瞬移回攀爬面）"
    assert k5.x < 10 * T + T, "不应瞬移回右缘"
    print("PASS 5 已穿过到另一侧不再错误吸附")

    # ---- 6) 跳到藤蔓上按住靠近方向下滑 → 滑到底脱离后不再反复吸附（无抽搐） ----
    s6 = build("right")
    k6 = s6.kid
    frames(s6, 5)
    k6.reset(12 * T + 8.0, VY)
    for _ in range(20):
        frames(s6, 1, pygame.K_LEFT)
        if k6.mode == "vine":
            break
    assert k6.mode == "vine", "应进入攀附"
    mode_flips = 0
    last = k6.mode
    for _ in range(120):
        frames(s6, 1, pygame.K_LEFT)      # 一直按住靠近方向（下滑）
        if k6.mode != last:
            mode_flips += 1
            last = k6.mode
    assert mode_flips <= 1, \
        f"滑到底脱离后不应反复吸附（抽搐），mode 变化 {mode_flips} 次"
    assert k6.mode == "normal" and k6.x < 10 * T, \
        f"应滑出藤蔓（x={k6.x:.0f}）"
    print("PASS 6 滑到底脱离后不再反复吸附（无抽搐）")

    # ---- 7) 普通脱离设再吸附冷却；跳出（leap）不设冷却 ----
    s7 = build("right")
    k7 = s7.kid
    frames(s7, 5)
    k7.reset(12 * T + 8.0, VY)
    for _ in range(20):
        frames(s7, 1, pygame.K_LEFT)
        if k7.mode == "vine":
            break
    frames(s7, 1, pygame.K_RIGHT)          # 反方向普通脱离
    assert s7._vine_reenter_block > 0, "普通脱离应设再吸附冷却"
    frames(s7, 30)                         # 冷却逐帧递减归零
    assert s7._vine_reenter_block == 0
    k7.reset(12 * T + 8.0, VY)
    for _ in range(20):
        frames(s7, 1, pygame.K_LEFT)
        if k7.mode == "vine":
            break
    frames(s7, 1, pygame.K_LSHIFT, pygame.K_RIGHT)   # Shift+反方向 跳出
    assert s7._vine_reenter_block == 0, "跳出(leap)不应设冷却（上攀靠跳出再跳回）"
    print("PASS 7 普通脱离设冷却；跳出(leap)无冷却")

    print("\n全部 PASS：藤蔓单向通道（左右区分正确，反向可自由穿过）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
