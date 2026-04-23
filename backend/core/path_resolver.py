from __future__ import annotations

import re
from pathlib import Path


def resolve_data_dir(data_dir: str | None, default_data_dir: Path) -> Path:
    """
    请求使用的数据目录：
    - 默认 ``default_data_dir``
    - ``users/<32位hex>`` 解析为 ``default_data_dir/users/...``（并做越界校验）
    - 其他路径仅在目录存在时生效
    """
    if not data_dir or not data_dir.strip():
        return default_data_dir
    s = data_dir.strip().replace("\\", "/")
    if s.startswith("users/"):
        rel = s[6:].strip("/")
        if re.match(r"^[a-f0-9]{32}$", rel):
            p = (default_data_dir / "users" / rel).resolve()
            users_root = (default_data_dir / "users").resolve()
            try:
                p.relative_to(users_root)
            except ValueError:
                return default_data_dir
            return p if p.is_dir() else default_data_dir
    p = Path(data_dir).resolve()
    return p if p.is_dir() else default_data_dir
