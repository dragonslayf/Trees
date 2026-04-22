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
from typing import Any

import cv2
import mmcv
import numpy as np
import pycocotools.mask as mask_util

# 与同目录下的 tif 读取共用
_ROOT = Path(__file__).resolve().parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))
from export_box_crops import read_tif_rgb_as_uint8  # noqa: E402
from split_tiff_tiles import compute_tile_layout  # noqa: E402


def raster_pixel_area_m2(image_path: Path) -> float:
    """
    单像元地面面积（m²）：
    - 投影坐标：按像元宽高 × 线性单位到米的换算系数计算；
    - 地理坐标（经纬度）：按中心点自动选择 UTM 分区，将像元角点投影到 UTM 后计算真实面积。
    无法读取或 CRS 缺失时退化为 1.0（此时 min_canopy_area_m2 等效像素数）。
    """
    try:
        import rasterio  # type: ignore
        from rasterio.warp import transform as rio_transform  # type: ignore

        with rasterio.open(str(image_path)) as src:
            t = src.transform
            pw = abs(float(t[0]))  # x 方向像元大小（CRS 单位）
            ph = abs(float(t[4]))  # y 方向像元大小（CRS 单位）
            crs = src.crs

            if crs is None:
                return 1.0

            # 地理坐标系（单位通常是度）：转 UTM 后按像元四角算真实面积
            if bool(getattr(crs, "is_geographic", False)):
                center_row = (src.height - 1) * 0.5
                center_col = (src.width - 1) * 0.5
                gx, gy = rasterio.transform.xy(t, center_row, center_col, offset="center")
                lons, lats = rio_transform(crs, "EPSG:4326", [float(gx)], [float(gy)])
                lon = float(lons[0])
                lat = float(lats[0])
                zone = int((lon + 180.0) // 6.0) + 1
                if zone < 1:
                    zone = 1
                if zone > 60:
                    zone = 60
                utm_epsg = f"EPSG:{32600 + zone if lat >= 0 else 32700 + zone}"

                # 取中心像元的四角，投影到 UTM 后按鞋带公式算面积
                corners_src = [
                    rasterio.transform.xy(t, center_row, center_col, offset="ul"),
                    rasterio.transform.xy(t, center_row, center_col, offset="ur"),
                    rasterio.transform.xy(t, center_row, center_col, offset="lr"),
                    rasterio.transform.xy(t, center_row, center_col, offset="ll"),
                ]
                xs = [float(p[0]) for p in corners_src]
                ys = [float(p[1]) for p in corners_src]
                ux, uy = rio_transform(crs, utm_epsg, xs, ys)
                area2 = 0.0
                n = len(ux)
                for i in range(n):
                    j = (i + 1) % n
                    area2 += float(ux[i]) * float(uy[j]) - float(ux[j]) * float(uy[i])
                area = abs(area2) * 0.5
                if area > 0:
                    return float(area)
                return 1.0

            # 投影坐标系：线性单位换算到米（如 feet -> meter）
            unit_to_meter = 1.0
            try:
                fac = getattr(crs, "linear_units_factor", None)
                if isinstance(fac, (tuple, list)) and fac:
                    unit_to_meter = float(fac[0])
                elif isinstance(fac, (int, float)):
                    unit_to_meter = float(fac)
            except Exception:
                unit_to_meter = 1.0
            return float(pw * ph * unit_to_meter * unit_to_meter)
    except Exception:
        return 1.0


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
    *,
    pixel_area_m2: float,
    min_canopy_area_m2: float = 0.0,
) -> list[dict]:
    """对每个 score>=thr 的实例计算质心；无掩码时用框中心。按树冠面积（m²）过滤。"""
    pa = float(pixel_area_m2) if pixel_area_m2 > 0 else 1.0
    pixel_size_m = float(np.sqrt(pa)) if pa > 0 else 1.0
    min_m2 = float(min_canopy_area_m2)
    out: list[dict] = []
    for i in range(bboxes.shape[0]):
        x1, y1, x2, y2, sc = bboxes[i].tolist()
        if sc < score_thr:
            continue
        cx = cy = None
        area_px = 0
        from_mask = False
        crown_major_px = 0.0
        crown_minor_px = 0.0
        if segms is not None and i < segms.shape[0]:
            m = segms[i]
            ys, xs = np.where(m > 0)
            area_px = int(xs.size)
            if area_px > 0:
                cx = float(xs.mean())
                cy = float(ys.mean())
                from_mask = True
                if area_px >= 2:
                    pts = np.stack([xs.astype(np.float64), ys.astype(np.float64)], axis=1)
                    centered = pts - pts.mean(axis=0, keepdims=True)
                    # PCA: 主方向/副方向取协方差矩阵特征向量，冠幅=投影范围(max-min)
                    cov = np.cov(centered, rowvar=False)
                    eigvals, eigvecs = np.linalg.eigh(cov)
                    order = np.argsort(eigvals)[::-1]
                    v1 = eigvecs[:, order[0]]
                    p1 = centered @ v1
                    crown_major_px = float(p1.max() - p1.min()) if p1.size else 0.0
                    if eigvecs.shape[1] > 1:
                        v2 = eigvecs[:, order[1]]
                        p2 = centered @ v2
                        crown_minor_px = float(p2.max() - p2.min()) if p2.size else 0.0
        if cx is None:
            cx = float((x1 + x2) * 0.5)
            cy = float((y1 + y2) * 0.5)
            area_px = max(0, int(abs(x2 - x1) * abs(y2 - y1)))
            crown_major_px = float(abs(x2 - x1))
            crown_minor_px = float(abs(y2 - y1))

        if crown_major_px < crown_minor_px:
            crown_major_px, crown_minor_px = crown_minor_px, crown_major_px

        area_m2 = float(area_px) * pa
        if area_m2 < min_m2:
            continue

        out.append(
            {
                "index": len(out),
                "cx": cx,
                "cy": cy,
                "score": float(sc),
                "bbox": [float(x1), float(y1), float(x2), float(y2)],
                "mask_area_px": area_px,
                "mask_area_m2": round(area_m2, 6),
                "crown_major_px": round(crown_major_px, 6),
                "crown_minor_px": round(crown_minor_px, 6),
                "crown_major_m": round(crown_major_px * pixel_size_m, 6),
                "crown_minor_m": round(crown_minor_px * pixel_size_m, 6),
                "from_mask": from_mask,
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


def attach_geographic_info(
    image_path: Path,
    centers: list[dict[str, Any]],
    *,
    center_x_key: str = "cx",
    center_y_key: str = "cy",
    bbox_key: str = "bbox",
) -> dict[str, Any]:
    """
    使用 rasterio 将像素坐标转换为 WGS84(经纬度)并附加到每条记录。

    写入字段：
    - `lon` / `lat`（由 center_x_key、center_y_key 转换）
    - `bbox_lonlat`（由 bbox 左上/右下像素角点转换）
    """
    try:
        import rasterio  # type: ignore
        from rasterio.warp import transform as rio_transform  # type: ignore
    except Exception as e:
        return {"geo_attached": False, "reason": f"rasterio 不可用: {e}"}

    image_path = image_path.expanduser().resolve()
    try:
        with rasterio.open(str(image_path)) as src:
            tr = src.transform
            src_crs = src.crs
            if src_crs is None:
                return {"geo_attached": False, "reason": "影像缺少 CRS"}

            def px_to_lonlat(x: float, y: float) -> tuple[float, float]:
                gx, gy = rasterio.transform.xy(tr, y, x, offset="center")
                lons, lats = rio_transform(src_crs, "EPSG:4326", [float(gx)], [float(gy)])
                return float(lons[0]), float(lats[0])

            attached = 0
            for c in centers:
                try:
                    x = float(c[center_x_key])
                    y = float(c[center_y_key])
                    lon, lat = px_to_lonlat(x, y)
                    c["lon"] = lon
                    c["lat"] = lat
                    attached += 1
                except (KeyError, TypeError, ValueError):
                    pass

                b = c.get(bbox_key)
                if isinstance(b, list) and len(b) >= 4:
                    try:
                        x1, y1, x2, y2 = float(b[0]), float(b[1]), float(b[2]), float(b[3])
                        lon1, lat1 = px_to_lonlat(x1, y1)
                        lon2, lat2 = px_to_lonlat(x2, y2)
                        c["bbox_lonlat"] = [lon1, lat1, lon2, lat2]
                    except (TypeError, ValueError):
                        pass

            return {
                "geo_attached": True,
                "attached_count": attached,
                "source_crs": str(src_crs),
                "target_crs": "EPSG:4326",
                "image": str(image_path),
            }
    except Exception as e:
        return {"geo_attached": False, "reason": str(e), "image": str(image_path)}


def vis_param_suffix(score_thr: float, min_canopy_area_m2: float) -> str:
    pct = int(round(float(score_thr) * 100))
    s = f"{float(min_canopy_area_m2):.4f}".rstrip("0").rstrip(".") or "0"
    s = s.replace(".", "p")
    return f"c{pct}m{s}"


def marked_vis_json_name(tile_stem: str, score_thr: float, min_canopy_area_m2: float) -> str:
    return f"{tile_stem}_vis_{vis_param_suffix(score_thr, min_canopy_area_m2)}.json"


def marked_vis_png_name(tile_stem: str, score_thr: float, min_canopy_area_m2: float) -> str:
    return f"{tile_stem}_vis_{vis_param_suffix(score_thr, min_canopy_area_m2)}.png"


def _bbox_iou(a: list[float], b: list[float]) -> float:
    ax1, ay1, ax2, ay2 = a
    bx1, by1, bx2, by2 = b
    ix1 = max(ax1, bx1)
    iy1 = max(ay1, by1)
    ix2 = min(ax2, bx2)
    iy2 = min(ay2, by2)
    iw = max(0.0, ix2 - ix1)
    ih = max(0.0, iy2 - iy1)
    inter = iw * ih
    if inter <= 0:
        return 0.0
    a_area = max(0.0, ax2 - ax1) * max(0.0, ay2 - ay1)
    b_area = max(0.0, bx2 - bx1) * max(0.0, by2 - by1)
    denom = a_area + b_area - inter
    if denom <= 0:
        return 0.0
    return float(inter / denom)


def _global_nms(items: list[dict[str, Any]], iou_thr: float = 0.35) -> list[dict[str, Any]]:
    """
    全局 NMS：按 score 降序保留 bbox，不与已保留框达到 IoU 阈值的条目。
    无 bbox 的条目直接保留（通常不应出现）。
    """
    ordered = sorted(items, key=lambda x: float(x.get("score", 0.0)), reverse=True)
    kept: list[dict[str, Any]] = []
    for rec in ordered:
        b = rec.get("bbox")
        if not isinstance(b, list) or len(b) < 4:
            kept.append(rec)
            continue
        cur = [float(b[0]), float(b[1]), float(b[2]), float(b[3])]
        suppressed = False
        for k in kept:
            kb = k.get("bbox")
            if not isinstance(kb, list) or len(kb) < 4:
                continue
            other = [float(kb[0]), float(kb[1]), float(kb[2]), float(kb[3])]
            if _bbox_iou(cur, other) >= iou_thr:
                suppressed = True
                break
        if not suppressed:
            kept.append(rec)
    for i, c in enumerate(kept):
        c["index"] = i
    return kept


def merge_tile_json_to_whole_json(
    *,
    dom_image: Path,
    seg_result_dir: Path,
    marked_dir: Path,
    score_thr: float,
    min_canopy_area_m2: float,
    tile: int = 800,
    overlap: int = 200,
    out_json: Path | None = None,
    out_mark_png: Path | None = None,
    nms_iou_thr: float = 0.35,
    mark_radius: int = 7,
) -> tuple[Path, Path]:
    """
    将各子图 json 的局部坐标转换为原图坐标，做全局 NMS 去重，
    并输出单一 json + 整图 mark 图。
    """
    dom_image = dom_image.expanduser().resolve()
    seg_result_dir = seg_result_dir.expanduser().resolve()
    marked_dir = marked_dir.expanduser().resolve()
    if not dom_image.is_file():
        raise FileNotFoundError(dom_image)

    layout = compute_tile_layout(dom_image, tile=tile, overlap=overlap)
    merged_raw: list[dict[str, Any]] = []
    missing_json = 0
    used_tiles = 0

    for t in layout["tiles"]:
        tile_name = str(t["file"])
        tile_path = seg_result_dir / tile_name
        if not tile_path.is_file():
            continue
        tile_stem = Path(tile_name).stem
        jpath = marked_dir / marked_vis_json_name(tile_stem, score_thr, min_canopy_area_m2)
        if not jpath.is_file():
            missing_json += 1
            continue
        try:
            payload = json.loads(jpath.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            missing_json += 1
            continue
        centers = payload.get("centers") if isinstance(payload, dict) else None
        if not isinstance(centers, list):
            missing_json += 1
            continue

        left = int(t["left"])
        upper = int(t["upper"])
        used_tiles += 1
        for c in centers:
            if not isinstance(c, dict):
                continue
            try:
                local_x = float(c["cx"])
                local_y = float(c["cy"])
            except (KeyError, TypeError, ValueError):
                continue
            rec = {k: v for k, v in c.items() if k not in ("index", "cx", "cy")}
            rec["cx"] = local_x + left
            rec["cy"] = local_y + upper
            rec["cx_local"] = local_x
            rec["cy_local"] = local_y
            rec["tile_file"] = tile_name
            rec["tile_row"] = int(t["row"])
            rec["tile_col"] = int(t["col"])
            if isinstance(c.get("bbox"), list) and len(c["bbox"]) >= 4:
                try:
                    b = [float(c["bbox"][0]), float(c["bbox"][1]), float(c["bbox"][2]), float(c["bbox"][3])]
                    rec["bbox_local"] = b
                    rec["bbox"] = [b[0] + left, b[1] + upper, b[2] + left, b[3] + upper]
                except (TypeError, ValueError):
                    pass
            merged_raw.append(rec)

    merged = _global_nms(merged_raw, iou_thr=float(nms_iou_thr))

    out_path = out_json or (seg_result_dir / f"{layout['stem']}_whole_centers.json")
    out_path = out_path.expanduser().resolve()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    mark_path = out_mark_png or (
        marked_dir / marked_vis_png_name(f"{layout['stem']}_whole", score_thr, min_canopy_area_m2)
    )
    mark_path = mark_path.expanduser().resolve()
    mark_path.parent.mkdir(parents=True, exist_ok=True)

    whole_img = load_image_rgb(dom_image)
    whole_vis = draw_centers(whole_img, merged, radius=max(2, int(mark_radius)))
    cv2.imwrite(str(mark_path), cv2.cvtColor(whole_vis, cv2.COLOR_RGB2BGR))
    geo_meta = attach_geographic_info(dom_image, merged, center_x_key="cx", center_y_key="cy")

    doc = {
        "meta": {
            "dom_image": str(dom_image),
            "dom_stem": layout["stem"],
            "image_shape": [int(layout["height"]), int(layout["width"])],
            "tile": int(tile),
            "overlap": int(overlap),
            "stride": int(layout["stride"]),
            "score_thr": float(score_thr),
            "min_canopy_area_m2": float(min_canopy_area_m2),
            "tiles_in_layout": len(layout["tiles"]),
            "tiles_with_json": used_tiles,
            "tiles_missing_json": missing_json,
            "centers_before_nms": len(merged_raw),
            "centers_after_nms": len(merged),
            "nms_iou_thr": float(nms_iou_thr),
            "whole_mark_png": str(mark_path),
            "geo": geo_meta,
        },
        "centers": merged,
    }
    out_path.write_text(json.dumps(doc, indent=2, ensure_ascii=False), encoding="utf-8")
    return out_path, mark_path


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
    ap.add_argument(
        "--min-canopy-area-m2",
        type=float,
        default=0.0,
        help="最小树冠面积（m²），由掩膜像素数×像元面积得到；无地理坐标时像元面积按 1 则等效为像素数",
    )
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
    payload = {
        "meta": {
            "pixel_area_m2": pixel_area_m2,
            "score_thr": float(args.score_thr),
            "min_canopy_area_m2": float(args.min_canopy_area_m2),
            "image": str(img_path),
            "image_shape": list(img.shape[:2]),
        },
        "centers": centers,
    }
    payload["meta"]["geo"] = attach_geographic_info(
        img_path,
        centers,
        center_x_key="cx",
        center_y_key="cy",
    )
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, ensure_ascii=False)


if __name__ == "__main__":
    main()
