#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
从 MMDetection 推理结果 pkl 中提取检测框，并把每个框裁成单独图片。
假设 result 来自：
  result = inference_detector(model, img)
并保存为 pickle：
  pickle.dump(result, f)
"""
from __future__ import annotations
import argparse
import os
import pickle
from pathlib import Path
import numpy as np
def read_tif_rgb_as_uint8(path: Path) -> np.ndarray:
    """读取 tif，并尽量取前 3 个波段作为 RGB，输出 uint8(H,W,3)。"""
    try:
        import rasterio  # type: ignore
        with rasterio.open(str(path)) as src:
            data = src.read()
        if data.ndim == 2:
            data = data[None, ...]
        # (C,H,W)
        if data.shape[0] >= 3:
            img = data[:3].transpose(1, 2, 0)  # (H,W,3)
        else:
            img = data[0]
            img = np.stack([img, img, img], axis=-1)
        if img.dtype != np.uint8:
            mn, mx = float(img.min()), float(img.max())
            if mx > mn:
                img = ((img.astype("float64") - mn) / (mx - mn) * 255.0).astype(np.uint8)
            else:
                img = np.zeros_like(img, dtype=np.uint8)
        return np.ascontiguousarray(img)
    except Exception as e:
        raise RuntimeError(f"读取 tif 失败: {path} ({e})") from e
def parse_bbox_result(result_obj, score_thr: float) -> list[dict]:
    """解析 MMDet2.x inference_detector 的 bbox_result: result[0]。"""
    boxes_out: list[dict] = []
    if not isinstance(result_obj, tuple) or len(result_obj) < 1:
        raise ValueError(f"不支持的 result 结构: {type(result_obj)}")
    bbox_result = result_obj[0]
    if not isinstance(bbox_result, list):
        raise ValueError(f"bbox_result 不是 list: {type(bbox_result)}")
    for cls_idx, arr in enumerate(bbox_result):
        if arr is None:
            continue
        arr = np.asarray(arr)
        if arr.size == 0:
            continue
        if arr.ndim != 2 or arr.shape[1] < 5:
            continue
        keep = arr[:, 4] >= score_thr
        arr = arr[keep]
        for j in range(arr.shape[0]):
            x1, y1, x2, y2, score = arr[j, :5].tolist()
            boxes_out.append(
                {
                    "class": int(cls_idx),
                    "score": float(score),
                    "x1": float(x1),
                    "y1": float(y1),
                    "x2": float(x2),
                    "y2": float(y2),
                }
            )
    return boxes_out
def crop_and_save(
    img: np.ndarray,
    boxes: list[dict],
    out_dir: Path,
    pad: int,
    fmt: str,
    max_boxes: int,
) -> None:
    import PIL.Image  # type: ignore
    h, w = img.shape[:2]
    out_dir.mkdir(parents=True, exist_ok=True)
    kept = boxes[:max_boxes] if max_boxes > 0 else boxes
    for idx, b in enumerate(kept):
        x1 = int(np.floor(b["x1"])) - pad
        y1 = int(np.floor(b["y1"])) - pad
        x2 = int(np.ceil(b["x2"])) + pad
        y2 = int(np.ceil(b["y2"])) + pad
        # clip
        x1 = max(0, min(x1, w - 1))
        y1 = max(0, min(y1, h - 1))
        x2 = max(0, min(x2, w))
        y2 = max(0, min(y2, h))
        if x2 <= x1 or y2 <= y1:
            continue
        crop = img[y1:y2, x1:x2, :]
        im = PIL.Image.fromarray(crop)
        score = b["score"]
        cls_idx = b["class"]
        # 文件名里带 score 便于肉眼筛选
        out_p = out_dir / f"box_{idx:04d}_cls{cls_idx}_sc{score:.3f}.{fmt}"
        im.save(str(out_p))
def main() -> None:
    parser = argparse.ArgumentParser(description="裁剪检测框并导出图片")
    parser.add_argument("--result-pkl", required=True, help="inference_detector 保存的 result.pkl")
    parser.add_argument("--image", required=True, help="对应的输入 tif 路径")
    parser.add_argument("--out-dir", default="box_crops", help="输出目录")
    parser.add_argument("--score-thr", type=float, default=0.3, help="框置信度阈值")
    parser.add_argument("--pad", type=int, default=0, help="每个框裁剪时额外 padding（像素）")
    parser.add_argument("--max-boxes", type=int, default=0, help="最多导出多少个框（0=不限制）")
    parser.add_argument("--fmt", type=str, default="png", help="输出图片格式（png/jpg/jpeg）")
    parser.add_argument("--save-meta", action="store_true", help="同时保存 boxes 坐标为 json")
    args = parser.parse_args()
    pkl_path = Path(args.result_pkl).expanduser().resolve()
    img_path = Path(args.image).expanduser().resolve()
    out_dir = Path(args.out_dir).expanduser().resolve()
    if not pkl_path.is_file():
        raise FileNotFoundError(f"result pkl 不存在: {pkl_path}")
    if not img_path.is_file():
        raise FileNotFoundError(f"image 不存在: {img_path}")
    with open(pkl_path, "rb") as f:
        result = pickle.load(f)
    boxes = parse_bbox_result(result, score_thr=args.score_thr)
    print(f"检测到框数量(>=thr): {len(boxes)}")
    img = read_tif_rgb_as_uint8(img_path)
    crop_and_save(
        img=img,
        boxes=boxes,
        out_dir=out_dir,
        pad=args.pad,
        fmt=args.fmt,
        max_boxes=args.max_boxes,
    )
    print(f"已导出到: {out_dir}")
    if args.save_meta:
        import json
        meta_p = out_dir / "boxes.json"
        with open(meta_p, "w", encoding="utf-8") as f:
            json.dump(boxes, f, indent=2, ensure_ascii=False)
        print(f"已保存 meta: {meta_p}")
if __name__ == "__main__":
    main()