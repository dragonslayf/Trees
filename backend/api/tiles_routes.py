from __future__ import annotations

from html import escape as html_escape
from io import BytesIO
import shutil
from pathlib import Path
from typing import Callable
from urllib.parse import urlencode

from fastapi import APIRouter, HTTPException
from fastapi.responses import HTMLResponse, Response

from storage.workspace_files import segmentation_result_dir


def _render_tiff_png(path: Path) -> bytes:
    """将 GeoTIFF 转为 PNG 字节（与 /api/thumbnail/preview 逻辑一致）。"""
    import numpy as np
    import rasterio

    try:
        from PIL import Image
    except ImportError as e:
        raise HTTPException(
            status_code=500,
            detail="需要安装 Pillow: pip install Pillow",
        ) from e
    if not path.is_file():
        raise HTTPException(status_code=404, detail=f"文件不存在: {path.name}")
    with rasterio.open(path) as src:
        data = src.read()
    if data.ndim == 3:
        rgb = data[:3].transpose(1, 2, 0)
        dmin, dmax = rgb.min(), rgb.max()
        if dmax > dmin:
            rgb = ((rgb.astype(np.float64) - dmin) / (dmax - dmin) * 255).astype(np.uint8)
        else:
            rgb = np.zeros_like(rgb, dtype=np.uint8)
        img = Image.fromarray(rgb)
    else:
        band = data[0]
        dmin, dmax = band.min(), band.max()
        if dmax > dmin:
            band = ((band.astype(np.float64) - dmin) / (dmax - dmin) * 255).astype(np.uint8)
        else:
            band = np.zeros_like(band, dtype=np.uint8)
        img = Image.fromarray(band, mode="L")
    buf = BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)
    return buf.read()


def create_tiles_router(
    *,
    resolve_data_dir: Callable[[str | None], Path],
    split_tiff_func: Callable[..., object],
) -> APIRouter:
    router = APIRouter()

    @router.get("/api/tile/preview.png")
    def tile_preview_png(
        filename: str,
        data_dir: str | None = None,
        t: str | None = None,
    ):
        """``segmentation_result`` 下的切片 TIFF 转 PNG，供画廊页 img 引用。"""
        use_dir = resolve_data_dir(data_dir)
        name = (filename or "").strip()
        if not name or Path(name).name != name:
            raise HTTPException(status_code=400, detail="非法文件名")
        base = segmentation_result_dir(use_dir).resolve()
        path = (base / name).resolve()
        if path.parent != base:
            raise HTTPException(status_code=400, detail="路径越界")
        return Response(
            content=_render_tiff_png(path),
            media_type="image/png",
            headers={"Cache-Control": "no-store, max-age=0"},
        )

    @router.post("/api/tiles/ensure")
    def ensure_dom_tiles(
        dom_filename: str | None = None,
        data_dir: str | None = None,
        tile: int = 800,
        overlap: int = 200,
    ):
        """
        若指定 DOM 对应的切片尚不存在，则调用 split_tiff_tiles.split_tiff 切分；
        切片写入 ``data_dir/segmentation_result``（与 pkl 同目录）。已存在则跳过。
        """
        use_data_dir = resolve_data_dir(data_dir)
        use_dom = (dom_filename or "").strip()
        dom_path = use_data_dir / use_dom
        if not dom_path.is_file():
            raise HTTPException(status_code=404, detail=f"DOM 文件不存在: {use_dom}")
        stem = dom_path.stem
        tile_root = segmentation_result_dir(use_data_dir)
        pattern = f"{stem}_tile_r*_c*.tif"
        tile_root.mkdir(parents=True, exist_ok=True)
        existing = sorted(tile_root.glob(pattern))
        split_run = False
        if not existing:
            legacy_root = (use_data_dir / "tile_result").resolve()
            if legacy_root.is_dir():
                for p in sorted(legacy_root.glob(pattern)):
                    dest = tile_root / p.name
                    if not dest.is_file():
                        try:
                            shutil.move(str(p), str(dest))
                        except OSError:
                            pass
                existing = sorted(tile_root.glob(pattern))
        if not existing:
            try:
                split_tiff_func(dom_path, tile=tile, overlap=overlap, out_dir=tile_root)
            except Exception as e:
                raise HTTPException(status_code=500, detail=str(e)) from e
            existing = sorted(tile_root.glob(pattern))
            split_run = True
        if not existing:
            raise HTTPException(status_code=500, detail="切分后未找到切片文件")
        return {
            "ok": True,
            "data_dir": str(use_data_dir),
            "segmentation_result_dir": str(tile_root),
            "stem": stem,
            "dom_filename": use_dom,
            "tiles": [f.name for f in existing],
            "split_run": split_run,
        }

    @router.get("/api/tiles/gallery", response_class=HTMLResponse)
    def tiles_gallery(dom_filename: str | None = None, data_dir: str | None = None):
        """简单 HTML 画廊：展示 ``segmentation_result`` 内当前 DOM 对应全部切片的 PNG 预览。"""
        use_data_dir = resolve_data_dir(data_dir)
        use_dom = (dom_filename or "").strip()
        stem = Path(use_dom).stem
        pattern = f"{stem}_tile_r*_c*.tif"
        files = sorted(segmentation_result_dir(use_data_dir).glob(pattern))
        if not files:
            return HTMLResponse(
                "<!DOCTYPE html><html><head><meta charset='utf-8'><title>切片预览</title></head>"
                "<body style='background:#2b2b2b;color:#ccc;font-family:sans-serif;padding:1.5rem'>"
                "<p>暂无切片。请在前端选择对应 DOM 文件名并点击「查看缩略图」触发切分。</p></body></html>"
            )
        cards = []
        for f in files:
            qs = urlencode({"filename": f.name, "data_dir": str(use_data_dir)})
            src = f"/api/tile/preview.png?{qs}"
            safe_name = f.name.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
            cards.append(
                f"<figure style='margin:0;background:#3c3f41;border-radius:8px;padding:0.75rem;border:1px solid #555'>"
                f"<img src='{src}' alt='' style='max-width:100%;height:auto;display:block;border-radius:4px'/>"
                f"<figcaption style='margin-top:0.5rem;font-size:0.8rem;word-break:break-all;color:#aaa'>{safe_name}</figcaption>"
                f"</figure>"
            )
        grid = "".join(cards)
        title = html_escape(f"{stem} 切片预览 ({len(files)} 张)")
        html = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8"/>
  <meta name="viewport" content="width=device-width, initial-scale=1"/>
  <title>{title}</title>
  <style>
    body {{ margin:0; background:#1e1e1e; color:#ddd; font-family: system-ui, sans-serif; }}
    header {{ padding:1rem 1.25rem; background:#2d2d2d; border-bottom:1px solid #444; }}
    h1 {{ font-size:1.1rem; font-weight:600; margin:0; }}
    .grid {{
      display:grid;
      grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
      gap:1rem;
      padding:1.25rem;
    }}
  </style>
</head>
<body>
  <header><h1>{title}</h1></header>
  <div class="grid">{grid}</div>
</body>
</html>"""
        return HTMLResponse(html)

    return router
