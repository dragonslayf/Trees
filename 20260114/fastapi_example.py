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
from pathlib import Path

from io import BytesIO

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, Response

# 与缩略图脚本同目录，便于直接 import
from create_dom_thumbnail import create_dom_thumbnail

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
    import rasterio
    import numpy as np
    try:
        from PIL import Image
    except ImportError:
        raise HTTPException(
            status_code=500,
            detail="需要安装 Pillow: pip install Pillow",
        )
    use_dir = _resolve_data_dir(data_dir)
    thumb_name = (filename or "").strip() or "DOMZone48_thumb_800x800.tif"
    path = use_dir / thumb_name
    if not path.is_file():
        raise HTTPException(status_code=404, detail="请先调用 POST /api/thumbnail/generate 生成缩略图")
    with rasterio.open(path) as src:
        data = src.read()
    if data.ndim == 3:
        # 多波段：取前 3 个波段做 RGB，归一化到 0–255
        rgb = data[:3].transpose(1, 2, 0)
        dmin, dmax = rgb.min(), rgb.max()
        if dmax > dmin:
            rgb = ((rgb.astype(np.float64) - dmin) / (dmax - dmin) * 255).astype(np.uint8)
        else:
            rgb = np.zeros_like(rgb, dtype=np.uint8)
        img = Image.fromarray(rgb)
    else:
        # 单波段：伪彩色
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
    return Response(content=buf.read(), media_type="image/png")


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
