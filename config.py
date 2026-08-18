"""
config.py — I Wanna 引擎 集中参数管理

约定：
    * 物理时间单位：frame（帧）。游戏固定 50 FPS，每帧调用一次 update()。
    * 不使用 delta time 物理。
    * 空间单位：pixel（像素）。
    * 速度单位：px/frame（每帧移动的像素数）。
"""

import pygame

# ============================================================
# 系统
# ============================================================
FPS = 50
TITLE = "I Wanna (Python)"
WINDOW_WIDTH = 800
WINDOW_HEIGHT = 608

# ============================================================
# Room（固定尺寸，一个 Room 一个屏幕）
# ============================================================
ROOM_WIDTH = 800
ROOM_HEIGHT = 608
TILE_SIZE = 32
GRID_COLS = ROOM_WIDTH // TILE_SIZE    # 25
GRID_ROWS = ROOM_HEIGHT // TILE_SIZE   # 19

# ============================================================
# 目录（基于项目根，从任意工作目录运行都正确）
# ============================================================
import os
import sys

if getattr(sys, "frozen", False):
    # 打包成单文件 exe 后分两个根：
    #   BASE_DIR = **exe 所在目录**（可写）：存档 save/ 写这里，重开游戏仍在，
    #              不会写进 PyInstaller 临时解包目录（_MEIxxxx，关掉就没了）。
    #   DATA_DIR = PyInstaller 临时解包目录（_MEIPASS）：内置只读数据
    #              （assets/sound/music/rooms，用 --add-data 打进 exe）。
    BASE_DIR = os.path.dirname(os.path.abspath(sys.executable))
    DATA_DIR = getattr(sys, "_MEIPASS", BASE_DIR)
else:
    _here = os.path.dirname(os.path.abspath(__file__))
    BASE_DIR = DATA_DIR = _here

PROJECT_ROOT = BASE_DIR            # 可写根（编辑器/打包工具用；打包版里 = exe 目录）
ASSET_DIR = os.path.join(DATA_DIR, "assets")   # 只读素材（打包版从 exe 内置读）
ROOMS_DIR = os.path.join(DATA_DIR, "rooms")    # 只读关卡（打包版从 exe 内置读）

# ============================================================
# 存档（Checkpoint 跨游戏会话持久化到磁盘）
# ============================================================
SAVE_DIR = os.path.join(PROJECT_ROOT, "save")
SAVE_FILE = "save.json"
SAVE_COOLDOWN_FRAMES = 150     # 存档冷却（3 秒 @50fps）：CD 内重复存档无效，
                               # CD 过后可再次存（同一 checkpoint 也能重复存）

# ============================================================
# 背景（纯色天蓝，编辑器内可调）
# ============================================================
BG_COLOR = (135, 206, 235)   # sky blue

# ============================================================
# Tile 类型（block，素材命名 tiles/block_{i}.png）
# ============================================================
TILE_TYPES = [f"block_{i}" for i in range(9)]

# ============================================================
# Kid 移动物理（px/frame）
# ============================================================
PLAYER_SPEED = 3.0             # 水平速度：立即响应，无惯性
GRAVITY = 0.4                  # 每帧 vsp += GRAVITY（Y 轴向下为正）
MAX_FALL_SPEED = 10.0          # 最大下落速度（可调）
JUMP_SPEED = -8.5              # 一段跳初速度（向上为负）
DOUBLE_JUMP_SPEED = -7.0       # 二段跳初速度（第三段及以上复用此值）
DOUBLE_JUMP_ENABLED = True     # 空中跳总开关
JUMP_CUT_MULTIPLIER = 0.45     # 松开跳跃且上升时：vsp *= 0.45（长短跳）

# ============================================================
# 跳跃星星（Jump Star）——碰到后改变"最多跳跃次数"
# ============================================================
# 星星不可消耗（不消失），碰到任意次都有效；玩家默认二段跳（max_jumps=2），
# 死亡/重生后 max_jumps 重置为默认 2（星星本体仍在原地，重新碰一次再生效）。
# 贴图映射：一段(黑)=star_0.png，二段(灰)=star_2.png，三段(黄)=star_3.png。
#   star_1.png 缺失不用；以后补图只需改 STAR_IMAGES 映射。
STAR_LEVELS = (1, 2, 3)                                  # 支持的最大跳跃次数（段数）
STAR_IMAGES = {1: "star_0.png", 2: "star_2.png", 3: "star_3.png"}
STAR_FX_FRAMES = 50          # 触碰特效总帧数（星星放大淡出）
STAR_FX_SCALE_END = 2.2      # 结束时放大倍数（慢慢放大）
STAR_FX_ALPHA_START = 220    # 开始时透明度（慢慢消失到 0）

# ============================================================
# 跳跃球（Plus Jump）——碰撞半径（判定 = Kid半径 + 球半径）
# ============================================================
# 球中心在格子中心；半径 8（直径 16）比整格（32）小一半，
# 需要 Kid 更贴近才触发（原为 14，几乎占满整格）。
PLUS_JUMP_RADIUS = 8

# ============================================================
# Kid 碰撞箱（≠ 图片尺寸）
# ============================================================
KID_WIDTH = 11
KID_HEIGHT = 21

# ============================================================
# Align 系统
# ============================================================
# Align = kid.x % ALIGN_MODULO
ALIGN_MODULO = 3

# ============================================================
# 尖刺（像素级精确碰撞：由图片 alpha 生成 mask）
# ============================================================
# 碰撞遮罩直接用 pygame.mask.from_surface(spike_{dir}.png) 的 alpha 通道逐像素生成，
# 与可见像素完全一致，不再手写近似形状；换素材图碰撞区自动同步。
# threshold：alpha >= 该值的像素视为实体（默认 127，排除抗锯齿淡边）。
SPIKE_MASK_THRESHOLD = 127

# ============================================================
# Kid 动画（素材：characters/kid/{anim}_{帧}.png，帧号从 0 开始）
# ============================================================
KID_ANIM_FRAMES = {
    "idle": 4,
    "run": 5,
    "jump": 2,
    "fall": 2,
    "on": 2,          # 攀附藤蔓（on_0/1.png 两帧循环）
    # 无 death 动画：死亡演出 = 红色粒子 + 头(head.png)掉落反弹
}
KID_ANIM_INTERVALS = {   # 每 N 帧切换一帧
    "idle": 6,
    "run": 3,
    "jump": 6,
    "fall": 6,
    "on": 6,
}

# ============================================================
# Checkpoint（素材：checkpoint_0.png 未存档 / checkpoint_1.png 存档后）
# ============================================================
CHECKPOINT_IMAGE_INACTIVE = "checkpoint_0.png"
CHECKPOINT_IMAGE_ACTIVE = "checkpoint_1.png"

# ============================================================
# 射击（Z 键发射子弹；子弹碰到 Checkpoint 也能存档）
# ============================================================
BULLET_SPEED = 10.0           # 子弹速度 px/frame
BULLET_FRAMES = 2             # 动画帧数（bullet_0/1.png）
BULLET_FRAME_INTERVAL = 4     # 每 N 帧切换一帧
BULLET_MAX = 8                # 屏幕内子弹数量上限
BULLET_MASK_THRESHOLD = 127   # 子弹碰撞遮罩：由 bullet_*.png 的 alpha 逐像素生成（像素级精确）
BULLET_CHECKPOINT_INFLATE = 0  # 子弹触发 Checkpoint 时触发区垂直扩展（子弹高度平飞也能碰到地板存档）

# ============================================================
# 水（Water）——三种类型统一减速下落
# ============================================================
# 一段/二段/零段水都会把最大下落速度压到 WATER_FALL_SPEED（文档约定统一 2.4）。
# 零段水额外禁止跳跃（但保留跳跃次数）；二段水进入时重置跳跃次数。
WATER_FALL_SPEED = 2.4    # 水中最大下落速度 px/frame

# ============================================================
# 单向平台（Platform）——32×16 像素
# ============================================================
# 平台是一种可以站立的单向平台：
#   - 玩家可以站在板子上
#   - 从下方穿过板子
#   - 只有从上方接触时才产生站立碰撞
#   - 玩家下落时检测平台顶部
#   - 玩家向上跳跃时不会被平台阻挡
PLATFORM_WIDTH = 32               # 平台宽度（像素）
PLATFORM_HEIGHT = 16              # 平台高度（像素）
PLATFORM_TOLERANCE = 4            # 站立判定的垂直容差（像素）
PLATFORM_PENETRATION_TOLERANCE = 2  # 允许玩家轻微穿透平台的深度（像素）

# ============================================================
# 藤蔓（Vine）——非梯子，从侧面进入攀附
# ============================================================
# 藤蔓不是梯子：不能按上下键攀爬，只能从藤蔓的正侧面碰撞进入攀附。
#   攀爬面在右侧（tengwan_right.png）→ Kid 从右向左进入，吸附在右侧；
#   攀爬面在左侧（tengwan_left.png） → Kid 从左向右进入，吸附在左侧。
# 有效碰撞箱 = 攀爬面那一侧的边缘竖线（right→右缘，left→左缘）。
# 攀附中（tengwan_right 为例，tengwan_left 左右互换）：
#   上方向键          = 无反应（保持不动；shift+上 不会让它向上）
#   下方向键          = 自然下滑（不冻结）
#   Shift + 靠近方向  = 不再上爬，自然下滑（shift+方向 不会让它向上）
#   Shift + 反方向    = 跳出藤蔓（向右上方出藤蔓）
#   按住反方向        = 普通脱离（向右）
#   按住靠近方向      = 保持在藤蔓上，仍缓慢下滑
#   无输入            = 沿藤蔓缓慢下滑
# 藤蔓上垂直移动对固体做碰撞（下滑/跳出不会穿墙）。
# 藤蔓不会刷新跳跃次数（攀附/脱离不重置 jump_count）。
# 上攀靠"跳出再跳回"循环：shift+反方向跳出藤蔓（带向上初速度），空中再跳回藤蔓。
VINE_SLIDE_SPEED = 1.0    # 无输入时沿藤蔓缓慢下滑 px/frame
VINE_LEAP_HSP = 4.0       # Shift+反方向 跳出藤蔓：水平推开速度
VINE_LEAP_VSP = -7.5      # Shift+反方向 跳出藤蔓：向上初速度（向右上方出藤蔓）
VINE_DETACH_HSP = 3.0     # 普通脱离：水平推开速度（向右/左普通脱离）

# ============================================================
# 死亡演出
# ============================================================
DEATH_FRAMES = 75               # 死亡演出总帧数，之后重生
DEATH_PARTICLE_COUNT = 40       # 红色粒子数量
DEATH_PARTICLE_GRAVITY = 0.35
DEATH_PARTICLE_COLORS = [(255, 60, 60), (255, 120, 60), (200, 30, 30), (160, 20, 20)]
DEATH_HEAD_HSP = 8.0            # 头弹出水平初速度（更猛）
DEATH_HEAD_VSP = -13.0          # 向上初速度
DEATH_HEAD_BOUNCE = 0.78        # 头落地反弹系数（保留更多能量，弹得更狠）
DEATH_HEAD_WALL = 0.92          # 头撞墙反弹系数
DEATH_HEAD_SPIN = 12.0          # 旋转速度系数（angle += hsp * SPIN）
DEATH_HEAD_HUE_SPEED = 16       # 每帧色相旋转度数（超级变色，360 度约 22 帧转一圈）
DEATH_HEAD_STRETCH_MIN = 0.35   # 随机拉伸最小倍率（更扁）
DEATH_HEAD_STRETCH_MAX = 2.6    # 随机拉伸最大倍率（更拉长）
DEATH_HEAD_STRETCH_EVERY = 5    # 每 N 帧重新随机一个拉伸目标（更频繁）
DEATH_HEAD_STRETCH_SMOOTH = 0.5 # 拉伸朝目标逼近系数（0~1，越大越生硬/夸张）
DEATH_HEAD_HOP_EVERY = 18       # 头落地静止后每 N 帧随机再跳一次（持续演出直到按 R）
DEATH_TRAIL_LENGTH = 16         # 头彩虹拖尾的残影数量
DEATH_TRAIL_HUE_STEP = 24       # 相邻残影色相差（度）：15×24=360，整条拖尾是一条完整彩虹
DEATH_TRAIL_HUE_FLOW = 8        # 每帧整个色相平移度数（彩虹沿拖尾流动）
DEATH_TRAIL_MIN_SCALE = 0.25    # 最旧残影的缩放（头→尾逐渐缩小）
DEATH_TRAIL_ALPHA = 0.85        # 最亮残影不透明度（随年龄线性衰减）
DEATH_HEAD_HOP_VSP_MIN = 4.0    # 再跳的向上速度范围（更猛）
DEATH_HEAD_HOP_VSP_MAX = 11.0
DEATH_HEAD_HOP_HSP = 5.0        # 再跳的水平速度上限
DEATH_OVERLAY_ALPHA = 235       # 提示图最大透明度
DEATH_VEIL_ALPHA = 150          # 四周变黑最大透明度
DEATH_FADE_STEP = 8             # 每帧渐显速度
DEATH_VEIL_STEP = 5

# ============================================================
# 通关演出（win.gif）
# ============================================================
WIN_FRAMES = 120
WIN_OVERLAY_ALPHA = 255
WIN_VEIL_ALPHA = 180
WIN_FADE_STEP = 6
WIN_VEIL_STEP = 4

# ============================================================
# 调试查看（F1 碰撞箱 / F2 隐藏参数+碰撞箱，或右上角按钮开关）
# ============================================================
DEBUG_HITBOX_KEYS = (pygame.K_F1, pygame.K_h, pygame.K_TAB)
# F2：开关独立小窗口「隐藏参数面板」（默认隐藏；碰撞箱只用 F1）
DEBUG_PARAMS_KEYS = (pygame.K_F2,)
HITBOX_COLORS = {
    "kid":        (255, 60, 60),    # Kid 碰撞箱（红）
    "solid":      (40, 220, 60),    # 固体 Tile 合并矩形（绿）
    "platform":   (100, 140, 180),  # 单向平台碰撞区（蓝）
    "spike":      (255, 140, 0),    # 尖刺碰撞区（橙，与视觉分离）
    "checkpoint": (255, 230, 0),    # Checkpoint 触发区（黄）
    "vine":       (120, 255, 120),  # 藤蔓攀爬面（绿，竖线）
    "exit":       (0, 220, 255),    # 出口触发区（青）
    "end":        (255, 0, 255),    # 终点触发区（品红）
    "bullet":     (255, 255, 0),    # 子弹碰撞遮罩（黄，精确到像素）
    "plus_jump":  (255, 192, 203),  # 跳跃球碰撞箱（粉）
    "star":       (255, 215, 0),    # 跳跃星星碰撞区（黄）
}

# ============================================================
# 音效（sound/ 目录，WAV 由 pygame.mixer 播放）
# ============================================================
SOUND_DIR = os.path.join(DATA_DIR, "sound")   # 打包版从 exe 内置读
SOUND_ENABLED = True            # 总开关（无声卡/无头环境下自动静音）
SOUND_FILES = {
    "jump":     "sndDJump.wav",  # 一段跳 / 二段跳
    "death":    "sndDeath.wav",  # 死亡
    "save":     "snditem.wav",   # 存档（按 S / 子弹碰到 Checkpoint）
    "shoot":    "sndShoot.wav",  # 射击（Z）
    "vine_leap": "sndwallum.wav", # 藤蔓跳出（Shift + 反方向）
    "star":     "sndBlockChange.wav",  # 碰到跳跃星星
    "collect":  "snditem.wav",    # 捡到跳跃球（返还一次跳跃）
    "ui_click": "sndCherry.wav",  # 编辑器按钮点击音效
}

# ============================================================
# 背景音乐（music/ 目录，pygame.mixer.music 播放，支持 mp3/ogg/wav）
# ============================================================
MUSIC_DIR = os.path.join(DATA_DIR, "music")   # 打包版从 exe 内置读
MUSIC_FADE_OUT_MS = 600         # 死亡时 BGM 淡出时长（毫秒）
MUSIC_FADE_IN_FRAMES = 20       # 复活后 BGM 淡入帧数（50FPS ≈ 0.4 秒）

# ============================================================
# 路径节点（编辑器里放置/画轨迹；游戏里与节点重合的元素沿轨迹往复移动）
# ============================================================
PATH_DEFAULT_SPEED = 1.0        # 默认移动速度（像素/帧）
PATH_SPEED_STEP = 0.5           # 速度调节步长
PATH_MIN_SPEED = 0.2            # 速度下限
PATH_MAX_SPEED = 8.0            # 速度上限
PATH_NODE_SIZE = 32             # 节点吸附区（32×32，与节点重合的元素被挂上）

# ============================================================
# 中文字体（pygame 默认字体不含中文，渲染成方块）
# ============================================================
# 依次尝试系统中支持中文的字体（微软雅黑 / 黑体 / 宋体 / 楷体），
# 找不到才回退 pygame 默认字体（英文正常，中文仍为方块）。
CJK_FONT_NAMES = (
    "microsoftyahei", "simhei", "simsun", "kaiti", "msyh",
)
_cjk_font_cache = {}


def get_font(size, bold=False):
    """返回支持中文的系统字体实例（带缓存）。需在 pygame.init() 之后调用。"""
    key = (size, bold)
    if key not in _cjk_font_cache:
        font = None
        for name in CJK_FONT_NAMES:
            path = pygame.font.match_font(name, bold=bold)
            if path:
                font = pygame.font.Font(path, size)
                break
        if font is None:
            font = pygame.font.Font(None, size)
        _cjk_font_cache[key] = font
    return _cjk_font_cache[key]


# ============================================================
# 按键绑定
# ============================================================
KEYMAP = {
    "left":    (pygame.K_LEFT, pygame.K_a),
    "right":   (pygame.K_RIGHT, pygame.K_d),
    # 上/下是死键：不参与跳跃/攀爬/移动。普通模式按住"上"会屏蔽跳跃，
    # 藤蔓上按住"上/下"保持不动（shift+上/下 不应有任何反应）。
    "up":      (pygame.K_UP, pygame.K_w),
    "down":    (pygame.K_DOWN,),
    "jump":    (pygame.K_LSHIFT, pygame.K_RSHIFT),
    "restart": (pygame.K_r,),
    "save":    (pygame.K_s,),   # 在 checkpoint 处按 S 存档
    "shoot":   (pygame.K_z,),   # 发射子弹
}
