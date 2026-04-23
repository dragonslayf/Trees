#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
读取 MMDetection 2.x inference_detector 保存的 result.pkl，
解码分割掩码，计算每个实例的质心并在原图上绘制。

该文件保留为 CLI 入口；核心算法已拆分到 algorithms/ 与 services/。
"""
from __future__ import annotations

import argparse
import json
import pickle
import sys
from pathlib import Path

import cv2

_ROOT = Path(__file__).resolve().parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from algorithms.detection import mask_centroids, parse_mmdet2_result  # noqa: E402
from algorithms.geo import attach_geographic_info, raster_pixel_area_m2  # noqa: E402
from algorithms.render import draw_centers, load_image_rgb  # noqa: E402
from services.merge_service import (  # noqa: E402,F401
    marked_vis_json_name,
    marked_vis_png_name,
    merge_tile_json_to_whole_json,
    vis_param_suffix,
)


def main() -> None:
    ap = argparse.ArgumentParser(description='从 result.pkl 读取分割结果，画质心')
    ap.add_argument('--pkl', required=True, type=Path, help='inference_detector 保存的 .pkl')
    ap.add_argument('--image', required=True, type=Path, help='与推理时一致的原始图像路径')
    ap.add_argument('--out', type=Path, default=None, help='输出可视化图路径（默认: *_centers.png）')
    ap.add_argument('--json-out', type=Path, default=None, help='质心列表 JSON（默认: 与 out 同 stem）')
    ap.add_argument('--score-thr', type=float, default=0.3, help='与推理可视化一致的分数阈值')
    ap.add_argument('--min-canopy-area-m2', type=float, default=0.0, help='最小树冠面积（m²）')
    ap.add_argument('--radius', type=int, default=6, help='圆点半径（像素）')
    args = ap.parse_args()

    pkl_path = args.pkl.expanduser().resolve()
    img_path = args.image.expanduser().resolve()
    if not pkl_path.is_file():
        raise FileNotFoundError(pkl_path)
    if not img_path.is_file():
        raise FileNotFoundError(img_path)

    with open(pkl_path, 'rb') as f:
        result = pickle.load(f)

    bboxes, segms = parse_mmdet2_result(result)
    pixel_area_m2 = raster_pixel_area_m2(img_path)
    centers = mask_centroids(
        bboxes,
        segms,
        score_thr=args.score_thr,
        pixel_area_m2=pixel_area_m2,
        min_canopy_area_m2=args.min_canopy_area_m2,
    )

    img = load_image_rgb(img_path)
    vis = draw_centers(img, centers, radius=args.radius)
    out = args.out.expanduser().resolve() if args.out else (pkl_path.parent / f'{pkl_path.stem}_centers.png')
    out.parent.mkdir(parents=True, exist_ok=True)
    cv2.imwrite(str(out), cv2.cvtColor(vis, cv2.COLOR_RGB2BGR))

    json_path = args.json_out.expanduser().resolve() if args.json_out else out.with_suffix('.json')
    payload = {
        'meta': {
            'pixel_area_m2': pixel_area_m2,
            'score_thr': float(args.score_thr),
            'min_canopy_area_m2': float(args.min_canopy_area_m2),
            'image': str(img_path),
            'image_shape': list(img.shape[:2]),
        },
        'centers': centers,
    }
    payload['meta']['geo'] = attach_geographic_info(img_path, centers, center_x_key='cx', center_y_key='cy')
    with open(json_path, 'w', encoding='utf-8') as f:
        json.dump(payload, f, indent=2, ensure_ascii=False)


if __name__ == '__main__':
    main()
