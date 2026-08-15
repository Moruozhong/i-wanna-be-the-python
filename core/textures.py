"""core/textures.py — 房间自定义材质（object 贴图替换）

房间 JSON 的 `textures` 字段：{ 贴图键 -> assets/textures/ 下的图片文件名 }。
绘制时用 `texture_for()` 取图：有自定义材质就**缩放到默认贴图尺寸**后替换，
没有（或文件缺失）就用默认贴图。缩放保证与碰撞箱/网格对齐。

**贴图键（按子类型，编辑器「材质」面板选择）**：
    tile:block_0..8        砖块逐种        star:1/2/3        星星逐段
    water:first/second/zero 水逐种         checkpoint:inactive/active 存档两图
    spike:up/down/left/right 尖刺逐向      mini_spike:up/down/left/right 小刺逐向
    vine:left/right         藤蔓逐侧
    platform / door(出口终点) / plus_jump  单贴图对象（无子类型）

**粗粒度兜底**：设了 `tile`（全部）或 `star`（全部）等不带子类型的键时，
所有子类型都用它（如 `tile:block_3` 未设置 → 用 `tile`）。
"""

import pygame


def texture_for(assets, room, key, default_surface):
    """返回该房间 key 对应的贴图。

    Args:
        assets: AssetManager
        room: Room（读取 room.textures）
        key: 贴图键（如 "tile:block_3" / "platform"）
        default_surface: 默认贴图（Surface），自定义材质按其尺寸缩放
    Returns:
        替换后的 Surface（可能引用 default_surface 本身）
    """
    name = room.textures.get(key)
    if name is None and ":" in key:
        name = room.textures.get(key.split(":", 1)[0])   # 粗粒度（全部）兜底
    if name:
        img = assets.custom_texture(name)
        if img is not None:
            target = default_surface.get_size()
            if img.get_size() != target:
                try:
                    img = pygame.transform.smoothscale(img, target)
                except (ValueError, pygame.error):
                    return default_surface
            return img
    return default_surface

