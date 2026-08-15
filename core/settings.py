"""core/settings.py — 项目级共享设置（编辑器与游戏共用，持久化 JSON）

设置项：
    default_bgm  默认背景音乐（没单独设 bgm 的房间自动播放）
    title        游戏标题（窗口标题 / 打包 exe 名）
    icon         程序图标文件名（assets/ 下，建议 .ico；exe 图标 + 窗口图标）
"""

import json
import os

import config

SETTINGS_PATH = os.path.join(config.DATA_DIR, "editor_settings.json")


def load_settings():
    """读取设置字典（损坏/缺失 → 空字典，不报错）。"""
    try:
        with open(SETTINGS_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def _save(data):
    os.makedirs(os.path.dirname(SETTINGS_PATH), exist_ok=True)
    with open(SETTINGS_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def get_default_bgm():
    """默认背景音乐文件名（None = 无默认）。"""
    value = load_settings().get("default_bgm")
    return value if isinstance(value, str) and value else None


def set_default_bgm(name):
    """设置默认背景音乐文件名（None 清除）。"""
    data = load_settings()
    data["default_bgm"] = name
    _save(data)


def get_title():
    """游戏标题（未设置 → config.TITLE）。"""
    value = load_settings().get("title")
    return value if isinstance(value, str) and value.strip() else config.TITLE


def set_title(title):
    """设置游戏标题（None/空 → 用默认 config.TITLE）。"""
    data = load_settings()
    data["title"] = title.strip() if isinstance(title, str) and title.strip() \
        else None
    _save(data)


def get_icon():
    """程序图标文件名（assets/ 下；None = 无自定义图标）。"""
    value = load_settings().get("icon")
    return value if isinstance(value, str) and value else None


def set_icon(name):
    """设置程序图标文件名（None 清除）。"""
    data = load_settings()
    data["icon"] = name if isinstance(name, str) and name else None
    _save(data)
