from __future__ import annotations

from typing import Callable

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse

import user_session


def create_session_router(*, set_session_cookie: Callable[[JSONResponse, str], None]) -> APIRouter:
    router = APIRouter()

    @router.post("/api/session/init")
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
            r = JSONResponse(
                {
                    "ok": True,
                    "data_dir": user_session.session_data_dir_relative(sid),
                    "expires_at": exp,
                    "slots_used": user_session.active_count(),
                    "slots_max": user_session.MAX_ACTIVE_SESSIONS,
                    "is_new": False,
                }
            )
            set_session_cookie(r, sid)
            return r

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
        set_session_cookie(r, sid)
        return r

    return router
