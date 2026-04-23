from __future__ import annotations

from pathlib import Path
from typing import Any


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
