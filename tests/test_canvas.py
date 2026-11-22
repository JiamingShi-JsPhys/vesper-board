"""Offline tests for the Canvas client — no network, no real token."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
import requests

from wsdock.canvas import CanvasClient, CanvasError
from wsdock.models import Assignment


def resp(status=200, json_data=None, headers=None, text=""):
    return SimpleNamespace(
        status_code=status,
        headers=headers or {},
        json=lambda: json_data,
        text=text,
    )


def test_next_link_parses_rel_next():
    header = ('<https://canvas.westlake.edu.cn/api/v1/courses?page=2>; rel="next", '
              '<https://canvas.westlake.edu.cn/api/v1/courses?page=1>; rel="current"')
    assert CanvasClient._next_link(header).endswith("page=2")
    assert CanvasClient._next_link('') is None


def test_assignments_include_submitted_and_sort_by_due():
    client = CanvasClient("https://canvas.example.edu", "tok")
    now = datetime.now(timezone.utc)

    courses = [{"id": 1, "name": "微积分 II"}, {"id": 2, "name": "线性代数"}]
    per_course = {
        1: [
            {"id": 11, "name": "已交的", "due_at": (now + timedelta(days=1)).isoformat(),
             "submission_types": ["online_upload"],
             "submission": {"workflow_state": "submitted", "submitted_at": now.isoformat()}},
            {"id": 12, "name": "要交的", "due_at": (now + timedelta(hours=5)).isoformat(),
             "submission_types": ["online_upload"], "submission": {"workflow_state": "unsubmitted"}},
            {"id": 13, "name": "太远的", "due_at": (now + timedelta(days=400)).isoformat(),
             "submission_types": ["online_upload"], "submission": {"workflow_state": "unsubmitted"}},
        ],
        2: [
            {"id": 21, "name": "没截止的", "due_at": None,
             "submission_types": ["online_text_entry"], "submission": {"workflow_state": "unsubmitted"}},
            {"id": 22, "name": "过期的", "due_at": (now - timedelta(days=2)).isoformat(),
             "submission_types": ["online_upload"], "submission": {"workflow_state": "unsubmitted"}},
        ],
    }

    with patch.object(CanvasClient, "courses", return_value=courses), \
         patch.object(CanvasClient, "_paginate", side_effect=lambda path, params=None: per_course[int(path.split("/")[4])]):
        items = client.assignments()

    titles = [a.title for a in items]
    assert titles == ["过期的", "要交的", "已交的", "没截止的"]
    submitted = [a for a in items if a.title == "已交的"][0]
    assert submitted.is_submitted is True
    assert submitted.submitted_at is not None
    assert all(isinstance(a, Assignment) for a in items)
    assert items[1].days_left is not None and 0.1 < items[1].days_left < 0.3


def test_submit_file_runs_three_step_flow(tmp_path):
    client = CanvasClient("https://canvas.example.edu", "tok")
    work = tmp_path / "作业.pdf"
    work.write_bytes(b"%PDF-1.4 fake")

    assignment = Assignment(
        id=99, course_id=7, course_name="物理", title="实验报告",
        due_at=None, html_url="", submitted=False, graded=False,
        submission_types=["online_upload"],
    )

    calls: list[tuple[str, str]] = []

    def fake_request(method, path, **kwargs):
        calls.append((method, path))
        if path.endswith("/files"):
            return resp(200, {"upload_url": "https://upload.example/abc",
                              "upload_params": {"key": "x", "policy": "y"}})
        if path.endswith("/submissions"):
            return resp(201, {"id": 4242, "workflow_state": "submitted"})
        raise AssertionError(f"unexpected {path}")

    uploaded = resp(200, {"id": 555})

    with patch.object(CanvasClient, "_request", side_effect=fake_request), \
         patch("requests.Session.post", return_value=uploaded) as post:
        result = client.submit_file(assignment, work)

    assert result["id"] == 4242
    # 学生没有课程文件写权限，建上传必须走作业提交专用接口
    assert calls[0][1].endswith("/api/v1/courses/7/assignments/99/submissions/self/files")
    assert calls[1][1].endswith("/api/v1/courses/7/assignments/99/submissions")
    assert post.call_args.args[0] == "https://upload.example/abc"


def test_submit_reports_canvas_error(tmp_path):
    client = CanvasClient("https://canvas.example.edu", "tok")
    work = tmp_path / "a.txt"
    work.write_text("x")
    assignment = Assignment(1, 1, "c", "t", None, "", False, False, ["online_upload"])

    with patch.object(CanvasClient, "_request", return_value=resp(422, {}, text="no link")):
        with pytest.raises(CanvasError):
            client.submit_file(assignment, work)


def test_401_becomes_readable_error():
    client = CanvasClient("https://canvas.example.edu", "bad")
    with patch.object(CanvasClient, "_request", return_value=resp(401, {"errors": []})):
        with pytest.raises(CanvasError, match="登录已失效"):
            client._get_json("/api/v1/courses")


def test_session_auth_adds_csrf_only_for_writes():
    client = CanvasClient("https://canvas.example.edu", cookies={"_canvas_session": "abc"})
    client.csrf = "csrf-123"
    captured = {}

    def fake_request(method, url, **kwargs):
        captured[method] = kwargs.get("headers", {})
        return SimpleNamespace(status_code=200, headers={}, json=lambda: [], text="")

    with patch.object(client.session, "request", side_effect=fake_request):
        client._request("GET", "/api/v1/courses")
        client._request("POST", "/api/v1/courses/1/files", json={"name": "a"})

    assert "X-CSRF-Token" not in captured["GET"]
    assert captured["POST"].get("X-CSRF-Token") == "csrf-123"


def test_csrf_is_read_from_cookie_when_meta_missing():
    client = CanvasClient("https://canvas.example.edu", cookies={"_canvas_session": "abc"})
    client.session.cookies.set("_csrf_token", "from-cookie",
                              domain="canvas.example.edu", path="/")
    with patch.object(client.session, "get", side_effect=requests.ConnectionError("offline")):
        client._ensure_csrf()
    assert client.csrf == "from-cookie"


def test_html_to_text_strips_markup():
    from wsdock.canvas import html_to_text
    html = "<p>交一份 <b>PDF</b>。</p><ul><li>页数 ≤ 5</li></ul><img src='x'>"
    text = html_to_text(html)
    assert "PDF" in text and "页数" in text and "≤ 5" in text
    assert "<" not in text


def test_extract_file_ids_dedupes_and_ignores_other_links():
    from wsdock.canvas import extract_file_ids
    html = ('<a href="/courses/1/files/42/download">a</a>'
            '<a href="/courses/1/files/42">b</a>'
            '<a href="/files/7">c</a><a href="/courses/1/modules">d</a>')
    assert extract_file_ids(html) == [42, 7]


def test_assignment_detail_resolves_attachments():
    client = CanvasClient("https://canvas.example.edu", "tok")
    assignment = Assignment(99, 7, "物理", "实验报告", None, "", False, False, ["online_upload"])

    def fake_get_json(path, params=None):
        if path.endswith("/assignments/99"):
            return {"description": '<p>交一份报告</p><a href="/courses/7/files/5">模板</a>'}
        if path == "/api/v1/files/5":
            return {"id": 5, "display_name": "template.pdf", "size": 2048,
                    "content-type": "application/pdf", "url": "https://files.example/5"}
        raise AssertionError("unexpected " + path)

    with patch.object(CanvasClient, "_get_json", side_effect=fake_get_json):
        detail = client.assignment_detail(assignment)

    assert "交一份报告" in detail.description
    assert len(detail.attachments) == 1
    assert detail.attachments[0].name == "template.pdf"
    assert detail.attachments[0].size_text == "2 KB"


def test_missing_file_is_skipped_not_fatal():
    client = CanvasClient("https://canvas.example.edu", "tok")
    assignment = Assignment(99, 7, "物理", "实验报告", None, "", False, False, ["online_upload"])

    def fake_get_json(path, params=None):
        if path.endswith("/assignments/99"):
            return {"description": '<a href="/courses/7/files/5">x</a>'}
        return {}

    with patch.object(CanvasClient, "_get_json", side_effect=fake_get_json):
        detail = client.assignment_detail(assignment)
    assert detail.attachments == []


# --------------------------------------------------------- 凭据不外发
#
# 这一组测试存在的理由：Canvas 的上传/下载地址可能指向对象存储的另一个域名，
# 那里只需要 URL 里的签名。带着 Bearer token 或会话 cookie 过去就是泄露。

def test_injected_cookies_are_bound_to_canvas_host():
    client = CanvasClient("https://canvas.westlake.edu.cn",
                          cookies={"_canvas_session": "abc", "_csrf_token": "def"})
    jar = list(client.session.cookies)
    assert jar, "cookie 应该被注入"
    # 空 domain 的 cookie 会被 http.cookiejar 发给任意主机
    assert all(cookie.domain == "canvas.westlake.edu.cn" for cookie in jar)


def test_request_refuses_cross_origin_absolute_url():
    client = CanvasClient("https://canvas.example.edu", "tok")
    with pytest.raises(CanvasError, match="Canvas 之外"):
        client._request("GET", "https://evil.example.net/api/v1/courses")


def test_upload_uses_credential_free_session(tmp_path):
    client = CanvasClient("https://canvas.example.edu", "TOPSECRET",
                          cookies={"_canvas_session": "SESS"})
    work = tmp_path / "报告.pdf"
    work.write_bytes(b"%PDF-1.4")
    assignment = Assignment(99, 7, "物理", "实验报告", None, "", False, False,
                            ["online_upload"])

    def fake_request(method, path, **kwargs):
        if path.endswith("/files"):
            return resp(200, {"upload_url": "https://bucket.example.net/abc",
                              "upload_params": {"key": "x"}})
        if path.endswith("/submissions"):
            return resp(201, {"id": 1})
        raise AssertionError(path)

    seen = {}

    def fake_post(session_self, url, **kwargs):
        seen["authorization"] = session_self.headers.get("Authorization")
        seen["cookies"] = list(session_self.cookies)
        return resp(200, {"id": 555})

    with patch.object(CanvasClient, "_request", side_effect=fake_request), \
         patch("wsdock.canvas.TransferSession.post", fake_post):
        client.submit_file(assignment, work)

    assert seen["authorization"] is None, "上传不应带 Bearer token"
    assert seen["cookies"] == [], "上传不应带 Canvas 会话 cookie"


def test_upload_rejects_external_location_callback(tmp_path):
    client = CanvasClient("https://canvas.example.edu", "tok")
    work = tmp_path / "a.txt"
    work.write_text("x")
    assignment = Assignment(1, 1, "c", "t", None, "", False, False, ["online_upload"])

    class Up:
        status_code = 302
        headers = {"Location": "https://evil.example.net/steal"}

        def json(self):
            raise ValueError

    def fake_request(method, path, **kwargs):
        return resp(200, {"upload_url": "https://bucket.example.net/abc",
                          "upload_params": {"key": "x"}})

    with patch.object(CanvasClient, "_request", side_effect=fake_request), \
         patch("wsdock.canvas.TransferSession.post", lambda *a, **k: Up()):
        with pytest.raises(CanvasError, match="外部回调地址"):
            client.submit_file(assignment, work)


def test_external_download_uses_credential_free_session(tmp_path):
    from wsdock.models import Attachment

    client = CanvasClient("https://canvas.example.edu", "TOPSECRET",
                          cookies={"_canvas_session": "SESS"})
    attachment = Attachment(id=3, name="讲义.pdf", size=5,
                            content_type="application/pdf",
                            url="https://files.example.net/讲义.pdf")
    seen = {}

    class FakeResp:
        status_code = 200

        def iter_content(self, chunk_size=65536):
            yield b"hello"

        def close(self):
            pass

    def fake_get(session_self, url, **kwargs):
        seen["authorization"] = session_self.headers.get("Authorization")
        seen["cookies"] = list(session_self.cookies)
        return FakeResp()

    with patch("wsdock.canvas.TransferSession.get", fake_get):
        target = client.download(attachment, tmp_path)

    assert target.read_bytes() == b"hello"
    assert seen["authorization"] is None
    assert seen["cookies"] == []


def test_safe_filename_handles_windows_quirks():
    from wsdock.canvas import _safe_filename

    assert _safe_filename("../../etc/passwd", "f") == "_.._etc_passwd"
    assert "/" not in _safe_filename(r"a/b\c.txt", "f")
    assert _safe_filename("CON.pdf", "f") == "_CON.pdf"
    assert _safe_filename("nul", "f") == "_nul"
    assert _safe_filename("a\x00b.txt", "f") == "a_b.txt"
    assert _safe_filename("..", "fallback") == "fallback"
    long_name = _safe_filename("x" * 400 + ".pdf", "f")
    assert len(long_name) <= 165 and long_name.endswith(".pdf")
