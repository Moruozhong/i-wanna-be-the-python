"""core/bgrender.py — 背景填充模式渲染（游戏与编辑器共用）

把一张背景图按填充模式渲染成指定尺寸的 Surface。

模式：
    stretch = 拉伸铺满（默认）
    fill    = 等比铺满裁剪（cover）
    fit     = 等比完整显示，居中留 bg_color 边（contain）
    tile    = 原尺寸平铺
    center  = 原尺寸居中
    zoom    = 自定义缩放倍数 + 偏移（放大缩小选一部分）
"""

import pygame

import config


def render_background(img, bg_color, mode="stretch", zoom=1.0, offset=(0, 0),
                      size=None):
    """把 img 按 mode 渲染成 size（默认 800×608）的 Surface。

    参数：
        img     背景图 Surface
        bg_color 底色（fit/tile/center/zoom 的留边色）
        mode    填充模式
        zoom    zoom 模式缩放倍数（相对原图，>0）
        offset  zoom 模式偏移（像素，(dx, dy)）
        size    目标尺寸 (w, h)
    """
    if size is None:
        size = (config.ROOM_WIDTH, config.ROOM_HEIGHT)
    W, H = size
    iw, ih = img.get_size()
    mode = mode or "stretch"

    if mode == "fill":          # cover：等比铺满，溢出裁剪
        sc = max(W / iw, H / ih)
        nw, nh = max(1, int(iw * sc)), max(1, int(ih * sc))
        img2 = pygame.transform.smoothscale(img, (nw, nh))
        return img2.subsurface(((nw - W) // 2, (nh - H) // 2, W, H)).copy()
    if mode == "fit":           # contain：等比完整，居中留边
        sc = min(W / iw, H / ih)
        nw, nh = max(1, int(iw * sc)), max(1, int(ih * sc))
        img2 = pygame.transform.smoothscale(img, (nw, nh))
        surf = pygame.Surface((W, H))
        surf.fill(bg_color)
        surf.blit(img2, ((W - nw) // 2, (H - nh) // 2))
        return surf
    if mode == "tile":          # 原尺寸平铺
        surf = pygame.Surface((W, H))
        surf.fill(bg_color)
        for y in range(0, H, ih):
            for x in range(0, W, iw):
                surf.blit(img, (x, y))
        return surf
    if mode == "center":        # 原尺寸居中
        surf = pygame.Surface((W, H))
        surf.fill(bg_color)
        surf.blit(img, ((W - iw) // 2, (H - ih) // 2))
        return surf
    if mode == "zoom":          # 自定义缩放 + 偏移
        sc = max(0.1, zoom or 1.0)
        nw, nh = max(1, int(iw * sc)), max(1, int(ih * sc))
        img2 = pygame.transform.smoothscale(img, (nw, nh))
        dx, dy = offset or (0, 0)
        surf = pygame.Surface((W, H))
        surf.fill(bg_color)
        # 偏移语义：窗口中心 = 缩放图中心 + (dx,dy)（与编辑器选择框一致，
        # 正 dx 显示图右侧部分），故 blit 位置用 -dx/-dy。
        surf.blit(img2, (int((W - nw) // 2 - dx), int((H - nh) // 2 - dy)))
        return surf
    # stretch（默认）：拉伸铺满
    return pygame.transform.smoothscale(img, (W, H))
