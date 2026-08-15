"""tests/test_jump_star.py — 跳跃星星回归测试（无头运行）

用户需求：三种跳跃星星（一段=黑/二段=灰/三段=黄），碰到后"最多跳跃次数"变为
对应段数（1/2/3），带 sndBlockChange 音效 + 放大淡出特效；星星**不可消耗**（不消失）。
玩家默认二段跳（max_jumps=2），去碰二段星无变化。死亡/重生 max_jumps 重置回 2。
兼容所有与跳跃次数有关的机制：藤蔓空中入藤（记 1）、跳跃球返还（减一）、
摸板子边沿重置（退款一次后正常消耗）。

真实 GameScene.update() + FakeKeys 无头驱动（同 endtoend 脚本），比手动 step 更忠实。

用法：python tests/test_jump_star.py
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
from levels.rooms_registry import load_room

save.clear_save()   # 封闭性（出生点不受存档影响）


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
    """受控房间：整排地板 + 三颗地面星(8/12/16,16) + 藤蔓(5,16) + 平台带(320,400)
    + 跳跃球(20,16)。星星全在地面一层，走上就碰。"""
    room = Room(name="jump_star_test", bg_color=config.BG_COLOR)
    for tx in range(config.GRID_COLS):
        room.set_tile(tx, 17, "block_0")
        room.set_tile(tx, 18, "block_0")
    room.vines[(5, 16)] = "right"                   # 攀爬面右缘，从右向左进入
    room.add_star(8, 16, 3)                         # 三段星（黄）
    room.add_star(12, 16, 1)                        # 一段星（黑）
    room.add_star(16, 16, 2)                        # 二段星（灰）
    for px in (320, 352, 384, 416):                 # 单向平台带，顶 y=400
        room.add_platform(px, 400)
    room.plus_jumps.append((20, 16))                # 跳跃球
    room.start = (96.0, 17 * config.TILE_SIZE - config.KID_HEIGHT)
    return GameScene(AssetManager(), room=room)


T = config.TILE_SIZE
KID_Y = 17 * T - config.KID_HEIGHT   # 站在地板上的 y（碰撞箱顶）


def star_cell(scene, level):
    for tx, ty, lv in scene.room.stars:
        if lv == level:
            return tx, ty
    raise AssertionError(f"房间没有 level={level} 的星星")


def touch_star(scene, level, settle=3):
    """把 kid 放到某颗星的正上方（中心对齐），空放几帧触发。"""
    scene._prev_star_cells = set()          # 清边沿状态，保证触发
    tx, ty = star_cell(scene, level)
    scene.kid.reset(tx * T + T // 2 - 5, KID_Y)
    frames(scene, settle)


def main():
    scene = build_scene()
    kid = scene.kid

    # ---- 测试 1：三段星 → max_jumps=3；空中 0→1→2→3，再用被门槛挡住 ----
    touch_star(scene, 3)
    assert kid.max_jumps == 3 and kid.jump_count == 0, \
        f"碰三段星应 max=3 jump=0，实际 max={kid.max_jumps} jump={kid.jump_count}"
    frames(scene, 1, pygame.K_LSHIFT)       # 地面一段跳 0→1
    assert kid.jump_count == 1, f"地面跳应 0→1，实际 {kid.jump_count}"
    frames(scene, 1)                        # 松开（截断）
    frames(scene, 1, pygame.K_LSHIFT)       # 空中 1→2
    assert kid.jump_count == 2, f"应 1→2，实际 {kid.jump_count}"
    frames(scene, 1)
    frames(scene, 1, pygame.K_LSHIFT)       # 空中 2→3（三段跳）
    assert kid.jump_count == 3, f"应 2→3，实际 {kid.jump_count}"
    frames(scene, 1)
    frames(scene, 1, pygame.K_LSHIFT)       # 3<3 → 挡住，不能再跳
    assert kid.jump_count == 3, f"三段跳用完(3)不应再跳，实际 {kid.jump_count}"
    print(f"PASS 1 三段星：max=3，空中 0→1→2→3，用完挡在第4跳 (vsp={kid.vsp:.2f})")

    # ---- 测试 2：一段星 → max_jumps=1，只能跳一次 ----
    touch_star(scene, 1)
    assert kid.max_jumps == 1, f"碰一段星应 max=1，实际 {kid.max_jumps}"
    frames(scene, 1, pygame.K_LSHIFT)       # 地面跳 0→1
    assert kid.jump_count == 1, f"一段星地面跳应 0→1，实际 {kid.jump_count}"
    frames(scene, 1)
    frames(scene, 1, pygame.K_LSHIFT)       # 空中 1<1 → 挡住
    assert kid.jump_count == 1, f"一段星只能跳一次，实际 {kid.jump_count}"
    print("PASS 2 一段星：max=1，只能 0→1 一次跳，空中按跳被挡")

    # ---- 测试 3：默认二段跳碰二段星无变化（max 保持 2） ----
    touch_star(scene, 2)
    assert kid.max_jumps == 2, f"默认二段跳碰二段星应保持 2，实际 {kid.max_jumps}"
    print(f"PASS 3 默认 2 碰二段星无变化（max 仍 {kid.max_jumps}）")

    # ---- 测试 4：星星不可消耗 + 离开再碰重新生效（边沿触发） ----
    n_stars = len(scene.room.stars)
    touch_star(scene, 3)
    assert kid.max_jumps == 3 and len(scene.room.stars) == n_stars, \
        "碰三段星后星星不应消失"
    kid.x, kid.y = 2 * T + 30.0, KID_Y      # 走开（不 reset——reset 会清 max，这里只换位置）
    frames(scene, 6)
    assert kid.max_jumps == 3, "离开星星不应改 max"
    touch_star(scene, 3)                     # 回来再碰 → 重新生效
    assert kid.max_jumps == 3 and len(scene.room.stars) == n_stars, \
        "再碰三段星应重新生效且星星仍在（不可消耗）"
    assert len(scene.star_fx) >= 1, "触碰应生成放大淡出特效"
    print(f"PASS 4 星星不可消耗（{n_stars} 颗仍在），离开再碰重新生效，特效已生成")

    # ---- 测试 5：降级 3→1 ----
    touch_star(scene, 3)
    assert kid.max_jumps == 3
    touch_star(scene, 1)
    assert kid.max_jumps == 1, f"碰一段星应降级为 1，实际 {kid.max_jumps}"
    print(f"PASS 5 降级：三段星(3) → 一段星(1)，max={kid.max_jumps}")

    # ---- 测试 6：落地后 jump_count 归 0 但 max 保留 ----
    touch_star(scene, 3)
    frames(scene, 1, pygame.K_LSHIFT)       # 地面跳 0→1
    assert kid.jump_count == 1
    frames(scene, 90)                        # 自由落体落地
    assert kid.on_ground and kid.jump_count == 0, \
        f"落地应 jump=0，实际 {kid.jump_count}"
    assert kid.max_jumps == 3, f"落地不应改 max，实际 {kid.max_jumps}"
    print(f"PASS 6 落地 jump 归 0，max 保留 {kid.max_jumps}")

    # ---- 测试 7：死亡/重生 max_jumps 重置回默认 2 ----
    touch_star(scene, 3)
    assert kid.max_jumps == 3
    kid.reset(*scene.room.start)            # _respawn() 同样调用 kid.reset()
    assert kid.max_jumps == 2, f"重生后 max 应回默认 2，实际 {kid.max_jumps}"
    print("PASS 7 死亡/重生 max_jumps 重置回默认 2")

    # ---- 测试 8：max=3 时藤蔓空中入藤记 1，出藤还能 1→2→3（剩两次跳） ----
    kid.reset(6 * T + 1.0, KID_Y - 20.0)     # 藤蔓右缘外 1px、脚离地 20px 坠落
    kid.max_jumps = 3                        # reset 会清 max，必须在 reset 之后设
    kid.jump_count = 0
    entered = False
    for _ in range(60):
        frames(scene, 1, pygame.K_LEFT)
        if kid.mode == "vine":
            entered = True
            break
    assert entered, "未能坠落入藤"
    assert kid.jump_count == 1, f"空中入藤应记 1（max=3），实际 {kid.jump_count}"
    frames(scene, 1, pygame.K_LSHIFT, pygame.K_RIGHT)   # Shift+反方向(右) 跳出，免费
    assert kid.jump_count == 1 and kid.mode != "vine", \
        f"跳出应免费保持 1，实际 {kid.jump_count}"
    frames(scene, 1)                        # 松开
    frames(scene, 1, pygame.K_LSHIFT)       # 1→2
    assert kid.jump_count == 2, f"出藤后应 1→2，实际 {kid.jump_count}"
    frames(scene, 1)
    frames(scene, 1, pygame.K_LSHIFT)       # 2→3
    assert kid.jump_count == 3, f"出藤后应 2→3，实际 {kid.jump_count}"
    frames(scene, 1)
    frames(scene, 1, pygame.K_LSHIFT)       # 用完挡
    assert kid.jump_count == 3, f"max=3 出藤后用完不应再跳，实际 {kid.jump_count}"
    print(f"PASS 8 max=3 藤蔓兼容：空中入藤记 1，出藤 1→2→3 用完挡")

    # ---- 测试 9：max=3 时跳跃球返还仍正确（jump_count=max(0,n-1)） ----
    touch_star(scene, 3)                     # 先落回地面并拿三段星
    frames(scene, 2)
    kid.jump_count = 3                       # 模拟三段跳已用完
    bx, _by = 20 * T + T // 2 - 5, KID_Y     # 传送到跳跃球(20,16)上方
    kid.x, kid.y = bx, KID_Y
    frames(scene, 1)
    assert kid.jump_count == 2, f"跳跃球应返还 3→2，实际 {kid.jump_count}"
    assert (20, 16) not in scene.room.plus_jumps, "跳跃球被吃掉应从房间移除"
    print(f"PASS 9 max=3 跳跃球返还：jump 3→{kid.jump_count}，球被移除")

    # ---- 测试 10：max=3 时摸板子边沿重置 + 摸板子时跳的那一跳消耗 ----
    kid.reset(320.0, 389.0)                  # 放进平台(320,400)碰撞箱，不落地
    kid.max_jumps = 3
    kid.jump_count = 3
    frames(scene, 1)                         # 摸板子第 1 帧：边沿触发重置 0
    assert kid.jump_count == 0, f"摸板子应重置 0，实际 {kid.jump_count}"
    frames(scene, 1, pygame.K_LSHIFT)        # 摸板子时跳 → 消耗 0→1 并立住
    assert kid.jump_count == 1, f"摸板子跳必须消耗(0→1)，实际 {kid.jump_count}"
    frames(scene, 2)                         # 松开并等完全离板
    frames(scene, 1, pygame.K_LSHIFT)        # 1→2
    assert kid.jump_count == 2, f"应 1→2，实际 {kid.jump_count}"
    frames(scene, 1)
    frames(scene, 1, pygame.K_LSHIFT)        # 2→3
    assert kid.jump_count == 3, f"max=3 应 2→3，实际 {kid.jump_count}"
    frames(scene, 1)
    frames(scene, 1, pygame.K_LSHIFT)        # 用完挡
    assert kid.jump_count == 3, f"max=3 用完不应再跳，实际 {kid.jump_count}"
    print(f"PASS 10 max=3 摸板子兼容：重置 0，跳消耗 0→1，共 3 跳用完挡")

    # ---- 测试 12：已是该段数时触碰不放音效/特效；段数变化（降级）才放 ----
    touch_star(scene, 3)                          # 2→3：变化，放特效
    fx_before = len(scene.star_fx)
    assert fx_before >= 1, "第一次碰三段星（变化）应放特效"
    kid.x, kid.y = 2 * T + 30.0, KID_Y            # 走开（不 reset，保持 max=3）
    frames(scene, 6)
    scene._prev_star_cells = set()
    tx3, ty3 = star_cell(scene, 3)
    kid.x, kid.y = tx3 * T + T // 2 - 5, KID_Y    # 回来再碰三段星
    frames(scene, 1)
    assert kid.max_jumps == 3
    assert len(scene.star_fx) == fx_before, \
        f"已是 3 段再碰 3 段星不应放特效（{fx_before}→{len(scene.star_fx)}）"
    scene._prev_star_cells = set()
    tx1, ty1 = star_cell(scene, 1)
    kid.x, kid.y = tx1 * T + T // 2 - 5, KID_Y    # 碰一段星：3→1 降级，变化 → 放特效
    frames(scene, 1)
    assert kid.max_jumps == 1
    assert len(scene.star_fx) == fx_before + 1, \
        f"降级 3→1 应放特效（{fx_before}→{len(scene.star_fx)}）"
    print("PASS 12 已是该段数触碰不放特效；段数变化（降级）才放")

    # ---- 测试 11：切房间保留星星改的最大跳跃次数；死亡才重置回 2 ----
    touch_star(scene, 3)
    assert kid.max_jumps == 3
    scene.reload_room(load_room("room001"))        # 模拟从出口切房
    assert kid.max_jumps == 3, \
        f"切房间应保留 max=3，实际 {kid.max_jumps}"
    kid.reset(*scene.room.start)                   # 死亡/重生 → 回默认 2
    assert kid.max_jumps == 2, \
        f"死亡后应回默认 2，实际 {kid.max_jumps}"
    print("PASS 11 切房间保留 max_jumps；死亡才重置回 2")

    # ---- 测试 13：走落台后空中只剩 max-1 次跳（离开地面记一段，不再白得满额跳） ----
    def walk_off_test(maxj):
        room = Room(name="walkoff", bg_color=config.BG_COLOR)
        for tx in range(11):                       # 地板到 x=352，右缘走落
            room.set_tile(tx, 17, "block_0")
            room.set_tile(tx, 18, "block_0")
        room.start = (96.0, KID_Y)
        s = GameScene(AssetManager(), room=room)
        k = s.kid
        k.reset(10 * T + 8, KID_Y)                 # 贴近右缘
        k.max_jumps = maxj                         # reset 会清 max，须在其后设
        for _ in range(3):
            frames(s, 1)
        for _ in range(30):                        # 向右走出边缘
            frames(s, 1, pygame.K_RIGHT)
            if not k.on_ground and k.x > 11 * T:
                break
        frames(s, 1)                               # 松开方向键
        assert k.jump_count == 1, \
            f"max={maxj} 走落台后应记一段(1)，实际 {k.jump_count}"
        gained = 0
        for _ in range(maxj + 2):                  # 空中连按，数能按出几次
            if k.on_ground:
                break
            before = k.jump_count
            frames(s, 1, pygame.K_LSHIFT)
            if k.jump_count > before:
                gained += 1
            if k.on_ground:
                break
            frames(s, 1)                           # 松开，为下次按跳备边沿
        assert gained == maxj - 1, \
            f"max={maxj} 走落台空中应只剩 {maxj-1} 次跳，实际 {gained}"
        print(f"PASS 13a max={maxj} 走落台：离开地面记 1，空中只剩 {maxj - 1} 次跳")

    for m in (1, 2, 3):
        walk_off_test(m)
    print("PASS 13 走落台后空中只剩 max-1 次跳（离开地面记一段，不再白得满额跳）")

    print("\n全部 PASS：跳跃星星改变最多跳跃次数，兼容所有跳跃次数机制")
    return 0


if __name__ == "__main__":
    sys.exit(main())
