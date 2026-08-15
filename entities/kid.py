"""
entities/kid.py — Kid 玩家

- 碰撞箱 11×21（与图片尺寸无关）
- 离散帧物理：水平立即响应，无加速度 / 滑行 / 惯性
- 每帧严格按 11 步顺序更新
- 玩家状态机 NORMAL / VINE_CLING / DEAD：NORMAL 走普通平台物理；
  VINE_CLING（藤蔓攀附）的输入/移动/下滑/脱离由 GameScene 独立处理；
  on_0/1.png 是吸附右侧藤蔓的成品姿势，吸附左侧藤蔓时绘制镜像反转
"""

import pygame

import config
from physics.collision import is_grounded, move_and_collide, move_and_collide_with_platforms, is_on_platform


class Kid:
    def __init__(self, x, y, assets, sounds=None):
        self.x = float(x)          # 碰撞箱左上角（浮点，绘制时取整）
        self.y = float(y)
        self.w = config.KID_WIDTH
        self.h = config.KID_HEIGHT
        self.assets = assets
        self.sounds = sounds       # SoundManager 或 None（无头测试用 None）

        self.hsp = 0.0
        self.vsp = 0.0
        self.on_ground = False
        self.hit_ceiling = False
        self.jump_count = 0        # 已用跳跃次数：0=未用 1=已一段跳 2=已二段跳 3=已三段跳
        self.max_jumps = 2         # 最多跳跃次数（默认二段跳；被跳跃星星改变，死亡重置回 2）
        self._was_touching_surface = False   # 上一帧是否落地/贴板（陆地，重置用边沿触发）
        self._was_in_second_water = False    # 上一帧是否在二段水中落地/贴板（二段水刷新用边沿触发）
        self.facing = 1
        self.alive = True

        # 玩家状态机：NORMAL / VINE_CLING（藤蔓攀附）/ DEAD（由场景 state 管理）
        self.mode = "normal"       # "normal" / "vine"
        self.vine_side = "right"   # 攀附的藤蔓面（仅 on 动画绘制用）

        self.anim = "idle"
        self.frame = 0
        self._anim_timer = 0
        self._last_anim = None
        self.last_draw_pos = None   # 最近一帧的贴图绘制坐标（F1/F2 调试用）

    # ---- 派生 ----
    @property
    def rect(self):
        return pygame.Rect(round(self.x), round(self.y), self.w, self.h)

    @property
    def align(self):
        return int(round(self.x)) % config.ALIGN_MODULO

    def reset(self, x, y):
        self.x = float(x)
        self.y = float(y)
        self.hsp = 0.0
        self.vsp = 0.0
        self.on_ground = False
        self.hit_ceiling = False
        self.jump_count = 0
        self.max_jumps = 2        # 死亡/重生后最多跳跃次数重置为默认二段跳
        self._was_touching_surface = False
        self._was_in_second_water = False
        self.alive = True
        self.mode = "normal"
        self.vine_side = "right"
        self._last_anim = None

    # ---- 主更新：严格 11 步 ----
    def update(self, inp, solids, platforms=None, water_type=None):
        """更新 Kid 物理状态，支持单向平台。

        参数：
            inp: InputState 输入状态
            solids: 固体矩形列表
            platforms: 单向平台矩形列表（可选，默认空列表）
            water_type: 当前所在的水类型（"first", "second", "zero" 或 None）
        """
        if platforms is None:
            platforms = []
        # 1. 读取输入
        left = inp.held("left")
        right = inp.held("right")
        up = inp.held("up")
        down = inp.held("down")
        jump_pressed = inp.pressed("jump")
        jump_released = inp.released("jump")

        # 2. 计算水平速度（立即响应，无惯性）
        if left and not right:
            self.hsp = -config.PLAYER_SPEED
        elif right and not left:
            self.hsp = config.PLAYER_SPEED
        else:
            self.hsp = 0.0

        # 3. 处理跳跃
        #    jump_count = 已用跳跃次数（0=未用 1=已一段跳 2=已二段跳 ...）
        #    max_jumps  = 最多可用次数（默认 2=二段跳；被跳跃星星改为 1/2/3）。
        #    空中跳按已用次数累加：0→第一跳(记1)、1→二段跳(记2)、...，
        #    判定门限 jump_count<max_jumps。
        #    上/下方向键是死键：按住"上"或"下"屏蔽跳跃（shift+上/下 不应有任何反应）
        # 如果是零段水，不允许跳跃（但保留跳跃次数）
        can_jump = True
        if water_type == "zero" and jump_pressed:
            can_jump = False
            # 零段水阻止跳跃，但不消耗跳跃次数

        if can_jump and jump_pressed and not (up or down):
            if self.on_ground:
                self.vsp = config.JUMP_SPEED
                # jump_count = 已用跳跃次数（0=未用 1=已一段跳 ...）。
                # 陆地一段跳记 1（空中判定 jump_count<max_jumps 仍可继续跳）；
                # 水中一段跳累加且封顶 max_jumps（水中跳跃不消耗次数，见空中分支）。
                if water_type is None:
                    self.jump_count = 1
                else:
                    self.jump_count = min(self.jump_count + 1, self.max_jumps)
                self._play("jump")
            elif config.DOUBLE_JUMP_ENABLED:
                # 在水中可以跳跃而不消耗次数（出水后由 GameScene 记一段，
                # 空中只剩一次跳，不会白得满额二段跳）
                if water_type is not None:
                    self.vsp = config.DOUBLE_JUMP_SPEED
                    self._play("jump")
                elif self.jump_count < self.max_jumps:
                    # 空中跳按"已用次数"累加：
                    #   0（没用过任何跳，如贴藤蔓未起跳 / 走出平台边缘）→ 第一跳，记 1
                    #   1（已用过一段跳）→ 二段跳，记 2；以此类推直到 max_jumps
                    # 之前空中跳一律记 2：贴藤蔓（0）→ 跳出 → 空中一按，跳跃计数直接
                    # 从 0 跳到 2，只给一次跳，二段跳被白白吞掉（bug）。
                    if self.jump_count == 0:
                        self.vsp = config.JUMP_SPEED
                        self.jump_count = 1
                    else:
                        self.vsp = config.DOUBLE_JUMP_SPEED
                        self.jump_count += 1
                    self._play("jump")
        # 松开跳跃键且仍在上升：立即截断（长短跳）
        if jump_released and self.vsp < 0:
            self.vsp *= config.JUMP_CUT_MULTIPLIER

        # 4. 应用重力（落地站立时 vsp 保持 0，离地瞬间从 0.4 开始加速）
        if self.on_ground and self.vsp >= 0:
            self.vsp = 0.0
        else:
            # 正常应用重力
            self.vsp = self.vsp + config.GRAVITY

            # 最大下落速度封顶（防止无限加速；单帧位移 < Tile 才不会高速穿墙）
            if self.vsp > config.MAX_FALL_SPEED:
                self.vsp = config.MAX_FALL_SPEED

            # 如果在水里，限制最大下落速度为 WATER_FALL_SPEED（更严格的封顶）
            if water_type is not None and self.vsp > config.WATER_FALL_SPEED:
                self.vsp = config.WATER_FALL_SPEED

        # 5-7. 移动X -> 检测X碰撞 -> 修正X位置
        # 8-10. 移动Y -> 检测Y碰撞 -> 修正Y位置（支持单向平台）
        new_x, new_y, landed, hit_ceiling, _hit_wall = \
            move_and_collide_with_platforms(self.x, self.y, self.w, self.h,
                                           self.hsp, self.vsp, solids, platforms)
        self.x, self.y = new_x, new_y
        if landed:
            self.vsp = 0.0
        if hit_ceiling:
            self.vsp = 0.0

        # 房间边界（不可越出；出口/切房在阶段5处理）
        self.x = max(0.0, min(self.x, config.ROOM_WIDTH - self.w))
        if self.y < 0.0:
            self.y = 0.0
            self.vsp = 0.0

        # 11. 更新状态（落地判定 + 动画 + 朝向）
        self.on_ground = is_grounded(self.x, self.y, self.w, self.h, solids, platforms)
        # 检测是否与板子重叠（不管是碰到的还是站着的）
        on_any_platform = is_on_platform(self.x, self.y, self.w, self.h, platforms)
        # 落地/贴板重置跳跃次数（边沿触发，只在"进入该状态"的那一帧清 0；
        # 若每帧持续清 0，空中擦过板子时按跳会先记 1 又立刻被抹掉，
        # 摸板子跳的那一跳永远不消耗，还能无限免费跳（bug 9））：
        #   · 陆地（不在水中）：落地/贴板重置 0；离开地面/板子（走落台阶）记一段，
        #     否则空中 jump_count=0 白得满额跳（与地面跳消耗一段一致）。
        #   · 二段水：落地/贴板也重置 0（"接触地面刷新跳跃次数"，泳池无限跳），
        #     但二段水中起跳不触发"离开地面记一段"（落地已刷新，正常 0→1 消耗）。
        #   · 一段水/零段水：不重置（一段水跳了消耗；零段水禁止跳且保留次数）。
        on_land_surface = (self.on_ground or on_any_platform) and water_type is None
        in_second_water = (self.on_ground or on_any_platform) and water_type == "second"
        if on_land_surface and not self._was_touching_surface:
            self.jump_count = 0     # 陆地落地/贴板：边沿重置
        elif not on_land_surface and self._was_touching_surface:
            self.jump_count = max(self.jump_count, 1)   # 离开陆地：视为已用一段跳
        if in_second_water and not self._was_in_second_water:
            self.jump_count = 0     # 二段水中落地/贴板：边沿重置（接触地面刷新）
        self._was_touching_surface = on_land_surface
        self._was_in_second_water = in_second_water
        if not self.on_ground:
            self.anim = "jump" if self.vsp < 0 else "fall"
        elif abs(self.hsp) > 0:
            self.anim = "run"
        else:
            self.anim = "idle"

        if self.hsp > 0:
            self.facing = 1
        elif self.hsp < 0:
            self.facing = -1

        self._advance_anim()

    def _play(self, name):
        if self.sounds is not None:
            self.sounds.play(name)

    def _advance_anim(self):
        # 动画切换时重置帧号，避免用旧动画的帧号去取新动画的素材（导致占位图）
        if self.anim != self._last_anim:
            self._last_anim = self.anim
            self.frame = 0
            self._anim_timer = 0
        frames = config.KID_ANIM_FRAMES.get(self.anim, 1)
        if frames <= 1:
            self.frame = 0
            return
        interval = config.KID_ANIM_INTERVALS.get(self.anim, 6)
        self._anim_timer += 1
        if self._anim_timer >= interval:
            self._anim_timer = 0
            self.frame = (self.frame + 1) % frames

    # ---- 绘制 ----
    def draw(self, screen):
        if not self.alive:
            return
        img = self.assets.kid(self.anim, self.frame)
        img_w, img_h = img.get_size()
        if self.anim == "on":
            # 攀附专用对齐（不能用普通动画的水平居中公式）：
            # on_*.png 是"吸附右侧藤蔓"的成品姿势，抓握手在图片左缘
            # （内容 bbox 从 x=0 开始），水平居中会让贴图整体向藤蔓侧
            # 偏移 (img_w-w)//2 ≈ 10px，Kid 沉进藤蔓里。
            # 正确对齐 = 抓握边贴碰撞箱朝向藤蔓的那条边（垂直仍底部对齐）：
            #   vine_side="right"：Kid 在藤蔓右侧、面朝左 → 图左缘(手)贴碰撞箱左缘
            #   vine_side="left" ：镜像后手在图右缘       → 图右缘贴碰撞箱右缘
            if self.vine_side == "left":
                img = pygame.transform.flip(img, True, False)
                draw_x = round(self.x) + self.w - img_w
            else:
                draw_x = round(self.x)
            draw_y = round(self.y) + self.h - img_h
        else:
            # 普通动画：图片底部对齐碰撞箱底部、水平居中
            draw_x = round(self.x) - (img_w - self.w) // 2
            draw_y = round(self.y) + self.h - img_h
            if self.facing < 0:
                img = pygame.transform.flip(img, True, False)
        self.last_draw_pos = (draw_x, draw_y)
        screen.blit(img, (draw_x, draw_y))
