"""tests/test_music.py — 背景音乐回归测试（无头运行）

覆盖：
  1. MusicManager 状态机：播放/自计时/淡出记住位置/复活续播（位置不归零）
  2. 曲目长度取模：淡出位置超出曲长时折回
  3. 切歌重置：换房间新歌从头放、同歌保持
  4. 游戏集成：房间 bgm → 场景启动播放；死亡淡出记住位置；复活从该位置续播

音频设备无关：enabled=False 或无声卡时，状态机照常推进（音频调用静默）。

用法：python tests/test_music.py
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.stdout.reconfigure(encoding="utf-8")
os.environ.setdefault("SDL_VIDEODRIVER", "dummy")

import pygame
pygame.init()

import config
from core import save
from core import settings as msettings
from core.assets import AssetManager
from core.game import GameScene
from core.sound import MusicManager
from levels.room import Room


def main():
    msettings.set_default_bgm(None)   # 封闭性：清掉默认音乐设置
    # ---- 1. 状态机：播放 → 淡出记住位置 → 复活从该位置续播 ----
    mm = MusicManager(enabled=False)     # 无音频：只测状态
    mm.play("track_a.mp3")
    assert mm._current == "track_a.mp3" and mm._playing
    assert mm._elapsed == 0.0
    for _ in range(100):                 # 播放 2 秒（50FPS）
        mm.update()
    assert abs(mm._elapsed - 2.0) < 1e-6, mm._elapsed
    mm.fade_out_and_remember()
    assert not mm._playing, "淡出后应停止播放"
    paused = mm._paused_at
    assert paused > 0, f"淡出应记住位置，实际 {paused}"
    for _ in range(50):                  # 淡出后不应再推进
        mm.update()
    assert mm._elapsed == paused, "淡出后自计时不应继续"
    mm.resume()
    assert mm._playing and mm._elapsed == paused, \
        f"复活应从淡出位置续播（{paused}），实际 {mm._elapsed}"
    assert mm._fade_in_left > 0, "复活应带淡入"
    for _ in range(10):
        mm.update()
    assert abs(mm._elapsed - (paused + 0.2)) < 1e-6, mm._elapsed
    print(f"PASS 1 状态机：淡出记住位置 {paused:.2f}s，复活从此续播")

    # ---- 2. 曲目长度取模：位置超曲长折回 ----
    mm2 = MusicManager(enabled=False)
    mm2._lengths["loop.mp3"] = 5.0       # 假曲长 5 秒
    mm2.play("loop.mp3")
    for _ in range(600):                 # 播放 12 秒（> 曲长 5 秒）
        mm2.update()
    assert abs(mm2._elapsed - 12.0) < 1e-6
    mm2.fade_out_and_remember()
    assert abs(mm2._paused_at - 2.0) < 1e-6, \
        f"12s % 5s 应记住 2.0s，实际 {mm2._paused_at}"
    print(f"PASS 2 曲长取模：12s 播放淡出记住 {mm2._paused_at:.2f}s（折回）")

    # ---- 3. 切歌重置 / 同歌保持 / 停止 ----
    mm3 = MusicManager(enabled=False)
    mm3.play("a.mp3")
    for _ in range(100):
        mm3.update()
    mm3.play("b.mp3")                    # 换歌 → 从头
    assert mm3._current == "b.mp3" and mm3._elapsed == 0.0
    for _ in range(50):
        mm3.update()
    mm3.play("b.mp3")                    # 同歌 → 不打断
    assert abs(mm3._elapsed - 1.0) < 1e-6, "同歌不应重置位置"
    mm3.play(None)                       # 停止
    assert mm3._current is None and not mm3._playing
    print("PASS 3 切歌重置 / 同歌保持 / 停止")

    # ---- 4. 游戏集成：房间 bgm 启动 → 死亡淡出记住 → 复活续播 ----
    save.clear_save()
    room = Room(name="music_test", bg_color=config.BG_COLOR)
    room.bgm = "track_b.mp3"
    for tx in range(config.GRID_COLS):          # 铺地板，防出生坠落死亡
        room.set_tile(tx, 17, "block_0")
        room.set_tile(tx, 18, "block_0")
    scene = GameScene(AssetManager(), room=room)
    assert scene.music._current == "track_b.mp3", "场景应播放房间 BGM"
    for _ in range(100):
        scene.update()
    assert scene.music._elapsed > 1.5, "播放中自计时应推进"
    # 换房间：无 BGM → 停止
    room2 = Room(name="music_test2", bg_color=config.BG_COLOR)
    for tx in range(config.GRID_COLS):
        room2.set_tile(tx, 17, "block_0")
        room2.set_tile(tx, 18, "block_0")
    scene.reload_room(room2)
    assert scene.music._current is None, "无 BGM 房间应停止音乐"
    # 换回有 BGM 的房间 → 新歌从头
    scene.reload_room(room)
    assert scene.music._current == "track_b.mp3" and scene.music._elapsed == 0.0
    for _ in range(50):
        scene.update()
    # 死亡 → 淡出记住位置
    scene._die()
    assert not scene.music._playing
    paused = scene.music._paused_at
    assert paused > 0, "死亡应记住 BGM 位置"
    # 复活 → 从该位置续播（不从头）
    scene.state = "dead"
    scene._respawn()
    assert scene.music._playing and scene.music._elapsed == paused, \
        f"复活应从 {paused:.2f}s 续播，实际 {scene.music._elapsed}"
    print(f"PASS 4 游戏集成：房间 BGM 启动/切房/死亡记住 {paused:.2f}s/复活续播")

    # ---- 5. 默认音乐：无 bgm 的房间自动播默认；有 bgm 优先用自己的 ----
    msettings.set_default_bgm("default_song.mp3")
    room_none = Room(name="no_bgm_room", bg_color=config.BG_COLOR)
    for tx in range(config.GRID_COLS):
        room_none.set_tile(tx, 17, "block_0")
        room_none.set_tile(tx, 18, "block_0")
    scene5 = GameScene(AssetManager(), room=room_none)
    assert scene5.music._current == "default_song.mp3", \
        "无 bgm 房间应自动播放默认音乐"
    room_own = Room(name="own_bgm_room", bg_color=config.BG_COLOR)
    room_own.bgm = "own_song.mp3"
    for tx in range(config.GRID_COLS):
        room_own.set_tile(tx, 17, "block_0")
        room_own.set_tile(tx, 18, "block_0")
    scene5.reload_room(room_own)
    assert scene5.music._current == "own_song.mp3", "有 bgm 房间应优先用自己的"
    # 清掉默认 → 无 bgm 房间无音乐
    msettings.set_default_bgm(None)
    scene5.reload_room(room_none)
    assert scene5.music._current is None, "清默认后无 bgm 房间应无音乐"
    if os.path.exists(msettings.SETTINGS_PATH):
        os.remove(msettings.SETTINGS_PATH)
    print("PASS 5 默认音乐：无 bgm 房间自动播默认，有 bgm 优先自己")

    print("\n全部 PASS：背景音乐（死亡淡出 → 复活从淡出位置续播）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
