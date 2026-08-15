"""
physics/collision.py — 离散 AABB 碰撞（自实现，无第三方物理引擎）

流程严格按 I Wanna 约定：先 X 轴（移动→检测→修正），再 Y 轴（移动→检测→修正）。
单帧最大位移 MAX_FALL_SPEED(10)px < Tile(32)px，高速下不会穿墙。
坐标可为浮点（物理保持亚像素精度），绘制时再取整。
"""

import config


def move_and_collide(x, y, w, h, hsp, vsp, solids):
    """以 hsp/vsp 移动碰撞箱并逐轴修正。

    参数：
        x, y   碰撞箱左上角（可为浮点）
        w, h   碰撞箱宽高
        hsp    本帧水平位移（可为浮点）
        vsp    本帧垂直位移
        solids 固体矩形列表（pygame.Rect，整数坐标）

    返回 (new_x, new_y, on_ground, hit_ceiling, hit_wall)：
        on_ground   — 本帧落在平面上
        hit_ceiling — 本帧撞到天花板
        hit_wall    — 1=撞右侧墙  -1=撞左侧墙  0=无
    """
    new_x = x + hsp
    new_y = y + vsp

    def overlap_at(cx, cy):
        hits = []
        for s in solids:
            if cx + w > s.left and cx < s.right and cy + h > s.top and cy < s.bottom:
                hits.append(s)
        return hits

    on_ground = False
    hit_ceiling = False
    hit_wall = 0

    # ---- X 轴：移动 -> 检测 -> 修正 ----
    if hsp > 0:
        hits = overlap_at(new_x, y)
        if hits:
            hit_wall = 1
            new_x = min(s.left for s in hits) - w
    elif hsp < 0:
        hits = overlap_at(new_x, y)
        if hits:
            hit_wall = -1
            new_x = max(s.right for s in hits)

    # ---- Y 轴：移动 -> 检测 -> 修正 ----
    if vsp > 0:
        hits = overlap_at(new_x, new_y)
        if hits:
            on_ground = True
            new_y = min(s.top for s in hits) - h
    elif vsp < 0:
        hits = overlap_at(new_x, new_y)
        if hits:
            hit_ceiling = True
            new_y = max(s.bottom for s in hits)

    return new_x, new_y, on_ground, hit_ceiling, hit_wall


def is_grounded(x, y, w, h, solids, platforms=None):
    """站立判定：底部再往下探 1px 是否与固体重叠。

    解决"vsp=0 时严格不等式导致落地判定逐帧闪烁"的问题，
    保证站立 / 走落平台边缘时 on_ground 连续稳定。

    支持单向平台：如果 platforms 非空，也会检测平台碰撞。
    """
    if platforms is None:
        platforms = []

    probe_y = y + 1

    # 检测固体
    for s in solids:
        if (x + w > s.left and x < s.right
                and probe_y + h > s.top and probe_y < s.bottom):
            return True

    # 检测单向平台（玩家必须在平台上方）
    for p in platforms:
        # 水平范围重叠
        if x + w > p.left and x < p.right:
            # 玩家底部在平台顶部附近（精确判定）
            player_bottom = y + h
            if player_bottom >= p.top - 1 and player_bottom <= p.top + 1:
                # 玩家必须在平台上方
                if player_bottom <= p.top + 2:
                    return True
    return False


def is_on_platform(x, y, w, h, platforms):
    """检测玩家是否在板子上（碰撞箱重叠）。

    参数：
        x, y     玩家碰撞箱左上角
        w, h     玩家碰撞箱宽高
        platforms 单向平台矩形列表

    返回：
        bool - 玩家是否与任何板子碰撞箱重叠
    """
    for p in platforms:
        if (x + w > p.left and x < p.right and
            y + h > p.top and y < p.bottom):
            return True
    return False


def polygons_overlap(poly_a, poly_b):
    """两个凸多边形是否重叠（分离轴定理 SAT）。

    点格式 [(x, y), ...]（顺/逆时针均可）。
    用于尖刺三角形碰撞：矩形 vs 三角形，比整格矩形精确。
    """
    for poly in (poly_a, poly_b):
        for i in range(len(poly)):
            x1, y1 = poly[i]
            x2, y2 = poly[(i + 1) % len(poly)]
            nx, ny = -(y2 - y1), (x2 - x1)   # 边的法线（候选分离轴）
            a_min = min(p[0] * nx + p[1] * ny for p in poly_a)
            a_max = max(p[0] * nx + p[1] * ny for p in poly_a)
            b_min = min(p[0] * nx + p[1] * ny for p in poly_b)
            b_max = max(p[0] * nx + p[1] * ny for p in poly_b)
            if a_max < b_min or b_max < a_min:
                return False   # 存在分离轴 → 不相交
    return True


def move_and_collide_with_platforms(x, y, w, h, hsp, vsp, solids, platforms):
    """以 hsp/vsp 移动碰撞箱并逐轴修正，支持单向平台。

    参数：
        x, y       碰撞箱左上角（可为浮点）
        w, h       碰撞箱宽高
        hsp, vsp   本帧水平/垂直位移
        solids     固体矩形列表（pygame.Rect，整数坐标）
        platforms  单向平台矩形列表（pygame.Rect，整数坐标，32×16）

    返回 (new_x, new_y, on_ground, hit_ceiling, hit_wall)：
        on_ground   — 本帧落在平面上（固体或平台）
        hit_ceiling — 本帧撞到天花板
        hit_wall    — 1=撞右侧墙  -1=撞左侧墙  0=无

    单向平台特性：
    - 只有向下移动时（vsp > 0）且玩家在平台上方时才产生碰撞
    - 平台不产生 X 轴碰撞
    - 玩家必须从上方落到平台上才能站立
    """
    new_x = x + hsp
    new_y = y + vsp

    def overlap_at(cx, cy):
        hits = []
        for s in solids:
            if cx + w > s.left and cx < s.right and cy + h > s.top and cy < s.bottom:
                hits.append(s)
        return hits

    def platform_collision_at(cx, cy):
        """单向平台碰撞：只在向下移动且玩家在平台上方时产生碰撞。"""
        hits = []
        for p in platforms:
            # 水平范围重叠
            if cx + w > p.left and cx < p.right:
                # 玩家底部在平台顶部附近（允许轻微穿透）
                player_bottom = cy + h
                if player_bottom >= p.top - 2 and player_bottom <= p.bottom:
                    # 玩家原本必须在平台上方（不能从太深处穿透）
                    if y + h <= p.top + 2:
                        hits.append(p)
        return hits

    on_ground = False
    hit_ceiling = False
    hit_wall = 0

    # ---- X 轴：移动 -> 检测 -> 修正（只检测固体，不检测平台）----
    if hsp > 0:
        hits = overlap_at(new_x, y)
        if hits:
            hit_wall = 1
            new_x = min(s.left for s in hits) - w
    elif hsp < 0:
        hits = overlap_at(new_x, y)
        if hits:
            hit_wall = -1
            new_x = max(s.right for s in hits)

    # ---- Y 轴：移动 -> 检测 -> 修正（固体 + 平台）----
    if vsp > 0:
        # 向下移动：检测固体和平台
        # 优先检测固体
        hits = overlap_at(new_x, new_y)
        if hits:
            on_ground = True
            new_y = min(s.top for s in hits) - h
        else:
            # 没有固体，检测平台
            plat_hits = platform_collision_at(new_x, new_y)
            if plat_hits:
                on_ground = True
                new_y = min(p.top for p in plat_hits) - h
    elif vsp < 0:
        # 向上移动：只检测固体（平台不阻挡向上跳跃）
        hits = overlap_at(new_x, new_y)
        if hits:
            hit_ceiling = True
            new_y = max(s.bottom for s in hits)

    return new_x, new_y, on_ground, hit_ceiling, hit_wall
