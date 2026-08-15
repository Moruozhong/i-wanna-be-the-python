"""
core/debug_panel.py — F2 独立调试窗口（隐藏参数面板）

用 pygame-ce 的 pygame.Window 创建第二个小窗口，专门显示游戏内部参数，
不再盖在主画面底部。窗口由 App 管理生命周期：F2 开 → 建窗口；F2 关 /
点击窗口关闭 → 销毁。
"""

import pygame

import config
from core import save


class DebugPanel:
    """隐藏参数小窗口：深色主题，标签/值双栏配色。"""

    BG = (22, 24, 30)          # 整体背景
    ROW_ALT = (28, 31, 39)     # 偶数行微亮，便于逐行阅读
    TEXT_DIM = (140, 146, 160) # 标签
    TEXT_BRIGHT = (235, 238, 244)
    ACCENT = (96, 180, 255)    # 标题下划线 / 出口
    BORDER = (52, 58, 72)
    STATE_COLORS = {
        "play":  (120, 220, 120),
        "dying": (240, 160, 70),
        "dead":  (240, 90, 90),
        "won":   (255, 215, 0),
    }

    def __init__(self):
        w, h = 400, 400
        self.window = pygame.Window(
            size=(w, h),
            title="隐藏参数",
            position=(config.WINDOW_WIDTH + 12, 40),
        )
        self.surface = self.window.get_surface()

    def close(self):
        if self.window is not None:
            self.window.destroy()
        self.window = None

    def flip(self):
        if self.window is not None:
            self.window.flip()

    def _rows(self, scene):
        """返回 [(标签, 值, 颜色), ...]，逐行渲染。"""
        k = scene.kid
        fx = scene.death_fx
        st = self.STATE_COLORS.get(scene.state, self.TEXT_BRIGHT)
        ground = (120, 220, 120) if k.on_ground else (220, 120, 120)
        return [
            ("房间", scene.room.name, self.ACCENT),
            ("状态", scene.state, st),
            ("模式", f"{k.mode.upper()} 藤蔓格={scene._vine_cell}",
             (120, 220, 255) if k.mode == "vine" else self.TEXT_BRIGHT),
            ("坐标", f"({k.x:6.1f},{k.y:6.1f})", self.TEXT_BRIGHT),
            ("速度", f"hsp {k.hsp:+.2f}  vsp {k.vsp:+.2f}", self.TEXT_BRIGHT),
            ("地面", "是" if k.on_ground else "否", ground),
            ("跳跃已用", f"{k.jump_count}/{k.max_jumps}", self.TEXT_BRIGHT),
            ("动画", f"{k.anim}/{k.frame}", self.TEXT_BRIGHT),
            ("绘制坐标", str(k.last_draw_pos), self.TEXT_BRIGHT),
            ("Align", f"{k.align} (x%{config.ALIGN_MODULO})", self.TEXT_BRIGHT),
            ("尖刺区/固体/子弹", f"{len(scene.spike_masks)} / {len(scene.solids)} / {len(scene.bullets)}",
             self.TEXT_BRIGHT),
            ("死亡演出", f"t={fx.timer}/{fx.duration} 头={'有' if fx.head else '无'}",
             self.TEXT_BRIGHT),
            ("存档点", str(scene.active_checkpoint), (255, 215, 0)),
            ("存档文件", save.save_path(),
             (120, 220, 120) if scene.has_save_file else (140, 146, 160)),
            ("进度", "已持久化（重开继续）" if scene.has_save_file else "未存档（默认出生）",
             (120, 220, 120) if scene.has_save_file else (140, 146, 160)),
            ("出生", f"{scene.spawn_room}@{int(scene.spawn_pos[0])},{int(scene.spawn_pos[1])}",
             self.TEXT_BRIGHT),
            ("Checkpoints", str(scene.room.checkpoints), self.TEXT_DIM),
            ("出口", f"{[(e['tile'], e['target']) for e in scene.room.exits]}", self.ACCENT),
            ("终点", str(scene.room.end), (255, 120, 255)),
        ]

    def render(self, scene):
        s = self.surface
        w, h = s.get_size()
        s.fill(self.BG)

        # 标题栏
        title = config.get_font(17, bold=True).render("隐藏参数", True, (255, 255, 255))
        hint = config.get_font(13).render("F2 开关", True, self.TEXT_DIM)
        s.blit(title, (14, 7))
        s.blit(hint, (w - hint.get_width() - 14, 12))
        pygame.draw.line(s, self.ACCENT, (0, 36), (w, 36), 2)

        # 数据行：标签在左，值右对齐；偶数行微亮底
        font = config.get_font(15)
        y = 46
        row_h = 19
        for i, (label, value, color) in enumerate(self._rows(scene)):
            if i % 2 == 0:
                pygame.draw.rect(s, self.ROW_ALT, (0, y, w, row_h))
            lab = font.render(label, True, self.TEXT_DIM)
            val = font.render(str(value), True, color)
            s.blit(lab, (14, y + 2))
            s.blit(val, (w - val.get_width() - 14, y + 2))
            y += row_h

        # 边框
        pygame.draw.rect(s, self.BORDER, s.get_rect(), 1)
