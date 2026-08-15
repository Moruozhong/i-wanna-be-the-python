"""tests/test_plus_jump.py — 跳跃球回归测试（无头运行）

复现的 bug：空中用完全部跳跃（jump_count=2）后捡到跳跃球，仍跳不起来。
根因：jump_count 记录"已用跳跃次数"，空中跳跃判定是 jump_count < 2，
旧代码捡球时写成 jump_count += 1（记作"更已用完"），3 < 2 永不成立。

修复：捡球应把已用次数减一（返还一次跳跃），用完二段跳后捡球计数 2→1，
1 < 2，还能再跳一次。

用法：python tests/test_plus_jump.py
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
    """受控房间：整排地板 + 空中 (15,10) 处一颗跳跃球。"""
    room = Room(name="plus_jump_test", bg_color=config.BG_COLOR)
    for tx in range(config.GRID_COLS):
        room.set_tile(tx, 17, "block_0")
        room.set_tile(tx, 18, "block_0")
    room.plus_jumps.append((15, 10))
    room.start = (96.0, 17 * config.TILE_SIZE - config.KID_HEIGHT)
    return GameScene(AssetManager(), room=room)


def main():
    save.clear_save()   # 封闭性：清掉磁盘存档，测试用自带房间不被存档劫持
    scene = build_scene()
    kid = scene.kid
    inp = scene.input
    T = config.TILE_SIZE
    pristine = list(scene.room.plus_jumps)   # 初始跳跃球（测试4重置用）

    # ---- 测试 1：bug 复现场景 —— 空中已用二段跳，捡球后能再跳 ----
    ball_cx, ball_cy = 15 * T + T // 2, 10 * T + T // 2
    kid.x = float(ball_cx - kid.w // 2)
    kid.y = float(ball_cy - kid.h // 2 - 6)   # 略微偏上，仍与球相交且不落地
    kid.vsp = 0.0
    kid.hsp = 0.0
    kid.jump_count = 2                        # 二段跳已用完，空中

    set_input(inp)                            # 一帧：kid.update → 捡球
    scene.update()
    assert kid.jump_count == 1, \
        f"捡球后应返还一次跳跃（2→1），实际 {kid.jump_count}"
    assert scene.room.plus_jumps == [], "跳跃球应被移除（一次性）"

    set_input(inp, ("jump",))                 # 下一帧按跳
    kid.update(inp, scene.solids)
    assert kid.vsp < -6.0, \
        f"捡球后应能再跳一次，实际 vsp={kid.vsp:.2f}（jump_count={kid.jump_count}）"
    print(f"PASS 1 空中用完二段跳后捡球可再跳 vsp={kid.vsp:.2f}")

    # ---- 测试 2：正常一段/二段跳不受影响 ----
    kid.reset(*scene.room.start)
    for _ in range(3):                        # 稳定落地
        set_input(inp)
        kid.update(inp, scene.solids)
    assert kid.on_ground and kid.jump_count == 0

    set_input(inp, ("jump",))                 # 一段跳
    kid.update(inp, scene.solids)
    assert kid.vsp < -8.0, f"一段跳失败 vsp={kid.vsp:.2f}"
    assert kid.jump_count == 1, \
        f"一段跳后跳跃次数应为 1（面板显示一致），实际 {kid.jump_count}"
    for _ in range(6):
        set_input(inp)
        kid.update(inp, scene.solids)

    set_input(inp, ("jump",))                 # 二段跳
    kid.update(inp, scene.solids)
    assert kid.jump_count == 2 and kid.vsp < -6.0, \
        f"二段跳失败 jump_count={kid.jump_count} vsp={kid.vsp:.2f}"
    print(f"PASS 2 正常一段/二段跳不受影响 vsp={kid.vsp:.2f}")

    # ---- 测试 3：落地时捡球不产生负数/无用计数 ----
    kid.reset(*scene.room.start)
    for _ in range(3):
        set_input(inp)
        kid.update(inp, scene.solids)
    assert kid.jump_count == 0 and kid.on_ground

    # 球放到地板高度，站在地板上的 Kid 一碰就捡
    scene.room.plus_jumps.clear()
    scene.room.plus_jumps.append((16, 16))    # 中心 (528,528)，紧邻地面
    kid.x = float(16 * T + T // 2 - kid.w // 2)
    kid.y = float(17 * T - kid.h)             # 站在地板顶部

    set_input(inp)
    scene.update()
    assert kid.jump_count == 0, \
        f"落地时捡球计数应保持 0，实际 {kid.jump_count}"
    assert scene.room.plus_jumps == [], "落地时也应移除跳跃球"
    print(f"PASS 3 落地捡球计数保持 0（jump_count={kid.jump_count}）")

    # ---- 测试 4：吃掉的跳跃球死亡后恢复（地图重置） ----
    scene.room.plus_jumps = list(pristine)   # 重置地图（前面测试已吃掉球）
    assert scene.room.plus_jumps, "测试房应有跳跃球"

    # 吃掉空中那颗球
    kid.x = float(ball_cx - kid.w // 2)
    kid.y = float(ball_cy - kid.h // 2 - 6)
    kid.jump_count = 2
    set_input(inp)
    scene.update()
    assert scene.room.plus_jumps == [], "吃球后应被移除"
    print(f"PASS 4a 跳跃球被吃掉（剩 {len(scene.room.plus_jumps)} 颗）")

    # 死亡 → 死亡演出 → 按 R 复活
    scene._die()
    while scene.state == "dying":
        scene.update()
    assert scene.state == "dead"
    scene.handle_event(pygame.event.Event(
        pygame.KEYDOWN, key=config.KEYMAP["restart"][0]))
    scene.update()
    assert scene.state == "play", f"复活后应为 play，实际 {scene.state}"
    assert list(scene.room.plus_jumps) == pristine, \
        "死亡复活后跳跃球应恢复原样（地图重置）"
    print(f"PASS 4 死亡后跳跃球恢复（{len(scene.room.plus_jumps)} 颗）")

    print("\n全部 PASS：跳跃球现在能正确返还一次跳跃，死亡后地图重置恢复跳跃球")
    return 0


if __name__ == "__main__":
    sys.exit(main())
