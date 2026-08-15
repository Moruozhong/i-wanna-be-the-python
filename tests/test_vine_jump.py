"""tests/test_vine_jump.py — 藤蔓跳出后二段跳回归测试（无头运行）

覆盖用户场景：从地面不起跳贴上藤蔓（0 次已用），Shift+反方向跳出，之后应能
空中 0→1（第一跳）→ 1→2（二段跳）。
修复要点：
  · 贴藤蔓时 `on_ground=False`，脱离后第一帧不会被当成"站在地面"。
  · 空中跳按"已用次数"累加：0→第一跳(记1)、1→二段跳(记2)，不再 0 直跳 2。
  · 跳出是免费动作：不消耗跳跃次数，也不自动触发一次跳——跳跃是边沿触发，
    跳出后每次跳都要玩家自己松开再按（否则跳出时按住 Shift，下一帧自动跳
    0→1，看起来就像"出藤耗了一次跳"）。

用法：python tests/test_vine_jump.py
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
    """受控房间：整排地板 + 地板旁高处藤蔓(5,12)（从地板旁贴上）。"""
    room = Room(name="vine_jump_test", bg_color=config.BG_COLOR)
    for tx in range(config.GRID_COLS):
        room.set_tile(tx, 17, "block_0")
        room.set_tile(tx, 18, "block_0")
    room.vines[(5, 16)] = "right"   # 攀爬面在右缘，玩家从右侧向左进入
    room.start = (96.0, 17 * config.TILE_SIZE - config.KID_HEIGHT)
    return GameScene(AssetManager(), room=room)


def step(scene, inp, held):
    """一帧游戏循环，复刻 GameScene.update() 的藤蔓/普通分支（含入藤跳跃规则）。"""
    set_input(inp, held)
    if scene.kid.mode == "vine":
        scene._vine_update(inp)
    else:
        pre_ground = scene.kid.on_ground   # 入藤不刷新跳跃次数（同 core/game.py update）
        scene.kid.update(inp, scene.solids)
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

    # ---- 测试 1（用户场景）：贴藤蔓(0) → Shift+反方向跳出 → 跳出免费（保持 0），
    #      按住 Shift 不自动触发跳（不会看起来像"出藤耗了一次跳"）----
    attach_from_ground(scene, inp, kid, T)
    assert kid.jump_count == 0, f"贴藤蔓不应产生跳跃次数，实际 {kid.jump_count}"
    step(scene, inp, ("jump", "right"))   # Shift+反方向 跳出
    assert kid.jump_count == 0 and kid.mode != "vine", \
        f"跳出不应消耗跳跃次数，实际 jump={kid.jump_count}"
    step(scene, inp, ("jump",))           # 跳出后仍按住 Shift → 不应自动跳
    assert kid.jump_count == 0, \
        f"跳出后按住 Shift 不应自动触发跳（否则像出藤耗了一次跳），实际 {kid.jump_count}"
    print(f"PASS 1 跳出免费：jump 保持 0，按住 Shift 不自动跳 vsp={kid.vsp:.2f}")

    # ---- 测试 2：松开再按 → 第一跳 0→1（玩家自己的按跳才消耗）----
    attach_from_ground(scene, inp, kid, T)
    step(scene, inp, ("jump", "right"))   # 跳出
    step(scene, inp, ())                  # 松开一帧
    step(scene, inp, ("jump",))           # 再按 → 第一跳 0→1
    assert kid.jump_count == 1 and kid.vsp < 0, \
        f"跳出后松开再按应记 1（第一跳），实际 jump={kid.jump_count} vsp={kid.vsp:.2f}"
    print(f"PASS 2 跳出后松开再按 0→1 vsp={kid.vsp:.2f}")

    # ---- 测试 2b：再松开再按 → 1→2（二段跳），计数不从 0 直跳 2 ----
    attach_from_ground(scene, inp, kid, T)
    step(scene, inp, ("jump", "right"))   # 跳出
    step(scene, inp, ())                  # 松开一帧
    step(scene, inp, ("jump",))           # 第一跳 0→1
    assert kid.jump_count == 1
    step(scene, inp, ())                  # 松开一帧
    step(scene, inp, ("jump",))           # 再按 → 二段跳 1→2
    assert kid.jump_count == 2 and kid.vsp < 0, \
        f"松开再按应 1→2 二段跳，实际 jump={kid.jump_count} vsp={kid.vsp:.2f}"
    print(f"PASS 2b 跳出后第一跳+二段跳 0→1→2 vsp={kid.vsp:.2f}")

    # ---- 测试 3：藤蔓不刷新跳跃次数（贴/离都保留 jump_count） ----
    attach_from_ground(scene, inp, kid, T)
    kid.jump_count = 2                    # 模拟二段跳已用完
    step(scene, inp, ("right",))          # 反方向普通脱离
    assert kid.jump_count == 2, f"藤蔓不应刷新跳跃次数，实际 {kid.jump_count}"
    scene._vine_reenter_block = 0         # 普通脱离设冷却；手动驱动清掉
    print(f"PASS 3 藤蔓不刷新跳跃次数（脱离后仍 {kid.jump_count}）")

    # ---- 测试 4：地面正常一段/二段跳不受影响（回归） ----
    kid.reset(*scene.room.start)
    for _ in range(3):
        step(scene, inp, ())
    step(scene, inp, ("jump",))           # 一段跳
    assert kid.jump_count == 1, f"一段跳后应为 1，实际 {kid.jump_count}"
    for _ in range(6):
        step(scene, inp, ())
    step(scene, inp, ("jump",))           # 松开再按 → 二段跳
    assert kid.jump_count == 2 and kid.vsp < -6.0, \
        f"二段跳失败 jump={kid.jump_count} vsp={kid.vsp:.2f}"
    print(f"PASS 4 地面正常二段跳不受影响 vsp={kid.vsp:.2f}")

    # ---- 测试 5：空中入藤（jump=1，脚离地不足 1px 会被 is_grounded 误判落地）
    #      入藤必须保持已用次数；出藤后只能再跳一次(1→2)，而不是白得两跳(0→1→2) ----
    # 藤蔓(5,16) side=right → 玩家从右向左入。放在藤蔓右缘、脚底 17*T-1（离地 1px），
    # jump_count=1（已用一段跳）。入藤帧重力下落后脚贴地 → is_grounded 误判 → 若入藤
    # 刷新跳跃，这里会清成 0；修复后保持 1。
    kid.reset((5 + 1) * T + 1.0, 17 * T - config.KID_HEIGHT - 1.0)
    kid.jump_count = 1
    step(scene, inp, ("left",))            # 入藤当帧：重力下落→is_grounded 误判落地
    assert kid.mode == "vine", "未能从空中贴上藤蔓"
    assert kid.jump_count == 1, f"空中入藤(jump=1)应保持 1，实际被刷成 {kid.jump_count}"
    print(f"PASS 5a 空中入藤保持已用次数 jump={kid.jump_count}")

    step(scene, inp, ("jump", "right"))    # Shift+反方向(右) 跳出
    assert kid.jump_count == 1, f"跳出应保持 1，实际 {kid.jump_count}"
    step(scene, inp, ())                   # 松开一帧
    step(scene, inp, ("jump",))            # 再按 → 只剩一次跳：1→2
    assert kid.jump_count == 2 and kid.vsp < 0, \
        f"空中入藤出藤后应只能再跳一次(1→2)，实际 1→{kid.jump_count}"
    print(f"PASS 5b 空中入藤出藤后只剩一次跳 1→2 vsp={kid.vsp:.2f}")

    # ---- 测试 5c：坠落空中入藤（未按跳，jump=0）→ 也应只视为已用一段跳（0→1），
    #      出藤后只能再跳一次。否则"走落台阶/平台坠落入藤"白得两跳(0→1→2) ----
    kid.reset((5 + 1) * T + 1.0, 17 * T - config.KID_HEIGHT - 20.0)  # 脚底离地 20px
    kid.jump_count = 0
    step(scene, inp, ("left",))            # 坠落中向左入藤
    assert kid.mode == "vine", "未能坠落入藤"
    assert kid.jump_count == 1, f"空中入藤(未跳)应记为已用一段跳(1)，实际 {kid.jump_count}"
    print(f"PASS 5c 坠落入藤记为已用一段跳 jump={kid.jump_count}")

    step(scene, inp, ("jump", "right"))    # Shift+反方向(右) 跳出
    assert kid.jump_count == 1, f"跳出应保持 1，实际 {kid.jump_count}"
    step(scene, inp, ())
    step(scene, inp, ("jump",))            # 再按 → 只剩一次跳：1→2
    assert kid.jump_count == 2 and kid.vsp < 0, \
        f"坠落入藤出藤后应只能再跳一次(1→2)，实际 1→{kid.jump_count}"
    print(f"PASS 5d 坠落入藤出藤后只剩一次跳 1→2 vsp={kid.vsp:.2f}")

    print("\n全部 PASS：藤蔓跳出后空中可正常二段跳，空中入藤视为已用一段跳")
    return 0


if __name__ == "__main__":
    sys.exit(main())
