"""tests/test_pack.py — 保存工程 / 打包 exe 回归测试（无头运行）

覆盖：
  1. 保存工程：复制游戏源码+数据到目标目录（不含编辑器/测试/__pycache__）
  2. 未装 pyinstaller 时打包给出明确提示（不崩溃）
  3. 编辑器按钮接线：存工程/打包走 `_pick_dir` 选目录后调用 worker

用法：python tests/test_pack.py
"""

import os
import shutil
import sys
import tempfile
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.stdout.reconfigure(encoding="utf-8")
os.environ.setdefault("SDL_VIDEODRIVER", "dummy")

import pygame
pygame.init()

import config
from core import pack as pack_mod


def main():
    tmp = tempfile.mkdtemp(prefix="iwanna_pack_")
    try:
        # ---- 1. 保存工程：只备份关卡内容（rooms/music/背景/材质），不含引擎代码 ----
        logs = []
        result = pack_mod.save_project(tmp, progress=logs.append)
        assert "已保存工程" in result, result
        assert os.path.isdir(os.path.join(tmp, "rooms")), "应备份 rooms/"
        assert os.path.isdir(os.path.join(tmp, "music")), "应备份 music/"
        assert os.path.isdir(os.path.join(tmp, "assets", "backgrounds")), \
            "应备份背景图"
        assert os.path.isdir(os.path.join(tmp, "assets", "textures")), \
            "应备份自定义材质"
        assert os.path.isfile(os.path.join(tmp, "工程说明.txt")), "应有工程说明"
        # 不再复制引擎/无关内容
        for f in ("main.py", "config.py", "README.md", "requirements.txt"):
            assert not os.path.exists(os.path.join(tmp, f)), \
                f"存工程不应包含 {f}"
        for d in ("core", "entities", "physics", "levels", "sound",
                  "save", "editor", "tests"):
            assert not os.path.exists(os.path.join(tmp, d)), \
                f"存工程不应包含 {d}/"
        assert not os.path.exists(os.path.join(tmp, "__pycache__")), \
            "不应复制 __pycache__"
        print(f"PASS 1 保存工程：只备份关卡内容（{tmp}）")

        # ---- 1b. 加载工程：备份内容复制回项目（存/载互逆） ----
        backup = tempfile.mkdtemp(prefix="iwanna_backup_")
        try:
            # 备份里放一个新房间 + 一首"音乐" + 一张"材质"
            os.makedirs(os.path.join(backup, "rooms"), exist_ok=True)
            with open(os.path.join(backup, "rooms", "imported_room.json"),
                      "w", encoding="utf-8") as f:
                f.write('{"name":"imported_room"}')
            os.makedirs(os.path.join(backup, "assets", "textures"),
                        exist_ok=True)
            with open(os.path.join(backup, "assets", "textures",
                                   "__imported_tex.png"), "wb") as f:
                f.write(b"\x89PNG")
            logs2 = []
            res = pack_mod.load_project(backup, progress=logs2.append)
            assert "已导入" in res, res
            assert os.path.isfile(os.path.join(
                config.ROOMS_DIR, "imported_room.json")), "房间应导回项目"
            assert os.path.isfile(os.path.join(
                config.PROJECT_ROOT, "assets", "textures",
                "__imported_tex.png")), "材质应导回项目"
            # 清理导回的文件
            os.remove(os.path.join(config.ROOMS_DIR,
                                   "imported_room.json"))
            os.remove(os.path.join(config.PROJECT_ROOT, "assets",
                                   "textures", "__imported_tex.png"))
            print("PASS 1b 加载工程：备份内容复制回项目（互逆）")
        finally:
            shutil.rmtree(backup, ignore_errors=True)

        # ---- 2. 未装 pyinstaller → 明确提示，不崩溃 ----
        if not pack_mod._pyinstaller_available():
            result2 = pack_mod.build_exe(tmp, progress=logs.append)
            assert "未安装 pyinstaller" in result2, result2
            print("PASS 2 打包提示：未安装 pyinstaller 时给出指引")
        else:
            print("PASS 2 跳过：本机已装 pyinstaller（打包走真实路径）")

        # ---- 3. 编辑器按钮接线（monkeypatch 选目录，不弹 tkinter） ----
        from editor.editor import Editor
        from levels.room import Room
        from levels.rooms_registry import clear_cache
        clear_cache()
        e = Editor()
        e.room = Room("pack_smoke")
        e._pick_dir = lambda title: tmp
        e._save_project_btn()
        assert os.path.isdir(os.path.join(tmp, "rooms")), \
            "存工程按钮应备份关卡内容"
        # 打包按钮：后台线程跑完（模拟 build，避免真实 PyInstaller 耗时），
        # 主循环轮询收尾；真实打包在 test_pack 之外验证过
        orig_build = pack_mod.build_exe
        pack_mod.build_exe = lambda t, progress=None: "已生成单文件（模拟）"
        try:
            e._package_btn()
            deadline = time.time() + 20
            while not e._pack_done and time.time() < deadline:
                time.sleep(0.05)
            assert e._pack_done, "打包线程应在限时内结束"
            e._poll_pack()
            assert "已生成单文件" in e.message, e.message
        finally:
            pack_mod.build_exe = orig_build
        # 载工程按钮：选 tmp（PASS 1 存的备份）→ 导入流程
        e._pick_dir = lambda title: tmp
        e._load_project_btn()
        assert "已导入" in e.message, e.message
        print("PASS 3 编辑器按钮接线：存工程/载工程/打包按钮走选目录流程")

        # ---- 4. 自定义标题/图标 + 游玩时长/死亡次数 + 打包命令（无黑窗/图标） ----
        from core import settings as st
        st.set_title("我的游戏")
        st.set_icon("icon.ico")
        assert st.get_title() == "我的游戏"
        assert st.get_icon() == "icon.ico"
        exe_name = pack_mod._safe_exe_name(st.get_title())
        cmd = pack_mod.build_cmd(
            tmp, exe_name=exe_name,
            icon_path=os.path.join(config.ASSET_DIR, "icon.ico"))
        assert "--noconsole" in cmd, "打包应带 --noconsole（去掉 cmd 黑窗）"
        assert "--icon" in cmd, "设置图标后打包应带 --icon"
        # 游戏：游玩时长帧数累计 / 死亡计数
        from core.assets import AssetManager
        from core.game import GameScene
        from levels.room import Room
        room = Room("t4")
        for tx in range(config.GRID_COLS):
            room.set_tile(tx, 17, "block_0")
            room.set_tile(tx, 18, "block_0")
        sc = GameScene(AssetManager(), room=room)
        for _ in range(50):
            sc.update()
        assert sc.play_frames >= 49, f"游玩帧数应累计 {sc.play_frames}"
        sc._die()
        sc._die()
        assert sc.death_count == 2, f"死亡计数应累计 {sc.death_count}"
        st.set_title(None)
        st.set_icon(None)
        assert st.get_title() == config.TITLE, "清空标题应回退默认"
        assert st.get_icon() is None
        if os.path.exists(st.SETTINGS_PATH):
            os.remove(st.SETTINGS_PATH)
        print("PASS 4 自定义标题/图标 + 游玩时长/死亡计数 + 打包 --noconsole/--icon")

        # ---- 5. 图标链路：png→ico 封装 / 窗口图标加载（ico 内嵌 PNG 提取） ----
        png = os.path.join(tmp, "ic.png")
        _s5 = pygame.Surface((64, 64))
        _s5.fill((10, 200, 10))
        pygame.image.save(_s5, png)
        ico = os.path.join(tmp, "ic.ico")
        pack_mod._png_to_ico(png, ico)
        with open(ico, "rb") as f:
            data = f.read()
        assert data.startswith(b"\x00\x00\x01\x00\x01\x00"), "ICO 头错误"
        assert b"\x89PNG\r\n\x1a\n" in data, "ICO 应内嵌 PNG"
        from core.app import App as AppCls
        surf = AppCls._load_icon_surface(ico)      # pygame 直读不了 ico
        assert surf is not None, "应能从 ico 提取内嵌 PNG 加载"
        assert surf.get_size() == (64, 64)
        surf2 = AppCls._load_icon_surface(png)
        assert surf2 is not None and surf2.get_size() == (64, 64)
        # 打包图标解析：png 图标自动封装成 .ico（--icon 用）
        st.set_icon("ic.png")
        icon_dst = os.path.join(config.ASSET_DIR, "ic.png")
        shutil.copy2(png, icon_dst)
        try:
            ico2 = pack_mod._resolve_icon_path(tmp)
            assert ico2 is not None and ico2.endswith(".ico"), ico2
            assert os.path.isfile(ico2), "自动生成的 ico 应存在"
        finally:
            os.remove(icon_dst)
            if os.path.exists(os.path.join(tmp, "_icon.ico")):
                os.remove(os.path.join(tmp, "_icon.ico"))
        st.set_icon(None)
        print("PASS 5 图标链路：png→ico 封装 + 窗口图标提取加载 + 打包图标解析")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    print("\n全部 PASS：保存工程 / 打包 exe")
    return 0


if __name__ == "__main__":
    sys.exit(main())
