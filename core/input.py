"""
core/input.py — 帧级输入状态

提供 按住 / 按下 / 松开 三个维度的查询（基于帧间对比，符合帧级物理约定）。
"""

import pygame

import config


class InputState:
    """每帧 begin_frame() 快照一次按键状态，供实体查询。"""

    def __init__(self, keymap=None):
        self.keymap = keymap if keymap is not None else config.KEYMAP
        self._prev = {}
        self._cur = {}

    def begin_frame(self):
        self._prev = self._cur
        keys = pygame.key.get_pressed()
        self._cur = {
            name: any(keys[k] for k in codes)
            for name, codes in self.keymap.items()
        }

    def held(self, name):
        """当前是否按住。"""
        return self._cur.get(name, False)

    def pressed(self, name):
        """本帧刚按下（上升沿）。"""
        return self._cur.get(name, False) and not self._prev.get(name, False)

    def released(self, name):
        """本帧刚松开（下降沿）。"""
        return not self._cur.get(name, False) and self._prev.get(name, False)

    def copy_without_jump(self):
        """创建一个新的输入状态，但不包含跳跃输入（用于零段水阻止跳跃）。"""
        new_input = InputState(self.keymap)
        new_input._prev = self._prev.copy()
        new_input._cur = self._cur.copy()
        # 强制设置jump为False
        if "jump" in new_input._cur:
            new_input._cur["jump"] = False
        return new_input
