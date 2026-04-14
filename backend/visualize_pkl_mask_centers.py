#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
读取 MMDetection 2.x inference_detector 保存的 result.pkl，
解码分割掩码，计算每个实例的质心（分割区域像素坐标均值），并在原图上绘制。

result 约定：tuple (bbox_result, segm_result)，与 inference_detector 一致。
"""
from __future__ import annotations

import argparse
import json
import pickle
import sys
from pathlib import Path

import cv2
import mmcv
import numpy as np
import pycocotools.mask as mask_util

# 与同目录下的 tif 读取共用
_ROOT = Path(__file__).resolve().parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))
from export_box_crops import read_tif_rgb_as_uint8  # noqa: E402


def load_image_rgb(path: Path) -> np.ndarray:
    """返回 RGB uint8, 形状 (H,W,3)。"""
    suf = path.suffix.lower()
    if suf in {".tif", ".tiff"}:
        return read_tif_rgb_as_uint8(path)
    bgr = cv2.imread(str(path))
    if bgr is None:
        raise FileNotFoundError(f"无法读取图像: {path}")
    return cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)


def parse_mmdet2_result(result) -> tuple[np.ndarray, np.ndarray | None]:
    """
    返回:
        bboxes: (N, 5)  x1,y1,x2,y2,score
        segms: (N, H, W) uint8 二值掩码；若无分割分支则为 None
    """
    if isinstance(result, tuple):
        bbox_result, segm_result = result[0], result[1] if len(result) > 1 else None
        if segm_result is not None and isinstance(segm_result, tuple):
            segm_result = segm_result[0]
    else:
        bbox_result, segm_result = result, None

    if not isinstance(bbox_result, list):
        raise ValueError(f"bbox_result 应为 list，得到 {type(bbox_result)}")

    parts = [np.asarray(b, dtype=np.float32) for b in bbox_result if b is not None and len(b) > 0]
    if not parts:
        return np.zeros((0, 5), dtype=np.float32), None

    bboxes = np.vstack(parts)

    segms = None
    if segm_result is not None:
        flat = mmcv.concat_list(segm_result)
        if len(flat) != len(bboxes):
            raise ValueError(
                f"掩码数量 {len(flat)} 与框数量 {len(bboxes)} 不一致，请确认 pkl 为完整分割结果"
            )
        if len(flat) > 0:
            # MMDet 可能保存 COCO RLE（dict）或已解码的 (H,W) ndarray / bool
            if isinstance(flat[0], dict):
                decoded = mask_util.decode(flat)
                if decoded.ndim == 2:
                    decoded = decoded[:, :, np.newaxis]
                segms = decoded.transpose(2, 0, 1).astype(np.uint8)
            else:
                segms = np.stack([np.asarray(x, dtype=np.uint8) for x in flat], axis=0)
                if segms.ndim == 2:
                    segms = segms[np.newaxis, ...]

    return bboxes, segms


def mask_centroids(
    bboxes: np.ndarray,
    segms: np.ndarray | None,
    score_thr: float,
) -> list[dict]:
    """对每个 score>=thr 的实例计算质心；无掩码时用框中心。"""
    out: list[dict] = []
    for i in range(bboxes.shape[0]):
        x1, y1, x2, y2, sc = bboxes[i].tolist()
        if sc < score_thr:
            continue
        cx = cy = None
        area = 0
        if segms is not None and i < segms.shape[0]:
            m = segms[i]
            ys, xs = np.where(m > 0)
            area = int(xs.size)
            if area > 0:
                cx = float(xs.mean())
                cy = float(ys.mean())
        if cx is None:
            cx = float((x1 + x2) * 0.5)
            cy = float((y1 + y2) * 0.5)
            area = max(0, int((x2 - x1) * (y2 - y1)))

        out.append(
            {
                "index": len(out),
                "cx": cx,
                "cy": cy,
                "score": float(sc), 
                "bbox": [float(x1), float(y1), float(x2), float(y2)],
                "mask_area_px": area,
                "from_mask": segms is not None and area > 0,
            }
        )
    return out


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


def main() -> None:
    ap = argparse.ArgumentParser(description="从 result.pkl 读取分割结果，画质心")
    ap.add_argument("--pkl", required=True, type=Path, help="inference_detector 保存的 .pkl")
    ap.add_argument("--image", required=True, type=Path, help="与推理时一致的原始图像路径")
    ap.add_argument(
        "--out",
        type=Path,
        default=None,
        help="输出可视化图路径（默认: 与 pkl 同目录，*_centers.png）",
    )
    ap.add_argument(
        "--json-out",
        type=Path,
        default=None,
        help="质心列表 JSON（默认: 与 out 同 stem 的 .json）",
    )
    ap.add_argument("--score-thr", type=float, default=0.3, help="与推理可视化一致的分数阈值")
    ap.add_argument("--radius", type=int, default=6, help="圆点半径（像素）")
    args = ap.parse_args()

    pkl_path = args.pkl.expanduser().resolve()
    img_path = args.image.expanduser().resolve()
    if not pkl_path.is_file():
        raise FileNotFoundError(pkl_path)
    if not img_path.is_file():
        raise FileNotFoundError(img_path)

    with open(pkl_path, "rb") as f:
        result = pickle.load(f)

    bboxes, segms = parse_mmdet2_result(result)
    centers = mask_centroids(bboxes, segms, score_thr=args.score_thr)

    img = load_image_rgb(img_path)
    vis = draw_centers(img, centers, radius=args.radius)

    out = args.out
    if out is None:
        out = pkl_path.parent / f"{pkl_path.stem}_centers.png"
    else:
        out = out.expanduser().resolve()
    out.parent.mkdir(parents=True, exist_ok=True)

    cv2.imwrite(str(out), cv2.cvtColor(vis, cv2.COLOR_RGB2BGR))

    json_path = args.json_out
    if json_path is None:
        json_path = out.with_suffix(".json")
    else:
        json_path = json_path.expanduser().resolve()
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(centers, f, indent=2, ensure_ascii=False)


if __name__ == "__main__":
    main()
