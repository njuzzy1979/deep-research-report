#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
生成 alt-sample 测试夹具 PNG 文件
规格：3 个不同尺寸的纯色 PNG，仅含 IHDR/IDAT/IEND chunk，刻意不包含 pHYs
"""

import struct
import zlib
import os

def generate_png(width, height, output_path, color=(200, 100, 50)):
    """
    生成最小化 PNG 文件（仅 IHDR/IDAT/IEND）

    Args:
        width: 图像宽度（像素）
        height: 图像高度（像素）
        output_path: 输出文件路径
        color: RGB 颜色元组 (R, G, B)
    """
    # PNG 文件签名
    png_signature = b'\x89PNG\r\n\x1a\n'

    # IHDR chunk（图像头信息）
    ihdr_data = struct.pack('>IIBBBBB', width, height, 8, 2, 0, 0, 0)  # 8-bit RGB
    ihdr_chunk = make_chunk(b'IHDR', ihdr_data)

    # IDAT chunk（图像数据）
    # 构建原始扫描线数据：每行为 1 字节过滤器类型（0=None）+ width*3 字节RGB
    raw_data = bytearray()
    for y in range(height):
        # 过滤器类型 0（无过滤）
        raw_data.append(0)
        # 填充该行的 RGB 数据
        for x in range(width):
            raw_data.extend(color)

    # 压缩数据
    compressed = zlib.compress(bytes(raw_data), 9)
    idat_chunk = make_chunk(b'IDAT', compressed)

    # IEND chunk（结束标记）
    iend_chunk = make_chunk(b'IEND', b'')

    # 写入文件
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, 'wb') as f:
        f.write(png_signature)
        f.write(ihdr_chunk)
        f.write(idat_chunk)
        f.write(iend_chunk)

def make_chunk(chunk_type, chunk_data):
    """
    生成 PNG chunk（长度 + 类型 + 数据 + CRC）
    """
    chunk_len = struct.pack('>I', len(chunk_data))
    chunk_crc = zlib.crc32(chunk_type + chunk_data) & 0xffffffff
    chunk_crc_bytes = struct.pack('>I', chunk_crc)
    return chunk_len + chunk_type + chunk_data + chunk_crc_bytes

if __name__ == '__main__':
    base_dir = os.path.dirname(os.path.abspath(__file__))
    figures_dir = os.path.join(base_dir, 'figures')

    # 图 1-1：1600x900，纯色橙红
    generate_png(1600, 900, os.path.join(figures_dir, '1-1-城际动车组谱系.png'), (255, 140, 0))
    print(f"✓ 已生成：1-1-城际动车组谱系.png (1600x900)")

    # 图 2-1：1200x1500（竖图），纯色青蓝
    generate_png(1200, 1500, os.path.join(figures_dir, '2-1-信号系统市场份额.png'), (70, 130, 180))
    print(f"✓ 已生成：2-1-信号系统市场份额.png (1200x1500)")

    # 图 3-1：800x400（小图），纯色绿色
    generate_png(800, 400, os.path.join(figures_dir, '3-1-出海项目分布.png'), (34, 139, 34))
    print(f"✓ 已生成：3-1-出海项目分布.png (800x400)")

    print("\n已完成所有夹具 PNG 生成。")
