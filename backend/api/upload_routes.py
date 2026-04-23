from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, File, HTTPException, Request, UploadFile

import user_session
from storage.workspace_files import (
    read_upload_manifest,
    remove_legacy_tile_result_dir,
    safe_unlink_user_file,
    wipe_segmentation_result,
    write_upload_manifest,
)


def _safe_upload_name(name: str) -> str:
    base = Path(name).name
    if not base or ".." in base or "/" in base or "\\" in base:
        raise HTTPException(status_code=400, detail="非法文件名")
    return base


def create_upload_router(*, data_dir: Path) -> APIRouter:
    router = APIRouter()

    @router.post("/api/user/upload")
    async def user_upload(
        request: Request,
        dom: UploadFile | None = File(None),
        chm: UploadFile | None = File(None),
        csv: UploadFile | None = File(None),
    ):
        """将 DOM/CHM/CSV 保存到当前 Cookie 对应目录 ``users/<id>/``。"""
        user_session.maintenance_cleanup()
        sid = request.cookies.get(user_session.COOKIE_NAME)
        if not user_session.is_valid_session(sid):
            raise HTTPException(
                status_code=401,
                detail="会话无效或已过期，请先刷新页面并重新建立会话",
            )
        user_dir = (data_dir / "users" / sid).resolve()
        users_root = (data_dir / "users").resolve()
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

        manifest_before = read_upload_manifest(user_dir)

        has_dom = any(k == "dom" for _, _, k in planned)
        if has_dom:
            dom_uf = next(uf for uf, _, k in planned if k == "dom")
            new_dom_name = _safe_upload_name(dom_uf.filename)
            prev_dom = manifest_before.get("dom")
            if prev_dom and prev_dom != new_dom_name:
                safe_unlink_user_file(user_dir / prev_dom)
            wipe_segmentation_result(user_dir)
            remove_legacy_tile_result_dir(user_dir)

        for uf, _, key in planned:
            if key != "chm" and key != "csv":
                continue
            fname = _safe_upload_name(uf.filename)
            prev = manifest_before.get(key)
            if prev and prev != fname:
                safe_unlink_user_file(user_dir / prev)

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

        write_upload_manifest(user_dir, manifest_after)

        saved_keys = [key for _, _, key in planned]
        return {
            "ok": True,
            "saved": saved,
            "saved_keys": saved_keys,
            "data_dir": user_session.session_data_dir_relative(sid),
        }

    @router.get("/api/user/files")
    def list_user_files(request: Request):
        """列出当前 Cookie 会话目录 ``users/<id>/`` 下的文件名（不含子目录）。"""
        user_session.maintenance_cleanup()
        sid = request.cookies.get(user_session.COOKIE_NAME)
        if not user_session.is_valid_session(sid):
            raise HTTPException(
                status_code=401,
                detail="会话无效或已过期，请先在数据管理页建立会话",
            )
        user_dir = (data_dir / "users" / sid).resolve()
        users_root = (data_dir / "users").resolve()
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

    return router
