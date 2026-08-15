"""
core/sound.py — 音效 / 背景音乐管理器

* 懒加载：首次 play 时才读取 WAV 并缓存
* 健壮性：mixer 初始化失败 / 文件缺失时自动静音，不影响游戏运行
* 主开关：config.SOUND_ENABLED 关闭所有音效（无头测试可置 False）
* MusicManager：房间自定义 BGM——死亡淡出，复活**从淡出位置续播**
  （不从头放）；状态机与音频设备解耦，无声卡时逻辑照常可测。
"""

import os

import pygame

import config


class SoundManager:
    def __init__(self, enabled=None):
        self.enabled = config.SOUND_ENABLED if enabled is None else enabled
        self._sounds = {}
        self._ensure_mixer()

    def _ensure_mixer(self):
        if not self.enabled:
            return
        if pygame.mixer.get_init() is None:
            try:
                pygame.mixer.init()
            except pygame.error:
                self.enabled = False
                print("[sound] 无音频设备，已静音")

    def play(self, name):
        """播放一个音效（无则忽略）。name 为 config.SOUND_FILES 的键。"""
        if not self.enabled or name not in config.SOUND_FILES:
            return
        sound = self._sounds.get(name)
        if sound is None:
            path = os.path.join(config.SOUND_DIR, config.SOUND_FILES[name])
            try:
                sound = pygame.mixer.Sound(path)
            except (pygame.error, OSError) as exc:
                print(f"[sound] 加载 {path} 失败：{exc}，已静音")
                self.enabled = False
                return
            self._sounds[name] = sound
        sound.play()


class MusicManager:
    """背景音乐管理器：每房间一份 BGM（文件名），循环播放。

    死亡 → fade_out_and_remember()：淡出并记住播放位置；
    复活 → resume()：**从淡出位置**淡入续播（不从头放）。
    切房间 → play(new_bgm)：新歌从头放；同歌则保持连续播放。

    播放位置用**自计时**（update() 每帧累加）而非 get_pos()，避免
    循环曲目位置语义差异；再用曲目长度取模，保证 start 参数合法。
    无音频设备 / 文件缺失时音频部分静默，但状态机照常推进（可无头测试）。
    """

    def __init__(self, enabled=None):
        self.enabled = config.SOUND_ENABLED if enabled is None else enabled
        self._current = None       # 当前音乐文件名（None = 无）
        self._elapsed = 0.0        # 当前曲目已播放秒数（自计时）
        self._paused_at = 0.0      # 淡出时记住的位置（秒）
        self._playing = False      # 逻辑播放状态（与音频设备无关）
        self._lengths = {}         # 文件名 -> 曲目长度秒数（取模用，未知=None）
        self._fade_in_left = 0     # 淡入剩余帧数
        self._check_mixer()

    def _check_mixer(self):
        if not self.enabled:
            return
        try:
            if pygame.mixer.get_init() is None:
                pygame.mixer.init()
        except pygame.error:
            self.enabled = False
            print("[music] 无音频设备，已静音")

    def _ok(self):
        return self.enabled and pygame.mixer.get_init() is not None

    def _path(self, file):
        return os.path.join(config.MUSIC_DIR, file)

    def _track_length(self, file):
        """曲目长度（秒），取不到返回 None。缓存结果。"""
        if file in self._lengths:
            return self._lengths[file]
        length = None
        try:
            length = pygame.mixer.Sound(self._path(file)).get_length()
        except (pygame.error, OSError):
            pass
        self._lengths[file] = length
        return length

    def play(self, file, restart=False):
        """播放/切换背景音乐（循环）。file=None 停止。

        restart=False 且 file == 当前曲目 → 保持播放（切房同歌不打断）。
        逻辑播放状态永远跟踪（文件缺失/无音频也不影响状态机，音频部分静默）。
        """
        if file == self._current and not restart:
            return
        self._current = file
        self._elapsed = 0.0
        self._paused_at = 0.0
        self._fade_in_left = 0
        self._playing = file is not None
        if not self._ok():
            return
        if not file:
            try:
                pygame.mixer.music.stop()
            except pygame.error:
                pass
            return
        try:
            pygame.mixer.music.load(self._path(file))
            pygame.mixer.music.play(loops=-1)
            pygame.mixer.music.set_volume(1.0)
        except (pygame.error, OSError) as exc:
            print(f"[music] 加载 {self._path(file)} 失败：{exc}")

    def update(self):
        """每帧推进：自计时 + 复活淡入音量斜坡。"""
        if self._playing:
            self._elapsed += 1.0 / config.FPS
        if self._fade_in_left > 0 and self._ok():
            self._fade_in_left -= 1
            try:
                vol = max(0.0, self._fade_in_left / config.MUSIC_FADE_IN_FRAMES)
                pygame.mixer.music.set_volume(1.0 - vol)
            except pygame.error:
                pass

    def fade_out_and_remember(self, fade_ms=None):
        """淡出当前 BGM 并记住播放位置（死亡时调用）。"""
        if self._current is None:
            return
        length = self._track_length(self._current)
        self._paused_at = (self._elapsed % length) if length else self._elapsed
        self._playing = False
        self._fade_in_left = 0
        if self._ok():
            try:
                pygame.mixer.music.fadeout(fade_ms or config.MUSIC_FADE_OUT_MS)
            except pygame.error:
                pass

    def resume(self):
        """从记住的位置淡入续播（复活时调用）。"""
        if self._current is None:
            return
        self._playing = True
        self._elapsed = self._paused_at
        self._fade_in_left = config.MUSIC_FADE_IN_FRAMES
        if not self._ok():
            return
        try:
            length = self._track_length(self._current)
            start = (self._paused_at % length) if length else self._paused_at
            pygame.mixer.music.play(loops=-1, start=start)
            pygame.mixer.music.set_volume(0.0)   # 由 update() 淡入
        except (pygame.error, OSError) as exc:
            print(f"[music] 续播 {self._path(self._current)} 失败：{exc}")

    def stop(self):
        """完全停止（编辑器试听停止 / 无音乐房间）。"""
        self.play(None)
