from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import cv2

from algorithms.detection import global_nms
from algorithms.geo import attach_geographic_info
from algorithms.render import draw_centers, load_image_rgb
from split_tiff_tiles import compute_tile_layout


def vis_param_suffix(score_thr: float, min_canopy_area_m2: float) -> str:
    pct = int(round(float(score_thr) * 100))
    s = f"{float(min_canopy_area_m2):.4f}".rstrip("0").rstrip(".") or "0"
    s = s.replace(".", "p")
    return f"c{pct}m{s}"


def marked_vis_json_name(tile_stem: str, score_thr: float, min_canopy_area_m2: float) -> str:
    return f"{tile_stem}_vis_{vis_param_suffix(score_thr, min_canopy_area_m2)}.json"


def marked_vis_png_name(tile_stem: str, score_thr: float, min_canopy_area_m2: float) -> str:
    return f"{tile_stem}_vis_{vis_param_suffix(score_thr, min_canopy_area_m2)}.png"


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

    merged = global_nms(merged_raw, iou_thr=float(nms_iou_thr))

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
