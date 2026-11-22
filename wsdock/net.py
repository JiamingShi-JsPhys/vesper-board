"""请求层：cookie 去重与域名绑定，以及「无凭据」的文件传输通道。

这里有三条必须守住的规则：

1. **cookie 必须带域名。** ``jar.update({name: value})`` 造出来的是 domain 为空的
   cookie，``http.cookiejar`` 会把它发给*任何*主机——请求一旦落到第三方域名，
   登录态就跟着出去了。所有注入都走 :func:`set_cookies`；发请求前
   ``_dedupe`` 还会把漏网的、没有域名的 cookie 直接丢掉。
2. **传输不带身份。** Canvas 的上传地址常常是对象存储的另一个域名（S3 等），
   那里只需要 URL 里自带的签名；绝不能附带 Bearer token 或会话 cookie。
   这类请求走 :class:`TransferSession`。
3. **跨域请求要走无凭据通道。** 判断用 :func:`same_origin`，按 scheme + 主机 +
   端口比较，不做后缀匹配。
"""

from __future__ import annotations

import threading
from urllib.parse import urlsplit

import requests

_DEDUPE_LOCK = threading.RLock()


def origin(url: str) -> tuple[str, str, int | None]:
    """(scheme, host, port)；缺省端口按 scheme 补上。

    端口畸形（``https://host:abc/``）时返回空主机——调用方按「不同来源」处理，
    而不是让 ValueError 冒到刷新流程里。
    """
    parts = urlsplit(url)
    scheme = (parts.scheme or "").lower()
    try:
        port = parts.port
        host = (parts.hostname or "").lower()
    except ValueError:
        return scheme, "", None
    if port is None:
        port = 443 if scheme == "https" else 80 if scheme == "http" else None
    return scheme, host, port


def same_origin(left: str, right: str) -> bool:
    """两个 URL 是否同一个来源（同 scheme、同主机、同端口）。"""
    return origin(left) == origin(right)


def in_domain(domain: str, base: str) -> bool:
    """``domain`` 是否就是 ``base`` 或它的子域。

    必须是后缀匹配，不能用 ``"x" in domain``——那样
    ``westlake.edu.cn.evil.com`` 也会被判成校内域。
    """
    d = (domain or "").strip().lstrip(".").lower()
    b = (base or "").strip().lstrip(".").lower()
    if not d or not b:
        return False
    return d == b or d.endswith("." + b)


def set_cookies(jar, base_url: str, cookies: dict) -> None:
    """把 ``name -> value`` 注入 cookie jar，并绑定到 base_url 的主机。

    不给 domain 的 cookie 会被发往任意主机，所以这里必须显式写死。
    """
    host = (urlsplit(base_url).hostname or "").lower()
    if not host:
        return
    for name, value in cookies.items():
        if name is None or value is None:
            continue
        jar.set(str(name), str(value), domain=host, path="/")


class TransferSession(requests.Session):
    """不带身份的文件传输通道：没有 Authorization，也没有 cookie。

    只用于「Canvas 给了一个外部上传/下载地址」这种场景。对象存储靠 URL 里的
    签名校验，多带一份 Canvas 令牌只会多一次泄露机会。

    ``trust_env = False``：不读 ``HTTP(S)_PROXY``，也不让 ``~/.netrc`` 自动
    附上该主机的 basic 认证——传输通道要么干净，要么不用。
    """

    def __init__(self, user_agent: str = "") -> None:
        super().__init__()
        self.trust_env = False
        if user_agent:
            self.headers["User-Agent"] = user_agent
        self.headers["Accept"] = "*/*"


def cookie_value(jar, name: str, default: str = "") -> str:
    """从 jar 里取第一个同名 cookie 的值（绕开 CookieConflictError）。"""
    for cookie in jar:
        if cookie.name == name:
            return cookie.value
    return default


def _beats(new, old) -> bool:
    """同 name+path 时谁留下：有 domain 的优先，其次后写入的优先。

    注入发生在客户端构造时，服务器 Set-Cookie 发生在之后，所以「后写优先」
    在正常时序下就是服务器下发的那份胜出。
    """
    if bool(new.domain) != bool(old.domain):
        return bool(new.domain)
    return True


def _dedupe(jar) -> None:
    """同名同路径只留一份，并且丢掉所有没有域名的 cookie。

    没有域名的 cookie 会被 ``http.cookiejar`` 发给任意主机——这是最危险的一种。
    正常路径上 ``set_cookies`` 都会绑定域名，这里兜底。
    """
    with _DEDUPE_LOCK:
        cookies = list(jar)
        if not cookies:
            return

        keep: dict[tuple[str, str], object] = {}
        for cookie in cookies:
            if not cookie.domain:
                continue
            key = (cookie.name, cookie.path or "/")
            current = keep.get(key)
            if current is None or _beats(cookie, current):
                keep[key] = cookie

        if len(keep) == len(cookies):
            return

        wanted = {id(cookie) for cookie in keep.values()}
        jar.clear()
        for cookie in cookies:
            if id(cookie) in wanted:
                jar.set_cookie(cookie)


class GuardedSession(requests.Session):
    def prepare_request(self, request):  # noqa: D102 - requests 内部钩子
        _dedupe(self.cookies)
        return super().prepare_request(request)
