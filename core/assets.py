"""
core/assets.py — 素材管理器与占位绘制

设计目标：
    * 所有素材统一放在 assets/ 下，通过 AssetManager 访问（统一缓存）。
    * 缺失的素材自动用代码绘制的占位图代替，保证程序随时可运行。
    * 启动时报告缺失素材清单，方便补齐文件。

素材命名规范（相对 assets/）：
    Kid 角色   characters/kid/{anim}_{帧号}.png     帧号从 0 开始
                其中 on_0/1.png = 攀附藤蔓两帧（成品姿势是吸附在右侧藤蔓上）
    头         objects/head.png
    Tile       tiles/{名称}.png                    当前 block_{0..8}（9 种）
    尖刺       spikes/spike_{方向}.png             方向: up / down / left / right
    Checkpoint objects/checkpoint_0.png(未存档) checkpoint_1.png(存档后)
    藤蔓       objects/tengwan_{left,right}.png    攀爬面在对应一侧
    子弹       objects/bullet_{0,1}.png（Z 射击，两帧动画）
    终点       objects/end.png
    提示图     ui/death.png  ui/win.gif
    UI         程序内绘制（不要求图片）
"""

import os

import pygame

import config
from core.gif import decode_gif


PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ASSET_ROOT = os.path.join(PROJECT_ROOT, config.ASSET_DIR)
ROOMS_ROOT = os.path.join(PROJECT_ROOT, config.ROOMS_DIR)

# 各类型占位图配色
_COLOR = {
    "kid":  (240, 240, 255),
    "tile": (132, 96, 56),
    "spike": (200, 44, 44),
    "checkpoint": (255, 204, 64),
    "ui": (64, 92, 128),
    "bullet": (255, 224, 96),
    "vine": (70, 170, 90),
    "platform": (100, 140, 180),
}


def _load_image(path):
    """加载图片；失败返回 None。"""
    if not os.path.isfile(path):
        return None
    try:
        img = pygame.image.load(path)
        if pygame.display.get_surface() is not None:
            img = img.convert_alpha()
        return img
    except Exception as exc:
        print(f"[assets] 素材加载失败: {path} ({exc})")
        return None


# ------------------------------------------------------------
# 占位图绘制（纯代码）
# ------------------------------------------------------------

def _ph_kid(anim):
    w, h = config.KID_WIDTH, config.KID_HEIGHT
    s = pygame.Surface((w, h), pygame.SRCALPHA)
    s.fill(_COLOR["kid"])
    pygame.draw.rect(s, (40, 40, 50), s.get_rect(), 1)
    pygame.draw.rect(s, (40, 40, 50), (2, 6, 2, 4))
    pygame.draw.rect(s, (40, 40, 50), (w - 4, 6, 2, 4))
    return s


def _ph_head():
    t = 26
    s = pygame.Surface((t, t), pygame.SRCALPHA)
    c = (240, 220, 220)
    pygame.draw.circle(s, c, (t // 2, t // 2), t // 2 - 1)
    pygame.draw.circle(s, (40, 40, 50), (t // 2 - 5, t // 2 - 2), 2)
    pygame.draw.circle(s, (40, 40, 50), (t // 2 + 5, t // 2 - 2), 2)
    pygame.draw.arc(s, (40, 40, 50),
                    pygame.Rect(t // 2 - 4, t // 2 + 2, 8, 6), 0, 3.14, 2)
    return s


def _ph_tile(name):
    s = pygame.Surface((config.TILE_SIZE, config.TILE_SIZE))
    s.fill(_COLOR["tile"])
    pygame.draw.rect(s, (255, 255, 255), s.get_rect(), 2)
    pygame.draw.line(s, (0, 0, 0), (4, 4),
                     (config.TILE_SIZE - 4, config.TILE_SIZE - 4), 2)
    pygame.draw.line(s, (0, 0, 0), (config.TILE_SIZE - 4, 4),
                     (4, config.TILE_SIZE - 4), 2)
    return s


def _ph_spike(direction):
    t = config.TILE_SIZE
    m = t // 2
    s = pygame.Surface((t, t), pygame.SRCALPHA)
    c = _COLOR["spike"]
    if direction == "down":
        pts = [(m, t - 5), (5, 4), (t - 5, 4)]
    elif direction == "left":
        pts = [(5, m), (t - 4, 5), (t - 4, t - 5)]
    elif direction == "right":
        pts = [(t - 5, m), (4, 5), (4, t - 5)]
    else:  # up
        pts = [(m, 5), (5, t - 4), (t - 5, t - 4)]
    pygame.draw.polygon(s, c, pts)
    pygame.draw.polygon(s, (255, 255, 255), pts, 1)
    return s


def _ph_checkpoint(active):
    t = config.TILE_SIZE
    s = pygame.Surface((t, t), pygame.SRCALPHA)
    c = _COLOR["checkpoint"] if active else (120, 120, 130)
    pygame.draw.rect(s, (200, 200, 210), (14, 6, 3, 20))
    pygame.draw.polygon(s, c, [(17, 6), (29, 12), (17, 18)])
    pygame.draw.rect(s, (200, 200, 210), (4, 26, 24, 4))
    return s


def _ph_bullet(frame):
    t = 12
    s = pygame.Surface((t, t), pygame.SRCALPHA)
    c = _COLOR["bullet"]
    r = 5 if frame == 0 else 3
    pygame.draw.circle(s, c, (t // 2, t // 2), r)
    pygame.draw.circle(s, (255, 255, 255), (t // 2, t // 2), r, 1)
    return s


def _ph_vine(facing):
    """藤蔓占位图：纵向藤茎 + 两侧叶片。攀爬面在 left/right 一侧。"""
    t = config.TILE_SIZE
    s = pygame.Surface((t, t), pygame.SRCALPHA)
    c = _COLOR["vine"]
    if facing == "right":
        stem_x, leaf_off = t - 5, -4     # 茎靠右，叶片向左
    else:
        stem_x, leaf_off = 5, 4          # 茎靠左，叶片向右
    pygame.draw.rect(s, (40, 120, 60), (stem_x, 0, 4, t))
    for i in range(0, t, 8):
        pygame.draw.circle(s, c, (stem_x + leaf_off, i + 4), 3)
    pygame.draw.rect(s, (60, 60, 60), s.get_rect(), 1)
    return s


def _ph_end():
    t = config.TILE_SIZE
    s = pygame.Surface((t, t), pygame.SRCALPHA)
    for i, y in enumerate(range(0, t, 8)):
        for j, x in enumerate(range(0, t, 8)):
            color = (240, 240, 240) if (i + j) % 2 == 0 else (30, 30, 30)
            pygame.draw.rect(s, color, (x, y, 8, 8))
    pygame.draw.rect(s, (255, 215, 0), s.get_rect(), 3)
    return s


def _ph_platform():
    """平台占位图：32×16 像素，顶部有明显的可站立表面。"""
    w, h = 32, 16
    s = pygame.Surface((w, h), pygame.SRCALPHA)
    c = _COLOR["platform"]
    # 顶部可站立表面（明显的亮色条）
    pygame.draw.rect(s, (180, 210, 255), (0, 0, w, 4))
    # 主体
    pygame.draw.rect(s, c, (0, 4, w, h - 4))
    # 顶部高光线
    pygame.draw.line(s, (255, 255, 255), (0, 0), (w, 0), 1)
    # 底部阴影线
    pygame.draw.line(s, (60, 90, 120), (0, h - 1), (w, h - 1), 1)
    return s


def _ph_plusjump():
    """跳跃球占位图：圆形，粉色。"""
    t = config.TILE_SIZE
    s = pygame.Surface((t, t), pygame.SRCALPHA)
    # 粉色圆形
    pygame.draw.circle(s, (255, 192, 203), (t // 2, t // 2), t // 2 - 2)
    # 白色高光
    pygame.draw.circle(s, (255, 255, 255), (t // 2 - 3, t // 2 - 3), 3)
    return s


def _ph_star(level):
    """跳跃星星占位图：五角星，颜色按段数（1=黑 / 2=灰 / 3=黄）。"""
    t = config.TILE_SIZE
    s = pygame.Surface((t, t), pygame.SRCALPHA)
    colors = {1: (0, 0, 0), 2: (160, 160, 160), 3: (224, 224, 0)}
    c = colors.get(level, (255, 255, 255))
    cx, cy = t // 2, t // 2
    outer = t // 2 - 2
    inner = outer * 0.42
    pts = []
    for i in range(10):
        ang = -90 + i * 36
        r = outer if i % 2 == 0 else inner
        pts.append((cx + r * pygame.math.Vector2(1, 0).rotate(ang)[0],
                    cy + r * pygame.math.Vector2(1, 0).rotate(ang)[1]))
    pygame.draw.polygon(s, c, pts)
    pygame.draw.polygon(s, (255, 255, 255), pts, 1)
    return s

def _ph_water(water_type):
    """水占位图：32×32 像素，半透明。"""
    s = pygame.Surface((config.TILE_SIZE, config.TILE_SIZE), pygame.SRCALPHA)
    # Different colors for different water types
    colors = {
        "first": (135, 206, 235, 128),    # Light blue
        "second": (0, 119, 190, 128),    # Blue
        "zero": (192, 192, 192, 128)     # Light gray
    }
    color = colors.get(water_type, (100, 100, 255, 128))
    s.fill(color)
    # Add some wave-like pattern
    for i in range(0, config.TILE_SIZE, 8):
        pygame.draw.line(s, (255, 255, 255, 50),
                        (i, 0), (i + 4, config.TILE_SIZE), 1)
    return s


def _ph_overlay(name):
    font = pygame.font.Font(None, 64)
    label = font.render(name.upper(), True, (255, 255, 255))
    s = pygame.Surface((label.get_width() + 80, 120), pygame.SRCALPHA)
    pygame.draw.rect(s, (20, 20, 32, 220), s.get_rect(), border_radius=16)
    pygame.draw.rect(s, (255, 255, 255, 120), s.get_rect(), 3, border_radius=16)
    s.blit(label, ((s.get_width() - label.get_width()) // 2, 30))
    return s


def _ph_ui(name):
    s = pygame.Surface((96, 32), pygame.SRCALPHA)
    pygame.draw.rect(s, _COLOR["ui"], s.get_rect(), border_radius=6)
    pygame.draw.rect(s, (255, 255, 255), s.get_rect(), 1, border_radius=6)
    return s


# ------------------------------------------------------------
# AssetManager
# ------------------------------------------------------------

class AssetManager:
    """素材统一访问入口：缓存加载 + 缺失占位。"""

    OVERLAY_FILES = {
        "death": "ui/death.png",
        "win": "ui/win.gif",
    }

    def __init__(self):
        self._cache = {}
        self._gif_cache = {}
        self._mask_cache = {}
        self.missing = set()

    # ---- 目录 ----
    def ensure_dirs(self):
        for sub in ("characters/kid", "tiles", "spikes", "objects", "ui",
                    "backgrounds", "textures"):
            os.makedirs(os.path.join(ASSET_ROOT, sub), exist_ok=True)
        os.makedirs(ROOMS_ROOT, exist_ok=True)
        os.makedirs(config.MUSIC_DIR, exist_ok=True)   # 背景音乐目录

    # ---- 核心 ----
    def _get(self, key, rel, maker):
        """缓存读取：有文件则加载图片，否则生成占位。"""
        if key in self._cache:
            return self._cache[key]
        img = _load_image(os.path.join(ASSET_ROOT, rel))
        if img is None:
            self.missing.add(rel)
            img = maker()
        self._cache[key] = img
        return img

    # ---- 各类型接口 ----
    def kid(self, anim, frame=0):
        rel = f"characters/kid/{anim}_{frame}.png"
        return self._get(f"kid:{anim}:{frame}", rel, lambda: _ph_kid(anim))

    def kid_head(self):
        rel = "objects/head.png"
        return self._get("kid:head", rel, _ph_head)

    def tile(self, name="block_0"):
        rel = f"tiles/{name}.png"
        return self._get(f"tile:{name}", rel, lambda: _ph_tile(name))

    def custom_texture(self, name):
        """自定义材质：assets/textures/{name}，缺失返回 None（调用方回退默认贴图）。"""
        key = f"custom_tex:{name}"
        if key in self._cache:
            return self._cache[key]
        img = _load_image(os.path.join(ASSET_ROOT, "textures", name))
        self._cache[key] = img
        return img

    def tile_small(self, name="block_0"):
        """小砖块：tiles/{name}.png 原贴图缩放到 16×16（贴图不变，仅缩小）。"""
        key = f"tile_small:{name}"
        if key in self._cache:
            return self._cache[key]
        img = self.tile(name)
        if img.get_size() != (16, 16):
            img = pygame.transform.smoothscale(img, (16, 16))
        self._cache[key] = img
        return img

    def spike(self, direction="up"):
        rel = f"spikes/spike_{direction}.png"
        return self._get(f"spike:{direction}", rel, lambda: _ph_spike(direction))

    def spike_mask(self, direction="up"):
        """尖刺像素级碰撞遮罩：由 spike_{direction}.png 的 alpha 通道逐像素生成。

        与 spike() 用同一张图，碰撞区精确贴合可见像素（含锯齿/不规则的形状），
        换素材自动同步；缺失时用占位图生成同样的遮罩。
        """
        key = f"spike_mask:{direction}"
        if key in self._mask_cache:
            return self._mask_cache[key]
        surf = self.spike(direction)
        mask = pygame.mask.from_surface(surf, config.SPIKE_MASK_THRESHOLD)
        self._mask_cache[key] = mask
        return mask

    def mini_spike(self, direction="up"):
        """小刺：spikes/mini_spike_{direction}.png（16×16 像素）。"""
        rel = f"spikes/mini_spike_{direction}.png"
        return self._get(f"mini_spike:{direction}", rel, lambda: _ph_mini_spike(direction))

    def mini_spike_mask(self, direction="up"):
        """小刺像素级碰撞遮罩：由 mini_spike_{direction}.png 的 alpha 逐像素生成。

        碰撞精确贴合可见像素（16×16 像素），与 spike_mask 同一套机制。
        """
        key = f"mini_spike_mask:{direction}"
        if key in self._mask_cache:
            return self._mask_cache[key]
        surf = self.mini_spike(direction)
        mask = pygame.mask.from_surface(surf, config.SPIKE_MASK_THRESHOLD)
        self._mask_cache[key] = mask
        return mask

    def checkpoint(self, active=False):
        name = config.CHECKPOINT_IMAGE_ACTIVE if active else config.CHECKPOINT_IMAGE_INACTIVE
        rel = f"objects/{name}"
        return self._get(f"checkpoint:{active}", rel, lambda: _ph_checkpoint(active))

    def bullet(self, frame=0):
        """子弹动画帧：objects/bullet_{frame}.png（两帧循环）。"""
        rel = f"objects/bullet_{frame}.png"
        return self._get(f"bullet:{frame}", rel, lambda: _ph_bullet(frame))

    def bullet_mask(self, frame=0):
        """子弹像素级碰撞遮罩：由 bullet_{frame}.png 的 alpha 逐像素生成。

        碰撞精确贴合可见像素（如 4×4 子弹的菱形实体、透明角不参与碰撞），
        换素材自动同步；与 spike_mask 同一套机制。
        """
        key = f"bullet_mask:{frame}"
        if key in self._mask_cache:
            return self._mask_cache[key]
        surf = self.bullet(frame)
        mask = pygame.mask.from_surface(surf, config.BULLET_MASK_THRESHOLD)
        self._mask_cache[key] = mask
        return mask

    def vine(self, facing="right"):
        """藤蔓格：objects/tengwan_{left,right}.png（攀爬面在对应一侧）。"""
        rel = f"objects/tengwan_{facing}.png"
        return self._get(f"vine:{facing}", rel, lambda: _ph_vine(facing))

    def platform(self):
        """平台：objects/platform.png（32×16 像素，单向平台）。"""
        rel = "objects/platform.png"
        return self._get("platform", rel, _ph_platform)

    def water(self, water_type="first"):
        """水：objects/water_{type}.png（32×32 像素，半透明）。"""
        rel = f"objects/water_{water_type}.png"
        return self._get(f"water:{water_type}", rel, lambda: _ph_water(water_type))

    def plusjump(self):
        """跳跃球：objects/plusjump.png（圆形，粉色）。"""
        rel = "objects/plusjump.png"
        return self._get("plusjump", rel, _ph_plusjump)

    def star(self, level):
        """跳跃星星：objects/star_{level映射}.png（段数 level=1/2/3）。

        贴图映射见 config.STAR_IMAGES（一段=star_0.png，二段=star_2.png，
        三段=star_3.png；star_1.png 缺失不用，补图只改映射即可）。
        """
        rel = f"objects/{config.STAR_IMAGES[level]}"
        return self._get(f"star:{level}", rel, lambda: _ph_star(level))

    def end(self):
        rel = "objects/end.png"
        return self._get("end", rel, _ph_end)

    def background(self, name):
        """背景图：assets/backgrounds/{name}；缺失或名为空返回 None（用纯色背景）。

        与其它素材不同，背景图**可缺**：没有就回退纯色 bg_color，不生成占位图。
        """
        if not name:
            return None
        key = f"background:{name}"
        if key in self._cache:
            return self._cache[key]
        img = _load_image(os.path.join(ASSET_ROOT, "backgrounds", name))
        if img is None:
            self.missing.add(f"backgrounds/{name}")
        self._cache[key] = img
        return img

    def overlay(self, name="death"):
        rel = self.OVERLAY_FILES.get(name, f"overlays/{name}.png")
        return self._get(f"overlay:{name}", rel, lambda: _ph_overlay(name))

    def gif_animation(self, name="win"):
        """返回动图帧列表 [(Surface, 时长ms), ...]；静态或无此图返回 None。"""
        key = f"gif:{name}"
        if key in self._gif_cache:
            return self._gif_cache[key]
        anim = None
        rel = self.OVERLAY_FILES.get(name)
        if rel and rel.lower().endswith(".gif"):
            path = os.path.join(ASSET_ROOT, rel)
            if os.path.isfile(path):
                anim = decode_gif(path)
        self._gif_cache[key] = anim
        return anim

    def ui(self, name="button"):
        rel = f"ui/{name}.png"
        return self._get(f"ui:{name}", rel, lambda: _ph_ui(name))

    # ---- 缺失报告 ----
    def required_files(self):
        """程序需要的全部素材文件清单。"""
        files = []
        for anim, frames in config.KID_ANIM_FRAMES.items():
            for i in range(frames):
                files.append(f"characters/kid/{anim}_{i}.png")
        files.append("objects/head.png")
        for name in config.TILE_TYPES:
            files.append(f"tiles/{name}.png")
        for d in ("up", "down", "left", "right"):
            files.append(f"spikes/spike_{d}.png")
        files.append("objects/" + config.CHECKPOINT_IMAGE_INACTIVE)
        files.append("objects/" + config.CHECKPOINT_IMAGE_ACTIVE)
        files.append("objects/end.png")
        for d in ("left", "right"):
            files.append(f"objects/tengwan_{d}.png")
        for i in range(config.BULLET_FRAMES):
            files.append(f"objects/bullet_{i}.png")
        files.append("objects/platform.png")
        for water_type in ("first", "second", "zero"):
            files.append(f"objects/water_{water_type}.png")
        for level in config.STAR_LEVELS:
            files.append(f"objects/{config.STAR_IMAGES[level]}")
        files.append(self.OVERLAY_FILES["death"])
        files.append(self.OVERLAY_FILES["win"])
        return files

    def report_missing(self):
        """扫描应备素材，打印缺失清单。"""
        missing = [f for f in self.required_files()
                   if not os.path.isfile(os.path.join(ASSET_ROOT, f))]
        if missing:
            print("[assets] 缺少以下素材（将使用占位图）：")
            for f in missing:
                print(f"    assets/{f}")
        else:
            print("[assets] 全部素材已就位。")
        return missing


def _ph_mini_spike(direction):
    """小刺占位图：16×16 像素，是正常刺的一半大小。"""
    t = 16  # 小刺的尺寸
    m = t // 2
    s = pygame.Surface((t, t), pygame.SURFACEALPHA)
    c = _COLOR["spike"]
    if direction == "down":
        pts = [(m, t - 2), (2, 2), (t - 2, 2)]
    elif direction == "left":
        pts = [(2, m), (t - 2, 2), (t - 2, t - 2)]
    elif direction == "right":
        pts = [(t - 2, m), (2, 2), (2, t - 2)]
    else:  # up
        pts = [(m, 2), (2, t - 2), (t - 2, t - 2)]
    pygame.draw.polygon(s, c, pts)
    pygame.draw.polygon(s, (255, 255, 255), pts, 1)
    return s
