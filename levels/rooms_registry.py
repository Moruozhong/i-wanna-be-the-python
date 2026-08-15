"""
levels/rooms_registry.py — 房间注册表

阶段6：优先从 rooms/{name}.json 读取关卡；无 JSON / 解析失败时回退到内置 sample 房。
带内存缓存（避免切房时反复读盘）；地图被编辑器改动后可调 clear_cache() 刷新。
"""

import json
import os

import config
from levels.room import Room
from levels.sample_room import create_room001, create_room002

# 内置测试房（回退用；JSON 缺失或损坏时才用）
BUILTIN = {
    "room001": create_room001,
    "room002": create_room002,
}

_cache = {}


def clear_cache():
    """清空房间缓存（编辑器保存/重读地图后调用）。"""
    _cache.clear()


def room_path(name):
    return os.path.join(config.ROOMS_DIR, f"{name}.json")


def load_room(name):
    """按名字取一个 Room。JSON 优先，内置房回退；都没有返回 None。"""
    if name in _cache:
        return _cache[name]

    room = None
    path = room_path(name)
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            room = Room.from_json(data)
        except (OSError, ValueError) as exc:
            print(f"[rooms] {name} JSON 解析失败：{exc}，回退内置房")
            room = None

    if room is None:
        factory = BUILTIN.get(name)
        room = factory() if factory is not None else None

    if room is not None:
        _cache[name] = room
    return room
