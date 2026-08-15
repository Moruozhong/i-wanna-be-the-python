"""
core/gif.py — 纯 Python GIF 帧解码器（无第三方依赖）

pygame-ce 只读取 GIF 第一帧，不播放动画。本模块实现 GIF89a 解码，
把每一帧合成为独立的 Surface，并附上每帧时长（毫秒），供 OverlayFX 播放。

支持：全局/局部调色板、LZW 压缩、图像交织、图形控制扩展（帧延时/透明色/
处置方式 dispose 0/1/2/3）、逻辑屏背景色填充。
"""

import os

import pygame

# ------------------------------------------------------------
# LZW 解压（GIF 变长码，LSB 优先）
# ------------------------------------------------------------

def _lzw_decode(data, min_code_size):
    """把压缩数据解成像素索引序列（bytes）。data 为所有子块拼接后的字节。"""
    out = bytearray()
    clear = 1 << min_code_size
    end = clear + 1
    code_size = min_code_size + 1
    table = {i: bytes([i]) for i in range(clear)}
    next_code = clear + 2
    prev = None

    bit_pos = 0
    nbits = len(data) * 8

    def read_code():
        nonlocal bit_pos, code_size
        if bit_pos + code_size > nbits:
            return None
        code = 0
        for i in range(code_size):
            code |= ((data[bit_pos >> 3] >> (bit_pos & 7)) & 1) << i
            bit_pos += 1
        return code

    while True:
        code = read_code()
        if code is None:
            break
        if code == clear:
            table = {i: bytes([i]) for i in range(clear)}
            next_code = clear + 2
            code_size = min_code_size + 1
            prev = None
            continue
        if code == end:
            break
        if code < next_code and code in table:
            entry = table[code]
        elif code == next_code:
            # KwKwK：前一个字符串 + 其首字符
            if prev is None:
                break
            entry = prev + prev[:1]
        else:
            break   # 数据损坏
        out.extend(entry)
        if prev is not None and next_code < 4096:
            table[next_code] = prev + entry[:1]
            next_code += 1
            if next_code == (1 << code_size) and code_size < 12:
                code_size += 1
        prev = entry
    return bytes(out)


# ------------------------------------------------------------
# 图像交织（行重排）
# ------------------------------------------------------------

def _deinterlace(raw, width, height):
    """raw 是按交错顺序排列的 width*height 像素；返回正常行序。"""
    rows = [raw[y * width:(y + 1) * width] for y in range(height)]
    out = [None] * height
    pos = 0
    for r in range(0, height, 8):     # pass 1：从第 0 行起每 8 行
        out[r] = rows[pos]; pos += 1
    for r in range(4, height, 8):     # pass 2：从第 4 行起每 8 行
        out[r] = rows[pos]; pos += 1
    for r in range(2, height, 4):     # pass 3：从第 2 行起每 4 行
        out[r] = rows[pos]; pos += 1
    for r in range(1, height, 2):     # pass 4：从第 1 行起每 2 行
        out[r] = rows[pos]; pos += 1
    return b"".join(out)


# ------------------------------------------------------------
# GIF 解码主入口
# ------------------------------------------------------------

def decode_gif(path):
    """解码一个 GIF，返回 [(Surface, 时长ms), ...]；失败或非 GIF 返回 None。"""
    with open(path, "rb") as f:
        data = f.read()

    if data[:6] not in (b"GIF87a", b"GIF89a"):
        return None

    w = int.from_bytes(data[6:8], "little")
    h = int.from_bytes(data[8:10], "little")
    packed = data[10]
    bg_index = data[11]
    has_gct = bool(packed & 0x80)
    gct_size = 2 ** ((packed & 0x07) + 1) if has_gct else 0

    pos = 13
    if has_gct:
        gct = _parse_color_table(data, pos, gct_size)
        pos += gct_size * 3
    else:
        gct = []

    # 逻辑屏背景色（canvas 初始填充用；透明画布则用全透明）
    bg_color = gct[bg_index] if gct and bg_index < len(gct) else (0, 0, 0)

    # 画布：RGBA 字节流，初始全透明
    canvas = bytearray(b"\x00\x00\x00\x00") * (w * h)

    frames = []          # [(surface, delay_ms)]
    transparent = -1     # 当前帧透明色索引；-1 表示无
    disposal = 0
    delay_ms = 100

    def canvas_copy():
        return bytearray(canvas)

    def save_frame():
        surf = pygame.image.frombytes(bytes(canvas), (w, h), "RGBA")
        if pygame.display.get_surface() is not None:
            surf = surf.convert_alpha()
        frames.append((surf, delay_ms))

    while pos < len(data):
        block = data[pos]
        if block == 0x3B:          # trailer
            break
        if block == 0x21:          # extension
            label = data[pos + 1]
            sub = _read_sub_blocks(data, pos + 2)
            if label == 0xF9:      # 图形控制扩展
                packed = sub[0]
                transparent = sub[3] if (packed & 1) else -1
                disposal = (packed >> 2) & 7
                delay_cs = int.from_bytes(sub[1:3], "little")
                delay_ms = delay_cs * 10 if delay_cs > 0 else 100
            pos = _skip_sub_blocks(data, pos + 2)   # 跳过 label 之后的一组子块
        elif block == 0x2C:        # 图像描述符
            left = int.from_bytes(data[pos + 1:pos + 3], "little")
            top = int.from_bytes(data[pos + 3:pos + 5], "little")
            iw = int.from_bytes(data[pos + 5:pos + 7], "little")
            ih = int.from_bytes(data[pos + 7:pos + 9], "little")
            ipack = data[pos + 9]
            has_lct = bool(ipack & 0x80)
            interlaced = bool(ipack & 0x40)
            lct_size = 2 ** ((ipack & 0x07) + 1) if has_lct else 0

            p = pos + 10
            if has_lct:
                lct = _parse_color_table(data, p, lct_size)
                p += lct_size * 3
            else:
                lct = gct
            min_code_size = data[p]
            p += 1
            raw = _lzw_decode(_read_sub_blocks(data, p), min_code_size)
            expected = iw * ih
            if len(raw) < expected:
                raw = raw + b"\x00" * (expected - len(raw))
            raw = raw[:expected]

            if interlaced:
                raw = _deinterlace(raw, iw, ih)

            if disposal == 3:      # 恢复前一帧：绘制前快照
                snapshot = canvas_copy()

            # 把本帧像素画到画布
            palette = lct if lct else gct
            for i in range(expected):
                idx = raw[i]
                if idx == transparent or idx >= len(palette):
                    continue
                r, g, b = palette[idx]
                ox = left + (i % iw)
                oy = top + (i // iw)
                if ox >= w or oy >= h:
                    continue
                j = (oy * w + ox) * 4
                canvas[j] = r
                canvas[j + 1] = g
                canvas[j + 2] = b
                canvas[j + 3] = 255

            save_frame()

            # 处置
            if disposal == 2:      # 恢复背景：本帧矩形清为透明
                for yy in range(top, min(top + ih, h)):
                    for xx in range(left, min(left + iw, w)):
                        j = (yy * w + xx) * 4
                        canvas[j:j + 4] = b"\x00\x00\x00\x00"
            elif disposal == 3:    # 恢复前一帧
                canvas[:] = snapshot

            pos = _skip_sub_blocks(data, pos + 10 + (lct_size * 3 if has_lct else 0) + 1)
        else:
            pos += 1

    if not frames:
        return None
    return frames


def _parse_color_table(data, pos, size):
    table = []
    for i in range(size):
        table.append((data[pos + i * 3], data[pos + i * 3 + 1], data[pos + i * 3 + 2]))
    return table


def _read_sub_blocks(data, pos):
    """读取从 pos 开始的一组子块（以长度 0 结束），返回拼接的 bytes。"""
    out = bytearray()
    while pos < len(data):
        sz = data[pos]
        pos += 1
        if sz == 0:
            break
        out.extend(data[pos:pos + sz])
        pos += sz
    return bytes(out)


def _skip_sub_blocks(data, pos):
    """跳过从 pos 开始的一组子块，返回下一块起始位置。"""
    while pos < len(data):
        sz = data[pos]
        pos += 1
        if sz == 0:
            break
        pos += sz
    return pos
