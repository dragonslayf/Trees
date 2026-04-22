#!/usr/bin/env python3
"""将大图按固定 tile 尺寸切分为子图（支持 overlap）。

默认保存到与输入同目录；若传入 ``out_dir`` 则保存到该目录（API 使用 ``segmentation_result``）。
"""
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
    out_dir: Path | None = None,
) -> None:
    path = path.resolve()
    if not path.is_file():
        raise FileNotFoundError(path)

    if overlap >= tile:
        raise ValueError("overlap 必须小于 tile")

    stride = tile - overlap  #  核心

    stem = prefix if prefix else path.stem
    out_dir = (path.parent if out_dir is None else Path(out_dir).resolve())
    out_dir.mkdir(parents=True, exist_ok=True)

    use_rasterio = path.suffix.lower() in {".tif", ".tiff"}
    if use_rasterio:
        try:
            import rasterio  # type: ignore
            from rasterio.windows import Window  # type: ignore
            from rasterio.windows import transform as window_transform  # type: ignore

            with rasterio.open(path) as src:
                W, H = int(src.width), int(src.height)
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
                        win_w = right - left
                        win_h = lower - upper
                        is_full = (win_w == tile) and (win_h == tile)

                        out_name = (
                            f"{stem}_tile_r{row:02d}_c{col:02d}.tif"
                            if is_full
                            else f"{stem}_tile_r{row:02d}_c{col:02d}_edge.tif"
                        )
                        out_path = out_dir / out_name
                        window = Window(left, upper, win_w, win_h)
                        tile_data = src.read(window=window)
                        profile = src.profile.copy()
                        profile.update(
                            driver="GTiff",
                            width=int(win_w),
                            height=int(win_h),
                            transform=window_transform(window, src.transform),
                        )
                        with rasterio.open(out_path, "w", **profile) as dst:
                            dst.write(tile_data)
                        n += 1

            print(
                f"原图 {W}x{H} -> stride={stride}，网格 {nrows}x{ncols}，共 {n} 张（含 overlap），输出目录: {out_dir}"
            )
            return
        except Exception:
            # 兼容无 rasterio 或读取失败场景：降级为 PIL 裁切（无地理信息）
            pass

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


def compute_tile_layout(path: Path, tile: int = 800, overlap: int = 200) -> dict:
    """返回与 split_tiff 一致的切片网格与偏移信息。"""
    path = path.resolve()
    if not path.is_file():
        raise FileNotFoundError(path)
    if overlap >= tile:
        raise ValueError("overlap 必须小于 tile")

    with Image.open(path) as img:
        width, height = img.size

    stride = tile - overlap
    ncols = math.ceil((width - overlap) / stride)
    nrows = math.ceil((height - overlap) / stride)
    stem = path.stem
    tiles: list[dict] = []

    for row in range(nrows):
        for col in range(ncols):
            left = col * stride
            upper = row * stride
            right = min(left + tile, width)
            lower = min(upper + tile, height)
            is_full = (right - left == tile) and (lower - upper == tile)
            fname = (
                f"{stem}_tile_r{row:02d}_c{col:02d}.tif"
                if is_full
                else f"{stem}_tile_r{row:02d}_c{col:02d}_edge.tif"
            )
            tiles.append(
                {
                    "file": fname,
                    "row": row,
                    "col": col,
                    "left": int(left),
                    "upper": int(upper),
                    "width": int(right - left),
                    "height": int(lower - upper),
                }
            )

    return {
        "dom_path": str(path),
        "stem": stem,
        "width": int(width),
        "height": int(height),
        "tile": int(tile),
        "overlap": int(overlap),
        "stride": int(stride),
        "nrows": int(nrows),
        "ncols": int(ncols),
        "tiles": tiles,
    }


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
    p.add_argument(
        "--out-dir",
        type=Path,
        default=None,
        help="输出目录（默认与输入影像同目录；API 使用 segmentation_result）",
    )
    args = p.parse_args()

    split_tiff(
        args.image,
        tile=args.tile,
        overlap=args.overlap,
        out_dir=args.out_dir,
    )


if __name__ == "__main__":
    main()