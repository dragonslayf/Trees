"""
基于 Cookie 的用户数据目录：users/{session_id}/，会话 1 小时有效（可滑动续期），最多同时 10 个活跃会话。

- 会话过期时间持久化到 ``<DATA_DIR>/.trees_sessions.json``，进程重启后仍能按过期时间删除目录。
- ``cleanup_expired`` 会删除内存中已过期项及对应 ``users/<sid>/``，并同步写回 JSON。
- 磁盘上存在、但不在持久化表中的 ``users/<32hex>/`` 视为孤儿目录并删除（保证文件夹数量与登记一致）。
- 若首次启动尚无 JSON 但 ``users/`` 下已有子目录：按目录 mtime 只保留最新的 ``MAX_ACTIVE_SESSIONS`` 个并登记 1h 过期，其余目录立即删除。
"""
from __future__ import annotations

import json
import os
import re
import shutil
import time
import uuid
from pathlib import Path

COOKIE_NAME = "trees_session_id"
SESSION_TTL_SEC = 3600
MAX_ACTIVE_SESSIONS = 10

# session_id (32 hex) -> 过期时间 Unix 时间戳
_sessions: dict[str, float] = {}

_users_root: Path | None = None
_data_dir: Path | None = None

_SESSION_STORE_NAME = ".trees_sessions.json"


def configure(data_dir: Path) -> None:
    global _users_root, _data_dir
    _data_dir = data_dir.resolve()
    _users_root = (_data_dir / "users").resolve()
    _load_or_bootstrap_sessions()


def _users_root_or_raise() -> Path:
    if _users_root is None:
        raise RuntimeError("user_session.configure() 未调用")
    return _users_root


def _session_store_path() -> Path:
    if _data_dir is None:
        raise RuntimeError("user_session.configure() 未调用")
    return _data_dir / _SESSION_STORE_NAME


def _persist_sessions() -> None:
    path = _session_store_path()
    tmp = path.with_suffix(".json.tmp")
    try:
        payload = json.dumps(_sessions, ensure_ascii=False, sort_keys=True, indent=0)
        tmp.write_text(payload, encoding="utf-8")
        os.replace(tmp, path)
    except OSError:
        try:
            if tmp.is_file():
                tmp.unlink()
        except OSError:
            pass


def _list_hex_user_dirs() -> list[tuple[str, Path, float]]:
    root = _users_root_or_raise()
    if not root.is_dir():
        return []
    out: list[tuple[str, Path, float]] = []
    for p in root.iterdir():
        if p.is_dir() and _SESSION_ID_RE.fullmatch(p.name):
            try:
                m = p.stat().st_mtime
            except OSError:
                continue
            out.append((p.name, p, m))
    return out


def _enforce_max_sessions() -> None:
    """持久化表中会话数超过上限时，按最早过期时间优先移除并删目录。"""
    global _sessions
    root = _users_root_or_raise()
    while len(_sessions) > MAX_ACTIVE_SESSIONS:
        sid = min(_sessions, key=lambda k: _sessions[k])
        _sessions.pop(sid, None)
        d = root / sid
        if d.is_dir():
            shutil.rmtree(d, ignore_errors=True)


def _bootstrap_from_existing_dirs() -> None:
    """无有效持久化记录时，根据现有目录保留最多 MAX 个会话，多出的删目录。"""
    global _sessions
    entries = _list_hex_user_dirs()
    if not entries:
        return
    entries.sort(key=lambda x: x[2], reverse=True)  # 最新 mtime 在前
    keep = entries[:MAX_ACTIVE_SESSIONS]
    drop = entries[MAX_ACTIVE_SESSIONS:]
    for _, p, _ in drop:
        shutil.rmtree(p, ignore_errors=True)
    now = time.time()
    exp = now + SESSION_TTL_SEC
    _sessions = {sid: exp for sid, _, _ in keep}


def _load_or_bootstrap_sessions() -> None:
    global _sessions
    path = _session_store_path()
    _sessions = {}
    if path.is_file():
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(raw, dict):
                _sessions = {
                    k: float(v)
                    for k, v in raw.items()
                    if isinstance(v, (int, float)) and _SESSION_ID_RE.fullmatch(k)
                }
        except (json.JSONDecodeError, OSError, TypeError, ValueError):
            _sessions = {}

    if not _sessions and _list_hex_user_dirs():
        _bootstrap_from_existing_dirs()

    _enforce_max_sessions()
    cleanup_expired()
    _reconcile_orphan_dirs()
    _persist_sessions()


def _reconcile_orphan_dirs() -> None:
    """删除磁盘上未在 _sessions 中登记的 users/<hex>（孤儿目录）。"""
    root = _users_root_or_raise()
    if not root.is_dir():
        return
    known = set(_sessions.keys())
    for p in root.iterdir():
        if not p.is_dir() or not _SESSION_ID_RE.fullmatch(p.name):
            continue
        if p.name not in known:
            shutil.rmtree(p, ignore_errors=True)


def maintenance_cleanup() -> None:
    """供 /health 等入口定时调用：过期会话 + 超上限修剪 + 孤儿目录 + 持久化文件同步。"""
    cleanup_expired()
    _enforce_max_sessions()
    _reconcile_orphan_dirs()
    _persist_sessions()


def cleanup_expired() -> None:
    """删除已过期会话的内存记录与磁盘目录，并写回持久化文件。"""
    root = _users_root_or_raise()
    now = time.time()
    expired = [sid for sid, exp in _sessions.items() if exp <= now]
    changed = bool(expired)
    for sid in expired:
        _sessions.pop(sid, None)
        d = root / sid
        if d.is_dir():
            shutil.rmtree(d, ignore_errors=True)
    if changed:
        _persist_sessions()


def active_count() -> int:
    cleanup_expired()
    return len(_sessions)


def get_session_expiry(sid: str) -> float | None:
    cleanup_expired()
    return _sessions.get(sid)


def is_valid_session(sid: str | None) -> bool:
    if not sid or not _SESSION_ID_RE.fullmatch(sid):
        return False
    cleanup_expired()
    exp = _sessions.get(sid)
    return exp is not None and exp > time.time()


def refresh_session_expiry(sid: str) -> float | None:
    """
    有效会话每次 init 时滑动续期 1h，并持久化。
    若 sid 无效则返回 None。
    """
    cleanup_expired()
    if sid not in _sessions:
        return None
    exp = time.time() + SESSION_TTL_SEC
    _sessions[sid] = exp
    _persist_sessions()
    return exp


_SESSION_ID_RE = re.compile(r"^[a-f0-9]{32}$")


def register_session() -> tuple[str, float]:
    """
    新建会话目录并登记。调用前应先 cleanup_expired。
    若已达上限，抛出 SessionLimitError。
    """
    root = _users_root_or_raise()
    cleanup_expired()
    if len(_sessions) >= MAX_ACTIVE_SESSIONS:
        raise SessionLimitError("当前活跃会话已达上限（10），请稍后再试")
    sid = uuid.uuid4().hex
    root.mkdir(parents=True, exist_ok=True)
    user_dir = root / sid
    user_dir.mkdir(parents=False, exist_ok=True)
    exp = time.time() + SESSION_TTL_SEC
    _sessions[sid] = exp
    _persist_sessions()
    return sid, exp


def ensure_session_cookie(sid: str) -> None:
    """若目录被删但内存仍有记录，重建空目录。"""
    root = _users_root_or_raise()
    d = root / sid
    d.mkdir(parents=True, exist_ok=True)


def session_data_dir_relative(sid: str) -> str:
    """供前端传给各 API 的 data_dir 相对标识：users/<id>"""
    return f"users/{sid}"


class SessionLimitError(Exception):
    pass
