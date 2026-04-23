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
import os
from functools import partial
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import (
    JSONResponse,
)

from api.session_routes import create_session_router
from api.segment_routes import create_segment_router
from api.phenotype_routes import create_phenotype_router
from api.tiles_routes import create_tiles_router
from api.upload_routes import create_upload_router
from core.path_resolver import resolve_data_dir
# 与缩略图脚本同目录，便于直接 import
from split_tiff_tiles import split_tiff

import user_session

# 数据目录 = 本文件上级目录（项目根）下的 data 文件夹
DATA_DIR = Path(__file__).resolve().parent.parent / "data"
BACKEND_DIR = Path(__file__).resolve().parent
MODELS_DIR = BACKEND_DIR / "models"
RUN_MODEL_SCRIPT = MODELS_DIR / "run_model_from_config.py"
VISUALIZE_SCRIPT = BACKEND_DIR / "visualize_pkl_mask_centers.py"
DEFAULT_SEG_CONFIG = MODELS_DIR / "20230430_224903_config3.py"

user_session.configure(DATA_DIR)

DEFAULT_CORS_ORIGINS = [
    "http://localhost:5173",
    "http://127.0.0.1:5173",
    "http://localhost:5174",
    "http://127.0.0.1:5174",
    "http://localhost:5175",
    "http://127.0.0.1:5175",
]


def _env_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _cors_allow_origins() -> list[str]:
    """
    读取 CORS 白名单：
    - 环境变量 CORS_ALLOW_ORIGINS（逗号分隔）
    - 未设置时使用开发默认 localhost/127.0.0.1 端口白名单
    """
    raw = os.getenv("CORS_ALLOW_ORIGINS", "").strip()
    if not raw:
        return DEFAULT_CORS_ORIGINS
    origins = [s.strip() for s in raw.split(",") if s.strip()]
    return origins or DEFAULT_CORS_ORIGINS


def _cookie_options() -> dict:
    """
    部署可配置 Cookie：
    - SESSION_COOKIE_SAMESITE: lax|strict|none（默认 lax）
    - SESSION_COOKIE_SECURE: true|false（默认: samesite==none 时 true）
    - SESSION_COOKIE_DOMAIN: 可选，跨子域时按需设置
    """
    samesite = (os.getenv("SESSION_COOKIE_SAMESITE", "lax").strip().lower() or "lax")
    if samesite not in {"lax", "strict", "none"}:
        samesite = "lax"
    secure_default = samesite == "none"
    secure = _env_bool("SESSION_COOKIE_SECURE", secure_default)
    domain = os.getenv("SESSION_COOKIE_DOMAIN", "").strip() or None
    return {
        "max_age": user_session.SESSION_TTL_SEC,
        "httponly": True,
        "samesite": samesite,
        "secure": secure,
        "path": "/",
        "domain": domain,
    }


def _set_session_cookie(resp: JSONResponse, sid: str) -> None:
    opts = _cookie_options()
    resp.set_cookie(
        key=user_session.COOKIE_NAME,
        value=sid,
        max_age=opts["max_age"],
        httponly=opts["httponly"],
        samesite=opts["samesite"],
        secure=opts["secure"],
        path=opts["path"],
        domain=opts["domain"],
    )


app = FastAPI(
    title="林木局 API 示例",
    description="DOM 缩略图生成 + 供 Trees Vue 前端调用的最小示例",
    version="0.1.0",
)

# 生产环境可通过 CORS_ALLOW_ORIGINS 覆盖；默认保留开发常见端口白名单
app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_allow_origins(),
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


app.include_router(
    create_session_router(
        set_session_cookie=_set_session_cookie,
    )
)

app.include_router(
    create_upload_router(
        data_dir=DATA_DIR,
    )
)

app.include_router(
    create_tiles_router(
        resolve_data_dir=partial(resolve_data_dir, default_data_dir=DATA_DIR),
        split_tiff_func=split_tiff,
    )
)


app.include_router(
    create_segment_router(
        resolve_data_dir=partial(resolve_data_dir, default_data_dir=DATA_DIR),
        models_dir=MODELS_DIR,
        run_model_script=RUN_MODEL_SCRIPT,
        visualize_script=VISUALIZE_SCRIPT,
        default_seg_config=DEFAULT_SEG_CONFIG,
    )
)

app.include_router(
    create_phenotype_router(
        resolve_data_dir=partial(resolve_data_dir, default_data_dir=DATA_DIR),
    )
)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("fastapi_example:app", host="0.0.0.0", port=7000)
