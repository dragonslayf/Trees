"""
FastAPI 使用示例：与 Vue 前端联调、触发 DOM 缩略图生成等。

运行前安装：
  pip install fastapi uvicorn python-multipart

启动：
  cd 20260114
  uvicorn fastapi_example:app --reload --host 0.0.0.0 --port 8000

浏览器打开文档：
  http://127.0.0.1:8000/docs
"""
from html import escape as html_escape
from io import BytesIO
from pathlib import Path
from urllib.parse import urlencode

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse, Response

# 与缩略图脚本同目录，便于直接 import
from split_tiff_tiles import split_tiff

# 数据目录 = 本文件所在目录（20260114）
DATA_DIR = Path(__file__).resolve().parent

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


@app.post("/api/thumbnail/generate")
def generate_thumbnail(
    thumb_size: int = 800,
    dom_filename: str | None = None,
    data_dir: str | None = None,
):
    """
    调用 create_dom_thumbnail 生成 DOM 缩略图。
    - dom_filename: 使用的 DOM 文件名（如 DOMZone48.tif），不传则用默认。
    - data_dir: 数据目录（服务器路径），不传则用默认 DATA_DIR。
    """
    use_data_dir = _resolve_data_dir(data_dir)
    use_dom = (dom_filename or "").strip() or "DOMZone48.tif"
    try:
        out_path = create_dom_thumbnail(
            use_data_dir,
            dom_filename=use_dom,
            thumb_size=thumb_size,
        )
        return {
            "ok": True,
            "path": str(out_path),
            "filename": out_path.name,
            "data_dir": str(use_data_dir),
        }
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/thumbnail/file")
def download_thumbnail(
    filename: str = "DOMZone48_thumb_800x800.tif",
    data_dir: str | None = None,
):
    """
    若已生成缩略图，直接返回 TIFF 文件下载。可选 data_dir 指定服务器上的数据目录。
    """
    use_dir = _resolve_data_dir(data_dir)
    path = use_dir / filename
    if not path.is_file():
        raise HTTPException(status_code=404, detail=f"文件不存在: {filename}")
    return FileResponse(
        path,
        media_type="image/tiff",
        filename=path.name,
    )


@app.get("/api/thumbnail/preview.png")
def thumbnail_preview_png(filename: str | None = None, data_dir: str | None = None):
    """
    返回缩略图的 PNG 预览。可选 filename、data_dir 与生成时一致。
    """
    use_dir = _resolve_data_dir(data_dir)
    thumb_name = (filename or "").strip() or "DOMZone48_thumb_800x800.tif"
    path = use_dir / thumb_name
    if not path.is_file():
        raise HTTPException(status_code=404, detail="请先调用 POST /api/thumbnail/generate 生成缩略图")
    return Response(content=_render_tiff_png(path), media_type="image/png")


@app.get("/api/tile/preview.png")
def tile_preview_png(filename: str, data_dir: str | None = None):
    """任意数据目录下的 TIFF（如切片）转 PNG，供画廊页 img 引用。"""
    use_dir = _resolve_data_dir(data_dir)
    name = (filename or "").strip()
    if not name or Path(name).name != name:
        raise HTTPException(status_code=400, detail="非法文件名")
    base = use_dir.resolve()
    path = (use_dir / name).resolve()
    if path.parent != base:
        raise HTTPException(status_code=400, detail="路径越界")
    return Response(content=_render_tiff_png(path), media_type="image/png")


@app.post("/api/tiles/ensure")
def ensure_dom_tiles(
    dom_filename: str | None = None,
    data_dir: str | None = None,
    tile: int = 800,
    overlap: int = 200,
):
    """
    若指定 DOM 对应的切片尚不存在，则调用 split_tiff_tiles.split_tiff 切分；
    已存在则跳过。返回切片文件名列表与 data_dir，供前端打开画廊。
    """
    use_data_dir = _resolve_data_dir(data_dir)
    use_dom = (dom_filename or "").strip() or "DOMZone48.tif"
    dom_path = use_data_dir / use_dom
    if not dom_path.is_file():
        raise HTTPException(status_code=404, detail=f"DOM 文件不存在: {use_dom}")
    stem = dom_path.stem
    pattern = f"{stem}_tile_r*_c*.tif"
    existing = sorted(use_data_dir.glob(pattern))
    split_run = False
    if not existing:
        try:
            split_tiff(dom_path, tile=tile, overlap=overlap)
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e)) from e
        existing = sorted(use_data_dir.glob(pattern))
        split_run = True
    if not existing:
        raise HTTPException(status_code=500, detail="切分后未找到切片文件")
    return {
        "ok": True,
        "data_dir": str(use_data_dir),
        "stem": stem,
        "dom_filename": use_dom,
        "tiles": [f.name for f in existing],
        "split_run": split_run,
    }


@app.get("/api/tiles/gallery", response_class=HTMLResponse)
def tiles_gallery(dom_filename: str | None = None, data_dir: str | None = None):
    """简单 HTML 画廊：同窗口内展示当前 DOM 对应全部切片的 PNG 预览。"""
    use_data_dir = _resolve_data_dir(data_dir)
    use_dom = (dom_filename or "").strip() or "DOMZone48.tif"
    stem = Path(use_dom).stem
    pattern = f"{stem}_tile_r*_c*.tif"
    files = sorted(use_data_dir.glob(pattern))
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

    uvicorn.run("fastapi_example:app", host="0.0.0.0", port=8000, reload=True)
