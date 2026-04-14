"""
FastAPI 使用示例：与 Vue 前端联调、触发 DOM 缩略图生成等。

运行前安装：
  pip install fastapi uvicorn python-multipart

启动：
  cd Trees/backend
  uvicorn fastapi_example:app --reload --host 0.0.0.0 --port 8000

浏览器打开文档：
  http://127.0.0.1:8000/docs
"""
from html import escape as html_escape
from io import BytesIO
import json
import subprocess
import sys
from pathlib import Path
from urllib.parse import urlencode

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse, Response, StreamingResponse
from pydantic import BaseModel

# 与缩略图脚本同目录，便于直接 import
from split_tiff_tiles import split_tiff

# 数据目录 = 本文件所在目录（20260114）
DATA_DIR = Path(__file__).resolve().parent
TREES_ROOT = DATA_DIR.parent
MODELS_DIR = TREES_ROOT / "Models"
RUN_MODEL_SCRIPT = MODELS_DIR / "run_model_from_config.py"
VISUALIZE_SCRIPT = MODELS_DIR / "visualize_pkl_mask_centers.py"
DEFAULT_SEG_CONFIG = MODELS_DIR / "20230430_224903_config3.py"


def _tile_result_dir(data_dir: Path) -> Path:
    """800×800 切片目录：``{data_dir}/tile_result``"""
    return (data_dir / "tile_result").resolve()


def _segmentation_result_dir(data_dir: Path) -> Path:
    """模型单木分割 pkl 等：``{data_dir}/segmentation_result``"""
    return (data_dir / "segmentation_result").resolve()


def _marked_result_dir(data_dir: Path) -> Path:
    """单木位置可视化：``{data_dir}/tile_result/marked_result``"""
    return (_tile_result_dir(data_dir) / "marked_result").resolve()


def _dom_tile_paths(data_dir: Path, stem: str) -> list[Path]:
    """某 DOM stem 对应的全部切片路径（位于 tile_result）。"""
    return sorted(_tile_result_dir(data_dir).glob(f"{stem}_tile_r*_c*.tif"))


def _find_checkpoint() -> str | None:
    ckpts = sorted(MODELS_DIR.glob("*.pth"))
    return str(ckpts[0].resolve()) if ckpts else None


def _segment_model_config_path() -> Path:
    if DEFAULT_SEG_CONFIG.is_file():
        return DEFAULT_SEG_CONFIG
    cands = sorted(MODELS_DIR.glob("*config*.py"))
    cands = [p for p in cands if p.name != "run_model_from_config.py"]
    if cands:
        return cands[0]
    raise HTTPException(
        status_code=500,
        detail=f"未找到分割 config，请将配置文件放在 {MODELS_DIR} 下",
    )


def _run_subprocess_or_500(cmd: list[str], cwd: Path, timeout: int = 7200) -> None:
    try:
        r = subprocess.run(
            cmd,
            cwd=str(cwd),
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired as e:
        raise HTTPException(status_code=504, detail="推理子进程超时") from e
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e
    if r.returncode != 0:
        tail = (r.stderr or r.stdout or "").strip()
        tail = tail[-4000:] if tail else "未知错误"
        raise HTTPException(status_code=500, detail=f"子进程失败: {tail}")


def _unlink_if_exists(path: Path) -> None:
    if path.is_file():
        path.unlink()


def _remove_prior_vis_outputs(marked_dir: Path, tile_stem: str, pkl_stem: str) -> None:
    """置信度变化重绘前删除 marked_result 下该切片旧的可视化产物（PNG/JSON 及脚本默认命名遗留）。"""
    vis_path = marked_dir / f"{tile_stem}_vis.png"
    legacy_centers = marked_dir / f"{pkl_stem}_centers.png"
    for p in (
        vis_path,
        vis_path.with_suffix(".json"),
        legacy_centers,
        legacy_centers.with_suffix(".json"),
    ):
        _unlink_if_exists(p)


app = FastAPI(
    title="林木局 API 示例",
    description="DOM 缩略图生成 + 供 Trees Vue 前端调用的最小示例",
    version="0.1.0",
)

# Vue 开发服务器默认端口 5173；按需增删
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/")
def root():
    return {"message": "FastAPI 示例已运行", "docs": "/docs"}


@app.get("/health")
def health():
    return {"status": "ok"}


def _resolve_data_dir(data_dir: str | None) -> Path:
    """请求使用的数据目录：未传则用默认 DATA_DIR，否则解析为绝对路径（可传相对路径，相对当前工作目录）。"""
    if not data_dir or not data_dir.strip():
        return DATA_DIR
    p = Path(data_dir).resolve()
    return p if p.is_dir() else DATA_DIR


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


@app.get("/api/tile/preview.png")
def tile_preview_png(
    filename: str,
    data_dir: str | None = None,
    t: str | None = None,
):
    """``tile_result`` 下的切片 TIFF 转 PNG，供画廊页 img 引用。"""
    use_dir = _resolve_data_dir(data_dir)
    name = (filename or "").strip()
    if not name or Path(name).name != name:
        raise HTTPException(status_code=400, detail="非法文件名")
    base = _tile_result_dir(use_dir).resolve()
    path = (base / name).resolve()
    if path.parent != base:
        raise HTTPException(status_code=400, detail="路径越界")
    return Response(
        content=_render_tiff_png(path),
        media_type="image/png",
        headers={"Cache-Control": "no-store, max-age=0"},
    )


@app.post("/api/tiles/ensure")
def ensure_dom_tiles(
    dom_filename: str | None = None,
    data_dir: str | None = None,
    tile: int = 800,
    overlap: int = 200,
):
    """
    若指定 DOM 对应的切片尚不存在，则调用 split_tiff_tiles.split_tiff 切分；
    切片写入 ``data_dir/tile_result``。已存在则跳过。
    """
    use_data_dir = _resolve_data_dir(data_dir)
    use_dom = (dom_filename or "").strip() or "DOMZone48.tif"
    dom_path = use_data_dir / use_dom
    if not dom_path.is_file():
        raise HTTPException(status_code=404, detail=f"DOM 文件不存在: {use_dom}")
    stem = dom_path.stem
    tile_root = _tile_result_dir(use_data_dir)
    pattern = f"{stem}_tile_r*_c*.tif"
    existing = sorted(tile_root.glob(pattern))
    split_run = False
    if not existing:
        try:
            split_tiff(dom_path, tile=tile, overlap=overlap, out_dir=tile_root)
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e)) from e
        existing = sorted(tile_root.glob(pattern))
        split_run = True
    if not existing:
        raise HTTPException(status_code=500, detail="切分后未找到切片文件")
    return {
        "ok": True,
        "data_dir": str(use_data_dir),
        "tile_result_dir": str(tile_root),
        "stem": stem,
        "dom_filename": use_dom,
        "tiles": [f.name for f in existing],
        "split_run": split_run,
    }


@app.get("/api/tiles/gallery", response_class=HTMLResponse)
def tiles_gallery(dom_filename: str | None = None, data_dir: str | None = None):
    """简单 HTML 画廊：展示 ``tile_result`` 内当前 DOM 对应全部切片的 PNG 预览。"""
    use_data_dir = _resolve_data_dir(data_dir)
    use_dom = (dom_filename or "").strip() or "DOMZone48.tif"
    stem = Path(use_dom).stem
    pattern = f"{stem}_tile_r*_c*.tif"
    files = sorted(_tile_result_dir(use_data_dir).glob(pattern))
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


class SegmentRunIn(BaseModel):
    dom_filename: str | None = None
    data_dir: str | None = None
    overwrite: bool = False
    score_thr: float = 0.3


@app.get("/api/segment/has-existing")
def segment_has_existing(dom_filename: str | None = None, data_dir: str | None = None):
    """检查当前 DOM 对应切片是否已有任意 result.pkl（用于前端覆盖确认）。"""
    use_data_dir = _resolve_data_dir(data_dir)
    use_dom = (dom_filename or "").strip() or "DOMZone48.tif"
    stem = Path(use_dom).stem
    seg_dir = _segmentation_result_dir(use_data_dir)
    marked_dir = _marked_result_dir(use_data_dir)
    tiles = _dom_tile_paths(use_data_dir, stem)
    if not tiles:
        return {
            "has_tiles": False,
            "has_any_pkl": False,
            "tile_count": 0,
            "data_dir": str(use_data_dir),
            "tile_result_dir": str(_tile_result_dir(use_data_dir)),
            "segmentation_result_dir": str(seg_dir),
            "marked_result_dir": str(marked_dir),
        }
    has_any = any((seg_dir / f"{t.stem}_result.pkl").is_file() for t in tiles)
    return {
        "has_tiles": True,
        "has_any_pkl": has_any,
        "tile_count": len(tiles),
        "data_dir": str(use_data_dir),
        "tile_result_dir": str(_tile_result_dir(use_data_dir)),
        "segmentation_result_dir": str(seg_dir),
        "marked_result_dir": str(marked_dir),
    }


@app.post("/api/segment/run")
def segment_run(body: SegmentRunIn):
    """
    对 ``tile_result`` 下该 DOM 的全部 800×800 切片依次调用 run_model_from_config.py；
    pkl 写入 ``segmentation_result``，可视化写入 ``tile_result/marked_result``。
    """
    if not RUN_MODEL_SCRIPT.is_file():
        raise HTTPException(status_code=500, detail=f"未找到脚本: {RUN_MODEL_SCRIPT}")
    if not VISUALIZE_SCRIPT.is_file():
        raise HTTPException(status_code=500, detail=f"未找到脚本: {VISUALIZE_SCRIPT}")

    use_data_dir = _resolve_data_dir(body.data_dir)
    use_dom = (body.dom_filename or "").strip() or "DOMZone48.tif"
    stem = Path(use_dom).stem
    tiles = _dom_tile_paths(use_data_dir, stem)
    if not tiles:
        raise HTTPException(
            status_code=400,
            detail="未找到切片 TIFF，请先在数据管理中完成 DOM 切分",
        )

    cfg_path = _segment_model_config_path()
    pkl_dir = _segmentation_result_dir(use_data_dir)
    marked_dir = _marked_result_dir(use_data_dir)
    pkl_dir.mkdir(parents=True, exist_ok=True)
    marked_dir.mkdir(parents=True, exist_ok=True)

    if not body.overwrite:
        for t in tiles:
            if (pkl_dir / f"{t.stem}_result.pkl").is_file():
                raise HTTPException(
                    status_code=409,
                    detail="已存在分割结果（pkl），如需覆盖请传 overwrite=true 或在前端确认后重试",
                )

    ckpt = _find_checkpoint()
    cfg_rel = cfg_path.name
    processed = 0
    for t in tiles:
        pkl_path = pkl_dir / f"{t.stem}_result.pkl"
        vis_path = marked_dir / f"{t.stem}_vis.png"
        cmd = [
            sys.executable,
            str(RUN_MODEL_SCRIPT.resolve()),
            "--config",
            cfg_rel,
            "--image",
            str(t.resolve()),
            "--out-dir",
            str(pkl_dir),
            "--save-result",
            "--score-thr",
            str(body.score_thr),
        ]
        if ckpt:
            cmd.extend(["--checkpoint", ckpt])
        _run_subprocess_or_500(cmd, cwd=MODELS_DIR)

        if not pkl_path.is_file():
            raise HTTPException(
                status_code=500,
                detail=f"推理后未生成 pkl: {pkl_path.name}",
            )

        vcmd = [
            sys.executable,
            str(VISUALIZE_SCRIPT.resolve()),
            "--pkl",
            str(pkl_path.resolve()),
            "--image",
            str(t.resolve()),
            "--out",
            str(vis_path.resolve()),
            "--score-thr",
            str(body.score_thr),
        ]
        _run_subprocess_or_500(vcmd, cwd=MODELS_DIR)
        processed += 1

    return {
        "ok": True,
        "processed": processed,
        "data_dir": str(use_data_dir),
        "tile_result_dir": str(_tile_result_dir(use_data_dir)),
        "segmentation_result_dir": str(pkl_dir),
        "marked_result_dir": str(marked_dir),
        "dom_filename": use_dom,
    }


class SegmentRegenerateVisIn(BaseModel):
    dom_filename: str | None = None
    data_dir: str | None = None
    score_thr: float = 0.3


@app.post("/api/segment/regenerate-vis")
def segment_regenerate_vis(body: SegmentRegenerateVisIn):
    """
    不重新推理，仅对已存在的 *_result.pkl 按当前 score_thr
    调用 visualize_pkl_mask_centers.py 重写 *_vis.png（树中心标注）。

    响应为 NDJSON 流：每行一条 JSON，含 type=progress|done|error，便于前端显示 n/total 进度。
    """
    if not VISUALIZE_SCRIPT.is_file():
        raise HTTPException(status_code=500, detail=f"未找到脚本: {VISUALIZE_SCRIPT}")

    use_data_dir = _resolve_data_dir(body.data_dir)
    use_dom = (body.dom_filename or "").strip() or "DOMZone48.tif"
    stem = Path(use_dom).stem
    tiles = _dom_tile_paths(use_data_dir, stem)
    if not tiles:
        raise HTTPException(
            status_code=400,
            detail="未找到 DOM 切片，请先在数据管理中完成切分",
        )

    pkl_dir = _segmentation_result_dir(use_data_dir)
    marked_dir = _marked_result_dir(use_data_dir)
    marked_dir.mkdir(parents=True, exist_ok=True)
    tiles_with_pkl = [t for t in tiles if (pkl_dir / f"{t.stem}_result.pkl").is_file()]
    total = len(tiles_with_pkl)

    def ndjson_stream():
        try:
            yield json.dumps(
                {"type": "progress", "n": 0, "total": total},
                ensure_ascii=False,
            ) + "\n"
            regenerated = 0
            for t in tiles_with_pkl:
                pkl_path = pkl_dir / f"{t.stem}_result.pkl"
                _remove_prior_vis_outputs(marked_dir, t.stem, pkl_path.stem)
                vis_path = marked_dir / f"{t.stem}_vis.png"
                vcmd = [
                    sys.executable,
                    str(VISUALIZE_SCRIPT.resolve()),
                    "--pkl",
                    str(pkl_path.resolve()),
                    "--image",
                    str(t.resolve()),
                    "--out",
                    str(vis_path.resolve()),
                    "--score-thr",
                    str(body.score_thr),
                ]
                _run_subprocess_or_500(vcmd, cwd=MODELS_DIR)
                regenerated += 1
                yield json.dumps(
                    {"type": "progress", "n": regenerated, "total": total},
                    ensure_ascii=False,
                ) + "\n"
            yield json.dumps(
                {
                    "type": "done",
                    "ok": True,
                    "regenerated": regenerated,
                    "data_dir": str(use_data_dir),
                    "tile_result_dir": str(_tile_result_dir(use_data_dir)),
                    "segmentation_result_dir": str(pkl_dir),
                    "marked_result_dir": str(marked_dir),
                    "dom_filename": use_dom,
                    "score_thr": body.score_thr,
                },
                ensure_ascii=False,
            ) + "\n"
        except HTTPException as e:
            yield json.dumps(
                {"type": "error", "detail": str(e.detail)},
                ensure_ascii=False,
            ) + "\n"
        except Exception as e:
            yield json.dumps(
                {"type": "error", "detail": str(e)},
                ensure_ascii=False,
            ) + "\n"

    return StreamingResponse(
        ndjson_stream(),
        media_type="application/x-ndjson",
        headers={
            "Cache-Control": "no-store",
            "X-Accel-Buffering": "no",
        },
    )


@app.get("/api/segment/vis.png")
def segment_vis_png(
    filename: str,
    data_dir: str | None = None,
    t: str | None = None,
):
    """返回 ``tile_result/marked_result`` 下的可视化 PNG（如 *_vis.png）。"""
    use_data_dir = _resolve_data_dir(data_dir)
    marked_dir = _marked_result_dir(use_data_dir)
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


@app.get("/api/segment/gallery", response_class=HTMLResponse)
def segment_overlay_gallery(
    dom_filename: str | None = None,
    data_dir: str | None = None,
    t: str | None = None,
):
    """分割结果画廊：``tile_result`` 切片与 ``tile_result/marked_result`` 可视化。"""
    use_data_dir = _resolve_data_dir(data_dir)
    use_dom = (dom_filename or "").strip() or "DOMZone48.tif"
    stem = Path(use_dom).stem
    marked_dir = _marked_result_dir(use_data_dir)
    cache_token = (t or "").strip()
    tiles = _dom_tile_paths(use_data_dir, stem)
    if not tiles:
        return HTMLResponse(
            "<!DOCTYPE html><html><head><meta charset='utf-8'><title>分割预览</title></head>"
            "<body style='background:#2b2b2b;color:#ccc;padding:1.5rem;font-family:sans-serif'>"
            "<p>暂无 DOM 切片。请先在数据管理中切分影像。</p></body></html>"
        )
    cards = []
    for tile_path in tiles:
        vis_name = f"{tile_path.stem}_vis.png"
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


# 可选：用 JSON 列出目录下与 DOM 相关的文件
@app.get("/api/data/list")
def list_data_files(data_dir: str | None = None):
    """列出数据目录中的影像相关文件。可选 data_dir 指定服务器上的数据目录。"""
    use_dir = _resolve_data_dir(data_dir)
    patterns = ("*.tif", "*.tfw", "*.ovr", "*.aux.xml")
    files = []
    for p in patterns:
        files.extend([f.name for f in use_dir.glob(p)])
    return {"data_dir": str(use_dir), "files": sorted(set(files))}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("fastapi_example:app", host="0.0.0.0", port=7000)
