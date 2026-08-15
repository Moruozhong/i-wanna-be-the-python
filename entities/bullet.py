"""
entities/bullet.py — 子弹（Z 射击）

像素级碰撞：碰撞遮罩由 bullet_*.png 的 alpha 逐像素生成（精确贴合可见像素），
碰撞箱尺寸 = 贴图实际尺寸，不再用写死的矩形。
帧级物理：每帧水平匀速移动，出屏即消失；不撞墙/尖刺（可穿过地形），只用来碰 Checkpoint 存档。
"""

import pygame

import config


class Bullet:
    def __init__(self, kid, assets):
        self.assets = assets
        # 尺寸 = 贴图实际尺寸；碰撞遮罩由贴图 alpha 逐像素生成
        self.w, self.h = self.assets.bullet(0).get_size()
        self.mask = self.assets.bullet_mask(0)
        self.facing = 1 if kid.facing >= 0 else -1
        # 出生点：Kid 朝向一侧的前缘，垂直居中
        self.x = (kid.x + kid.w - 1) if self.facing > 0 else (kid.x - self.w + 1)
        self.y = kid.y + (kid.h - self.h) // 2
        self.hsp = self.facing * config.BULLET_SPEED
        self.frame = 0
        self._frame_timer = 0

    @property
    def rect(self):
        return pygame.Rect(round(self.x), round(self.y), self.w, self.h)

    def update(self):
        """推进一帧；返回 False 表示子弹已出屏（死亡）。"""
        self.x += self.hsp
        self._frame_timer += 1
        if self._frame_timer >= config.BULLET_FRAME_INTERVAL:
            self._frame_timer = 0
            self.frame = (self.frame + 1) % config.BULLET_FRAMES
            self.mask = self.assets.bullet_mask(self.frame)   # 同步当前帧的碰撞遮罩
        if self.x < -self.w or self.x > config.ROOM_WIDTH:
            return False
        return True

    def draw(self, screen):
        img = self.assets.bullet(self.frame)
        if self.facing < 0:
            img = pygame.transform.flip(img, True, False)
        screen.blit(img, (round(self.x), round(self.y)))
