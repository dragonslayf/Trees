"""
从 DOM 影像生成固定尺寸的缩略图（默认 800×800 像素）。
通过整体缩放/重采样得到，而不是从原图中央裁剪一块。
"""
from pathlib import Path

import numpy as np
import rasterio
from rasterio.transform import from_bounds
from rasterio.warp import Resampling, calculate_default_transform, reproject


def create_dom_thumbnail(
    data_dir: Path,
    dom_filename: str = "DOMZone48.tif",
    thumb_size: int = 800,
    output_name: str | None = None,
) -> Path:
    """
    读取 DOM 影像，重采样为 thumb_size × thumb_size 的缩略图。

    - 整张图按比例缩放到固定像素尺寸（800×800），不保留原图局部裁剪。
    - 若原图宽高比不是 1:1，地理上相当于把 bounds 压进正方形像素格，
      像素在地面上的尺寸在 X/Y 方向可能不同，适合作为预览/缩略图。
    - 输出为 GeoTIFF，带 transform/crs。
    """
    data_dir = Path(data_dir)
    src_path = data_dir / dom_filename

    if not src_path.exists():
        raise FileNotFoundError(f"DOM 文件不存在: {src_path}")

    if output_name is None:
        stem = src_path.stem
        output_name = f"{stem}_thumb_{thumb_size}x{thumb_size}.tif"

    dst_path = data_dir / output_name

    with rasterio.Env():
        with rasterio.open(src_path) as src:
            # 将源图整个范围映射到 thumb_size × thumb_size 的栅格
            dst_transform, dst_w, dst_h = calculate_default_transform(
                src.crs,
                src.crs,
                src.width,
                src.height,
                *src.bounds,
                dst_width=thumb_size,
                dst_height=thumb_size,
            )

            if dst_w != thumb_size or dst_h != thumb_size:
                # 极少数情况下可能不是精确尺寸，强制为 thumb_size × thumb_size
                dst_transform = from_bounds(*src.bounds, thumb_size, thumb_size)

            # 按源 dtype 分配目标数组
            dst_dtype = src.dtypes[0]
            thumb_data = np.zeros(
                (src.count, thumb_size, thumb_size), dtype=dst_dtype
            )

            for i in range(1, src.count + 1):
                reproject(
                    source=rasterio.band(src, i),
                    destination=thumb_data[i - 1],
                    src_transform=src.transform,
                    src_crs=src.crs,
                    dst_transform=dst_transform,
                    dst_crs=src.crs,
                    resampling=Resampling.bilinear,
                )

            profile = src.profile.copy()
            profile.update(
                width=thumb_size,
                height=thumb_size,
                transform=dst_transform,
            )

            with rasterio.open(dst_path, "w", **profile) as dst:
                dst.write(thumb_data)

    return dst_path


if __name__ == "__main__":

    base_dir = Path(__file__).resolve().parent
    output_path = create_dom_thumbnail(base_dir)
    print(f"缩略图已生成: {output_path}")
