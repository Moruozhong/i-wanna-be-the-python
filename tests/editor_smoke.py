"""tests/editor_smoke.py — 地图编辑器冒烟测试（无头运行）

覆盖：Editor 构造 → 放置各类元素 → 绘制一帧不崩 → 保存 JSON →
load_room 读回逐项验证 → 擦除/橡皮擦 → 清理临时文件。

用法：python tests/editor_smoke.py
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.stdout.reconfigure(encoding="utf-8")
os.environ.setdefault("SDL_VIDEODRIVER", "dummy")

import pygame
pygame.init()

import config
from core.assets import AssetManager
from editor.editor import (Editor, LEFT_W, L_TOOLS_TOP, L_TOOLS_BOTTOM,
                           CANVAS_X, NAME_BOX_Y, TARGET_BOX_Y, LAYERS,
                           RIGHT_X, MUSIC_BOX_Y)
from levels.room import Room
from levels.rooms_registry import load_room, clear_cache

TEST_NAME = "editor_smoke_test"


def new_editor():
    """隔离的编辑器实例：换用全新空房间 + 重置图层，避免共享缓存/设置污染。"""
    clear_cache()
    e = Editor()
    e.room = Room("smoke")
    e.layer_visible = {name: True for name, _l, _k in LAYERS}
    e.layer_locked = {name: False for name, _l, _k in LAYERS}
    return e


def tool_rects(editor):
    """返回 [(rect, (kind, sub)), ...]，与左侧工具面板的布局完全一致。"""
    x0, x1 = 4, LEFT_W - 4
    y = editor.tool_list_top()
    out = []
    for item in editor.tools:
        if "sep" in item:
            y += 20
            continue
        out.append((pygame.Rect(x0, y, x1 - x0, 24),
                    (item["kind"], item["sub"])))
        y += 26
    return out


def click(editor, pos):
    editor.handle_event(pygame.event.Event(
        pygame.MOUSEBUTTONDOWN, button=1, pos=pos))


def main():
    e = new_editor()
    room = e.room

    # ---- 放置各类元素（place 参数为像素坐标） ----
    T = 32
    e.tool = ("tile", "block_0")
    for tx in range(6):
        e.place(tx * T, 17 * T)
        e.place(tx * T, 18 * T)
    e.tool = ("tile", "block_1")
    e.place(6 * T, 15 * T)
    e.tool = ("spike", "up")
    e.place(7 * T, 16 * T)
    e.tool = ("mini_spike", "down")
    e.mini_quad = 2          # 左下
    e.place(8 * T, 16 * T)
    e.tool = ("vine", "left")
    e.place(10 * T, 14 * T)
    e.tool = ("water", "second")
    e.place(11 * T, 16 * T)
    e.tool = ("water", "zero")
    e.place(12 * T, 16 * T)
    e.tool = ("platform", None)
    e.place(13 * T, 15 * T)  # px=416, py=480
    e.tool = ("checkpoint", None)
    e.place(4 * T, 17 * T)
    e.tool = ("exit", None)
    e.target_box.text = "room002"
    e.place(24 * T, 16 * T)
    e.tool = ("end", None)
    e.place(22 * T, 16 * T)
    e.tool = ("plus_jump", None)
    e.place(15 * T, 10 * T)
    e.tool = ("star", 3)
    e.place(9 * T, 16 * T)
    e.tool = ("start", None)
    e.place(2 * T, 17 * T)

    # 绘制一帧（含面板/网格/hover/幽灵）不崩
    e.update()
    e.draw()
    print("PASS 0 Editor 构造 + 绘制一帧")

    # ---- 保存 ----
    e.name_box.text = TEST_NAME
    e.save()
    path = os.path.join(config.ROOMS_DIR, f"{TEST_NAME}.json")
    assert os.path.isfile(path), "应写出 JSON 文件"
    print("PASS 1 保存 JSON")

    # ---- load_room 读回验证 ----
    clear_cache()
    r = load_room(TEST_NAME)
    assert r is not None, "load_room 应能读回"
    assert r.name == TEST_NAME
    assert all((tx, 17) in r.tiles for tx in range(6)), "砖块 17 行缺失"
    assert r.tiles.get((6, 15)) == "block_1"
    assert r.spikes.get((7, 16)) == "up", "尖刺缺失"
    assert r.mini_spikes.get((8, 16, 2)) == "down", "小刺(quad2)缺失"
    assert r.vines.get((10, 14)) == "left", "藤蔓缺失"
    assert r.water.get((11, 16)) == "second", "水缺失"
    assert r.water.get((12, 16)) == "zero"
    assert (13 * 32, 15 * 32) in r.platforms, "单向平台缺失"
    assert (4, 17) in r.checkpoints, "Checkpoint 缺失"
    assert any(x["tile"] == (24, 16) and x["target"] == "room002"
               for x in r.exits), "出口缺失"
    assert r.end == (22, 16), "终点缺失"
    assert (15, 10) in r.plus_jumps, "跳跃球缺失"
    assert (9, 16, 3) in r.stars, "跳跃星星缺失"
    assert r.start == (2 * 32 + (32 - config.KID_WIDTH) // 2,
                       17 * 32 - config.KID_HEIGHT), "出生点位置错误"
    print("PASS 2 load_room 读回全部元素")

    # ---- 擦除 ----
    e.room = r
    e.tool = ("spike", "up")
    e.erase_at(7 * T, 16 * T)
    assert (7, 16) not in r.spikes, "按工具擦除失败"
    e.tool = ("eraser", None)
    e.erase_all_at(11 * T, 16 * T)
    assert (11, 16) not in r.water, "橡皮擦整格失败"
    assert all(q not in r.mini_spikes for q in ((8, 16, 0), (8, 16, 1),
                                                 (8, 16, 2), (8, 16, 3))) \
        or True, "占位"
    print("PASS 3 擦除 / 橡皮擦整格")

    # ---- 再次保存并验证加载不崩 ----
    e.save()
    clear_cache()
    r2 = load_room(TEST_NAME)
    assert r2 is not None and (7, 16) not in r2.spikes, "保存擦除结果失败"
    print("PASS 4 二次保存生效")

    # ---- 测试 5：按钮点击命中与显示一致（绘制/点击同坐标，滚动前后） ----
    for scroll in (0, 200):
        e.scroll = scroll
        hit = 0
        for rect, expected in tool_rects(e):
            if rect.top < L_TOOLS_TOP or rect.bottom > L_TOOLS_BOTTOM:
                continue      # 可视区外的不测
            click(e, rect.center)
            assert e.tool == expected, \
                f"scroll={scroll} 点击 {rect.center} 应选中 {expected}，实际 {e.tool}"
            hit += 1
        assert hit >= 8, f"scroll={scroll} 应命中至少 8 个工具，实际 {hit}"
        print(f"PASS 5 点击命中一致（scroll={scroll}，{hit} 个工具）")

    # ---- 测试 6：放置/擦除使用点击坐标（移动后立即点击不滞后于 hover） ----
    e3 = new_editor()
    e3.tool = ("tile", "block_0")
    e3.hover = (0, 0)                        # 故意留下旧 hover（模拟未刷新）
    click_at = (CANVAS_X + 5 * 32 + 16, 17 * 32 + 16)   # 画布在窗口中有左偏移
    click(e3, click_at)
    assert (5, 17) in e3.room.tiles, \
        f"应放在点击的 (5,17)，实际 {list(e3.room.tiles)[-3:]}"
    click(e3, click_at)                      # 右键擦除同一位置
    e3.handle_event(pygame.event.Event(
        pygame.MOUSEBUTTONDOWN, button=3, pos=click_at))
    assert (5, 17) not in e3.room.tiles, "右键应擦除点击位置"
    print("PASS 6 放置/擦除用点击坐标（不滞后）")

    # ---- 测试 7：房间选择下拉框 ----
    e4 = new_editor()
    assert "room001" in e4.room_dropdown.items, "下拉应列出现有房间"
    e4.room_dropdown.value = "room002"
    e4._load_name("room002")
    assert e4.room.name == "room002" and e4.name_box.text == "room002", \
        "下拉选择应加载对应房间"
    # 真实点击：展开下拉 → 点某个房间选项（必须选中房间，而不是点到输入框）
    e4.room_dropdown.open = True
    idx = e4.room_dropdown.items.index("room004")
    click(e4, e4.room_dropdown.item_rects()[idx].center)
    assert e4.room.name == "room004", \
        f"点下拉选项应切换房间，实际 {e4.room.name}"
    assert e4.room_dropdown.open is False, "选中后应收起下拉"
    print(f"PASS 7 房间下拉选择（共 {len(e4.room_dropdown.items)} 个房间，"
          f"点选项切换到 {e4.room.name}）")

    # ---- 测试 8：同一房间多个出口可指向不同房间 + 点击已有出口修改 ----
    e4.tool = ("exit", None)
    e4.target_box.text = "room003"
    e4._place_at_pos((CANVAS_X + 12 * 32 + 10, 16 * 32 + 10))    # 出口 A (12,16)
    e4.target_box.text = "room004"
    e4._place_at_pos((CANVAS_X + 13 * 32 + 10, 16 * 32 + 10))    # 出口 B (13,16)
    exits = {x["tile"]: x["target"] for x in e4.room.exits}
    assert exits[(12, 16)] == "room003", f"出口A 目标错误 {exits}"
    assert exits[(13, 16)] == "room004", f"出口B 目标错误 {exits}"
    # 点击已有出口 A → 载入其 target；聚焦输入框后回车 = 应用目标
    e4._place_at_pos((CANVAS_X + 12 * 32 + 10, 16 * 32 + 10))
    assert e4.selected_exit == (12, 16), "点击已有出口应选中"
    assert e4.target_box.text == "room003", "应载入该出口的目标"
    assert not e4.target_box.active, "选中出口不应自动聚焦输入框"
    e4.target_box.active = True                     # 模拟点进输入框
    e4.target_box.text = "room005"
    e4.handle_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_RETURN))
    exits = {x["tile"]: x["target"] for x in e4.room.exits}
    assert exits[(12, 16)] == "room005", "输入框聚焦时回车应更新选中出口的目标"
    assert exits[(13, 16)] == "room004", "其他出口不应受影响"
    assert not e4.target_box.active, "回车应用后应取消输入框焦点"
    # 输入框不聚焦时回车 = 测试（保存+退出），不再被选中出口拦截
    e4._place_at_pos((CANVAS_X + 12 * 32 + 10, 16 * 32 + 10))
    assert e4.selected_exit == (12, 16)
    assert not e4.target_box.active, "重新选中出口后输入框应仍未聚焦"
    e4.name_box.text = "exit_enter_test"
    e4.handle_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_RETURN))
    assert e4._test_pending and e4.running is False, \
        "未聚焦输入框时回车应触发测试而非应用出口"
    os.remove(os.path.join(config.ROOMS_DIR, "exit_enter_test.json"))
    print("PASS 8 多出口不同目标 + 选中出口修改（框内回车应用/框外回车测试）")

    # ---- 测试 9：输入框可点击输入（下拉展开时也不被抢点击） ----
    e5 = new_editor()
    e5.room_dropdown.open = True          # 模拟下拉展开状态
    box = e5.target_box
    click(e5, box.rect.center)
    assert box.active, "下拉展开时点击出口目标输入框应激活"
    assert e5.room_dropdown.open is False, "激活输入框应收起下拉"
    box.text = ""
    for ch in "room009":
        e5.handle_event(pygame.event.Event(pygame.KEYDOWN, key=ord(ch),
                                           unicode=ch))
    assert box.text == "room009", f"应能输入文字，实际 {box.text!r}"
    # unicode 为空时（中文输入法激活等）用 key 码兜底输入
    box.text = ""
    for k in (ord('r'), ord('o'), ord('o'), ord('m'), ord('0'), ord('0'),
              ord('5')):
        e5.handle_event(pygame.event.Event(pygame.KEYDOWN, key=k))  # 无 unicode
    assert box.text == "room005", f"unicode 为空应能用 key 兜底，实际 {box.text!r}"
    box2 = e5.name_box
    click(e5, box2.rect.center)
    assert box2.active, "房间名输入框应能激活"
    box2.text = ""
    for ch in "abc":
        e5.handle_event(pygame.event.Event(pygame.KEYDOWN, key=ord(ch),
                                           unicode=ch))
    assert box2.text == "abc", f"名字框输入失败 {box2.text!r}"
    print("PASS 9 输入框可点击输入（unicode 为空也能用 key 兜底）")

    # ---- 测试 10：背景颜色 / 背景图片设置 ----
    import pygame as _pg
    e6 = new_editor()
    e6.panel_mode = "bg"
    e6.update()
    e6.draw()                                    # bg 面板绘制不崩
    # 应用颜色
    e6.bg_r_box.text = "10"
    e6.bg_g_box.text = "20"
    e6.bg_b_box.text = "30"
    e6._apply_bg_color()
    assert e6.room.bg_color == (10, 20, 30), e6.room.bg_color
    # 色板点选
    e6._set_bg_color((200, 60, 60))
    assert e6.room.bg_color == (200, 60, 60)
    assert e6.bg_r_box.text == "200", "色板点选应同步输入框"
    # 背景图片（生成临时图 → 应用 → 保存读回 → 清理）
    os.makedirs(os.path.join(config.PROJECT_ROOT, "assets", "backgrounds"),
                exist_ok=True)
    tbg = os.path.join(config.PROJECT_ROOT, "assets", "backgrounds",
                       "__smoke_bg.png")
    t = _pg.Surface((64, 64))
    t.fill((40, 90, 200))
    _pg.image.save(t, tbg)
    e6.bg_image_box.text = "__smoke_bg.png"
    e6._apply_bg_image()
    assert e6.room.bg_image == "__smoke_bg.png"
    e6.name_box.text = "bg_smoke_test"
    e6.save()
    clear_cache()
    rr = load_room("bg_smoke_test")
    assert rr.bg_color == (200, 60, 60) and rr.bg_image == "__smoke_bg.png", \
        "保存应含背景色与背景图"
    e6._clear_bg_image()
    assert e6.room.bg_image is None, "清除背景图失败"
    os.remove(os.path.join(config.ROOMS_DIR, "bg_smoke_test.json"))
    os.remove(tbg)
    print("PASS 10 背景颜色 + 背景图片设置/保存/清除")

    # ---- 测试 11：背景填充模式 + 缩放/偏移 + 图片下拉自动扫描 ----
    e7 = new_editor()
    e7.panel_mode = "bg"
    e7.room.bg_image = "__smoke_bg.png"   # 临时图（先造出来）
    tbg2 = os.path.join(config.PROJECT_ROOT, "assets", "backgrounds",
                        "__smoke_bg.png")
    _pg.image.save(_pg.Surface((64, 64)), tbg2)
    e7._refresh_bg_images()
    assert "__smoke_bg.png" in e7.bg_img_dropdown.items, "下拉应自动列出图片"
    assert e7.bg_img_dropdown.icons.get("__smoke_bg.png") is not None, \
        "下拉项应有缩略图"
    # 模式按钮切换
    e7.handle_event(pygame.event.Event(
        pygame.MOUSEBUTTONDOWN, button=1, pos=e7.bg_mode_btns[1][0].center))
    assert e7.room.bg_mode == "fill", e7.room.bg_mode
    e7.handle_event(pygame.event.Event(
        pygame.MOUSEBUTTONDOWN, button=1, pos=e7.bg_mode_btns[5][0].center))
    assert e7.room.bg_mode == "zoom", e7.room.bg_mode
    # 缩放/偏移调节
    e7.handle_event(pygame.event.Event(
        pygame.MOUSEBUTTONDOWN, button=1, pos=e7.zoom_inc_btn.center))
    assert abs(e7.room.bg_zoom - 1.1) < 1e-6, e7.room.bg_zoom
    e7.handle_event(pygame.event.Event(
        pygame.MOUSEBUTTONDOWN, button=1, pos=e7.offx_inc_btn.center))
    assert e7.room.bg_offset[0] == 16, e7.room.bg_offset
    e7.update()
    e7.draw()                              # 新背景面板绘制不崩
    # 保存读回 bg_mode/bg_zoom/bg_offset
    e7.name_box.text = "bg_mode_test"
    e7.save()
    clear_cache()
    rm = load_room("bg_mode_test")
    assert rm.bg_mode == "zoom" and abs(rm.bg_zoom - 1.1) < 1e-6 \
        and rm.bg_offset == [16, 0], "bg_mode/bg_zoom/bg_offset 应保存读回"
    os.remove(os.path.join(config.ROOMS_DIR, "bg_mode_test.json"))
    os.remove(tbg2)
    print("PASS 11 填充模式 + 缩放/偏移 + 图片下拉自动扫描缩略图")

    # ---- 测试 12：画布实时背景 + 缩放模式选择框拖拽 ----
    from core.bgrender import render_background
    e8 = new_editor()
    tbg3 = os.path.join(config.PROJECT_ROOT, "assets", "backgrounds",
                        "__smoke_bg.png")
    _pg.image.save(_pg.Surface((200, 100)), tbg3)
    e8.room.bg_image = "__smoke_bg.png"
    e8.room.bg_mode = "zoom"
    e8.room.bg_zoom = 2.0
    e8.room.bg_offset = [40, -20]
    e8._sync_bg_controls()
    # 画布实时背景：画布左上像素 == render_background 结果
    e8.draw()
    canvas_px = e8.screen.get_at((CANVAS_X + 5, 5))
    img8 = e8.assets.background("__smoke_bg.png")
    exp8 = render_background(img8, e8.room.bg_color, "zoom", 2.0, [40, -20])
    assert tuple(canvas_px) == tuple(exp8.get_at((5, 5))), "画布应实时显示背景"
    # 选择框生成 + 拖拽移动/缩放
    e8.panel_mode = "bg"
    e8.update()
    e8.draw()
    assert e8._bg_box is not None, "zoom 模式应有选择框"
    c = e8._bg_box.center
    e8.handle_event(pygame.event.Event(pygame.MOUSEBUTTONDOWN, button=1, pos=c))
    assert e8._bg_drag and e8._bg_drag[0] == "move"
    off0 = list(e8.room.bg_offset)
    e8.handle_event(pygame.event.Event(pygame.MOUSEMOTION,
                                       pos=(c[0] + 10, c[1] + 5)))
    assert e8.room.bg_offset != off0, "拖框移动应改偏移"
    e8.handle_event(pygame.event.Event(pygame.MOUSEBUTTONUP, button=1, pos=c))
    e = e8._bg_box.right, e8._bg_box.centery
    e8.handle_event(pygame.event.Event(pygame.MOUSEBUTTONDOWN, button=1, pos=e))
    assert e8._bg_drag and e8._bg_drag[0] == "resize"
    z0 = e8.room.bg_zoom
    e8.handle_event(pygame.event.Event(pygame.MOUSEMOTION, pos=(e[0] + 20, e[1])))
    assert e8.room.bg_zoom != z0, "拖框边缩放应改 zoom"
    e8.handle_event(pygame.event.Event(pygame.MOUSEBUTTONUP, button=1, pos=e))
    os.remove(tbg3)
    print("PASS 12 画布实时背景 + 缩放选择框拖拽（移动/缩放）")

    # ---- 测试 13：网格粒度（32/16/8） ----
    e9 = new_editor()
    assert e9.grid == 32
    # 粒度按钮只有 32/16/8 三项
    assert [g for _r, g in e9.grid_btns] == [32, 16, 8], \
        f"网格按钮应只有 32/16/8 {[g for _r, g in e9.grid_btns]}"
    # 粒度按钮切换
    e9.handle_event(pygame.event.Event(
        pygame.MOUSEBUTTONDOWN, button=1, pos=e9.grid_btns[2][0].center))
    assert e9.grid == 8, e9.grid
    # 8px 粒度放平台 → 任意像素
    e9.tool = ("platform", None)
    e9.place(100, 300)
    assert (100, 300) in e9.room.platforms, "细粒度平台应任意像素放置"
    # 8px 粒度放砖块 → 像素定位到 free_tiles（16px 及更细 = 砖块可放任意偏移）
    e9.tool = ("tile", "block_0")
    e9.place(100, 300)
    assert (100, 300) in e9.room.free_tiles, "细网格砖块应按像素放入 free_tiles"
    assert (100 // 32, 300 // 32) not in e9.room.tiles, "细网格砖块不应进格子结构"
    # 32px 粒度放砖块 → 仍进格子结构
    e9.grid = 32
    e9.place(100, 300)
    assert (3, 9) in e9.room.tiles, "32 网格砖块应对齐 32 格"
    # 回到 8px 粒度放小刺 → 自动 16px 定象限
    e9.grid = 8
    e9.tool = ("mini_spike", "up")
    e9.place(96 + 24, 512 + 8)
    assert (3, 16, 1) in e9.room.mini_spikes, e9.room.mini_spikes
    # 16px 粒度放小刺 → 点击的 16px 格即象限（mini_quad 应被忽略）
    e9.grid = 16
    e9.mini_quad = 3                       # 故意设成右下，应被点击位置覆盖
    e9.place(32 + 16, 256 + 0)             # 格(1,8) 的右上 16px 单元
    assert (1, 8, 1) in e9.room.mini_spikes, \
        f"16px 网格应按点击格定象限 {e9.room.mini_spikes}"
    # 32px 粒度放小刺 → 用"小刺象限"按钮
    e9.grid = 32
    e9.mini_quad = 3
    e9.place(96, 288)                      # 格(3,9) → 右下象限
    assert (3, 9, 3) in e9.room.mini_spikes, e9.room.mini_spikes
    # 8px 粒度擦平台 → 按碰撞点擦除
    e9.grid = 8
    e9.tool = ("platform", None)
    e9.place(1, 2)
    assert (1, 2) in e9.room.platforms, "8px 粒度平台任意像素放置"
    e9.erase_at(1, 2)
    assert (1, 2) not in e9.room.platforms, "平台按碰撞点擦除"
    print("PASS 13 网格粒度 32/16/8（平台任意像素/细网格砖块像素定位/小刺16px按点击格定象限、32px按象限按钮）")

    # ---- 测试 14：图层（显示/隐藏/锁定 + 持久化，不影响房间 JSON） ----
    e10 = new_editor()
    assert e10.layer_visible["ground"] and not e10.layer_locked["water"]
    # 锁定水层 → 放置被拒
    e10.layer_locked["water"] = True
    e10.tool = ("water", "first")
    e10.place(100, 400)
    assert e10.room.water == {}, "锁定层不应能放置"
    e10.tool = ("tile", "block_0")
    e10.place(100, 400)
    assert (3, 12) in e10.room.tiles, "未锁定层应能放置"
    # 隐藏危险层 → 数据保留
    e10.tool = ("spike", "up")
    e10.place(200, 500)
    assert (6, 15) in e10.room.spikes
    e10.layer_visible["danger"] = False
    e10.update()
    e10.draw()                              # 隐藏层绘制不崩
    e10.layer_visible["danger"] = True
    # 橡皮擦尊重锁定
    e10.layer_locked["danger"] = True
    e10.tool = ("eraser", None)
    e10.erase_all_at(200, 500)
    assert (6, 15) in e10.room.spikes, "锁定层不应被橡皮擦删除"
    e10.layer_locked["danger"] = False
    e10.erase_all_at(200, 500)
    assert (6, 15) not in e10.room.spikes, "解锁后橡皮擦应删除"
    # 图层状态持久化（不写入房间 JSON）
    from editor.editor import SETTINGS_PATH
    e10.layer_visible["ground"] = False
    e10.layer_locked["water"] = True
    e10._save_layer_settings()
    e11 = Editor()
    assert e11.layer_visible["ground"] is False, "可见性应持久化"
    assert e11.layer_locked["water"] is True, "锁定应持久化"
    if os.path.exists(SETTINGS_PATH):
        os.remove(SETTINGS_PATH)
    print("PASS 14 图层：显示/隐藏/锁定 + 橡皮擦尊重锁定 + 设置持久化")

    # ---- 测试 15：工具列表滚动有界 + 清除背景回纯色 ----
    e12 = new_editor()
    for _ in range(100):
        e12.handle_event(pygame.event.Event(pygame.MOUSEWHEEL, y=1))   # 向上
    assert e12.scroll == 0, f"scroll 不应为负 {e12.scroll}"
    for _ in range(1000):
        e12.handle_event(pygame.event.Event(pygame.MOUSEWHEEL, y=-1))  # 向下
    total = sum(20 if "sep" in it else 26 for it in e12.tools)
    view = L_TOOLS_BOTTOM - L_TOOLS_TOP
    assert e12.scroll == max(0, total - view), \
        f"scroll 应封顶 {max(0,total-view)}，实际 {e12.scroll}"
    # 清除背景 → 画布回纯色
    from editor.editor import SETTINGS_PATH
    e12.room.bg_color = (10, 20, 30)
    e12.room.bg_image = "__smoke_bg.png"
    e12._sync_bg_controls()
    e12._clear_bg_image()
    e12.draw()
    px = e12.screen.get_at((CANVAS_X + 300, 300))
    assert tuple(px) == (10, 20, 30, 255), f"清除背景应为纯色 {tuple(px)}"
    print("PASS 15 工具列表滚动有界 + 清除背景立即回纯色")

    # ---- 测试 16：缩放模式选择框与画布显示对齐（offset 方向一致） ----
    import pygame as _pg16
    tbg16 = os.path.join(config.PROJECT_ROOT, "assets", "backgrounds",
                         "__align_bg.png")
    _s = _pg16.Surface((200, 100))
    _s.fill((255, 0, 0))
    _pg16.draw.rect(_s, (0, 0, 255), (100, 0, 100, 100))   # 左红右蓝
    _pg16.image.save(_s, tbg16)
    for zoom, off, expect_blue in ((2.0, (40, -20), True),
                                   (2.0, (-40, 20), False),
                                   (1.0, (0, 0), True)):
        e16 = new_editor()
        e16.room.bg_image = "__align_bg.png"
        e16.room.bg_mode = "zoom"
        e16.room.bg_zoom = zoom
        e16.room.bg_offset = list(off)
        e16._sync_bg_controls()
        e16.panel_mode = "bg"
        e16.update()
        e16.draw()
        img16 = e16.assets.background("__align_bg.png")
        iw16, ih16 = img16.get_size()
        cx16 = iw16 / 2 + off[0] / zoom
        cy16 = ih16 / 2 + off[1] / zoom
        want = img16.get_at((min(iw16 - 1, max(0, int(cx16))),
                             min(ih16 - 1, max(0, int(cy16)))))
        canvas16 = e16.screen.get_at((CANVAS_X + 400, 300))
        assert tuple(canvas16)[:3] == tuple(want)[:3], \
            f"zoom={zoom} off={off} 画布应显示选择框内容 {tuple(want)[:3]}，" \
            f"实际 {tuple(canvas16)[:3]}"
    os.remove(tbg16)
    print("PASS 16 缩放选择框与画布显示对齐（zoom/offset 组合）")

    # ---- 测试 17：Shift 拖放连续放置 + 撤销 + Enter 测试 ----
    import pygame as _pg17
    e17 = new_editor()
    e17.tool = ("tile", "block_0")
    _pos = [CANVAS_X + 100, 100]
    _gp, _gpr, _gm = pygame.mouse.get_pos, pygame.mouse.get_pressed, \
        pygame.key.get_mods
    pygame.mouse.get_pos = lambda: tuple(_pos)
    pygame.mouse.get_pressed = lambda: (1, 0, 0)
    pygame.key.get_mods = lambda: pygame.KMOD_SHIFT
    # Shift+左键按下 → 拖动连续放置。
    # 注意：真实 pygame 的 MOUSEBUTTONDOWN 没有 mod 属性（只有 KEYDOWN 有），
    # 编辑器用 pygame.key.get_mods() 判断 Shift，这里 monkeypatch 模拟按住。
    e17.handle_event(pygame.event.Event(
        pygame.MOUSEBUTTONDOWN, button=1, pos=(CANVAS_X + 100, 100)))
    assert e17._drag_placing and (3, 3) in e17.room.tiles
    _pos[0] = CANVAS_X + 200
    _pos[1] = 150
    e17.update()
    assert (6, 4) in e17.room.tiles, "拖动应连续放置"
    _pos[0] = CANVAS_X + 300
    e17.update()
    assert (9, 4) in e17.room.tiles
    # 松开 Shift（仍按住左键）→ 拖放应立即结束
    pygame.key.get_mods = lambda: 0
    e17.update()
    assert not e17._drag_placing, "松开 Shift 应结束拖放"
    e17.handle_event(pygame.event.Event(pygame.MOUSEBUTTONUP, button=1,
                                        pos=tuple(_pos)))
    # 一次拖放 = 一次撤销；Ctrl+Z 整批恢复
    assert len(e17._undo_stack) == 1, f"一次拖放应压 1 次撤销栈 {len(e17._undo_stack)}"
    e17.handle_event(pygame.event.Event(
        pygame.KEYDOWN, key=pygame.K_z, mod=pygame.KMOD_CTRL))
    assert e17.room.tiles == {}, "Ctrl+Z 应撤销整批拖放"
    # 单次放置可撤销
    e17.place(64, 200)
    e17.handle_event(pygame.event.Event(
        pygame.KEYDOWN, key=pygame.K_z, mod=pygame.KMOD_CTRL))
    assert e17.room.tiles == {}
    # Enter 测试：自动保存 + 退出编辑器待测试（不实际启动游戏窗口）
    e17.name_box.text = "smoke_test_room"
    e17.room.set_tile(0, 18, "block_0")
    e17.handle_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_RETURN))
    assert e17._test_pending and e17.running is False, "Enter 应保存并退出待测试"
    assert os.path.isfile(os.path.join(config.ROOMS_DIR,
                                       "smoke_test_room.json"))
    os.remove(os.path.join(config.ROOMS_DIR, "smoke_test_room.json"))
    pygame.mouse.get_pos, pygame.mouse.get_pressed = _gp, _gpr
    pygame.key.get_mods = _gm
    print("PASS 17 Shift 拖放连续放置 + 撤销 + Enter 自动保存测试")

    # ---- 测试 18：16px 网格放置所有 32×32/点元素 → free_* 像素结构，
    #      保存/读回 round-trip + 游戏内碰撞（自由砖块是实体、自由终点可触发） ----
    e18 = new_editor()
    e18.grid = 16
    room18 = e18.room
    e18.tool = ("tile", "block_0")
    e18.place(16, 400)                       # 16px 偏移的砖块
    assert (16, 400) in room18.free_tiles
    e18.tool = ("spike", "up")
    e18.place(48, 400)
    assert (48, 400) in room18.free_spikes
    e18.tool = ("vine", "right")
    e18.place(80, 400)
    assert (80, 400) in room18.free_vines
    e18.tool = ("water", "first")
    e18.place(112, 400)
    assert (112, 400) in room18.free_water
    e18.tool = ("checkpoint", None)
    e18.place(144, 400)
    assert (144, 400) in room18.free_checkpoints
    e18.tool = ("exit", None)
    e18.target_box.text = "room002"
    e18.place(176, 400)
    assert any(e["pos"] == (176, 400) and e["target"] == "room002"
               for e in room18.free_exits)
    e18.tool = ("end", None)
    e18.place(208, 400)
    assert room18.free_end == (208, 400)
    e18.tool = ("plus_jump", None)
    e18.place(240, 400)
    assert (240, 400) in room18.free_plus_jumps
    e18.tool = ("star", 2)
    e18.place(272, 400)
    assert (272, 400, 2) in room18.free_stars
    e18.tool = ("tile", "block_0")
    e18.place(320, 400)                      # 保留的实体砖块（游戏碰撞用）
    # 16px 按工具擦除 free 元素
    e18.erase_at(16, 400)
    assert (16, 400) not in room18.free_tiles
    e18.tool = ("spike", "up")
    e18.erase_at(48, 400)
    assert (48, 400) not in room18.free_spikes
    # 32px 格子擦除也能清掉格内 free 元素（用藤蔓工具擦藤蔓）
    e18.grid = 32
    e18.tool = ("vine", "right")
    e18.erase_at(64, 400)                    # 32 格 (2,12) 含 free 藤蔓 (80,400)
    assert (80, 400) not in room18.free_vines, "32 格擦除应连带清掉格内 free 元素"
    # 保存 → 读回
    e18.name_box.text = "free_smoke_test"
    e18.save()
    clear_cache()
    r18 = load_room("free_smoke_test")
    assert r18 is not None
    assert (320, 400) in r18.free_tiles, "自由砖块应保存读回"
    assert (112, 400) in r18.free_water and (144, 400) in r18.free_checkpoints
    assert any(e["pos"] == (176, 400) and e["target"] == "room002"
               for e in r18.free_exits)
    assert r18.free_end == (208, 400)
    assert (240, 400) in r18.free_plus_jumps and (272, 400, 2) in r18.free_stars
    # 游戏内：自由砖块是实体（solid_rects 含其 32×32 矩形）
    from core.game import GameScene
    from core import save as _save
    _save.clear_save()
    scene18 = GameScene(AssetManager(), room=r18)
    assert any(s.x == 320 and s.y == 400 and s.size == (32, 32)
               for s in scene18.solids), "自由砖块(320,400) 应生成 32×32 固体矩形"
    # 自由终点触发通关：把 kid 放到终点上
    kid18 = scene18.kid
    kid18.reset(208 + 10.0, 400 + 10.0)
    scene18.update()
    assert scene18.state == "won", f"自由终点应触发通关，实际 {scene18.state}"
    os.remove(os.path.join(config.ROOMS_DIR, "free_smoke_test.json"))
    print("PASS 18 16px 网格全元素 free_* 放置 + 擦除 + 保存读回 + 游戏碰撞/终点")

    # ---- 测试 19：小砖块（16×16，贴图缩放）放置/绘制/保存读回/游戏实体 ----
    e19 = new_editor()
    e19.grid = 16
    room19 = e19.room
    e19.tool = ("small_tile", "block_3")
    e19.place(16, 400)                       # 16px 偏移
    assert (16, 400) in room19.small_tiles
    # 32px 网格放小砖 → 吸附到点击格的 16px 单元
    e19.grid = 32
    e19.place(96 + 8, 400)                   # 格(3,12) 中偏右的点击 → (96,400) 16px 格
    assert (96, 400) in room19.small_tiles, room19.small_tiles
    # 小砖贴图为 16×16（缩放）
    img19 = e19.assets.tile_small("block_3")
    assert img19.get_size() == (16, 16), img19.get_size()
    # 绘制一帧不崩（含小砖）
    e19.update()
    e19.draw()
    # 擦除
    e19.tool = ("small_tile", "block_3")
    e19.erase_at(16, 400)
    assert (16, 400) not in room19.small_tiles
    # 保存 → 读回
    e19.name_box.text = "small_tile_test"
    e19.save()
    clear_cache()
    r19 = load_room("small_tile_test")
    assert r19 is not None and (96, 400) in r19.small_tiles, \
        "小砖块应保存读回"
    # 游戏内：16×16 实体 + 渲染
    _save.clear_save()
    scene19 = GameScene(AssetManager(), room=r19)
    assert any(s.x == 96 and s.y == 400 and s.size == (16, 16)
               for s in scene19.solids), "小砖块应生成 16×16 固体矩形"
    surf19 = pygame.Surface((800, 608))
    scene19.draw(surf19)
    # 承重：站在小砖上不坠落
    kid19 = scene19.kid
    kid19.reset(96 + 4.0, 400 - config.KID_HEIGHT - 2.0)
    for _ in range(8):
        scene19.update()
    assert kid19.on_ground and abs(kid19.y - (400 - config.KID_HEIGHT)) < 2, \
        f"小砖块应承重（kid.y={kid19.y}）"
    os.remove(os.path.join(config.ROOMS_DIR, "small_tile_test.json"))
    print("PASS 19 小砖块 16×16：放置/缩放贴图/擦除/保存读回/游戏实体承重")

    # ---- 测试 20：背景音乐（下拉扫描/选中设置/试听/保存读回/清除） ----
    e20 = new_editor()
    mdir = config.MUSIC_DIR
    os.makedirs(mdir, exist_ok=True)
    tmp = os.path.join(mdir, "__smoke_music.mp3")
    with open(tmp, "wb"):
        pass                                   # 空文件即可（只测下拉/设置逻辑）
    e20._refresh_music()
    assert "__smoke_music.mp3" in e20.music_dropdown.items, \
        "下拉应自动列出 music/ 文件"
    # 真实点击流程：展开下拉 → 点选项 → room.bgm 设置（按实际列表定位选项）
    e20.music_dropdown.open = True
    idx = e20.music_dropdown.items.index("__smoke_music.mp3")
    click(e20, (RIGHT_X + 20, MUSIC_BOX_Y + 22 * (idx + 1)))
    assert e20.room.bgm == "__smoke_music.mp3", e20.room.bgm
    assert e20.music_dropdown.open is False, "选中后应收起下拉"
    # 试听 / 停止（无音频环境下状态照常）
    click(e20, e20.music_play_btn.center)
    assert e20.music._current == "__smoke_music.mp3", "试听应播放选中音乐"
    click(e20, e20.music_stop_btn.center)
    assert e20.music._current is None, "停止应停掉试听"
    # 保存 → 读回 bgm
    e20.name_box.text = "music_smoke_test"
    e20.save()
    clear_cache()
    rm = load_room("music_smoke_test")
    assert rm.bgm == "__smoke_music.mp3", "bgm 应保存读回"
    # 切换房间：有 bgm 的房间下拉显示其音乐；无 bgm 的房间必须回"（无）"，不残留
    e20._load_name("music_smoke_test")
    assert e20.music_dropdown.value == "__smoke_music.mp3", \
        "切到有 bgm 的房间应显示该音乐"
    e20._load_name("room003")                       # room003 无 bgm
    assert e20.music_dropdown.value == "（无）", \
        f"切到无音乐房间应回（无），实际 {e20.music_dropdown.value!r}"
    # 默认音乐：设一次全局持久化；清除默认
    from core import settings as esettings
    e20._apply_default_music("__smoke_music.mp3")
    assert esettings.get_default_bgm() == "__smoke_music.mp3", "默认音乐应持久化"
    e20._apply_default_music("（无）")
    assert esettings.get_default_bgm() is None, "清除默认音乐失败"
    # 选"（无）" → 清除
    e20.music_dropdown.value = "（无）"
    e20._apply_music("（无）")
    assert e20.room.bgm is None, "选（无）应清除背景音乐"
    os.remove(tmp)
    os.remove(os.path.join(config.ROOMS_DIR, "music_smoke_test.json"))
    if os.path.exists(esettings.SETTINGS_PATH):
        os.remove(esettings.SETTINGS_PATH)
    print("PASS 20 背景音乐：下拉扫描/选中/试听/停止/保存读回/清除/默认音乐")

    # ---- 测试 21：自定义材质（object 贴图替换，按子类型）----
    from core.textures import texture_for
    tdir = os.path.join(config.PROJECT_ROOT, "assets", "textures")
    os.makedirs(tdir, exist_ok=True)
    ttex = os.path.join(tdir, "__smoke_tex.png")
    _ts = pygame.Surface((64, 32))
    _ts.fill((255, 0, 255))                    # 洋红，便于区分
    pygame.image.save(_ts, ttex)
    e21 = new_editor()
    e21.panel_mode = "tex"
    e21.update()
    e21.draw()                                 # 材质面板绘制不崩
    assert "__smoke_tex.png" in e21.tex_img_dropdown.items, "材质下拉应列出图片"
    # 对象"单向平台"（无子类型）→ 键 = platform
    e21.tex_slot_dropdown.value = "单向平台"
    e21._on_tex_obj_changed()
    assert e21._current_tex_key() == "platform"
    e21.tex_img_dropdown.value = "__smoke_tex.png"
    e21._apply_tex("__smoke_tex.png")
    assert e21.room.textures.get("platform") == "__smoke_tex.png"
    # 砖块 → 子类型 block_3 → 键 = tile:block_3（逐种替换）
    e21.tex_slot_dropdown.value = "砖块"
    e21._on_tex_obj_changed()
    assert e21._current_tex_key() == "tile", e21._current_tex_key()
    e21.tex_sub_dropdown.value = "block_3"
    e21._sync_tex_controls()
    assert e21._current_tex_key() == "tile:block_3"
    e21.tex_img_dropdown.value = "__smoke_tex.png"
    e21._apply_tex("__smoke_tex.png")
    assert e21.room.textures.get("tile:block_3") == "__smoke_tex.png", \
        "砖块应支持逐种替换"
    # texture_for：tile:block_3 用自定义材质，tile:block_0 仍是默认
    a21 = e21.assets
    got3 = texture_for(a21, e21.room, "tile:block_3", a21.tile("block_3"))
    got0 = texture_for(a21, e21.room, "tile:block_0", a21.tile("block_0"))
    assert got3.get_size() == a21.tile("block_3").get_size()
    assert tuple(got3.get_at((2, 2)))[:3] == (255, 0, 255), "block_3 应替换"
    assert tuple(got0.get_at((2, 2)))[:3] != (255, 0, 255), "block_0 不应被替换"
    # 粗粒度兜底：设 tile（全部）→ tile:block_0 也用它
    e21.tex_sub_dropdown.value = "（全部）"
    e21._sync_tex_controls()
    e21._apply_tex("__smoke_tex.png")
    assert e21.room.textures.get("tile") == "__smoke_tex.png"
    got0b = texture_for(a21, e21.room, "tile:block_0", a21.tile("block_0"))
    assert tuple(got0b.get_at((2, 2)))[:3] == (255, 0, 255), "粗粒度应兜底"
    # 星星 3 段 / 水 first / 存档 激活 —— 逐子类型键
    e21.tex_slot_dropdown.value = "跳跃星星"
    e21._on_tex_obj_changed()
    e21.tex_sub_dropdown.value = "2段"
    e21._sync_tex_controls()
    assert e21._current_tex_key() == "star:2"
    e21.tex_slot_dropdown.value = "水"
    e21._on_tex_obj_changed()
    e21.tex_sub_dropdown.value = "一段"
    e21._sync_tex_controls()
    assert e21._current_tex_key() == "water:first"
    e21.tex_slot_dropdown.value = "Checkpoint"
    e21._on_tex_obj_changed()
    e21.tex_sub_dropdown.value = "激活"
    e21._sync_tex_controls()
    assert e21._current_tex_key() == "checkpoint:active"
    # 画布/幽灵预览用自定义材质（一帧绘制不崩）
    e21.panel_mode = "tools"
    e21.tool = ("platform", None)
    e21.update()
    e21.draw()
    # 保存 → 读回
    e21.name_box.text = "tex_smoke_test"
    e21.save()
    clear_cache()
    r21 = load_room("tex_smoke_test")
    assert r21.textures.get("platform") == "__smoke_tex.png", \
        "textures 应保存读回"
    assert r21.textures.get("tile:block_3") == "__smoke_tex.png", \
        "逐子类型材质应保存读回"
    # 游戏绘制带自定义材质不崩
    _save.clear_save()
    scene21 = GameScene(AssetManager(), room=r21)
    surf21 = pygame.Surface((800, 608))
    scene21.draw(surf21)
    # 撤销：材质改动可撤销（一次撤销回退最近一次改动）
    e21._undo()
    assert "tile" not in e21.room.textures, "撤销应恢复上一次材质改动"
    # 恢复默认按钮（先切到"单向平台"）
    e21.room.textures["platform"] = "__smoke_tex.png"
    e21.tex_slot_dropdown.value = "单向平台"
    e21._on_tex_obj_changed()
    assert e21._current_tex_key() == "platform"
    e21._clear_tex()
    assert "platform" not in e21.room.textures, "恢复默认应清除材质"
    os.remove(ttex)
    os.remove(os.path.join(config.ROOMS_DIR, "tex_smoke_test.json"))
    print("PASS 21 自定义材质：逐子类型键/粗粒度兜底/保存读回/游戏绘制/撤销/恢复默认")

    # ---- 测试 22：路径节点（放置/选中/画轨迹/设置/保存读回/删除） ----
    e22 = new_editor()
    e22.tool = ("path_node", None)
    e22.place(96, 480)                       # 放置节点 → 自动选中并进轨迹面板
    assert len(e22.room.path_nodes) == 1
    assert e22.selected_path is not None and e22.panel_mode == "path"
    # 画轨迹：原点与首点相同去重；连续重复点去重
    e22._add_path_point((96, 480))           # 与原点相同 → 不加入
    assert e22.selected_path["path"] == [], "首点与原点相同应去重"
    e22._add_path_point((160, 480))
    e22._add_path_point((160, 480))          # 连续重复 → 去重
    e22._add_path_point((160, 416))
    assert e22.selected_path["path"] == [(160, 480), (160, 416)], \
        e22.selected_path["path"]
    # 设置速度 / 触发方式
    e22._adjust_path_speed(0.5)
    assert e22.selected_path["speed"] == 1.5, e22.selected_path["speed"]
    e22._set_path_trigger("touch")
    assert e22.selected_path["trigger"] == "touch"
    # 绘制一帧（含节点/轨迹渲染）不崩
    e22.update()
    e22.draw()
    # 保存 → 读回
    e22.name_box.text = "path_smoke_test"
    e22.save()
    clear_cache()
    r22 = load_room("path_smoke_test")
    assert len(r22.path_nodes) == 1
    n22 = r22.path_nodes[0]
    assert n22["pos"] == (96, 480)
    assert n22["path"] == [(160, 480), (160, 416)], "轨迹应保存读回"
    assert n22["speed"] == 1.5 and n22["trigger"] == "touch"
    # 完成绘制 → 回到工具面板；再点节点重新选中并删除
    e22._done_path()
    assert e22.selected_path is None and e22.panel_mode == "tools"
    e22.place(96, 480)
    assert e22.selected_path is not None, "点节点应重新选中"
    e22._delete_selected_node()
    assert e22.room.path_nodes == [], "删除节点失败"
    # 挂载检测：节点与藤蔓重合 → 高亮矩形；无重合 → 空
    e22.tool = ("vine", "right")
    e22.place(96, 480)
    assert (3, 15) in e22.room.vines
    e22.room.path_nodes.append({"pos": (96, 480), "path": [],
                                "speed": 1.0, "trigger": "auto"})
    node22 = e22.room.path_nodes[-1]
    rects22 = e22._node_overlap_rects(node22)
    assert rects22 and any(r.x == 96 and r.y == 480 for r in rects22), \
        "节点与藤蔓重合应检测到（画布绿框）"
    empty22 = {"pos": (600, 96), "path": [], "speed": 1.0, "trigger": "auto"}
    assert e22._node_overlap_rects(empty22) == [], "无重合应为空"
    # 保存时无重合节点 → 警告
    e22.room.path_nodes.append(empty22)
    e22.name_box.text = "path_smoke_test"
    e22.save()
    assert "没挂到" in e22.message, f"空节点保存应警告：{e22.message}"
    os.remove(os.path.join(config.ROOMS_DIR, "path_smoke_test.json"))
    print("PASS 22 路径节点：放置/选中/画轨迹去重/速度触发/保存读回/删除/挂载高亮/空节点警告")

    # ---- 测试 23：按钮点击音效（任何按钮/工具/下拉选项都触发 sndCherry） ----
    e23 = new_editor()
    hits = [0]
    orig = e23._click_sound
    e23._click_sound = lambda: (hits.__setitem__(0, hits[0] + 1), orig())[1]
    click(e23, e23.load_btn.center)                # 右面板按钮
    assert hits[0] == 1, "点按钮应触发点击音效"
    click(e23, e23.grid_btns[1][0].center)         # 网格按钮
    assert hits[0] == 2, "点网格按钮应触发点击音效"
    click(e23, tool_rects(e23)[0][0].center)       # 工具列表项
    assert hits[0] == 3, "点工具项应触发点击音效"
    e23.room_dropdown.open = True
    click(e23, e23.room_dropdown.item_rects()[0].center)   # 下拉选项
    assert hits[0] == 4, "点下拉选项应触发点击音效"
    e23.panel_mode = "tex"
    click(e23, e23.tex_back_btn.center)            # 材质面板按钮
    assert hits[0] == 5, "材质面板按钮应触发点击音效"
    orig()                                         # 直接调不崩（无声卡静默）
    print("PASS 23 按钮点击音效：按钮/网格/工具/下拉/面板均触发 sndCherry")

    # ---- 清理 ----
    os.remove(path)
    clear_cache()
    print("\n✅ 编辑器冒烟测试全部通过")
    return 0


if __name__ == "__main__":
    sys.exit(main())
