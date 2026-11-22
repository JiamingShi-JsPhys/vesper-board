"""Westlake Dock — a floating ball for Canvas homework and AMS timetable."""

from __future__ import annotations

import logging
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path

from PySide6.QtCore import (QEvent, QLockFile, QPoint, QRect, QRectF, QSize, Qt,
                            QTimer, Signal)
from PySide6.QtGui import (
    QAction, QColor, QFont, QIcon, QLinearGradient, QPainter, QPainterPath, QPen, QPixmap,
)
from PySide6.QtWidgets import (
    QApplication, QMenu, QSystemTrayIcon, QWidget,
)

from wsdock import archive, paths, reminders, security
from wsdock import i18n
from wsdock.i18n import set_language, t
from wsdock import autostart as autostart_mod
from wsdock import session as session_store
from wsdock.models import Assignment, Snapshot
from wsdock.schedule import badge_left, human_left, in_quiet_hours
from wsdock.settings import Settings
from wsdock.ui import theme
from wsdock.ui.ball import Ball
from wsdock.ui.panel import Panel
from wsdock.worker import Worker

log = logging.getLogger("wsdock")


# --------------------------------------------------------------------- toast
class Toast(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowFlags(
            Qt.WindowType.Tool
            | Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.WindowTransparentForInput
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, True)
        self._text = ""
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(self.hide)
        self.setFont(theme.font(8.5))

    def show_text(self, text: str, near: QRect, msec: int = 2600) -> None:
        self._text = text
        from PySide6.QtGui import QFontMetrics
        width = QFontMetrics(self.font()).horizontalAdvance(text) + 28
        self.setFixedSize(max(140, width), 38)
        x = near.center().x() - self.width() // 2
        y = near.top() - self.height() - 10
        screen = self.screen().availableGeometry() if self.screen() else None
        if screen:
            x = max(screen.left() + 8, min(x, screen.right() - self.width() - 8))
            if y < screen.top():
                y = near.bottom() + 10
        self.move(x, y)
        self.show()
        self.raise_()
        self._timer.start(msec)

    def paintEvent(self, event):  # noqa: N802
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setBrush(theme.BG_CARD)
        painter.setPen(QPen(theme.BORDER, 1))
        painter.drawRoundedRect(self.rect().adjusted(0, 0, -1, -1), 12, 12)
        painter.setPen(QPen(theme.TEXT))
        painter.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, self._text)


class HoverTip(QWidget):
    """The strip that slides out of the ball on hover (beacon-style)."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowFlags(
            Qt.WindowType.Tool
            | Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.WindowTransparentForInput
            | Qt.WindowType.NoDropShadowWindowHint
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, True)
        self.setFont(theme.font(8.5))
        self._text = ""
        self._tail_right = True

    def show_text(self, text: str, anchor) -> None:
        if not text:
            self.hide()
            return
        self._text = text
        from PySide6.QtGui import QFontMetrics
        width = QFontMetrics(self.font()).horizontalAdvance(text) + 30
        self.setFixedSize(max(150, width), 36)
        screen = self.screen().availableGeometry() if self.screen() else None
        x = anchor.left() - self.width() - 8
        self._tail_right = True
        if screen and x < screen.left() + 6:
            x = anchor.right() + 8                 # ball is on the left edge
            self._tail_right = False
        y = anchor.center().y() - self.height() // 2
        if screen:
            x = max(screen.left() + 6, min(x, screen.right() - self.width() - 6))
            y = max(screen.top() + 6, min(y, screen.bottom() - self.height() - 6))
        self.move(x, y)
        self.show()
        self.raise_()

    def paintEvent(self, event):  # noqa: N802
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        tail = 9
        body = self.rect().adjusted(0, 0, -1, -1)
        if self._tail_right:
            body.setRight(body.right() - tail)
        else:
            body.setLeft(body.left() + tail)

        path = QPainterPath()
        path.addRoundedRect(QRectF(body), 12, 12)
        tip = QPainterPath()
        mid = body.center().y()
        if self._tail_right:
            tip.moveTo(body.right(), mid - 6)
            tip.lineTo(body.right() + tail, mid)
            tip.lineTo(body.right(), mid + 6)
        else:
            tip.moveTo(body.left(), mid - 6)
            tip.lineTo(body.left() - tail, mid)
            tip.lineTo(body.left(), mid + 6)
        tip.closeSubpath()
        path = path.united(tip)

        painter.setPen(QPen(theme.BORDER, 1))
        painter.setBrush(theme.BG_CARD)
        painter.drawPath(path)
        painter.setPen(QPen(theme.TEXT))
        painter.drawText(body, Qt.AlignmentFlag.AlignCenter, self._text)



class SpeechBubble(QWidget):
    """人物旁边的小对话气泡：刷新时说「让我看看…」，更新完说结果。

    自动消失（默认 4.5 秒），点一下也会收起；不抢焦点、不挡鼠标。
    """

    TAIL = 9
    HEIGHT = 34

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowFlags(
            Qt.WindowType.Tool
            | Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.NoDropShadowWindowHint
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, True)
        self.setFont(theme.font(8.5))
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self._tail = "bottom"
        self._text = ""
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(self.hide)
        self.setFixedSize(160, self.HEIGHT)

    def say(self, text: str, anchor, seconds: float = 4.5) -> None:  # noqa: C901
        text = (text or "").strip()
        if not text:
            return
        self._text = text
        from PySide6.QtGui import QFontMetrics
        width = QFontMetrics(self.font()).horizontalAdvance(text) + 28
        width = max(84, min(240, width))
        self.setFixedSize(width + 2, self.HEIGHT + self.TAIL)

        screen = self.screen().availableGeometry() if self.screen() else None
        x = anchor.center().x() - self.width() // 2
        y = anchor.top() - self.height() - 4
        self._tail = "bottom"
        if screen and y < screen.top() + 4:
            y = anchor.bottom() + 4
            self._tail = "top"
        if screen:
            x = max(screen.left() + 4, min(x, screen.right() - self.width() - 4))
            y = max(screen.top() + 4, min(y, screen.bottom() - self.height() - 4))
        self.move(x, y)
        self.update()
        self.show()
        self.raise_()
        self._timer.start(int(seconds * 1000))

    def mousePressEvent(self, event):  # noqa: N802
        if event.button() == Qt.MouseButton.LeftButton:
            self.hide()

    def paintEvent(self, event):  # noqa: N802
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        tail = self.TAIL
        body = self.rect().adjusted(0, 0, -1, -1)
        if self._tail == "bottom":
            body.setBottom(body.bottom() - tail)
        else:
            body.setTop(body.top() + tail)

        path = QPainterPath()
        path.addRoundedRect(QRectF(body), 12, 12)
        tip = QPainterPath()
        mid = body.center().x()
        if self._tail == "bottom":
            tip.moveTo(mid - 6, body.bottom())
            tip.lineTo(mid, body.bottom() + tail)
            tip.lineTo(mid + 6, body.bottom())
        else:
            tip.moveTo(mid - 6, body.top())
            tip.lineTo(mid, body.top() - tail)
            tip.lineTo(mid + 6, body.top())
        tip.closeSubpath()
        path = path.united(tip)

        painter.setPen(QPen(theme.BORDER, 1))
        painter.setBrush(theme.BG_CARD)
        painter.drawPath(path)
        painter.setPen(QPen(theme.TEXT))
        painter.drawText(body.adjusted(10, 0, -10, 0),
                         Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignHCenter,
                         self._text)


# --------------------------------------------------------------------- icons
def make_icon(size: int = 64) -> QIcon:
    # 有官方图标就用它（assets/app_icon.png），没有就退回代码画的圆球
    icon_path = paths.bundle_dir() / "assets" / "app_icon.png"
    if icon_path.exists():
        source = QPixmap(str(icon_path))
        if not source.isNull():
            icon = QIcon()
            for side in (16, 24, 32, 48, 64, 128, 256):
                icon.addPixmap(source.scaled(side, side,
                                             Qt.AspectRatioMode.KeepAspectRatio,
                                             Qt.TransformationMode.SmoothTransformation))
            return icon
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    pad = size * 0.06
    rect = pixmap.rect().toRectF().adjusted(pad, pad, -pad, -pad)
    gradient = QLinearGradient(0, rect.top(), 0, rect.bottom())
    gradient.setColorAt(0, QColor(86, 158, 255))
    gradient.setColorAt(1, QColor(44, 96, 214))
    painter.setBrush(gradient)
    painter.setPen(Qt.PenStyle.NoPen)
    painter.drawEllipse(rect)
    font = QFont("Microsoft YaHei UI")
    font.setPixelSize(int(size * 0.42))
    font.setWeight(QFont.Weight.DemiBold)
    painter.setFont(font)
    painter.setPen(QPen(QColor(255, 255, 255, 245)))
    painter.drawText(pixmap.rect(), Qt.AlignmentFlag.AlignCenter, "V")
    painter.end()
    return QIcon(pixmap)


# ----------------------------------------------------------------------- app
class Dock(QWidget):
    def __init__(self, settings: Settings):
        super().__init__()
        self.setWindowFlags(Qt.WindowType.Tool)
        self.setAttribute(Qt.WidgetAttribute.WA_DontShowOnScreen, True)
        self.settings = settings

        self.ball = Ball()
        self.ball.set_skin(getattr(settings, "pet_skin", ""))
        self.ball.set_pet_size(int(getattr(settings, "pet_size", 92) or 92))
        self.ball.set_glow(bool(getattr(settings, "pet_glow", False)))
        self.ball.set_badge(bool(getattr(settings, "show_badge", False)))
        self.panel = Panel(settings)
        self.panel.set_user_name(getattr(settings, "user_name", "") or "")
        self.toast = Toast()
        self.tip = HoverTip()
        self.bubble = SpeechBubble()
        self.panel.installEventFilter(self)
        self._speech_key = ""
        self._speech_at = 0.0
        self._first_snap = True
        self.worker = Worker(settings)
        self._seen_ids: set[int] | None = None
        self._notified: set[int] = set()
        self._class_seen: set[tuple] = set()
        self._focus: dict | None = None
        self._busy = False
        self._ball_offset = None
        self._syncing = False      # 防止「人物跟面板」「面板跟人物」互相触发
        self._reminder_timer = QTimer(self)
        self._reminder_timer.setInterval(30_000)
        self._reminder_timer.timeout.connect(self._check_scheduled_reminders)
        self._in_class = False
        self._relogin_window = None
        self._last_relogin = 0.0
        self._focus_timer = QTimer(self)
        self._focus_timer.setInterval(1000)
        self._focus_timer.timeout.connect(self._tick_focus)

        self._wire()
        self._reminder_timer.start()
        self._place_ball()
        self._build_tray()

    # ------------------------------------------------------------------ setup
    def _wire(self) -> None:
        self.ball.clicked.connect(self._toggle_panel)
        self.ball.moved.connect(self._follow_pet)
        self.ball.moved.connect(self._place_bubble)
        self.ball.context_requested.connect(self._show_menu)
        self.ball.hover_in.connect(self._show_hover)
        self.ball.hover_out.connect(self._hide_hover)

        self.worker.snapshot.connect(self._on_snapshot)
        self.worker.busy.connect(self._on_busy)
        self.worker.submitted.connect(self._on_submitted)
        self.worker.downloaded.connect(self._on_downloaded)
        self.worker.log.connect(self._append_log)
        self.worker.auth_expired.connect(self._on_auth_expired)
        self._wire_panel()

    def _wire_panel(self) -> None:
        p = self.panel
        p.submit_requested.connect(self._on_submit)
        p.refresh_requested.connect(self.worker.kick)
        p.settings_requested.connect(self._open_settings)
        p.open_url.connect(self._open_url)
        p.detail_requested.connect(self.worker.request_detail)
        p.download_requested.connect(self.worker.request_download)
        p.submit_confirmed.connect(self._on_submit_confirmed)
        p.archive_changed.connect(self.worker.kick)
        p.export_requested.connect(self._export_ics)
        p.focus_requested.connect(self._start_focus)
        p.remind_requested.connect(self._remind)
        p.login_requested.connect(self._on_login_requested)
        p.settings_changed.connect(self._on_settings_changed)
        p.moved.connect(self._follow_ball)
        p.scheduled_remind.connect(self._on_scheduled_remind)
        p.scheduled_remind_at.connect(self._on_scheduled_remind_at)
        p.close_requested.connect(self._close_panel)
        p.login_done.connect(lambda _mode: self.worker.kick())
        self.worker.busy.connect(p.set_busy)
        self.worker.detail_ready.connect(p.show_detail)
        snap = getattr(self, "_snapshot", None)
        if snap is not None:
            p.apply_snapshot(snap)

    def _rebuild_panel(self) -> None:
        """换主题后整块重建：颜色是建控件时写死的，只能重来一遍。"""
        was_open = self.panel.isVisible()
        self.panel.hide()
        self.panel.deleteLater()
        self.panel = Panel(self.settings)
        self._wire_panel()
        self._set_native_level(self.panel, "top" if (self.settings.window_level or "top") == "top" else "normal")
        if was_open:
            self.panel.popup(self.ball.frameGeometry())

    def _place_ball(self) -> None:
        screen = QApplication.primaryScreen().availableGeometry()
        if self.settings.ball_x is not None and self.settings.ball_y is not None:
            x, y = self.settings.ball_x, self.settings.ball_y
        else:
            x = screen.right() - self.ball.width() - 24
            y = screen.center().y() - self.ball.height() // 2
        x = max(screen.left(), min(x, screen.right() - self.ball.width()))
        y = max(screen.top(), min(y, screen.bottom() - self.ball.height()))
        self.ball.move(x, y)

    def _build_tray(self) -> None:
        self.tray = QSystemTrayIcon(make_icon(), self)
        self.tray.setToolTip("晚星看板 · Vesper Board")
        menu = QMenu()
        act_open = QAction("打开面板", self)
        act_open.triggered.connect(self._toggle_panel)
        act_refresh = QAction("立即刷新", self)
        act_refresh.triggered.connect(self.worker.kick)
        act_settings = QAction("设置…", self)
        act_settings.triggered.connect(self._open_settings)
        act_quit = QAction("退出", self)
        act_quit.triggered.connect(self.shutdown)
        menu.addAction(act_open)
        menu.addAction(act_refresh)
        menu.addSeparator()
        menu.addAction(act_settings)
        menu.addSeparator()
        self.level_actions = {}
        for key, label in (("top", "置顶显示"),
                           ("normal", "普通窗口层"),
                           ("desktop", "贴桌面（不挡窗口）")):
            act = QAction(label, self)
            act.setCheckable(True)
            act.triggered.connect(lambda _checked=False, k=key: self._apply_level(k))
            menu.addAction(act)
            self.level_actions[key] = act
        menu.addSeparator()
        menu.addAction(act_quit)
        menu.aboutToShow.connect(self._sync_level_actions)
        self._tray_menu = menu
        self.tray.setContextMenu(menu)
        self.tray.activated.connect(
            lambda reason: self._toggle_panel() if reason == QSystemTrayIcon.ActivationReason.Trigger else None
        )
        self.tray.show()

    def start(self) -> None:
        self.ball.show()
        self.ball.set_skin(getattr(self.settings, "pet_skin", ""))
        self.ball.set_pet_size(int(getattr(self.settings, "pet_size", 92) or 92))
        self._apply_level(self.settings.window_level or "top", persist=False)
        force_setup = "--setup" in sys.argv
        if force_setup or not session_store.has_any_canvas_auth():
            self._open_settings(first_run=True)
            if not self.settings.first_run_done:
                # 第一次用：直接把登录窗叫出来，之后靠保存的会话启动
                self.settings.first_run_done = True
                try:
                    self.settings.save()
                except OSError:
                    pass
                QTimer.singleShot(900, lambda: self.panel.start_first_login("canvas"))
        elif not session_store.has_ams_session():
            # Canvas 还在、AMS 掉了：后台悄悄补一次，不打扰
            QTimer.singleShot(1200, lambda: self._silent_relogin("ams"))
        self.worker.start()

    # ---------------------------------------------------------------- actions
    # ------------------------------------------------------- 定时提醒
    def _on_scheduled_remind(self, assignment, minutes: int) -> None:
        when = datetime.now() + timedelta(minutes=max(1, int(minutes)))
        reminders.add(assignment.id, assignment.title, when)
        if not autostart_mod.is_enabled():
            try:
                autostart_mod.set_enabled(True)
                self.toast.show_text(t("toast.autostart_on"), self.ball.frameGeometry(), 4200)
            except OSError:
                pass
        self.toast.show_text(t("toast.remind_set") % when.strftime("%m-%d %H:%M"),
                             self.ball.frameGeometry())
        if not self._reminder_timer.isActive():
            self._reminder_timer.start()

    def _on_scheduled_remind_at(self, assignment, when) -> None:
        """右键里自己挑的日期时间，直接按那个时间点提醒。"""
        reminders.add(assignment.id, assignment.title, when)
        if not autostart_mod.is_enabled():
            try:
                autostart_mod.set_enabled(True)
                self.toast.show_text(t("toast.autostart_on"), self.ball.frameGeometry(), 4200)
            except OSError:
                pass
        self.toast.show_text(t("toast.remind_set") % when.strftime("%m-%d %H:%M"),
                             self.ball.frameGeometry())
        if not self._reminder_timer.isActive():
            self._reminder_timer.start()

    def _check_scheduled_reminders(self) -> None:
        for item in reminders.due():
            if self._quiet_now():
                continue
            self.tray.showMessage(t("tray.reminder"), item["title"],
                                  QSystemTrayIcon.MessageIcon.Information, 10000)
            self.toast.show_text("%s · %s" % (t("tray.reminder"), item["title"]),
                                 self.ball.frameGeometry(), 4200)
            reminders.remove(item["id"])

    def _follow_pet(self) -> None:
        """拖着人物走时，面板跟着一起走（保持打开时的相对位置）。"""
        if self._syncing or self._ball_offset is None or not self.panel.isVisible():
            return
        self._syncing = True
        try:
            top_right = self.ball.pos() - self._ball_offset
            self.panel.move(top_right.x() - self.panel.width() + 1, top_right.y())
        finally:
            self._syncing = False

    def _follow_ball(self) -> None:
        """面板被拖动/缩放时，让球跟着面板右上角走，保持原来的相对位置。"""
        if self._syncing:
            return
        if self.panel.isVisible() and self._ball_offset is not None:
            target = self.panel.geometry().topRight() + self._ball_offset
            self.ball.move(target)

    def _close_panel(self) -> None:
        self.panel.hide()
        self._ball_offset = None

    def _toggle_panel(self) -> None:
        self.panel.toggle_near(self.ball.frameGeometry())
        if self.panel.isVisible():
            self.bubble.hide()
            # 记下球相对面板右上角的偏移，之后面板一挪球就跟着
            self._ball_offset = self.ball.pos() - self.panel.geometry().topRight()
        else:
            self._ball_offset = None
        # 面板是普通窗口，球是置顶窗口；开合时把球重新提到最前，
        # 免得某些窗口管理器在激活面板时把它压下去。
        self.ball.raise_()
        level = self.settings.window_level or "top"
        self._set_native_level(self.ball, level)
        self._set_native_level(self.panel, "top" if level == "top" else "normal")

    # ------------------------------------------------------------ reminders
    @staticmethod
    def _active(snap: Snapshot) -> list[Assignment]:
        """归档过的作业不再参与任何提醒、计数和角标。"""
        ids = archive.ids()
        return [a for a in snap.assignments if a.id not in ids]

    def _check_reminders(self, snap: Snapshot) -> None:
        """New homework and anything due within two hours."""
        now = datetime.now()
        active = self._active(snap)
        current = {a.id for a in active if not a.is_submitted}
        first_run = self._seen_ids is None
        new_ids = current - (self._seen_ids or set())
        self._seen_ids = current

        if not first_run and not self._quiet_now():
            for assignment in active:
                if assignment.id in new_ids and not assignment.is_reminder:
                    self.tray.showMessage(
                        "新作业", "%s · %s" % (assignment.course_name, assignment.title),
                        QSystemTrayIcon.MessageIcon.Information, 6000,
                    )
                    break

        for assignment in active:
            if assignment.is_submitted or assignment.is_reminder or assignment.due_at is None:
                continue
            due = assignment.due_at
            if due.tzinfo:
                due = due.astimezone().replace(tzinfo=None)
            left = (due - now).total_seconds()
            if 0 < left <= 7200 and assignment.id not in self._notified:
                if self._quiet_now():
                    continue
                self._notified.add(assignment.id)
                self.tray.showMessage(
                    "即将截止",
                    "%s · 还剩 %d 分钟" % (assignment.title, max(1, int(left // 60))),
                    QSystemTrayIcon.MessageIcon.Warning, 8000,
                )

    # ------------------------------------------------------- 提醒时间窗
    def _quiet_now(self) -> bool:
        """勿扰时段内不弹任何提示（数字照常更新）。"""
        start = int(getattr(self.settings, "quiet_start", 23) or 0)
        end = int(getattr(self.settings, "quiet_end", 7) or 0)
        return in_quiet_hours(datetime.now().hour, start, end)

    def _check_class_reminders(self, snap: Snapshot) -> None:
        """开课前 N 分钟提醒一次，同一节课只提醒一次。"""
        if not getattr(self.settings, "class_reminders", True):
            return
        minutes = max(1, int(getattr(self.settings, "class_remind_minutes", 10)))
        now = datetime.now()
        today = now.date().isoformat()
        self._class_seen = {k for k in self._class_seen if k[0] == today}
        for lesson in snap.lessons:
            start = lesson.start
            if start is None:
                continue
            if start.tzinfo:
                start = start.astimezone().replace(tzinfo=None)
            left = (start - now).total_seconds()
            if not 0 < left <= minutes * 60:
                continue
            key = (start.date().isoformat(), start.strftime("%H:%M"), lesson.title)
            if key in self._class_seen:
                continue
            self._class_seen.add(key)
            if self._quiet_now():
                continue
            where = lesson.location or lesson.title
            text = "%s · %d 分钟后上课" % (where, max(1, int(left // 60)))
            self.tray.showMessage("快上课了", text, QSystemTrayIcon.MessageIcon.Information, 8000)
            self.toast.show_text(text, self.ball.frameGeometry())

    def _maybe_daily_brief(self, snap: Snapshot) -> None:
        """每天第一条早报：今天几节课、几个待交、最近一件是什么。"""
        if not getattr(self.settings, "daily_brief", True):
            return
        now = datetime.now()
        if now.hour < 7 or self._quiet_now():
            return
        day = now.date().isoformat()
        if getattr(self.settings, "last_brief_day", "") == day:
            return
        if not snap.canvas_ok and not snap.ams_ok:
            return
        parts = []
        if snap.ams_ok:
            parts.append("今天 %d 节课" % len([l for l in snap.lessons if l.start]))
        pending = [a for a in self._active(snap) if not a.is_submitted and not a.is_reminder]
        if snap.canvas_ok:
            parts.append("%d 个待交" % len(pending))
        if not parts:
            return
        text = " · ".join(parts)
        soon = self._next_due_text(pending, now)
        if soon:
            text += "，最近一件 " + soon
        self.settings.last_brief_day = day
        try:
            self.settings.save()
        except OSError:
            pass
        self.tray.showMessage("早上好", text, QSystemTrayIcon.MessageIcon.Information, 10000)
        self.toast.show_text(text, self.ball.frameGeometry())

    @staticmethod
    def _next_due_text(pending, now: datetime) -> str:
        due = None
        title = ""
        for assignment in pending:
            if assignment.due_at is None:
                continue
            d = assignment.due_at
            if d.tzinfo:
                d = d.astimezone().replace(tzinfo=None)
            if due is None or d < due:
                due, title = d, assignment.title
        if due is None:
            return ""
        return "%s（%s）" % (title, human_left((due - now).total_seconds()))

    def _badge_text(self, snap: Snapshot) -> str | None:
        """角标口径：默认是待交数量；选了 due 就显示离最近截止还有多久。"""
        if getattr(self.settings, "badge_mode", "count") != "due":
            return None
        now = datetime.now()
        due = None
        for assignment in self._active(snap):
            if assignment.is_submitted or assignment.is_reminder or assignment.due_at is None:
                continue
            d = assignment.due_at
            if d.tzinfo:
                d = d.astimezone().replace(tzinfo=None)
            if due is None or d < due:
                due = d
        if due is None:
            return None
        text = badge_left((due - now).total_seconds())
        if text != getattr(self, "_last_badge", None):
            self._last_badge = text
            logging.getLogger("wsdock.perf").info("角标：%s", text)
        return text

    # ---------------------------------------------------------------- focus
    # ---------------------------------------------------- silent re-login
    def _on_auth_expired(self, which: str) -> None:
        """Session died — renew it behind the scenes."""
        if time.time() - self._last_relogin < 300:
            return
        self._last_relogin = time.time()
        self._silent_relogin("ams" if which == "ams" else "canvas")

    def _silent_relogin(self, mode: str = "canvas") -> None:
        if self._relogin_window is not None:
            return
        try:
            from wsdock.ui.login import LoginWindow
        except Exception:
            return
        window = LoginWindow(mode)
        window.setAttribute(Qt.WidgetAttribute.WA_DontShowOnScreen, True)
        window.succeeded.connect(self._on_silent_login)
        window.show()          # WA_DontShowOnScreen：不可见、不抢焦点
        self._relogin_window = window
        logging.getLogger("wsdock.perf").info("静默续期（%s）…", mode)
        QTimer.singleShot(15000, lambda: self._end_silent_login(window))

    def _on_silent_login(self, mode: str, payload: dict) -> None:
        from wsdock import session as session_store
        cookies = (payload or {}).get("cookies") or {}
        if mode == "canvas":
            session_store.save_cookies(cookies)
        else:
            session_store.save_ams_cookies(cookies)
        self.worker.kick()

    def _end_silent_login(self, window) -> None:
        try:
            window.close()
        except RuntimeError:
            pass
        if self._relogin_window is window:
            self._relogin_window = None
        if not session_store.has_any_canvas_auth():
            self.panel.set_needs_login(True)

    def _on_busy(self, busy: bool) -> None:
        self._busy = bool(busy)
        self._refresh_ball_mode()
        if busy:
            self._say("refresh", t("say.refresh"), 8.0)

    def _refresh_ball_mode(self) -> None:
        was = self.ball.current_state()
        if self._busy:
            self.ball.set_mode("syncing")
        elif self._in_class:
            self.ball.set_mode("class")
        else:
            self.ball.set_mode("idle")
        if not self._busy and self._in_class and was != "class":
            self._say("class", t("say.class"), 5.0)

    def _remind(self, assignment) -> None:
        title = assignment.title
        QTimer.singleShot(30 * 60 * 1000, lambda: self.tray.showMessage(
            "提醒", title, QSystemTrayIcon.MessageIcon.Information, 10000))
        self.toast.show_text(t("toast.reminded") % title, self.ball.frameGeometry())

    def _start_focus(self, assignment) -> None:
        self._focus = {"title": assignment.title,
                       "ends": datetime.now() + timedelta(minutes=25)}
        self._focus_timer.start()
        self.toast.show_text("专注开始 · 25 分钟", self.ball.frameGeometry())

    def _focus_text(self) -> str:
        if not self._focus:
            return ""
        left = int((self._focus["ends"] - datetime.now()).total_seconds())
        left = max(0, left)
        return "专注 %02d:%02d · %s" % (left // 60, left % 60, self._focus["title"])

    def _tick_focus(self) -> None:
        if not self._focus:
            self._focus_timer.stop()
            return
        if (self._focus["ends"] - datetime.now()).total_seconds() > 0:
            return
        title = self._focus["title"]
        self._focus = None
        self._focus_timer.stop()
        self.tray.showMessage("专注结束", "%s · 25 分钟到了" % title,
                              QSystemTrayIcon.MessageIcon.Information, 8000)

    # ---------------------------------------------------------------- export
    def _export_ics(self) -> None:
        from wsdock.ics import build_ics

        snap = self.panel.snapshot()
        if snap is None:
            self.toast.show_text("还没有数据，先刷新一次", self.ball.frameGeometry())
            return
        lessons = snap.lessons_week or snap.lessons
        text = build_ics(lessons, snap.assignments)
        target = Path.home() / "Downloads" / "VesperBoard" / "vesper-board.ics"
        try:
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(text, encoding="utf-8")
        except OSError as exc:
            self.toast.show_text("导出失败：%s" % exc, self.ball.frameGeometry())
            return
        self.toast.show_text("已导出 %s" % target.name, self.ball.frameGeometry())
        self.tray.showMessage("已导出课表", str(target),
                              QSystemTrayIcon.MessageIcon.Information, 6000)

    def _show_menu(self, pos: QPoint) -> None:
        self._tray_menu.popup(pos)

    def _on_snapshot(self, snap: Snapshot) -> None:
        self._snapshot = snap
        now = datetime.now()
        self._in_class = any(
            lesson.start and lesson.end and lesson.start <= now <= lesson.end
            for lesson in snap.lessons
        )
        self._refresh_ball_mode()
        self._check_reminders(snap)
        self._check_class_reminders(snap)
        self._maybe_daily_brief(snap)
        if getattr(snap, "user_name", "") and snap.user_name != getattr(self.settings, "user_name", ""):
            self.settings.user_name = snap.user_name
            self.panel.set_user_name(snap.user_name)
            try:
                self.settings.save()
            except OSError:
                pass
        self.panel.apply_snapshot(snap)
        count, urgent = self.panel.pending_count()
        self.ball.set_state(count, urgent, snap.canvas_ok, self._badge_text(snap))
        tip = "晚星看板 · Vesper Board"
        if snap.canvas_ok:
            tip += f" · 要交 {count} 项"
        if snap.ams_ok and snap.lessons:
            tip += f" · 今天 {len(snap.lessons)} 节课"
        self.ball.setToolTip(tip)
        self.tray.setToolTip(tip)
        self._speak_snapshot(snap, count, urgent)

    def _on_submit(self, assignment: Assignment) -> None:
        # 文件在面板里一行一行挑，全部挑好再一次性提交（Canvas 那种）
        self.panel.show_submit(assignment)

    def _on_submitted(self, result: dict) -> None:
        # 提交成功与否都留一行日志，出问题时能直接看到 Canvas 的原话
        self._append_log("提交结果：%s" % result.get("message", ""))
        if result.get("ok"):
            self.panel.mark_submitted(result.get("assignment"))
            self.worker.kick()
        message = result.get("message", "完成")
        self.toast.show_text(message, self.ball.frameGeometry(),
                             msec=4200 if result.get("ok") else 6000)
        if not self.panel.isVisible():
            self.tray.showMessage("Vesper Board", message, QSystemTrayIcon.MessageIcon.Information, 4000)

    def _on_downloaded(self, result: dict) -> None:
        message = result.get("message", "完成")
        self.toast.show_text(message, self.ball.frameGeometry(),
                             msec=4200 if result.get("ok") else 6000)
        if not self.panel.isVisible():
            self.tray.showMessage("Vesper Board", message,
                                  QSystemTrayIcon.MessageIcon.Information, 4000)

    def _open_settings(self, first_run: bool = False) -> None:
        if not self.panel.isVisible():
            self.panel.popup(self.ball.frameGeometry())
        self.panel.show_settings()

    def _on_login_requested(self) -> None:
        self._open_settings()
        self.panel.start_first_login("canvas")

    def _on_settings_changed(self) -> None:
        try:
            self.settings.save()
        except OSError:
            pass
        self.ball.set_skin(getattr(self.settings, "pet_skin", ""))
        self.ball.set_pet_size(int(getattr(self.settings, "pet_size", 92) or 92))
        self.ball.set_glow(bool(getattr(self.settings, "pet_glow", False)))
        self.ball.set_badge(bool(getattr(self.settings, "show_badge", False)))
        before_mode = theme.MODE
        if theme.apply_mode(getattr(self.settings, "theme_mode", "system")) != before_mode:
            theme.apply_palette(QApplication.instance())
            self._rebuild_panel()
        # 换形象 / 改大小只动小人，面板留在原地看着不动：
        # 这里只重算一下跟随用的偏移，不重新弹面板（否则窗口会"跳"一下）
        if self.panel.isVisible():
            self._ball_offset = self.ball.pos() - self.panel.geometry().topRight()
        self._apply_level(self.settings.window_level or "top", persist=False)
        self.worker.reload(self.settings)
        self.worker.kick()

    def _on_submit_confirmed(self, assignment, paths) -> None:
        files = paths if isinstance(paths, (list, tuple)) else [paths]
        self.toast.show_text("正在上传…", self.ball.frameGeometry())
        self.worker.request_submit(assignment, list(files))

    def _open_url(self, url: str) -> None:
        """Only ever hand http(s) URLs to the shell — never file:, javascript: etc."""
        if not url:
            return
        from PySide6.QtCore import QUrl
        from PySide6.QtGui import QDesktopServices
        parsed = QUrl(url)
        if parsed.scheme() not in ("http", "https") or not parsed.host():
            self._append_log(f"拒绝打开非 http(s) 链接：{url[:60]}")
            return
        # 浏览器启动后会抢焦点，面板会误以为你切走了；先按住几秒
        self.panel.hold(True)
        QDesktopServices.openUrl(parsed)
        QTimer.singleShot(5000, lambda: self.panel.hold(False))

    @staticmethod
    def _append_log(message: str) -> None:
        log.info(message)
        try:
            with paths.log_file().open("a", encoding="utf-8") as fh:
                fh.write(message + "\n")
        except OSError:
            pass

    # ------------------------------------------------------------------ close
    # ------------------------------------------------------------ z-order
    def _sync_level_actions(self) -> None:
        current = self.settings.window_level or "top"
        for key, action in self.level_actions.items():
            action.setChecked(key == current)

    def _apply_level(self, level: str, persist: bool = True) -> None:
        """top = always on top, normal = ordinary window, desktop = bottom layer."""
        level = level if level in ("top", "normal", "desktop") else "top"
        self.settings.window_level = level
        if persist:
            try:
                self.settings.save()
            except OSError:
                pass
        self._set_native_level(self.ball, level)
        # 面板是挂在人物旁边的，人物置顶时面板也置顶
        self._set_native_level(self.panel, "top" if level == "top" else "normal")
        if level != "top":
            self.tip.hide()

    @staticmethod
    def _set_native_level(widget, level: str) -> None:
        if not sys.platform.startswith("win"):
            # macOS / Linux 没有 SetWindowPos；用 Qt 的置顶标志，改完要重新 show。
            try:
                widget.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint, level == "top")
                if widget.isVisible():
                    widget.show()
            except Exception:
                pass
            return
        try:
            import ctypes
            u32 = ctypes.windll.user32
            # 64 位下 HWND 是 8 字节：不声明 argtypes 会被 ctypes 截成 int32，
            # SetWindowPos 就返回 ERROR_INVALID_WINDOW_HANDLE（置顶静默失效）。
            u32.SetWindowPos.argtypes = (
                ctypes.c_void_p, ctypes.c_void_p, ctypes.c_int,
                ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_uint,
            )
            u32.SetWindowPos.restype = ctypes.c_bool
            hwnd = ctypes.c_void_p(int(widget.winId()) & 0xFFFFFFFFFFFFFFFF)
            target = ctypes.c_void_p(
                {"top": -1, "normal": -2, "desktop": 1}[level] & 0xFFFFFFFFFFFFFFFF)
            flags = 0x0001 | 0x0002 | 0x0010          # NOSIZE | NOMOVE | NOACTIVATE
            u32.SetWindowPos(hwnd, target, 0, 0, 0, 0, flags)
        except Exception:
            pass

    # -------------------------------------------------------------- hover
    def _show_hover(self) -> None:
        if self.panel.isVisible():
            return
        text = self._focus_text() or self.panel.hover_summary()
        self.tip.show_text(text, self.ball.frameGeometry())

    def _hide_hover(self) -> None:
        self.tip.hide()

    def eventFilter(self, obj, event):  # noqa: N802
        # 面板一出现就把气泡收起来，免得被弹窗挡住/从边上露出来
        if obj is self.panel and event.type() == QEvent.Type.Show:
            if self.bubble.isVisible():
                self.bubble.hide()
        return super().eventFilter(obj, event)

    # ------------------------------------------------------------- speech
    def _say(self, key: str, text: str, seconds: float = 6.0) -> None:
        """人物说一句话。同一句 45 秒内不重复，面板打开时不打扰。"""
        if self.panel.isVisible():
            return
        now = time.time()
        if key and key == self._speech_key and now - self._speech_at < 45:
            return
        self._speech_key = key
        self._speech_at = now
        self.bubble.say(text, self.ball.frameGeometry(), seconds)

    def _speak_snapshot(self, snap: Snapshot, count: int, urgent: bool) -> None:
        # 第一次刷新完先打个招呼，保证一打开就能看到人物说话
        if self._first_snap:
            self._first_snap = False
            if snap.canvas_ok:
                line = t("say.hello") % count if count else t("say.done")
                self._say("hello", line, 8.0)
                return
        if not snap.canvas_ok and snap.canvas_error:
            self._say("error", t("say.error"), 6.0)
            return
        if count <= 0:
            self._say("done", t("say.done"), 5.0)
            return
        if urgent:
            self._say("urgent", t("say.urgent") % count, 5.0)
            return
        nxt = self.panel.hover_summary()
        if nxt:
            self._say("next", nxt, 5.0)

    def _place_bubble(self) -> None:
        if self.bubble.isVisible():
            self.bubble.say(self.bubble._text, self.ball.frameGeometry(), 2.5)

    def shutdown(self) -> None:
        self.settings.ball_x = self.ball.x()
        self.settings.ball_y = self.ball.y()
        try:
            self.settings.save()
        except OSError:
            pass
        self.worker.stop()
        self.tray.hide()
        QApplication.quit()


_MUTEX = None


def already_running() -> bool:
    """单实例。

    Windows 上用命名互斥量：QLockFile 靠锁文件的 mtime + PID 判断，实测出现过
    两个进程同时认为自己持有锁（旧进程被认定成 stale），结果桌面上并排两个球、
    一个还是旧代码。
    """
    global _MUTEX
    if _MUTEX or globals().get("_LOCK"):
        # 本次进程已经拿到锁。再建一个同名互斥量/锁文件会得到「已存在」，
        # 把自己误判成「已有实例」。
        return False

    if sys.platform.startswith("win"):
        try:
            import ctypes
            k32 = ctypes.WinDLL("kernel32", use_last_error=True)
            k32.CreateMutexW.restype = ctypes.c_void_p
            k32.CloseHandle.argtypes = [ctypes.c_void_p]
            # CreateMutexW 成功时不会清零 last error，必须先自己置 0，
            # 否则读到上一次调用残留的 ERROR_ALREADY_EXISTS（183）会误判。
            ctypes.set_last_error(0)
            handle = k32.CreateMutexW(None, False, "VesperBoard")
            already = ctypes.get_last_error() == 183   # ERROR_ALREADY_EXISTS
            if not handle:
                raise OSError(ctypes.get_last_error())
            if already:
                k32.CloseHandle(handle)                # 别人创建的，别持有
                return True
            _MUTEX = handle                            # 进程存活期间一直持有
            return False
        except Exception:
            pass
    # 锁放在数据目录的父级：这里还没决定是否要迁移/创建数据目录
    lock_dir = paths.root_dir().parent
    try:
        lock_dir.mkdir(parents=True, exist_ok=True)
    except OSError:
        import tempfile
        lock_dir = Path(tempfile.gettempdir())
    lock = QLockFile(str(lock_dir / ("%s.lock" % paths.APP_NAME)))
    lock.setStaleLockTime(30_000)
    if not lock.tryLock(100):
        return True
    globals()["_LOCK"] = lock          # keep the lock alive for the process
    return False


def main() -> int:
    # 单实例检查必须在任何 paths.data_dir() 之前：日志、迁移都会碰数据目录，
    # 两个实例并发迁移会互相踩 staging。
    if already_running():
        return 0

    from logging.handlers import RotatingFileHandler

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
        handlers=[RotatingFileHandler(
            paths.log_file(), maxBytes=1_000_000, backupCount=2, encoding="utf-8")],
    )
    for gone in paths.purge_plain_cookies():
        logging.getLogger("wsdock.privacy").info("已清理明文 cookie：%s", gone.name)
    _t0 = time.perf_counter()
    QApplication.setAttribute(Qt.ApplicationAttribute.AA_ShareOpenGLContexts, True)
    QApplication.setAttribute(Qt.ApplicationAttribute.AA_DontCreateNativeWidgetSiblings, True)
    try:                                  # 让通知以"Vesper Board"的身份弹出
        import ctypes
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("VesperBoard.1")
    except Exception:
        pass
    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)
    app.setApplicationName("VesperBoard")
    theme.install_qss_hook()
    app.setApplicationDisplayName("Vesper Board")
    app.setWindowIcon(make_icon())

    settings = Settings.load()
    set_language(getattr(settings, "language", "zh"))
    theme.apply_mode(getattr(settings, "theme_mode", "system"))
    theme.apply_palette(app)

    if "--login-check" in sys.argv:
        # 打包环境下排查"点登录没反应"用：构造一个隐藏的登录窗，把结果写进日志
        try:
            from wsdock.ui.login import LoginWindow
            probe = LoginWindow("canvas", seed=False)
            probe.setAttribute(Qt.WidgetAttribute.WA_DontShowOnScreen, True)
            probe.show()
            ok = probe.isVisible()
            probe.close()
            logging.getLogger("wsdock.login").info("登录窗自检：%s", "通过" if ok else "窗口未显示")
        except Exception as exc:
            import traceback
            logging.getLogger("wsdock.login").error(
                "登录窗自检失败：%s\n%s", exc, traceback.format_exc())
        return 0
    logging.getLogger("wsdock.perf").info(
        "启动配置：语言设置=%s 实际=%s 角标=%s 形象=%s 归档=%d",
        getattr(settings, "language", "?"), i18n.LANG,
        getattr(settings, "badge_mode", "?"), getattr(settings, "pet_skin", "") or "默认",
        len(archive.ids()),
    )
    logging.getLogger("wsdock.perf").info("启动: Qt 就绪 %.0f ms", (time.perf_counter() - _t0) * 1000)
    dock = Dock(settings)
    logging.getLogger("wsdock.perf").info("启动: Dock 构建 %.0f ms", (time.perf_counter() - _t0) * 1000)
    dock.show()
    dock.start()
    logging.getLogger("wsdock.perf").info("启动: 全部就绪 %.0f ms", (time.perf_counter() - _t0) * 1000)
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
