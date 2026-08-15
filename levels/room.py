"""
levels/room.py — Room 数据模型

一个 Room 固定 800×608（25×19 网格，32px Tile），独立坐标，左上角 (0,0)。
阶段3：Tile 网格 + 由 Tile 构建固体碰撞矩形。
阶段6：from_json/to_json 与 rooms/*.json 互通（地图数据与代码解耦）。
尖刺 / Checkpoint / 出生点 / 出口 字段定义见下。
"""

import pygame

import config


def _parse_color(value):
    """JSON 里的 [r,g,b] → 元组；非法则回退默认背景色。"""
    if (isinstance(value, (list, tuple)) and len(value) == 3
            and all(isinstance(c, int) for c in value)):
        return tuple(min(max(c, 0), 255) for c in value)
    return config.BG_COLOR


class Room:
    def __init__(self, name="room001", bg_color=None):
        self.name = name
        self.width = config.ROOM_WIDTH
        self.height = config.ROOM_HEIGHT
        self.bg_color = bg_color if bg_color is not None else config.BG_COLOR
        self.bg_image = None     # 背景图片文件名（assets/backgrounds/ 下），None=纯色背景
        self.bg_mode = "stretch"  # 背景填充模式：stretch/fill/fit/tile/center/zoom
        self.bg_zoom = 1.0       # zoom 模式缩放倍数（相对原图）
        self.bg_offset = [0, 0]  # zoom 模式偏移（像素，正值向右/下）
        self.bgm = None          # 背景音乐文件名（music/ 下），None=无音乐
        self.textures = {}       # 物体类型键 -> assets/textures/ 图片文件名（自定义材质）

        self.tiles = {}          # (tx, ty) -> tile_type (str，如 "block_0")
        self.spikes = {}         # (tx, ty) -> "up"/"down"/"left"/"right"
        self.mini_spikes = {}    # (tx, ty) -> "up"/"down"/"left"/"right"（小刺，16×16px）
        self.vines = {}          # (tx, ty) -> "left"/"right"（攀爬面在对应一侧）
        self.platforms = []      # [(px, py), ...] 平台左上角像素坐标（32×16 尺寸）
        self.checkpoints = []    # [(tx, ty), ...]
        self.water = {}          # (tx, ty) -> "first"/"second"/"zero"（水类型）
        self.start = (96.0, 17 * config.TILE_SIZE - config.KID_HEIGHT)  # 像素，碰撞箱左上角
        self.exits = []          # [{"tile": (tx,ty), "target": "room002"}, ...]
        self.end = None          # (tx, ty) 终点（end.png），碰到即通关；None 表示无终点
        self.plus_jumps = []    # [(tx, ty), ...] 跳跃球位置
        self.stars = []          # [(tx, ty, level), ...] 跳跃星星（level=1/2/3，不可消耗）

        # ---- 细网格（16/8px）像素定位元素 ----
        # 32 网格放置仍写入上面的格子结构；16px 及更细粒度放置写入下面的
        # "free_*" 结构（键为像素坐标 px/py，即元素左上角）。游戏/编辑器
        # 同时渲染和碰撞两套，格子结构行为完全不变（旧房间/测试不受影响）。
        self.free_tiles = {}       # (px, py) -> tile_type     像素定位砖块（32×32 贴图）
        self.free_spikes = {}      # (px, py) -> "up"/...      像素定位尖刺（32×32 贴图）
        self.free_vines = {}       # (px, py) -> "left"/"right" 像素定位藤蔓
        self.free_water = {}       # (px, py) -> water_type    像素定位水
        self.free_checkpoints = [] # [(px, py), ...]           像素定位 Checkpoint
        self.free_exits = []       # [{"pos": (px,py), "target": ...}]
        self.free_end = None       # (px, py) 或 None           像素定位终点
        self.free_plus_jumps = []  # [(px, py), ...]           像素定位跳跃球
        self.free_stars = []       # [(px, py, level), ...]    像素定位跳跃星星
        self.small_tiles = {}      # (px, py) -> tile_type     小砖块（16×16，贴图缩放）
        self.path_nodes = []       # [{"pos": (px,py), "path": [(x,y),...],
                                   #    "speed": float, "trigger": "auto"/"touch"}]

    # ---- 坐标换算 ----
    @staticmethod
    def px(tx):
        return tx * config.TILE_SIZE

    @staticmethod
    def in_bounds(tx, ty):
        return 0 <= tx < config.GRID_COLS and 0 <= ty < config.GRID_ROWS

    @staticmethod
    def in_bounds_px(px, py):
        """像素坐标（元素左上角）是否在房间内。"""
        return 0 <= px < config.ROOM_WIDTH and 0 <= py < config.ROOM_HEIGHT

    # ---- Tile ----
    def set_tile(self, tx, ty, tile_type=None):
        """放置/删除一个 Tile（tile_type=None 表示删除）。"""
        if not self.in_bounds(tx, ty):
            return
        if tile_type is None:
            self.tiles.pop((tx, ty), None)
        else:
            self.tiles[(tx, ty)] = tile_type

    def get_tile(self, tx, ty):
        return self.tiles.get((tx, ty))

    def clear_tiles(self):
        self.tiles.clear()

    # ---- Platform（单向平台，32×16 像素） ----
    def add_platform(self, px, py):
        """添加一个平台，px/py 为左上角像素坐标（任意像素位置，编辑器细粒度放置）。"""
        px, py = float(px), float(py)
        if 0 <= px < self.width and 0 <= py < self.height:
            # 避免重复添加
            if (px, py) not in self.platforms:
                self.platforms.append((px, py))

    def remove_platform(self, px, py):
        """移除指定位置的平台。"""
        if (px, py) in self.platforms:
            self.platforms.remove((px, py))

    def clear_platforms(self):
        """清空所有平台。"""
        self.platforms.clear()

    # ---- Star（跳跃星星，不可消耗） ----
    def add_star(self, tx, ty, level):
        """添加一颗跳跃星星，tx/ty 为网格坐标，level 为段数（1/2/3）。"""
        if self.in_bounds(tx, ty) and level in config.STAR_LEVELS:
            star = (tx, ty, level)
            if star not in self.stars:
                self.stars.append(star)

    def remove_star(self, tx, ty):
        """移除指定网格的星星（不论段数）。"""
        self.stars = [s for s in self.stars if (s[0], s[1]) != (tx, ty)]

    def clear_stars(self):
        """清空所有星星。"""
        self.stars.clear()

    # ---- Water（水实体） ----
    def add_water(self, tx, ty, water_type="first"):
        """添加一个水实体，tx/ty 为网格坐标。

        Args:
            tx, ty: 网格坐标
            water_type: "first", "second", or "zero"
        """
        if self.in_bounds(tx, ty):
            self.water[(tx, ty)] = water_type

    def remove_water(self, tx, ty):
        """移除指定位置的水实体。"""
        self.water.pop((tx, ty), None)

    def clear_water(self):
        """清空所有水实体。"""
        self.water.clear()

    # ---- Mini Spike（小刺） ----
    def add_mini_spike(self, tx, ty, direction="up", quad=0):
        """添加一个小刺，tx/ty 为网格坐标，quad 为四等分位置。

        Args:
            tx, ty: 网格坐标
            direction: "up", "down", "left", "right"
            quad: 0=左上, 1=右上, 2=左下, 3=右下 (在32×32px空间中的位置)
        """
        if self.in_bounds(tx, ty) and direction in ("up", "down", "left", "right") and 0 <= quad <= 3:
            self.mini_spikes[(tx, ty, quad)] = direction

    def remove_mini_spike(self, tx, ty, quad=0):
        """移除指定位置的小刺。"""
        self.mini_spikes.pop((tx, ty, quad), None)

    def clear_mini_spikes(self):
        """清空所有小刺。"""
        self.mini_spikes.clear()

    # ---- JSON 读写（rooms/*.json） ----
    @classmethod
    def from_json(cls, data):
        """从 JSON 字典构建 Room；逐字段校验，非法项跳过不报错。"""
        room = cls(name=str(data.get("name", "room")),
                   bg_color=_parse_color(data.get("bg_color")))
        bg = data.get("bg_image")
        room.bg_image = bg if isinstance(bg, str) and bg else None
        mode = data.get("bg_mode")
        if mode in ("stretch", "fill", "fit", "tile", "center", "zoom"):
            room.bg_mode = mode
        zoom = data.get("bg_zoom")
        if isinstance(zoom, (int, float)) and zoom > 0:
            room.bg_zoom = float(zoom)
        off = data.get("bg_offset")
        if (isinstance(off, list) and len(off) == 2
                and all(isinstance(v, (int, float)) for v in off)):
            room.bg_offset = [int(off[0]), int(off[1])]
        bgm = data.get("bgm")
        room.bgm = bgm if isinstance(bgm, str) and bgm else None
        tex = data.get("textures")
        if isinstance(tex, dict):
            for k, v in tex.items():
                if isinstance(k, str) and isinstance(v, str) and v:
                    room.textures[k] = v

        for t in data.get("tiles", []):
            tx, ty = t.get("tx"), t.get("ty")
            typ = t.get("type")
            if cls.in_bounds(tx, ty) and typ:
                room.set_tile(tx, ty, str(typ))

        for s in data.get("spikes", []):
            tx, ty = s.get("tx"), s.get("ty")
            d = s.get("dir")
            if cls.in_bounds(tx, ty) and d in ("up", "down", "left", "right"):
                room.spikes[(tx, ty)] = d

        for v in data.get("vines", []):
            tx, ty, side = v.get("tx"), v.get("ty"), v.get("side")
            if cls.in_bounds(tx, ty) and side in ("left", "right"):
                room.vines[(tx, ty)] = side

        for w in data.get("water", []):
            tx, ty, water_type = w.get("tx"), w.get("ty"), w.get("type")
            if cls.in_bounds(tx, ty) and water_type in ("first", "second", "zero"):
                room.add_water(tx, ty, water_type)

        for ms in data.get("mini_spikes", []):
            tx, ty, direction = ms.get("tx"), ms.get("ty"), ms.get("dir")
            quad = ms.get("quad", 0)  # 默认为0（左上）
            if cls.in_bounds(tx, ty) and direction in ("up", "down", "left", "right") and 0 <= quad <= 3:
                room.add_mini_spike(tx, ty, direction, quad)

        for p in data.get("platforms", []):
            px, py = p.get("px"), p.get("py")
            if isinstance(px, (int, float)) and isinstance(py, (int, float)):
                room.add_platform(float(px), float(py))

        for c in data.get("checkpoints", []):
            tx, ty = c.get("tx"), c.get("ty")
            if cls.in_bounds(tx, ty):
                room.checkpoints.append((tx, ty))

        for e in data.get("exits", []):
            tx, ty, target = e.get("tx"), e.get("ty"), e.get("target")
            if cls.in_bounds(tx, ty) and target:
                room.exits.append({"tile": (tx, ty), "target": str(target)})

        # 处理跳跃球
        for pj in data.get("plus_jumps", []):
            tx, ty = pj.get("tx"), pj.get("ty")
            if cls.in_bounds(tx, ty):
                room.plus_jumps.append((tx, ty))

        # 处理跳跃星星（level 必须 1/2/3，非法跳过）
        for s in data.get("stars", []):
            tx, ty, level = s.get("tx"), s.get("ty"), s.get("level")
            if cls.in_bounds(tx, ty) and level in config.STAR_LEVELS:
                room.stars.append((tx, ty, level))

        st = data.get("start")
        if (isinstance(st, dict) and isinstance(st.get("x"), (int, float))
                and isinstance(st.get("y"), (int, float))):
            room.start = (float(st["x"]), float(st["y"]))

        en = data.get("end")
        if (isinstance(en, dict) and isinstance(en.get("tx"), int)
                and isinstance(en.get("ty"), int)
                and cls.in_bounds(en["tx"], en["ty"])):
            room.end = (en["tx"], en["ty"])

        # ---- 细网格像素定位元素（free_*） ----
        for ft in data.get("free_tiles", []):
            px, py, typ = ft.get("x"), ft.get("y"), ft.get("type")
            if isinstance(px, (int, float)) and isinstance(py, (int, float)) \
                    and typ and cls.in_bounds_px(px, py):
                room.free_tiles[(px, py)] = str(typ)
        for fs in data.get("free_spikes", []):
            px, py, d = fs.get("x"), fs.get("y"), fs.get("dir")
            if isinstance(px, (int, float)) and isinstance(py, (int, float)) \
                    and d in ("up", "down", "left", "right") \
                    and cls.in_bounds_px(px, py):
                room.free_spikes[(px, py)] = d
        for fv in data.get("free_vines", []):
            px, py, side = fv.get("x"), fv.get("y"), fv.get("side")
            if isinstance(px, (int, float)) and isinstance(py, (int, float)) \
                    and side in ("left", "right") and cls.in_bounds_px(px, py):
                room.free_vines[(px, py)] = side
        for fw in data.get("free_water", []):
            px, py, wt = fw.get("x"), fw.get("y"), fw.get("type")
            if isinstance(px, (int, float)) and isinstance(py, (int, float)) \
                    and wt in ("first", "second", "zero") \
                    and cls.in_bounds_px(px, py):
                room.free_water[(px, py)] = wt
        for fc in data.get("free_checkpoints", []):
            px, py = fc.get("x"), fc.get("y")
            if isinstance(px, (int, float)) and isinstance(py, (int, float)) \
                    and cls.in_bounds_px(px, py):
                room.free_checkpoints.append((px, py))
        for fe in data.get("free_exits", []):
            px, py, target = fe.get("x"), fe.get("y"), fe.get("target")
            if isinstance(px, (int, float)) and isinstance(py, (int, float)) \
                    and target and cls.in_bounds_px(px, py):
                room.free_exits.append({"pos": (px, py), "target": str(target)})
        fen = data.get("free_end")
        if (isinstance(fen, dict) and isinstance(fen.get("x"), (int, float))
                and isinstance(fen.get("y"), (int, float))
                and cls.in_bounds_px(fen["x"], fen["y"])):
            room.free_end = (fen["x"], fen["y"])
        for fp in data.get("free_plus_jumps", []):
            px, py = fp.get("x"), fp.get("y")
            if isinstance(px, (int, float)) and isinstance(py, (int, float)) \
                    and cls.in_bounds_px(px, py):
                room.free_plus_jumps.append((px, py))
        for fst in data.get("free_stars", []):
            px, py, level = fst.get("x"), fst.get("y"), fst.get("level")
            if isinstance(px, (int, float)) and isinstance(py, (int, float)) \
                    and level in config.STAR_LEVELS and cls.in_bounds_px(px, py):
                room.free_stars.append((px, py, level))

        # 小砖块（16×16，像素定位）
        for st in data.get("small_tiles", []):
            px, py, typ = st.get("x"), st.get("y"), st.get("type")
            if isinstance(px, (int, float)) and isinstance(py, (int, float)) \
                    and typ and cls.in_bounds_px(px, py):
                room.small_tiles[(px, py)] = str(typ)

        # 路径节点（编辑器可见；游戏里驱动重合元素移动）
        for pn in data.get("path_nodes", []):
            px, py = pn.get("x"), pn.get("y")
            if not (isinstance(px, (int, float))
                    and isinstance(py, (int, float))
                    and cls.in_bounds_px(px, py)):
                continue
            path = []
            raw = pn.get("path", [])
            if isinstance(raw, list):
                for pt in raw:
                    if (isinstance(pt, list) and len(pt) == 2
                            and isinstance(pt[0], (int, float))
                            and isinstance(pt[1], (int, float))):
                        path.append((pt[0], pt[1]))
            speed = pn.get("speed", config.PATH_DEFAULT_SPEED)
            if not isinstance(speed, (int, float)) or speed <= 0:
                speed = config.PATH_DEFAULT_SPEED
            trigger = pn.get("trigger", "auto")
            if trigger not in ("auto", "touch"):
                trigger = "auto"
            room.path_nodes.append({"pos": (px, py), "path": path,
                                    "speed": float(speed),
                                    "trigger": trigger})
        return room

    def to_json(self):
        """当前房间序列化为 JSON 可写字典（rooms/*.json 格式）。"""
        out = {
            "name": self.name,
            "width": self.width,
            "height": self.height,
            "bg_color": list(self.bg_color),
            "bg_image": self.bg_image,
            "bg_mode": self.bg_mode,
            "bg_zoom": self.bg_zoom,
            "bg_offset": list(self.bg_offset),
            "bgm": self.bgm,
            "textures": dict(self.textures) if self.textures else {},
            "tiles": [{"tx": tx, "ty": ty, "type": t}
                      for (tx, ty), t in sorted(self.tiles.items())],
            "spikes": [{"tx": tx, "ty": ty, "dir": d}
                       for (tx, ty), d in sorted(self.spikes.items())],
            "vines": [{"tx": tx, "ty": ty, "side": side}
                      for (tx, ty), side in sorted(self.vines.items())],
            "water": [{"tx": tx, "ty": ty, "type": water_type}
                      for (tx, ty), water_type in sorted(self.water.items())],
            "mini_spikes": [{"tx": tx, "ty": ty, "dir": d, "quad": quad}
                           for (tx, ty, quad), d in sorted(self.mini_spikes.items())],
            "platforms": [{"px": px, "py": py} for px, py in sorted(self.platforms)],
            "start": {"x": self.start[0], "y": self.start[1]},
            "checkpoints": [{"tx": tx, "ty": ty} for tx, ty in self.checkpoints],
            "exits": [{"tx": e["tile"][0], "ty": e["tile"][1], "target": e["target"]}
                      for e in self.exits],
            "end": {"tx": self.end[0], "ty": self.end[1]} if self.end else None,
            "plus_jumps": [{"tx": tx, "ty": ty} for tx, ty in self.plus_jumps],
            "stars": [{"tx": tx, "ty": ty, "level": level}
                      for tx, ty, level in self.stars],
        }
        # 细网格像素元素：仅在非空时写入（旧房间文件保持干净）
        if self.free_tiles:
            out["free_tiles"] = [{"x": px, "y": py, "type": t}
                                 for (px, py), t in sorted(self.free_tiles.items())]
        if self.free_spikes:
            out["free_spikes"] = [{"x": px, "y": py, "dir": d}
                                  for (px, py), d in sorted(self.free_spikes.items())]
        if self.free_vines:
            out["free_vines"] = [{"x": px, "y": py, "side": side}
                                 for (px, py), side in sorted(self.free_vines.items())]
        if self.free_water:
            out["free_water"] = [{"x": px, "y": py, "type": wt}
                                 for (px, py), wt in sorted(self.free_water.items())]
        if self.free_checkpoints:
            out["free_checkpoints"] = [{"x": px, "y": py}
                                       for px, py in self.free_checkpoints]
        if self.free_exits:
            out["free_exits"] = [{"x": e["pos"][0], "y": e["pos"][1],
                                  "target": e["target"]} for e in self.free_exits]
        if self.free_end is not None:
            out["free_end"] = {"x": self.free_end[0], "y": self.free_end[1]}
        if self.free_plus_jumps:
            out["free_plus_jumps"] = [{"x": px, "y": py}
                                      for px, py in self.free_plus_jumps]
        if self.free_stars:
            out["free_stars"] = [{"x": px, "y": py, "level": level}
                                 for px, py, level in self.free_stars]
        if self.small_tiles:
            out["small_tiles"] = [{"x": px, "y": py, "type": t}
                                  for (px, py), t in sorted(self.small_tiles.items())]
        if self.path_nodes:
            out["path_nodes"] = [
                {"x": n["pos"][0], "y": n["pos"][1],
                 "path": [[p[0], p[1]] for p in n["path"]],
                 "speed": n["speed"], "trigger": n["trigger"]}
                for n in self.path_nodes]
        return out

    # ---- 固体碰撞矩形（按行合并水平相邻 Tile，减少碰撞检测数） ----
    def solid_rects(self):
        rects = []
        T = config.TILE_SIZE
        for ty in range(config.GRID_ROWS):
            tx = 0
            while tx < config.GRID_COLS:
                if (tx, ty) in self.tiles:
                    start = tx
                    while tx < config.GRID_COLS and (tx, ty) in self.tiles:
                        tx += 1
                    rects.append(pygame.Rect(
                        start * T, ty * T, (tx - start) * T, T))
                else:
                    tx += 1
        # 细网格像素定位的砖块：每个单独一个 32×32 矩形（不做行合并）
        for (px, py), _t in self.free_tiles.items():
            rects.append(pygame.Rect(px, py, T, T))
        # 小砖块：16×16 像素实体
        for (px, py), _t in self.small_tiles.items():
            rects.append(pygame.Rect(px, py, 16, 16))
        return rects
