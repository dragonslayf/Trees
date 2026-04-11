#!/usr/bin/env python3
"""将大图按固定 tile 尺寸切分为子图（支持 overlap），保存到同目录。"""
from __future__ import annotations

import argparse
import math
from pathlib import Path

from PIL import Image


def split_tiff(
    path: Path,
    tile: int = 800,
    overlap: int = 200,   #  新增
    prefix: str | None = None,
    fmt: str = "TIFF",
) -> None:
    path = path.resolve()
    if not path.is_file():
        raise FileNotFoundError(path)

    if overlap >= tile:
        raise ValueError("overlap 必须小于 tile")

    stride = tile - overlap  #  核心

    stem = prefix if prefix else path.stem
    out_dir = path.parent

    img = Image.open(path)
    W, H = img.size

    #  改为基于 stride 计算
    ncols = math.ceil((W - overlap) / stride)
    nrows = math.ceil((H - overlap) / stride)

    n = 0
    for row in range(nrows):
        for col in range(ncols):
            left = col * stride
            upper = row * stride
            right = min(left + tile, W)
            lower = min(upper + tile, H)

            box = (left, upper, right, lower)
            crop = img.crop(box)

            # 判断是否为完整 tile
            is_full = (right - left == tile) and (lower - upper == tile)

            if is_full:
                out_name = f"{stem}_tile_r{row:02d}_c{col:02d}.tif"
            else:
                out_name = f"{stem}_tile_r{row:02d}_c{col:02d}_edge.tif"

            out_path = out_dir / out_name
            crop.save(out_path, format=fmt)
            n += 1

    print(
        f"原图 {W}x{H} -> stride={stride}，网格 {nrows}x{ncols}，共 {n} 张（含 overlap），输出目录: {out_dir}"
    )


def main() -> None:
    p = argparse.ArgumentParser(description="TIFF 切分为固定尺寸子图（支持 overlap）")
    p.add_argument(
        "image",
        type=Path,
        nargs="?",
        default=Path(__file__).resolve().parent / "DOMZone48.tif",
        help="输入 TIFF 路径",
    )
    p.add_argument("--tile", type=int, default=800, help="子图边长（像素）")
    p.add_argument("--overlap", type=int, default=200, help="重叠像素")  # ✅ 新增参数
    args = p.parse_args()

    split_tiff(args.image, tile=args.tile, overlap=args.overlap)


if __name__ == "__main__":
    main()