"""
core/game.py — 游戏场景

* 固定 Room 摄像机：一个 Room 对应一个屏幕，无自由滚动
* 出口（Room.exits）：触碰后切换到目标房间，保留跨房间的存档点
* 终点（Room.end）：end.png，碰到即通关，播放 win.gif 演出
* 尖刺：碰撞遮罩由尖刺图片的 alpha 通道逐像素生成（像素级精确，贴合可见形状）
* 藤蔓：非梯子，从正侧面碰撞进入 VINE_CLING；Shift+左/右 攀爬、反方向脱离、
  无输入下滑；不刷新跳跃次数；不用普通平台碰撞逻辑
* Checkpoint：接触后按 S 存档（checkpoint_1.png），死亡回最近存档点
* 死亡演出结束后停留在死亡画面，按 R 自行复活（不自动复活、无提示文字）
* F1：开关碰撞箱可视化调试（Kid/固体/尖刺/藤蔓/存档/出口/终点）
"""

import copy

import pygame

import config
from core import save
from core import settings
from core.bgrender import render_background
from core.effects import DeathFX, OverlayFX, StarFX
from core.input import InputState
from core.sound import MusicManager, SoundManager
from core.textures import texture_for
from entities.bullet import Bullet
from entities.kid import Kid
from entities.water import Water
from levels.rooms_registry import load_room


def _mask_hits_rect(mask, mx, my, rect):
    """碰撞遮罩（左上角在 mx,my）与矩形 rect 是否有实心像素相交。

    只扫描相交区域内的像素，对 4×4 这种小 mask 是常数开销。
    子弹坐标是 float（x += hsp），先取整到像素。
    """
    mw, mh = mask.get_size()
    mx, my = int(mx), int(my)
    x0, x1 = max(mx, rect.left), min(mx + mw, rect.right)
    y0, y1 = max(my, rect.top), min(my + mh, rect.bottom)
    for x in range(x0, x1):
        for y in range(y0, y1):
            if mask.get_at((x - mx, y - my)):
                return True
    return False


class PathMover:
    """路径节点移动器：与节点重合的元素沿折线轨迹**往复循环**移动。

    轨迹 = [节点原点] + 编辑器画的 path 点（像素坐标，吸附格子）。
    移动方式：t 沿折线累计（speed 像素/帧），到终点折返、回原点再折返
    （往复）。trigger == "touch" 时玩家碰到节点 32×32 区域才激活。
    """

    def __init__(self, node, origin):
        self.node = node
        self.origin = origin                  # 节点原点（元素起始位置基准）
        self.pts = [origin] + [tuple(p) for p in node.get("path", [])]
        self.speed = float(node.get("speed") or 1.0)
        self.trigger = node.get("trigger", "auto")
        self.active = (self.trigger == "auto")
        self.t = 0.0                          # 已沿路径走的距离（px）
        self.dir = 1                          # 1 正向 / -1 反向（往复）
        self.total = self._polyline_len()
        self.prev_delta = (0.0, 0.0)          # 上一帧累计位移（算本帧步进用）
        self.origin_rect = pygame.Rect(origin[0], origin[1],
                                       config.PATH_NODE_SIZE,
                                       config.PATH_NODE_SIZE)
        self.elements = []                    # [(kind, key), ...]
        self.originals = []                   # [元素原始左上角 (px,py), ...]

    def _polyline_len(self):
        total = 0.0
        for a, b in zip(self.pts, self.pts[1:]):
            total += ((b[0] - a[0]) ** 2 + (b[1] - a[1]) ** 2) ** 0.5
        return total

    def current_point(self):
        """沿路径行走 t 距离后的坐标（像素，float）。"""
        if self.total <= 0:
            return self.pts[0]
        t = self.t
        for a, b in zip(self.pts, self.pts[1:]):
            seg = ((b[0] - a[0]) ** 2 + (b[1] - a[1]) ** 2) ** 0.5
            if seg == 0:
                continue
            if t <= seg:
                frac = t / seg
                return (a[0] + (b[0] - a[0]) * frac,
                        a[1] + (b[1] - a[1]) * frac)
            t -= seg
        return self.pts[-1]

    def advance(self):
        """推进 t：到终点/原点折返（往复循环）。"""
        if not self.active or self.total <= 0:
            return
        self.t += self.speed * self.dir
        if self.t >= self.total:
            self.t = self.total - (self.t - self.total)
            self.dir = -1
        elif self.t <= 0:
            self.t = -self.t
            self.dir = 1

    def delta(self):
        """当前位移（相对原点）。"""
        cx, cy = self.current_point()
        return (cx - self.origin[0], cy - self.origin[1])


class GameScene:
    def __init__(self, assets, room=None, sounds=None):
        self.assets = assets
        self.sounds = sounds if sounds is not None else SoundManager()
        self.music = MusicManager()     # 房间背景音乐（死亡淡出/复活续播）
        self.music_default = settings.get_default_bgm()   # 默认 BGM（无 bgm 的房间用）
        self.room_registry = load_room
        self.input = InputState()

        self._pristine_plus_jumps = {}   # room_name -> 初始跳跃球列表（死亡恢复用）

        self.room = room if room is not None else self.room_registry("room001")
        self.room = copy.deepcopy(self.room)      # 场景独占副本（路径移动会改位置）
        self._room_backup = copy.deepcopy(self.room)   # 死亡重置回原位的基准
        self._moved_mini = []                     # 被路径挂载的小刺（像素运行时列表）
        self._movers = []                         # 路径节点移动器
        self._snapshot_room(self.room)   # 记录当前房间的初始跳跃球
        self.solids = self.room.solid_rects()
        self.end_rect = self._build_end_rect()
        self.free_end_rect = self._build_free_end_rect()
        self.platforms = self._build_platform_rects()   # 单向平台矩形列表（32×16）
        self.vines = self.room.vines       # (tx,ty) -> "left"/"right" 攀爬面
        self.free_vines = self.room.free_vines   # 细网格像素定位藤蔓 (px,py)
        self._vine_cell = None             # 当前攀附的藤蔓格 (tx,ty) 或像素 (px,py)
        self._vine_reenter_block = 0       # 脱离后"再吸附"冷却帧数（防滑到底反复吸附抽搐）
        self.play_frames = 0               # 游玩帧数（窗口标题显示游玩时长）
        self.death_count = 0               # 死亡次数（窗口标题显示）
        self.vine_barriers = self._build_vine_barriers()   # 攀爬面边缘竖线的实体碰撞
        self.water_tiles = []              # [(water_obj, rect), ...] 水实体及其矩形
        self._build_water_tiles()         # 构建水实体列表
        self.in_water = None               # 当前所在的水实体（water_type 或 None）
        self.bg_surface = self._build_bg_surface()   # 背景图（None=纯色 bg_color）
        self.music.play(self.room.bgm or self.music_default)   # 本房间 BGM（无则默认）
        self._build_path_movers()    # 路径节点：挂载重合元素（死亡重置用备份）

        # Kid 的碰撞遮罩：与碰撞箱同尺寸的全实心矩形（每次触碰检测复用）
        self._kid_mask = pygame.mask.Mask((config.KID_WIDTH, config.KID_HEIGHT))
        self._kid_mask.fill()

        # 尖刺和小刺的碰撞遮罩
        self.spike_masks = self._build_spike_masks()
        self.mini_spike_masks = self._build_mini_spike_masks()

        # 存档点 = 出生点/最近保存的 Checkpoint（含所在房间，支持跨房复活）
        self.spawn_pos = self.room.start
        self.spawn_room = self.room.name
        self.active_checkpoint = None     # (room_name, tx, ty) 或 None
        self.has_save_file = False        # 磁盘上是否有有效存档（关闭游戏再开可继续）
        self._save_cooldown = 0           # 存档冷却（重复存档的 CD 计时）
        self._saved_max_jumps = None      # 存档记录的"最多跳跃次数"（几段跳）

        self.kid = Kid(*self.room.start, assets, self.sounds)
        self._apply_saved_checkpoint()   # 有存档则从最近存档的 Checkpoint 继续
        self.death_fx = DeathFX(assets)
        self.win_fx = OverlayFX(assets, "win",
                                config.WIN_FRAMES,
                                config.WIN_OVERLAY_ALPHA,
                                config.WIN_VEIL_ALPHA,
                                config.WIN_FADE_STEP,
                                config.WIN_VEIL_STEP)
        self.state = "play"   # play / dying / dead / won
        self.show_hitboxes = False   # F1/H/Tab：碰撞箱轮廓（默认隐藏）
        self.show_params = False     # F2：独立小窗口「隐藏参数」面板（默认隐藏，窗口由 App 管理）
        self.debug_water = False     # 水调试信息开关
        self.bullets = []            # Z 射击的子弹（场景级实体）
        self.star_fx = []            # 跳跃星星触碰特效（放大淡出）
        self._prev_star_cells = set()  # 上一帧重叠的星星格 (tx,ty,level)（边沿触发用）

    def reload_room(self, room, preserve_spawn=False):
        """载入一个房间。preserve_spawn=True 时保留跨房间存档点。

        跳跃星星改的最大跳跃次数在切房间时**保留**（星星不可消耗、玩家带段数走），
        只有死亡/重生走 kid.reset() 才重置回默认 2。reload_room 内部也会调
        kid.reset()，所以先记住旧值再恢复。"""
        prev_max = self.kid.max_jumps      # 切房间保留星星改的最大跳跃次数
        self.room = copy.deepcopy(room)    # 场景独占副本
        self._room_backup = copy.deepcopy(self.room)
        self._moved_mini = []
        self._snapshot_room(self.room)
        self.solids = self.room.solid_rects()
        self.spike_masks = self._build_spike_masks()
        self.mini_spike_masks = self._build_mini_spike_masks()
        self.end_rect = self._build_end_rect()
        self.free_end_rect = self._build_free_end_rect()
        self.platforms = self._build_platform_rects()   # 重新加载平台
        # 注意：必须从**场景副本** self.room 取别名——路径移动器会改副本里的
        # free_vines 键，绘制/攀爬若读原房间（缓存）就会看到"藤蔓不动"。
        self.vines = self.room.vines
        self.free_vines = self.room.free_vines
        self._vine_cell = None
        self.vine_barriers = self._build_vine_barriers()
        self._build_water_tiles()
        self.in_water = None
        self.bg_surface = self._build_bg_surface()   # 切房同步背景
        self.music_default = settings.get_default_bgm()   # 每次切房重读默认（编辑器可能改过）
        self.music.play(room.bgm or self.music_default)  # 切房同步 BGM（无则默认，同歌保持）
        self._build_path_movers()    # 重建路径移动器（新房间从头开始）
        if not preserve_spawn:
            self.spawn_pos = room.start
            self.spawn_room = room.name
            self.active_checkpoint = None
        self.kid.reset(*room.start)
        self.kid.max_jumps = prev_max      # 恢复星星改的段数（死亡才由 kid.reset 重置）
        self.bullets = []
        self.star_fx = []
        self._prev_star_cells = set()
        self.state = "play"

    # ---- 房间消耗状态（死亡重置） ----
    def _snapshot_room(self, room):
        """记录某房间首次载入时的初始跳跃球；重复载入不覆盖。

        这样即使房间对象被缓存、中途吃掉了球，也能保存一份"原样"清单，
        死亡时按房间名恢复。切换房间回来不重置（切房不复活已吃物）。
        """
        if room.name not in self._pristine_plus_jumps:
            self._pristine_plus_jumps[room.name] = (
                list(room.plus_jumps), list(room.free_plus_jumps))

    def _restore_room_state(self):
        """死亡复活时重置当前房间的消耗性状态：被吃掉的跳跃球恢复原样。"""
        pristine = self._pristine_plus_jumps.get(self.room.name)
        if pristine is not None:
            self.room.plus_jumps = list(pristine[0])
            self.room.free_plus_jumps = list(pristine[1])

    # ---- 路径节点：挂载 / 推进 / 重置 ----
    def _build_path_movers(self):
        """从 room.path_nodes 构建移动器：与节点 32×32 区重合的元素全部挂上。

        挂载时把格子元素转成像素结构（可平滑移动）；小刺转运行时 _moved_mini。
        """
        self._movers = []
        if not self.room.path_nodes:
            return
        for node in self.room.path_nodes:
            mover = PathMover(node, tuple(node["pos"]))
            self._attach_overlapping(mover)
            if mover.elements:
                self._movers.append(mover)
        if self._movers:
            self._rebuild_collision_structures()

    def _attach_overlapping(self, mover):
        """把与节点区重合的元素挂到 mover 上（记录原始位置，格子→像素转换）。"""
        room = self.room
        T = config.TILE_SIZE
        nrect = mover.origin_rect

        def attach_dict(d, kind, rect):
            for key in [k for k in d]:
                px, py = key[0], key[1]
                r = pygame.Rect(px, py, rect[0], rect[1])
                if nrect.colliderect(r):
                    mover.elements.append((kind, key))
                    mover.originals.append((px, py))

        # 格子砖块 → 转像素 free_tile（可平滑移动）
        for (tx, ty) in [k for k in room.tiles]:
            r = pygame.Rect(tx * T, ty * T, T, T)
            if nrect.colliderect(r):
                room.free_tiles[(tx * T, ty * T)] = room.tiles.pop((tx, ty))
        attach_dict(room.free_tiles, "free_tile", (T, T))
        attach_dict(room.small_tiles, "small_tile", (16, 16))
        # 平台（记录下标）
        for i, (px, py) in enumerate(room.platforms):
            if nrect.colliderect(pygame.Rect(px, py, 32, 16)):
                mover.elements.append(("platform", i))
                mover.originals.append((px, py))
        # 尖刺：格子 → free
        for (tx, ty) in [k for k in room.spikes]:
            r = pygame.Rect(tx * T, ty * T, T, T)
            if nrect.colliderect(r):
                room.free_spikes[(tx * T, ty * T)] = room.spikes.pop((tx, ty))
        attach_dict(room.free_spikes, "free_spike", (T, T))
        # 小刺 → 运行时像素列表
        for (tx, ty, quad) in [k for k in room.mini_spikes]:
            qx = tx * T + (T // 2 if quad in (1, 3) else 0)
            qy = ty * T + (T // 2 if quad in (2, 3) else 0)
            if nrect.colliderect(pygame.Rect(qx, qy, 16, 16)):
                d = room.mini_spikes.pop((tx, ty, quad))
                self._moved_mini.append([qx, qy, d])
                mover.elements.append(("mini", len(self._moved_mini) - 1))
                mover.originals.append((qx, qy))
        # 藤蔓：格子 → free
        for (tx, ty) in [k for k in room.vines]:
            r = pygame.Rect(tx * T, ty * T, T, T)
            if nrect.colliderect(r):
                room.free_vines[(tx * T, ty * T)] = room.vines.pop((tx, ty))
        attach_dict(room.free_vines, "free_vine", (T, T))
        # 水：格子 → free
        for (tx, ty) in [k for k in room.water]:
            r = pygame.Rect(tx * T, ty * T, T, T)
            if nrect.colliderect(r):
                room.free_water[(tx * T, ty * T)] = room.water.pop((tx, ty))
        attach_dict(room.free_water, "free_water", (T, T))
        # Checkpoint：格子 → free（记录下标）
        for (tx, ty) in list(room.checkpoints):
            r = pygame.Rect(tx * T, ty * T, T, T)
            if nrect.colliderect(r):
                room.checkpoints.remove((tx, ty))
                room.free_checkpoints.append((tx * T, ty * T))
                mover.elements.append(("free_cp", len(room.free_checkpoints) - 1))
                mover.originals.append((tx * T, ty * T))
        for i, (px, py) in enumerate(room.free_checkpoints):
            if nrect.colliderect(pygame.Rect(px, py, T, T)):
                mover.elements.append(("free_cp", i))
                mover.originals.append((px, py))
        # 出口：格子 → free
        for e in list(room.exits):
            tx, ty = e["tile"]
            if nrect.colliderect(pygame.Rect(tx * T, ty * T, T, T)):
                room.exits.remove(e)
                room.free_exits.append({"pos": (tx * T, ty * T),
                                        "target": e["target"]})
                mover.elements.append(("free_exit", len(room.free_exits) - 1))
                mover.originals.append((tx * T, ty * T))
        for i, e in enumerate(room.free_exits):
            px, py = e["pos"]
            if nrect.colliderect(pygame.Rect(px, py, T, T)):
                mover.elements.append(("free_exit", i))
                mover.originals.append((px, py))
        # 终点
        if room.end is not None:
            tx, ty = room.end
            if nrect.colliderect(pygame.Rect(tx * T, ty * T, T, T)):
                room.end = None
                room.free_end = (tx * T, ty * T)
                mover.elements.append(("free_end", 0))
                mover.originals.append((tx * T, ty * T))
        if room.free_end is not None:
            px, py = room.free_end
            if nrect.colliderect(pygame.Rect(px, py, T, T)):
                mover.elements.append(("free_end", 0))
                mover.originals.append((px, py))
        # 跳跃球：格子 → free
        for (tx, ty) in list(room.plus_jumps):
            r = pygame.Rect(tx * T, ty * T, T, T)
            if nrect.colliderect(r):
                room.plus_jumps.remove((tx, ty))
                room.free_plus_jumps.append((tx * T, ty * T))
                mover.elements.append(("free_pj", len(room.free_plus_jumps) - 1))
                mover.originals.append((tx * T, ty * T))
        for i, (px, py) in enumerate(room.free_plus_jumps):
            if nrect.colliderect(pygame.Rect(px, py, T, T)):
                mover.elements.append(("free_pj", i))
                mover.originals.append((px, py))
        # 星星：格子 → free
        for (tx, ty, lv) in list(room.stars):
            r = pygame.Rect(tx * T, ty * T, T, T)
            if nrect.colliderect(r):
                room.stars.remove((tx, ty, lv))
                room.free_stars.append((tx * T, ty * T, lv))
                mover.elements.append(("free_star", len(room.free_stars) - 1))
                mover.originals.append((tx * T, ty * T))
        for i, (px, py, lv) in enumerate(room.free_stars):
            if nrect.colliderect(pygame.Rect(px, py, T, T)):
                mover.elements.append(("free_star", i))
                mover.originals.append((px, py))

    def _update_path_movers(self):
        """推进路径移动器并应用位移（含载人）；有移动则重建碰撞结构。"""
        if not self._movers:
            return
        room = self.room
        moved_any = False
        kid = self.kid
        carried = False
        for mover in self._movers:
            if mover.trigger == "touch" and not mover.active:
                # 碰到节点 32×32 区（含站上格顶）→ 开动
                touch_rect = mover.origin_rect.inflate(0, 6)
                if kid.rect.colliderect(touch_rect):
                    mover.active = True
            mover.advance()
            dx, dy = mover.delta()            # 累计位移（元素定位用：原位置+累计）
            step_x, step_y = dx - mover.prev_delta[0], dy - mover.prev_delta[1]
            mover.prev_delta = (dx, dy)       # 本帧步进（载人用：只加这一步）
            if mover.active and (step_x, step_y) != (0.0, 0.0):
                moved_any = True
            for i, ((kind, key), (ox, oy)) in enumerate(
                    zip(mover.elements, mover.originals)):
                nx, ny = round(ox + dx), round(oy + dy)
                cur_rect = None
                if kind in ("free_tile", "small_tile", "free_spike",
                            "free_vine", "free_water"):
                    d = {"free_tile": room.free_tiles,
                         "small_tile": room.small_tiles,
                         "free_spike": room.free_spikes,
                         "free_vine": room.free_vines,
                         "free_water": room.free_water}[kind]
                    # 键即位置：把"当前键"挪到新位置，并记录新键（下一帧用）
                    if key in d and key != (nx, ny):
                        d[(nx, ny)] = d.pop(key)
                    mover.elements[i] = (kind, (nx, ny))
                    size = 16 if kind == "small_tile" else config.TILE_SIZE
                    cur_rect = pygame.Rect(nx, ny, size, size)
                    # 吸附中的藤蔓：吸附格跟随移动，Kid 被带着走（骑乘）
                    if kind == "free_vine" and self._vine_cell == key:
                        self._vine_cell = (nx, ny)
                        if not carried:
                            kid.x += step_x
                            kid.y += step_y
                            carried = True
                elif kind == "platform":
                    room.platforms[key] = (nx, ny)
                    cur_rect = pygame.Rect(nx, ny, 32, 16)
                elif kind == "mini":
                    self._moved_mini[key][0] = nx
                    self._moved_mini[key][1] = ny
                    cur_rect = pygame.Rect(nx, ny, 16, 16)
                elif kind == "free_cp":
                    room.free_checkpoints[key] = (nx, ny)
                    cur_rect = pygame.Rect(nx, ny, config.TILE_SIZE,
                                           config.TILE_SIZE)
                elif kind == "free_exit":
                    room.free_exits[key]["pos"] = (nx, ny)
                    cur_rect = pygame.Rect(nx, ny, config.TILE_SIZE,
                                           config.TILE_SIZE)
                elif kind == "free_end":
                    room.free_end = (nx, ny)
                    cur_rect = pygame.Rect(nx, ny, config.TILE_SIZE,
                                           config.TILE_SIZE)
                elif kind == "free_pj":
                    room.free_plus_jumps[key] = (nx, ny)
                    cur_rect = pygame.Rect(nx, ny, config.TILE_SIZE,
                                           config.TILE_SIZE)
                elif kind == "free_star":
                    room.free_stars[key] = (nx, ny,
                                            room.free_stars[key][2])
                    cur_rect = pygame.Rect(nx, ny, config.TILE_SIZE,
                                           config.TILE_SIZE)
                # 载人：站在该元素顶上的 Kid 跟着走（只加**本帧**位移，不瞬移）
                if (cur_rect is not None and not carried and kid.on_ground
                        and abs(kid.rect.bottom - cur_rect.top) <= 6
                        and kid.rect.right > cur_rect.left
                        and kid.rect.left < cur_rect.right):
                    kid.x += step_x
                    kid.y += step_y
                    carried = True
        if carried:
            self._resolve_kid_overlap()   # 载人后推出固体：墙挡住，不穿墙
        if moved_any:
            self._rebuild_collision_structures()

    def _resolve_kid_overlap(self):
        """载人把 Kid 挪进固体后，沿穿透最小的轴推出（防止穿墙/陷入地板）。"""
        kid = self.kid
        for _ in range(3):
            r = kid.rect
            hit = next((s for s in self.solids if r.colliderect(s)), None)
            if hit is None:
                return
            dx_right = hit.right - r.left     # 向左推的距离
            dx_left = r.right - hit.left      # 向右推的距离
            dy_bottom = hit.bottom - r.top    # 向上推的距离
            dy_top = r.bottom - hit.top       # 向下推的距离
            choice = min(dx_right, dx_left, dy_bottom, dy_top)
            if choice in (dx_right, dx_left):
                kid.x += dx_right if choice == dx_right else -dx_left
            else:
                kid.y += dy_bottom if choice == dy_bottom else -dy_top

    def _rebuild_collision_structures(self):
        """移动后重建全部预计算碰撞结构（房间小，逐帧重建开销可忽略）。"""
        self.solids = self.room.solid_rects()
        self.platforms = self._build_platform_rects()
        self.spike_masks = self._build_spike_masks()
        self.mini_spike_masks = self._build_mini_spike_masks()
        self._build_water_tiles()
        self.end_rect = self._build_end_rect()
        self.free_end_rect = self._build_free_end_rect()

    def _reset_path_movers(self):
        """死亡重置：元素全部回原位（从备份恢复房间并重建移动器）。"""
        if not self._movers and not self._moved_mini:
            return
        self.room = copy.deepcopy(self._room_backup)
        # 重新绑定别名：vines/free_vines 必须指向**新房间**的 dict，
        # 否则绘制/攀爬读到旧 dict（藤蔓定格在死前位置 = "停止移动"）
        self.vines = self.room.vines
        self.free_vines = self.room.free_vines
        self._moved_mini = []
        self._build_path_movers()
        self._rebuild_collision_structures()

    # ---- 碰撞区构建 ----
    def _build_spike_masks(self):
        """尖刺碰撞区 = 由图片 alpha 逐像素生成的 mask（精确贴合可见形状）。

        每个元素 (mask, ox, oy)：ox/oy 为该尖刺 Tile 的左上角绝对坐标。
        """
        T = config.TILE_SIZE
        masks = []
        for (tx, ty), direction in self.room.spikes.items():
            mask = self.assets.spike_mask(direction)
            masks.append((mask, tx * T, ty * T))
        # 细网格像素定位尖刺：贴图左上角即像素坐标
        for (px, py), direction in self.room.free_spikes.items():
            mask = self.assets.spike_mask(direction)
            masks.append((mask, px, py))
        return masks

    def _build_mini_spike_masks(self):
        """小刺碰撞区 = 由图片 alpha 逐像素生成的 mask（精确贴合可见形状）。

        每个元素 (mask, ox, oy)：ox/oy 为该小刺 Tile 的左上角绝对坐标。
        quad 值决定了 16×16 小刺在 32×32 空间中的位置：
        0=左上, 1=右上, 2=左下, 3=右下
        """
        T = config.TILE_SIZE
        Q = T // 2  # 16px
        masks = []
        for (tx, ty, quad), direction in self.room.mini_spikes.items():
            mask = self.assets.mini_spike_mask(direction)
            # 计算小刺的实际位置
            base_x = tx * T
            base_y = ty * T
            if quad == 0:  # 左上
                x, y = base_x, base_y
            elif quad == 1:  # 右上
                x, y = base_x + Q, base_y
            elif quad == 2:  # 左下
                x, y = base_x, base_y + Q
            else:  # quad == 3, 右下
                x, y = base_x + Q, base_y + Q
            masks.append((mask, x, y))
        # 被路径节点挂载的小刺（运行时像素列表，随移动更新）
        for (x, y, direction) in self._moved_mini:
            masks.append((self.assets.mini_spike_mask(direction), x, y))
        return masks

    def _build_end_rect(self):
        if self.room.end is None:
            return None
        tx, ty = self.room.end
        T = config.TILE_SIZE
        return pygame.Rect(tx * T, ty * T, T, T)

    def _build_free_end_rect(self):
        """细网格像素定位终点的碰撞矩形（32×32）。"""
        if self.room.free_end is None:
            return None
        px, py = self.room.free_end
        T = config.TILE_SIZE
        return pygame.Rect(px, py, T, T)

    def _build_platform_rects(self):
        """构建单向平台的碰撞矩形（32×16）。"""
        PLATFORM_WIDTH = 32
        PLATFORM_HEIGHT = 16
        rects = []
        for px, py in self.room.platforms:
            # 平台矩形：左上角坐标，32×16 尺寸
            rects.append(pygame.Rect(px, py, PLATFORM_WIDTH, PLATFORM_HEIGHT))
        return rects

    def _build_vine_barriers(self):
        """藤蔓攀爬面竖线（1px 宽薄矩形）——仅供测试/参考（physics_test PASS 28）。

        真实游戏里藤蔓是**单向通道**：攀爬面竖线不再作为无方向实体塞进
        solids（否则从非攀爬面一侧也过不去）。进入吸附由 `_try_enter_vine`
        按"攀爬面边缘 ±4px + 来向"触发（tengwan_right 只挡从右来的 Kid，
        tengwan_left 只挡从左来的 Kid，另一侧可自由穿过）。
        """
        T = config.TILE_SIZE
        bars = []
        for (tx, ty), facing in self.vines.items():
            tile = pygame.Rect(tx * T, ty * T, T, T)
            if facing == "right":
                bars.append(pygame.Rect(tile.right - 1, tile.top, 1, T))
            else:
                bars.append(pygame.Rect(tile.left, tile.top, 1, T))
        for (px, py), facing in self.free_vines.items():
            tile = pygame.Rect(px, py, T, T)
            if facing == "right":
                bars.append(pygame.Rect(tile.right - 1, tile.top, 1, T))
            else:
                bars.append(pygame.Rect(tile.left, tile.top, 1, T))
        return bars

    def _build_water_tiles(self):
        """构建水实体列表，包含 Water 对象和碰撞矩形。"""
        self.water_tiles = []
        T = config.TILE_SIZE
        for (tx, ty), water_type in self.room.water.items():
            water = Water(tx * T, ty * T, water_type)
            self.water_tiles.append((water, water.rect))
        # 细网格像素定位水
        for (px, py), water_type in self.room.free_water.items():
            water = Water(px, py, water_type)
            self.water_tiles.append((water, water.rect))

    def _build_bg_surface(self):
        """按房间的 bg_mode 生成 800×608 背景；无图/加载失败返回 None。"""
        img = self.assets.background(self.room.bg_image) if self.room.bg_image \
            else None
        if img is None:
            return None
        return render_background(img, self.room.bg_color, self.room.bg_mode,
                                 self.room.bg_zoom, self.room.bg_offset)

    def _check_water_collision(self):
        """检查玩家是否在水域中，返回水类型或 None。"""
        kid_rect = self.kid.rect
        for water, water_rect in self.water_tiles:
            if kid_rect.colliderect(water_rect):
                return water.water_type
        return None

    # ---- 触发检测 ----
    def _touches_spike(self):
        """Kid 碟撞箱（实心 mask）与任一尖刺图片的 alpha mask 是否重叠。

        偏移量 = 尖刺 Tile 左上角相对 Kid 左上角的位置（mask.overlap 的
        offset 是对方在自身坐标系中的位置），逐像素精确判断。
        """
        r = self.kid.rect
        for mask, ox, oy in self.spike_masks:
            if self._kid_mask.overlap(mask, (ox - r.left, oy - r.top)):
                return True
        return False

    def _touches_mini_spike(self):
        """Kid 碰撞箱（实心 mask）与任一小刺图片的 alpha mask 是否重叠。

        小刺是16×16像素，放在32×32的tile网格中，碰撞检测使用精确的像素判定。
        """
        r = self.kid.rect
        for mask, ox, oy in self.mini_spike_masks:
            if self._kid_mask.overlap(mask, (ox - r.left, oy - r.top)):
                return True
        return False

    def _touches_end(self):
        if self.end_rect is not None and self.kid.rect.colliderect(self.end_rect):
            return True
        return (self.free_end_rect is not None
                and self.kid.rect.colliderect(self.free_end_rect))

    def _touches_plus_jump(self):
        """Kid 碰撞箱与跳跃球是否重叠（圆形碰撞检测）。

        球半径 = config.PLUS_JUMP_RADIUS（默认 8，直径 16，比整格 32 小一半）。
        """
        T = config.TILE_SIZE
        kid_rect = self.kid.rect
        kid_center = (kid_rect.centerx, kid_rect.centery)
        kid_radius = min(kid_rect.width, kid_rect.height) // 2

        for (tx, ty) in self.room.plus_jumps:
            # 跳跃球中心坐标
            ball_center = (tx * T + T // 2, ty * T + T // 2)
            # 跳跃球碰撞半径（缩小，需更贴近才触发）
            ball_radius = config.PLUS_JUMP_RADIUS

            # 计算两个圆心之间的距离
            dx = kid_center[0] - ball_center[0]
            dy = kid_center[1] - ball_center[1]
            distance = (dx * dx + dy * dy) ** 0.5

            # 如果距离小于两个半径之和，则发生碰撞
            if distance < kid_radius + ball_radius:
                return True
        for (px, py) in self.room.free_plus_jumps:
            ball_center = (px + T // 2, py + T // 2)
            ball_radius = config.PLUS_JUMP_RADIUS
            dx = kid_center[0] - ball_center[0]
            dy = kid_center[1] - ball_center[1]
            if (dx * dx + dy * dy) ** 0.5 < kid_radius + ball_radius:
                return True
        return False

    def _touches_exit(self):
        r = self.kid.rect
        for ex in self.room.exits:
            tx, ty = ex["tile"]
            tile = pygame.Rect(tx * config.TILE_SIZE, ty * config.TILE_SIZE,
                               config.TILE_SIZE, config.TILE_SIZE)
            if r.colliderect(tile):
                return ex["target"]
        for ex in self.room.free_exits:
            px, py = ex["pos"]
            tile = pygame.Rect(px, py, config.TILE_SIZE, config.TILE_SIZE)
            if r.colliderect(tile):
                return ex["target"]
        return None

    def _checkpoint_touch_at(self, rect, v_inflate=0):
        """给定矩形触碰的 checkpoint（格子坐标或像素坐标）；未触碰返回 None。

        触发区 = **32×32 整格**（不再上下扩展）。站上格顶（Kid 底边贴格顶线）
        也能触发（bottom >= tile.top，含贴线）。返回的键 = 该 checkpoint 的
        存储键（格子 (tx,ty) 或像素 (px,py)），供 _do_save 换算复活点。"""
        T = config.TILE_SIZE
        for (tx, ty) in self.room.checkpoints:
            tile = pygame.Rect(tx * T, ty * T, T, T)
            if v_inflate:
                tile = tile.inflate(0, v_inflate)
            if (rect.right > tile.left and rect.left < tile.right
                    and rect.bottom >= tile.top and rect.top < tile.bottom):
                return (tx, ty)
        for (px, py) in self.room.free_checkpoints:
            tile = pygame.Rect(px, py, T, T)
            if v_inflate:
                tile = tile.inflate(0, v_inflate)
            if (rect.right > tile.left and rect.left < tile.right
                    and rect.bottom >= tile.top and rect.top < tile.bottom):
                return (px, py)
        return None

    def _checkpoint_touch(self):
        """Kid 触碰的 checkpoint 网格坐标；未触碰返回 None。"""
        return self._checkpoint_touch_at(self.kid.rect)

    def _save_checkpoint_at(self, bullet):
        """子弹（像素级 mask）触碰 checkpoint 即存档。"""
        T = config.TILE_SIZE
        for (tx, ty) in self.room.checkpoints:
            tile = pygame.Rect(tx * T, ty * T, T, T).inflate(
                0, config.BULLET_CHECKPOINT_INFLATE)
            if _mask_hits_rect(bullet.mask, bullet.x, bullet.y, tile):
                self._do_save((tx, ty))
                return
        for (px, py) in self.room.free_checkpoints:
            tile = pygame.Rect(px, py, T, T).inflate(
                0, config.BULLET_CHECKPOINT_INFLATE)
            if _mask_hits_rect(bullet.mask, bullet.x, bullet.y, tile):
                self._do_save((px, py))
                return

    def _save_checkpoint(self):
        cp = self._checkpoint_touch()
        if cp is not None:
            self._do_save(cp)

    def _do_save(self, cp):
        """存档（Kid 按 S / 子弹碰到 checkpoint 共用）。

        可**重复存档**（同一 checkpoint 也能再存），但受
        SAVE_COOLDOWN_FRAMES 冷却限制：CD 内再触发无效（静默），
        CD 过后可再次存档。
        """
        if self._save_cooldown > 0:
            return          # 冷却中：本次存档无效
        T = config.TILE_SIZE
        # 统一换算成像素坐标：格子 checkpoint → (tx*T, ty*T)，像素的直接用
        if cp in self.room.checkpoints:
            px, py = cp[0] * T, cp[1] * T
        else:
            px, py = cp
        new_cp = (self.room.name, px, py)
        self.active_checkpoint = new_cp
        self._save_cooldown = config.SAVE_COOLDOWN_FRAMES
        self.sounds.play("save")
        # 复活点 = 站在 checkpoint 格顶，水平居中
        self.spawn_pos = (float(px + (T - config.KID_WIDTH) // 2),
                          float(py - config.KID_HEIGHT))
        self.spawn_room = self.room.name
        # 持久化到磁盘：关闭游戏再开，从该 Checkpoint 继续；
        # 同时保存跳跃星星改的"最多跳跃次数"（几段跳）
        self.has_save_file = True
        self._saved_max_jumps = self.kid.max_jumps   # 死亡复活也要恢复（内存同步）
        save.write_save(self.spawn_room, self.spawn_pos,
                        self.active_checkpoint, self.kid.max_jumps)

    def _apply_saved_checkpoint(self):
        """启动时读取存档：有有效存档则出生点/复活点设为最近存档的 Checkpoint，
        并恢复存档时跳跃星星改的"最多跳跃次数"（几段跳）。"""
        data = save.load_save()
        if not data:
            return
        spawn_room_name = data.get("spawn_room")
        if self.room_registry(spawn_room_name) is None:
            print("[save] 存档房间不存在（地图可能已修改），回默认出生点")
            return

        # 存档记录的段数（旧存档无此字段 → 默认 2）
        mj = data.get("max_jumps")
        self._saved_max_jumps = mj if isinstance(mj, int) and mj >= 1 else None

        def _norm_cp(cp):
            """存档里的 checkpoint → (room, px, py) 像素坐标。

            旧存档存的是格子坐标 (tx,ty)；新存档直接存像素。小坐标判旧格式。
            """
            if not (isinstance(cp, list) and len(cp) == 3):
                return None
            room_name, x, y = cp[0], cp[1], cp[2]
            if not isinstance(room_name, str) or not isinstance(x, (int, float)) \
                    or not isinstance(y, (int, float)):
                return None
            if x < config.GRID_COLS and y < config.GRID_ROWS:
                x, y = x * config.TILE_SIZE, y * config.TILE_SIZE   # 旧格式换算
            return (room_name, int(x), int(y))

        # 如果存档点在当前房间，只重置位置
        if spawn_room_name == self.room.name:
            cp = data.get("active_checkpoint")
            pos = data.get("spawn_pos")
            if not (isinstance(cp, list) and len(cp) == 3
                    and isinstance(pos, list) and len(pos) == 2):
                return
            norm = _norm_cp(cp)
            if norm is None:
                return
            self.spawn_room = spawn_room_name
            self.spawn_pos = (float(pos[0]), float(pos[1]))
            self.active_checkpoint = norm
            self.has_save_file = True
            self.kid.reset(*self.spawn_pos)
            if self._saved_max_jumps is not None:
                self.kid.max_jumps = self._saved_max_jumps   # 恢复几段跳
            print(f"[save] 已从存档继续：{self.spawn_room} @ {self.spawn_pos[0]:.0f},{self.spawn_pos[1]:.0f}"
                  f"（{self.kid.max_jumps} 段跳）")
        else:
            # 如果存档点在其他房间，切换到那个房间
            cp = data.get("active_checkpoint")
            pos = data.get("spawn_pos")
            if not (isinstance(cp, list) and len(cp) == 3
                    and isinstance(pos, list) and len(pos) == 2):
                return
            norm = _norm_cp(cp)
            if norm is None:
                return
            target_room = self.room_registry(spawn_room_name)
            if target_room:
                self.spawn_room = spawn_room_name
                self.spawn_pos = (float(pos[0]), float(pos[1]))
                self.active_checkpoint = norm
                self.has_save_file = True
                self.reload_room(target_room, preserve_spawn=True)
                self.kid.reset(*self.spawn_pos)
                if self._saved_max_jumps is not None:
                    self.kid.max_jumps = self._saved_max_jumps   # 恢复几段跳
                print(f"[save] 已从存档继续：{self.spawn_room} @ {self.spawn_pos[0]:.0f},{self.spawn_pos[1]:.0f}"
                      f"（{self.kid.max_jumps} 段跳）")
            else:
                print("[save] 存档房间不存在（地图可能已修改），回默认出生点")

    # ---- 房间切换 ----
    def _goto_exit(self, target):
        room = self.room_registry(target)
        if room is None:
            print(f"[room] 目标房间 {target} 不存在")
            return
        self.reload_room(room, preserve_spawn=True)

    # ---- 事件 ----
    def handle_event(self, event):
        if event.type != pygame.KEYDOWN:
            return
        if event.key in config.DEBUG_HITBOX_KEYS:
            self.show_hitboxes = not self.show_hitboxes
        elif event.key in config.DEBUG_PARAMS_KEYS:
            self.show_params = not self.show_params
        elif event.key == pygame.K_F3:  # F3 开关水调试
            self.debug_water = not self.debug_water
            print(f"Water debug: {self.debug_water}")
        elif event.key in config.KEYMAP["restart"]:
            # 死亡演出中/死亡画面按 R 自行复活；游戏进行中按 R 回出生点
            self._respawn()

    # ---- 逻辑 ----
    def update(self):
        self.input.begin_frame()
        self.music.update()                # 背景音乐自计时 / 复活淡入
        if self._vine_reenter_block > 0:
            self._vine_reenter_block -= 1   # 藤蔓再吸附冷却逐帧递减
        if self._save_cooldown > 0:
            self._save_cooldown -= 1        # 存档冷却逐帧递减
        if self.state == "play":
            self.play_frames += 1          # 游玩时长累计（标题栏显示）
            self._update_path_movers()   # 先推进路径移动（物体移动后再算碰撞/触发）
            if self.kid.mode == "vine":
                self._vine_update(self.input)   # VINE_CLING：独立输入/移动/下滑/脱离
            else:
                # 普通物理带上藤蔓攀爬面竖线碰撞和单向平台
                # 先检查水的状态
                was_in_water = self.in_water
                self.in_water = self._check_water_collision()
                in_water_now = self.in_water

                # 检查是否刚刚进入二段水
                if was_in_water != in_water_now and in_water_now == "second":
                    # 一碰到二段水就重置跳跃次数
                    self.kid.jump_count = 0
                    if self.debug_water:
                        print(f"Second water touched! Jump count reset to 0")

                # 检查是否进入一段水（调试用）
                if was_in_water != in_water_now and in_water_now == "first" and self.debug_water:
                    print(f"First water entered! Jump count: {self.kid.jump_count} (should NOT reset)")

                # 正常更新kid，让kid内部处理水的物理。
                # 藤蔓攀爬面是**单向通道**：不再把 vine_barriers 当无方向实体
                # 塞进 solids（否则从非攀爬面一侧也过不去）；攀附由
                # _try_enter_vine 检测"攀爬面边缘 ±4px + 来向"触发吸附。
                pre_ground = self.kid.on_ground   # 入藤前是否在地面（上一帧末的状态）
                self.kid.update(self.input, self.solids, self.platforms, in_water_now)

                # 离开可跳跃的水（一段/二段）且在**本帧**空中：水中跳跃不消耗次数，
                # 出水若不补记一段，jump_count 会一直停留在 0，在空中白得满额二段跳。
                # 出水即视为已用一段跳，空中只剩一次跳（1→2）。
                # 零段水除外：零段水里不能跳（没有白跳），次数应保留（"保留次数"语义）。
                # 用 kid.update 之后的 on_ground：本帧落地/上岸 → 不记（落地逻辑正常刷新）。
                if was_in_water in ("first", "second") and in_water_now is None \
                        and not self.kid.on_ground:
                    self.kid.jump_count = max(self.kid.jump_count, 1)
                    if self.debug_water:
                        print(f"Exited {was_in_water} water in air! Jump count -> 1 (only one air jump left)")

                self._try_enter_vine()          # 从藤蔓正侧面碰撞 → 进入 VINE_CLING
                if self.kid.mode == "vine":
                    # 入藤不刷新跳跃次数：
                    #   · 从地面入藤（pre_ground）→ 保持 update 后的已用次数不变；
                    #   · 从空中入藤 → 至少视为已用一段跳（jump = max(jump, 1)），
                    #     否则"走落台阶/平台坠落"入藤会白得两跳，出藤后 0→1→2。
                    #     这也顺带覆盖 kid.update 第11步的误判：is_grounded 向下探
                    #     1px，空中入藤脚离地不足 1px 的那一帧会把已用次数误清成 0，
                    #     max(jump,1) 把它补回 1。
                    if not pre_ground:
                        self.kid.jump_count = max(self.kid.jump_count, 1)
            if self.input.pressed("shoot"):
                self._shoot()
            self._update_bullets()
            self._update_star_fx()
            self._check_star_touches()   # 藤蔓/普通两种模式都检测（星星不挑模式）
            if self.kid.y > config.ROOM_HEIGHT or self._touches_spike() or self._touches_mini_spike():
                self._die()
            elif self._touches_end():
                self._win()
            elif self._touches_plus_jump():
                self._collect_plus_jump()
            elif (target := self._touches_exit()) is not None:
                self._goto_exit(target)
            elif self.input.pressed("save"):
                self._save_checkpoint()
        elif self.state == "dying":
            self.death_fx.update(self.solids)
            if self.death_fx.done:
                self.state = "dead"   # 停留等待按 R，不自动复活
        elif self.state == "dead":
            self.death_fx.update(self.solids)   # 头继续飞/变色/拉伸，直到按 R 复活
        elif self.state == "won":
            self.win_fx.update()
            if self.win_fx.done:
                self.state = "won"    # 停留通关画面，按 R 回出生点

    def _die(self):
        self.state = "dying"
        self.kid.alive = False
        self.death_count += 1              # 死亡次数（窗口标题显示）
        self.kid.mode = "normal"   # 脱离藤蔓
        self._vine_cell = None
        self.in_water = None       # 清水状态，避免死亡演出期间残留影响复活判定
        self.bullets = []
        self.music.fade_out_and_remember()   # BGM 淡出并记住播放位置
        self.sounds.play("death")
        self.death_fx.start(self.kid.rect, self.kid.facing)

    # ---- 射击（Z） ----
    def _shoot(self):
        """从 Kid 朝向的一侧发射一枚子弹。"""
        if len(self.bullets) >= config.BULLET_MAX:
            return
        self.bullets.append(Bullet(self.kid, self.assets))
        self.sounds.play("shoot")

    def _update_bullets(self):
        """推进所有子弹；出屏的移除，碰到 Checkpoint 的触发存档。"""
        alive = []
        for b in self.bullets:
            if b.update():
                alive.append(b)
                self._save_checkpoint_at(b)   # 子弹也能存档
        self.bullets = alive

    # ---- 藤蔓（VINE_CLING） ----
    def _vine_facing(self, cell):
        """当前藤蔓格的朝向：格子结构优先，其次像素结构（_vine_cell 可能是
        (tx,ty) 格子键或 (px,py) 像素键）。"""
        f = self.vines.get(cell)
        if f is not None:
            return f
        return self.free_vines.get(cell)

    def _vine_tile_rect(self, cell):
        """藤蔓格的 32×32 矩形：格子键 → tx*T；像素键 → 直接 px,py。"""
        T = config.TILE_SIZE
        if cell in self.vines:
            return pygame.Rect(cell[0] * T, cell[1] * T, T, T)
        return pygame.Rect(cell[0], cell[1], T, T)

    def _try_enter_vine(self):
        """NORMAL 态：Kid 从藤蔓**攀爬面**一侧接近时进入 VINE_CLING。

        藤蔓是**单向通道**：
            tengwan_right = 攀爬面在右侧 → 只从**右侧向左**撞上时吸附/阻挡
                            （右缘竖线）；从左侧经过/穿过不受阻挡。
            tengwan_left  = 攀爬面在左侧 → 只从**左侧向右**撞上时吸附/阻挡
                            （左缘竖线）；从右侧经过/穿过不受阻挡。
        攀爬面侧**不可穿过**：撞上时如果处于再吸附冷却期（普通脱离/滑到底后
        防抽搐的冷却），先**物理阻挡**（贴竖线，不穿过），冷却结束立即吸附；
        只有垂直已滑出藤蔓高度（滑到底走开）才允许穿过。
        """
        kid = self.kid
        if kid.hsp == 0.0:
            return
        T = config.TILE_SIZE
        r = kid.rect
        for (tx, ty), facing in self.vines.items():
            tile = pygame.Rect(tx * T, ty * T, T, T)
            over = kid.x + kid.w          # Kid 右缘
            under = kid.x                 # Kid 左缘
            # 必须"攀爬面竖线穿过 Kid 碰撞箱"（Kid 真正撞上竖线）且
            # **垂直与藤蔓重叠**（底 > 格顶-16 且 顶 < 格底）才处理：
            #   · 垂直不重叠（从上方远处经过/滑到底/从下方穿过）→ 直接穿过，
            #     不会出现"空气墙"。
            if facing == "right" and kid.hsp < 0 \
                    and over > tile.right and under <= tile.right \
                    and r.top < tile.bottom and r.bottom > tile.top - 16:
                # 从攀爬面（右缘竖线）侧向左撞上：**绝不允许穿过**
                if self._vine_reenter_block > 0:
                    kid.x = float(tile.right)   # 冷却期先钉住，冷却结束吸附
                else:
                    self._enter_vine((tx, ty))
                return
            if facing == "left" and kid.hsp > 0 \
                    and under < tile.left and over >= tile.left \
                    and r.top < tile.bottom and r.bottom > tile.top - 16:
                if self._vine_reenter_block > 0:
                    kid.x = float(tile.left - kid.w)
                else:
                    self._enter_vine((tx, ty))
                return
        # 细网格像素定位藤蔓：同一套单向判定，tile 用像素坐标
        for (vpx, vpy), facing in self.free_vines.items():
            tile = pygame.Rect(vpx, vpy, T, T)
            over = kid.x + kid.w
            under = kid.x
            if facing == "right" and kid.hsp < 0 \
                    and over > tile.right and under <= tile.right \
                    and r.top < tile.bottom and r.bottom > tile.top - 16:
                if self._vine_reenter_block > 0:
                    kid.x = float(tile.right)
                else:
                    self._enter_vine((vpx, vpy))
                return
            if facing == "left" and kid.hsp > 0 \
                    and under < tile.left and over >= tile.left \
                    and r.top < tile.bottom and r.bottom > tile.top - 16:
                if self._vine_reenter_block > 0:
                    kid.x = float(tile.left - kid.w)
                else:
                    self._enter_vine((vpx, vpy))
                return

    def _enter_vine(self, cell):
        kid = self.kid
        self._vine_cell = cell
        kid.mode = "vine"
        kid.hsp = 0.0
        kid.vsp = 0.0
        kid.anim = "on"
        kid.vine_side = self._vine_facing(cell)
        kid.facing = -1 if kid.vine_side == "right" else 1   # 面对藤蔓
        self._clamp_to_vine()
        self._clamp_vine_vertical()   # 垂直也对齐到藤蔓格内（防从攀爬面下方撞上后钻过去）
        # 藤蔓上不算地面：清掉 on_ground，否则脱离后第一帧还被当成"站在地面"，
        # 空中按跳会走地面跳分支而非二段跳。
        kid.on_ground = False
        # 同时清掉"是否贴地面"边沿状态：藤蔓不算贴地面，跳出藤时不应触发
        # kid 第 11 步的"离开地面记一段跳"，否则从地面走进藤再跳出会被误记 1
        #（跳出应免费，保持原跳跃次数）。
        kid._was_touching_surface = False
        kid._was_in_second_water = False   # 同理：藤蔓不参与二段水落地刷新判定
        # 注意：不重置 jump_count —— 藤蔓不会刷新跳跃次数

    def _clamp_vine_vertical(self):
        """吸附时垂直**最小移动**：只要在 `_reanchor_vine` 判定范围
        （底 > 格顶-4、顶 < 格底+4）内就不动，保持 Kid 撞到藤蔓的位置
        （不偏移）。完全出格（从下方撞时 Kid 整体已在格下方）才移回容差线。
        否则硬拽到格顶/格底会让吸附位置跳动（旧实现偏移 18px）。"""
        kid = self.kid
        T = config.TILE_SIZE
        tx, ty = self._vine_cell
        tile = self._vine_tile_rect(self._vine_cell)
        if kid.y + kid.h <= tile.top - 4:          # 完全在格上方（连容差外）
            kid.y = float(tile.top - 4 - kid.h + 1)   # 底 = 格顶-3（容差内）
        elif kid.y >= tile.bottom + 4:             # 完全在格下方（连容差外）
            kid.y = float(tile.bottom + 3)         # 顶 = 格底+3（容差内）

    def _clamp_to_vine(self):
        """水平贴紧攀爬面：Kid 碰撞箱紧贴当前藤蔓格一侧。"""
        kid = self.kid
        T = config.TILE_SIZE
        tile = self._vine_tile_rect(self._vine_cell)
        if self._vine_facing(self._vine_cell) == "right":
            kid.x = float(tile.right)          # kid.left = 藤蔓右缘
        else:
            kid.x = float(tile.left - kid.w)   # kid.right = 藤蔓左缘

    def _vine_update(self, inp):
        """VINE_CLING 每帧：独立输入 / 移动 / 下滑 / 脱离（不用普通平台碰撞，
        但垂直移动对固体做碰撞，下滑/跳出不会穿墙）。

        （tengwan_right 为例，tengwan_left 左右互换）：
        - 上方向键         = 无反应（保持不动；shift+上 不会让它向上）
        - 下方向键         = 自然下滑（不冻结）
        - Shift + 靠近方向 = 不再上爬，自然下滑（shift+方向 不会让它向上）
        - Shift + 反方向   = 跳出藤蔓（向右上方/左上方出藤蔓，带向上初速度）
        - 按住反方向       = 普通脱离（向右/左，带小推开速度）
        - 按住靠近方向     = 保持在藤蔓上，仍缓慢下滑
        - 无输入           = 沿藤蔓缓慢下滑（VINE_SLIDE_SPEED）
        """
        kid = self.kid
        facing = self._vine_facing(self._vine_cell)
        if facing is None:                       # 藤蔓已不存在 → 脱离
            self._leave_vine()
            return
        left = inp.held("left")
        right = inp.held("right")
        up = inp.held("up")
        shift = inp.held("jump")
        toward = -1 if facing == "right" else 1  # 靠近藤蔓的方向
        away = -toward
        toward_held = (toward == -1 and left) or (toward == 1 and right)
        away_held = (away == -1 and left) or (away == 1 and right)

        # 上方向键：无反应（保持不动）；下方向键：自然下滑（不冻结）。
        # Shift+靠近方向 不再上爬（shift+方向不会让它向上），落在"靠近=下滑"分支。
        if up:
            dy = 0.0
        elif shift and away_held:
            # Shift + 反方向 = 跳出藤蔓（向右上方 / 左上方出藤蔓）
            self.sounds.play("vine_leap")
            # 跳出是免费动作：不消耗跳跃次数，也不自动触发一次跳。
            # 若在这里 consume_press("jump")，跳出后下一帧按住 Shift 会
            # 自动产生一次按下沿 → 空中自动跳 0→1，看起来就像"出藤耗了一
            # 次跳"。跳跃是边沿触发，跳出后的每次跳都应靠玩家自己松开再按
            # 来触发（与全游戏一致），故这里不消耗、不自动跳。
            self._leave_vine(away * config.VINE_LEAP_HSP, config.VINE_LEAP_VSP)
            return
        elif away_held:
            # 反方向 = 普通脱离（向右/左，带小推开速度；优先于靠近方向）。
            # 脱离后设冷却：Kid 还在攀爬面竖线上，不冷却会被立即重新吸附
            # → 按住方向会"吸附-脱离"抽搐。
            self._leave_vine(away * config.VINE_DETACH_HSP, 0.0,
                             reenter_block=True)
            return
        elif toward_held:
            dy = config.VINE_SLIDE_SPEED         # 靠近方向 = 保持在藤蔓上，仍下滑
        else:
            dy = config.VINE_SLIDE_SPEED         # 无输入 → 缓慢下滑

        kid.y += dy
        self._clamp_vine_y(dy)                   # 防穿墙：撞到固体贴回表面
        self._reanchor_vine()
        if kid.mode != "vine":
            return
        kid.hsp = 0.0
        kid.vsp = 0.0
        self._clamp_to_vine()
        kid.anim = "on"
        kid.facing = -1 if facing == "right" else 1
        kid._advance_anim()
        # 房间边界（藤蔓无普通平台碰撞，但要限制在屏内）
        kid.x = max(0.0, min(kid.x, config.ROOM_WIDTH - kid.w))
        if kid.y < 0.0:
            kid.y = 0.0

    def _clamp_vine_y(self, dy):
        """藤蔓垂直移动后防穿墙：碰撞箱与固体重叠则贴回固体表面
        （向上撞到 → 头顶贴固体底面；向下撞到 → 脚贴固体顶面）。"""
        kid = self.kid
        for _ in range(2):                       # 处理连续重叠（一般一次就够）
            r = kid.rect
            hit = next((s for s in self.solids if r.colliderect(s)), None)
            if hit is None:
                return
            if dy < 0:
                kid.y = float(hit.bottom)
            elif dy > 0:
                kid.y = float(hit.top - kid.h)
            else:
                return

    def _reanchor_vine(self):
        """垂直移动后重吸附：当前格上下有同向藤蔓则换格，否则脱离。

        _vine_cell 可能是格子键 (tx,ty) 或像素键 (px,py)：
        格子藤蔓在 (tx, ty±1) 找相邻格；像素藤蔓在 (px, py±32) 找。"""
        kid = self.kid
        T = config.TILE_SIZE
        cell = self._vine_cell
        facing = self._vine_facing(cell)
        if cell in self.vines:
            tx, ty = cell
            cands = ((tx, ty - 1), (tx, ty), (tx, ty + 1))
        else:
            px, py = cell
            cands = ((px, py - T), (px, py), (px, py + T))
        r = kid.rect
        for cand in cands:
            if self._vine_facing(cand) == facing:
                tile = self._vine_tile_rect(cand)
                # 判定与吸附一致（±4 容差）：Kid 顶过格底 4px 内仍算在格，
                # 下滑到藤蔓底部附近才脱离（不是吸附后 1-2 帧"消失"）
                if r.bottom > tile.top - 4 and r.top < tile.bottom + 4:
                    self._vine_cell = cand
                    return
        self._leave_vine(reenter_block=True)   # 滑到底：脱离并冷却，防反复吸附

    def _leave_vine(self, hsp_push=0.0, vsp_push=0.0, reenter_block=False):
        """脱离藤蔓回到 NORMAL：保留跳跃次数（藤蔓不刷新跳跃）。

        可带初速度：普通脱离传 hsp_push（向右/左推开）、跳出传 hsp_push+vsp_push
        （向右上方/左上方出藤蔓）；默认从静止下落。

        reenter_block=True 时设置"再吸附冷却"（20 帧）：
        下滑到底/普通脱离后 Kid 还压在攀爬面竖线上，若立即按住靠近方向，
        下一帧就会被重新吸附 → 吸附-下滑-脱离无限循环（Kid 抽搐）。
        冷却期间不触发吸附，Kid 得以走出藤蔓。
        注意：**跳出（Shift+反方向 leap）不设冷却**——上攀靠"跳出再跳回"
        循环，跳出后要能立即跳回藤蔓。
        """
        kid = self.kid
        kid.mode = "normal"
        self._vine_cell = None
        kid.hsp = hsp_push
        kid.vsp = vsp_push
        kid.anim = "idle" if kid.on_ground else "fall"
        if reenter_block:
            self._vine_reenter_block = 20

    def _collect_plus_jump(self):
        """收集跳跃球：返还一次跳跃并移除该跳跃球（圆形碰撞检测）。

        jump_count 记录的是"已用跳跃次数"（0=未用 1=已用一段跳 2=二段跳已用），
        空中跳跃判定是 jump_count < max_jumps（默认 2，可被跳跃星星改为 1/2/3）。
        所以跳跃球必须把已用次数**减一**（返还一次跳跃），才能让用完的 Kid 再跳
        一次；之前写成 += 1 等于记作"更已用完"，二段跳后捡球计数变 3，3 < 2
        不成立，永远跳不起来（bug）。
        """
        T = config.TILE_SIZE
        kid_rect = self.kid.rect
        kid_center = (kid_rect.centerx, kid_rect.centery)
        kid_radius = min(kid_rect.width, kid_rect.height) // 2

        # 找到并移除被收集的跳跃球
        for i, (tx, ty) in enumerate(self.room.plus_jumps):
            # 跳跃球中心坐标
            ball_center = (tx * T + T // 2, ty * T + T // 2)
            # 跳跃球碰撞半径（与 _touches_plus_jump 一致，缩小）
            ball_radius = config.PLUS_JUMP_RADIUS

            # 计算两个圆心之间的距离
            dx = kid_center[0] - ball_center[0]
            dy = kid_center[1] - ball_center[1]
            distance = (dx * dx + dy * dy) ** 0.5

            # 如果距离小于两个半径之和，则发生碰撞
            if distance < kid_radius + ball_radius:
                # 返还一次跳跃：把"已用次数"减一，让空中跳跃判定重新成立
                self.kid.jump_count = max(0, self.kid.jump_count - 1)
                self.sounds.play("collect")
                # 移除该跳跃球
                self.room.plus_jumps.pop(i)
                return
        # 细网格像素定位跳跃球
        for i, (px, py) in enumerate(self.room.free_plus_jumps):
            ball_center = (px + T // 2, py + T // 2)
            ball_radius = config.PLUS_JUMP_RADIUS
            dx = kid_center[0] - ball_center[0]
            dy = kid_center[1] - ball_center[1]
            if (dx * dx + dy * dy) ** 0.5 < kid_radius + ball_radius:
                self.kid.jump_count = max(0, self.kid.jump_count - 1)
                self.sounds.play("collect")
                self.room.free_plus_jumps.pop(i)
                return

    # ---- 跳跃星星（改变最多跳跃次数，不可消耗） ----
    def _star_cells_touching(self):
        """Kid 碰撞箱与哪些星星重叠（圆形碰撞检测），返回 [(tx, ty, level), ...]。"""
        T = config.TILE_SIZE
        kid_rect = self.kid.rect
        kid_center = (kid_rect.centerx, kid_rect.centery)
        kid_radius = min(kid_rect.width, kid_rect.height) // 2

        hits = []
        for (tx, ty, level) in self.room.stars:
            star_center = (tx * T + T // 2, ty * T + T // 2)
            star_radius = T // 2 - 2   # 留一点边距
            dx = kid_center[0] - star_center[0]
            dy = kid_center[1] - star_center[1]
            if (dx * dx + dy * dy) ** 0.5 < kid_radius + star_radius:
                hits.append((tx, ty, level))
        # 细网格像素定位星星（像素坐标 = 贴图左上角）
        for (px, py, level) in self.room.free_stars:
            star_center = (px + T // 2, py + T // 2)
            star_radius = T // 2 - 2
            dx = kid_center[0] - star_center[0]
            dy = kid_center[1] - star_center[1]
            if (dx * dx + dy * dy) ** 0.5 < kid_radius + star_radius:
                hits.append((px, py, level))
        return hits

    def _check_star_touches(self):
        """碰到跳跃星星：把最多跳跃次数改为星星的段数（1/2/3）。

        边沿触发：只在**进入重叠**的那一帧生效一次（用上一帧的 _prev_star_cells
        做差集），重叠期间不会每帧重复触发（避免反复刷音效/特效），离开再碰
        能重新生效。星星不可消耗：本体留在原地，不删、不随死亡恢复。

        玩家**已是该段数**（max_jumps 已等于星星段数）时，段数没有变化，
        再碰同一段星星不放音效/特效（碰了也白碰，不刷反馈）。
        """
        current = {cell for cell in self._star_cells_touching()}
        for x, y, level in current - self._prev_star_cells:
            if self.kid.max_jumps == level:
                continue            # 已是该段数：无变化 → 不放音效/特效
            self.kid.max_jumps = level
            self.sounds.play("star")
            # 特效中心：格子星 → tx*T+T//2；像素星 → px+T//2
            if (x, y, level) in self.room.stars:
                fx_x = x * config.TILE_SIZE + config.TILE_SIZE // 2
                fx_y = y * config.TILE_SIZE + config.TILE_SIZE // 2
            else:
                fx_x = x + config.TILE_SIZE // 2
                fx_y = y + config.TILE_SIZE // 2
            self.star_fx.append(StarFX(self.assets.star(level), fx_x, fx_y,
                                       level))
        self._prev_star_cells = current

    def _update_star_fx(self):
        """推进所有星星触碰特效，播完的移除。"""
        for fx in self.star_fx:
            fx.update()
        self.star_fx = [fx for fx in self.star_fx if not fx.dead]

    def _win(self):
        self.state = "won"
        self.kid.alive = False
        self.win_fx.start()

    def _respawn(self):
        if self.spawn_room != self.room.name:
            target = self.room_registry(self.spawn_room)
            if target is not None:
                self.reload_room(target, preserve_spawn=True)
        else:
            self._reset_path_movers()   # 死亡重置：路径物体回原位
        self._restore_room_state()   # 死亡重置地图：被吃掉的跳跃球恢复
        self.in_water = None         # 清残留，复活帧不误判"离开水"
        self.kid.reset(*self.spawn_pos)
        self.music.resume()          # BGM 从淡出位置续播（切房则从新歌开始）
        # 恢复存档时的"最多跳跃次数"（几段跳随存档保存，死亡后不丢）
        if self._saved_max_jumps is not None:
            self.kid.max_jumps = self._saved_max_jumps
        self.state = "play"

    # ---- 渲染 ----
    def draw(self, screen):
        screen.fill(self.room.bg_color)
        if self.bg_surface is not None:
            screen.blit(self.bg_surface, (0, 0))   # 背景图盖在纯色之上
        self._draw_room(screen)
        self._draw_objects(screen)
        if self.state == "play":
            self.kid.draw(screen)
            self._draw_water(screen)   # 水半透明，叠在玩家之上（沉浸感）
        for b in self.bullets:
            b.draw(screen)
        for fx in self.star_fx:
            fx.draw(screen)          # 星星触碰特效（顶层，压在子弹之上）
        if self.state in ("dying", "dead"):
            self.death_fx.draw(screen)
        elif self.state == "won":
            self.win_fx.draw(screen)
        if self.show_hitboxes:
            self._draw_hitboxes(screen)
        # 隐藏参数面板由 App 画进独立小窗口（F2），不占主画面

    def _draw_room(self, screen):
        T = config.TILE_SIZE
        for (tx, ty), tile_type in self.room.tiles.items():
            img = texture_for(self.assets, self.room, f"tile:{tile_type}",
                              self.assets.tile(tile_type))
            screen.blit(img, (tx * T, ty * T))
        # 细网格像素定位砖块：贴图左上角即像素坐标
        for (px, py), tile_type in self.room.free_tiles.items():
            img = texture_for(self.assets, self.room, f"tile:{tile_type}",
                              self.assets.tile(tile_type))
            screen.blit(img, (px, py))
        # 小砖块：16×16（原贴图缩放；有自定义砖块材质时同步替换）
        for (px, py), tile_type in self.room.small_tiles.items():
            img = texture_for(self.assets, self.room, f"tile:{tile_type}",
                              self.assets.tile_small(tile_type))
            screen.blit(img, (px, py))

    def _draw_objects(self, screen):
        T = config.TILE_SIZE
        # 绘制平台（32×16）
        for px, py in self.room.platforms:
            img = texture_for(self.assets, self.room, "platform",
                              self.assets.platform())
            screen.blit(img, (px, py))
        for (tx, ty), direction in self.room.spikes.items():
            img = texture_for(self.assets, self.room, f"spike:{direction}",
                              self.assets.spike(direction))
            screen.blit(img, (tx * T, ty * T))
        for (px, py), direction in self.room.free_spikes.items():
            img = texture_for(self.assets, self.room, f"spike:{direction}",
                              self.assets.spike(direction))
            screen.blit(img, (px, py))
        for (tx, ty, quad), direction in self.room.mini_spikes.items():
            # 计算小刺的实际渲染位置
            Q = T // 2  # 16px
            base_x = tx * T
            base_y = ty * T
            if quad == 0:  # 左上
                x, y = base_x, base_y
            elif quad == 1:  # 右上
                x, y = base_x + Q, base_y
            elif quad == 2:  # 左下
                x, y = base_x, base_y + Q
            else:  # quad == 3, 右下
                x, y = base_x + Q, base_y + Q
            img = texture_for(self.assets, self.room,
                              f"mini_spike:{direction}",
                              self.assets.mini_spike(direction))
            screen.blit(img, (x, y))
        # 被路径节点挂载的小刺（运行时像素列表）
        for (x, y, direction) in self._moved_mini:
            img = texture_for(self.assets, self.room,
                              f"mini_spike:{direction}",
                              self.assets.mini_spike(direction))
            screen.blit(img, (x, y))
        for (tx, ty), facing in self.vines.items():
            img = texture_for(self.assets, self.room, f"vine:{facing}",
                              self.assets.vine(facing))
            screen.blit(img, (tx * T, ty * T))
        for (px, py), facing in self.free_vines.items():
            img = texture_for(self.assets, self.room, f"vine:{facing}",
                              self.assets.vine(facing))
            screen.blit(img, (px, py))
        for (tx, ty) in self.room.checkpoints:
            active = self.active_checkpoint == (self.room.name, tx * T, ty * T)
            img = texture_for(self.assets, self.room,
                              f"checkpoint:{'active' if active else 'inactive'}",
                              self.assets.checkpoint(active))
            screen.blit(img, (tx * T, ty * T))
        for (px, py) in self.room.free_checkpoints:
            active = self.active_checkpoint == (self.room.name, px, py)
            img = texture_for(self.assets, self.room,
                              f"checkpoint:{'active' if active else 'inactive'}",
                              self.assets.checkpoint(active))
            screen.blit(img, (px, py))
        # 绘制跳跃球
        for (tx, ty) in self.room.plus_jumps:
            img = texture_for(self.assets, self.room, "plus_jump",
                              self.assets.plusjump())
            screen.blit(img, (tx * T, ty * T))
        for (px, py) in self.room.free_plus_jumps:
            img = texture_for(self.assets, self.room, "plus_jump",
                              self.assets.plusjump())
            screen.blit(img, (px, py))
        # 绘制跳跃星星（按段数取贴图；不可消耗，永远在）
        for (tx, ty, level) in self.room.stars:
            img = texture_for(self.assets, self.room, f"star:{level}",
                              self.assets.star(level))
            screen.blit(img, (tx * T, ty * T))
        for (px, py, level) in self.room.free_stars:
            img = texture_for(self.assets, self.room, f"star:{level}",
                              self.assets.star(level))
            screen.blit(img, (px, py))
        # 传送门与终点统一使用 end.png（同为"门"外观）；自定义材质键 door
        for ex in self.room.exits:
            tx, ty = ex["tile"]
            img = texture_for(self.assets, self.room, "door",
                              self.assets.end())
            screen.blit(img, (tx * T, ty * T))
        for ex in self.room.free_exits:
            px, py = ex["pos"]
            img = texture_for(self.assets, self.room, "door",
                              self.assets.end())
            screen.blit(img, (px, py))
        if self.room.end is not None:
            tx, ty = self.room.end
            img = texture_for(self.assets, self.room, "door",
                              self.assets.end())
            screen.blit(img, (tx * T, ty * T))
        if self.room.free_end is not None:
            px, py = self.room.free_end
            img = texture_for(self.assets, self.room, "door",
                              self.assets.end())
            screen.blit(img, (px, py))

    def _draw_water(self, screen):
        """绘制水（半透明，叠在玩家角色之上）。"""
        for water, _ in self.water_tiles:
            img = texture_for(self.assets, self.room,
                              f"water:{water.water_type}",
                              self.assets.water(water.water_type))
            screen.blit(img, (round(water.x), round(water.y)))

    # ---- 碰撞箱可视化（F1） ----
    def _draw_hitboxes(self, screen):
        colors = config.HITBOX_COLORS
        if self.state == "play":
            pygame.draw.rect(screen, colors["kid"], self.kid.rect, 1)
            self._draw_kid_debug_text(screen)
        for r in self.solids:
            pygame.draw.rect(screen, colors["solid"], r, 1)
        for (px, py), _t in self.room.small_tiles.items():
            pygame.draw.rect(screen, colors["solid"],
                             pygame.Rect(px, py, 16, 16), 1)
        for mask, ox, oy in self.spike_masks:
            outline = mask.outline()
            pts = [(x + ox, y + oy) for x, y in outline]
            if len(pts) >= 3:
                pygame.draw.polygon(screen, colors["spike"], pts, 1)
        for mask, ox, oy in self.mini_spike_masks:
            outline = mask.outline()
            pts = [(x + ox, y + oy) for x, y in outline]
            if len(pts) >= 3:
                pygame.draw.polygon(screen, colors["spike"], pts, 1)
        for (x, y, _d) in self._moved_mini:
            pygame.draw.rect(screen, colors["spike"],
                             pygame.Rect(x, y, 16, 16), 1)
        T = config.TILE_SIZE
        # 绘制平台的碰撞箱（蓝色）
        for px, py in self.room.platforms:
            platform_rect = pygame.Rect(px, py, 32, 16)
            pygame.draw.rect(screen, colors["platform"], platform_rect, 1)
        for (tx, ty), facing in self.vines.items():
            tile = pygame.Rect(tx * T, ty * T, T, T)
            # 攀爬面 = 藤蔓一侧的竖线（绿色）
            face_x = tile.right if facing == "right" else tile.left
            pygame.draw.line(screen, colors["vine"],
                             (face_x, tile.top), (face_x, tile.bottom), 1)
        for (px, py), facing in self.free_vines.items():
            tile = pygame.Rect(px, py, T, T)
            face_x = tile.right if facing == "right" else tile.left
            pygame.draw.line(screen, colors["vine"],
                             (face_x, tile.top), (face_x, tile.bottom), 1)
        for (tx, ty) in self.room.checkpoints:
            # 触发区 = 32×32 整格（不再上下扩展）
            tile = pygame.Rect(tx * T, ty * T, T, T)
            pygame.draw.rect(screen, colors["checkpoint"], tile, 1)
        for (px, py) in self.room.free_checkpoints:
            tile = pygame.Rect(px, py, T, T)
            pygame.draw.rect(screen, colors["checkpoint"], tile, 1)
        for ex in self.room.exits:
            tx, ty = ex["tile"]
            pygame.draw.rect(screen, colors["exit"],
                             pygame.Rect(tx * T, ty * T, T, T), 1)
        for ex in self.room.free_exits:
            px, py = ex["pos"]
            pygame.draw.rect(screen, colors["exit"],
                             pygame.Rect(px, py, T, T), 1)
        if self.end_rect is not None:
            pygame.draw.rect(screen, colors["end"], self.end_rect, 1)
        if self.free_end_rect is not None:
            pygame.draw.rect(screen, colors["end"], self.free_end_rect, 1)
        # 绘制跳跃球的碰撞箱（圆形，缩小后的半径）
        T = config.TILE_SIZE
        for (tx, ty) in self.room.plus_jumps:
            ball_center = (tx * T + T // 2, ty * T + T // 2)
            ball_radius = config.PLUS_JUMP_RADIUS
            pygame.draw.circle(screen, colors["plus_jump"], ball_center, ball_radius, 1)
        for (px, py) in self.room.free_plus_jumps:
            ball_center = (px + T // 2, py + T // 2)
            ball_radius = config.PLUS_JUMP_RADIUS
            pygame.draw.circle(screen, colors["plus_jump"], ball_center, ball_radius, 1)
        # 绘制跳跃星星的碰撞箱（圆形）
        for (tx, ty, _level) in self.room.stars:
            star_center = (tx * T + T // 2, ty * T + T // 2)
            star_radius = T // 2 - 2
            pygame.draw.circle(screen, colors["star"], star_center, star_radius, 1)
        for (px, py, _level) in self.room.free_stars:
            star_center = (px + T // 2, py + T // 2)
            star_radius = T // 2 - 2
            pygame.draw.circle(screen, colors["star"], star_center, star_radius, 1)
        # 绘制水的碰撞箱（水蓝色）
        for water, rect in self.water_tiles:
            pygame.draw.rect(screen, (100, 180, 255), rect, 1)
            # 显示水类型
            font = config.get_font(10)
            text = font.render(water.water_type[0].upper(), True, (255, 255, 255))
            screen.blit(text, (rect.centerx - 5, rect.centery - 5))
        for b in self.bullets:
            outline = b.mask.outline()
            pts = [(x + round(b.x), y + round(b.y)) for x, y in outline]
            if len(pts) >= 3:
                pygame.draw.polygon(screen, colors["bullet"], pts, 1)

    def _draw_kid_debug_text(self, screen):
        """F1 调试文字：状态 / 动画帧号 / 碰撞箱坐标 / 贴图绘制坐标（贴在 Kid 旁）。"""
        k = self.kid
        font = config.get_font(13)
        mode = "VINE" if k.mode == "vine" else "NORMAL"
        lines = [
            f"{mode}  {k.anim}#{k.frame}",
            f"hitbox ({k.rect.x},{k.rect.y}) {k.rect.w}x{k.rect.h}",
            f"draw {k.last_draw_pos}",
        ]
        x = k.rect.right + 6
        y = max(2, k.rect.top - 4)
        for line in lines:
            img = font.render(line, True, (255, 255, 255))
            x = min(x, config.ROOM_WIDTH - img.get_width() - 2)   # 防出屏
            bg = pygame.Surface(img.get_size(), pygame.SRCALPHA)
            bg.fill((0, 0, 0, 160))
            screen.blit(bg, (x, y))
            screen.blit(img, (x, y))
            y += img.get_height() + 2
