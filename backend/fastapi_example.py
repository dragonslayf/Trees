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
import math
import re
import shutil
import subprocess
import sys
from pathlib import Path
from urllib.parse import urlencode

from fastapi import FastAPI, File, HTTPException, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import (
    FileResponse,
    HTMLResponse,
    JSONResponse,
    Response,
    StreamingResponse,
)
from pydantic import BaseModel

# 与缩略图脚本同目录，便于直接 import
from split_tiff_tiles import split_tiff
from visualize_pkl_mask_centers import merge_tile_json_to_whole_json

import user_session

# 数据目录 = 本文件上级目录（项目根）下的 data 文件夹
DATA_DIR = Path(__file__).resolve().parent.parent / "data"
TREES_ROOT = DATA_DIR.parent
MODELS_DIR = TREES_ROOT / "models"
BACKEND_DIR = TREES_ROOT / "backend"
RUN_MODEL_SCRIPT = MODELS_DIR / "run_model_from_config.py"
VISUALIZE_SCRIPT = BACKEND_DIR / "visualize_pkl_mask_centers.py"
DEFAULT_SEG_CONFIG = MODELS_DIR / "20230430_224903_config3.py"

user_session.configure(DATA_DIR)

UPLOAD_MANIFEST_NAME = ".upload_manifest.json"


def _segmentation_result_dir(data_dir: Path) -> Path:
    """切片 TIFF、pkl、等与分割相关的输出根目录：``{data_dir}/segmentation_result``"""
    return (data_dir / "segmentation_result").resolve()


def _marked_result_dir(data_dir: Path) -> Path:
    """单木位置可视化：``{data_dir}/segmentation_result/marked_result``"""
    return (_segmentation_result_dir(data_dir) / "marked_result").resolve()


def _dom_tile_paths(data_dir: Path, stem: str) -> list[Path]:
    """某 DOM stem 对应的全部切片路径（与 pkl 同在 segmentation_result）。"""
    return sorted(_segmentation_result_dir(data_dir).glob(f"{stem}_tile_r*_c*.tif"))


def _read_upload_manifest(user_dir: Path) -> dict[str, str]:
    p = user_dir / UPLOAD_MANIFEST_NAME
    if not p.is_file():
        return {}
    try:
        raw = json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return {}
    out: dict[str, str] = {}
    for k in ("dom", "chm", "csv"):
        v = raw.get(k)
        if isinstance(v, str) and v.strip():
            out[k] = v.strip()
    return out


def _write_upload_manifest(user_dir: Path, manifest: dict[str, str]) -> None:
    (user_dir / UPLOAD_MANIFEST_NAME).write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def _safe_unlink_user_file(path: Path) -> None:
    try:
        if path.is_file():
            path.unlink()
    except OSError:
        pass


def _remove_legacy_tile_result_dir(data_dir: Path) -> None:
    """历史 ``tile_result`` 与 segmentation_result 并存时仅保留后者；上传替换时可删遗留目录。"""
    tr = (data_dir / "tile_result").resolve()
    if tr.is_dir():
        shutil.rmtree(tr, ignore_errors=True)


def _wipe_segmentation_result(data_dir: Path) -> None:
    seg = _segmentation_result_dir(data_dir)
    if seg.is_dir():
        shutil.rmtree(seg, ignore_errors=True)


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
    """删除旧版固定命名 ``{tile}_vis.png`` 及 centers 遗留（与按参数后缀命名共存清理）。"""
    vis_path = marked_dir / f"{tile_stem}_vis.png"
    legacy_centers = marked_dir / f"{pkl_stem}_centers.png"
    for p in (
        vis_path,
        vis_path.with_suffix(".json"),
        legacy_centers,
        legacy_centers.with_suffix(".json"),
    ):
        _unlink_if_exists(p)


def _vis_param_suffix(score_thr: float, min_canopy_area_m2: float) -> str:
    """与 ``visualize_pkl_mask_centers.py`` 输出文件名后缀一致：置信度(百分整数)+最小面积(m²)。"""
    pct = int(round(float(score_thr) * 100))
    s = f"{float(min_canopy_area_m2):.4f}".rstrip("0").rstrip(".") or "0"
    s = s.replace(".", "p")
    return f"c{pct}m{s}"


def _marked_vis_png_name(tile_stem: str, score_thr: float, min_canopy_area_m2: float) -> str:
    return f"{tile_stem}_vis_{_vis_param_suffix(score_thr, min_canopy_area_m2)}.png"


def _marked_vis_outputs_ready(marked_dir: Path, png_name: str) -> bool:
    p = marked_dir / png_name
    return p.is_file() and p.with_suffix(".json").is_file()


def _unlink_marked_vis_pair(marked_dir: Path, png_name: str) -> None:
    _unlink_if_exists(marked_dir / png_name)
    _unlink_if_exists((marked_dir / png_name).with_suffix(".json"))


app = FastAPI(
    title="林木局 API 示例",
    description="DOM 缩略图生成 + 供 Trees Vue 前端调用的最小示例",
    version="0.1.0",
)

# Vue 开发服务器常见端口 5173/5174（多实例时 Vite 会顺延）；按需增删
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:5174",
        "http://127.0.0.1:5174",
        "http://localhost:5175",
        "http://127.0.0.1:5175",
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
    """顺带触发会话过期与孤儿目录清理，便于长时间无业务请求时仍能回收磁盘。"""
    user_session.maintenance_cleanup()
    return {"status": "ok"}


@app.post("/api/session/init")
def session_init(request: Request):
    """
    建立或恢复会话：设置 HttpOnly Cookie（1 小时），数据目录为 ``users/<session_id>``。
    活跃会话满 10 个时返回 429。
    """
    user_session.maintenance_cleanup()
    sid = request.cookies.get(user_session.COOKIE_NAME)

    if sid and user_session.is_valid_session(sid):
        user_session.ensure_session_cookie(sid)
        exp = user_session.refresh_session_expiry(sid)
        if exp is None:
            exp = user_session.get_session_expiry(sid)
        return JSONResponse(
            {
                "ok": True,
                "data_dir": user_session.session_data_dir_relative(sid),
                "expires_at": exp,
                "slots_used": user_session.active_count(),
                "slots_max": user_session.MAX_ACTIVE_SESSIONS,
                "is_new": False,
            }
        )

    try:
        sid, exp = user_session.register_session()
    except user_session.SessionLimitError as e:
        raise HTTPException(status_code=429, detail=str(e)) from e

    payload = {
        "ok": True,
        "data_dir": user_session.session_data_dir_relative(sid),
        "expires_at": exp,
        "slots_used": user_session.active_count(),
        "slots_max": user_session.MAX_ACTIVE_SESSIONS,
        "is_new": True,
    }
    r = JSONResponse(payload)
    r.set_cookie(
        key=user_session.COOKIE_NAME,
        value=sid,
        max_age=user_session.SESSION_TTL_SEC,
        httponly=True,
        samesite="lax",
        path="/",
    )
    return r


def _safe_upload_name(name: str) -> str:
    base = Path(name).name
    if not base or ".." in base or "/" in base or "\\" in base:
        raise HTTPException(status_code=400, detail="非法文件名")
    return base


@app.post("/api/user/upload")
async def user_upload(
    request: Request,
    dom: UploadFile | None = File(None),
    chm: UploadFile | None = File(None),
    csv: UploadFile | None = File(None),
):
    """将 DOM/CHM/CSV 保存到当前 Cookie 对应目录 ``users/<id>/``。

    再次上传同类型文件时：删除该类型上一份原始文件；上传新 DOM 时还会清空
    ``segmentation_result`` 及遗留的 ``tile_result``（切分与分割派生结果）。
    """
    user_session.maintenance_cleanup()
    sid = request.cookies.get(user_session.COOKIE_NAME)
    if not user_session.is_valid_session(sid):
        raise HTTPException(
            status_code=401,
            detail="会话无效或已过期，请先刷新页面并重新建立会话",
        )
    user_dir = (DATA_DIR / "users" / sid).resolve()
    users_root = (DATA_DIR / "users").resolve()
    try:
        user_dir.relative_to(users_root)
    except ValueError as e:
        raise HTTPException(status_code=500, detail="用户目录异常") from e

    planned: list[tuple[UploadFile, str, str]] = []
    for uf, label, key in (
        (dom, "dom", "dom"),
        (chm, "chm", "chm"),
        (csv, "csv", "csv"),
    ):
        if uf is not None and uf.filename:
            planned.append((uf, label, key))

    if not planned:
        raise HTTPException(status_code=400, detail="请至少选择一个文件上传")

    manifest_before = _read_upload_manifest(user_dir)

    has_dom = any(k == "dom" for _, _, k in planned)
    if has_dom:
        dom_uf = next(uf for uf, _, k in planned if k == "dom")
        new_dom_name = _safe_upload_name(dom_uf.filename)
        prev_dom = manifest_before.get("dom")
        if prev_dom and prev_dom != new_dom_name:
            _safe_unlink_user_file(user_dir / prev_dom)
        _wipe_segmentation_result(user_dir)
        _remove_legacy_tile_result_dir(user_dir)

    for uf, label, key in planned:
        if key != "chm" and key != "csv":
            continue
        fname = _safe_upload_name(uf.filename)
        prev = manifest_before.get(key)
        if prev and prev != fname:
            _safe_unlink_user_file(user_dir / prev)

    saved: list[str] = []
    manifest_after = dict(manifest_before)
    for uf, label, key in planned:
        fname = _safe_upload_name(uf.filename)
        dest = user_dir / fname
        body = await uf.read()
        if len(body) > 200 * 1024 * 1024:
            raise HTTPException(status_code=413, detail=f"{label} 文件过大（单文件上限 200MB）")
        dest.write_bytes(body)
        saved.append(fname)
        manifest_after[key] = fname

    _write_upload_manifest(user_dir, manifest_after)

    saved_keys = [key for _, _, key in planned]
    return {
        "ok": True,
        "saved": saved,
        "saved_keys": saved_keys,
        "data_dir": user_session.session_data_dir_relative(sid),
    }


@app.get("/api/user/files")
def list_user_files(request: Request):
    """列出当前 Cookie 会话目录 ``users/<id>/`` 下的文件名（不含子目录），供前端自动识别 DOM 等。"""
    user_session.maintenance_cleanup()
    sid = request.cookies.get(user_session.COOKIE_NAME)
    if not user_session.is_valid_session(sid):
        raise HTTPException(
            status_code=401,
            detail="会话无效或已过期，请先在数据管理页建立会话",
        )
    user_dir = (DATA_DIR / "users" / sid).resolve()
    users_root = (DATA_DIR / "users").resolve()
    try:
        user_dir.relative_to(users_root)
    except ValueError as e:
        raise HTTPException(status_code=500, detail="用户目录异常") from e
    if not user_dir.is_dir():
        return {
            "data_dir": user_session.session_data_dir_relative(sid),
            "files": [],
        }
    files = [p.name for p in user_dir.iterdir() if p.is_file() and not p.name.startswith(".")]
    return {
        "data_dir": user_session.session_data_dir_relative(sid),
        "files": sorted(files),
    }


def _resolve_data_dir(data_dir: str | None) -> Path:
    """请求使用的数据目录：默认 DATA_DIR；``users/<32位hex>`` 解析为 ``DATA_DIR/users/...``。"""
    if not data_dir or not data_dir.strip():
        return DATA_DIR
    s = data_dir.strip().replace("\\", "/")
    if s.startswith("users/"):
        rel = s[6:].strip("/")
        if re.match(r"^[a-f0-9]{32}$", rel):
            p = (DATA_DIR / "users" / rel).resolve()
            users_root = (DATA_DIR / "users").resolve()
            try:
                p.relative_to(users_root)
            except ValueError:
                return DATA_DIR
            return p if p.is_dir() else DATA_DIR
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
    """``segmentation_result`` 下的切片 TIFF 转 PNG，供画廊页 img 引用。"""
    use_dir = _resolve_data_dir(data_dir)
    name = (filename or "").strip()
    if not name or Path(name).name != name:
        raise HTTPException(status_code=400, detail="非法文件名")
    base = _segmentation_result_dir(use_dir).resolve()
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
    切片写入 ``data_dir/segmentation_result``（与 pkl 同目录）。已存在则跳过。
    """
    use_data_dir = _resolve_data_dir(data_dir)
    use_dom = (dom_filename or "").strip()
    dom_path = use_data_dir / use_dom
    if not dom_path.is_file():
        raise HTTPException(status_code=404, detail=f"DOM 文件不存在: {use_dom}")
    stem = dom_path.stem
    tile_root = _segmentation_result_dir(use_data_dir)
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
        "segmentation_result_dir": str(tile_root),
        "stem": stem,
        "dom_filename": use_dom,
        "tiles": [f.name for f in existing],
        "split_run": split_run,
    }


@app.get("/api/tiles/gallery", response_class=HTMLResponse)
def tiles_gallery(dom_filename: str | None = None, data_dir: str | None = None):
    """简单 HTML 画廊：展示 ``segmentation_result`` 内当前 DOM 对应全部切片的 PNG 预览。"""
    use_data_dir = _resolve_data_dir(data_dir)
    use_dom = (dom_filename or "").strip()
    stem = Path(use_dom).stem
    pattern = f"{stem}_tile_r*_c*.tif"
    files = sorted(_segmentation_result_dir(use_data_dir).glob(pattern))
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
    min_canopy_area_m2: float = 0.0


@app.get("/api/segment/has-existing")
def segment_has_existing(dom_filename: str | None = None, data_dir: str | None = None):
    """检查当前 DOM 对应切片是否已有任意 result.pkl（用于前端覆盖确认）。"""
    use_data_dir = _resolve_data_dir(data_dir)
    use_dom = (dom_filename or "").strip()
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


@app.post("/api/segment/run")
def segment_run(body: SegmentRunIn):
    """
    对 ``segmentation_result`` 下该 DOM 的全部 800×800 切片依次调用 run_model_from_config.py；
    pkl 与切片同目录，可视化写入 ``segmentation_result/marked_result``。

    响应为 NDJSON 流：每行一条 JSON，含 type=progress|done|error，progress 的 n/total
    为已完成的块数（每块含推理 + 可视化），与 ``/api/segment/regenerate-vis`` 一致便于前端进度条。
    """
    if not RUN_MODEL_SCRIPT.is_file():
        raise HTTPException(status_code=500, detail=f"未找到脚本: {RUN_MODEL_SCRIPT}")
    if not VISUALIZE_SCRIPT.is_file():
        raise HTTPException(status_code=500, detail=f"未找到脚本: {VISUALIZE_SCRIPT}")

    use_data_dir = _resolve_data_dir(body.data_dir)
    use_dom = (body.dom_filename or "").strip()
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
    total = len(tiles)

    def ndjson_stream():
        try:
            yield json.dumps(
                {"type": "progress", "n": 0, "total": total},
                ensure_ascii=False,
            ) + "\n"
            processed = 0
            for t in tiles:
                pkl_path = pkl_dir / f"{t.stem}_result.pkl"
                vis_png = _marked_vis_png_name(
                    t.stem, body.score_thr, body.min_canopy_area_m2
                )
                vis_path = marked_dir / vis_png
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

                if _marked_vis_outputs_ready(marked_dir, vis_png):
                    processed += 1
                else:
                    _unlink_marked_vis_pair(marked_dir, vis_png)
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
                        "--min-canopy-area-m2",
                        str(body.min_canopy_area_m2),
                    ]
                    _run_subprocess_or_500(vcmd, cwd=MODELS_DIR)
                    processed += 1
                yield json.dumps(
                    {"type": "progress", "n": processed, "total": total},
                    ensure_ascii=False,
                ) + "\n"
            whole_json: str | None = None
            whole_mark_png: str | None = None
            whole_json_error: str | None = None
            try:
                p_json, p_mark = merge_tile_json_to_whole_json(
                    dom_image=use_data_dir / use_dom,
                    seg_result_dir=pkl_dir,
                    marked_dir=marked_dir,
                    score_thr=body.score_thr,
                    min_canopy_area_m2=body.min_canopy_area_m2,
                    tile=800,
                    overlap=200,
                )
                whole_json = str(p_json)
                whole_mark_png = str(p_mark)
            except Exception as e:
                whole_json_error = str(e)
            done_payload: dict = {
                "type": "done",
                "ok": True,
                "processed": processed,
                "data_dir": str(use_data_dir),
                "segmentation_result_dir": str(pkl_dir),
                "marked_result_dir": str(marked_dir),
                "dom_filename": use_dom,
                "score_thr": body.score_thr,
                "min_canopy_area_m2": body.min_canopy_area_m2,
            }
            if whole_json:
                done_payload["whole_centers_json"] = whole_json
            if whole_mark_png:
                done_payload["whole_mark_png"] = whole_mark_png
            if whole_json_error:
                done_payload["whole_centers_json_error"] = whole_json_error
            yield json.dumps(done_payload, ensure_ascii=False) + "\n"
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


class SegmentRegenerateVisIn(BaseModel):
    dom_filename: str | None = None
    data_dir: str | None = None
    score_thr: float = 0.3
    min_canopy_area_m2: float = 0.0


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
    use_dom = (body.dom_filename or "").strip()
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
                vis_png = _marked_vis_png_name(
                    t.stem, body.score_thr, body.min_canopy_area_m2
                )
                vis_path = marked_dir / vis_png
                if _marked_vis_outputs_ready(marked_dir, vis_png):
                    regenerated += 1
                else:
                    _unlink_marked_vis_pair(marked_dir, vis_png)
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
                        "--min-canopy-area-m2",
                        str(body.min_canopy_area_m2),
                    ]
                    _run_subprocess_or_500(vcmd, cwd=MODELS_DIR)
                    regenerated += 1
                yield json.dumps(
                    {"type": "progress", "n": regenerated, "total": total},
                    ensure_ascii=False,
                ) + "\n"
            whole_json: str | None = None
            whole_mark_png: str | None = None
            whole_json_error: str | None = None
            try:
                p_json, p_mark = merge_tile_json_to_whole_json(
                    dom_image=use_data_dir / use_dom,
                    seg_result_dir=pkl_dir,
                    marked_dir=marked_dir,
                    score_thr=body.score_thr,
                    min_canopy_area_m2=body.min_canopy_area_m2,
                    tile=800,
                    overlap=200,
                )
                whole_json = str(p_json)
                whole_mark_png = str(p_mark)
            except Exception as e:
                whole_json_error = str(e)
            done_payload: dict = {
                "type": "done",
                "ok": True,
                "regenerated": regenerated,
                "data_dir": str(use_data_dir),
                "segmentation_result_dir": str(pkl_dir),
                "marked_result_dir": str(marked_dir),
                "dom_filename": use_dom,
                "score_thr": body.score_thr,
                "min_canopy_area_m2": body.min_canopy_area_m2,
            }
            if whole_json:
                done_payload["whole_centers_json"] = whole_json
            if whole_mark_png:
                done_payload["whole_mark_png"] = whole_mark_png
            if whole_json_error:
                done_payload["whole_centers_json_error"] = whole_json_error
            yield json.dumps(done_payload, ensure_ascii=False) + "\n"
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
    """返回 ``segmentation_result/marked_result`` 下的可视化 PNG（如 *_vis.png）。"""
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
    score_thr: float | None = None,
    min_canopy_area_m2: float | None = None,
):
    """分割结果画廊：``segmentation_result`` 切片与 ``marked_result`` 可视化。"""
    use_data_dir = _resolve_data_dir(data_dir)
    use_dom = (dom_filename or "").strip()
    stem = Path(use_dom).stem
    marked_dir = _marked_result_dir(use_data_dir)
    cache_token = (t or "").strip()
    tiles = _dom_tile_paths(use_data_dir, stem)
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
        vis_suffixed = _marked_vis_png_name(tile_path.stem, thr, min_m2)
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


@app.get("/api/phenotype/extract")
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
    use_data_dir = _resolve_data_dir(data_dir)
    use_dom = (dom_filename or "").strip()
    if not use_dom:
        raise HTTPException(status_code=400, detail="缺少 dom_filename")
    dom_path = use_data_dir / use_dom
    if not dom_path.is_file():
        raise HTTPException(status_code=404, detail=f"DOM 文件不存在: {use_dom}")

    stem = Path(use_dom).stem
    whole_json = _segmentation_result_dir(use_data_dir) / f"{stem}_whole_centers.json"
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
