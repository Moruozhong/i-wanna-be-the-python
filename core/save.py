"""
core/save.py — 持久化存档

Checkpoint 存档跨游戏会话保存到 save/save.json。
关闭游戏再打开，从最近一次存档的 Checkpoint 继续，不再从头开始。
删除 save/save.json 即重置。
"""

import json
import os

import config


def save_path():
    return os.path.join(config.SAVE_DIR, config.SAVE_FILE)


def has_save():
    return os.path.exists(save_path())


def load_save():
    """读取存档。无存档 / 损坏 / 结构错误返回 None。"""
    try:
        with open(save_path(), "r", encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, ValueError):
        return None
    if not isinstance(data, dict):
        return None
    return data


def write_save(spawn_room, spawn_pos, active_checkpoint, max_jumps=None):
    """写存档：出生房间、出生点像素坐标、激活的 Checkpoint（房间, tx, ty）。

    max_jumps：跳跃星星改的"最多跳跃次数"（段数），随存档一起保存，
    重开/复活时恢复；None 表示不记录（旧行为）。
    """
    os.makedirs(config.SAVE_DIR, exist_ok=True)
    data = {
        "spawn_room": spawn_room,
        "spawn_pos": [float(spawn_pos[0]), float(spawn_pos[1])],
        "active_checkpoint": list(active_checkpoint) if active_checkpoint else None,
        "max_jumps": int(max_jumps) if max_jumps else None,
    }
    with open(save_path(), "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def clear_save():
    """删除存档文件（重置进度）。"""
    path = save_path()
    if os.path.exists(path):
        os.remove(path)
