"""Background polling thread: talks to Canvas and AMS, never blocks the UI."""

from __future__ import annotations

import logging
import threading
import time
import traceback
from datetime import datetime, timedelta
from pathlib import Path

from PySide6.QtCore import QThread, Signal

from . import paths, security, session as session_store
from .ams import AmsClient, AmsError
from .canvas import CanvasClient, CanvasError
from .models import Assignment, Snapshot
from .settings import Settings


class Worker(QThread):
    snapshot = Signal(object)      # Snapshot
    busy = Signal(bool)
    submitted = Signal(object)     # {"ok": bool, "message": str, "assignment": Assignment|None}
    detail_ready = Signal(object)  # AssignmentDetail
    downloaded = Signal(object)    # {"ok": bool, "message": str}
    auth_expired = Signal(str)     # "canvas" | "ams"
    log = Signal(str)

    def __init__(self, settings: Settings, parent=None):
        super().__init__(parent)
        self._settings = settings
        self._stop = False
        self._wake = threading.Event()
        self._lock = threading.Lock()
        self._job: tuple[Assignment, str] | None = None
        self._detail_job = None
        self._download_job = None

    # ---------------------------------------------------------------- public
    def reload(self, settings: Settings) -> None:
        with self._lock:
            self._settings = settings
        self.kick()

    def kick(self) -> None:
        self._wake.set()

    def request_submit(self, assignment: Assignment, paths) -> None:
        if isinstance(paths, (str, Path)):
            paths = [paths]
        with self._lock:
            self._job = (assignment, list(paths))
        self._wake.set()

    def request_detail(self, assignment: Assignment) -> None:
        with self._lock:
            self._detail_job = assignment
        self._wake.set()

    def request_download(self, attachment) -> None:
        with self._lock:
            self._download_job = attachment
        self._wake.set()

    def stop(self) -> None:
        self._stop = True
        self._wake.set()
        self.wait(5000)

    # ------------------------------------------------------------------ loop
    def run(self) -> None:  # noqa: C901 - simple state machine
        while not self._stop:
            with self._lock:
                job = self._job
                detail_job = self._detail_job
                download_job = self._download_job
                self._job = None
                self._detail_job = None
                self._download_job = None
                settings = self._settings
            if job is not None:
                try:
                    self._do_submit(*job, settings)
                except Exception:                 # 任何意外都不能把工作线程打死
                    traceback.print_exc()
                    self.submitted.emit({"ok": False,
                                         "message": "提交时出错，详情见日志",
                                         "assignment": job[0]})
                continue
            if detail_job is not None:
                self._do_detail(detail_job, settings)
                continue
            if download_job is not None:
                self._do_download(download_job, settings)
                continue

            self._wake.clear()
            self.busy.emit(True)
            _t0 = time.time()
            try:
                snap = self._collect(settings)
                logging.getLogger("wsdock.perf").info(
                    "数据刷新 %.0f ms", (time.time() - _t0) * 1000)
                self.snapshot.emit(snap)
            except Exception as exc:            # never let the thread die
                traceback.print_exc()
                self.log.emit(f"刷新异常：{exc}")
            finally:
                self.busy.emit(False)

            interval = max(1, int(settings.poll_minutes)) * 60
            self._wake.wait(timeout=interval)

    # --------------------------------------------------------------- helpers
    def _collect(self, settings: Settings) -> Snapshot:
        snap = Snapshot(updated_at=datetime.now())

        cookies = session_store.load_cookies()
        canvas_token = security.load_secret(paths.canvas_token_file())
        if cookies or canvas_token:
            try:
                client = CanvasClient(
                    settings.canvas_url,
                    token="" if cookies else canvas_token,
                    cookies=cookies or None,
                )
                snap.assignments = client.assignments()
                snap.canvas_ok = True
                snap.user_name = client.self_name()
                try:
                    snap.grades = client.grades()
                except CanvasError as exc:
                    self.log.emit(f"成绩: {exc}")
                try:
                    snap.notices.extend(client.announcements())
                except CanvasError as exc:
                    self.log.emit(f"公告: {exc}")
            except CanvasError as exc:
                snap.canvas_error = str(exc)
                if "登录已失效" in str(exc):
                    self.auth_expired.emit("canvas")
                self.log.emit(f"Canvas: {exc}")
            except Exception as exc:
                snap.canvas_error = f"意外错误：{exc}"
                self.log.emit(f"Canvas: {exc}")
        else:
            snap.canvas_error = "尚未设置 Canvas 访问令牌"

        ams_cookies = session_store.load_ams_cookies()
        if ams_cookies:
            week = None
            err = ""
            ams = None
            for attempt in (1, 2):          # 偶发失败重试一次，别整页清空
                try:
                    ams = AmsClient(settings.ams_url, cookies=ams_cookies)
                    week = ams.week()
                    break
                except AmsError as exc:
                    err = str(exc)
                    if "登录已失效" in err:
                        self.auth_expired.emit("ams")
                        break
                    if attempt == 1:
                        time.sleep(1.2)
                except Exception as exc:
                    err = f"意外错误：{exc}"
                    if attempt == 1:
                        time.sleep(1.2)

            if week is None and getattr(self, "_last_week", None):
                week = self._last_week       # 拉不到就沿用上一份，别让课表空掉
                self.log.emit(f"AMS: {err}（沿用上次课表）")
            if week is not None:
                self._last_week = week
                today = datetime.now().date()
                tomorrow = today + timedelta(days=1)
                snap.lessons_week = week
                snap.lessons = [l for l in week if l.start and l.start.date() == today]
                snap.lessons_tomorrow = [l for l in week if l.start and l.start.date() == tomorrow]
                snap.ams_ok = not err
                snap.ams_error = err
                if not err:
                    self.log.emit("AMS: 课表已更新")
                if ams is not None:
                    try:
                        snap.notices.extend(ams.notices())
                    except AmsError as exc:
                        self.log.emit(f"AMS 通知: {exc}")
                snap.notices.sort(
                    key=lambda n: n.posted_at or datetime.min, reverse=True
                )
        else:
            snap.ams_error = "尚未登录 AMS"

        return snap

    def _client(self, settings: Settings):
        cookies = session_store.load_cookies()
        token = security.load_secret(paths.canvas_token_file())
        if not cookies and not token:
            return None
        return CanvasClient(settings.canvas_url, token="" if cookies else token,
                            cookies=cookies or None)

    def _do_detail(self, assignment: Assignment, settings: Settings) -> None:
        from .models import AssignmentDetail
        client = self._client(settings)
        if client is None:
            self.detail_ready.emit(AssignmentDetail(assignment=assignment, error="尚未登录 Canvas"))
            return
        self.busy.emit(True)
        try:
            self.detail_ready.emit(client.assignment_detail(assignment))
        except Exception as exc:
            self.detail_ready.emit(AssignmentDetail(assignment=assignment, error=str(exc)))
        finally:
            self.busy.emit(False)

    def _do_download(self, attachment, settings: Settings) -> None:
        client = self._client(settings)
        if client is None:
            self.downloaded.emit({"ok": False, "message": "尚未登录 Canvas"})
            return
        self.busy.emit(True)
        try:
            target = Path.home() / "Downloads" / "VesperBoard"
            path = client.download(attachment, target)
            self.downloaded.emit({"ok": True, "message": f"已下载到 {path}"})
        except Exception as exc:
            self.downloaded.emit({"ok": False, "message": f"下载失败：{exc}"})
        finally:
            self.busy.emit(False)

    def _do_submit(self, assignment: Assignment, files: list, settings: Settings) -> None:
        # 注意：参数不能叫 paths —— 会遮住模块级的 paths，取配置文件时直接 AttributeError
        cookies = session_store.load_cookies()
        token = security.load_secret(paths.canvas_token_file())
        if not cookies and not token:
            self.submitted.emit({"ok": False, "message": "尚未登录 Canvas", "assignment": assignment})
            return
        self.busy.emit(True)
        try:
            client = CanvasClient(
                settings.canvas_url,
                token="" if cookies else token,
                cookies=cookies or None,
            )
            client.submit_files(assignment, [Path(p) for p in files])
            self.submitted.emit({
                "ok": True,
                "message": f"已提交：{assignment.title}（{len(files)} 个文件）" if len(files) > 1 else f"已提交：{assignment.title}",
                "assignment": assignment,
            })
        except CanvasError as exc:
            self.submitted.emit({"ok": False, "message": str(exc), "assignment": assignment})
        except Exception as exc:
            traceback.print_exc()
            self.submitted.emit({"ok": False, "message": f"提交失败：{exc}", "assignment": assignment})
        finally:
            self.busy.emit(False)
            self._wake.set()
