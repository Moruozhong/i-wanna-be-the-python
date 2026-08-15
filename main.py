"""
main.py — 项目入口

用法：
    python main.py            启动游戏（阶段1为占位画面，后续为实际关卡）
    python main.py --editor   启动地图编辑器（阶段7实现）
"""

import argparse
import sys

# Windows 控制台/管道下强制 UTF-8，避免中文提示乱码
for stream in (sys.stdout, sys.stderr):
    if hasattr(stream, "reconfigure"):
        try:
            stream.reconfigure(encoding="utf-8")
        except Exception:
            pass


def main():
    parser = argparse.ArgumentParser(description="I Wanna (Python) 引擎")
    parser.add_argument("--editor", action="store_true", help="启动地图编辑器")
    parser.add_argument("--water-test", action="store_true", help="加载水测试房间")
    args = parser.parse_args()

    if args.editor:
        from editor.editor import Editor
        Editor().run()
        sys.exit(0)

    from core.app import App

    if args.water_test:
        # Load water test room
        from levels.room import Room
        import json
        with open(os.path.join(config.ROOMS_DIR, "water_test_room.json"),
                  "r", encoding="utf-8") as f:
            data = json.load(f)
        water_room = Room.from_json(data)
        app = App()
        app.scene.room = water_room
        app.scene.solids = app.scene.room.solid_rects()
        app.scene.spike_masks = app.scene._build_spike_masks()
        app.scene.end_rect = app.scene._build_end_rect()
        app.scene.platforms = app.scene._build_platform_rects()
        app.scene.vines = app.scene.room.vines
        app.scene.free_vines = app.scene.room.free_vines
        app.scene._vine_cell = None
        app.scene.vine_barriers = app.scene._build_vine_barriers()
        app.scene._build_water_tiles()
        app.scene.in_water = None
        app.scene.kid.reset(*app.scene.room.start)
        app.run()
    else:
        App().run()


if __name__ == "__main__":
    main()
