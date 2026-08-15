"""tests/test_platform_reset.py — 摸板子重置跳跃次数：边沿触发回归测试（无头运行）

用户场景（bug 9）：从地面不起跳入藤 → 反方向出藤 → 二段跳摸到板子 → 跳，
不落到板子上，在空中还能二段跳。规则：碰到板子重置跳跃次数可以接受，
但**摸板子时跳的那一跳必须消耗**——不能因为重叠判定每帧把 jump_count 清 0，
导致跳完立刻被抹掉（0→1→清 0），从而无限免费跳。

修复：kid.update 第 11 步的"落地/贴板重置"改为**边沿触发**——只在进入
"落地/贴板状态"的那一帧清 0。持续贴着板子不再每帧清 0，于是摸板子跳的
那一跳正常消耗（0→1 立住）→ 1→2，用完后不能再跳。

用法：python tests/test_platform_reset.py
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


def set_input(inp, held=()):
    inp._prev = inp._cur
    inp._cur = {k: (k in held) for k in config.KEYMAP}


def build_scene():
    """受控房间：整排地板 + 右侧高处单向平台带（py=400，4 块连成 128px 宽）
    + 地板旁藤蔓(5,16)（攀爬面在右缘，玩家从右侧向左贴上）。"""
    room = Room(name="platform_reset_test", bg_color=config.BG_COLOR)
    for tx in range(config.GRID_COLS):
        room.set_tile(tx, 17, "block_0")
        room.set_tile(tx, 18, "block_0")
    room.vines[(5, 16)] = "right"                       # 攀爬面在右缘
    for px in (320, 352, 384, 416):                     # 单向平台带，顶 y=400
        room.add_platform(px, 400)
    room.start = (96.0, 17 * config.TILE_SIZE - config.KID_HEIGHT)
    return GameScene(AssetManager(), room=room)


def step(scene, inp, held):
    """一帧游戏循环，复刻 GameScene.update()（含入藤跳跃规则 + 传 platforms）。"""
    set_input(inp, held)
    if scene.kid.mode == "vine":
        scene._vine_update(inp)
    else:
        pre_ground = scene.kid.on_ground   # 入藤不刷新跳跃次数（同 core/game.py update）
        scene.kid.update(inp, scene.solids, scene.platforms)
        scene._try_enter_vine()
        if scene.kid.mode == "vine" and not pre_ground:
            scene.kid.jump_count = max(scene.kid.jump_count, 1)


def attach_from_ground(scene, inp, kid, T):
    """从地板不起跳，向左走贴上藤蔓(5,16)。"""
    kid.reset(8 * T + 30.0, 17 * T - config.KID_HEIGHT)
    for _ in range(3):
        step(scene, inp, ())
    for _ in range(60):
        step(scene, inp, ("left",))
        if kid.mode == "vine":
            return
    raise AssertionError("未能从地面贴上藤蔓")


def main():
    save.clear_save()   # 封闭性
    scene = build_scene()
    kid = scene.kid
    inp = scene.input
    T = config.TILE_SIZE

    # ---- 测试 1：摸板子只重置一次，摸板子时跳的那一跳消耗并立住 ----
    # 直接把 kid 放进单向平台(320,400,32,16)的碰撞箱里（在空中擦过、不落地）：
    #   kid 底 y=410 > 平台顶 400（重叠），且 probe_bottom=411 不在 [399,401]（不算站上）。
    #   起跳后底 y=401.9 仍 >400 → 跳的那帧 step11 还在贴板，用来验证不把消耗抹掉。
    #   jump_count=2（模拟二段跳已用完）→ 摸板子 → 边沿触发重置 0。
    kid.reset(320.0, 389.0)
    kid.jump_count = 2
    step(scene, inp, ())                 # 摸板子第 1 帧：边沿触发 → 重置 0
    assert kid.jump_count == 0, f"摸板子应重置为 0，实际 {kid.jump_count}"
    step(scene, inp, ("jump",))          # 摸板子时按跳 → 应消耗：0→1 且立住（不会被同帧再清 0）
    assert kid.jump_count == 1, \
        f"摸板子时跳的那一跳必须消耗(0→1)，实际 {kid.jump_count}（说明被板子重叠每帧清 0，无限免费跳）"
    print(f"PASS 1 摸板子跳消耗并立住 jump={kid.jump_count} vsp={kid.vsp:.2f}")

    step(scene, inp, ())                 # 松开一帧（截断跳跃；脚可能瞬时"冒顶"贴板——贴板也不该再重置）
    assert kid.jump_count == 1, f"冒顶贴板也不应再重置，实际 {kid.jump_count}"
    step(scene, inp, ())                 # 再空一帧，等完全离板（on_ground=False）
    step(scene, inp, ("jump",))          # 空中 1→2 二段跳
    assert kid.jump_count == 2, f"应 1→2，实际 {kid.jump_count}"
    step(scene, inp, ())
    step(scene, inp, ("jump",))          # 用完后再按 → 不能再跳（无无限免费跳）
    assert kid.jump_count == 2, f"用完不应再跳，实际 {kid.jump_count}"
    print(f"PASS 1b 摸板子退款只够 2 跳，用完不能再跳（jump 锁在 {kid.jump_count}）")

    # ---- 测试 2：落地/站上板子仍正常重置（回归，没破坏原有重置） ----
    kid.reset(*scene.room.start)
    for _ in range(3):
        step(scene, inp, ())
    step(scene, inp, ("jump",))          # 一段跳
    assert kid.jump_count == 1
    for _ in range(6):
        step(scene, inp, ())
    step(scene, inp, ("jump",))          # 二段跳
    assert kid.jump_count == 2 and kid.vsp < -6.0, f"地面二段跳失败 jump={kid.jump_count}"
    for _ in range(120):                 # 落到地板 → 落地重置
        step(scene, inp, ())
    assert kid.on_ground and kid.jump_count == 0, \
        f"落地应重置为 0，实际 jump={kid.jump_count} on_ground={kid.on_ground}"
    print("PASS 2 落地仍正常重置（jump=0），地面二段跳不受影响")

    # ---- 测试 3：完整用户场景 — 地面入藤(0)→反方向出藤(0)→二段跳摸板子→
    #      摸板子时跳的那一跳消耗(0→1 立住)→1→2 后用完 ----
    attach_from_ground(scene, inp, kid, T)
    assert kid.jump_count == 0, f"地面入藤应保持 0，实际 {kid.jump_count}"
    step(scene, inp, ("jump", "right"))  # Shift+反方向(右) 出藤
    assert kid.jump_count == 0 and kid.mode != "vine", f"出藤应保持 0，实际 {kid.jump_count}"
    # 模拟"二段跳摸到板子"：把 kid 挪进平台带碰撞箱（不落地），已用次数=2
    kid.reset(352.0, 389.0)
    kid.jump_count = 2
    step(scene, inp, ())                 # 摸板子 → 边沿触发重置 0
    assert kid.jump_count == 0, f"摸板子应重置 0，实际 {kid.jump_count}"
    step(scene, inp, ("jump",))          # 摸板子时按跳 → 消耗并立住
    assert kid.jump_count == 1, f"摸板子跳应消耗 0→1 并立住，实际 {kid.jump_count}"
    step(scene, inp, ())                 # 松开一帧（可能瞬时冒顶贴板，也不该再重置）
    assert kid.jump_count == 1, f"冒顶贴板也不应再重置，实际 {kid.jump_count}"
    step(scene, inp, ())                 # 等完全离板
    step(scene, inp, ("jump",))          # 空中 1→2
    assert kid.jump_count == 2, f"应 1→2，实际 {kid.jump_count}"
    step(scene, inp, ())
    step(scene, inp, ("jump",))          # 用完不能再跳
    assert kid.jump_count == 2, f"用完不应再跳，实际 {kid.jump_count}"
    print("PASS 3 完整用户场景：出藤后摸板子退款 2 跳，跳的那一跳正常消耗，用尽无无限跳")

    print("\n全部 PASS：摸板子重置改为边沿触发，摸板子时跳的那一跳正常消耗，无无限免费跳")
    return 0


if __name__ == "__main__":
    sys.exit(main())
