"""
core/effects.py — 死亡 / 通关演出效果

死亡：红色粒子迸发 + Kid 的头(head.png)掉落并四处弹跳 + 提示图渐显 + 四周变黑。
通关：提示图渐显 + 四周变黑。
"""

import colorsys
import random

import pygame

import config
from physics.collision import move_and_collide


# ------------------------------------------------------------
# 粒子
# ------------------------------------------------------------

class Particle:
    __slots__ = ("x", "y", "hsp", "vsp", "life", "max_life", "surf")

    def __init__(self, x, y, hsp, vsp, life, size, color):
        self.x = x
        self.y = y
        self.hsp = hsp
        self.vsp = vsp
        self.life = life
        self.max_life = life
        self.surf = pygame.Surface((size, size))
        self.surf.fill(color)

    def update(self):
        self.vsp += config.DEATH_PARTICLE_GRAVITY
        self.x += self.hsp
        self.y += self.vsp
        self.life -= 1

    @property
    def dead(self):
        return self.life <= 0

    def draw(self, screen):
        if self.life <= 0:
            return
        self.surf.set_alpha(int(255 * max(self.life / self.max_life, 0.0)))
        screen.blit(self.surf, (round(self.x), round(self.y)))


# ------------------------------------------------------------
# 跳跃星星触碰特效：透明的星星慢慢放大慢慢消失
# ------------------------------------------------------------

class StarFX:
    """碰到跳跃星星时的反馈：星星从 1 倍慢慢放大到 STAR_FX_SCALE_END，
    透明度从 STAR_FX_ALPHA_START 线性淡出到 0，共 STAR_FX_FRAMES 帧。"""

    __slots__ = ("surf", "x", "y", "level", "timer")

    def __init__(self, image, cx, cy, level):
        self.surf = image
        self.x = float(cx)
        self.y = float(cy)
        self.level = level
        self.timer = 0

    def update(self):
        self.timer += 1

    @property
    def dead(self):
        return self.timer >= config.STAR_FX_FRAMES

    def draw(self, screen):
        t = self.timer
        n = config.STAR_FX_FRAMES
        if t <= 0 or t >= n:
            return
        p = t / max(n - 1, 1)                        # 进度 0→1
        scale = 1.0 + (config.STAR_FX_SCALE_END - 1.0) * p
        alpha = int(config.STAR_FX_ALPHA_START * (1.0 - p))
        base_w, base_h = self.surf.get_size()
        w = max(1, int(base_w * scale))
        h = max(1, int(base_h * scale))
        img = pygame.transform.smoothscale(self.surf, (w, h))
        img.set_alpha(alpha)
        rect = img.get_rect(center=(round(self.x), round(self.y)))
        screen.blit(img, rect)


# ------------------------------------------------------------
# 公用：四周变黑 + 提示图渐显
# ------------------------------------------------------------

def _draw_veil_and_overlay(screen, veil_alpha, overlay_img, overlay_alpha):
    if veil_alpha > 0:
        veil = pygame.Surface(screen.get_size())
        veil.fill((0, 0, 0))
        veil.set_alpha(veil_alpha)
        screen.blit(veil, (0, 0))
    if overlay_alpha > 0 and overlay_img is not None:
        img = overlay_img.copy()
        img.set_alpha(overlay_alpha)
        rect = img.get_rect(center=(config.ROOM_WIDTH // 2, config.ROOM_HEIGHT // 2))
        screen.blit(img, rect)


# ------------------------------------------------------------
# 死亡演出
# ------------------------------------------------------------

class DeathFX:
    def __init__(self, assets):
        self.assets = assets
        self.timer = 0
        self.duration = config.DEATH_FRAMES
        self.particles = []
        self.head = None          # dict：surf/w/h/x/y/hsp/vsp/angle/resting
        self._base = None         # 头原图（变色/拉伸的基准）
        self._stretch_x = 1.0     # 当前拉伸倍率（向随机目标平滑逼近）
        self._stretch_y = 1.0
        self._stretch_tx = 1.0    # 随机拉伸目标
        self._stretch_ty = 1.0
        self.trail = []           # 彩虹拖尾残影：[{x,y,angle,hue}, ...]（旧→新）
        self._palette = []        # 预着色好的彩虹色头图（按 DEATH_TRAIL_HUE_STEP 取 N 种色相）
        self.overlay_alpha = 0
        self.veil_alpha = 0
        self.active = False

    def start(self, kid_rect, facing):
        self.timer = 0
        self.active = True
        self.overlay_alpha = 0
        self.veil_alpha = 0
        self.particles = []
        self.trail = []
        self._stretch_x = self._stretch_y = 1.0
        self._stretch_tx = self._stretch_ty = 1.0
        cx, cy = kid_rect.centerx, kid_rect.centery
        for _ in range(config.DEATH_PARTICLE_COUNT):
            self.particles.append(Particle(
                cx + random.uniform(-4, 4),
                cy + random.uniform(-6, 6),
                random.uniform(-4.0, 4.0),
                random.uniform(-7.0, 2.0),
                random.randint(18, 45),
                random.randint(2, 4),
                random.choice(config.DEATH_PARTICLE_COLORS),
            ))
        self._base = self.assets.kid_head()
        hw, hh = self._base.get_size()
        self.head = {
            "surf": self._base, "w": hw, "h": hh,
            "x": kid_rect.x + (kid_rect.w - hw) / 2.0,
            "y": float(kid_rect.y),
            "hsp": float(facing) * config.DEATH_HEAD_HSP,
            "vsp": config.DEATH_HEAD_VSP,
            "angle": 0.0,
            "resting": False,
        }
        # 彩虹调色板：_colorize 是逐像素操作很贵，这里一次死亡只预着色 N 种色相，
        # 之后每帧拖尾只是从调色板取图 + scale/rotate（C 加速），保证 50FPS 流畅
        self._palette = [self._colorize(self._base, h)
                         for h in range(0, 360, config.DEATH_TRAIL_HUE_STEP)]

    def _colorize(self, surf, hue_deg):
        """把整张图做色相旋转（超级变色：棕色/肤色逐帧循环变色）。"""
        shift = (hue_deg / 360.0) % 1.0
        if shift == 0.0:
            return surf
        out = surf.copy()
        w, hgt = surf.get_size()
        for y in range(hgt):
            for x in range(w):
                r, g, b, a = surf.get_at((x, y))
                if a == 0:
                    continue
                hh, ss, vv = colorsys.rgb_to_hsv(r / 255.0, g / 255.0, b / 255.0)
                hh = (hh + shift) % 1.0
                rr, gg, bb = colorsys.hsv_to_rgb(hh, ss, vv)
                out.set_at((x, y), (int(rr * 255), int(gg * 255), int(bb * 255), a))
        return out

    def update(self, solids):
        if not self.active:
            return
        self.timer += 1
        for p in self.particles:
            p.update()
        self.particles = [p for p in self.particles if not p.dead]

        if self.head is not None:
            h = self.head
            nx, ny, on_ground, hit_ceil, hit_wall = move_and_collide(
                h["x"], h["y"], h["w"], h["h"], h["hsp"], h["vsp"], solids)
            h["x"], h["y"] = nx, ny
            if on_ground:
                if abs(h["vsp"]) < 1.0:
                    h["vsp"] = 0.0
                    h["resting"] = True
                else:
                    h["vsp"] = -abs(h["vsp"]) * config.DEATH_HEAD_BOUNCE
                    h["resting"] = False
            if hit_ceil:
                h["vsp"] = abs(h["vsp"]) * 0.5
            if hit_wall != 0:
                h["hsp"] = config.DEATH_HEAD_WALL * (
                    abs(h["hsp"]) if hit_wall == -1 else -abs(h["hsp"]))
            # 房间边界反弹：头一直在屏幕内弹跳，持续演出到按 R
            if h["x"] < 0:
                h["x"], h["hsp"] = 0.0, abs(h["hsp"]) * config.DEATH_HEAD_WALL
            elif h["x"] + h["w"] > config.ROOM_WIDTH:
                h["x"] = config.ROOM_WIDTH - h["w"]
                h["hsp"] = -abs(h["hsp"]) * config.DEATH_HEAD_WALL
            if h["y"] < 0:
                h["y"], h["vsp"] = 0.0, abs(h["vsp"]) * 0.6
            elif h["y"] + h["h"] > config.ROOM_HEIGHT:
                h["y"] = config.ROOM_HEIGHT - h["h"]
                h["vsp"] = -abs(h["vsp"]) * config.DEATH_HEAD_BOUNCE
                h["resting"] = False
            h["angle"] += h["hsp"] * config.DEATH_HEAD_SPIN

            # 落地静止后随机再跳，让头的演出一直持续到按 R 复活
            if h["resting"] and self.timer % config.DEATH_HEAD_HOP_EVERY == 0:
                h["vsp"] = -random.uniform(config.DEATH_HEAD_HOP_VSP_MIN,
                                           config.DEATH_HEAD_HOP_VSP_MAX)
                h["hsp"] = random.choice((-1, 1)) * random.uniform(
                    0.5, config.DEATH_HEAD_HOP_HSP)
                h["resting"] = False

            # 随机拉伸：每 N 帧换一个目标，平滑逼近（橡皮头效果）
            if self.timer % config.DEATH_HEAD_STRETCH_EVERY == 0:
                self._stretch_tx = random.uniform(config.DEATH_HEAD_STRETCH_MIN,
                                                  config.DEATH_HEAD_STRETCH_MAX)
                self._stretch_ty = random.uniform(config.DEATH_HEAD_STRETCH_MIN,
                                                  config.DEATH_HEAD_STRETCH_MAX)
            self._stretch_x += (self._stretch_tx - self._stretch_x) * config.DEATH_HEAD_STRETCH_SMOOTH
            self._stretch_y += (self._stretch_ty - self._stretch_y) * config.DEATH_HEAD_STRETCH_SMOOTH

            # 彩虹拖尾：记录头的中心/旋转快照；相邻残影色相差 HUE_STEP，
            # 再加上随时间流动的偏移 → 整条彩虹沿轨迹流动
            self.trail.append({
                "x": h["x"] + h["w"] / 2.0,
                "y": h["y"] + h["h"] / 2.0,
                "angle": h["angle"],
                "sx": self._stretch_x,   # 同步头的实时拉伸，拖尾跟着橡皮头一起变形
                "sy": self._stretch_y,
                "hue": ((self.timer * config.DEATH_TRAIL_HUE_FLOW
                         + len(self.trail) * config.DEATH_TRAIL_HUE_STEP) % 360.0),
            })
            if len(self.trail) > config.DEATH_TRAIL_LENGTH:
                self.trail.pop(0)

        self.overlay_alpha = min(self.overlay_alpha + config.DEATH_FADE_STEP,
                                 config.DEATH_OVERLAY_ALPHA)
        self.veil_alpha = min(self.veil_alpha + config.DEATH_VEIL_STEP,
                              config.DEATH_VEIL_ALPHA)

    @property
    def done(self):
        return self.active and self.timer >= self.duration

    def draw(self, screen):
        if not self.active:
            return
        for p in self.particles:
            p.draw(screen)
        # 彩虹拖尾：从最旧到最新依次画残影（年龄越大越透明/越小），压在头下方
        if self.trail:
            n = len(self.trail)
            for i, seg in enumerate(self.trail):
                # trail[0] 是最旧的残影（先压入、满员时从头弹出），trail[-1] 最新、紧贴头。
                # age：0=最新（最大最亮），1=最旧（最小最淡）。
                age = (n - 1 - i) / max(n - 1, 1)
                alpha = int(255 * config.DEATH_TRAIL_ALPHA * (1.0 - age))
                sc = (config.DEATH_TRAIL_MIN_SCALE
                      + (1.0 - config.DEATH_TRAIL_MIN_SCALE) * (1.0 - age))
                sprite = self._palette[
                    int((seg["hue"] % 360) / config.DEATH_TRAIL_HUE_STEP)
                    % len(self._palette)]
                w = max(1, int(sprite.get_width() * sc * seg["sx"]))
                ht = max(1, int(sprite.get_height() * sc * seg["sy"]))
                img = pygame.transform.scale(sprite, (w, ht))
                img = pygame.transform.rotate(img, seg["angle"])
                img.set_alpha(alpha)
                rect = img.get_rect(center=(round(seg["x"]), round(seg["y"])))
                screen.blit(img, rect)

        if self.head is not None:
            h = self.head
            # 超级变色（色相旋转）→ 随机拉伸（非等比缩放）→ 旋转
            tinted = self._colorize(self._base, self.timer * config.DEATH_HEAD_HUE_SPEED)
            w = max(1, int(tinted.get_width() * self._stretch_x))
            ht = max(1, int(tinted.get_height() * self._stretch_y))
            if (w, ht) != tinted.get_size():
                tinted = pygame.transform.scale(tinted, (w, ht))
            img = pygame.transform.rotate(tinted, h["angle"])
            rect = img.get_rect(center=(
                round(h["x"] + h["w"] / 2),
                round(h["y"] + h["h"] / 2)))
            screen.blit(img, rect)
        _draw_veil_and_overlay(screen, self.veil_alpha,
                               self.assets.overlay("death"), self.overlay_alpha)


# ------------------------------------------------------------
# 通关演出
# ------------------------------------------------------------

class OverlayFX:
    def __init__(self, assets, image_key,
                 duration, overlay_alpha, veil_alpha, fade_step, veil_step):
        self.assets = assets
        self.image_key = image_key
        self.duration = duration
        self.overlay_max = overlay_alpha
        self.veil_max = veil_alpha
        self.fade_step = fade_step
        self.veil_step = veil_step
        self.timer = 0
        self.overlay_alpha = 0
        self.veil_alpha = 0
        self.active = False
        self.frames = None          # 懒加载：首次 start() 时才解码
        self.frame_index = 0
        self.frame_timer = 0
        self.frame_delays = []      # 每帧的游戏帧数

    def _load_frames(self):
        anim = self.assets.gif_animation(self.image_key)
        if anim and len(anim) > 1:
            self.frames = [s.copy() for s, _ in anim]
            # 时长 ms → 游戏帧（固定 50 FPS）
            self.frame_delays = [max(1, round(ms * config.FPS / 1000)) for _, ms in anim]
        else:
            self.frames = [self.assets.overlay(self.image_key)]
            self.frame_delays = [1]

    def start(self):
        if self.frames is None:
            self._load_frames()
        self.timer = 0
        self.frame_index = 0
        self.frame_timer = 0
        self.overlay_alpha = 0
        self.veil_alpha = 0
        self.active = True

    def update(self):
        if not self.active:
            return
        self.timer += 1
        if len(self.frames) > 1:
            self.frame_timer += 1
            if self.frame_timer >= self.frame_delays[self.frame_index]:
                self.frame_timer = 0
                self.frame_index = (self.frame_index + 1) % len(self.frames)
        self.overlay_alpha = min(self.overlay_alpha + self.fade_step, self.overlay_max)
        self.veil_alpha = min(self.veil_alpha + self.veil_step, self.veil_max)

    @property
    def done(self):
        return self.active and self.timer >= self.duration

    def draw(self, screen):
        if not self.active:
            return
        _draw_veil_and_overlay(screen, self.veil_alpha,
                               self.frames[self.frame_index], self.overlay_alpha)
