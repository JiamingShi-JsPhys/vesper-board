"""Minimal Canvas LMS REST client (only the calls this app needs)."""

from __future__ import annotations

import mimetypes
import math
import re as _re
from html.parser import HTMLParser
import re
import time
from urllib.parse import unquote
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import requests

from .net import (
    GuardedSession, TransferSession, cookie_value, same_origin, set_cookies,
)
from .models import (
    Assignment, AssignmentDetail, Attachment, CourseGrade, GradeItem, Notice,
)

USER_AGENT = "VesperBoard/1.0 (+desktop widget)"


def _error_text(resp: requests.Response) -> str:
    """把 Canvas 的错误 JSON 翻成一句人能看懂的话。"""
    try:
        data = resp.json()
    except ValueError:
        return "HTTP %d %s" % (resp.status_code, resp.text[:120])
    if isinstance(data, dict):
        errors = data.get("errors")
        if isinstance(errors, list) and errors:
            first = errors[0]
            message = first.get("message") if isinstance(first, dict) else first
            if message:
                return str(message)
        if data.get("message"):
            return str(data["message"])
    return "HTTP %d" % resp.status_code

_FILE_LINK = _re.compile(r"/(?:courses/\d+/)?files/(\d+)")

_BAD_FILENAME = _re.compile(r'[\\/:*?"<>|\x00-\x1f]')
_RESERVED_NAMES = {"CON", "PRN", "AUX", "NUL"} | {
    "%s%d" % (prefix, i) for prefix in ("COM", "LPT") for i in range(1, 10)}


def _safe_filename(name: str, fallback: str) -> str:
    """把 Canvas 给的文件名变成 Windows 上能安全落盘的名字。

    Canvas 的文件名是服务端可控输入：除了路径分隔符，还要处理控制字符、
    结尾的点和空格、``CON``/``NUL`` 这类保留设备名，以及过长导致 OSError 的情况。
    """
    safe = _BAD_FILENAME.sub("_", str(name or "")).strip(" .")
    if not safe:
        return fallback
    stem, sep, ext = safe.rpartition(".")
    if not sep:
        stem, ext = safe, ""
    if stem.upper() in _RESERVED_NAMES:
        stem = "_" + stem
    stem = stem[:160] or "file"
    ext = ext[:20].rstrip(" .")
    return stem + ("." + ext if ext else "")


class _TextExtractor(HTMLParser):
    """Canvas gives the assignment body as HTML; the panel wants readable text."""

    _BREAK = {"br", "p", "div", "li", "tr", "h1", "h2", "h3", "h4", "h5", "h6"}

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self._skip = 0

    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style"):
            self._skip += 1
        elif tag == "img":
            self.parts.append("[图片] ")
        elif tag in self._BREAK:
            self.parts.append("\n")

    def handle_endtag(self, tag):
        if tag in ("script", "style") and self._skip:
            self._skip -= 1
        elif tag in self._BREAK:
            self.parts.append("\n")

    def handle_data(self, data):
        if not self._skip:
            self.parts.append(data)


def html_to_text(html: str) -> str:
    if not html:
        return ""
    parser = _TextExtractor()
    parser.feed(html)
    text = "".join(parser.parts)
    text = _re.sub(r"[ \t\u00a0]+", " ", text)
    text = _re.sub(r"\n[ \t]*(\n[ \t]*)+", "\n\n", text)
    return text.strip()


def extract_file_ids(html: str) -> list[int]:
    seen: list[int] = []
    for match in _FILE_LINK.finditer(html or ""):
        fid = int(match.group(1))
        if fid not in seen:
            seen.append(fid)
    return seen


class CanvasError(RuntimeError):
    pass


# course files change rarely; one copy per course is enough for a session
_COURSE_FILES_CACHE: dict[int, tuple[float, list]] = {}
# graded items change only when a teacher grades something
_GRADE_ITEMS_CACHE: dict[int, tuple[float, list]] = {}
_ANNOUNCE_CACHE: dict[str, tuple[float, list]] = {}


def _parse_time(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


class CanvasClient:
    def __init__(self, base_url: str, token: str = "", cookies: dict | None = None,
                 timeout: int = 20):
        self.base = base_url.rstrip("/")
        self.timeout = timeout
        self.session = GuardedSession()
        self.session.headers.update({
            "Accept": "application/json",
            "User-Agent": USER_AGENT,
        })
        self.session_auth = bool(cookies)
        self.csrf: str | None = None
        self._raw_cache: dict[int, list] = {}
        if token:
            self.session.headers["Authorization"] = f"Bearer {token}"
        if cookies:
            # 不能 jar.update()：那样造出的 cookie 没有域名，会被发给任意主机。
            set_cookies(self.session.cookies, self.base, cookies)

    def self_name(self) -> str:
        """Canvas 上当前登录用户的名字，用来做问候语。失败就返回空串。"""
        try:
            resp = self._request("GET", "/api/v1/users/self")
            data = resp.json() if resp.content else {}
        except Exception:
            return ""
        if not isinstance(data, dict):
            return ""
        name = str(data.get("short_name") or data.get("name") or "").strip()
        # 学校的名字形如「某某 |GIVEN FAMILY」，问候语只要竖线前面那段
        if "|" in name:
            name = name.split("|")[0].strip()
        return name[:24]

    # ---------------------------------------------------------------- helpers
    def _trusted(self, url: str) -> bool:
        """只有 Canvas 自己这个来源才配拿到令牌 / 会话 cookie。"""
        return same_origin(url, self.base)

    def _request(self, method: str, path: str, **kwargs) -> requests.Response:
        if self.session_auth and method.upper() != "GET":
            self._ensure_csrf()
            if self.csrf:
                headers = dict(kwargs.pop("headers", None) or {})
                headers.setdefault("X-CSRF-Token", self.csrf)
                kwargs["headers"] = headers

        url = path if path.startswith("http") else f"{self.base}{path}"
        if path.startswith("http") and not self._trusted(url):
            # 分页 Link、重定向目标都算输入；跨来源一律不带凭据。
            raise CanvasError("拒绝向 Canvas 之外的地址发送登录凭据")
        resp: requests.Response | None = None
        for attempt in range(3):
            try:
                resp = self.session.request(method, url, timeout=self.timeout, **kwargs)
            except requests.RequestException as exc:
                if attempt == 2:
                    raise CanvasError(f"网络不通：{exc}") from exc
                time.sleep(1.5 * (attempt + 1))
                continue

            if resp.status_code == 429:
                try:
                    wait = float(resp.headers.get("Retry-After", 3))
                except (TypeError, ValueError):
                    wait = 3.0    # Retry-After 也可能是 HTTP-date，或代理给的怪值
                if not math.isfinite(wait):
                    wait = 3.0
                time.sleep(max(0.0, min(wait, 30)))
                continue
            if resp.status_code in (500, 502, 503, 504) and attempt < 2:
                time.sleep(1.5 * (attempt + 1))
                continue
            return resp
        if resp is None:  # pragma: no cover
            raise CanvasError("请求失败")
        return resp

    def _ensure_csrf(self) -> None:
        """Session-cookie auth needs a CSRF token for POST/PUT/DELETE."""
        if self.csrf or not self.session_auth:
            return
        try:
            # 默认 Accept 是 application/json，首页会直接 406；
            # 想拿 <meta name="csrf-token"> 就得明确要 HTML。
            page = self.session.get(self.base + "/", timeout=self.timeout,
                                    headers={"Accept": "text/html,application/xhtml+xml"})
            m = re.search(r'name="csrf-token"[^>]*content="([^"]+)"', page.text)
            if m:
                self.csrf = m.group(1)
                return
        except requests.RequestException:
            pass
        # cookie 里存的是拼进 Set-Cookie 的百分号编码版本（%2F、%2B、%3D），
        # 原样放进 X-CSRF-Token 会让 Rails 校验失败并回一句通用的 422。
        raw = cookie_value(self.session.cookies, "_csrf_token")
        self.csrf = unquote(raw) if raw else ""

    def _get_json(self, path: str, params: dict | None = None) -> Any:
        resp = self._request("GET", path, params=params)
        if resp.status_code == 401:
            raise CanvasError("登录已失效，请在设置里重新登录 Canvas")
        if resp.status_code >= 400:
            raise CanvasError(f"Canvas 返回 {resp.status_code}：{resp.text[:160]}")
        return resp.json()

    def _paginate(self, path: str, params: dict | None = None, limit: int = 1000) -> list[dict]:
        params = dict(params or {})
        params.setdefault("per_page", 100)
        out: list[dict] = []
        url: str | None = f"{self.base}{path}"
        first = True
        while url and len(out) < limit:
            resp = self._request("GET", url, params=params if first else None)
            first = False
            if resp.status_code == 401:
                raise CanvasError("登录已失效，请在设置里重新登录 Canvas")
            if resp.status_code >= 400:
                raise CanvasError(f"Canvas 返回 {resp.status_code}：{resp.text[:160]}")
            chunk = resp.json()
            if isinstance(chunk, dict):
                chunk = [chunk]
            out.extend(chunk)
            url = self._next_link(resp.headers.get("Link", ""))
        return out[:limit]

    @staticmethod
    def _next_link(header: str) -> str | None:
        for part in header.split(","):
            if 'rel="next"' in part:
                m = re.search(r"<([^>]+)>", part)
                if m:
                    return m.group(1)
        return None

    # ------------------------------------------------------------------ calls
    def whoami(self) -> dict:
        return self._get_json("/api/v1/users/self")

    def courses(self) -> list[dict]:
        data = self._paginate(
            "/api/v1/courses",
            {"enrollment_state": "active", "include[]": ["term"], "state[]": ["available"]},
        )
        return [c for c in data if c.get("id")]

    def assignments(self, look_back_days: int = 60, look_ahead_days: int = 120) -> list[Assignment]:
        courses = self.courses()
        now = datetime.now(timezone.utc)
        earliest = now - timedelta(days=look_back_days)
        latest = now + timedelta(days=look_ahead_days)
        results: list[Assignment] = []

        def one(course: dict) -> list[Assignment]:
            cid = course["id"]
            name = course.get("name") or course.get("course_code") or f"课程 {cid}"
            try:
                raw = self._assignments_raw(cid)
            except CanvasError:
                return []
            items: list[Assignment] = []
            for a in raw:
                sub = a.get("submission") or {}
                state = (sub.get("workflow_state") or "").lower()
                submitted = bool(sub.get("submitted_at")) or state in {"submitted", "graded", "pending_review"}
                graded = state == "graded"
                due = _parse_time(a.get("due_at"))
                if due is not None and not (earliest <= due <= latest):
                    continue
                items.append(Assignment(
                    id=a["id"],
                    course_id=cid,
                    course_name=name,
                    title=a.get("name") or "(未命名作业)",
                    due_at=due,
                    html_url=a.get("html_url") or "",
                    submitted=submitted,
                    graded=graded,
                    submission_types=list(a.get("submission_types") or []),
                    points_possible=a.get("points_possible"),
                    quiz=bool(a.get("quiz_id")),
                    discussion=bool(a.get("discussion_topic")),
                    submitted_at=_parse_time(sub.get("submitted_at")),
                ))
            return items

        with ThreadPoolExecutor(max_workers=6) as pool:
            for batch in pool.map(one, courses):
                results.extend(batch)

        results.sort(key=lambda x: (x.due_at is None, x.due_at or now))
        return results

    # ----------------------------------------------------------------- grades
    def _assignments_raw(self, course_id: int) -> list:
        cached = self._raw_cache.get(course_id)
        if cached is not None:
            return cached
        data = self._paginate(
            "/api/v1/courses/%d/assignments" % course_id,
            {"include[]": ["submission"], "order_by": "due_at", "per_page": 100},
        )
        self._raw_cache[course_id] = data
        return data

    def _graded_items(self, course_id: int, ttl: float = 600) -> list:
        now = time.time()
        hit = _GRADE_ITEMS_CACHE.get(course_id)
        if hit and now - hit[0] < ttl:
            return hit[1]
        try:
            raw = self._assignments_raw(course_id)
        except CanvasError:
            return []
        items: list[GradeItem] = []
        for assignment in raw:
            submission = assignment.get("submission") or {}
            score = submission.get("score")
            if score is None:
                continue
            graded_at = _parse_time(submission.get("graded_at"))
            if graded_at is not None and graded_at.tzinfo:
                graded_at = graded_at.astimezone().replace(tzinfo=None)
            items.append(GradeItem(
                name=str(assignment.get("name") or "作业"),
                score=score,
                points=assignment.get("points_possible"),
                graded_at=graded_at,
            ))
        items.sort(key=lambda i: i.graded_at or datetime.min, reverse=True)
        _GRADE_ITEMS_CACHE[course_id] = (now, items)
        return items

    def grades(self) -> list["CourseGrade"]:
        """One row per course, even when Canvas lists several sections of it."""
        data = self._paginate(
            "/api/v1/courses",
            {"enrollment_state": "active", "include[]": ["total_scores"], "per_page": 100},
        )
        merged: dict[str, CourseGrade] = {}
        ids_by_key: dict[str, list[int]] = {}

        for course in data:
            cid = course.get("id")
            if not cid:
                continue
            name = str(course.get("name") or course.get("course_code") or cid)
            key = name.strip().lower()
            enrollment = (course.get("enrollments") or [{}])[0] or {}
            current = enrollment.get("computed_current_score")
            final = enrollment.get("computed_final_score")

            ids_by_key.setdefault(key, [])
            if int(cid) not in ids_by_key[key]:
                ids_by_key[key].append(int(cid))

            existing = merged.get(key)
            if existing is None:
                merged[key] = CourseGrade(course_id=int(cid), name=name,
                                          current=current, final=final)
            else:
                if existing.current is None or (
                        current is not None and current > existing.current):
                    existing.current = current
                if existing.final is None or (
                        final is not None and final > existing.final):
                    existing.final = final

        def one(key: str) -> tuple[str, list]:
            collected: list[GradeItem] = []
            for cid in ids_by_key.get(key, [])[:3]:
                collected.extend(self._graded_items(cid))
            collected.sort(key=lambda i: i.graded_at or datetime.min, reverse=True)
            return key, collected[:12]

        if merged:
            with ThreadPoolExecutor(max_workers=6) as pool:
                for key, items in pool.map(one, list(merged)):
                    merged[key].items = items

        return sorted(merged.values(), key=lambda g: g.name)

    def announcements(self, limit: int = 30, ttl: float = 300) -> list["Notice"]:
        cached = _ANNOUNCE_CACHE.get("all")
        if cached and time.time() - cached[0] < ttl:
            return cached[1][:limit]
        result = self._announcements_uncached(limit)
        _ANNOUNCE_CACHE["all"] = (time.time(), result)
        return result

    def _announcements_uncached(self, limit: int = 30) -> list["Notice"]:
        courses = self._paginate(
            "/api/v1/courses", {"enrollment_state": "active", "per_page": 100}
        )
        codes = ["course_%d" % c["id"] for c in courses if c.get("id")]
        if not codes:
            return []
        names = {"course_%d" % c["id"]: str(c.get("name") or "") for c in courses if c.get("id")}
        data = self._paginate(
            "/api/v1/announcements",
            {"context_codes[]": codes, "per_page": 50, "active_only": True},
        )
        out: list[Notice] = []
        for item in data[:limit]:
            if not item.get("id"):
                continue
            out.append(Notice(
                uid="canvas-%s" % item["id"],
                title=str(item.get("title") or "(无标题公告)"),
                posted_at=_parse_time(item.get("posted_at")),
                url=str(item.get("html_url") or ""),
                source="canvas",
                course=names.get(str(item.get("context_code") or ""), ""),
                body=html_to_text(item.get("message") or "")[:3000],
            ))
        out.sort(key=lambda n: n.posted_at or datetime.min.replace(tzinfo=None), reverse=True)
        return out

    # ----------------------------------------------------------------- detail
    def assignment_detail(self, assignment: Assignment, max_files: int = 8,
                          chars: int = 4000) -> AssignmentDetail:
        """Fetch the assignment body and whatever files it links to."""
        data = self._get_json(
            f"/api/v1/courses/{assignment.course_id}/assignments/{assignment.id}"
        )
        description_html = data.get("description") or ""
        detail = AssignmentDetail(
            assignment=assignment,
            description=html_to_text(description_html)[:chars],
        )
        detail.course_files = self.course_files(assignment.course_id)
        for fid in extract_file_ids(description_html)[:max_files]:
            attachment = self.file_info(fid)
            if attachment is not None:
                detail.attachments.append(attachment)
        return detail

    def course_files(self, course_id: int, limit: int = 12, ttl: float = 600) -> list[Attachment]:
        """Recent files of the course — where lab handouts and templates live."""
        now = time.time()
        hit = _COURSE_FILES_CACHE.get(course_id)
        if hit and now - hit[0] < ttl:
            return hit[1][:limit]
        try:
            data = self._paginate(
                "/api/v1/courses/%d/files" % course_id,
                {"per_page": 50, "sort": "created_at", "order": "desc"},
            )
        except CanvasError:
            return []
        files = [
            Attachment(
                id=int(item["id"]),
                name=str(item.get("display_name") or item.get("filename") or "文件"),
                size=int(item.get("size") or 0),
                content_type=str(item.get("content-type") or item.get("content_type") or ""),
                url=str(item.get("url") or ""),
            )
            for item in data
            if item.get("id")
        ]
        _COURSE_FILES_CACHE[course_id] = (now, files)
        return files[:limit]

    def file_info(self, file_id: int) -> Attachment | None:
        try:
            data = self._get_json(f"/api/v1/files/{file_id}")
        except CanvasError:
            return None
        if not isinstance(data, dict) or not data.get("id"):
            return None
        return Attachment(
            id=int(data["id"]),
            name=str(data.get("display_name") or data.get("filename") or f"文件 {file_id}"),
            size=int(data.get("size") or 0),
            content_type=str(data.get("content-type") or data.get("content_type") or ""),
            url=str(data.get("url") or ""),
        )

    def download(self, attachment: Attachment, target_dir: Path) -> Path:
        target_dir.mkdir(parents=True, exist_ok=True)
        safe = _safe_filename(attachment.name, f"file-{attachment.id}")
        target = target_dir / safe
        url = attachment.url or f"/api/v1/files/{attachment.id}/download"
        url = url if url.startswith("http") else f"{self.base}{url}"
        if not url.lower().startswith("https://"):
            # 签名在 query 里，走明文等于把附件白送给链路上的人
            raise CanvasError("附件地址不是 https，已拒绝")

        transfer = None
        if self._trusted(url):
            resp = self._request("GET", url, stream=True)
        else:
            # 文件可能放在对象存储上：那里靠 URL 里的签名，不需要也不该拿到登录态。
            transfer = TransferSession(USER_AGENT)
            resp = transfer.get(url, stream=True, timeout=self.timeout,
                                allow_redirects=True)
        try:
            if resp.status_code >= 400:
                raise CanvasError(f"下载失败：HTTP {resp.status_code}")
            with target.open("wb") as fh:
                for chunk in resp.iter_content(chunk_size=65536):
                    if chunk:
                        fh.write(chunk)
        finally:
            resp.close()
            if transfer is not None:
                transfer.close()
        return target

    # ----------------------------------------------------------------- submit
    def _upload_one(self, assignment: Assignment, path: Path) -> int:
        size = path.stat().st_size
        ctype = mimetypes.guess_type(path.name)[0] or "application/octet-stream"

        # 学生没有「课程文件」的写权限（/courses/:id/files 回 401），
        # 作业上传要走 submissions 专用的建上传接口。
        start = self._request(
            "POST",
            f"/api/v1/courses/{assignment.course_id}/assignments/{assignment.id}"
            f"/submissions/self/files",
            json={"name": path.name, "size": size, "content_type": ctype,
                  "submit_assignment": False},
        )
        if start.status_code >= 400:
            raise CanvasError("创建上传失败：%s" % _error_text(start))
        info = start.json()
        upload_url = info.get("upload_url")
        params = info.get("upload_params") or {}
        file_param = info.get("file_param") or "file"
        if not upload_url:
            raise CanvasError("Canvas 未返回上传地址")
        if not str(upload_url).lower().startswith("https://"):
            raise CanvasError("Canvas 返回的上传地址不是 https，已拒绝")

        # 上传地址可能在对象存储上。用干净的 Session：不带 Authorization，
        # 也不带 Canvas 的会话 cookie——Instructure 的文档同样要求第二步不要带令牌。
        transfer = TransferSession(USER_AGENT)
        try:
            with path.open("rb") as fh:
                up = transfer.post(
                    upload_url,
                    data=params,
                    files={file_param: (path.name, fh, ctype)},
                    timeout=300,
                    allow_redirects=False,
                )
        finally:
            transfer.close()

        file_id = None
        if up.status_code in (200, 201):
            try:
                file_id = up.json().get("id")
            except ValueError:
                file_id = None

        loc = up.headers.get("Location") or up.headers.get("location") or ""
        if file_id is None and loc:
            # 上传成功后 Canvas 会 302 到 .../files/:id/create_success。
            # 这一步必须带着登录 cookie 跟过去，附件才会被标记成可用；
            # 只从 URL 里抠出 id 而不访问它，提交时会报
            # "No valid file ids given"。
            url = loc if loc.startswith("http") else f"{self.base}{loc}"
            if not self._trusted(url):
                raise CanvasError(
                    "上传成功后 Canvas 返回了外部回调地址，已拒绝携带登录凭据访问")
            follow = self.session.get(url, timeout=120, allow_redirects=True)
            # 这个响应可能是 text/html 的 Content-Type 但正文其实是 JSON，
            # 所以不看头，直接试着解析。
            try:
                file_id = follow.json().get("id")
            except ValueError:
                file_id = None
            if file_id is None:
                m = re.search(r"/files/(\d+)", loc)
                if m:
                    file_id = int(m.group(1))

        if file_id is None:
            raise CanvasError(f"文件上传失败：HTTP {up.status_code}")
        return int(file_id)

    def submit_files(self, assignment: Assignment, paths) -> dict:
        """Upload every file, then hand them to Canvas in one submission."""
        files = [Path(p) for p in paths]
        if not files:
            raise CanvasError("没有选择文件")
        file_ids = [self._upload_one(assignment, path) for path in files]

        payload = [("submission[submission_type]", "online_upload")]
        for file_id in file_ids:
            payload.append(("submission[file_ids][]", str(file_id)))
        resp = self._request(
            "POST",
            f"/api/v1/courses/{assignment.course_id}/assignments/{assignment.id}/submissions",
            data=payload,
        )
        if resp.status_code >= 400:
            raise CanvasError(f"提交失败：{_error_text(resp)}")
        return resp.json()

    def submit_file(self, assignment: Assignment, path) -> dict:
        return self.submit_files(assignment, [path])
