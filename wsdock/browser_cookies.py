"""Read the WebEngine profile's cookie database.

`QWebEngineCookieStore.loadAllCookies()` does not emit cookies that were
restored from disk (only ones set live during the session), so the reliable
source is the profile's own SQLite file — opened read-only, which works even
while Chromium has it open.

Values are plaintext in QtWebEngine's profile here; if a future build starts
encrypting them (`encrypted_value` instead of `value`), we simply get nothing
and the caller falls back to the live `cookieAdded` collector.
"""

from __future__ import annotations

import sqlite3

from . import paths
from .net import in_domain


def read_cookies(host_suffix: str) -> dict[str, str]:
    """Return {name: value} for cookies whose host ends with `host_suffix`."""
    db = paths.web_profile_dir() / "Cookies"
    if not db.exists():
        return {}
    try:
        con = sqlite3.connect(f"file:{db.as_posix()}?mode=ro", uri=True, timeout=3)
        try:
            rows = con.execute(
                "SELECT host_key, name, value, is_secure FROM cookies "
                "ORDER BY last_access_utc DESC"
            ).fetchall()
        finally:
            con.close()
    except sqlite3.Error:
        return {}

    out: dict[str, str] = {}
    for host, name, value, _secure in rows:
        if not host or not name:
            continue
        if in_domain(str(host), host_suffix):
            if value:
                out.setdefault(str(name), str(value))   # newest first wins
    return out
