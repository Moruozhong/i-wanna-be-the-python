"""
editor/editor.py — 可视化地图编辑器（阶段 7）

用法：python main.py --editor

布局（三栏，避免单侧面板过挤）：
    * 左侧 190px 工具面板：小刺象限 + 工具列表（全高可滚动）
    * 中间 800×608 房间画布（25×19 网格，32px Tile）
    * 右侧 240px 设置面板：房间选择/房间名/出口目标/底部按钮；
      点"背景"进入背景设置（颜色 RGB + 色板 + 背景图片 + 预览）。
    * 左键放置当前工具；右键按当前工具擦除；滚轮滚动工具列表。
    * Ctrl+S 保存到 rooms/{房间名}.json（保存后自动清房间缓存，
      游戏内重进房间即可看到改动）；Ctrl+L 加载已存在的房间。

工具：砖块(block_0..8)、尖刺(四方向)、小刺(四方向×四象限)、藤蔓(left/right)、
水(first/second/zero)、单向平台、Checkpoint、出口(带目标房间)、终点、跳跃球、
跳跃星星(1/2/3 段)、出生点、橡皮擦(擦当前工具/整格)。
"""

import json
import os
import sys
import threading

# 支持从任意目录直接运行（python editor/editor.py）：把项目根目录加入模块搜索路径
_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

import pygame

import config
from core import pack as pack_mod
from core import settings
from core import settings
from core.assets import AssetManager
from core.bgrender import render_background
from core.sound import MusicManager, SoundManager
from core.textures import texture_for
from levels.room import Room
from levels.rooms_registry import load_room, clear_cache, room_path

# ============================================================
# 三栏布局常量（绘制与点击判定共用同一套坐标，避免偏移）
# ============================================================
LEFT_W = 190                       # 左侧工具面板宽
CANVAS_X = LEFT_W                  # 画布在窗口中的左偏移
RIGHT_W = 240                      # 右侧设置面板宽
RIGHT_X = LEFT_W + config.ROOM_WIDTH   # 右侧面板左缘
WIN_W = RIGHT_X + RIGHT_W          # 窗口宽
WIN_H = config.ROOM_HEIGHT
T = config.TILE_SIZE

# 左侧工具面板
QUAD_LABEL_Y = 28                  # "小刺象限"
QUAD_BTN_Y = 42                    # 象限按钮（两行）
GRID_LABEL_Y = 88                  # "网格"
GRID_BTN_Y = 102                   # 网格粒度按钮（32/16/8）
LAYER_LABEL_Y = 128                # "图层"
LAYER_ROW_Y = 142                  # 图层行（5 行 × 20）
L_TOOLS_TOP = 254                  # 工具列表起点（- scroll 滚动）
L_TOOLS_BOTTOM = WIN_H - 8         # 工具列表可视区下限

# 图层定义：元素按类型分组（编辑器级图层，不改变房间 JSON 格式）
# 每层可：显示/隐藏（画布不渲染）、锁定（禁止放置/擦除）
LAYERS = [
    ("ground",    "地形", ("tile", "small_tile")),
    ("danger",    "危险", ("spike", "mini_spike")),
    ("structure", "平台", ("platform", "vine")),
    ("objects",   "物体", ("checkpoint", "exit", "end", "plus_jump",
                           "star", "start", "path_node")),
    ("water",     "水",   ("water",)),
]
SETTINGS_PATH = os.path.join(config.PROJECT_ROOT, "editor_layers.json")

# 可自定义材质的对象（键 = 房间 textures 字段的键；子类型 None = 无子类型/全部）
# 贴图键规则：有子类型 = "对象:子类型"（如 tile:block_3 / water:first / star:2 /
# checkpoint:active）；"（全部）" = 仅对象键（如 tile），所有子类型统一用它。
TEX_OBJECTS = [
    ("tile",       "砖块",
     [("（全部）", None)] + [(f"block_{i}", f"block_{i}") for i in range(9)]),
    ("spike",      "尖刺",
     [("（全部）", None)] + [(d, d) for d in ("up", "down", "left", "right")]),
    ("mini_spike", "小刺",
     [("（全部）", None)] + [(d, d) for d in ("up", "down", "left", "right")]),
    ("vine",       "藤蔓",
     [("（全部）", None), ("left", "left"), ("right", "right")]),
    ("water",      "水",
     [("（全部）", None), ("一段", "first"), ("二段", "second"),
      ("零段", "zero")]),
    ("platform",   "单向平台", [("（全部）", None)]),
    ("checkpoint", "Checkpoint",
     [("（全部）", None), ("未激活", "inactive"), ("激活", "active")]),
    ("door",       "出口/终点", [("（全部）", None)]),
    ("plus_jump",  "跳跃球", [("（全部）", None)]),
    ("star",       "跳跃星星",
     [("（全部）", None), ("1段", "1"), ("2段", "2"), ("3段", "3")]),
]

# 右侧设置面板
DROP_BOX_Y = 54                    # 房间选择下拉框（展开列表向下盖到 ~296，下方控件避开）
NAME_BOX_Y = 300                   # 房间名输入框（放在房间下拉展开区之下，不重叠）
TARGET_BOX_Y = 352                 # 出口目标房间输入框
MUSIC_LABEL_Y = 384                # "背景音乐（本房间）"标签
MUSIC_BOX_Y = 398                  # 背景音乐下拉框
MUSIC_DEF_LABEL_Y = 428            # "默认音乐"标签
MUSIC_DEF_BOX_Y = 442              # 默认音乐下拉框
MUSIC_BTN_Y = 472                  # 试听 / 停止按钮
BTN_ROW1_Y = 522                   # 保存/加载
BTN_ROW2_Y = 552                   # 材质/背景/清空/退出

# 材质设置（panel_mode == "tex"）
TEX_SLOT_LABEL_Y = 36              # "替换对象"标签
TEX_SLOT_BOX_Y = 50                # 对象下拉
TEX_SUB_LABEL_Y = 86               # "子类型"标签
TEX_SUB_BOX_Y = 100                # 子类型下拉（（全部）= 统一材质）
TEX_IMG_LABEL_Y = 136              # "材质图片"标签
TEX_IMG_BOX_Y = 150                # 材质图片下拉
TEX_PREVIEW_Y = 186                # 预览区（130 高）
TEX_CLEAR_Y = 340                  # 恢复默认
TEX_BACK_Y = 370                   # 返回工具

# 路径节点设置（panel_mode == "path"，选中路径节点时自动打开）
PATH_SPEED_LABEL_Y = 60            # "速度"
PATH_SPEED_Y = 74                  # 速度调节行
PATH_TRIGGER_LABEL_Y = 116         # "触发方式"
PATH_TRIGGER_Y = 130               # 触发按钮（自动/触碰）
PATH_CLEAR_Y = 180                 # 清除轨迹
PATH_DELETE_Y = 214                # 删除节点
PATH_DONE_Y = 248                  # 完成绘制（取消选中）

# 项目设置（panel_mode == "settings"：游戏标题 / 程序图标）
SET_TITLE_LABEL_Y = 40             # "游戏标题"
SET_TITLE_BOX_Y = 54               # 标题输入框
SET_ICON_LABEL_Y = 90              # "程序图标"
SET_ICON_BOX_Y = 104               # 图标下拉（扫描 assets/ 根目录）
SET_APPLY_Y = 160                  # 应用设置
SET_BACK_Y = 194                   # 返回工具

# 背景设置（右面板，panel_mode == "bg"）
BG_COLOR_LABEL_Y = 36              # "背景颜色"
BG_RGB_Y = 50                      # R/G/B 输入框 + 色块
BG_APPLY_Y = 76                    # 应用颜色按钮
BG_PALETTE_Y = 104                 # 预设色板（一行 8 个）
BG_IMG_LABEL_Y = 158               # "背景图片"
BG_IMG_BOX_Y = 172                 # 图片文件名输入框
BG_IMG_DROP_Y = 198                # 图片下拉
BG_MODE_LABEL_Y = 224              # "填充模式"
BG_MODE_Y = 238                    # 模式按钮（2 行 3 列，每 72×22）
BG_ZOOM_LABEL_Y = 288              # "缩放 / 偏移 (缩放模式)"
BG_ZOOM_Y = 302                    # 缩放行
BG_OFFX_Y = 328                    # 偏移 X
BG_OFFY_Y = 354                    # 偏移 Y
BG_PREVIEW_Y = 382                 # 预览
BG_BTN_Y = 516                     # 应用图片 / 清除图片
BG_BACK_Y = 546                    # 返回工具

BG_PANEL = (30, 34, 42)
BG_INPUT = (20, 22, 28)
TEXT_DIM = (150, 156, 170)
TEXT_BRIGHT = (235, 238, 244)
ACCENT = (96, 180, 255)
SEL_BG = (52, 88, 140)
HOVER_BG = (44, 52, 66)
BORDER = (58, 64, 78)
OK_GREEN = (120, 220, 120)
ERR_RED = (240, 120, 110)


def _thumb_key(kind, sub):
    return (kind, sub)


class InputBox:
    """简单文本框：点击聚焦，Backspace 删除，可打印字符输入（ASCII）。

    输入取字符的优先级：event.unicode（正常输入）→ chr(event.key)
    （unicode 为空时兜底，如中文输入法激活状态下按英文键也能输入）。
    """

    def __init__(self, rect, text="", font=None):
        self.rect = pygame.Rect(rect)
        self.text = text
        self.font = font
        self.active = False

    def handle(self, event):
        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            self.active = self.rect.collidepoint(event.pos)
            return self.active
        if event.type == pygame.KEYDOWN and self.active:
            if event.key == pygame.K_BACKSPACE:
                self.text = self.text[:-1]
            elif event.key in (pygame.K_RETURN, pygame.K_TAB, pygame.K_ESCAPE):
                self.active = False          # 回车/Tab/Esc 取消焦点
            else:
                ch = getattr(event, "unicode", "") or (
                    chr(event.key) if 32 <= event.key < 127 else "")
                if ch and ch.isprintable():
                    self.text += ch
            return True
        return False

    def draw(self, screen):
        bg = BG_INPUT if not self.active else (34, 48, 66)
        pygame.draw.rect(screen, bg, self.rect, border_radius=3)
        pygame.draw.rect(screen, ACCENT if self.active else BORDER, self.rect, 1,
                         border_radius=3)
        img = self.font.render(self.text or " ", True, TEXT_BRIGHT)
        screen.blit(img, (self.rect.x + 5, self.rect.y + 3))
        if self.active and (pygame.time.get_ticks() // 400) % 2 == 0:
            # 闪烁光标：明确指示"正在此框输入"
            cx = self.rect.x + 5 + img.get_width()
            pygame.draw.line(screen, TEXT_BRIGHT,
                             (cx, self.rect.y + 4),
                             (cx, self.rect.y + self.rect.h - 4), 1)


class Dropdown:
    """下拉选择框：点击展开选项列表，点击选项选中（展开为临时浮层）。"""

    def __init__(self, rect, font):
        self.rect = pygame.Rect(rect)
        self.font = font
        self.items = []
        self.value = ""
        self.open = False
        self.icons = {}          # value -> Surface（可选缩略图，展开项左侧显示）

    def set_items(self, items):
        self.items = list(items)
        if self.value not in self.items:
            self.value = self.items[0] if self.items else ""

    def item_rects(self):
        return [pygame.Rect(self.rect.x, self.rect.y + 22 * (i + 1),
                            self.rect.w, 20)
                for i in range(len(self.items))]

    def handle(self, event):
        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            if self.rect.collidepoint(event.pos):
                self.open = not self.open
                return True
            if self.open:
                for i, r in enumerate(self.item_rects()):
                    if r.collidepoint(event.pos):
                        self.value = self.items[i]
                        self.open = False
                        return "selected"
                self.open = False
        return False

    def draw(self, screen):
        """只画下拉框本体（展开列表由 draw_open 最后绘制，避免被其他控件覆盖）。"""
        bg = BG_INPUT if not self.open else (34, 48, 66)
        pygame.draw.rect(screen, bg, self.rect, border_radius=3)
        pygame.draw.rect(screen, ACCENT if self.open else BORDER, self.rect,
                         1, border_radius=3)
        img = self.font.render(self.value or "—", True, TEXT_BRIGHT)
        screen.blit(img, (self.rect.x + 5, self.rect.y + 3))
        pygame.draw.polygon(screen, TEXT_DIM, [
            (self.rect.right - 12, self.rect.y + 7),
            (self.rect.right - 4, self.rect.y + 7),
            (self.rect.right - 8, self.rect.y + 14)])

    def draw_open(self, screen):
        """展开浮层：必须在面板所有控件之后绘制（覆盖输入框/按钮）。"""
        if not self.open:
            return
        try:
            selected_idx = self.items.index(self.value)
        except ValueError:
            selected_idx = -1          # value 不在列表中（如房间名≠文件名）
        for i, r in enumerate(self.item_rects()):
            hover = r.collidepoint(pygame.mouse.get_pos())
            pygame.draw.rect(screen, HOVER_BG if hover else BG_INPUT, r,
                             border_radius=2)
            pygame.draw.rect(screen, ACCENT if i == selected_idx else BORDER,
                             r, 1, border_radius=2)
            icon = self.icons.get(self.items[i])
            tx = r.x + 4
            if icon is not None:
                screen.blit(icon, (r.x + 3, r.y + (20 - icon.get_height()) // 2))
                tx = r.x + 22
            t = self.font.render(self.items[i], True, TEXT_BRIGHT)
            screen.blit(t, (tx, r.y + 2))


class Editor:
    def __init__(self):
        pygame.init()
        pygame.display.set_caption("I Wanna 关卡编辑器")
        self.screen = pygame.display.set_mode((WIN_W, WIN_H))
        self.clock = pygame.time.Clock()
        self.assets = AssetManager()
        self.assets.ensure_dirs()
        self._canvas = pygame.Surface((config.ROOM_WIDTH, config.ROOM_HEIGHT))

        self.room = load_room("room001") or Room("room001")   # 打开即加载现有关卡作参考
        self.tool = ("tile", "block_0")     # (kind, subtype)
        self.mini_quad = 0                  # 小刺四象限：0=左上 1=右上 2=左下 3=右下
        self.scroll = 0
        self.mouse_pos = (0, 0)
        self.hover = None                   # 鼠标悬停的 (tx, ty)
        self.running = True
        self.message = ""
        self.message_color = OK_GREEN
        self.message_timer = 0
        self._bg_dirty = True        # 背景缓存是否需重渲（画布实时预览用）
        self._bg_cache = None        # 800×608 背景渲染缓存
        self._bg_drag = None         # 预览框拖拽状态 (mode, 起点, zoom, offset, 框宽)
        self._bg_k = 0.0             # 预览里整图显示比例（拖拽换算用）
        self._bg_box = None          # 预览视口框 Rect（命中检测用）
        # ---- 撤销 / 拖放 / 测试 ----
        self._undo_stack = []        # 撤销栈（房间 JSON 快照）
        self._undo_batching = False  # 拖放批次中（一次拖动合并为一次撤销）
        self._drag_placing = False   # Shift 拖放连续放置中
        self._last_drag_cell = None  # 拖放上一次放置的格子
        self._test_pending = False   # 按 Enter 后待启动的游戏测试

        self.font = config.get_font(14)
        self.font_small = config.get_font(12)
        self.font_bold = config.get_font(15, bold=True)

        # ---- 右侧设置面板控件 ----
        self.room_dropdown = Dropdown((RIGHT_X + 8, DROP_BOX_Y, RIGHT_W - 16, 22),
                                      self.font)
        self.name_box = InputBox((RIGHT_X + 8, NAME_BOX_Y, RIGHT_W - 16, 22),
                                 "room001", self.font)
        self.target_box = InputBox((RIGHT_X + 8, TARGET_BOX_Y, RIGHT_W - 16, 22),
                                   "room002", self.font)
        self.save_btn = pygame.Rect(RIGHT_X + 8, BTN_ROW1_Y, 43, 26)
        self.load_btn = pygame.Rect(RIGHT_X + 55, BTN_ROW1_Y, 43, 26)
        self.project_btn = pygame.Rect(RIGHT_X + 102, BTN_ROW1_Y, 43, 26)
        self.load_project_btn = pygame.Rect(RIGHT_X + 149, BTN_ROW1_Y, 43, 26)
        self.exe_btn = pygame.Rect(RIGHT_X + 196, BTN_ROW1_Y, 43, 26)
        self.tex_btn = pygame.Rect(RIGHT_X + 8, BTN_ROW2_Y, 43, 26)
        self.bg_btn = pygame.Rect(RIGHT_X + 55, BTN_ROW2_Y, 43, 26)
        self.settings_btn = pygame.Rect(RIGHT_X + 102, BTN_ROW2_Y, 43, 26)
        self.clear_btn = pygame.Rect(RIGHT_X + 149, BTN_ROW2_Y, 43, 26)
        self.exit_btn = pygame.Rect(RIGHT_X + 196, BTN_ROW2_Y, 43, 26)

        # ---- 背景音乐（房间自定义 BGM，music/ 目录）----
        self.music = MusicManager()          # 编辑器试听用（游戏里另有实例）
        self.sounds = SoundManager()         # 按钮点击音效（sound/sndCherry.wav）
        self.music_dropdown = Dropdown((RIGHT_X + 8, MUSIC_BOX_Y,
                                        RIGHT_W - 16, 22), self.font)
        self.music_def_dropdown = Dropdown((RIGHT_X + 8, MUSIC_DEF_BOX_Y,
                                            RIGHT_W - 16, 22), self.font)
        self.music_play_btn = pygame.Rect(RIGHT_X + 8, MUSIC_BTN_Y, 60, 22)
        self.music_stop_btn = pygame.Rect(RIGHT_X + 74, MUSIC_BTN_Y, 60, 22)
        self._refresh_music()

        # ---- 左侧工具面板：小刺象限 + 网格粒度 + 工具列表 ----
        self.quad_btns = []
        for i, label in enumerate(("左上", "右上", "左下", "右下")):
            self.quad_btns.append((
                pygame.Rect(8 + (i % 2) * 62, QUAD_BTN_Y + (i // 2) * 22,
                            60, 20), label))
        self.grid = 32                      # 放置网格粒度（像素）
        self.grid_btns = []
        for i, g in enumerate((32, 16, 8)):
            self.grid_btns.append((pygame.Rect(6 + i * 30, GRID_BTN_Y, 28,
                                               20), g))
        # 图层状态（编辑器级，不影响房间 JSON）
        self.layer_visible = {name: True for name, _l, _k in LAYERS}
        self.layer_locked = {name: False for name, _l, _k in LAYERS}
        self._load_layer_settings()
        self._build_tools()

        self._thumbs = {}                  # 缩略图缓存
        self.selected_exit = None          # 当前选中编辑的出口格 (tx, ty)
        self.selected_path = None          # 当前选中的路径节点 dict（None = 未选中）
        self._path_drawing = False         # 正在画轨迹（左键拖拽中）
        self._path_last_cell = None        # 轨迹上一个吸附点
        # ---- 保存工程 / 打包 exe ----
        self._pack_thread = None           # 打包线程（避免阻塞主循环）
        self._pack_status = ""             # 打包进度（线程写入，主循环显示）
        self._pack_done = False            # 打包是否结束
        self._pack_result = ""             # 打包结果消息
        self.current_room_name = "room001"  # 当前房间的文件名（下拉框用文件名，≠ room.name 字段）
        self._refresh_rooms()

        # ---- 背景设置（panel_mode == "bg" 时显示在右面板）----
        self.panel_mode = "tools"          # "tools"=工具 / "bg"=背景设置
        r, g, b = self.room.bg_color
        self.bg_r_box = InputBox((RIGHT_X + 8, BG_RGB_Y, 52, 22), str(r),
                                 self.font)
        self.bg_g_box = InputBox((RIGHT_X + 66, BG_RGB_Y, 52, 22), str(g),
                                 self.font)
        self.bg_b_box = InputBox((RIGHT_X + 124, BG_RGB_Y, 52, 22), str(b),
                                 self.font)
        self.bg_color_swatch = pygame.Rect(RIGHT_X + 182, BG_RGB_Y, 34, 22)
        self.bg_apply_color_btn = pygame.Rect(RIGHT_X + 8, BG_APPLY_Y, 108, 24)
        self.bg_palette = [(135, 206, 235), (0, 0, 0), (255, 255, 255),
                           (200, 60, 60), (60, 200, 90), (60, 90, 220),
                           (150, 60, 200), (240, 200, 60)]
        self.bg_palette_rects = [pygame.Rect(RIGHT_X + 8 + i * 29,
                                             BG_PALETTE_Y, 27, 27)
                                 for i in range(len(self.bg_palette))]
        self.bg_image_box = InputBox((RIGHT_X + 8, BG_IMG_BOX_Y, RIGHT_W - 16,
                                      22), "", self.font)
        self.bg_img_dropdown = Dropdown((RIGHT_X + 8, BG_IMG_DROP_Y,
                                         RIGHT_W - 16, 22), self.font)
        self.bg_apply_img_btn = pygame.Rect(RIGHT_X + 8, BG_BTN_Y, 108, 24)
        self.bg_clear_img_btn = pygame.Rect(RIGHT_X + 124, BG_BTN_Y, 108, 24)
        self.bg_back_btn = pygame.Rect(RIGHT_X + 8, BG_BACK_Y, RIGHT_W - 16,
                                       26)
        # 填充模式按钮（2 行 3 列）
        self.bg_modes = [("stretch", "拉伸"), ("fill", "填充"), ("fit", "适应"),
                         ("tile", "平铺"), ("center", "居中"), ("zoom", "缩放")]
        self.bg_mode_btns = []
        for i, (_mode, label) in enumerate(self.bg_modes):
            self.bg_mode_btns.append((
                pygame.Rect(RIGHT_X + 8 + (i % 3) * 74,
                            BG_MODE_Y + (i // 3) * 24, 72, 22), label))
        # 缩放 / 偏移调节（zoom 模式，[-][值][+]）
        self.zoom_dec_btn = pygame.Rect(RIGHT_X + 8, BG_ZOOM_Y, 30, 22)
        self.zoom_inc_btn = pygame.Rect(RIGHT_X + 142, BG_ZOOM_Y, 30, 22)
        self.offx_dec_btn = pygame.Rect(RIGHT_X + 8, BG_OFFX_Y, 30, 22)
        self.offx_inc_btn = pygame.Rect(RIGHT_X + 142, BG_OFFX_Y, 30, 22)
        self.offy_dec_btn = pygame.Rect(RIGHT_X + 8, BG_OFFY_Y, 30, 22)
        self.offy_inc_btn = pygame.Rect(RIGHT_X + 142, BG_OFFY_Y, 30, 22)
        self._refresh_bg_images()
        self._sync_bg_controls()

        # ---- 材质设置（panel_mode == "tex" 时显示在右面板）----
        self.tex_slot_dropdown = Dropdown((RIGHT_X + 8, TEX_SLOT_BOX_Y,
                                           RIGHT_W - 16, 22), self.font)
        self.tex_slot_dropdown.set_items([label for _k, label, _s in TEX_OBJECTS])
        self.tex_sub_dropdown = Dropdown((RIGHT_X + 8, TEX_SUB_BOX_Y,
                                          RIGHT_W - 16, 22), self.font)
        self.tex_img_dropdown = Dropdown((RIGHT_X + 8, TEX_IMG_BOX_Y,
                                          RIGHT_W - 16, 22), self.font)
        self.tex_clear_btn = pygame.Rect(RIGHT_X + 8, TEX_CLEAR_Y, 108, 24)
        self.tex_back_btn = pygame.Rect(RIGHT_X + 124, TEX_CLEAR_Y, 108, 24)
        self._refresh_tex_images()
        self._on_tex_obj_changed()          # 按默认对象填充子类型 + 同步

        # ---- 项目设置（panel_mode == "settings"：游戏标题 / 程序图标）----
        self.title_box = InputBox((RIGHT_X + 8, SET_TITLE_BOX_Y,
                                   RIGHT_W - 16, 22), settings.get_title(),
                                  self.font)
        self.icon_dropdown = Dropdown((RIGHT_X + 8, SET_ICON_BOX_Y,
                                       RIGHT_W - 16, 22), self.font)
        self.settings_apply_btn = pygame.Rect(RIGHT_X + 8, SET_APPLY_Y, 108,
                                              24)
        self.settings_back_btn = pygame.Rect(RIGHT_X + 124, SET_APPLY_Y, 108,
                                             24)
        self._refresh_icon_images()

        # ---- 路径节点设置（panel_mode == "path"）----
        self.path_speed_dec_btn = pygame.Rect(RIGHT_X + 8, PATH_SPEED_Y, 30, 22)
        self.path_speed_inc_btn = pygame.Rect(RIGHT_X + 142, PATH_SPEED_Y, 30,
                                              22)
        self.path_auto_btn = pygame.Rect(RIGHT_X + 8, PATH_TRIGGER_Y, 60, 22)
        self.path_touch_btn = pygame.Rect(RIGHT_X + 74, PATH_TRIGGER_Y, 60, 22)
        self.path_clear_btn = pygame.Rect(RIGHT_X + 8, PATH_CLEAR_Y, 108, 24)
        self.path_delete_btn = pygame.Rect(RIGHT_X + 124, PATH_CLEAR_Y, 108,
                                           24)
        self.path_done_btn = pygame.Rect(RIGHT_X + 8, PATH_DONE_Y,
                                         RIGHT_W - 16, 26)

    # ---------------- 背景图片列表 / 控件同步 ----------------
    def _refresh_bg_images(self):
        """自动扫描 assets/backgrounds/ 的图片文件填充背景图下拉（带缩略图）。"""
        bg_dir = os.path.join(config.PROJECT_ROOT, "assets", "backgrounds")
        files = []
        icons = {}
        if os.path.isdir(bg_dir):
            for f in sorted(os.listdir(bg_dir)):
                if not f.lower().endswith((".png", ".jpg", ".jpeg",
                                           ".gif", ".bmp")):
                    continue
                files.append(f)
                img = self.assets.background(f)
                if img is not None:
                    iw, ih = img.get_size()
                    r = min(16 / iw, 16 / ih)
                    icons[f] = pygame.transform.smoothscale(
                        img, (max(1, int(iw * r)), max(1, int(ih * r))))
        self.bg_img_dropdown.icons = icons
        self.bg_img_dropdown.set_items(["（无）"] + files)
        # 当前房间有背景图且文件在 → 选中它；否则回"（无）"（切房不残留旧值）
        if self.room.bg_image in files:
            self.bg_img_dropdown.value = self.room.bg_image
        else:
            self.bg_img_dropdown.value = "（无）"

    def _sync_bg_controls(self):
        """把 room.bg_color / bg_image 同步到背景控件，并标记画布背景需重渲。"""
        r, g, b = self.room.bg_color
        self.bg_r_box.text = str(r)
        self.bg_g_box.text = str(g)
        self.bg_b_box.text = str(b)
        self.bg_image_box.text = self.room.bg_image or ""
        self._refresh_bg_images()
        self._bg_dirty = True        # 背景变了 → 画布实时刷新

    # ---------------- 背景音乐 ----------------
    def _refresh_music(self):
        """自动扫描 music/ 目录的音频文件填充背景音乐下拉。"""
        files = []
        if os.path.isdir(config.MUSIC_DIR):
            files = sorted(f for f in os.listdir(config.MUSIC_DIR)
                           if f.lower().endswith((".mp3", ".ogg", ".wav",
                                                  ".flac")))
        self.music_dropdown.set_items(["（无）"] + files)
        # 当前房间有 bgm 且文件在 → 选中它；否则回"（无）"。
        # 关键：切换房间后**必须重置**，否则下拉会残留上一个房间的选中值，
        # 让人误以为音乐已设置（实际 room.bgm 只在点选那一刻写入当前房间）。
        if self.room.bgm in files:
            self.music_dropdown.value = self.room.bgm
        else:
            self.music_dropdown.value = "（无）"
        # 默认音乐下拉（全局设置，游戏里无 bgm 的房间自动播放它）
        self.music_def_dropdown.set_items(["（无）"] + files)
        default = settings.get_default_bgm()
        if default in files:
            self.music_def_dropdown.value = default
        else:
            self.music_def_dropdown.value = "（无）"

    def _sync_music_controls(self):
        """把 room.bgm 同步到背景音乐下拉。"""
        self._refresh_music()

    def _apply_music(self, value):
        """应用选中的背景音乐（"（无）" → None）。"""
        self._undo_push()
        self.room.bgm = None if value == "（无）" else value
        self._sync_music_controls()
        self.set_message("背景音乐：" + (self.room.bgm or "无"))

    def _apply_default_music(self, value):
        """设置默认背景音乐（全局持久化；无 bgm 的房间在游戏里播放它）。"""
        settings.set_default_bgm(None if value == "（无）" else value)
        self._sync_music_controls()
        self.set_message("默认音乐：" + (settings.get_default_bgm() or "无") +
                         "（没设 bgm 的房间自动播放）")

    # ---------------- 自定义材质（object 贴图替换） ----------------
    def _refresh_tex_images(self):
        """扫描 assets/textures/ 的图片填充材质下拉（带缩略图）。"""
        tex_dir = os.path.join(config.PROJECT_ROOT, "assets", "textures")
        files = []
        icons = {}
        if os.path.isdir(tex_dir):
            for f in sorted(os.listdir(tex_dir)):
                if not f.lower().endswith((".png", ".jpg", ".jpeg",
                                           ".gif", ".bmp")):
                    continue
                files.append(f)
                img = self.assets.custom_texture(f)
                if img is not None:
                    iw, ih = img.get_size()
                    r = min(16 / iw, 16 / ih)
                    icons[f] = pygame.transform.smoothscale(
                        img, (max(1, int(iw * r)), max(1, int(ih * r))))
        self.tex_img_dropdown.icons = icons
        self.tex_img_dropdown.set_items(["（默认）"] + files)

    def _current_tex_obj(self):
        """材质面板当前选中的对象键（如 "tile"）。"""
        label = self.tex_slot_dropdown.value
        for _k, lab, _s in TEX_OBJECTS:
            if lab == label:
                return _k
        return TEX_OBJECTS[0][0]

    def _current_tex_subs(self):
        """当前对象的子类型表 [(显示名, 键后缀), ...]。"""
        label = self.tex_slot_dropdown.value
        for _k, lab, subs in TEX_OBJECTS:
            if lab == label:
                return subs
        return [("（全部）", None)]

    def _current_tex_key(self):
        """当前选中的贴图键：有子类型 = "对象:子类型"，"（全部）" = 仅对象键。"""
        obj = self._current_tex_obj()
        suffix = None
        for lab, s in self._current_tex_subs():
            if lab == self.tex_sub_dropdown.value:
                suffix = s
                break
        return f"{obj}:{suffix}" if suffix else obj

    def _sync_tex_controls(self):
        """把 room.textures[当前贴图键] 同步到材质图片下拉（切房/切对象时调用）。"""
        self._refresh_tex_images()
        key = self._current_tex_key()
        name = self.room.textures.get(key)
        if name is None and ":" in key:
            name = self.room.textures.get(key.split(":", 1)[0])   # 粗粒度兜底显示
        if name in self.tex_img_dropdown.items:
            self.tex_img_dropdown.value = name
        else:
            self.tex_img_dropdown.value = "（默认）"

    def _on_tex_obj_changed(self):
        """对象下拉变化：重建子类型下拉（重置"（全部）"）并同步材质显示。"""
        subs = self._current_tex_subs()
        labels = [lab for lab, _s in subs]
        self.tex_sub_dropdown.set_items(labels)
        if self.tex_sub_dropdown.value not in labels:
            self.tex_sub_dropdown.value = labels[0]
        self._sync_tex_controls()

    def _apply_tex(self, value):
        """给当前贴图键应用自定义材质（"（默认）" → 恢复原贴图）。"""
        self._undo_push()
        key = self._current_tex_key()
        if value == "（默认）":
            self.room.textures.pop(key, None)
        else:
            self.room.textures[key] = value
        self._sync_tex_controls()
        self.set_message(f"材质 {key} → {value if value != '（默认）' else '默认'}")

    def _clear_tex(self):
        """清除当前贴图键的自定义材质。"""
        self._undo_push()
        key = self._current_tex_key()
        self.room.textures.pop(key, None)
        self._sync_tex_controls()
        self.set_message(f"已恢复 {key} 默认材质")

    def _tex_preview_surface(self, key):
        """预览：该贴图键的默认贴图（或已应用的自定义材质）。"""
        a = self.assets
        obj, _, suffix = key.partition(":")
        if obj == "tile":
            typ = suffix or "block_0"
            return texture_for(a, self.room, key, a.tile(typ))
        if obj == "spike":
            return texture_for(a, self.room, key, a.spike(suffix or "up"))
        if obj == "mini_spike":
            return texture_for(a, self.room, key, a.mini_spike(suffix or "up"))
        if obj == "vine":
            return texture_for(a, self.room, key, a.vine(suffix or "right"))
        if obj == "water":
            return texture_for(a, self.room, key, a.water(suffix or "first"))
        if obj == "platform":
            return texture_for(a, self.room, key, a.platform())
        if obj == "checkpoint":
            return texture_for(a, self.room, key,
                               a.checkpoint(suffix == "active"))
        if obj == "door":
            return texture_for(a, self.room, key, a.end())
        if obj == "plus_jump":
            return texture_for(a, self.room, key, a.plusjump())
        if obj == "star":
            lv = int(suffix) if suffix and suffix.isdigit() else 3
            return texture_for(a, self.room, key, a.star(lv))
        return a.tile("block_0")

    # ---------------- 房间列表 / 加载 ----------------
    def _refresh_rooms(self):
        """扫描 rooms/*.json 填充房间下拉框，选中项保持当前房间。"""
        names = sorted(f[:-5] for f in os.listdir(config.ROOMS_DIR)
                       if f.endswith(".json"))
        self.room_dropdown.set_items(names)
        if self.current_room_name in names:
            self.room_dropdown.value = self.current_room_name

    def _load_name(self, name):
        """按文件名加载房间到画布（下拉选择 / Ctrl+L 共用）。"""
        room = load_room(name)
        if room is None:
            self.set_message(f"房间 {name} 不存在", ERR_RED)
            return
        self.room = room
        self.current_room_name = name
        self.name_box.text = room.name
        self.room_dropdown.value = name
        self.selected_exit = None
        self.selected_path = None          # 切房清掉路径选中
        self._path_drawing = False
        if self.panel_mode == "path":
            self.panel_mode = "tools"
        self._sync_bg_controls()   # 背景控件跟随房间
        self._sync_music_controls()   # 背景音乐控件跟随房间
        self._sync_tex_controls()   # 材质控件跟随房间
        self.set_message(f"已加载 {name}")

    # ---------------- 图层 ----------------
    def _layer_of(self, kind):
        for name, _label, kinds in LAYERS:
            if kind in kinds:
                return name
        return None

    def _layer_label(self, kind):
        name = self._layer_of(kind)
        if name is None:
            return "?"
        return next(label for n, label, _k in LAYERS if n == name)

    def _layer_visible(self, kind):
        name = self._layer_of(kind)
        return True if name is None else self.layer_visible.get(name, True)

    def _layer_blocked(self, kind):
        """该工具所属层是否锁定或隐藏（隐藏层不允许放置）。"""
        name = self._layer_of(kind)
        if name is None:
            return False
        return self.layer_locked.get(name, False) \
            or not self.layer_visible.get(name, True)

    def _save_layer_settings(self):
        try:
            with open(SETTINGS_PATH, "w", encoding="utf-8") as f:
                json.dump({"visible": self.layer_visible,
                           "locked": self.layer_locked}, f,
                          ensure_ascii=False, indent=2)
        except OSError:
            pass

    def _load_layer_settings(self):
        try:
            with open(SETTINGS_PATH, "r", encoding="utf-8") as f:
                data = json.load(f)
        except (OSError, ValueError):
            return
        if not isinstance(data, dict):
            return
        for key, attr in (("visible", "layer_visible"),
                          ("locked", "layer_locked")):
            src = data.get(key)
            if isinstance(src, dict):
                for k, v in src.items():
                    if k in getattr(self, attr) and isinstance(v, bool):
                        getattr(self, attr)[k] = v

    # ---------------- 工具定义 ----------------
    def _build_tools(self):
        items = []
        def add(kind, sub, label=None):
            items.append({"kind": kind, "sub": sub,
                          "label": label if label is not None
                          else f"{kind} {sub}"})
        items.append({"sep": "工具"})
        add("eraser", None, "橡皮擦")
        add("start", None, "出生点")
        items.append({"sep": "砖块"})
        for i in range(9):
            add("tile", f"block_{i}", f"block_{i}")
        items.append({"sep": "小砖块(16px)"})
        for i in range(9):
            add("small_tile", f"block_{i}", f"小砖 {i}")
        items.append({"sep": "尖刺"})
        for d in ("up", "down", "left", "right"):
            add("spike", d, f"尖刺 {d}")
        items.append({"sep": "小刺（四象限）"})
        for d in ("up", "down", "left", "right"):
            add("mini_spike", d, f"小刺 {d}")
        items.append({"sep": "藤蔓"})
        add("vine", "left", "藤蔓 左")
        add("vine", "right", "藤蔓 右")
        items.append({"sep": "水"})
        add("water", "first", "水 一段")
        add("water", "second", "水 二段")
        add("water", "zero", "水 零段")
        items.append({"sep": "物体"})
        add("platform", None, "单向平台")
        add("checkpoint", None, "Checkpoint")
        add("exit", None, "出口")
        add("end", None, "终点")
        add("plus_jump", None, "跳跃球")
        add("star", 1, "一段星(黑)")
        add("star", 2, "二段星(灰)")
        add("star", 3, "三段星(黄)")
        add("path_node", None, "路径节点(编辑器)")
        self.tools = items

    # ---------------- 缩略图 ----------------
    def _thumb(self, kind, sub):
        key = _thumb_key(kind, sub)
        if key in self._thumbs:
            return self._thumbs[key]
        img = None
        if kind == "tile":
            img = self.assets.tile(sub)
        elif kind == "small_tile":
            img = self.assets.tile_small(sub)
        elif kind == "spike":
            img = self.assets.spike(sub)
        elif kind == "mini_spike":
            img = self.assets.mini_spike(sub)
        elif kind == "vine":
            img = self.assets.vine(sub)
        elif kind == "water":
            img = self.assets.water(sub)
        elif kind == "platform":
            img = self.assets.platform()
        elif kind == "checkpoint":
            img = self.assets.checkpoint(False)
        elif kind in ("exit", "end"):
            img = self.assets.end()
        elif kind == "plus_jump":
            img = self.assets.plusjump()
        elif kind == "star":
            img = self.assets.star(sub)
        if img is not None:
            w, h = img.get_size()
            if w > 18 or h > 18:
                r = min(18 / w, 18 / h)
                img = pygame.transform.smoothscale(
                    img, (max(1, int(w * r)), max(1, int(h * r))))
            self._thumbs[key] = img
            return img
        # 自绘占位
        s = pygame.Surface((16, 16), pygame.SRCALPHA)
        if kind == "eraser":
            pygame.draw.line(s, ERR_RED, (2, 2), (14, 14), 2)
            pygame.draw.line(s, ERR_RED, (14, 2), (2, 14), 2)
        elif kind == "start":
            pygame.draw.rect(s, (80, 220, 120), (2, 2, 12, 12), 1)
            pygame.draw.circle(s, (80, 220, 120), (8, 8), 4)
        elif kind == "path_node":
            pygame.draw.rect(s, (255, 80, 220), (1, 1, 14, 14), 1)
            pygame.draw.circle(s, (255, 80, 220), (8, 8), 3)
            pygame.draw.line(s, (255, 80, 220), (13, 13), (15, 15), 2)
        self._thumbs[key] = s
        return s

    # ---------------- 放置 / 擦除（px/py 为已按网格粒度对齐的像素坐标） ----
    def place(self, px, py):
        kind, sub = self.tool
        room = self.room
        T = config.TILE_SIZE
        fine = self.grid < T          # 16px 及更细网格 → 写入 free_* 像素结构
        if kind == "eraser":
            self.erase_all_at(px, py)
            return
        if self._layer_blocked(kind):
            self.set_message(f"图层「{self._layer_label(kind)}」已锁定或隐藏",
                             ERR_RED)
            return
        self._undo_push()          # 修改前压栈（拖放批次中自动合并）
        if kind == "start":
            if self.grid >= T:
                # 32 粒度：放在格顶 → 玩家站在该格上
                room.start = (float(px + (T - config.KID_WIDTH) // 2),
                              float(py - config.KID_HEIGHT))
            else:
                room.start = (float(px), float(py))   # 细粒度：点哪放哪（碰撞箱左上角）
        elif kind == "tile":
            if fine:
                room.free_tiles[(px, py)] = sub   # 16px 及更细：砖块按像素定位
            else:
                room.set_tile(px // T, py // T, sub)
        elif kind == "small_tile":
            # 小砖块 16×16：始终按点击位置吸附 16px 格（任意网格粒度）
            room.small_tiles[((px // 16) * 16, (py // 16) * 16)] = sub
        elif kind == "spike":
            if fine:
                room.free_spikes[(px, py)] = sub
            else:
                room.spikes[(px // T, py // T)] = sub
        elif kind == "mini_spike":
            if self.grid < T:
                # 16px 及更细粒度：点击位置即 16px 单元 → 自动定象限
                # （不再用"小刺象限"按钮，否则 16px 格点击会落到别的象限）
                px16 = (px // 16) * 16
                py16 = (py // 16) * 16
                quad = ((py16 % T) // 16) * 2 + ((px16 % T) // 16)
                room.add_mini_spike(px16 // T, py16 // T, sub, quad)
            else:
                # 32 粒度：整格点击，用"小刺象限"按钮选中的象限
                room.add_mini_spike(px // T, py // T, sub, self.mini_quad)
        elif kind == "vine":
            if fine:
                room.free_vines[(px, py)] = sub
            else:
                room.vines[(px // T, py // T)] = sub
        elif kind == "water":
            if fine:
                room.free_water[(px, py)] = sub
            else:
                room.water[(px // T, py // T)] = sub
        elif kind == "platform":
            room.add_platform(px, py)               # 任意像素位置
        elif kind == "checkpoint":
            if fine:
                if (px, py) not in room.free_checkpoints:
                    room.free_checkpoints.append((px, py))
            else:
                c = (px // T, py // T)
                if c not in room.checkpoints:
                    room.checkpoints.append(c)
        elif kind == "exit":
            if fine:
                pos = (px, py)
                existing = next((e for e in room.free_exits
                                 if e["pos"] == pos), None)
                if existing is not None:
                    # 点击已有出口：选中它并载入其目标房间
                    #（点输入框后再回车 = 应用目标；不点输入框直接回车 = 测试）
                    self.selected_exit = pos
                    self.target_box.text = existing["target"]
                    self.set_message(f"已选中出口 {pos} → 点输入框改目标后回车")
                else:
                    # 新出口：用输入框当前的目标房间
                    target = self.target_box.text.strip() or "room001"
                    room.free_exits.append({"pos": pos, "target": target})
                    self.selected_exit = None
                    self.set_message(f"出口 {pos} → {target}")
            else:
                c = (px // T, py // T)
                existing = next((e for e in room.exits if e["tile"] == c), None)
                if existing is not None:
                    # 点击已有出口：选中它并载入其目标房间
                    self.selected_exit = c
                    self.target_box.text = existing["target"]
                    self.set_message(f"已选中出口 {c} → 点输入框改目标后回车")
                else:
                    # 新出口：用输入框当前的目标房间
                    target = self.target_box.text.strip() or "room001"
                    room.exits.append({"tile": c, "target": target})
                    self.selected_exit = None
                    self.set_message(f"出口 {c} → {target}")
        elif kind == "end":
            if fine:
                room.free_end = (px, py)
            else:
                room.end = (px // T, py // T)
        elif kind == "plus_jump":
            if fine:
                if (px, py) not in room.free_plus_jumps:
                    room.free_plus_jumps.append((px, py))
            else:
                c = (px // T, py // T)
                if c not in room.plus_jumps:
                    room.plus_jumps.append(c)
        elif kind == "star":
            if fine:
                c = (px, py)
                room.free_stars = [s for s in room.free_stars
                                   if (s[0], s[1]) != c]
                room.free_stars.append((c[0], c[1], sub))
            else:
                c = (px // T, py // T)
                room.stars = [s for s in room.stars if (s[0], s[1]) != c]
                room.stars.append((c[0], c[1], sub))
        elif kind == "path_node":
            c = (px, py)
            existing = self._node_at(c)
            if existing is not None:
                # 点已有节点 = 选中并进入轨迹编辑
                self.selected_path = existing
            else:
                # 空位 = 放置新节点并自动选中
                node = {"pos": c, "path": [],
                        "speed": config.PATH_DEFAULT_SPEED, "trigger": "auto"}
                room.path_nodes.append(node)
                self.selected_path = node
            self._path_last_cell = None
            self.panel_mode = "path"
            self.set_message("路径节点：按住左键拖动画轨迹（吸附网格）")
        else:
            self.set_message(f"未知工具 {kind}", ERR_RED)

    def erase_at(self, px, py):
        """按当前工具擦除该位置的元素（px/py 为像素）。"""
        kind, sub = self.tool
        room = self.room
        T = config.TILE_SIZE
        if kind == "eraser":
            self.erase_all_at(px, py)
            return
        if self._layer_blocked(kind):
            self.set_message(f"图层「{self._layer_label(kind)}」已锁定或隐藏",
                             ERR_RED)
            return
        self._undo_push()          # 修改前压栈
        fine = self.grid < T       # 16px 及更细：按像素擦 free_* 结构
        if kind == "tile":
            if fine:
                room.free_tiles.pop((px, py), None)
                if px % T == 0 and py % T == 0:   # 恰在 32 对齐点 → 连格子砖一起擦
                    room.set_tile(px // T, py // T, None)
            else:
                room.set_tile(px // T, py // T, None)
                self._clear_free_in_cell(room.free_tiles, px, py)
        elif kind == "small_tile":
            room.small_tiles.pop(((px // 16) * 16, (py // 16) * 16), None)
        elif kind == "spike":
            if fine:
                room.free_spikes.pop((px, py), None)
                if px % T == 0 and py % T == 0:
                    room.spikes.pop((px // T, py // T), None)
            else:
                room.spikes.pop((px // T, py // T), None)
                self._clear_free_in_cell(room.free_spikes, px, py)
        elif kind == "mini_spike":
            if self.grid < T:
                px16 = (px // 16) * 16
                py16 = (py // 16) * 16
                quad = ((py16 % T) // 16) * 2 + ((px16 % T) // 16)
                room.mini_spikes.pop((px16 // T, py16 // T, quad), None)
            else:
                room.mini_spikes.pop((px // T, py // T, self.mini_quad), None)
        elif kind == "vine":
            if fine:
                room.free_vines.pop((px, py), None)
                if px % T == 0 and py % T == 0:
                    room.vines.pop((px // T, py // T), None)
            else:
                room.vines.pop((px // T, py // T), None)
                self._clear_free_in_cell(room.free_vines, px, py)
        elif kind == "water":
            if fine:
                room.free_water.pop((px, py), None)
                if px % T == 0 and py % T == 0:
                    room.water.pop((px // T, py // T), None)
            else:
                room.water.pop((px // T, py // T), None)
                self._clear_free_in_cell(room.free_water, px, py)
        elif kind == "platform":
            # 平台可任意像素放置 → 擦除时按碰撞点找
            for i, (plx, ply) in enumerate(room.platforms):
                if pygame.Rect(plx, ply, 32, 16).collidepoint(px, py):
                    room.platforms.pop(i)
                    break
        elif kind == "checkpoint":
            if fine:
                if (px, py) in room.free_checkpoints:
                    room.free_checkpoints.remove((px, py))
            else:
                c = (px // T, py // T)
                if c in room.checkpoints:
                    room.checkpoints.remove(c)
                room.free_checkpoints = [
                    (fx, fy) for (fx, fy) in room.free_checkpoints
                    if not (px <= fx < px + T and py <= fy < py + T)]
        elif kind == "exit":
            if fine:
                room.free_exits = [e for e in room.free_exits
                                   if e["pos"] != (px, py)]
                if self.selected_exit == (px, py):
                    self.selected_exit = None
            else:
                c = (px // T, py // T)
                room.exits = [e for e in room.exits if e["tile"] != c]
                room.free_exits = [
                    e for e in room.free_exits
                    if not (px <= e["pos"][0] < px + T
                            and py <= e["pos"][1] < py + T)]
                if self.selected_exit == c or (
                        self.selected_exit is not None
                        and px <= self.selected_exit[0] < px + T
                        and py <= self.selected_exit[1] < py + T):
                    self.selected_exit = None
        elif kind == "end":
            if fine:
                if room.free_end == (px, py):
                    room.free_end = None
            else:
                if room.end == (px // T, py // T):
                    room.end = None
                if room.free_end is not None \
                        and px <= room.free_end[0] < px + T \
                        and py <= room.free_end[1] < py + T:
                    room.free_end = None
        elif kind == "plus_jump":
            if fine:
                if (px, py) in room.free_plus_jumps:
                    room.free_plus_jumps.remove((px, py))
            else:
                c = (px // T, py // T)
                if c in room.plus_jumps:
                    room.plus_jumps.remove(c)
                room.free_plus_jumps = [
                    (fx, fy) for (fx, fy) in room.free_plus_jumps
                    if not (px <= fx < px + T and py <= fy < py + T)]
        elif kind == "star":
            if fine:
                c = (px, py)
                room.free_stars = [s for s in room.free_stars
                                   if (s[0], s[1]) != c]
            else:
                c = (px // T, py // T)
                room.stars = [s for s in room.stars if (s[0], s[1]) != c]
                room.free_stars = [
                    s for s in room.free_stars
                    if not (px <= s[0] < px + T and py <= s[1] < py + T)]
        elif kind == "path_node":
            n = self._node_at((px, py))
            if n is not None:
                room.path_nodes.remove(n)
                if self.selected_path is n:
                    self.selected_path = None
                    self.panel_mode = "tools"

    def _clear_free_in_cell(self, container, px, py):
        """清掉 32px 格 [px,px+T)×[py,py+T) 内的 free_* 字典元素（格子擦除时用）。"""
        T = config.TILE_SIZE
        for key in [k for k in container
                    if px <= k[0] < px + T and py <= k[1] < py + T]:
            del container[key]

    def erase_all_at(self, px, py):
        """橡皮擦：清掉该位置全部元素（px/py 为像素）。"""
        room = self.room
        T = config.TILE_SIZE
        self._undo_push()          # 修改前压栈
        gx, gy = px // T, py // T
        cx0, cy0 = gx * T, gy * T       # 32px 格的像素范围（擦 free_* 用）
        if not self._layer_blocked("tile"):
            room.set_tile(gx, gy, None)
            self._clear_free_in_cell(room.free_tiles, cx0, cy0)
            # 小砖块（16px）：清掉 32px 格内的全部
            room.small_tiles = {
                k: v for k, v in room.small_tiles.items()
                if not (cx0 <= k[0] < cx0 + T and cy0 <= k[1] < cy0 + T)}
        if not self._layer_blocked("spike"):
            room.spikes.pop((gx, gy), None)
            for q in range(4):
                room.mini_spikes.pop((gx, gy, q), None)
            self._clear_free_in_cell(room.free_spikes, cx0, cy0)
        if not self._layer_blocked("vine"):
            room.vines.pop((gx, gy), None)
            self._clear_free_in_cell(room.free_vines, cx0, cy0)
        if not self._layer_blocked("water"):
            room.water.pop((gx, gy), None)
            self._clear_free_in_cell(room.free_water, cx0, cy0)
        if not self._layer_blocked("platform"):
            for i, (plx, ply) in enumerate(room.platforms):
                if pygame.Rect(plx, ply, 32, 16).collidepoint(px, py):
                    room.platforms.pop(i)
                    break
        if not self._layer_blocked("checkpoint"):
            if (gx, gy) in room.checkpoints:
                room.checkpoints.remove((gx, gy))
            room.free_checkpoints = [
                (fx, fy) for (fx, fy) in room.free_checkpoints
                if not (cx0 <= fx < cx0 + T and cy0 <= fy < cy0 + T)]
        if not self._layer_blocked("exit"):
            room.exits = [e for e in room.exits if e["tile"] != (gx, gy)]
            room.free_exits = [
                e for e in room.free_exits
                if not (cx0 <= e["pos"][0] < cx0 + T
                        and cy0 <= e["pos"][1] < cy0 + T)]
            if self.selected_exit == (gx, gy) or (
                    self.selected_exit is not None
                    and cx0 <= self.selected_exit[0] < cx0 + T
                    and cy0 <= self.selected_exit[1] < cy0 + T):
                self.selected_exit = None
        if not self._layer_blocked("end"):
            if room.end == (gx, gy):
                room.end = None
            if room.free_end is not None \
                    and cx0 <= room.free_end[0] < cx0 + T \
                    and cy0 <= room.free_end[1] < cy0 + T:
                room.free_end = None
        if not self._layer_blocked("plus_jump"):
            if (gx, gy) in room.plus_jumps:
                room.plus_jumps.remove((gx, gy))
            room.free_plus_jumps = [
                (fx, fy) for (fx, fy) in room.free_plus_jumps
                if not (cx0 <= fx < cx0 + T and cy0 <= fy < cy0 + T)]
        if not self._layer_blocked("star"):
            room.stars = [s for s in room.stars if (s[0], s[1]) != (gx, gy)]
            room.free_stars = [
                s for s in room.free_stars
                if not (cx0 <= s[0] < cx0 + T and cy0 <= s[1] < cy0 + T)]
        if not self._layer_blocked("path_node"):
            room.path_nodes = [
                n for n in room.path_nodes
                if not (cx0 <= n["pos"][0] < cx0 + T
                        and cy0 <= n["pos"][1] < cy0 + T)]
            if self.selected_path is not None \
                    and self.selected_path not in room.path_nodes:
                self.selected_path = None
                self.panel_mode = "tools"

    def _node_at(self, cell):
        """返回位于该像素格上的路径节点（None = 无）。"""
        return next((n for n in self.room.path_nodes
                     if n["pos"] == tuple(cell)), None)

    def _node_overlap_rects(self, node):
        """该节点 32×32 区重合的元素矩形（编辑器高亮"哪些会随节点移动"）。

        与游戏端 _attach_overlapping 的挂载判定一致（含格子/像素/小元素）。
        """
        room = self.room
        T = config.TILE_SIZE
        nrect = pygame.Rect(node["pos"][0], node["pos"][1], T, T)
        rects = []
        def add(px, py, w, h):
            r = pygame.Rect(px, py, w, h)
            if nrect.colliderect(r):
                rects.append(r)
        for (tx, ty) in room.tiles:
            add(tx * T, ty * T, T, T)
        for (px, py) in room.free_tiles:
            add(px, py, T, T)
        for (px, py) in room.small_tiles:
            add(px, py, 16, 16)
        for (px, py) in room.platforms:
            add(px, py, 32, 16)
        for (tx, ty) in room.spikes:
            add(tx * T, ty * T, T, T)
        for (px, py) in room.free_spikes:
            add(px, py, T, T)
        for (tx, ty, quad) in room.mini_spikes:
            qx = tx * T + (T // 2 if quad in (1, 3) else 0)
            qy = ty * T + (T // 2 if quad in (2, 3) else 0)
            add(qx, qy, 16, 16)
        for (tx, ty) in room.vines:
            add(tx * T, ty * T, T, T)
        for (px, py) in room.free_vines:
            add(px, py, T, T)
        for (tx, ty) in room.water:
            add(tx * T, ty * T, T, T)
        for (px, py) in room.free_water:
            add(px, py, T, T)
        for (tx, ty) in room.checkpoints:
            add(tx * T, ty * T, T, T)
        for (px, py) in room.free_checkpoints:
            add(px, py, T, T)
        for e in room.exits:
            add(e["tile"][0] * T, e["tile"][1] * T, T, T)
        for e in room.free_exits:
            add(e["pos"][0], e["pos"][1], T, T)
        if room.end is not None:
            add(room.end[0] * T, room.end[1] * T, T, T)
        if room.free_end is not None:
            add(room.free_end[0], room.free_end[1], T, T)
        for (tx, ty) in room.plus_jumps:
            add(tx * T, ty * T, T, T)
        for (px, py) in room.free_plus_jumps:
            add(px, py, T, T)
        for (tx, ty, _lv) in room.stars:
            add(tx * T, ty * T, T, T)
        for (px, py, _lv) in room.free_stars:
            add(px, py, T, T)
        return rects

    # ---------------- 保存 / 加载 / 撤销 ----------------
    def set_message(self, text, color=OK_GREEN):
        self.message = text
        self.message_color = color
        self.message_timer = 180

    def _click_sound(self):
        """按钮点击音效（sound/sndCherry.wav）；无声卡/缺文件时静默。"""
        try:
            self.sounds.play("ui_click")
        except Exception:
            pass

    def _undo_push(self):
        """把当前房间快照压入撤销栈（**修改前**调用）。

        拖放批次（_undo_batching）中不重复压栈——一次 Shift 拖放
        合并为一次撤销。栈上限 100 步。
        """
        if self._undo_batching:
            return
        try:
            data = self.room.to_json()
        except Exception:
            return
        self._undo_stack.append(data)
        if len(self._undo_stack) > 100:
            self._undo_stack.pop(0)

    def _undo(self):
        """Ctrl+Z：撤销上一步修改（放置/擦除/背景/清空等）。"""
        if not self._undo_stack:
            self.set_message("没有可撤销的操作", ERR_RED)
            return
        self._undo_batching = False
        try:
            self.room = Room.from_json(self._undo_stack.pop())
        except Exception as exc:
            self.set_message(f"撤销失败：{exc}", ERR_RED)
            return
        self._sync_bg_controls()
        self._sync_music_controls()
        self._sync_tex_controls()
        self.selected_path = None
        self._path_drawing = False
        if self.panel_mode == "path":
            self.panel_mode = "tools"
        self.set_message("已撤销")

    def _apply_selected_exit(self):
        """把输入框内容应用到选中出口的目标房间。"""
        if self.selected_exit is None:
            return
        target = self.target_box.text.strip() or "room001"
        for e in self.room.exits:
            if e["tile"] == self.selected_exit:
                e["target"] = target
        for e in self.room.free_exits:
            if e["pos"] == self.selected_exit:
                e["target"] = target
        self.set_message(f"出口 {self.selected_exit} → {target} 已更新")

    def save(self):
        name = self.name_box.text.strip()
        if not name:
            self.set_message("房间名不能为空", ERR_RED)
            return
        if any(ch in name for ch in '\\/:*?"<>| '):
            self.set_message("房间名含非法字符", ERR_RED)
            return
        self.room.name = name
        os.makedirs(config.ROOMS_DIR, exist_ok=True)
        path = room_path(name)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(self.room.to_json(), f, ensure_ascii=False, indent=2)
        clear_cache()
        self.current_room_name = name
        self._refresh_rooms()
        # 保存提示：没有挂到任何元素的路径节点（选中节点时画布会绿色高亮重合元素）
        empty_nodes = [n for n in self.room.path_nodes
                       if not self._node_overlap_rects(n)]
        if empty_nodes:
            self.set_message(
                f"已保存 rooms/{name}.json（警告：{len(empty_nodes)} 个路径节点"
                f"没挂到任何元素，选中节点查看绿色高亮）", ERR_RED)
        else:
            self.set_message(f"已保存 rooms/{name}.json")

    def load(self):
        self._load_name(self.name_box.text.strip())

    # ---------------- 保存工程 / 打包 exe ----------------
    def _pick_dir(self, title):
        """弹出系统文件夹选择框（tkinter）。取消/失败返回 None。"""
        try:
            import tkinter as tk
            from tkinter import filedialog
            root = tk.Tk()
            root.withdraw()
            root.attributes("-topmost", True)
            path = filedialog.askdirectory(title=title)
            root.destroy()
            return path if path else None
        except Exception:
            return None

    def _save_project_btn(self):
        """保存工程：备份关卡内容到所选文件夹。"""
        self._click_sound()
        path = self._pick_dir("选择「保存工程」的目标文件夹")
        if not path:
            self.set_message("已取消保存工程", ERR_RED)
            return
        result = pack_mod.save_project(path, progress=self._pack_status_set)
        self.set_message(result, OK_GREEN if "已保存" in result else ERR_RED)

    def _load_project_btn(self):
        """加载工程：把备份内容（关卡/音乐/背景/材质）复制回项目。"""
        self._click_sound()
        path = self._pick_dir("选择「工程备份」文件夹（存工程生成的）")
        if not path:
            self.set_message("已取消加载工程", ERR_RED)
            return
        result = pack_mod.load_project(path, progress=self._pack_status_set)
        clear_cache()                     # 导入的房间重新读取
        self._refresh_rooms()
        self._sync_bg_controls()          # 背景图/材质/音乐下拉刷新
        self._sync_music_controls()
        self._sync_tex_controls()
        self.set_message(result, OK_GREEN if "已导入" in result else ERR_RED)

    def _package_btn(self):
        """打包为 exe：选输出目录 → 后台 PyInstaller 打包 + 复制数据。"""
        self._click_sound()
        # 打包前强制应用当前面板的标题/图标（防止"选了没应用"导致 exe 没图标）
        if self.panel_mode == "settings":
            self._apply_settings()
        path = self._pick_dir("选择「打包 exe」的输出目录")
        if not path:
            self.set_message("已取消打包", ERR_RED)
            return
        if self._pack_thread is not None and self._pack_thread.is_alive():
            self.set_message("正在打包中，请稍候...", ERR_RED)
            return
        self._pack_done = False
        self._pack_result = ""
        self._pack_thread = threading.Thread(
            target=self._pack_worker, args=(path,), daemon=True)
        self._pack_thread.start()
        self._pack_status_set("正在打包（约 1-3 分钟）...")

    def _pack_worker(self, path):
        try:
            result = pack_mod.build_exe(
                path, progress=self._pack_status_set)
        except Exception as exc:            # 打包线程内兜底，不让编辑器崩
            result = f"打包异常：{exc}"
        self._pack_result = result
        self._pack_done = True

    def _pack_status_set(self, msg):
        self._pack_status = msg             # 线程写入；主循环 update 里显示

    def _poll_pack(self):
        """主循环轮询打包线程：显示进度；结束后展示结果。"""
        if self._pack_thread is not None:
            if self._pack_done:
                result = self._pack_result
                self._pack_thread = None
                self._pack_done = False
                self.set_message(result,
                                 OK_GREEN if "已生成" in result or
                                 "已保存" in result else ERR_RED)
            elif self._pack_status:
                self.set_message(self._pack_status, OK_GREEN)

    def clear_room(self):
        name = self.name_box.text.strip() or "room001"
        self._undo_push()
        self.room = Room(name)
        self.current_room_name = name
        self.selected_path = None
        self._sync_bg_controls()
        self._sync_music_controls()
        self._sync_tex_controls()
        self.set_message("已清空房间")

    # ---------------- 背景设置 ----------------
    def _apply_bg_color(self):
        try:
            r = min(255, max(0, int(self.bg_r_box.text.strip() or 0)))
            g = min(255, max(0, int(self.bg_g_box.text.strip() or 0)))
            b = min(255, max(0, int(self.bg_b_box.text.strip() or 0)))
        except ValueError:
            self.set_message("颜色需为 0-255 数字", ERR_RED)
            return
        self._undo_push()
        self.room.bg_color = (r, g, b)
        self._sync_bg_controls()
        self.set_message(f"背景色 RGB({r},{g},{b})")

    def _set_bg_color(self, color):
        self._undo_push()
        self.room.bg_color = tuple(color)
        self._sync_bg_controls()

    def _apply_bg_image(self):
        name = self.bg_image_box.text.strip()
        self._undo_push()
        if name:
            self.room.bg_image = name
            self.set_message(f"背景图 {name}（文件放 assets/backgrounds/）")
        else:
            self.room.bg_image = None
            self.set_message("已清除背景图（纯色背景）")
        self._sync_bg_controls()

    def _clear_bg_image(self):
        self._undo_push()
        self.room.bg_image = None
        self.bg_image_box.text = ""
        self.bg_img_dropdown.value = "（无）"
        self._sync_bg_controls()       # 刷新画布背景缓存 → 立即回到纯色
        self.set_message("已清除背景图（纯色背景）")

    # ---------------- 事件 ----------------
    def handle_event(self, event):
        if event.type == pygame.QUIT:
            self.running = False
            return
        if event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
            self.running = False
            return
        if event.type == pygame.KEYDOWN and event.key == pygame.K_RETURN:
            # 回车两用，互不冲突：
            #   · 出口目标输入框**聚焦**且选中了出口 → 回车 = 应用目标（不测试）
            #   · 其他任何时候 → 保存并启动游戏测试
            if self.target_box.active and self.selected_exit is not None:
                self._apply_selected_exit()
                self.target_box.active = False
                return
            self._test_game()
            return
        if event.type == pygame.KEYDOWN and \
                getattr(event, "mod", 0) & pygame.KMOD_CTRL:
            if event.key == pygame.K_s:
                self.save()
            elif event.key == pygame.K_l:
                self.load()
            elif event.key == pygame.K_z:
                self._undo()
            return
        if self.panel_mode == "bg":
            self._handle_bg_event(event)
            return
        if self.panel_mode == "tex":
            self._handle_tex_event(event)
            return
        if self.panel_mode == "path":
            self._handle_path_event(event)
            return
        if self.panel_mode == "settings":
            self._handle_settings_event(event)
            return
        # ---- 下拉框优先：展开中的下拉选项必须能点 ----
        # （旧顺序把输入框放前面，房间下拉的选项列表盖住输入框时点不到选项。
        #   现在下拉先判定：点选项 = 选中；点选项外 = 收起下拉（输入框随后可点）。）
        r = self.room_dropdown.handle(event)
        if r == "selected":
            self._click_sound()
            self._load_name(self.room_dropdown.value)
            return
        if r:
            self.music_dropdown.open = False
            self.music_def_dropdown.open = False
            return
        r = self.music_dropdown.handle(event)
        if r == "selected":
            self._click_sound()
            self._apply_music(self.music_dropdown.value)
            return
        if r:
            self.room_dropdown.open = False
            self.music_def_dropdown.open = False
            return
        r = self.music_def_dropdown.handle(event)
        if r == "selected":
            self._click_sound()
            self._apply_default_music(self.music_def_dropdown.value)
            return
        if r:
            self.room_dropdown.open = False
            self.music_dropdown.open = False
            return
        # 文本框（所有下拉收起/点选项外后，正常聚焦输入）
        if self.name_box.handle(event) or self.target_box.handle(event):
            if event.type == pygame.MOUSEBUTTONDOWN:
                self.room_dropdown.open = False
                self.music_dropdown.open = False
                self.music_def_dropdown.open = False
            return
        if event.type == pygame.MOUSEBUTTONDOWN:
            if event.button == 1:
                # 背景音乐 试听 / 停止
                if self.music_play_btn.collidepoint(event.pos):
                    self._click_sound()
                    v = self.music_dropdown.value
                    if v == "（无）":
                        self.set_message("请先选择一首背景音乐", ERR_RED)
                    else:
                        self.music.play(v, restart=True)
                        self.set_message(f"试听：{v}")
                    return
                if self.music_stop_btn.collidepoint(event.pos):
                    self._click_sound()
                    self.music.stop()
                    self.set_message("停止试听")
                    return
                # Shift+左键点画布 = 进入"连续拖放"模式（拖动连续放置）。
                # 注意：MOUSEBUTTONDOWN 事件没有 mod 属性（只有 KEYDOWN 有），
                # 必须用 pygame.key.get_mods() 读键盘修饰键状态。
                if pygame.key.get_mods() & pygame.KMOD_SHIFT \
                        and self._grid_at(event.pos) is not None:
                    self._drag_placing = True
                    self._last_drag_cell = None
                    self._undo_push()          # 先压栈（此时还未进入批次）
                    self._undo_batching = True # 之后拖动中合并为一次撤销
                    self._place_at_pos(event.pos)
                    self._last_drag_cell = self._grid_at(event.pos)
                    return
                # 面板按钮（左工具 + 右设置：保存/加载/材质/背景/清空/退出/
                # 网格/象限/图层/工具列表 → 全部播点击音效）
                if self._hit_panel_button(event.pos):
                    self._click_sound()
                    return
                # 画布放置：直接用事件坐标算格（不等 hover——
                # 鼠标移动后立即点击时 hover 还是上一帧的值，会放错格）
                self._place_at_pos(event.pos)
            elif event.button == 3:
                self._erase_at_pos(event.pos)
        elif event.type == pygame.MOUSEBUTTONUP and event.button == 1:
            if self._drag_placing:
                self._drag_placing = False
                self._undo_batching = False
                self._last_drag_cell = None
                return
        elif event.type == pygame.MOUSEWHEEL:
            self.scroll -= event.y * 24
            self._clamp_scroll()   # 工具列表滚动到边界即停，不无限滚

    def _clamp_scroll(self):
        """工具列表滚动范围：0（顶部）到"列表总高 - 可视区高"（底部）。"""
        total = sum(20 if "sep" in it else 26 for it in self.tools)
        view = L_TOOLS_BOTTOM - L_TOOLS_TOP
        self.scroll = max(0, min(self.scroll, max(0, total - view)))

    # ---------------- 材质设置面板事件 ----------------
    def _handle_tex_event(self, event):
        # 对象类型下拉（切对象 → 重建子类型 + 同步该对象的材质显示）
        r = self.tex_slot_dropdown.handle(event)
        if r == "selected":
            self._click_sound()
            self._on_tex_obj_changed()
            return
        if r:
            return
        # 子类型下拉（如 block_3 / first / 激活 → 同步该子类型的材质显示）
        r = self.tex_sub_dropdown.handle(event)
        if r == "selected":
            self._click_sound()
            self._sync_tex_controls()
            return
        if r:
            return
        # 材质图片下拉（选中即应用）
        r = self.tex_img_dropdown.handle(event)
        if r == "selected":
            self._click_sound()
            self._apply_tex(self.tex_img_dropdown.value)
            return
        if r:
            return
        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            if self.tex_clear_btn.collidepoint(event.pos):
                self._click_sound()
                self._clear_tex()
            elif self.tex_back_btn.collidepoint(event.pos):
                self._click_sound()
                self.panel_mode = "tools"

    # ---------------- 路径节点面板事件（画轨迹 / 设置） ----------------
    def _handle_path_event(self, event):
        node = self.selected_path
        if node is None:
            self.panel_mode = "tools"
            return
        # 画布：左键按下/拖拽 = 画轨迹（吸附网格）；点节点 = 切换选中
        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            cell = self._grid_at(event.pos)
            if cell is not None:
                if self._node_at(cell) is not None:
                    self.selected_path = self._node_at(cell)   # 切到该节点
                    self._path_last_cell = None
                    return
                self._undo_push()          # 一次拖画 = 一次撤销
                self._undo_batching = True
                self._add_path_point(cell)
                self._path_drawing = True
                return
        elif event.type == pygame.MOUSEMOTION and self._path_drawing:
            cell = self._grid_at(event.pos)
            if cell is not None and cell != self._path_last_cell:
                self._add_path_point(cell)
            return
        elif event.type == pygame.MOUSEBUTTONUP and event.button == 1:
            self._path_drawing = False
            self._undo_batching = False
            return
        # 面板按钮
        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            if self.path_speed_dec_btn.collidepoint(event.pos):
                self._click_sound()
                self._adjust_path_speed(-config.PATH_SPEED_STEP)
            elif self.path_speed_inc_btn.collidepoint(event.pos):
                self._click_sound()
                self._adjust_path_speed(config.PATH_SPEED_STEP)
            elif self.path_auto_btn.collidepoint(event.pos):
                self._click_sound()
                self._set_path_trigger("auto")
            elif self.path_touch_btn.collidepoint(event.pos):
                self._click_sound()
                self._set_path_trigger("touch")
            elif self.path_clear_btn.collidepoint(event.pos):
                self._click_sound()
                self._clear_path()
            elif self.path_delete_btn.collidepoint(event.pos):
                self._click_sound()
                self._delete_selected_node()
            elif self.path_done_btn.collidepoint(event.pos):
                self._click_sound()
                self._done_path()

    def _add_path_point(self, cell):
        """给选中节点追加一个轨迹点（吸附网格；去重连续重复点和原点）。"""
        node = self.selected_path
        if node is None:
            return
        path = node["path"]
        cell = (cell[0], cell[1])
        if not path and cell == tuple(node["pos"]):
            return                       # 第一个点与原点相同 → 不重复
        if path and path[-1] == cell:
            return
        path.append(cell)
        self._path_last_cell = cell

    def _adjust_path_speed(self, delta):
        node = self.selected_path
        if node is None:
            return
        self._undo_push()
        node["speed"] = round(max(config.PATH_MIN_SPEED,
                                  min(config.PATH_MAX_SPEED,
                                      node["speed"] + delta)), 2)
        self.set_message(f"速度 {node['speed']:.2f} 像素/帧")

    def _set_path_trigger(self, mode):
        node = self.selected_path
        if node is None:
            return
        self._undo_push()
        node["trigger"] = mode
        self.set_message("触发：自动开始" if mode == "auto"
                         else "触发：玩家碰到才开始")

    def _clear_path(self):
        node = self.selected_path
        if node is None:
            return
        self._undo_push()
        node["path"] = []
        self._path_last_cell = None
        self.set_message("已清除轨迹")

    def _delete_selected_node(self):
        if self.selected_path is None:
            return
        self._undo_push()
        self.room.path_nodes.remove(self.selected_path)
        self.selected_path = None
        self._path_drawing = False
        self.panel_mode = "tools"
        self.set_message("已删除路径节点")

    def _done_path(self):
        self.selected_path = None
        self._path_drawing = False
        self._undo_batching = False
        self.panel_mode = "tools"
        self.set_message("路径完成（用「路径节点」工具点节点可再编辑）")

    # ---------------- 项目设置（游戏标题 / 程序图标） ----------------
    def _refresh_icon_images(self):
        """扫描 assets/ 根目录的图标文件（.ico/.png 等）填充下拉。"""
        files = []
        if os.path.isdir(config.ASSET_DIR):
            files = sorted(
                f for f in os.listdir(config.ASSET_DIR)
                if f.lower().endswith((".ico", ".png", ".jpg", ".jpeg",
                                       ".bmp")))
        self.icon_dropdown.set_items(["（无）"] + files)
        icon = settings.get_icon()
        self.icon_dropdown.value = icon if icon in files else "（无）"

    def _apply_settings(self):
        """保存游戏标题 + 程序图标（editor_settings.json，游戏/打包读取）。"""
        settings.set_title(self.title_box.text)
        v = self.icon_dropdown.value
        settings.set_icon(None if v == "（无）" else v)
        self._refresh_icon_images()
        self.set_message(
            f"已应用：标题「{settings.get_title()}」 图标 "
            f"{settings.get_icon() or '无'}")

    # ---------------- 项目设置面板事件 ----------------
    def _handle_settings_event(self, event):
        if self.title_box.handle(event):
            return
        r = self.icon_dropdown.handle(event)
        if r == "selected":
            # 图标下拉选中即保存（防止选了忘点「应用设置」，打包时读不到）
            self._click_sound()
            self._apply_settings()
            return
        if r:
            return
        if event.type == pygame.KEYDOWN and event.key == pygame.K_RETURN:
            if self.title_box.active:
                self._click_sound()
                self._apply_settings()
                self.title_box.active = False
            return
        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            if self.settings_apply_btn.collidepoint(event.pos):
                self._click_sound()
                self._apply_settings()
            elif self.settings_back_btn.collidepoint(event.pos):
                self._click_sound()
                self._apply_settings()       # 离开面板也保存（防漏）
                self.panel_mode = "tools"

    # ---------------- 背景设置面板事件 ----------------
    def _handle_bg_event(self, event):
        for box in (self.bg_r_box, self.bg_g_box, self.bg_b_box,
                    self.bg_image_box):
            if box.handle(event):
                return
        r = self.bg_img_dropdown.handle(event)
        if r == "selected":
            self._click_sound()
            v = self.bg_img_dropdown.value
            self.bg_image_box.text = "" if v == "（无）" else v
            self._apply_bg_image()
            return
        if r:
            return
        # 预览框拖拽（缩放模式）：移动框 / 缩放框
        if self.room.bg_mode == "zoom" and self._bg_box is not None:
            if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                hit = self._bg_box.inflate(10, 10).collidepoint(event.pos)
                if hit:
                    # 靠近框边(≤7px) = 缩放，否则移动
                    near = (abs(event.pos[0] - self._bg_box.left) <= 7 or
                            abs(event.pos[0] - self._bg_box.right) <= 7 or
                            abs(event.pos[1] - self._bg_box.top) <= 7 or
                            abs(event.pos[1] - self._bg_box.bottom) <= 7)
                    self._bg_drag = (
                        "resize" if near else "move",
                        event.pos,
                        self.room.bg_zoom,
                        list(self.room.bg_offset),
                        self._bg_box.width)
                    return
            elif event.type == pygame.MOUSEMOTION and self._bg_drag is not None:
                self._apply_bg_drag(event.pos)
                return
            elif event.type == pygame.MOUSEBUTTONUP:
                self._bg_drag = None
                return
        elif event.type in (pygame.MOUSEMOTION, pygame.MOUSEBUTTONUP):
            self._bg_drag = None
        if event.type == pygame.MOUSEWHEEL:
            if self.room.bg_mode == "zoom" and self.room.bg_image:
                self.room.bg_zoom = max(0.25, min(
                    4.0, round(self.room.bg_zoom + 0.1 * event.y, 2)))
                self._sync_bg_controls()
            return
        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            if self.bg_apply_color_btn.collidepoint(event.pos):
                self._click_sound()
                self._apply_bg_color()
            elif self.bg_apply_img_btn.collidepoint(event.pos):
                self._click_sound()
                self._apply_bg_image()
            elif self.bg_clear_img_btn.collidepoint(event.pos):
                self._click_sound()
                self._clear_bg_image()
            elif self.bg_back_btn.collidepoint(event.pos):
                self._click_sound()
                self.panel_mode = "tools"
            elif self.zoom_dec_btn.collidepoint(event.pos):
                self._click_sound()
                self.room.bg_zoom = max(0.25, round(self.room.bg_zoom - 0.1, 2))
                self._sync_bg_controls()
            elif self.zoom_inc_btn.collidepoint(event.pos):
                self._click_sound()
                self.room.bg_zoom = min(4.0, round(self.room.bg_zoom + 0.1, 2))
                self._sync_bg_controls()
            elif self.offx_dec_btn.collidepoint(event.pos):
                self._click_sound()
                self.room.bg_offset[0] -= 16
                self._sync_bg_controls()
            elif self.offx_inc_btn.collidepoint(event.pos):
                self._click_sound()
                self.room.bg_offset[0] += 16
                self._sync_bg_controls()
            elif self.offy_dec_btn.collidepoint(event.pos):
                self._click_sound()
                self.room.bg_offset[1] -= 16
                self._sync_bg_controls()
            elif self.offy_inc_btn.collidepoint(event.pos):
                self._click_sound()
                self.room.bg_offset[1] += 16
                self._sync_bg_controls()
            else:
                for i, (rect, _label) in enumerate(self.bg_mode_btns):
                    if rect.collidepoint(event.pos):
                        self._click_sound()
                        self.room.bg_mode = self.bg_modes[i][0]
                        self._sync_bg_controls()
                        break
                else:
                    for rect, color in zip(self.bg_palette_rects,
                                           self.bg_palette):
                        if rect.collidepoint(event.pos):
                            self._click_sound()
                            self._set_bg_color(color)
                            break

    def _apply_bg_drag(self, pos):
        """预览框拖拽：move → 改偏移；resize → 改缩放。"""
        mode, start_pos, start_zoom, start_off, start_w = self._bg_drag
        k = self._bg_k or 0.01
        dx = pos[0] - start_pos[0]
        dy = pos[1] - start_pos[1]
        if mode == "move":
            zoom = start_zoom
            ox = start_off[0] + int(dx / k * zoom)
            oy = start_off[1] + int(dy / k * zoom)
        else:   # resize：框宽变化 → 反算缩放倍数
            nw = max(12, start_w + dx)
            zoom = max(0.25, min(4.0, config.ROOM_WIDTH / (nw / k)))
            ox, oy = start_off
        self.room.bg_zoom = round(zoom, 2)
        self.room.bg_offset = [max(-3000, min(3000, ox)),
                               max(-3000, min(3000, oy))]
        self._sync_bg_controls()

    def _grid_at(self, pos):
        """鼠标位置 → 按当前网格粒度对齐的像素坐标（画布内）。"""
        mx, my = pos
        mx -= CANVAS_X                     # 画布在窗口中有左偏移
        if 0 <= mx < config.ROOM_WIDTH and 0 <= my < config.ROOM_HEIGHT:
            g = self.grid
            return ((mx // g) * g, (my // g) * g)
        return None

    def _placement_rect(self, hx, hy):
        """当前工具在 hover 格 (hx,hy) **实际**放置的矩形。

        与 place() 的落点规则完全一致：32×32 元素（砖块/尖刺/藤蔓/水/物体）
        始终吸附 32 格 → 细网格下高亮也吸附到 32 格，不再显示会误导的细格框
        （这也是"16px 网格放砖块和 32px 没区别"的视觉原因：砖块就是 32×32）。
        """
        kind = self.tool[0]
        if kind == "eraser":
            return pygame.Rect(hx, hy, self.grid, self.grid)
        if kind == "small_tile":
            return pygame.Rect((hx // 16) * 16, (hy // 16) * 16, 16, 16)
        if kind == "mini_spike":
            if self.grid >= T:
                tx = (hx // T) * T
                ty = (hy // T) * T
                qx = tx + (T // 2 if self.mini_quad in (1, 3) else 0)
                qy = ty + (T // 2 if self.mini_quad in (2, 3) else 0)
                return pygame.Rect(qx, qy, 16, 16)
            return pygame.Rect((hx // 16) * 16, (hy // 16) * 16, 16, 16)
        if kind == "platform":
            return pygame.Rect(hx, hy, 32, 16)
        if kind == "start":
            if self.grid >= T:
                gx = (hx // T) * T + (T - config.KID_WIDTH) // 2
                gy = (hy // T) * T - config.KID_HEIGHT
                return pygame.Rect(gx, gy, config.KID_WIDTH, config.KID_HEIGHT)
            return pygame.Rect(hx, hy, self.grid, self.grid)
        # 其余 32×32 贴图元素：hx/hy 已按网格粒度对齐（32 网格 = 32 对齐，
        # 16px 及更细 = 像素放置）→ 高亮直接就是放置矩形
        return pygame.Rect(hx, hy, T, T)

    def _place_at_pos(self, pos):
        g = self._grid_at(pos)
        if g is not None:
            self.place(*g)

    def _erase_at_pos(self, pos):
        g = self._grid_at(pos)
        if g is not None:
            self.erase_at(*g)

    def _hit_panel_button(self, pos):
        # 右侧设置面板按钮
        if self.save_btn.collidepoint(pos):
            self.save()
            return True
        if self.load_btn.collidepoint(pos):
            self.load()
            return True
        if self.project_btn.collidepoint(pos):
            self._save_project_btn()
            return True
        if self.load_project_btn.collidepoint(pos):
            self._load_project_btn()
            return True
        if self.exe_btn.collidepoint(pos):
            self._package_btn()
            return True
        if self.tex_btn.collidepoint(pos):
            self.panel_mode = "tex"
            self._sync_tex_controls()
            return True
        if self.bg_btn.collidepoint(pos):
            self.panel_mode = "bg"
            self._sync_bg_controls()
            return True
        if self.settings_btn.collidepoint(pos):
            self.panel_mode = "settings"
            self.title_box.text = settings.get_title()
            self._refresh_icon_images()
            return True
        if self.clear_btn.collidepoint(pos):
            self.clear_room()
            return True
        if self.exit_btn.collidepoint(pos):
            self.running = False
            return True
        # 左侧：小刺象限按钮（仅 32 网格生效；16px 及更细按点击位置自动定象限）
        if self.grid >= T:
            for i, (rect, _label) in enumerate(self.quad_btns):
                if rect.collidepoint(pos):
                    self.mini_quad = i
                    return True
        # 左侧：网格粒度按钮
        for rect, g in self.grid_btns:
            if rect.collidepoint(pos):
                self.grid = g
                return True
        # 左侧：图层 可见/锁定 切换
        for i, (name, _label, _kinds) in enumerate(LAYERS):
            y = LAYER_ROW_Y + i * 20
            vis = pygame.Rect(6, y, 20, 16)
            lok = pygame.Rect(28, y, 20, 16)
            if vis.collidepoint(pos):
                self.layer_visible[name] = not self.layer_visible[name]
                self._save_layer_settings()
                return True
            if lok.collidepoint(pos):
                self.layer_locked[name] = not self.layer_locked[name]
                self._save_layer_settings()
                return True
        # 左侧：工具列表（只响应可视区内的项）
        x0, x1 = 4, LEFT_W - 4
        y = self.tool_list_top()
        for item in self.tools:
            if "sep" in item:
                y += 20
                continue
            rect = pygame.Rect(x0, y, x1 - x0, 24)
            if rect.top > L_TOOLS_BOTTOM:
                break                       # 已滚出可视区
            if rect.bottom >= L_TOOLS_TOP and rect.collidepoint(pos):
                self.tool = (item["kind"], item["sub"])
                return True
            y += 26
        return False

    def tool_list_top(self):
        return L_TOOLS_TOP - self.scroll

    def update(self):
        self._poll_pack()                    # 打包线程进度/结果
        self.mouse_pos = pygame.mouse.get_pos()
        mx, my = self.mouse_pos
        mx -= CANVAS_X
        if 0 <= mx < config.ROOM_WIDTH and 0 <= my < config.ROOM_HEIGHT:
            g = self.grid
            self.hover = ((mx // g) * g, (my // g) * g)
        else:
            self.hover = None
        # Shift 拖放连续放置：按住 Shift + 左键拖动，经过的每个新格子都放置
        if self._drag_placing:
            pressed = pygame.mouse.get_pressed()
            mods = pygame.key.get_mods()
            if not (pressed[0] and mods & pygame.KMOD_SHIFT):
                self._drag_placing = False
                self._undo_batching = False
                self._last_drag_cell = None
            else:
                cell = self._grid_at(self.mouse_pos)
                if cell is not None and cell != self._last_drag_cell:
                    self._last_drag_cell = cell
                    self.place(*cell)      # 批次中不重复压撤销栈
        if self.message_timer > 0:
            self.message_timer -= 1
            if self.message_timer == 0:
                self.message = ""

    # ---------------- 绘制 ----------------
    def draw(self):
        self._draw_canvas()
        self._draw_left_panel()
        if self.panel_mode == "bg":
            self._draw_bg_panel()
        elif self.panel_mode == "tex":
            self._draw_tex_panel()
        elif self.panel_mode == "path":
            self._draw_path_panel()
        elif self.panel_mode == "settings":
            self._draw_settings_panel()
        else:
            self._draw_right_panel()
        pygame.display.flip()

    def _draw_canvas(self):
        """画布画到独立 surface（房间坐标 0..800），再整体平移到窗口中间。

        背景按当前 bg_color/bg_image/bg_mode/zoom/offset 实时渲染（带缓存，
        属性变化由 _sync_bg_controls 置脏）。
        """
        s = self._canvas
        s.fill(self.room.bg_color)
        if self.room.bg_image:
            if self._bg_dirty or self._bg_cache is None:
                img = self.assets.background(self.room.bg_image)
                self._bg_cache = render_background(
                    img, self.room.bg_color, self.room.bg_mode,
                    self.room.bg_zoom, self.room.bg_offset,
                    (config.ROOM_WIDTH, config.ROOM_HEIGHT)) if img else None
                self._bg_dirty = False
            if self._bg_cache is not None:
                s.blit(self._bg_cache, (0, 0))
        room = self.room
        # 砖块（地形层）
        if self._layer_visible("tile"):
            for (tx, ty), typ in room.tiles.items():
                img = texture_for(self.assets, room, f"tile:{typ}",
                                  self.assets.tile(typ))
                s.blit(img, (tx * T, ty * T))
            for (px, py), typ in room.free_tiles.items():
                img = texture_for(self.assets, room, f"tile:{typ}",
                                  self.assets.tile(typ))
                s.blit(img, (px, py))
            # 小砖块（16×16，原贴图缩放；有自定义砖块材质时同步替换）
            for (px, py), typ in room.small_tiles.items():
                img = texture_for(self.assets, room, f"tile:{typ}",
                                  self.assets.tile_small(typ))
                s.blit(img, (px, py))
        # 单向平台（平台层）
        if self._layer_visible("platform"):
            for px, py in room.platforms:
                img = texture_for(self.assets, room, "platform",
                                  self.assets.platform())
                s.blit(img, (px, py))
        # 尖刺 / 小刺（危险层）
        if self._layer_visible("spike"):
            for (tx, ty), d in room.spikes.items():
                img = texture_for(self.assets, room, f"spike:{d}",
                                  self.assets.spike(d))
                s.blit(img, (tx * T, ty * T))
            for (px, py), d in room.free_spikes.items():
                img = texture_for(self.assets, room, f"spike:{d}",
                                  self.assets.spike(d))
                s.blit(img, (px, py))
            for (tx, ty, quad), d in room.mini_spikes.items():
                qx = tx * T + (T // 2 if quad in (1, 3) else 0)
                qy = ty * T + (T // 2 if quad in (2, 3) else 0)
                img = texture_for(self.assets, room, f"mini_spike:{d}",
                                  self.assets.mini_spike(d))
                s.blit(img, (qx, qy))
        # 藤蔓（平台层）
        if self._layer_visible("vine"):
            for (tx, ty), side in room.vines.items():
                img = texture_for(self.assets, room, f"vine:{side}",
                                  self.assets.vine(side))
                s.blit(img, (tx * T, ty * T))
            for (px, py), side in room.free_vines.items():
                img = texture_for(self.assets, room, f"vine:{side}",
                                  self.assets.vine(side))
                s.blit(img, (px, py))
        # Checkpoint / 跳跃球 / 星星 / 出口 / 终点 / 出生点（物体层）
        if self._layer_visible("checkpoint"):
            for (tx, ty) in room.checkpoints:
                img = texture_for(self.assets, room, "checkpoint:inactive",
                                  self.assets.checkpoint(False))
                s.blit(img, (tx * T, ty * T))
            for (px, py) in room.free_checkpoints:
                img = texture_for(self.assets, room, "checkpoint:inactive",
                                  self.assets.checkpoint(False))
                s.blit(img, (px, py))
        if self._layer_visible("plus_jump"):
            for (tx, ty) in room.plus_jumps:
                img = texture_for(self.assets, room, "plus_jump",
                                  self.assets.plusjump())
                s.blit(img, (tx * T, ty * T))
            for (px, py) in room.free_plus_jumps:
                img = texture_for(self.assets, room, "plus_jump",
                                  self.assets.plusjump())
                s.blit(img, (px, py))
        if self._layer_visible("star"):
            for (tx, ty, level) in room.stars:
                img = texture_for(self.assets, room, f"star:{level}",
                                  self.assets.star(level))
                s.blit(img, (tx * T, ty * T))
            for (px, py, level) in room.free_stars:
                img = texture_for(self.assets, room, f"star:{level}",
                                  self.assets.star(level))
                s.blit(img, (px, py))
        if self._layer_visible("exit"):
            for e in room.exits:
                tx, ty = e["tile"]
                img = texture_for(self.assets, room, "door",
                                  self.assets.end())
                s.blit(img, (tx * T, ty * T))
                img = self.font_small.render(f"→{e['target']}", True,
                                             (0, 0, 0))
                s.blit(img, (tx * T + 2, ty * T + 2))
                if self.selected_exit == (tx, ty):
                    pygame.draw.rect(s, (255, 220, 60),
                                     (tx * T, ty * T, T, T), 3)
            for e in room.free_exits:
                px, py = e["pos"]
                img = texture_for(self.assets, room, "door",
                                  self.assets.end())
                s.blit(img, (px, py))
                img = self.font_small.render(f"→{e['target']}", True,
                                             (0, 0, 0))
                s.blit(img, (px + 2, py + 2))
                if self.selected_exit == (px, py):
                    pygame.draw.rect(s, (255, 220, 60),
                                     (px, py, T, T), 3)
        if self._layer_visible("end"):
            if room.end is not None:
                tx, ty = room.end
                img = texture_for(self.assets, room, "door",
                                  self.assets.end())
                s.blit(img, (tx * T, ty * T))
                img = self.font_small.render("END", True, (255, 255, 255))
                s.blit(img, (tx * T + 2, ty * T + 2))
            if room.free_end is not None:
                px, py = room.free_end
                img = texture_for(self.assets, room, "door",
                                  self.assets.end())
                s.blit(img, (px, py))
                img = self.font_small.render("END", True, (255, 255, 255))
                s.blit(img, (px + 2, py + 2))
        # 水（水层）
        if self._layer_visible("water"):
            for (tx, ty), wt in room.water.items():
                img = texture_for(self.assets, room, f"water:{wt}",
                                  self.assets.water(wt))
                s.blit(img, (tx * T, ty * T))
            for (px, py), wt in room.free_water.items():
                img = texture_for(self.assets, room, f"water:{wt}",
                                  self.assets.water(wt))
                s.blit(img, (px, py))
        # 出生点（物体层）
        if self._layer_visible("start"):
            sx, sy = room.start
            s.blit(self._thumb("start", None), (round(sx) - 2, round(sy) - 2))
            pygame.draw.rect(s, (80, 220, 120),
                             (round(sx) - 3, round(sy) - 3, 14, 14), 1)
        # 路径节点（仅编辑器可见）：节点标记 + 轨迹折线（吸附格子的点）
        PATH_COLOR = (255, 80, 220)
        for node in room.path_nodes:
            px, py = node["pos"]
            pts = [node["pos"]] + list(node["path"])
            if len(pts) >= 2:
                pygame.draw.lines(s, PATH_COLOR, False, pts, 2)
            for pt in node["path"]:
                pygame.draw.circle(s, PATH_COLOR, pt, 3)
            nrect = pygame.Rect(px, py, 32, 32)
            ov = pygame.Surface((32, 32), pygame.SRCALPHA)
            ov.fill((255, 80, 220, 40))
            s.blit(ov, nrect.topleft)
            selected = node is self.selected_path
            pygame.draw.rect(s, (255, 220, 60) if selected else PATH_COLOR,
                             nrect, 3 if selected else 2)
            pygame.draw.circle(s, PATH_COLOR, (px + 16, py + 16), 4)
            if selected:
                # 高亮所有会被挂载移动的元素（与游戏挂载判定一致）
                for r in self._node_overlap_rects(node):
                    pygame.draw.rect(s, (120, 255, 120), r, 2)
        # 网格线：粒度 >=8 画全部；更细时画 8px 辅助线；主 32 网格线始终加深
        gstep = self.grid if self.grid >= 8 else 8
        for x in range(0, config.ROOM_WIDTH + 1, gstep):
            pygame.draw.line(s, (0, 0, 0, 40), (x, 0), (x, config.ROOM_HEIGHT), 1)
        for y in range(0, config.ROOM_HEIGHT + 1, gstep):
            pygame.draw.line(s, (0, 0, 0, 40), (0, y), (config.ROOM_WIDTH, y), 1)
        for x in range(0, config.ROOM_WIDTH + 1, T):
            pygame.draw.line(s, (70, 70, 80), (x, 0), (x, config.ROOM_HEIGHT), 1)
        for y in range(0, config.ROOM_HEIGHT + 1, T):
            pygame.draw.line(s, (70, 70, 80), (0, y), (config.ROOM_WIDTH, y), 1)
        # hover 高亮（按实际放置位置）+ 幽灵（预览与实际 place() 一致）
        if self.hover is not None:
            hx, hy = self.hover
            rect = self._placement_rect(hx, hy)
            pygame.draw.rect(s, (255, 255, 255, 60), rect, 2)
            if self.tool[0] != "eraser" and not self._layer_blocked(
                    self.tool[0]):
                kind, sub = self.tool
                g = self._ghost_surface(kind, sub).copy()
                g.set_alpha(120)
                if kind == "small_tile":
                    gx, gy = (hx // 16) * 16, (hy // 16) * 16   # 16px 格
                elif kind == "mini_spike":
                    if self.grid >= T:
                        # 32 粒度：幽灵显示在"小刺象限"按钮选中的象限格
                        tx = (hx // T) * T
                        ty = (hy // T) * T
                        gx = tx + (T // 2 if self.mini_quad in (1, 3) else 0)
                        gy = ty + (T // 2 if self.mini_quad in (2, 3) else 0)
                    else:
                        gx = (hx // 16) * 16        # 细粒度：点击的 16px 单元
                        gy = (hy // 16) * 16
                elif kind == "platform":
                    gx, gy = hx, hy                 # 任意像素
                elif kind == "start":
                    if self.grid >= T:
                        gx = (hx // T) * T + (T - config.KID_WIDTH) // 2
                        gy = (hy // T) * T - config.KID_HEIGHT
                    else:
                        gx, gy = hx, hy
                else:
                    gx, gy = hx, hy   # 32×32 贴图：32 网格 = 32 对齐，细网格 = 像素放置
                s.blit(g, (gx, gy))
        # 整体平移到窗口中间
        self.screen.blit(s, (CANVAS_X, 0))

    def _ghost_surface(self, kind, sub):
        """返回工具对应的贴图（含房间自定义材质；供幽灵预览；不缩放）。"""
        room = self.room
        if kind == "tile":
            return texture_for(self.assets, room, f"tile:{sub}",
                               self.assets.tile(sub))
        if kind == "small_tile":
            return texture_for(self.assets, room, f"tile:{sub}",
                               self.assets.tile_small(sub))
        if kind == "spike":
            return texture_for(self.assets, room, f"spike:{sub}",
                               self.assets.spike(sub))
        if kind == "mini_spike":
            return texture_for(self.assets, room, f"mini_spike:{sub}",
                               self.assets.mini_spike(sub))
        if kind == "vine":
            return texture_for(self.assets, room, f"vine:{sub}",
                               self.assets.vine(sub))
        if kind == "water":
            return texture_for(self.assets, room, f"water:{sub}",
                               self.assets.water(sub))
        if kind == "platform":
            return texture_for(self.assets, room, "platform",
                               self.assets.platform())
        if kind == "checkpoint":
            return texture_for(self.assets, room, "checkpoint:inactive",
                               self.assets.checkpoint(False))
        if kind in ("exit", "end"):
            return texture_for(self.assets, room, "door", self.assets.end())
        if kind == "plus_jump":
            return texture_for(self.assets, room, "plus_jump",
                               self.assets.plusjump())
        if kind == "star":
            return texture_for(self.assets, room, f"star:{sub}",
                               self.assets.star(sub))
        if kind == "path_node":
            return self._thumb("path_node", None)
        return self._thumb(kind, sub)    # start 等自绘缩略图

    def _draw_left_panel(self):
        """左侧工具面板：小刺象限 + 工具列表（全高滚动）。"""
        s = self.screen
        pygame.draw.rect(s, BG_PANEL, (0, 0, LEFT_W, WIN_H))
        pygame.draw.line(s, BORDER, (LEFT_W, 0), (LEFT_W, WIN_H), 2)
        title = self.font_bold.render("工具", True, TEXT_BRIGHT)
        s.blit(title, (8, 6))
        q_active = self.grid >= T          # 象限按钮仅 32 网格生效（细网格自动定象限）
        lab = self.font_small.render("小刺象限" + ("" if q_active
                                                  else "·细网格自动"), True,
                                     TEXT_DIM)
        s.blit(lab, (8, QUAD_LABEL_Y))
        for i, (rect, label) in enumerate(self.quad_btns):
            bg = SEL_BG if q_active and i == self.mini_quad else BG_INPUT
            pygame.draw.rect(s, bg, rect, border_radius=3)
            pygame.draw.rect(s, ACCENT if q_active and i == self.mini_quad
                             else BORDER, rect, 1, border_radius=3)
            img = self.font_small.render(label, True,
                                         TEXT_BRIGHT if q_active else TEXT_DIM)
            s.blit(img, (rect.x + 6, rect.y + 2))

        # 网格粒度按钮
        lab = self.font_small.render("网格", True, TEXT_DIM)
        s.blit(lab, (8, GRID_LABEL_Y))
        for rect, g in self.grid_btns:
            selected = self.grid == g
            pygame.draw.rect(s, SEL_BG if selected else BG_INPUT, rect,
                             border_radius=3)
            pygame.draw.rect(s, ACCENT if selected else BORDER, rect, 1,
                             border_radius=3)
            img = self.font_small.render(str(g), True, TEXT_BRIGHT)
            s.blit(img, (rect.x + 7, rect.y + 3))

        # 图层：可见(V/眼) / 锁定(L) / 名称
        lab = self.font_small.render("图层（V=显示 L=锁定）", True, TEXT_DIM)
        s.blit(lab, (8, LAYER_LABEL_Y))
        for i, (name, label, _kinds) in enumerate(LAYERS):
            y = LAYER_ROW_Y + i * 20
            vis = pygame.Rect(6, y, 20, 16)
            lok = pygame.Rect(28, y, 20, 16)
            pygame.draw.rect(s, SEL_BG if self.layer_visible[name] else BG_INPUT,
                             vis, border_radius=3)
            pygame.draw.rect(s, BORDER, vis, 1, border_radius=3)
            vimg = self.font_small.render("V" if self.layer_visible[name]
                                          else "X", True, TEXT_BRIGHT)
            s.blit(vimg, (vis.x + 5, vis.y + 1))
            pygame.draw.rect(s, SEL_BG if self.layer_locked[name] else BG_INPUT,
                             lok, border_radius=3)
            pygame.draw.rect(s, BORDER, lok, 1, border_radius=3)
            limg = self.font_small.render("L" if self.layer_locked[name]
                                          else "·", True, TEXT_BRIGHT)
            s.blit(limg, (lok.x + 5, lok.y + 1))
            t = self.font_small.render(label, True, TEXT_BRIGHT)
            s.blit(t, (52, y + 1))

        # 工具列表（可滚动；起点与点击判定一致 = tool_list_top()）
        y = self.tool_list_top()
        x0, x1 = 4, LEFT_W - 4
        for item in self.tools:
            if "sep" in item:
                if L_TOOLS_TOP <= y <= L_TOOLS_BOTTOM:
                    img = self.font_small.render(f"— {item['sep']} —",
                                                 True, TEXT_DIM)
                    s.blit(img, (x0 + 4, y))
                y += 20
                continue
            rect = pygame.Rect(x0, y, x1 - x0, 24)
            if rect.bottom < L_TOOLS_TOP or rect.top > L_TOOLS_BOTTOM:
                y += 26
                continue
            selected = self.tool == (item["kind"], item["sub"])
            bg = SEL_BG if selected else (BG_INPUT if rect.collidepoint(
                self.mouse_pos) else None)
            if bg:
                pygame.draw.rect(s, bg, rect, border_radius=3)
            thumb = self._thumb(item["kind"], item["sub"])
            if thumb is not None:
                s.blit(thumb, (rect.x + 3, rect.y + (24 - thumb.get_height()) // 2))
            img = self.font_small.render(item["label"], True, TEXT_BRIGHT)
            s.blit(img, (rect.x + 26, rect.y + 4))
            y += 26

    def _draw_right_panel(self):
        """右侧设置面板：房间选择/房间名/出口目标/底部按钮。"""
        s = self.screen
        pygame.draw.rect(s, BG_PANEL, (RIGHT_X, 0, RIGHT_W, WIN_H))
        pygame.draw.line(s, BORDER, (RIGHT_X, 0), (RIGHT_X, WIN_H), 2)
        title = self.font_bold.render("关卡设置", True, TEXT_BRIGHT)
        s.blit(title, (RIGHT_X + 8, 6))
        hint = self.font_small.render("ESC退出  Ctrl+S保存", True, TEXT_DIM)
        s.blit(hint, (RIGHT_X + 8, 24))

        lab = self.font_small.render("选择房间", True, TEXT_DIM)
        s.blit(lab, (RIGHT_X + 8, DROP_BOX_Y - 14))
        self.room_dropdown.draw(s)

        lab = self.font_small.render("房间名(保存用)", True, TEXT_DIM)
        s.blit(lab, (RIGHT_X + 8, NAME_BOX_Y - 14))
        self.name_box.draw(s)

        lab = self.font_small.render("出口目标房间(文件名)", True, TEXT_DIM)
        s.blit(lab, (RIGHT_X + 8, TARGET_BOX_Y - 14))
        self.target_box.draw(s)

        # 背景音乐（房间自定义 BGM）
        lab = self.font_small.render("背景音乐(本房间)", True, TEXT_DIM)
        s.blit(lab, (RIGHT_X + 8, MUSIC_LABEL_Y))
        self.music_dropdown.draw(s)
        lab = self.font_small.render("默认音乐(没设bgm的房间)", True, TEXT_DIM)
        s.blit(lab, (RIGHT_X + 8, MUSIC_DEF_LABEL_Y))
        self.music_def_dropdown.draw(s)
        for rect, label, color in (
                (self.music_play_btn, "试听", (120, 200, 120)),
                (self.music_stop_btn, "停止", ERR_RED)):
            pygame.draw.rect(s, color if not rect.collidepoint(
                self.mouse_pos) else SEL_BG, rect, border_radius=3)
            pygame.draw.rect(s, BORDER, rect, 1, border_radius=3)
            img = self.font_small.render(label, True, TEXT_BRIGHT)
            s.blit(img, (rect.x + 10, rect.y + 3))
        tip = self.font_small.render("mp3/ogg/wav 放 music/ 后重启编辑器", True,
                                     TEXT_DIM)
        s.blit(tip, (RIGHT_X + 8, MUSIC_BTN_Y + 24))

        # 底部按钮
        for rect, label, color in (
                (self.save_btn, "保存", ACCENT),
                (self.load_btn, "加载", (140, 170, 220)),
                (self.project_btn, "存工程", (200, 180, 120)),
                (self.load_project_btn, "载工程", (200, 180, 120)),
                (self.exe_btn, "打包", (120, 220, 180)),
                (self.tex_btn, "材质", (170, 160, 230)),
                (self.bg_btn, "背景", (140, 200, 170)),
                (self.settings_btn, "设置", (150, 200, 230)),
                (self.clear_btn, "清空", ERR_RED),
                (self.exit_btn, "退出", TEXT_DIM)):
            pygame.draw.rect(s, color if not rect.collidepoint(
                self.mouse_pos) else SEL_BG, rect, border_radius=4)
            pygame.draw.rect(s, BORDER, rect, 1, border_radius=4)
            img = self.font_small.render(label, True, TEXT_BRIGHT)
            s.blit(img, (rect.x + 6, rect.y + 5))

        if self.message:
            img = self.font_small.render(self.message, True, self.message_color)
            s.blit(img, (RIGHT_X + 8, WIN_H - 30))
        # 下拉框展开浮层最后画（覆盖其他控件）
        self.room_dropdown.draw_open(s)
        self.music_dropdown.draw_open(s)
        self.music_def_dropdown.draw_open(s)

    # ---------------- 材质设置面板绘制（右面板） ----------------
    def _draw_tex_panel(self):
        s = self.screen
        pygame.draw.rect(s, BG_PANEL, (RIGHT_X, 0, RIGHT_W, WIN_H))
        pygame.draw.line(s, BORDER, (RIGHT_X, 0), (RIGHT_X, WIN_H), 2)
        title = self.font_bold.render("材质设置", True, TEXT_BRIGHT)
        s.blit(title, (RIGHT_X + 8, 6))
        hint = self.font_small.render("替换 object 贴图  Ctrl+S保存", True,
                                      TEXT_DIM)
        s.blit(hint, (RIGHT_X + 8, 24))

        lab = self.font_small.render("替换对象", True, TEXT_DIM)
        s.blit(lab, (RIGHT_X + 8, TEX_SLOT_LABEL_Y))
        self.tex_slot_dropdown.draw(s)

        lab = self.font_small.render("子类型 (（全部）= 统一材质)", True,
                                     TEXT_DIM)
        s.blit(lab, (RIGHT_X + 8, TEX_SUB_LABEL_Y))
        self.tex_sub_dropdown.draw(s)

        lab = self.font_small.render("材质图片 (assets/textures/)", True,
                                     TEXT_DIM)
        s.blit(lab, (RIGHT_X + 8, TEX_IMG_LABEL_Y))
        self.tex_img_dropdown.draw(s)

        # 预览：当前贴图键的默认贴图（或已应用的材质）
        pv = (RIGHT_X + 8, TEX_PREVIEW_Y, RIGHT_W - 16, 130)
        pygame.draw.rect(s, BG_INPUT, pv, border_radius=4)
        pygame.draw.rect(s, BORDER, pv, 1, border_radius=4)
        img = self._tex_preview_surface(self._current_tex_key())
        if img is not None:
            iw, ih = img.get_size()
            r = min(140 / iw, 140 / ih)
            pv_img = pygame.transform.smoothscale(
                img, (max(1, int(iw * r)), max(1, int(ih * r))))
            s.blit(pv_img, (pv[0] + (pv[2] - pv_img.get_width()) // 2,
                            pv[1] + (pv[3] - pv_img.get_height()) // 2))
        key = self._current_tex_key()
        name = self.room.textures.get(key)
        from_coarse = False
        if name is None and ":" in key:
            coarse = self.room.textures.get(key.split(":", 1)[0])
            if coarse:
                name = coarse
                from_coarse = True
        suffix = "（来自「全部」统一）" if from_coarse else ""
        t = self.font_small.render("当前：" + (name or "默认材质") + suffix,
                                   True, TEXT_BRIGHT)
        s.blit(t, (pv[0] + 4, pv[1] + pv[3] - 18))
        tip = self.font_small.render("选中图片立即生效（自动缩放到物体尺寸）",
                                     True, TEXT_DIM)
        s.blit(tip, (RIGHT_X + 8, TEX_PREVIEW_Y + pv[3] + 6))

        for rect, label, color in (
                (self.tex_clear_btn, "恢复默认", ERR_RED),
                (self.tex_back_btn, "← 返回工具", ACCENT)):
            hover = rect.collidepoint(self.mouse_pos)
            pygame.draw.rect(s, SEL_BG if hover else color, rect,
                             border_radius=4)
            pygame.draw.rect(s, BORDER, rect, 1, border_radius=4)
            img = self.font_small.render(label, True, TEXT_BRIGHT)
            s.blit(img, (rect.x + 6, rect.y + 5))

        if self.message:
            img = self.font_small.render(self.message, True, self.message_color)
            s.blit(img, (RIGHT_X + 8, WIN_H - 30))
        self.tex_slot_dropdown.draw_open(s)
        self.tex_sub_dropdown.draw_open(s)
        self.tex_img_dropdown.draw_open(s)

    # ---------------- 路径节点面板绘制（右面板） ----------------
    def _draw_path_panel(self):
        s = self.screen
        pygame.draw.rect(s, BG_PANEL, (RIGHT_X, 0, RIGHT_W, WIN_H))
        pygame.draw.line(s, BORDER, (RIGHT_X, 0), (RIGHT_X, WIN_H), 2)
        title = self.font_bold.render("路径节点", True, TEXT_BRIGHT)
        s.blit(title, (RIGHT_X + 8, 6))
        node = self.selected_path
        if node is None:
            t = self.font_small.render("未选中节点", True, TEXT_DIM)
            s.blit(t, (RIGHT_X + 8, 40))
            return
        pos = node["pos"]
        n_attached = len(self._node_overlap_rects(node))
        info = self.font_small.render(
            f"节点 ({pos[0]},{pos[1]})  轨迹点 {len(node['path'])} 个"
            f"  挂载 {n_attached} 个元素", True,
            ERR_RED if n_attached == 0 else TEXT_BRIGHT)
        s.blit(info, (RIGHT_X + 8, 30))
        if n_attached == 0:
            w = self.font_small.render("⚠ 没挂到任何元素（绿框=重合元素）",
                                       True, ERR_RED)
            s.blit(w, (RIGHT_X + 8, 46))
        else:
            hint = self.font_small.render("按住左键拖动画轨迹（吸附网格）",
                                          True, TEXT_DIM)
            s.blit(hint, (RIGHT_X + 8, 46))

        # 速度
        lab = self.font_small.render("速度（像素/帧）", True, TEXT_DIM)
        s.blit(lab, (RIGHT_X + 8, PATH_SPEED_LABEL_Y))
        for rect, label, color in (
                (self.path_speed_dec_btn, "-", ACCENT),
                (self.path_speed_inc_btn, "+", ACCENT)):
            pygame.draw.rect(s, color if not rect.collidepoint(
                self.mouse_pos) else SEL_BG, rect, border_radius=3)
            pygame.draw.rect(s, BORDER, rect, 1, border_radius=3)
            img = self.font_bold.render(label, True, TEXT_BRIGHT)
            s.blit(img, (rect.x + 9, rect.y + 2))
        v = self.font.render(f"{node['speed']:.2f}", True, TEXT_BRIGHT)
        s.blit(v, (RIGHT_X + 44, PATH_SPEED_Y + 3))

        # 触发方式
        lab = self.font_small.render("触发方式", True, TEXT_DIM)
        s.blit(lab, (RIGHT_X + 8, PATH_TRIGGER_LABEL_Y))
        for rect, label, mode in (
                (self.path_auto_btn, "自动", "auto"),
                (self.path_touch_btn, "触碰", "touch")):
            selected = node["trigger"] == mode
            pygame.draw.rect(s, SEL_BG if selected else BG_INPUT, rect,
                             border_radius=3)
            pygame.draw.rect(s, ACCENT if selected else BORDER, rect, 1,
                             border_radius=3)
            img = self.font_small.render(label, True, TEXT_BRIGHT)
            s.blit(img, (rect.x + 12, rect.y + 3))
        tip = self.font_small.render(
            "触碰 = 玩家碰到节点才开动", True, TEXT_DIM)
        s.blit(tip, (RIGHT_X + 8, PATH_TRIGGER_Y + 24))

        # 按钮
        for rect, label, color in (
                (self.path_clear_btn, "清除轨迹", (170, 140, 220)),
                (self.path_delete_btn, "删除节点", ERR_RED)):
            hover = rect.collidepoint(self.mouse_pos)
            pygame.draw.rect(s, SEL_BG if hover else color, rect,
                             border_radius=4)
            pygame.draw.rect(s, BORDER, rect, 1, border_radius=4)
            img = self.font_small.render(label, True, TEXT_BRIGHT)
            s.blit(img, (rect.x + 10, rect.y + 5))
        hover = self.path_done_btn.collidepoint(self.mouse_pos)
        pygame.draw.rect(s, SEL_BG if hover else ACCENT, self.path_done_btn,
                         border_radius=4)
        pygame.draw.rect(s, BORDER, self.path_done_btn, 1, border_radius=4)
        img = self.font.render("完成绘制 ✓", True, TEXT_BRIGHT)
        s.blit(img, (self.path_done_btn.x + 10, self.path_done_btn.y + 5))

        if self.message:
            img = self.font_small.render(self.message, True, self.message_color)
            s.blit(img, (RIGHT_X + 8, WIN_H - 30))

    # ---------------- 项目设置面板绘制（右面板） ----------------
    def _draw_settings_panel(self):
        s = self.screen
        pygame.draw.rect(s, BG_PANEL, (RIGHT_X, 0, RIGHT_W, WIN_H))
        pygame.draw.line(s, BORDER, (RIGHT_X, 0), (RIGHT_X, WIN_H), 2)
        title = self.font_bold.render("项目设置", True, TEXT_BRIGHT)
        s.blit(title, (RIGHT_X + 8, 6))
        hint = self.font_small.render("游戏标题 / 程序图标", True, TEXT_DIM)
        s.blit(hint, (RIGHT_X + 8, 24))

        lab = self.font_small.render("游戏标题（窗口标题/打包 exe 名）", True,
                                     TEXT_DIM)
        s.blit(lab, (RIGHT_X + 8, SET_TITLE_LABEL_Y))
        self.title_box.draw(s)

        lab = self.font_small.render("程序图标（assets/ 下）", True, TEXT_DIM)
        s.blit(lab, (RIGHT_X + 8, SET_ICON_LABEL_Y))
        self.icon_dropdown.draw(s)
        tip = self.font_small.render(
            "图标 .ico 或 png 均可（窗口+任务栏+exe 都会用；选完点应用设置）",
            True, TEXT_DIM)
        s.blit(tip, (RIGHT_X + 8, SET_ICON_BOX_Y + 24))

        for rect, label, color in (
                (self.settings_apply_btn, "应用设置", ACCENT),
                (self.settings_back_btn, "← 返回工具", TEXT_DIM)):
            hover = rect.collidepoint(self.mouse_pos)
            pygame.draw.rect(s, SEL_BG if hover else color, rect,
                             border_radius=4)
            pygame.draw.rect(s, BORDER, rect, 1, border_radius=4)
            img = self.font_small.render(label, True, TEXT_BRIGHT)
            s.blit(img, (rect.x + 6, rect.y + 5))

        if self.message:
            img = self.font_small.render(self.message, True, self.message_color)
            s.blit(img, (RIGHT_X + 8, WIN_H - 30))
        self.icon_dropdown.draw_open(s)

    # ---------------- 背景设置面板绘制（右面板） ----------------
    def _draw_bg_panel(self):
        s = self.screen
        pygame.draw.rect(s, BG_PANEL, (RIGHT_X, 0, RIGHT_W, WIN_H))
        pygame.draw.line(s, BORDER, (RIGHT_X, 0), (RIGHT_X, WIN_H), 2)
        title = self.font_bold.render("背景设置", True, TEXT_BRIGHT)
        s.blit(title, (RIGHT_X + 8, 6))
        hint = self.font_small.render("Ctrl+S保存  ESC退出", True, TEXT_DIM)
        s.blit(hint, (RIGHT_X + 8, 24))

        # 背景颜色
        lab = self.font_small.render("背景颜色 RGB (0-255)", True, TEXT_DIM)
        s.blit(lab, (RIGHT_X + 8, BG_COLOR_LABEL_Y))
        for box in (self.bg_r_box, self.bg_g_box, self.bg_b_box):
            box.draw(s)
        pygame.draw.rect(s, self.room.bg_color, self.bg_color_swatch,
                         border_radius=3)
        pygame.draw.rect(s, BORDER, self.bg_color_swatch, 1, border_radius=3)
        hover = self.bg_apply_color_btn.collidepoint(self.mouse_pos)
        pygame.draw.rect(s, SEL_BG if hover else ACCENT,
                         self.bg_apply_color_btn, border_radius=4)
        img = self.font_small.render("应用颜色", True, TEXT_BRIGHT)
        s.blit(img, (self.bg_apply_color_btn.x + 8,
                     self.bg_apply_color_btn.y + 5))
        # 预设色板
        for rect, color in zip(self.bg_palette_rects, self.bg_palette):
            pygame.draw.rect(s, color, rect, border_radius=3)
            pygame.draw.rect(s, BORDER, rect, 1, border_radius=3)
        tip = self.font_small.render("点击色板直接换色", True, TEXT_DIM)
        s.blit(tip, (RIGHT_X + 8, BG_PALETTE_Y + 30))

        # 背景图片
        lab = self.font_small.render("背景图片 (assets/backgrounds/)", True,
                                     TEXT_DIM)
        s.blit(lab, (RIGHT_X + 8, BG_IMG_LABEL_Y))
        self.bg_image_box.draw(s)
        self.bg_img_dropdown.draw(s)

        # 填充模式按钮（2 行 3 列）
        lab = self.font_small.render("填充模式", True, TEXT_DIM)
        s.blit(lab, (RIGHT_X + 8, BG_MODE_LABEL_Y))
        for i, (rect, label) in enumerate(self.bg_mode_btns):
            mode = self.bg_modes[i][0]
            selected = self.room.bg_mode == mode
            bg = SEL_BG if selected else (BG_INPUT if rect.collidepoint(
                self.mouse_pos) else BG_INPUT)
            pygame.draw.rect(s, SEL_BG if selected else BG_INPUT, rect,
                             border_radius=3)
            pygame.draw.rect(s, ACCENT if selected else BORDER, rect, 1,
                             border_radius=3)
            img = self.font_small.render(label, True, TEXT_BRIGHT)
            s.blit(img, (rect.x + 10, rect.y + 3))

        # 缩放 / 偏移（缩放模式）
        lab = self.font_small.render("缩放 / 偏移 (缩放模式)", True, TEXT_DIM)
        s.blit(lab, (RIGHT_X + 8, BG_ZOOM_LABEL_Y))
        for rect, label, color in (
                (self.zoom_dec_btn, "-", ACCENT),
                (self.zoom_inc_btn, "+", ACCENT),
                (self.offx_dec_btn, "-", ACCENT),
                (self.offx_inc_btn, "+", ACCENT),
                (self.offy_dec_btn, "-", ACCENT),
                (self.offy_inc_btn, "+", ACCENT)):
            pygame.draw.rect(s, color if not rect.collidepoint(
                self.mouse_pos) else SEL_BG, rect, border_radius=4)
            pygame.draw.rect(s, BORDER, rect, 1, border_radius=4)
            img = self.font_bold.render(label, True, TEXT_BRIGHT)
            s.blit(img, (rect.x + 9, rect.y + 2))
        zval = self.font.render(f"缩放 x{self.room.bg_zoom:.2f}", True,
                                TEXT_BRIGHT)
        s.blit(zval, (RIGHT_X + 44, BG_ZOOM_Y + 3))
        xval = self.font.render(f"偏移X {self.room.bg_offset[0]:+d}", True,
                                TEXT_BRIGHT)
        s.blit(xval, (RIGHT_X + 44, BG_OFFX_Y + 3))
        yval = self.font.render(f"偏移Y {self.room.bg_offset[1]:+d}", True,
                                TEXT_BRIGHT)
        s.blit(yval, (RIGHT_X + 44, BG_OFFY_Y + 3))

        # 预览：完整图 + 视口选择框（缩放模式可拖动框移动/缩放）
        pv = (RIGHT_X + 8, BG_PREVIEW_Y, 200, 120)
        img = self.assets.background(self.room.bg_image) if self.room.bg_image \
            else None
        self._bg_box = None
        if img is not None:
            iw, ih = img.get_size()
            k = min(pv[2] / iw, pv[3] / ih)          # 整图 fit 预览比例
            self._bg_k = k
            dw, dh = int(iw * k), int(ih * k)
            dx0 = pv[0] + (pv[2] - dw) // 2
            dy0 = pv[1] + (pv[3] - dh) // 2
            s.blit(pygame.transform.smoothscale(img, (dw, dh)), (dx0, dy0))
            if self.room.bg_mode == "zoom":
                # 视口框：视口(800×608)在整图上的位置（受 zoom/offset 影响）
                zoom = max(0.25, self.room.bg_zoom or 1.0)
                vw = config.ROOM_WIDTH / zoom
                vh = config.ROOM_HEIGHT / zoom
                cx = iw / 2 + (self.room.bg_offset[0] / zoom)
                cy = ih / 2 + (self.room.bg_offset[1] / zoom)
                bx = dx0 + (cx - vw / 2) * k
                by = dy0 + (cy - vh / 2) * k
                bw, bh = max(4, vw * k), max(4, vh * k)
                self._bg_box = pygame.Rect(int(bx), int(by), int(bw), int(bh))
                pygame.draw.rect(s, (255, 220, 60), self._bg_box, 2)
                ov = pygame.Surface(self._bg_box.size, pygame.SRCALPHA)
                ov.fill((255, 220, 60, 36))
                s.blit(ov, self._bg_box.topleft)
                tip = self.font_small.render("拖框内移动 · 拖边缩放", True,
                                             (255, 220, 60))
                s.blit(tip, (pv[0], pv[1] + pv[3] + 3))
        else:
            pygame.draw.rect(s, BG_INPUT, pv, border_radius=4)
            pygame.draw.rect(s, BORDER, pv, 1, border_radius=4)
            t = self.font_small.render("无背景图", True, TEXT_DIM)
            s.blit(t, (pv[0] + 20, pv[1] + 45))
        # 应用/清除图片 + 返回
        for rect, label, color in (
                (self.bg_apply_img_btn, "应用图片", ACCENT),
                (self.bg_clear_img_btn, "清除图片", ERR_RED)):
            hover = rect.collidepoint(self.mouse_pos)
            pygame.draw.rect(s, SEL_BG if hover else color, rect,
                             border_radius=4)
            pygame.draw.rect(s, BORDER, rect, 1, border_radius=4)
            img = self.font_small.render(label, True, TEXT_BRIGHT)
            s.blit(img, (rect.x + 6, rect.y + 5))
        hover = self.bg_back_btn.collidepoint(self.mouse_pos)
        pygame.draw.rect(s, SEL_BG if hover else BG_INPUT, self.bg_back_btn,
                         border_radius=4)
        pygame.draw.rect(s, BORDER, self.bg_back_btn, 1, border_radius=4)
        img = self.font_small.render("← 返回工具", True, TEXT_BRIGHT)
        s.blit(img, (self.bg_back_btn.x + 8, self.bg_back_btn.y + 6))

        if self.message:
            img = self.font_small.render(self.message, True, self.message_color)
            s.blit(img, (RIGHT_X + 8, WIN_H - 30))
        self.bg_img_dropdown.draw_open(s)

    # ---------------- 主循环 ----------------
    def run(self):
        while self.running:
            for event in pygame.event.get():
                self.handle_event(event)
            self.update()
            self.draw()
            self.clock.tick(config.FPS)
        pygame.display.quit()
        if self._test_pending:
            self._launch_test()      # 按 Enter：保存后进入游戏测试
        pygame.quit()

    # ---------------- 游戏测试（Enter 自动保存并进游戏） ----------------
    def _test_game(self):
        """自动保存当前房间，然后关闭编辑器、启动游戏测试（从当前房间开始）。"""
        self.save()
        if self.message_color == ERR_RED:
            return                    # 保存失败（房间名非法等），不测试
        self._test_pending = True
        self.running = False

    def _launch_test(self):
        """关闭编辑器后启动游戏，加载当前编辑的房间。"""
        from core.app import App
        from levels.rooms_registry import load_room, clear_cache
        clear_cache()
        app = App()
        name = self.name_box.text.strip()
        room = load_room(name) if name else None
        if room is not None:
            app.scene.reload_room(room, preserve_spawn=False)
        app.run()


if __name__ == "__main__":
    # 支持直接运行：python editor/editor.py（等价于 python main.py --editor）
    Editor().run()
