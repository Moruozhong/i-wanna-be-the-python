"""tests/physics_test.py — 帧级物理冒烟测试（无头运行）

用法：python tests/physics_test.py
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


def set_input(inp, held=()):
    """手动注入一帧按键状态（cur/prev 帧间对比）。"""
    inp._prev = inp._cur
    inp._cur = {k: (k in held) for k in config.KEYMAP}


def main():
    save.clear_save()   # 封闭性：清掉磁盘存档，测试从默认出生点开始
    scene = GameScene(AssetManager())
    kid = scene.kid
    inp = InputState()
    T = config.TILE_SIZE

    # 1. 落地站立
    # 显式放到地板：不依赖房间默认出生点（room001.json 的 start 是关卡设计值，
    # 可能不在地板上；本测试只验证"落地→站立"物理本身）。
    kid.reset(96.0, 17 * T - config.KID_HEIGHT)
    for _ in range(5):
        set_input(inp)
        kid.update(inp, scene.solids)
    assert kid.on_ground, "应稳定落地"
    assert kid.vsp == 0.0, f"站立 vsp 应为 0，实际 {kid.vsp}"
    assert kid.y == 17 * T - config.KID_HEIGHT, f"应站在地板顶部，y={kid.y}"
    print("PASS 1 落地站立 vsp=0")

    # 2. 水平移动：按住右，每帧 +3px
    x0 = kid.x
    for _ in range(5):
        set_input(inp, ("right",))
        kid.update(inp, scene.solids)
    assert kid.x == x0 + 5 * config.PLAYER_SPEED, f"x 位移错误 {x0}->{kid.x}"
    print(f"PASS 2 水平移动每帧+{config.PLAYER_SPEED}px")

    # 3. 撞墙：压向墙柱，x 停在墙左缘
    kid.reset(560.0, 17 * T - config.KID_HEIGHT)
    for _ in range(120):
        set_input(inp, ("right",))
        kid.update(inp, scene.solids)
    assert kid.x == 18 * T - config.KID_WIDTH, \
        f"撞墙应停在 {18*T-config.KID_WIDTH}，实际 {kid.x}"
    print("PASS 3 墙壁碰撞不穿墙")

    # 4. 平台着陆：从平台 A 上方落下
    kid.reset(8 * T + 4.0, 12 * T)
    for _ in range(200):
        set_input(inp)
        kid.update(inp, scene.solids)
        if kid.on_ground:
            break
    assert kid.y == 14 * T - config.KID_HEIGHT, \
        f"应落在平台 A 顶 y={14*T-config.KID_HEIGHT}，实际 {kid.y}"
    print("PASS 4 平台着陆")

    # 5. 一段跳
    kid.reset(96.0, 17 * T - config.KID_HEIGHT)
    for _ in range(3):
        set_input(inp)
        kid.update(inp, scene.solids)
    set_input(inp, ("jump",))
    kid.update(inp, scene.solids)
    assert kid.jump_count == 1 and kid.vsp < -8.0, f"一段跳失败 vsp={kid.vsp}"
    print(f"PASS 5 一段跳 vsp={kid.vsp:.2f}（应为 {config.JUMP_SPEED}+重力）")

    # 6. 松手截断（长短跳）
    set_input(inp)
    kid.update(inp, scene.solids)
    assert kid.vsp < 0 and kid.vsp > config.JUMP_SPEED, f"松手应截断上升，vsp={kid.vsp}"
    print(f"PASS 6 松手截断 vsp={kid.vsp:.2f}（约为 {config.JUMP_SPEED*config.JUMP_CUT_MULTIPLIER:.2f}）")

    # 7. 二段跳
    for _ in range(300):
        set_input(inp)
        kid.update(inp, scene.solids)
        if kid.on_ground:
            break
    set_input(inp, ("jump",))
    kid.update(inp, scene.solids)
    assert kid.jump_count == 1
    for _ in range(6):
        set_input(inp)
        kid.update(inp, scene.solids)
    set_input(inp, ("jump",))
    kid.update(inp, scene.solids)
    assert kid.jump_count == 2 and kid.vsp < -6.0, \
        f"二段跳失败 jump_count={kid.jump_count} vsp={kid.vsp}"
    print(f"PASS 7 二段跳 vsp={kid.vsp:.2f}")

    # 8. 最大下落速度封顶（掉进右侧缺口自由落体）
    kid.reset(700.0, 0.0)
    max_vsp = 0.0
    for _ in range(120):
        set_input(inp)
        kid.update(inp, scene.solids)
        max_vsp = max(max_vsp, kid.vsp)
    assert max_vsp <= config.MAX_FALL_SPEED + 0.001, f"vsp 超限 {max_vsp}"
    assert max_vsp >= config.MAX_FALL_SPEED - 0.5, f"vsp 未达封顶 {max_vsp}"
    print(f"PASS 8 下落封顶 max_vsp={max_vsp:.2f}")

    # 9. 掉出房间 → 死亡演出 → 停留等按 R 复活（不自动重生）
    scene.kid.reset(700.0, config.ROOM_HEIGHT + 10)
    for _ in range(3):
        scene.update()
    assert scene.state == "dying", f"应进入 dying，实际 {scene.state}"
    while scene.state == "dying":
        scene.update()
    assert scene.state == "dead", f"演出结束后应停留 dead 等按 R，实际 {scene.state}"
    # 不按 R 不应重生
    for _ in range(5):
        scene.update()
    assert scene.state == "dead", "不按 R 不应自动复活"
    # 死亡演出持续到按 R：dead 状态下头应继续飞/跳（不冻结）
    hd = scene.death_fx.head
    head_moved = False
    for _ in range(25):
        x0, y0 = hd["x"], hd["y"]
        scene.update()
        if round(hd["x"]) != round(x0) or round(hd["y"]) != round(y0):
            head_moved = True
    assert head_moved, "dead 状态下头应持续移动（演出未结束）"
    assert scene.state == "dead", "持续演出不应改变死亡状态"
    # 按 R 复活
    scene.handle_event(pygame.event.Event(
        pygame.KEYDOWN, key=config.KEYMAP["restart"][0]))
    scene.update()
    assert scene.state == "play", f"按 R 后应复活，实际 {scene.state}"
    print("PASS 9 掉出房间→死亡演出→按R自行复活")

    # 10. 走落平台边缘后空中起跳（离开地面记一段，空中只剩 max-1 次跳：
    #     走落时 jump=1，第一次空中跳 1→2，用尽后再按被挡——与
    #     test_jump_star PASS 13 的"走落台记一段"规则一致，不再白得满额跳）
    kid.reset(8 * T, 14 * T - config.KID_HEIGHT)   # 平台 A 上
    walked_off = False
    for _ in range(300):
        set_input(inp, ("right",))
        kid.update(inp, scene.solids)
        if not kid.on_ground:
            walked_off = True
            break
    assert walked_off, "应已走落平台边缘"
    assert kid.jump_count == 1, \
        f"离开地面应记一段(1)，实际 {kid.jump_count}"
    set_input(inp, ("jump",))
    kid.update(inp, scene.solids)
    assert kid.jump_count == 2 and kid.vsp < -6.0, \
        f"空中第一跳失败 jump_count={kid.jump_count} vsp={kid.vsp}"
    set_input(inp, ())
    kid.update(inp, scene.solids)
    set_input(inp, ("jump",))
    kid.update(inp, scene.solids)
    assert kid.jump_count == 2, \
        f"二段跳用尽后按跳应被挡（jump 锁在 2），实际 {kid.jump_count}"
    print(f"PASS 10 走落平台边缘空中起跳 1→2 后用尽 vsp={kid.vsp:.2f}")

    # 11. 动画切换不请求不存在的帧（不触发占位图）
    kid.reset(96.0, 17 * T - config.KID_HEIGHT)
    dummy = pygame.Surface((config.ROOM_WIDTH, config.ROOM_HEIGHT))
    scenario = [
        (), (), (), (),
        ("right",) * 20,
        ("jump",), ("right",) * 10,
        ("right", "jump"), ("right",) * 5,
        () * 40,
    ]
    for held in scenario:
        set_input(inp, held)
        kid.update(inp, scene.solids)
        kid.draw(dummy)
        assert kid.frame < config.KID_ANIM_FRAMES.get(kid.anim, 1), \
            f"帧号越界 {kid.anim}/{kid.frame}"
    bad = [f for f in scene.assets.missing if f.startswith("characters/kid")]
    assert not bad, f"请求了不存在的 Kid 帧素材: {bad}"
    print("PASS 11 动画切换不触发占位图")

    # 12. Room.solid_rects 行合并正确
    rects = scene.room.solid_rects()
    row17 = [r for r in rects if r.y == 17 * T]
    assert any(r.x == 0 and r.w == 21 * T and r.h == T for r in row17), \
        "地板第17行应合并为 (0,544,672,32)"
    assert any(r.x == 24 * T and r.w == T for r in row17), "右缘平台应独立成矩形"
    assert len([r for r in rects if r.y == 17 * T]) == 2, "第17行应恰为2个矩形（0-20列 + 24列）"
    print("PASS 12 Room.solid_rects 行合并")

    # 13. 碰到尖刺立即死亡（视觉与碰撞分离：碰撞区在尖刺格上部）
    scene.kid.reset(15 * T + 4.0, 14 * T)   # 从上尖刺 (15,16) 正上方落下
    for _ in range(60):
        scene.update()
        if scene.state != "play":
            break
    assert scene.state == "dying", f"碰到尖刺应立即死亡，实际 {scene.state}"
    # 落点检查：碰撞区在 (15,16) 上部而非整格，落地砖面不应误伤
    scene.handle_event(pygame.event.Event(
        pygame.KEYDOWN, key=config.KEYMAP["restart"][0]))
    scene.update()
    assert scene.state == "play", "按 R 应复活"
    print("PASS 13 尖刺碰撞立即死亡")

    # 14. Checkpoint：接触按 S 存档 → 死亡后回存档点复活
    scene.kid.reset(12 * T + 4.0, 17 * T - config.KID_HEIGHT)   # 站在 checkpoint 格上
    for _ in range(5):
        set_input(inp)
        kid.update(inp, scene.solids)
    scene._save_checkpoint()
    assert scene.active_checkpoint == ("room001", 12 * T, 17 * T), \
        f"存档失败 {scene.active_checkpoint}"
    assert scene.spawn_room == "room001", f"存档房间错误 {scene.spawn_room}"
    expected_spawn = (12 * T + (T - config.KID_WIDTH) // 2,
                      17 * T - config.KID_HEIGHT)
    assert scene.spawn_pos == expected_spawn, f"存档点错误 {scene.spawn_pos}"
    # 再死一次 → 复活回存档点
    scene.kid.reset(700.0, config.ROOM_HEIGHT + 10)
    for _ in range(5):
        scene.update()
    while scene.state == "dying":
        scene.update()
    scene.handle_event(pygame.event.Event(
        pygame.KEYDOWN, key=config.KEYMAP["restart"][0]))
    scene.update()
    assert scene.state == "play", "按 R 应复活"
    assert (kid.x, kid.y) == scene.spawn_pos, \
        f"应回存档点复活，实际 {(kid.x, kid.y)}，存档点 {scene.spawn_pos}"
    print("PASS 14 Checkpoint 存档 + 存档点复活")

    # 15. 出口切房：room001 出口 (24,16) → 切到 room002，保留存档点
    scene.kid.reset(24 * T + 4.0, 16 * T + 4.0)
    for _ in range(3):
        scene.update()
    assert scene.room.name == "room002", f"应切到 room002，实际 {scene.room.name}"
    assert scene.active_checkpoint == ("room001", 12 * T, 17 * T), \
        "切房应保留存档点"
    assert scene.state == "play", f"切房后应为 play，实际 {scene.state}"
    print("PASS 15 出口切房 + 保留存档点")

    # 16. 终点：room002 的 end → 通关演出，演出结束停留 won
    scene.kid.reset(22 * T + 4.0, 16 * T + 4.0)   # 终点 (22,16)
    for _ in range(3):
        scene.update()
    assert scene.state == "won", f"碰终点应通关，实际 {scene.state}"
    for _ in range(config.WIN_FRAMES + 5):
        scene.update()
    assert scene.state == "won", "通关演出结束应停留 won"
    print("PASS 16 终点通关演出")

    # 17. 跨房间死亡复活：room002 掉坑死亡 → 按 R 回 room001 存档点
    scene.state = "play"                          # 离开通关画面
    scene.kid.reset(700.0, config.ROOM_HEIGHT + 10)
    for _ in range(5):
        scene.update()
    assert scene.state in ("dying", "dead"), f"room002 掉坑应死亡 {scene.state}"
    while scene.state == "dying":
        scene.update()
    scene.handle_event(pygame.event.Event(
        pygame.KEYDOWN, key=config.KEYMAP["restart"][0]))
    scene.update()
    assert scene.state == "play", f"按 R 应复活，实际 {scene.state}"
    assert scene.room.name == "room001", f"应回存档点房间 room001，实际 {scene.room.name}"
    assert (kid.x, kid.y) == scene.spawn_pos, \
        f"应回存档点复活 {(kid.x, kid.y)}，存档点 {scene.spawn_pos}"
    print("PASS 17 跨房间死亡回存档点")

    # 18. 尖刺像素级碰撞：mask 由图片 alpha 逐像素生成，0 像素偏差
    m_up = scene.assets.spike_mask("up")
    img_up = scene.assets.spike("up")
    threshold = config.SPIKE_MASK_THRESHOLD
    diff = sum(1 for y in range(32) for x in range(32)
               if bool(m_up.get_at((x, y))) != (img_up.get_at((x, y))[3] >= threshold))
    assert diff == 0, f"spike_up 碰撞 mask 与图片 alpha 有 {diff} 像素不一致"
    # 旧三角形把底边画到 x=1..30；真实图底边只到中心，角落透明（"偏差"的根源）
    assert not m_up.get_at((0, 28)), "spike_up 左下角应透明"
    assert m_up.get_at((15, 28)), "spike_up 底边中心应实体"
    assert m_up.get_at((15, 0)), "spike_up 顶点应实体"

    # 直接验证 overlap 偏移方向：offset = 对方在自身坐标系中的位置
    # （写反会导致碰撞区镜像、与 F1 显示的碰撞箱完全不符）
    scene.kid.reset(484.0, 500.0)
    rr = scene.kid.rect
    sign_p = pygame.mask.Mask((32, 32))
    sign_p.set_at((10, 0))     # 尖刺像素绝对 (490,512)，在 Kid 矩形 (484,500)-(495,521) 内
    assert scene._kid_mask.overlap(sign_p, (480 - rr.left, 512 - rr.top)) is not None, \
        "尖刺像素在 Kid 矩形内应命中（offset 方向错会导致漏判）"
    sign_q = pygame.mask.Mask((32, 32))
    sign_q.set_at((0, 0))      # 尖刺像素绝对 (480,512)，在 Kid 矩形左缘之外
    assert scene._kid_mask.overlap(sign_q, (480 - rr.left, 512 - rr.top)) is None, \
        "尖刺像素在 Kid 矩形外不应命中（offset 方向错会导致镜像误伤）"

    # 游戏级 1：正上方落下，覆盖不透明像素 → 立即死
    scene.kid.reset(15 * T + 4.0, 14 * T)
    for _ in range(60):
        scene.update()
        if scene.state != "play":
            break
    assert scene.state == "dying", f"正上方落下应死，实际 {scene.state}"
    scene.handle_event(pygame.event.Event(
        pygame.KEYDOWN, key=config.KEYMAP["restart"][0]))
    scene.update()
    assert scene.state == "play"

    # 游戏级 2：矩形压到尖刺 Tile 但未覆盖任何尖刺实心像素 → 不误伤
    # （旧整格矩形碰撞箱在这里会误杀——这正是"偏差"所在）
    spike_tile = pygame.Rect(15 * T, 16 * T, T, T)
    found = None
    for dx in range(-8, 33):
        for dy in range(-20, 13):
            r = pygame.Rect(spike_tile.left + dx, spike_tile.top + dy,
                            config.KID_WIDTH, config.KID_HEIGHT)
            if r.colliderect(spike_tile):     # 矩形压到尖刺格（旧矩形会杀）
                scene.kid.reset(float(r.left), float(r.top))
                if not scene._touches_spike():   # 但对所有尖刺都无实心像素重叠（新碰撞不杀）
                    found = (r.left, r.top)
                    break
        if found:
            break
    assert found, "应存在“矩形碰 Tile 但 mask 不重叠”的位置（旧矩形会误杀）"
    assert scene._touches_spike() is False, "仅覆盖透明像素不应误伤"
    # 反证：Kid 覆盖一个尖刺实心像素 → 应命中
    opx = next((x, y) for y in range(32) for x in range(32) if m_up.get_at((x, y)))
    scene.kid.reset(float(15 * T + opx[0] - config.KID_WIDTH // 2),
                    float(16 * T + opx[1] - config.KID_HEIGHT // 2))
    assert scene._touches_spike() is True, "覆盖尖刺实心像素应命中"
    print("PASS 18 尖刺像素级碰撞（mask=图片 alpha，0 偏差，透明区不误伤/实心区必命中）")

    # 19. 藤蔓进入：room001 右侧藤蔓 (11,13..16)，从右向左碰撞 → VINE_CLING
    kid.reset(12 * T + 8.0, 16 * T - config.KID_HEIGHT)   # 藤蔓(11,16)右侧
    scene._vine_cell = None
    entered = False
    for _ in range(6):
        set_input(inp, ("left",))
        kid.update(inp, scene.solids)
        scene._try_enter_vine()
        if kid.mode == "vine":
            entered = True
            break
    assert entered, f"应从右向左进入藤蔓，实际 mode={kid.mode}"
    assert kid.x == 11 * T + T, f"应吸附在藤蔓右缘 x={11*T+T}，实际 {kid.x}"
    assert kid.vsp == 0.0 and kid.hsp == 0.0, "进入后速度应清零"
    assert kid.vine_side == "right" and kid.facing == -1, "应吸附右侧、面左"
    assert kid.anim == "on", f"应切到 on 动画，实际 {kid.anim}"
    print("PASS 19 从右侧藤蔓正侧面进入 VINE_CLING")

    # 20. 无输入 / 按住靠近方向(左) → 均沿藤蔓缓慢下滑（纯方向键不直接爬）
    y0 = kid.y
    for _ in range(4):
        set_input(inp)
        scene._vine_update(inp)
    assert kid.mode == "vine" and kid.y == y0 + 4 * config.VINE_SLIDE_SPEED, \
        f"无输入应下滑，{y0}->{kid.y}"
    y0 = kid.y
    for _ in range(4):
        set_input(inp, ("left",))
        scene._vine_update(inp)
    assert kid.mode == "vine" and kid.y == y0 + 4 * config.VINE_SLIDE_SPEED, \
        f"按住靠近方向应仍缓慢下滑（不是贴住），{y0}->{kid.y}"
    print("PASS 20 无输入 / 按住靠近方向 → 均缓慢下滑")

    # 21. Shift+靠近方向(左) 不再上爬（自然下滑）；Shift+反方向(右) = 跳出藤蔓（向右上方）
    y0 = kid.y
    for _ in range(4):
        set_input(inp, ("jump", "left"))
        scene._vine_update(inp)
    assert kid.mode == "vine" and kid.y == y0 + 4 * config.VINE_SLIDE_SPEED, \
        f"Shift+靠近方向 不应上爬，应自然下滑 {y0}->{kid.y}"
    set_input(inp, ("jump", "right"))      # Shift + 反方向 = 跳出藤蔓
    scene._vine_update(inp)
    assert kid.mode == "normal", f"Shift+反方向 应跳出藤蔓，实际 {kid.mode}"
    assert kid.vsp < 0, f"跳出应向上（向右上方），vsp={kid.vsp}"
    assert kid.hsp > 0, f"跳出应向右，hsp={kid.hsp}"
    print("PASS 21 Shift+靠近方向 不再上爬（下滑）/ Shift+反方向 跳出藤蔓（向右上方）")

    # 22. 按住反方向(右) → 普通脱离（向右推开）；藤蔓不刷新跳跃次数
    kid.reset(12 * T + 8.0, 15 * T - config.KID_HEIGHT)   # 藤蔓(11,15)右侧
    kid.mode = "normal"
    scene._vine_cell = None
    for _ in range(6):
        set_input(inp, ("left",))
        kid.update(inp, scene.solids)
        scene._try_enter_vine()
        if kid.mode == "vine":
            break
    assert kid.mode == "vine", f"应进入攀附，实际 {kid.mode}"
    kid.jump_count = 2   # 模拟二段跳已用完（藤蔓不刷新跳跃）
    set_input(inp, ("right",))
    scene._vine_update(inp)
    assert kid.mode == "normal", f"反方向应普通脱离，实际 {kid.mode}"
    assert kid.jump_count == 2, "藤蔓不刷新跳跃次数"
    assert kid.hsp > 0, f"普通脱离应向右推开，hsp={kid.hsp}"
    assert kid.vsp == 0.0, f"普通脱离不应向上，vsp={kid.vsp}"
    scene._vine_reenter_block = 0   # 普通脱离会设再吸附冷却；本测试手动驱动
                                    #（不跑主循环递减），下一场景前清掉
    print("PASS 22 反方向普通脱离（向右推开、不刷新跳跃次数）")

    # 23. 左侧藤蔓镜像：手动加一个 left 藤蔓，从左向右进入 → 吸附左侧、面右
    scene.vines[(5, 15)] = "left"
    kid.reset(5 * T - config.KID_WIDTH - 8.0, 15 * T)
    scene._vine_cell = None
    entered = False
    for _ in range(6):
        set_input(inp, ("right",))
        kid.update(inp, scene.solids)
        scene._try_enter_vine()
        if kid.mode == "vine":
            entered = True
            break
    assert entered, f"应从左向右进入左侧藤蔓，实际 mode={kid.mode}"
    assert kid.x == 5 * T - config.KID_WIDTH, \
        f"应吸附在藤蔓左缘 x={5*T-config.KID_WIDTH}，实际 {kid.x}"
    assert kid.vine_side == "left" and kid.facing == 1, "应吸附左侧、面右"
    dummy = pygame.Surface((config.ROOM_WIDTH, config.ROOM_HEIGHT))
    kid.draw(dummy)   # 镜像绘制不崩
    print("PASS 23 左侧藤蔓镜像吸附")

    # 24. 碰撞修复：Kid 已穿过藤蔓到另一侧（左侧），仍向左 → 不应错误吸附瞬移回右侧
    kid.reset(350.0, 15 * T)
    kid.mode = "normal"
    scene._vine_cell = None
    for _ in range(10):
        set_input(inp, ("left",))
        kid.update(inp, scene.solids)
        scene._try_enter_vine()
    assert kid.mode == "normal", f"已到藤蔓左侧仍向左不应吸附，实际 mode={kid.mode}"
    assert kid.x < 11 * T, f"不应瞬移到藤蔓右侧，实际 x={kid.x}"
    print("PASS 24 穿过藤蔓到另一侧不再错误吸附（碰撞修复）")

    # 25. 循环攀爬：按住靠近方向(左)下滑时按反方向(右) → 脱离（左右同按以脱离为准）
    kid.reset(12 * T + 8.0, 15 * T - config.KID_HEIGHT)   # 藤蔓(11,15)右侧
    kid.mode = "normal"
    scene._vine_cell = None
    for _ in range(6):
        set_input(inp, ("left",))
        kid.update(inp, scene.solids)
        scene._try_enter_vine()
        if kid.mode == "vine":
            break
    assert kid.mode == "vine", f"应进入攀附，实际 {kid.mode}"
    set_input(inp, ("left", "right"))   # 靠近 + 反方向同时按住
    scene._vine_update(inp)
    assert kid.mode == "normal", f"左右同按应以脱离为准，实际 {kid.mode}"
    scene._vine_reenter_block = 0   # 普通脱离设冷却；手动驱动需清掉再测"跳回"
    # 再向左跳回藤蔓 → 重新吸附（循环攀爬）
    for _ in range(6):
        set_input(inp, ("left",))
        kid.update(inp, scene.solids)
        scene._try_enter_vine()
        if kid.mode == "vine":
            break
    assert kid.mode == "vine", f"应能再次吸附（循环攀爬），实际 {kid.mode}"
    print("PASS 25 左右同按脱离 + 再次跳回吸附（循环攀爬）")

    # 26. 防穿墙：藤蔓下滑撞到下方固体 → 停在固体顶面，不穿墙
    scene.vines.clear()
    scene.vines[(20, 14)] = "right"   # 一段 2 格藤蔓，正下方放一块固体
    scene.vines[(20, 15)] = "right"
    scene.solids[:] = []
    scene.solids.append(pygame.Rect(21 * T, 16 * T, T, T))   # kid 吸附在藤蔓右缘 x=21*T，固体放其正下方
    kid.reset(21 * T + 8.0, 15 * T - config.KID_HEIGHT)
    kid.mode = "normal"
    scene._vine_cell = None
    entered = False
    for _ in range(8):
        set_input(inp, ("left",))
        kid.update(inp, scene.solids)
        scene._try_enter_vine()
        if kid.mode == "vine":
            entered = True
            break
    assert entered and kid.x == 21 * T, \
        f"应吸附藤蔓(20,15)右缘，实际 mode={kid.mode} x={kid.x}"
    for _ in range(40):
        set_input(inp)                     # 无输入 → 缓慢下滑，撞到下方固体停住
        scene._vine_update(inp)
    assert kid.mode == "vine", f"被固体挡住应仍在藤蔓上，实际 {kid.mode}"
    assert kid.y == 16 * T - config.KID_HEIGHT, \
        f"应停在固体顶面(16*T-21={16*T-config.KID_HEIGHT})，实际 y={kid.y}"
    print("PASS 26 藤蔓上下滑撞固体不穿墙（停在固体顶面）")

    # 27. 上方向键是死键：shift+上 无反应（普通模式不跳、藤蔓上保持不动）；shift 单独仍可跳
    scene.vines.clear()
    scene.vines[(11, 15)] = "right"
    scene.solids[:] = []
    for tx in range(25):
        scene.solids.append(pygame.Rect(tx * T, 17 * T, T, T))   # 只留地板
    scene.vine_barriers = scene._build_vine_barriers()
    kid.reset(96.0, 17 * T - config.KID_HEIGHT)
    kid.mode = "normal"
    scene._vine_cell = None
    for _ in range(5):
        set_input(inp)
        kid.update(inp, scene.solids + scene.vine_barriers)
    y0 = kid.y
    for _ in range(4):
        set_input(inp, ("jump", "up"))     # shift + 上 = 不应有任何反应
        kid.update(inp, scene.solids + scene.vine_barriers)
    assert kid.y == y0, f"shift+上 不应有任何反应，y {y0}->{kid.y}"
    set_input(inp)
    kid.update(inp, scene.solids + scene.vine_barriers)
    y0 = kid.y
    set_input(inp, ("jump",))              # shift 单独（先松开再按）仍应起跳
    kid.update(inp, scene.solids + scene.vine_barriers)
    assert kid.y < y0, f"shift 单独应起跳，y {y0}->{kid.y}"
    # 藤蔓上 shift+上：保持不动（不滑落）
    kid.reset(12 * T + 8.0, 15 * T - config.KID_HEIGHT)
    kid.mode = "normal"
    scene._vine_cell = None
    for _ in range(8):
        set_input(inp, ("left",))
        kid.update(inp, scene.solids + scene.vine_barriers)
        scene._try_enter_vine()
        if kid.mode == "vine":
            break
    assert kid.mode == "vine", f"应进入攀附，实际 {kid.mode}"
    y0 = kid.y
    for _ in range(4):
        set_input(inp, ("jump", "up"))
        scene._vine_update(inp)
    assert kid.y == y0, f"藤蔓上 shift+上 应保持不动，y {y0}->{kid.y}"
    print("PASS 27 上方向键是死键：shift+上 无反应（普通不跳 / 藤蔓不动）")

    # 28. 藤蔓攀爬面竖线实体碰撞：kid 撞上右缘竖线停在攀爬面吸附，穿不过藤蔓（左缘镜像）
    scene.vines.clear()
    scene.vines[(11, 14)] = "right"
    scene.vine_barriers = scene._build_vine_barriers()
    kid.reset(12 * T + 20.0, 14 * T - config.KID_HEIGHT)   # 右缘 x=384，从右侧撞入
    kid.mode = "normal"
    scene._vine_cell = None
    entered = False
    for _ in range(20):
        set_input(inp, ("left",))
        kid.update(inp, scene.solids + scene.vine_barriers)
        scene._try_enter_vine()
        if kid.mode == "vine":
            entered = True
            break
    assert entered and kid.x == 11 * T + T, \
        f"撞上右缘竖线应停在攀爬面吸附，实际 mode={kid.mode} x={kid.x}"
    scene.vines.clear()
    scene.vines[(11, 14)] = "left"                          # 左缘 x=352，从左侧撞入
    scene.vine_barriers = scene._build_vine_barriers()
    kid.reset(10 * T, 14 * T - config.KID_HEIGHT)
    kid.mode = "normal"
    scene._vine_cell = None
    entered = False
    for _ in range(20):
        set_input(inp, ("right",))
        kid.update(inp, scene.solids + scene.vine_barriers)
        scene._try_enter_vine()
        if kid.mode == "vine":
            entered = True
            break
    assert entered and kid.x == 11 * T - config.KID_WIDTH, \
        f"撞上左缘竖线应停在攀爬面吸附，实际 mode={kid.mode} x={kid.x}"
    print("PASS 28 藤蔓攀爬面竖线实体碰撞：撞到边缘吸附，穿不过藤蔓")

    # 29. 细网格像素砖块（free_tiles）是实体：16px 偏移的砖块照常承重/碰撞
    scene.vines.clear()
    scene.room.free_tiles.clear()
    scene.room.free_tiles[(11 * T + 16, 15 * T)] = "block_0"   # 右移 16px 的砖块
    scene.solids = scene.room.solid_rects()
    assert any(s.x == 11 * T + 16 and s.y == 15 * T and s.size == (T, T)
               for s in scene.solids), "free 砖块应生成 32×32 固体矩形"
    kid.reset(11 * T + 16 + 5.0, 15 * T - config.KID_HEIGHT - 4.0)  # 悬在砖顶上方
    kid.mode = "normal"
    scene._vine_cell = None
    for _ in range(10):
        set_input(inp)
        kid.update(inp, scene.solids)
    assert kid.on_ground and abs(kid.y - (15 * T - config.KID_HEIGHT)) < 2, \
        f"free 砖块应承重（kid.y={kid.y}，期望 {15*T - config.KID_HEIGHT}）"
    # 撞墙：从右向左走应被 free 砖块的右缘挡住
    kid.reset(11 * T + 16 + T + 4.0, 15 * T - config.KID_HEIGHT)
    kid.mode = "normal"
    scene._vine_cell = None
    for _ in range(10):
        set_input(inp, ("left",))
        kid.update(inp, scene.solids)
    assert abs(kid.x - (11 * T + 16 + T)) < 2, \
        f"free 砖块应挡墙（kid.x={kid.x}，右缘 {11*T+16+T}）"
    print("PASS 29 细网格 free 砖块：固体承重 + 撞墙阻挡")

    save.clear_save()   # PASS 14 的 _save_checkpoint 会写盘，结尾清掉保持封闭
    print("\nALL PHYSICS TESTS PASSED")


if __name__ == "__main__":
    main()
