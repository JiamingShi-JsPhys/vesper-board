"""Browser-obtained sessions: stored encrypted, restored into a requests session.

Two things can be kept:
  * a Canvas cookie jar (from the embedded login window)
  * an AMS `Admin-Token` JWT

Both are written through DPAPI, so the file is useless off this machine.
"""

from __future__ import annotations

import json

from . import paths, security


def save_cookie_map(hosts: dict[str, dict[str, str]]) -> None:
    """按域名保存登录窗拿到的全部 westlake cookie。

    静默续期要靠统一身份认证那层（.iam.westlake.edu.cn）的会话来免密，
    只存 canvas/ams 两个域是不够的。
    """
    security.save_secret(paths.cookie_map_file(),
                         json.dumps(hosts, ensure_ascii=False))


def load_cookie_map() -> dict[str, dict[str, str]]:
    raw = security.load_secret(paths.cookie_map_file())
    if not raw:
        return {}
    try:
        data = json.loads(raw)
    except ValueError:
        return {}
    if not isinstance(data, dict):
        return {}
    out: dict[str, dict[str, str]] = {}
    for host, jar in data.items():
        if isinstance(jar, dict):
            out[str(host)] = {str(k): str(v) for k, v in jar.items()}
    return out


def save_cookies(cookies: dict[str, str]) -> None:
    security.save_secret(paths.canvas_session_file(), json.dumps(cookies, ensure_ascii=False))


def clear_cookie_map() -> None:
    """登出时一并清掉登录窗的 cookie 快照，否则静默续期会拿它把会话复活。"""
    security.save_secret(paths.cookie_map_file(), "")


def load_cookies() -> dict[str, str]:
    raw = security.load_secret(paths.canvas_session_file())
    if not raw:
        return {}
    try:
        data = json.loads(raw)
    except ValueError:
        return {}
    return {str(k): str(v) for k, v in data.items()} if isinstance(data, dict) else {}


def clear_cookies() -> None:
    # 走 save_secret("")：主文件、.plain 回退和钥匙串条目一起清掉
    security.save_secret(paths.canvas_session_file(), "")


def save_ams_cookies(cookies: dict[str, str]) -> None:
    security.save_secret(paths.ams_session_file(), json.dumps(cookies, ensure_ascii=False))


def load_ams_cookies() -> dict[str, str]:
    raw = security.load_secret(paths.ams_session_file())
    if not raw:
        return {}
    try:
        data = json.loads(raw)
    except ValueError:
        return {}
    return {str(k): str(v) for k, v in data.items()} if isinstance(data, dict) else {}


def clear_ams_cookies() -> None:
    security.save_secret(paths.ams_session_file(), "")


def has_canvas_session() -> bool:
    return bool(load_cookies())


def has_ams_session() -> bool:
    return bool(load_ams_cookies())


def has_any_canvas_auth() -> bool:
    return bool(load_cookies()) or bool(security.load_secret(paths.canvas_token_file()))
