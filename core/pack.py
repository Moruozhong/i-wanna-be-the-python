"""core/pack.py — 编辑器：保存工程 / 打包为 exe

保存工程：只备份**你的关卡内容**（rooms/ 关卡、music/ 音乐、
assets/backgrounds/ 背景图、assets/textures/ 自定义材质）——不含引擎代码。
打包为 exe：PyInstaller 单文件，用 --add-data 把 assets/sound/music/rooms
**打进 exe 内部**（运行时从临时解包目录读，只读）；输出只有 1 个 exe 文件。
存档 save/ 写在 **exe 旁边**（config 的 sys.frozen 分支：
BASE_DIR = exe 目录 / DATA_DIR = 内置数据），重开游戏进度仍在。
"""

import os
import shutil
import subprocess
import sys

import config
from core import settings

# 存工程 = 备份用户自己的内容（不含引擎代码）
PROJECT_CONTENT_DIRS = [
    ("rooms", "关卡"),
    ("music", "背景音乐"),
    ("assets/backgrounds", "背景图"),
    ("assets/textures", "自定义材质"),
]
SETTINGS_REL = "editor_settings.json"    # 项目设置（标题/图标）随工程一起备份

README_TXT = """本文件夹是「I Wanna」关卡工程备份，包含：
{content}

不含引擎代码（引擎在开发目录/打包 exe 里）。
"""


def _copy_into(src_root, names, dst_root, progress=None):
    for n in names:
        s = os.path.join(src_root, n)
        if not os.path.exists(s):
            continue
        d = os.path.join(dst_root, n)
        if os.path.isdir(s):
            if progress:
                progress(f"复制 {n}/ ...")
            shutil.copytree(s, d, dirs_exist_ok=True,
                            ignore=shutil.ignore_patterns("__pycache__",
                                                          "*.pyc"))
        else:
            os.makedirs(os.path.dirname(d), exist_ok=True)
            shutil.copy2(s, d)


def save_project(target_dir, progress=None):
    """保存工程：只备份关卡内容（rooms/music/背景图/自定义材质）。"""
    if progress:
        progress("保存工程（仅关卡内容）...")
    os.makedirs(target_dir, exist_ok=True)
    content_lines = []
    for rel, label in PROJECT_CONTENT_DIRS:
        if os.path.isdir(os.path.join(config.PROJECT_ROOT, rel)):
            content_lines.append(f"  {rel}/（{label}）")
            _copy_into(config.PROJECT_ROOT, [rel], target_dir, progress)
    # 项目设置（游戏标题/图标）随工程备份
    s_src = os.path.join(config.PROJECT_ROOT, SETTINGS_REL)
    if os.path.isfile(s_src):
        shutil.copy2(s_src, os.path.join(target_dir, SETTINGS_REL))
        content_lines.append(f"  {SETTINGS_REL}（项目设置：标题/图标）")
    with open(os.path.join(target_dir, "工程说明.txt"), "w",
              encoding="utf-8") as f:
        f.write(README_TXT.format(content="\n".join(content_lines)))
    return f"已保存工程（关卡/音乐/背景/材质）到 {target_dir}"


def load_project(source_dir, progress=None):
    """加载工程：把备份内容复制回项目（rooms/music/背景/材质），同名覆盖。

    与 save_project 互逆；旧版"整包"备份同样可导入（都含这些目录）。
    """
    imported = []
    for rel, label in PROJECT_CONTENT_DIRS:
        s = os.path.join(source_dir, rel)
        if not os.path.isdir(s):
            continue
        d = os.path.join(config.PROJECT_ROOT, rel)
        os.makedirs(d, exist_ok=True)
        n = 0
        for f in os.listdir(s):
            src_f = os.path.join(s, f)
            if os.path.isfile(src_f):
                shutil.copy2(src_f, os.path.join(d, f))
                n += 1
        if n:
            imported.append(f"{label}×{n}")
            if progress:
                progress(f"导入 {label} {n} 个文件...")
    if not imported:
        return "没有找到可导入的内容（备份里缺少 rooms/ 等目录）"
    # 项目设置（标题/图标）导回
    s_src = os.path.join(source_dir, SETTINGS_REL)
    if os.path.isfile(s_src):
        shutil.copy2(s_src, os.path.join(config.PROJECT_ROOT, SETTINGS_REL))
        imported.append("项目设置（标题/图标）")
    return "已导入工程：" + "、".join(imported)


def _pyinstaller_available():
    import importlib.util
    return importlib.util.find_spec("PyInstaller") is not None


def _safe_exe_name(title):
    """把游戏标题转成合法文件名（去掉非法字符），空则回退 I Wanna。"""
    cleaned = "".join(c for c in title if c.isalnum() or c in " _-").strip()
    return cleaned or "I Wanna"


def _png_to_ico(png_path, ico_path):
    """把 PNG 封装成 .ico（内嵌 PNG 的 ICO，Windows Vista+ 支持）。

    PyInstaller 的 --icon 只收 .ico；用户选 png 图标时自动转换。
    ICO 结构：目录头(6B) + 单个目录项(16B) + PNG 数据。
    """
    with open(png_path, "rb") as f:
        png = f.read()
    if not png.startswith(b"\x89PNG\r\n\x1a\n"):
        raise ValueError("不是有效的 PNG 文件")
    header = b"\x00\x00\x01\x00\x01\x00"          # 1 个图像
    entry = (bytes([0, 0, 0, 0]) + b"\x01\x00\x20\x00"
             + len(png).to_bytes(4, "little")
             + (22).to_bytes(4, "little"))
    with open(ico_path, "wb") as f:
        f.write(header + entry + png)


def _resolve_icon_path(target_dir):
    """返回打包用的 .ico 路径：图标是 .ico 直接用；png 自动封装。

    返回 None 表示没有可用图标。生成物放 target_dir/_icon.ico（用完清理）。
    """
    icon_name = settings.get_icon()
    if not icon_name:
        return None
    src = os.path.join(config.ASSET_DIR, icon_name)
    if not os.path.isfile(src):
        return None
    if icon_name.lower().endswith(".ico"):
        return src
    if icon_name.lower().endswith((".png", ".jpg", ".jpeg", ".bmp")):
        # PNG-in-ICO 需要 PNG 数据；jpg/bmp 先经 pygame 转 PNG
        import pygame
        if not pygame.get_init():
            pygame.init()
        img = pygame.image.load(src)
        png_tmp = os.path.join(target_dir, "_icon_tmp.png")
        pygame.image.save(img, png_tmp)
        ico_tmp = os.path.join(target_dir, "_icon.ico")
        try:
            _png_to_ico(png_tmp, ico_tmp)
            return ico_tmp
        finally:
            if os.path.exists(png_tmp):
                os.remove(png_tmp)
    return None


def build_cmd(target_dir, exe_name=None, icon_path=None):
    """构造 PyInstaller 命令（供测试检查 / 实际打包共用）。

    --noconsole：打包后**不弹 cmd 黑窗**（纯 GUI）。
    --icon：自定义 exe 图标（需 .ico）。
    """
    cmd = [sys.executable, "-m", "PyInstaller", "--noconfirm", "--onefile",
           "--noconsole", "--name", exe_name or "I Wanna"]
    if icon_path:
        cmd += ["--icon", icon_path]
    # --add-data 语法（Windows 分隔符 ;）：**源必须用绝对路径**——
    # 指定了 --specpath 后 PyInstaller 把相对源路径按 spec 目录解析，
    # 相对路径会变成找 _spec\assets 而失败（unable to find）。
    # 目标（分号后）相对解包根：assets 打进 _MEIPASS/assets。
    add_data = [f"{os.path.join(config.PROJECT_ROOT, d)};{d}"
                for d in ("assets", "rooms", "sound", "music")]
    # 项目设置（标题/图标）也打进 exe → 打包版运行时从内置读，
    # 窗口标题/图标用自定义值（settings.py 在打包态读 DATA_DIR）。
    settings_file = os.path.join(config.PROJECT_ROOT, "editor_settings.json")
    if os.path.isfile(settings_file):
        add_data.append(f"{settings_file};.")
    for ad in add_data:
        cmd += ["--add-data", ad]
    cmd += ["--distpath", target_dir, "--workpath",
            os.path.join(target_dir, "_build"),
            "--specpath", os.path.join(target_dir, "_spec"), "main.py"]
    return cmd


def build_exe(target_dir, progress=None):
    """打包为单文件 exe：素材/关卡/音乐用 --add-data 打进 exe，输出只有 1 个文件。

    save 位置：打包版把 save/save.json 写在 **exe 旁边**的 save/ 里
    （config 的 sys.frozen 分支：BASE_DIR=exe 目录 / DATA_DIR=内置数据），
    不会写进临时解包目录，重开游戏存档仍在。
    """
    if not _pyinstaller_available():
        return "未安装 pyinstaller：请先运行 pip install pyinstaller"
    if progress:
        progress("打包中（约 1-3 分钟）...")
    os.makedirs(target_dir, exist_ok=True)
    # 先检查要打进 exe 的源目录存在（避免 PyInstaller "unable to find"）
    missing = [d for d in ("assets", "rooms", "sound", "music")
               if not os.path.isdir(os.path.join(config.PROJECT_ROOT, d))]
    if missing:
        return (f"打包失败：项目里缺少目录 {missing}，"
                f"请确认在项目根 {config.PROJECT_ROOT} 下运行")
    build_dir = os.path.join(target_dir, "_build")
    spec_dir = os.path.join(target_dir, "_spec")
    exe_name = _safe_exe_name(settings.get_title())   # 自定义标题 → exe 名
    icon_path = _resolve_icon_path(target_dir)        # .ico 直接用 / png 自动封装
    cmd = build_cmd(target_dir, exe_name=exe_name, icon_path=icon_path)
    try:
        proc = subprocess.run(cmd, cwd=config.PROJECT_ROOT,
                              capture_output=True, text=True)
    except OSError as exc:
        return f"打包失败：{exc}"
    shutil.rmtree(build_dir, ignore_errors=True)
    shutil.rmtree(spec_dir, ignore_errors=True)
    _ico = os.path.join(target_dir, "_icon.ico")
    if os.path.exists(_ico):
        os.remove(_ico)                 # 清理自动生成的图标
    if proc.returncode != 0:
        # 完整日志落盘，消息里给末尾错误 + 常见原因提示
        log_text = (proc.stdout or "") + "\n" + (proc.stderr or "")
        log_path = os.path.join(target_dir, "打包日志.txt")
        try:
            with open(log_path, "w", encoding="utf-8",
                      errors="replace") as f:
                f.write(log_text)
        except OSError:
            log_path = None
        lines = [ln for ln in log_text.splitlines() if ln.strip()]
        last = lines[-1] if lines else "PyInstaller 报错"
        hint = ""
        if "unable to find" in log_text.lower():
            hint = "；提示：输出/项目路径含中文或空格时 PyInstaller 可能找不到目录，" \
                   "请改用纯英文路径重试"
        tail_msg = f"（完整日志：{log_path}）" if log_path else ""
        return f"打包失败：{last}{hint}{tail_msg}"
    exe_path = os.path.join(target_dir, exe_name + ".exe")
    if not os.path.exists(exe_path):
        return f"打包失败：未找到 {exe_path}"
    # 存档目录：建在 exe 旁边（可写；打包版游戏从这里读写 save.json）
    os.makedirs(os.path.join(target_dir, "save"), exist_ok=True)
    return (f"已生成单文件 {exe_path}（素材/关卡已内置，"
            f"存档在 exe 旁 save/）")
