#!/usr/bin/env python3
"""将大图按固定 tile 尺寸切分为子图，保存到同目录。"""
from __future__ import annotations

import argparse
import math
from pathlib import Path

from PIL import Image


def split_tiff(
    path: Path,
    tile: int = 800,
    prefix: str | None = None,
    fmt: str = "TIFF",
) -> None:
    path = path.resolve()
    if not path.is_file():
        raise FileNotFoundError(path)

    stem = prefix if prefix else path.stem
    out_dir = path.parent

    img = Image.open(path)
    # 统一为 RGBA 或 RGB，便于 pad
    W, H = img.size
    ncols = math.ceil(W / tile)
    nrows = math.ceil(H / tile)
    new_w = ncols * tile
    new_h = nrows * tile

    if img.mode == "RGBA":
        bg = (0, 0, 0, 0)
    elif img.mode == "RGB":
        bg = (0, 0, 0)
    else:
        img = img.convert("RGBA")
        bg = (0, 0, 0, 0)

    padded = Image.new(img.mode, (new_w, new_h), bg)
    padded.paste(img, (0, 0))

    n = 0
    for row in range(nrows):
        for col in range(ncols):
            box = (col * tile, row * tile, (col + 1) * tile, (row + 1) * tile)
            crop = padded.crop(box)
            out_name = f"{stem}_tile_r{row:02d}_c{col:02d}.tif"
            out_path = out_dir / out_name
            crop.save(out_path, format=fmt)
            n += 1

    print(
        f"原图 {W}x{H} -> 网格 {nrows}x{ncols}，共 {n} 张 {tile}x{tile}，输出目录: {out_dir}"
    )


def main() -> None:
    p = argparse.ArgumentParser(description="TIFF 切分为固定尺寸子图")
    p.add_argument(
        "image",
        type=Path,
        nargs="?",
        default=Path(__file__).resolve().parent / "DOMZone48.tif",
        help="输入 TIFF 路径",
    )
    p.add_argument("--tile", type=int, default=800, help="子图边长（像素）")
    args = p.parse_args()
    split_tiff(args.image, tile=args.tile)


if __name__ == "__main__":
    main()
