from __future__ import annotations

from typing import Any

import mmcv
import numpy as np
import pycocotools.mask as mask_util


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
            raise ValueError(f"掩码数量 {len(flat)} 与框数量 {len(bboxes)} 不一致，请确认 pkl 为完整分割结果")
        if len(flat) > 0:
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


def bbox_iou(a: list[float], b: list[float]) -> float:
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


def global_nms(items: list[dict[str, Any]], iou_thr: float = 0.35) -> list[dict[str, Any]]:
    """全局 NMS：按 score 降序保留 bbox，不与已保留框达到 IoU 阈值的条目。"""
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
            if bbox_iou(cur, other) >= iou_thr:
                suppressed = True
                break
        if not suppressed:
            kept.append(rec)
    for i, c in enumerate(kept):
        c["index"] = i
    return kept
