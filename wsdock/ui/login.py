"""Embedded login window: the school's SSO page runs in a real browser engine.

The password never touches our code — the user types it into the school's own
page, and all we keep is the resulting session cookies (Canvas and AMS both
authenticate with an HttpOnly session cookie), encrypted with DPAPI.
"""

from __future__ import annotations

import logging
import time

import requests
from PySide6.QtCore import QTimer, QUrl, Signal, Qt
from PySide6.QtGui import QFont
from PySide6.QtNetwork import QNetworkCookie
from PySide6.QtWebEngineCore import QWebEnginePage, QWebEngineProfile
from PySide6.QtWebEngineWidgets import QWebEngineView
from PySide6.QtWidgets import (
    QDialog, QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget,
)

from .. import paths
from .. import session as session_store
from ..i18n import t
from ..browser_cookies import read_cookies
from ..net import GuardedSession, in_domain, set_cookies
from . import theme

log = logging.getLogger("wsdock.perf")

CANVAS_START = "https://canvas.westlake.edu.cn/"
AMS_START = "https://ams.westlake.edu.cn/home/"


def _log(message: str) -> None:
    """Diagnostics for the login flow — counts and hosts only, never values."""
    try:
        with paths.log_file().open("a", encoding="utf-8") as fh:
            fh.write("[login] " + message + "\n")
    except OSError:
        pass


def _as_text(value) -> str:
    if isinstance(value, str):
        return value
    try:
        return bytes(value).decode("utf-8", "ignore")
    except Exception:
        return str(value)


class LoginWindow(QDialog):
    """mode 'canvas' or 'ams' — both end with a cookie jar in `payload`."""

    succeeded = Signal(str, object)    # mode, {"cookies": {...}}
    cancelled = Signal(str)

    def __init__(self, mode: str, parent=None, seed: bool = True):
        _t0 = time.perf_counter()
        super().__init__(parent)
        self.mode = mode
        self._done = False
        self._last_url = ""
        self._last_verify = 0.0
        self._phase = mode
        self._ams_pass = False
        self._canvas_cookies: dict[str, str] = {}
        self._seen: set[tuple[str, str]] = set()
        self._last_seen: frozenset = frozenset()
        self._ams_cookies: dict[str, str] = {}
        self._all_cookies: dict[str, dict[str, str]] = {}

        self.setWindowTitle("登录 Canvas · Vesper Board" if mode == "canvas"
                            else "登录 AMS · Vesper Board")
        # 悬浮球和面板都是置顶窗口；登录窗如果只是普通对话框，会被压在它们下面，
        # 学校的输入框正好被挡住。让它自己也置顶，并在 showEvent 里提到最前。
        self.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint, True)
        self.resize(1020, 780)
        self.setStyleSheet("QDialog { background: __CARD__; }")

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        header = QWidget()
        header.setFixedHeight(54)
        header.setStyleSheet("background: __CARD__; border-bottom: 1px solid __INK14__;")
        head_row = QHBoxLayout(header)
        head_row.setContentsMargins(18, 0, 14, 0)
        title = QLabel("用学校统一身份认证登录"
                       + ("（Canvas）" if mode == "canvas" else "（AMS 课表）"))
        title.setFont(theme.font(10, QFont.Weight.DemiBold))
        title.setStyleSheet("color: __TEXT__;")
        head_row.addWidget(title, 1)
        close_btn = QPushButton("取消")
        close_btn.setFont(theme.font(8))
        close_btn.setFixedHeight(26)
        close_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        close_btn.setStyleSheet(
            "QPushButton { color: __TEXT__; background: __INK10__;"
            " border: 1px solid __INK24__; border-radius: 13px; padding: 0 14px; }"
            "QPushButton:hover { background: __INK18__; }"
        )
        close_btn.clicked.connect(self.reject)
        head_row.addWidget(close_btn)
        root.addWidget(header)

        if seed:
            self.profile = QWebEngineProfile("wsdock-login", self)
            self.profile.setPersistentStoragePath(str(paths.web_profile_dir()))
            self.profile.setCachePath(str(paths.web_cache_dir()))
            # 只放内存：Chromium 的 cookie 库是明文的，落盘等于把账号钥匙摊在磁盘上。
            # 登录时我们用 cookieAdded 实时抓下来，再经 DPAPI 存进 canvas/ams_session.bin。
            self.profile.setPersistentCookiesPolicy(
                QWebEngineProfile.PersistentCookiesPolicy.NoPersistentCookies
            )
        else:
            # 主动登录用一次性的内存 profile：天然没有旧 cookie，
            # 不再依赖「清完再等 600ms」这种有竞态的时序。
            self.profile = QWebEngineProfile(self)
        self._cookie_store = self.profile.cookieStore()
        self._cookie_store.cookieAdded.connect(self._on_cookie)
        if seed:
            self._seed_cookies()

        self.page = QWebEnginePage(self.profile, self)
        self.view = QWebEngineView(self)
        self.view.setPage(self.page)
        root.addWidget(self.view, 1)

        footer = QWidget()
        footer.setFixedHeight(40)
        footer.setStyleSheet("background: __CARD__; border-top: 1px solid __INK14__;")
        foot_row = QHBoxLayout(footer)
        foot_row.setContentsMargins(18, 0, 14, 0)
        self.status = QLabel("等待登录…密码不会离开这个窗口，程序只保存登录后的会话。")
        self.status.setFont(theme.font(7.5))
        self.status.setStyleSheet("color: __MUTED__;")
        foot_row.addWidget(self.status, 1)
        manual = QPushButton("我已完成登录")
        manual.setFont(theme.font(8))
        manual.setFixedHeight(24)
        manual.clicked.connect(self._check)
        manual.setStyleSheet(
            "QPushButton { color: white; background: __ACCENT__;"
            " border: none; border-radius: 12px; padding: 0 14px; }"
            "QPushButton:hover { background: #60A0FF; }"
        )
        foot_row.addWidget(manual)
        root.addWidget(footer)

        self.view.loadFinished.connect(self._on_loaded)
        self.view.urlChanged.connect(lambda _url: self._check())
        self._timer = QTimer(self)
        self._timer.setInterval(1200)
        self._timer.timeout.connect(self._check)
        self._timer.start()

        QTimer.singleShot(800, self._cookie_store.loadAllCookies)
        log.info("登录窗构建 %.0f ms", (time.perf_counter() - _t0) * 1000)
        self._t_open = time.perf_counter()
        # 关键：导航放进事件循环。否则 SSO 还在时会在构造函数里同步登录完成，
        # 此时调用方还没来得及 connect，成功的信号就丢了。
        start_url = CANVAS_START if mode == "canvas" else AMS_START
        # 清 cookie 是异步的，给它一点时间再导航
        QTimer.singleShot(0, lambda: self.view.setUrl(QUrl(start_url)))

    # ------------------------------------------------------------------ state
    def showEvent(self, event) -> None:
        super().showEvent(event)
        # 静默续期用的是 WA_DontShowOnScreen 的隐藏窗，不能抢焦点
        if self.testAttribute(Qt.WidgetAttribute.WA_DontShowOnScreen):
            return
        self.raise_()
        self.activateWindow()

    def _seed_cookies(self) -> None:
        """内存 profile 没有磁盘 cookie，静默续期会变成要求重新登录。

        这里把 DPAPI 里存着的会话注入进去：页面带着有效 cookie 打开，
        多数情况下直接就是已登录状态，用户不用再输密码。
        """
        maps = session_store.load_cookie_map()
        if not maps:                       # 老版本只有单域的两份
            maps = {
                "canvas.westlake.edu.cn": session_store.load_cookies(),
                "ams.westlake.edu.cn": session_store.load_ams_cookies(),
            }
        jars = list(maps.items())
        for host, jar in jars:
            # 只回放校内域：存过的 map 可能是被旧版本（或伪造页面）写坏的
            if not in_domain(str(host), "westlake.edu.cn"):
                continue
            for name, value in (jar or {}).items():
                if not name or not value:
                    continue
                cookie = QNetworkCookie(str(name).encode("utf-8"),
                                        str(value).encode("utf-8"))
                cookie.setDomain(host)
                cookie.setPath("/")
                cookie.setSecure(True)
                self._cookie_store.setCookie(cookie)

    def _on_cookie(self, cookie) -> None:
        domain = _as_text(cookie.domain()).lstrip(".").lower()
        name = _as_text(cookie.name())
        self._seen.add((domain, name))
        value = _as_text(cookie.value())
        if in_domain(domain, "canvas.westlake.edu.cn"):
            self._canvas_cookies[name] = value
        elif in_domain(domain, "ams.westlake.edu.cn"):
            self._ams_cookies[name] = value
        if in_domain(domain, "westlake.edu.cn"):
            self._all_cookies.setdefault(domain, {})[name] = value

    def _on_loaded(self, ok: bool) -> None:
        log.info("登录页加载完成 %.0f ms（ok=%s）",
                 (time.perf_counter() - getattr(self, "_t_open", time.perf_counter())) * 1000, ok)
        self._check()

    def _check(self) -> None:
        try:
            self._check_inner()
        except Exception as exc:  # never let a widget callback die silently
            _log(f"检查异常: {type(exc).__name__}: {exc}")

    def _check_inner(self) -> None:
        if self._done:
            return
        url = self.view.url()
        if url.toString() != self._last_url:
            self._last_url = url.toString()
            _log(f"{self.mode} 页面: {url.host()}{url.path()}")
        if self._phase == "canvas":
            self._check_canvas(url)
        else:
            self._check_ams(url)

    # ----------------------------------------------------------------- canvas
    def _check_canvas(self, url: QUrl) -> None:
        if not in_domain(url.host(), "canvas.westlake.edu.cn"):
            return
        if "login" in url.path():
            return
        self._cookie_store.loadAllCookies()
        found = {**read_cookies("canvas.westlake.edu.cn"), **self._canvas_cookies}
        if not any("session" in k.lower() for k in found):
            self.status.setText("还在等待 Canvas 登录完成…")
            return
        self._throttled(lambda: self._verify_canvas(found))

    def _verify_canvas(self, cookies: dict[str, str]) -> None:
        works = self._canvas_session_works(cookies)
        _log(f"canvas 验证: {len(cookies)} 个 cookie, 结果 {works}")
        if not works:
            self.status.setText("会话已拿到但尚未登录成功，请在这个窗口里完成登录…")
            return
        self._finish("canvas", {"cookies": cookies},
                     f"canvas 登录成功，保存 {len(cookies)} 个 cookie")

    @staticmethod
    def _canvas_session_works(cookies: dict[str, str]) -> bool:
        base = "https://canvas.westlake.edu.cn"
        # 用 GuardedSession + 绑定域名的 cookie：裸 requests.get(cookies=dict)
        # 造出的是无域名 cookie，跟随重定向时会被发到链上的任意主机。
        session = GuardedSession()
        session.headers.update({
            "Accept": "application/json",
            "User-Agent": "VesperBoard/1.0",
        })
        set_cookies(session.cookies, base, cookies)
        try:
            resp = session.get(base + "/api/v1/users/self", timeout=6,
                               allow_redirects=False)
            return resp.status_code == 200 and bool(resp.json().get("id"))
        except (requests.RequestException, ValueError):
            return False
        finally:
            session.close()

    # -------------------------------------------------------------------- ams
    def _check_ams(self, url: QUrl) -> None:
        if not in_domain(url.host(), "ams.westlake.edu.cn"):
            return
        if not url.path().startswith("/home"):
            return
        self._cookie_store.loadAllCookies()
        found = {**read_cookies("ams.westlake.edu.cn"), **self._ams_cookies}
        if not found.get("SESSION"):
            self.status.setText("还在等待 AMS 登录完成…")
            return
        self._throttled(lambda: self._verify_ams(found))

    def _verify_ams(self, cookies: dict[str, str]) -> None:
        name = self._ams_person_name(cookies)
        _log(f"ams 验证: {len(cookies)} 个 cookie, 身份已识别={bool(name)}")
        if not name:
            self.status.setText("已到 AMS，但会话还没生效，完成登录后会自动继续…")
            return
        self._finish("ams", {"cookies": cookies},
                     f"ams 登录成功，保存 {len(cookies)} 个 cookie")

    @staticmethod
    def _ams_person_name(cookies: dict[str, str]) -> str:
        base = "https://ams.westlake.edu.cn"
        session = GuardedSession()
        session.headers.update({
            "Accept": "application/json",
            "User-Agent": "VesperBoard/1.0",
        })
        set_cookies(session.cookies, base, cookies)
        try:
            resp = session.get(
                base + "/portal-service/api/v1/home/index",
                params={"identity": "STUDENT"}, timeout=6, allow_redirects=False,
            )
            data = resp.json()
            if isinstance(data, dict) and data.get("code") == 0:
                return str((data.get("data") or {}).get("personName") or "")
        except (requests.RequestException, ValueError):
            pass
        finally:
            session.close()
        return ""

    # ---------------------------------------------------------------- helpers
    def _throttled(self, action) -> None:
        if time.monotonic() - self._last_verify < 4:
            return
        self._last_verify = time.monotonic()
        action()

    def _finish(self, mode: str, payload: dict, message: str) -> None:
        _log(message)
        if self._all_cookies:
            session_store.save_cookie_map(self._all_cookies)
        self.succeeded.emit(mode, payload)

        # 同一个统一身份认证账号：Canvas 登进去之后顺手把 AMS 也带上
        if mode == "canvas" and not self._ams_pass and not session_store.has_ams_session():
            self._ams_pass = True
            self._phase = "ams"
            self._last_verify = 0.0
            self.status.setText(t("login.next_ams"))
            self._cookie_store.loadAllCookies()
            self.view.setUrl(QUrl(AMS_START))
            QTimer.singleShot(10000, self._finish_ams_pass)
            return

        self._done = True
        self._timer.stop()
        self.accept()

    def _finish_ams_pass(self) -> None:
        """Give the AMS hop 10 s; if it doesn't take, keep what we have."""
        if self._done:
            return
        _log("ams 复用登录超时，先只保存 Canvas")
        self._done = True
        self._timer.stop()
        self.accept()

    def reject(self) -> None:
        if not self._done:
            self.cancelled.emit(self.mode)
        super().reject()
