"""请求层测试：域名判定、绑定、去重、无凭据通道。"""

from __future__ import annotations

from requests.cookies import RequestsCookieJar

from wsdock.net import _dedupe, in_domain, origin, same_origin, set_cookies


def test_same_origin_is_strict():
    assert same_origin("https://canvas.example.edu/a", "https://canvas.example.edu/b")
    assert same_origin("https://canvas.example.edu/a", "https://canvas.example.edu:443/b")
    # 后缀匹配不算同源（evil-canvas.example.edu 之类）
    assert not same_origin("https://canvas.example.edu", "https://evil.canvas.example.edu")
    assert not same_origin("https://canvas.example.edu", "http://canvas.example.edu")
    assert not same_origin("https://canvas.example.edu", "https://canvas.example.edu:8443")
    assert not same_origin("https://canvas.example.edu", "https://example.edu")


def test_origin_rejects_malformed_port():
    assert origin("https://host:abc/x") == ("https", "", None)
    assert not same_origin("https://host:abc/x", "https://host/x")


def test_in_domain_is_suffix_not_substring():
    assert in_domain("canvas.westlake.edu.cn", "westlake.edu.cn")
    assert in_domain(".westlake.edu.cn", "westlake.edu.cn")
    assert in_domain("WESTLAKE.EDU.CN", "westlake.edu.cn")
    # 子串匹配会把这两个放进来
    assert not in_domain("westlake.edu.cn.evil.com", "westlake.edu.cn")
    assert not in_domain("notwestlake.edu.cn", "westlake.edu.cn")
    assert not in_domain("", "westlake.edu.cn")
    assert not in_domain("westlake.edu.cn", "")


def test_set_cookies_binds_domain():
    jar = RequestsCookieJar()
    set_cookies(jar, "https://canvas.example.edu/api/v1", {"_session": "abc"})
    cookies = list(jar)
    assert len(cookies) == 1
    assert cookies[0].domain == "canvas.example.edu"
    assert cookies[0].path == "/"


def test_dedupe_drops_cookies_without_domain():
    jar = RequestsCookieJar()
    jar.set("SESSION", "danger", path="/")                       # 无域名
    jar.set("ok", "1", domain="canvas.example.edu", path="/")
    _dedupe(jar)
    assert [c.name for c in jar] == ["ok"], "无域名 cookie 会发给任意主机，必须丢掉"


def test_dedupe_keeps_later_cookie_for_same_name_and_path():
    jar = RequestsCookieJar()
    jar.set("_csrf_token", "injected", domain="canvas.example.edu", path="/")
    jar.set("_csrf_token", "server", domain=".example.edu", path="/")
    _dedupe(jar)
    cookies = list(jar)
    assert len(cookies) == 1
    # 注入发生在构造时，Set-Cookie 在后；后写入的那份胜出
    assert cookies[0].value == "server"


def test_dedupe_leaves_distinct_names_alone():
    jar = RequestsCookieJar()
    jar.set("a", "1", domain="canvas.example.edu", path="/")
    jar.set("b", "2", domain="canvas.example.edu", path="/")
    _dedupe(jar)
    assert {c.name for c in jar} == {"a", "b"}
