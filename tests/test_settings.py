"""基础 URL 白名单：只认校内 https，且不携带 userinfo。"""

from __future__ import annotations

from wsdock.settings import DEFAULT_CANVAS, safe_base_url


def test_base_url_drops_userinfo():
    url = safe_base_url("https://user:pass@canvas.westlake.edu.cn/x", DEFAULT_CANVAS)
    assert url == "https://canvas.westlake.edu.cn"


def test_base_url_keeps_explicit_port():
    url = safe_base_url("https://canvas.westlake.edu.cn:8443/api", DEFAULT_CANVAS)
    assert url == "https://canvas.westlake.edu.cn:8443"


def test_base_url_rejects_lookalike_and_http():
    assert safe_base_url("https://canvas.westlake.edu.cn.evil.com", DEFAULT_CANVAS) == DEFAULT_CANVAS
    assert safe_base_url("http://canvas.westlake.edu.cn", DEFAULT_CANVAS) == DEFAULT_CANVAS
    assert safe_base_url("https://evil.example.com", DEFAULT_CANVAS) == DEFAULT_CANVAS
    assert safe_base_url("", DEFAULT_CANVAS) == DEFAULT_CANVAS
