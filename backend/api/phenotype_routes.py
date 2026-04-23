from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Callable

from fastapi import APIRouter, HTTPException

from storage.workspace_files import segmentation_result_dir


def create_phenotype_router(*, resolve_data_dir: Callable[[str | None], Path]) -> APIRouter:
    router = APIRouter()

    @router.get("/api/phenotype/extract")
    def phenotype_extract(
        dom_filename: str | None = None,
        data_dir: str | None = None,
        chm_filename: str | None = None,
    ):
        """
        读取 ``segmentation_result/{dom_stem}_whole_centers.json``，提取表型：
        - 冠幅：PCA 主/次轴（已在 whole json）
        - 树冠面积：mask_area_m2
        - 树高：按中心点经纬度在 CHM 栅格采样（可选）
        - 体积：树冠面积 × 树高 × 0.6
        - DBH：由冠幅异速生长方程估算（默认使用主轴冠幅）
        """
        use_data_dir = resolve_data_dir(data_dir)
        use_dom = (dom_filename or "").strip()
        if not use_dom:
            raise HTTPException(status_code=400, detail="缺少 dom_filename")
        dom_path = use_data_dir / use_dom
        if not dom_path.is_file():
            raise HTTPException(status_code=404, detail=f"DOM 文件不存在: {use_dom}")

        stem = Path(use_dom).stem
        whole_json = segmentation_result_dir(use_data_dir) / f"{stem}_whole_centers.json"
        if not whole_json.is_file():
            raise HTTPException(
                status_code=404,
                detail=f"未找到整图 JSON: {whole_json.name}，请先在分割页完成可视化重建",
            )

        try:
            payload = json.loads(whole_json.read_text(encoding="utf-8"))
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"读取整图 JSON 失败: {e}") from e
        centers = payload.get("centers") if isinstance(payload, dict) else None
        if not isinstance(centers, list):
            raise HTTPException(status_code=500, detail="整图 JSON 缺少 centers 列表")

        # 自动 CHM：优先参数，其次 users/<id>/ 下文件名含 chm 的 tif/tiff（排除 DOM）
        use_chm: Path | None = None
        if chm_filename and chm_filename.strip():
            cand = use_data_dir / chm_filename.strip()
            if cand.is_file():
                use_chm = cand
        else:
            tifs = [p for p in use_data_dir.iterdir() if p.is_file() and p.suffix.lower() in {".tif", ".tiff"}]
            for p in sorted(tifs):
                n = p.name.lower()
                if p.name == use_dom:
                    continue
                if "chm" in n:
                    use_chm = p
                    break

        # 异速生长方程（可按树种区域调整）
        # DBH(cm) = alpha * crown_major_m ** beta
        dbh_alpha = 8.0
        dbh_beta = 0.85

        rows: list[dict] = []
        chm_missing = 0

        if use_chm is not None:
            try:
                import rasterio  # type: ignore
                from rasterio.transform import rowcol  # type: ignore
                from rasterio.warp import transform as rio_transform  # type: ignore
            except Exception as e:
                raise HTTPException(status_code=500, detail=f"读取 CHM 需要 rasterio: {e}") from e

            with rasterio.open(str(use_chm)) as chm_src:
                arr = chm_src.read(1)
                nodata = chm_src.nodata
                h, w = arr.shape

                def sample_height(c: dict) -> float | None:
                    lon = c.get("lon")
                    lat = c.get("lat")
                    if lon is None or lat is None:
                        return None
                    try:
                        lons, lats = [float(lon)], [float(lat)]
                        if chm_src.crs and str(chm_src.crs) != "EPSG:4326":
                            xs, ys = rio_transform("EPSG:4326", chm_src.crs, lons, lats)
                        else:
                            xs, ys = lons, lats
                        rr, cc = rowcol(chm_src.transform, xs[0], ys[0])
                        r = int(rr)
                        cidx = int(cc)
                        if r < 0 or cidx < 0 or r >= h or cidx >= w:
                            return None
                        v = float(arr[r, cidx])
                        if nodata is not None and math.isclose(v, float(nodata), rel_tol=0.0, abs_tol=1e-8):
                            return None
                        if not math.isfinite(v):
                            return None
                        return max(0.0, v)
                    except Exception:
                        return None

                for i, c in enumerate(centers):
                    if not isinstance(c, dict):
                        continue
                    crown_major_m = c.get("crown_major_m")
                    crown_minor_m = c.get("crown_minor_m")
                    canopy_area_m2 = c.get("mask_area_m2")
                    try:
                        crown_major_m = float(crown_major_m) if crown_major_m is not None else None
                        crown_minor_m = float(crown_minor_m) if crown_minor_m is not None else None
                        canopy_area_m2 = float(canopy_area_m2) if canopy_area_m2 is not None else None
                    except (TypeError, ValueError):
                        crown_major_m = crown_minor_m = canopy_area_m2 = None

                    height_m = sample_height(c)
                    if height_m is None:
                        chm_missing += 1
                    volume_m3 = (
                        float(canopy_area_m2) * float(height_m) * 0.6
                        if canopy_area_m2 is not None and height_m is not None
                        else None
                    )
                    dbh_cm = (
                        dbh_alpha * (max(crown_major_m, 1e-6) ** dbh_beta)
                        if crown_major_m is not None
                        else None
                    )
                    lon = c.get("lon")
                    lat = c.get("lat")
                    if isinstance(lon, (int, float)) and isinstance(lat, (int, float)):
                        tid = f"T_{lat:.7f}_{lon:.7f}"
                    else:
                        tid = f"T_{i+1:05d}"

                    rows.append(
                        {
                            "tree_id": tid,
                            "height_m": height_m,
                            "crown_major_m": crown_major_m,
                            "crown_minor_m": crown_minor_m,
                            "canopy_area_m2": canopy_area_m2,
                            "volume_m3": volume_m3,
                            "dbh_cm": dbh_cm,
                            "lon": lon,
                            "lat": lat,
                            "index": c.get("index", i),
                        }
                    )
        else:
            for i, c in enumerate(centers):
                if not isinstance(c, dict):
                    continue
                crown_major_m = c.get("crown_major_m")
                crown_minor_m = c.get("crown_minor_m")
                canopy_area_m2 = c.get("mask_area_m2")
                try:
                    crown_major_m = float(crown_major_m) if crown_major_m is not None else None
                    crown_minor_m = float(crown_minor_m) if crown_minor_m is not None else None
                    canopy_area_m2 = float(canopy_area_m2) if canopy_area_m2 is not None else None
                except (TypeError, ValueError):
                    crown_major_m = crown_minor_m = canopy_area_m2 = None
                dbh_cm = (
                    dbh_alpha * (max(crown_major_m, 1e-6) ** dbh_beta)
                    if crown_major_m is not None
                    else None
                )
                lon = c.get("lon")
                lat = c.get("lat")
                if isinstance(lon, (int, float)) and isinstance(lat, (int, float)):
                    tid = f"T_{lat:.7f}_{lon:.7f}"
                else:
                    tid = f"T_{i+1:05d}"
                rows.append(
                    {
                        "tree_id": tid,
                        "height_m": None,
                        "crown_major_m": crown_major_m,
                        "crown_minor_m": crown_minor_m,
                        "canopy_area_m2": canopy_area_m2,
                        "volume_m3": None,
                        "dbh_cm": dbh_cm,
                        "lon": lon,
                        "lat": lat,
                        "index": c.get("index", i),
                    }
                )

        return {
            "ok": True,
            "data_dir": str(use_data_dir),
            "dom_filename": use_dom,
            "whole_centers_json": str(whole_json),
            "chm_filename": use_chm.name if use_chm else None,
            "dbh_model": {"alpha": dbh_alpha, "beta": dbh_beta, "formula": "DBH(cm)=alpha*crown_major_m^beta"},
            "rows": rows,
            "count": len(rows),
            "height_missing_count": chm_missing if use_chm else len(rows),
        }

    @router.get("/api/data/list")
    def list_data_files(data_dir: str | None = None):
        """列出数据目录中的影像相关文件。可选 data_dir 指定服务器上的数据目录。"""
        use_dir = resolve_data_dir(data_dir)
        patterns = ("*.tif", "*.tfw", "*.ovr", "*.aux.xml")
        files = []
        for p in patterns:
            files.extend([f.name for f in use_dir.glob(p)])
        return {"data_dir": str(use_dir), "files": sorted(set(files))}

    return router
