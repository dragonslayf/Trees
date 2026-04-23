from __future__ import annotations

from html import escape as html_escape
from pathlib import Path
from typing import Callable
from urllib.parse import urlencode

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse, HTMLResponse
from pydantic import BaseModel

from services.segment_service import (
    marked_vis_png_name,
    regenerate_vis_stream,
    run_segment_stream,
)
from storage.workspace_files import (
    dom_tile_paths,
    marked_result_dir,
    segmentation_result_dir,
)


class SegmentRunIn(BaseModel):
    dom_filename: str | None = None
    data_dir: str | None = None
    overwrite: bool = False
    score_thr: float = 0.3
    min_canopy_area_m2: float = 0.0


class SegmentRegenerateVisIn(BaseModel):
    dom_filename: str | None = None
    data_dir: str | None = None
    score_thr: float = 0.3
    min_canopy_area_m2: float = 0.0


def create_segment_router(
    *,
    resolve_data_dir: Callable[[str | None], Path],
    models_dir: Path,
    run_model_script: Path,
    visualize_script: Path,
    default_seg_config: Path,
) -> APIRouter:
    router = APIRouter()

    @router.get("/api/segment/has-existing")
    def segment_has_existing(dom_filename: str | None = None, data_dir: str | None = None):
        """检查当前 DOM 对应切片是否已有任意 result.pkl（用于前端覆盖确认）。"""
        use_data_dir = resolve_data_dir(data_dir)
        use_dom = (dom_filename or "").strip()
        stem = Path(use_dom).stem
        seg_dir = segmentation_result_dir(use_data_dir)
        marked_dir = marked_result_dir(use_data_dir)
        tiles = dom_tile_paths(use_data_dir, stem)
        if not tiles:
            return {
                "has_tiles": False,
                "has_any_pkl": False,
                "tile_count": 0,
                "data_dir": str(use_data_dir),
                "segmentation_result_dir": str(seg_dir),
                "marked_result_dir": str(marked_dir),
            }
        has_any = any((seg_dir / f"{t.stem}_result.pkl").is_file() for t in tiles)
        return {
            "has_tiles": True,
            "has_any_pkl": has_any,
            "tile_count": len(tiles),
            "data_dir": str(use_data_dir),
            "segmentation_result_dir": str(seg_dir),
            "marked_result_dir": str(marked_dir),
        }

    @router.post("/api/segment/run")
    def segment_run(body: SegmentRunIn):
        """运行分割并流式返回进度。"""
        use_data_dir = resolve_data_dir(body.data_dir)
        use_dom = (body.dom_filename or "").strip()
        return run_segment_stream(
            use_data_dir=use_data_dir,
            use_dom=use_dom,
            overwrite=body.overwrite,
            score_thr=body.score_thr,
            min_canopy_area_m2=body.min_canopy_area_m2,
            models_dir=models_dir,
            run_model_script=run_model_script,
            visualize_script=visualize_script,
            default_seg_config=default_seg_config,
        )

    @router.post("/api/segment/regenerate-vis")
    def segment_regenerate_vis(body: SegmentRegenerateVisIn):
        """不重新推理，仅重建可视化并流式返回进度。"""
        use_data_dir = resolve_data_dir(body.data_dir)
        use_dom = (body.dom_filename or "").strip()
        return regenerate_vis_stream(
            use_data_dir=use_data_dir,
            use_dom=use_dom,
            score_thr=body.score_thr,
            min_canopy_area_m2=body.min_canopy_area_m2,
            models_dir=models_dir,
            visualize_script=visualize_script,
        )

    @router.get("/api/segment/vis.png")
    def segment_vis_png(
        filename: str,
        data_dir: str | None = None,
        t: str | None = None,
    ):
        """返回 ``segmentation_result/marked_result`` 下的可视化 PNG（如 *_vis.png）。"""
        use_data_dir = resolve_data_dir(data_dir)
        marked_dir = marked_result_dir(use_data_dir)
        name = (filename or "").strip()
        if not name or Path(name).name != name or not name.lower().endswith(".png"):
            raise HTTPException(status_code=400, detail="非法文件名")
        base = marked_dir.resolve()
        path = (marked_dir / name).resolve()
        if path.parent != base:
            raise HTTPException(status_code=400, detail="路径越界")
        if not path.is_file():
            raise HTTPException(status_code=404, detail="可视化文件不存在，请先运行分割")
        return FileResponse(
            path,
            media_type="image/png",
            headers={"Cache-Control": "no-store, max-age=0"},
        )

    @router.get("/api/segment/gallery", response_class=HTMLResponse)
    def segment_overlay_gallery(
        dom_filename: str | None = None,
        data_dir: str | None = None,
        t: str | None = None,
        score_thr: float | None = None,
        min_canopy_area_m2: float | None = None,
    ):
        """分割结果画廊：``segmentation_result`` 切片与 ``marked_result`` 可视化。"""
        use_data_dir = resolve_data_dir(data_dir)
        use_dom = (dom_filename or "").strip()
        stem = Path(use_dom).stem
        marked_dir = marked_result_dir(use_data_dir)
        cache_token = (t or "").strip()
        tiles = dom_tile_paths(use_data_dir, stem)
        thr = float(score_thr) if score_thr is not None else 0.3
        min_m2 = float(min_canopy_area_m2) if min_canopy_area_m2 is not None else 0.0
        if not tiles:
            return HTMLResponse(
                "<!DOCTYPE html><html><head><meta charset='utf-8'><title>分割预览</title></head>"
                "<body style='background:#2b2b2b;color:#ccc;padding:1.5rem;font-family:sans-serif'>"
                "<p>暂无 DOM 切片。请先在数据管理中切分影像。</p></body></html>"
            )
        cards = []
        for tile_path in tiles:
            vis_suffixed = marked_vis_png_name(tile_path.stem, thr, min_m2)
            legacy_name = f"{tile_path.stem}_vis.png"
            if (marked_dir / vis_suffixed).is_file():
                vis_name = vis_suffixed
            elif (marked_dir / legacy_name).is_file():
                vis_name = legacy_name
            else:
                vis_name = vis_suffixed
            safe_tile = tile_path.name.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
            if (marked_dir / vis_name).is_file():
                vis_params: dict[str, str] = {
                    "filename": vis_name,
                    "data_dir": str(use_data_dir),
                }
                if cache_token:
                    vis_params["t"] = cache_token
                qs = urlencode(vis_params)
                src = f"/api/segment/vis.png?{qs}"
                cap = safe_tile
            else:
                tile_params: dict[str, str] = {
                    "filename": tile_path.name,
                    "data_dir": str(use_data_dir),
                }
                if cache_token:
                    tile_params["t"] = cache_token
                qs = urlencode(tile_params)
                src = f"/api/tile/preview.png?{qs}"
                cap = f"{safe_tile}（尚未分割，仅原切片）"
            cards.append(
                f"<figure style='margin:0;background:#3c3f41;border-radius:8px;padding:0.75rem;border:1px solid #555'>"
                f"<img src='{src}' alt='' style='max-width:100%;height:auto;display:block;border-radius:4px'/>"
                f"<figcaption style='margin-top:0.5rem;font-size:0.8rem;word-break:break-all;color:#aaa'>{cap}</figcaption>"
                f"</figure>"
            )
        grid = "".join(cards)
        title = html_escape(f"{stem} 分割结果预览 ({len(tiles)} 块)")
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
