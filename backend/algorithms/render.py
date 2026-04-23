from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np

from export_box_crops import read_tif_rgb_as_uint8


def load_image_rgb(path: Path) -> np.ndarray:
    """返回 RGB uint8, 形状 (H,W,3)。"""
    suf = path.suffix.lower()
    if suf in {".tif", ".tiff"}:
        return read_tif_rgb_as_uint8(path)
    bgr = cv2.imread(str(path))
    if bgr is None:
        raise FileNotFoundError(f"无法读取图像: {path}")
    return cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)


def draw_centers(
    img_rgb: np.ndarray,
    centers: list[dict],
    radius: int = 6,
    color: tuple[int, int, int] = (255, 0, 0),
    thickness: int = 2,
) -> np.ndarray:
    """在 RGB 图上画圆点与十字。"""
    vis = img_rgb.copy()
    bgr = cv2.cvtColor(vis, cv2.COLOR_RGB2BGR)
    for c in centers:
        x, y = int(round(c["cx"])), int(round(c["cy"]))
        cv2.circle(bgr, (x, y), radius, color[::-1], thickness, lineType=cv2.LINE_AA)
        d = radius + 4
        cv2.line(bgr, (x - d, y), (x + d, y), color[::-1], 1, cv2.LINE_AA)
        cv2.line(bgr, (x, y - d), (x, y + d), color[::-1], 1, cv2.LINE_AA)
    return cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)
