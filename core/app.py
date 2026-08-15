"""
core/app.py — 游戏主应用

职责：主窗口创建、50FPS 固定帧主循环、事件分发、场景切换。
固定 Room 摄像机：一个 Room 对应一个屏幕，无自由滚动。
F2：隐藏参数面板独立小窗口（pygame.Window），不再盖在主画面底部。
"""

import os

import pygame

import config
from core import settings
from core.assets import AssetManager
from core.debug_panel import DebugPanel
from core.game import GameScene
from core.sound import SoundManager


class App:
    def __init__(self):
        pygame.mixer.pre_init(44100, -16, 2, 512)   # 在 init 前预设，降低播放延迟
        pygame.init()
        self.title = settings.get_title()   # 自定义游戏标题（默认 config.TITLE）
        pygame.display.set_caption(self.title)
        self._apply_window_icon()           # 自定义程序图标（窗口图标）
        self.screen = pygame.display.set_mode(
            (config.WINDOW_WIDTH, config.WINDOW_HEIGHT))
        self.clock = pygame.time.Clock()
        self.running = True

        self.assets = AssetManager()
        self.assets.ensure_dirs()
        self.assets.report_missing()

        self.sounds = SoundManager()
        self.scene = GameScene(self.assets, sounds=self.sounds)

        # 启动自检：上/下是死键，shift+上/下 不应有任何反应。
        # 若 KEYMAP 缺失 up/down（旧进程/旧字节码），直接报错提示，而不是静默保留旧行为。
        assert "up" in config.KEYMAP and "down" in config.KEYMAP, \
            "config.KEYMAP 缺少死键 up/down——正在运行旧代码，请完全关闭游戏后重新运行 python main.py"
        print("[input] 死键已启用：普通模式 shift+上/下 不跳跃；藤蔓上按上自然下滑")

        self.debug_panel = None   # F2 隐藏参数小窗口（懒创建）

    def _apply_window_icon(self):
        """自定义程序图标：assets/{icon}，缩到 32×32 后设为窗口/任务栏图标。

        pygame 加载不了 .ico（Unsupported image format），但现代 .ico 内部
        嵌的是 PNG——提取内嵌 PNG 再加载。png 图标直接加载。
        """
        icon_name = settings.get_icon()
        if not icon_name:
            return
        path = os.path.join(config.ASSET_DIR, icon_name)
        if not os.path.exists(path):
            print(f"[icon] 图标文件不存在：{path}")
            return
        img = self._load_icon_surface(path)
        if img is None:
            print(f"[icon] 无法加载图标：{path}")
            return
        if img.get_size() != (32, 32):
            img = pygame.transform.smoothscale(img, (32, 32))
        try:
            pygame.display.set_icon(img)
        except pygame.error as exc:
            print(f"[icon] 设置窗口图标失败：{exc}")

    @staticmethod
    def _load_icon_surface(path):
        """加载图标为 Surface：pygame 直读；.ico 走"提取内嵌 PNG"兜底。"""
        try:
            return pygame.image.load(path)
        except pygame.error:
            pass
        if path.lower().endswith(".ico"):
            try:
                with open(path, "rb") as f:
                    data = f.read()
                idx = data.find(b"\x89PNG\r\n\x1a\n")   # 内嵌 PNG 签名
                if idx >= 0:
                    import io
                    return pygame.image.load(io.BytesIO(data[idx:]))
            except (OSError, pygame.error):
                pass
        return None

    def _update_caption(self):
        """窗口标题 = 游戏标题 + 游玩时长 + 死亡次数。"""
        m, s = divmod(self.scene.play_frames // config.FPS, 60)
        pygame.display.set_caption(
            f"{self.title}  ⏱ {m:02d}:{s:02d}  💀 {self.scene.death_count}")

    # ---------------- 事件 ----------------
    def handle_events(self):
        for event in pygame.event.get():
            # 调试窗口自身的事件（点右上角关闭）→ 只关面板，不退出游戏
            ev_win = getattr(event, "window", None)
            if (self.debug_panel is not None and ev_win is not None
                    and ev_win is self.debug_panel.window):
                if event.type in (pygame.WINDOWCLOSE, pygame.QUIT):
                    self.scene.show_params = False
                    self.debug_panel.close()
                    self.debug_panel = None
                continue
            if event.type == pygame.QUIT:
                self.running = False
            elif event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
                self.running = False
            else:
                self.scene.handle_event(event)

    # ---------------- 逻辑 ----------------
    def update(self):
        self.scene.update()
        # F2 开关 → 同步调试小窗口的生命周期
        if self.scene.show_params and self.debug_panel is None:
            self.debug_panel = DebugPanel()
        elif not self.scene.show_params and self.debug_panel is not None:
            self.debug_panel.close()
            self.debug_panel = None

    # ---------------- 渲染 ----------------
    def draw(self):
        self.scene.draw(self.screen)
        pygame.display.flip()
        if self.debug_panel is not None:
            self.debug_panel.render(self.scene)
            self.debug_panel.flip()

    # ---------------- 主循环 ----------------
    def run(self):
        while self.running:
            self.handle_events()
            self.update()
            self.draw()
            self._update_caption()        # 标题栏：标题 + 游玩时长 + 死亡次数
            self.clock.tick(config.FPS)   # 固定 50 FPS，物理按帧推进
        if self.debug_panel is not None:
            self.debug_panel.close()
        pygame.quit()
