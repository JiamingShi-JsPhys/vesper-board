"""The expanded card: today's unfinished work and today's timetable."""

from __future__ import annotations

import logging
import time
from datetime import datetime, timedelta
from pathlib import Path

from PySide6.QtCore import QPoint, QRectF, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QFont, QLinearGradient, QPainter, QPainterPath, QPen, QPixmap
from PySide6.QtWidgets import (
    QApplication, QButtonGroup, QFrame, QHBoxLayout, QLabel, QPushButton,
    QScrollArea, QSizePolicy, QStackedWidget, QVBoxLayout, QWidget,
)

from .. import archive
from ..agenda import build as build_agenda
from ..i18n import t
from ..models import Assignment, AssignmentDetail, Attachment, Lesson, Snapshot
from ..settings import Settings
from .settings_page import SettingsPage
from . import theme
from ..timefmt import fmt_date, weekdays
from .widgets import (
    AssignmentRow, AttachmentRow, DropArea, ElidedLabel, EmptyState,
    FilePickRow, FoldSection, GradeRow, LessonRow, NoticeRow, SectionHeader,
    fmt_day, fmt_relative,
)

log = logging.getLogger("wsdock.perf")

WIDTH = 760
HEIGHT = 620
MARGIN = 14
SIDEBAR_W = 92



def _brand_mark(side: int) -> QPixmap:
    """左上角的品牌标：优先用 assets/app_icon.png，没有就画一个圆球 V。"""
    from .. import paths as _paths
    path = _paths.bundle_dir() / "assets" / "app_icon.png"
    if path.exists():
        pix = QPixmap(str(path))
        if not pix.isNull():
            return pix.scaled(side, side, Qt.AspectRatioMode.KeepAspectRatio,
                              Qt.TransformationMode.SmoothTransformation)
    pix = QPixmap(side, side)
    pix.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pix)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    grad = QLinearGradient(0, 0, 0, side)
    grad.setColorAt(0, QColor(86, 158, 255))
    grad.setColorAt(1, QColor(44, 96, 214))
    painter.setBrush(grad)
    painter.setPen(Qt.PenStyle.NoPen)
    painter.drawEllipse(QRectF(0.5, 0.5, side - 1, side - 1))
    font = QFont("Microsoft YaHei UI")
    font.setPixelSize(int(side * 0.52))
    font.setWeight(QFont.Weight.DemiBold)
    painter.setFont(font)
    painter.setPen(QPen(QColor(255, 255, 255, 240)))
    painter.drawText(pix.rect(), Qt.AlignmentFlag.AlignCenter, "V")
    painter.end()
    return pix


class Panel(QWidget):
    submit_requested = Signal(object)
    refresh_requested = Signal()
    settings_requested = Signal()
    open_url = Signal(str)
    detail_requested = Signal(object)
    download_requested = Signal(object)
    settings_changed = Signal()
    login_done = Signal(str)
    submit_confirmed = Signal(object, object)   # (assignment, [路径])
    archive_requested = Signal(object)
    archive_changed = Signal()
    focus_requested = Signal(object)
    remind_requested = Signal(object)
    login_requested = Signal()
    export_requested = Signal()
    scheduled_remind = Signal(object, int)
    scheduled_remind_at = Signal(object, object)   # (assignment, datetime)
    moved = Signal()          # 面板被拖动或缩放，球要跟着走
    close_requested = Signal()   # 点右上角 ✕

    def __init__(self, settings: Settings | None = None, parent=None):
        super().__init__(parent)
        self.settings = settings or Settings.load()
        # 面板是挂在人物旁边的悬浮窗：和人物一起置顶，拖着人物走它跟着走
        self.setWindowFlags(
            Qt.WindowType.Tool
            | Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.NoDropShadowWindowHint
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setMinimumSize(640, 470)
        self.resize(max(640, int(getattr(self.settings, "panel_w", WIDTH) or WIDTH)),
                    max(470, int(getattr(self.settings, "panel_h", HEIGHT) or HEIGHT)))
        self._drag_from = None
        self._hold_open = False
        self._shown_at = 0.0
        self._snapshot: Snapshot | None = None
        self._section = "homework"
        self._dirty: set[str] = set()

        # 顶部一条横跨整个面板（左栏 + 右栏）的标题带，下面才是 侧栏 | 内容
        root = QVBoxLayout(self)
        root.setContentsMargins(MARGIN + 20, MARGIN + 18, MARGIN + 22, MARGIN + 20)
        root.setSpacing(10)
        self._build_header(root)

        body = QHBoxLayout()
        body.setSpacing(12)
        body.addWidget(self._build_sidebar())
        outer = QVBoxLayout()
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(10)
        body.addLayout(outer, 1)
        root.addLayout(body, 1)
        self._build_stack(outer)
        self._build_detail(outer)
        self._build_settings(outer)
        self._build_confirm(outer)
        self._build_notice(outer)
        self._build_footer(outer)
        self._install_resize()

    # ------------------------------------------------------------------ build
    def _build_header(self, outer: QVBoxLayout) -> None:
        self._user_name = ""

        top = QHBoxLayout()
        top.setSpacing(8)

        mark = QLabel()
        mark.setFixedSize(30, 30)
        mark.setPixmap(_brand_mark(30))
        mark.setStyleSheet("background: transparent;")
        top.addWidget(mark, 0, Qt.AlignmentFlag.AlignTop)

        brand_col = QVBoxLayout()
        brand_col.setSpacing(1)
        self.brand_label = QLabel(t("brand"))
        brand_font = theme.font(13, QFont.Weight.DemiBold)
        brand_font.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, 0.6)
        self.brand_label.setFont(brand_font)
        self.brand_label.setStyleSheet(f"color: {theme.TEXT.name()};")
        brand_col.addWidget(self.brand_label)

        self.greet_label = ElidedLabel(self._greeting(), theme.font(8.5), theme.TEXT_MUTED)
        brand_col.addWidget(self.greet_label)
        top.addLayout(brand_col, 1)

        self.refresh_btn = QPushButton(t("header.refresh"))
        self.refresh_btn.setFont(theme.font(8))
        self.refresh_btn.setFixedHeight(26)
        self.refresh_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.refresh_btn.clicked.connect(self.refresh_requested.emit)
        self.refresh_btn.setStyleSheet(
            "QPushButton { color: __TEXT__; background: __INK16__;"
            " border: 1px solid __INK22__; border-radius: 13px; padding: 0 12px; }"
            "QPushButton:hover { background: __INK32__; }"
        )

        self.close_btn = QPushButton("✕")
        self.close_btn.setFixedSize(26, 26)
        self.close_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.close_btn.setToolTip(t("header.close"))
        self.close_btn.setStyleSheet(
            "QPushButton { color: __TEXT__; background: __INK16__;"
            " border: 1px solid __INK22__; border-radius: 13px; font-size: 12px; }"
            "QPushButton:hover { color: white; background: __INK34__; }"
        )
        self.close_btn.clicked.connect(self.close_requested.emit)

        for btn in (self.refresh_btn, self.close_btn):
            top.addWidget(btn, 0, Qt.AlignmentFlag.AlignTop)
        outer.addLayout(top)

        row = QHBoxLayout()
        row.setSpacing(8)

        col = QVBoxLayout()
        col.setSpacing(2)
        self.date_label = QLabel("—")
        self.date_label.setFont(theme.font(12, QFont.Weight.DemiBold))
        self.date_label.setStyleSheet(f"color: {theme.TEXT.name()};")
        col.addWidget(self.date_label)

        self.summary_label = ElidedLabel(t("header.loading"), theme.font(8), theme.TEXT_MUTED)
        col.addWidget(self.summary_label)
        row.addLayout(col, 1)

        self.login_btn = QPushButton(t("header.login"))
        self.login_btn.setFont(theme.font(8))
        self.login_btn.setFixedHeight(26)
        self.login_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.login_btn.clicked.connect(self.login_requested.emit)
        self.login_btn.setStyleSheet(
            "QPushButton { color: white; background: rgba(74,144,255,200); border: none;"
            " border-radius: 13px; padding: 0 12px; }"
            "QPushButton:hover { background: rgba(96,160,255,235); }"
        )
        row.addWidget(self.login_btn, 0, Qt.AlignmentFlag.AlignTop)
        self.login_btn.setVisible(False)
        outer.addLayout(row)

    def _greeting(self) -> str:
        """按当前时段问好；名字来自 Canvas，没有就用「同学」。"""
        hour = datetime.now().hour
        if 5 <= hour < 11:
            part = "greet.morning"
        elif 11 <= hour < 13:
            part = "greet.noon"
        elif 13 <= hour < 18:
            part = "greet.afternoon"
        elif 18 <= hour < 23:
            part = "greet.evening"
        else:
            part = "greet.night"
        name = self._user_name or t("greet.guest")
        return t("greet.line") % (t(part), name)

    def set_user_name(self, name: str) -> None:
        name = str(name or "").strip()
        if not name or name == self._user_name:
            return
        self._user_name = name
        if hasattr(self, "greet_label"):
            self.greet_label.setText(self._greeting())


    def _build_sidebar(self) -> QWidget:
        bar = QWidget()
        bar.setFixedWidth(SIDEBAR_W)
        bar.setStyleSheet("background: __INK7__; border-radius: 13px;")
        col = QVBoxLayout(bar)
        col.setContentsMargins(8, 12, 8, 10)
        col.setSpacing(3)

        self.tab_group = QButtonGroup(self)
        self.tab_group.setExclusive(True)
        self.tab_homework = self._nav_button(t("nav.homework"))
        self.tab_schedule = self._nav_button(t("nav.schedule"))
        self.tab_grades = self._nav_button(t("nav.grades"))
        self.tab_notices = self._nav_button(t("nav.notices"))
        self._tabs = (self.tab_homework, self.tab_schedule,
                      self.tab_grades, self.tab_notices)
        # 视觉顺序：课表 → 作业 → 成绩 → 消息 → 设置；按钮 id 仍是 stack 的下标
        for btn, name in ((self.tab_schedule, "schedule"),
                          (self.tab_homework, "homework"),
                          (self.tab_grades, "grades"),
                          (self.tab_notices, "notices")):
            self.tab_group.addButton(btn, self.SECTIONS.index(name))
            col.addWidget(btn)
        self.tab_homework.setChecked(True)

        col.addStretch(1)
        self.side_settings = self._nav_button(t("nav.settings"))
        self.tab_group.addButton(self.side_settings, len(self.SECTIONS))
        col.addWidget(self.side_settings)
        self.tab_group.idClicked.connect(self._on_tab)

        self.tabs_bar = bar          # kept for the "hide on inner pages" logic
        return bar

    def _nav_button(self, label: str) -> QPushButton:
        btn = QPushButton(label)
        btn.setCheckable(True)
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        btn.setFont(theme.font(9))
        btn.setFixedHeight(34)
        btn.setStyleSheet(
            "QPushButton { color: __NAV__; background: transparent;"
            " border: none; border-radius: 9px; text-align: left; padding-left: 12px; }"
            "QPushButton:hover { background: __INK14__; color: white; }"
            "QPushButton:checked { background: rgba(74,144,255,120); color: white; }"
        )
        return btn

    def set_needs_login(self, needed: bool) -> None:
        self.login_btn.setVisible(bool(needed))

    def _update_nav(self) -> None:
        from .. import session as session_store
        self.login_btn.setVisible(not session_store.has_any_canvas_auth())
        snap = self._snapshot
        count = 0
        unread = 0
        if snap is not None:
            archived_ids = archive.ids()
            count = self._agenda([a for a in snap.assignments
                                  if a.id not in archived_ids]).actionable
            unread = sum(1 for n in snap.notices if self._is_unread(n))
        self.tab_homework.setText("%s  %d" % (t("nav.homework"), count) if count else t("nav.homework"))
        self.tab_schedule.setText(t("nav.schedule"))
        self.tab_grades.setText(t("nav.grades"))
        self.tab_notices.setText("%s  %d" % (t("nav.notices"), unread) if unread else t("nav.notices"))
        self.side_settings.setText(t("nav.settings"))

    def _build_stack(self, outer: QVBoxLayout) -> None:
        self.stack = QStackedWidget()
        self.homework_page, self.homework_layout = self._scroll_page()
        self.schedule_page, self.schedule_layout = self._scroll_page()
        self.grades_page, self.grades_layout = self._scroll_page()
        self.notices_page, self.notices_layout = self._scroll_page()
        self.stack.addWidget(self.homework_page)
        self.stack.addWidget(self.schedule_page)
        self.stack.addWidget(self.grades_page)
        self.stack.addWidget(self.notices_page)
        self.stack.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        outer.addWidget(self.stack, 1)

    def _scroll_page(self) -> tuple[QScrollArea, QVBoxLayout]:
        area = QScrollArea()
        area.setWidgetResizable(True)
        area.setFrameShape(QFrame.Shape.NoFrame)
        area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        area.setStyleSheet(theme.SCROLL_QSS)
        holder = QWidget()
        holder.setStyleSheet("background: transparent;")
        layout = QVBoxLayout(holder)
        layout.setContentsMargins(0, 4, 2, 4)
        layout.setSpacing(4)
        layout.addStretch(1)
        area.setWidget(holder)
        return area, layout

    def _build_footer(self, outer: QVBoxLayout) -> None:
        row = QHBoxLayout()
        row.setSpacing(6)
        self.footer_label = QLabel("等待数据…")
        self.footer_label.setFont(theme.font(7.5))
        self.footer_label.setStyleSheet(f"color: {theme.TEXT_MUTED.name()};")
        row.addWidget(self.footer_label, 1)
        outer.addLayout(row)

    def _build_detail(self, outer: QVBoxLayout) -> None:
        self.detail_page = QWidget()
        layout = QVBoxLayout(self.detail_page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        head = QHBoxLayout()
        head.setSpacing(8)
        self.back_btn = QPushButton(t("detail.back"))
        self.back_btn.setFont(theme.font(8))
        self.back_btn.setFixedHeight(26)
        self.back_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.back_btn.setStyleSheet(
            "QPushButton { color: __TEXT__; background: __INK16__;"
            " border: 1px solid __INK22__; border-radius: 13px; padding: 0 12px; }"
            "QPushButton:hover { background: __INK32__; }"
        )
        self.back_btn.clicked.connect(self.close_detail)
        head.addWidget(self.back_btn)
        self.detail_title = ElidedLabel("", theme.font(9.5, QFont.Weight.DemiBold), theme.TEXT)
        head.addWidget(self.detail_title, 1)
        layout.addLayout(head)

        self.detail_meta = QLabel("")
        self.detail_meta.setFont(theme.font(8))
        self.detail_meta.setStyleSheet("color: %s;" % theme.TEXT_MUTED.name())
        layout.addWidget(self.detail_meta)

        self.detail_scroll, self.detail_layout = self._scroll_page()
        layout.addWidget(self.detail_scroll, 1)

        actions = QHBoxLayout()
        actions.setSpacing(8)
        self.detail_submit = QPushButton("提交文件")
        self.detail_submit.setFont(theme.font(8.5))
        self.detail_submit.setFixedHeight(30)
        self.detail_submit.setCursor(Qt.CursorShape.PointingHandCursor)
        self.detail_submit.setStyleSheet(
            "QPushButton { color: white; background: rgba(74,144,255,200); border: none;"
            " border-radius: 15px; padding: 0 16px; }"
            "QPushButton:hover { background: rgba(96,160,255,235); }"
            "QPushButton:disabled { background: __INK16__;"
            " color: __TEXT__; }"
        )
        self.detail_submit.clicked.connect(self._submit_from_detail)
        self.detail_open = QPushButton(t("detail.open_canvas"))
        self.detail_open.setFont(theme.font(8.5))
        self.detail_open.setFixedHeight(30)
        self.detail_open.setCursor(Qt.CursorShape.PointingHandCursor)
        self.detail_open.setStyleSheet(
            "QPushButton { color: __TEXT__; background: __INK18__;"
            " border: none; border-radius: 15px; padding: 0 16px; }"
            "QPushButton:hover { background: __INK34__; }"
        )
        self.detail_open.clicked.connect(self._open_from_detail)
        actions.addWidget(self.detail_submit)
        actions.addWidget(self.detail_open)
        self.detail_archive = QPushButton(t("detail.archive"))
        self.detail_archive.setFont(theme.font(8.5))
        self.detail_archive.setFixedHeight(30)
        self.detail_archive.setCursor(Qt.CursorShape.PointingHandCursor)
        self.detail_archive.setStyleSheet(
            "QPushButton { color: __TEXT__; background: transparent;"
            " border: 1px solid __INK26__; border-radius: 15px; padding: 0 14px; }"
            "QPushButton:hover { background: __INK18__; }"
        )
        self.detail_archive.clicked.connect(self._archive_from_detail)
        actions.addWidget(self.detail_archive)
        self.detail_focus = QPushButton(t("detail.focus"))
        self.detail_focus.setFont(theme.font(8.5))
        self.detail_focus.setFixedHeight(30)
        self.detail_focus.setCursor(Qt.CursorShape.PointingHandCursor)
        self.detail_focus.setStyleSheet(
            "QPushButton { color: __TEXT__; background: rgba(46,180,150,90);"
            " border: none; border-radius: 15px; padding: 0 14px; }"
            "QPushButton:hover { background: rgba(46,180,150,150); }"
        )
        self.detail_focus.clicked.connect(self._focus_from_detail)
        actions.addWidget(self.detail_focus)
        self.detail_remind = QPushButton(t("detail.remind"))
        self.detail_remind.setFont(theme.font(8.5))
        self.detail_remind.setFixedHeight(30)
        self.detail_remind.setCursor(Qt.CursorShape.PointingHandCursor)
        self.detail_remind.setStyleSheet(
            "QPushButton { color: __TEXT__; background: transparent;"
            " border: 1px solid __INK26__; border-radius: 15px; padding: 0 12px; }"
            "QPushButton:hover { background: __INK18__; }"
        )
        self.detail_remind.clicked.connect(self._remind_from_detail)
        actions.addWidget(self.detail_remind)
        actions.addStretch(1)
        layout.addLayout(actions)

        self.stack.addWidget(self.detail_page)
        self._detail: AssignmentDetail | None = None

    def show_detail(self, detail: AssignmentDetail) -> None:
        self._detail = detail
        self._render_detail(detail)
        self.stack.setCurrentIndex(self.stack.indexOf(self.detail_page))

    def close_detail(self) -> None:
        self._restore_tab()

    def _submit_from_detail(self) -> None:
        if self._detail is not None:
            self.submit_requested.emit(self._detail.assignment)

    def _focus_from_detail(self) -> None:
        if self._detail is not None:
            assignment = self._detail.assignment
            self.close_detail()
            self.focus_requested.emit(assignment)

    def _remind_from_detail(self) -> None:
        if self._detail is not None:
            self.remind_requested.emit(self._detail.assignment)

    def _archive_from_detail(self) -> None:
        if self._detail is not None:
            assignment = self._detail.assignment
            self.close_detail()
            self._archive(assignment)

    def _archive(self, assignment) -> None:
        archive.add(assignment)
        if self._snapshot is not None:
            self.apply_snapshot(self._snapshot)
        self.archive_changed.emit()

    def _restore(self, assignment) -> None:
        archive.remove(assignment.id)
        if self._snapshot is not None:
            self.apply_snapshot(self._snapshot)
        self.archive_changed.emit()

    def _open_from_detail(self) -> None:
        if self._detail is not None:
            self.open_url.emit(self._detail.assignment.html_url)

    def _attachment_row(self, attachment: Attachment) -> AttachmentRow:
        row = AttachmentRow(attachment)
        row.open_requested.connect(self._open_attachment)
        row.download_requested.connect(self.download_requested.emit)
        return row

    def _open_attachment(self, attachment: Attachment) -> None:
        url = attachment.url or ""
        if not url:
            self.open_url.emit("https://canvas.westlake.edu.cn/files/%d" % attachment.id)
            return
        self.open_url.emit(url)

    def _render_detail(self, detail: AssignmentDetail) -> None:
        self._clear(self.detail_layout)
        assignment = detail.assignment
        self.detail_title.setText(assignment.title)
        due = fmt_day(assignment.due_at) if assignment.due_at else t("time.nodeadline")
        meta = "%s · %s" % (assignment.course_name, due)
        if assignment.is_submitted:
            when = fmt_day(assignment.submitted_at) if assignment.submitted_at else "已提交"
            meta += " · 已提交（%s）" % when
        self.detail_meta.setText(meta)

        if detail.error:
            self.detail_layout.addWidget(EmptyState("读不到作业详情", detail.error))
        else:
            body = QLabel(detail.description or "（这份作业没有文字说明，点下面的按钮去 Canvas 看）")
            body.setWordWrap(True)
            body.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            body.setFont(theme.font(8.5))
            body.setStyleSheet("color: %s;" % theme.TEXT_SOFT.name())
            body.setContentsMargins(4, 2, 4, 6)
            self.detail_layout.addWidget(body)

            if detail.attachments:
                self.detail_layout.addWidget(SectionHeader("附件 · %d" % len(detail.attachments)))
                for attachment in detail.attachments:
                    self.detail_layout.addWidget(self._attachment_row(attachment))

            if detail.course_files:
                rows = [self._attachment_row(f) for f in detail.course_files]
                self.detail_layout.addWidget(
                    FoldSection("课程文件", rows, expanded=not detail.attachments)
                )
        self.detail_layout.addStretch(1)

        self.detail_submit.setVisible(not assignment.is_reminder)
        self.detail_submit.setEnabled(assignment.can_upload)
        self.detail_submit.setText(
            (t("row.resubmit") if assignment.is_submitted else t("row.submit"))
            if assignment.can_upload else t("detail.web_only")
        )
        self.detail_archive.setVisible(True)

    # --------------------------------------------------------------- settings
    def _build_settings(self, outer: QVBoxLayout) -> None:
        self.settings_page = SettingsPage(self.settings)
        self._wire_settings_page(self.settings_page)
        self.settings_scroll = QScrollArea()
        self.settings_scroll.setWidgetResizable(True)
        self.settings_scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.settings_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.settings_scroll.setStyleSheet(theme.SCROLL_QSS)
        self.settings_scroll.setWidget(self.settings_page)
        self.stack.addWidget(self.settings_scroll)

    def _wire_settings_page(self, page) -> None:
        page.back_requested.connect(self.close_settings)
        page.changed.connect(self.settings_changed.emit)
        page.logged_in.connect(self.login_done.emit)
        page.logged_out.connect(self.login_done.emit)
        page.export_requested.connect(self.export_requested.emit)
        page.language_changed.connect(self._on_language_changed)

    def _on_language_changed(self, code: str) -> None:
        from ..i18n import set_language
        set_language(code)
        self.retranslate()

    def start_first_login(self, mode: str = "canvas") -> None:
        self.show_settings()
        self.settings_page.start_login(mode)

    def show_settings(self) -> None:
        self.settings_page.refresh()
        self.stack.setCurrentIndex(self.stack.indexOf(self.settings_scroll))

    def close_settings(self) -> None:
        self._restore_tab()

    # ----------------------------------------------------------------- submit
    def _build_confirm(self, outer: QVBoxLayout) -> None:
        """Canvas 风格的多文件提交页：一行一个文件，最后一次性提交。"""
        self.confirm_page = DropArea()   # 也可以直接从资源管理器拖文件进来
        self.confirm_page.files_dropped.connect(self._add_paths)
        layout = QVBoxLayout(self.confirm_page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)

        head = QHBoxLayout()
        head.setSpacing(8)
        back = QPushButton(t("common.cancel"))
        back.setFont(theme.font(8))
        back.setFixedHeight(26)
        back.setCursor(Qt.CursorShape.PointingHandCursor)
        back.setStyleSheet(
            "QPushButton { color: __TEXT__; background: __INK16__;"
            " border: 1px solid __INK22__; border-radius: 13px; padding: 0 12px; }"
            "QPushButton:hover { background: __INK32__; }"
        )
        back.clicked.connect(self.close_confirm)
        head.addWidget(back)
        title = QLabel(t("confirm.title"))
        title.setFont(theme.font(9.5, QFont.Weight.DemiBold))
        title.setStyleSheet("color: %s;" % theme.TEXT.name())
        head.addWidget(title, 1)
        layout.addLayout(head)

        self.confirm_title = QLabel("")
        self.confirm_title.setFont(theme.font(9.5, QFont.Weight.DemiBold))
        self.confirm_title.setWordWrap(True)
        self.confirm_title.setStyleSheet("color: %s;" % theme.TEXT.name())
        layout.addWidget(self.confirm_title)

        self.confirm_meta = QLabel("")
        self.confirm_meta.setFont(theme.font(8))
        self.confirm_meta.setWordWrap(True)
        self.confirm_meta.setStyleSheet("color: %s;" % theme.TEXT_MUTED.name())
        layout.addWidget(self.confirm_meta)

        layout.addWidget(SectionHeader(t("submit.files")))

        self.file_scroll = QScrollArea()
        self.file_scroll.setWidgetResizable(True)
        self.file_scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.file_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.file_scroll.setStyleSheet(theme.SCROLL_QSS)
        self.file_scroll.setMaximumHeight(190)
        # 至少露出三行，否则后面加的文件全被挤进滚动条里看不见
        self.file_scroll.setMinimumHeight(134)
        holder = QWidget()
        self.file_layout = QVBoxLayout(holder)
        self.file_layout.setContentsMargins(0, 0, 4, 0)
        self.file_layout.setSpacing(6)
        self.file_layout.addStretch(1)
        self.file_scroll.setWidget(holder)
        layout.addWidget(self.file_scroll)
        self.file_rows: list[FilePickRow] = []

        self.add_file_btn = QPushButton(t("submit.add"))
        self.add_file_btn.setFont(theme.font(8.5))
        self.add_file_btn.setFixedHeight(32)
        self.add_file_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.add_file_btn.setStyleSheet(
            "QPushButton { color: %s; background: transparent;"
            " border: 1px solid %s; border-radius: 8px; padding: 0 16px; }"
            "QPushButton:hover { background: rgba(74,144,255,30); }"
            % (theme.ACCENT.name(), theme.ACCENT.name())
        )
        self.add_file_btn.clicked.connect(self._add_file_row)
        layout.addWidget(self.add_file_btn, 0, Qt.AlignmentFlag.AlignLeft)

        for key in ("submit.hint", "confirm.note"):
            note = QLabel(t(key))
            note.setFont(theme.font(7.5))
            note.setWordWrap(True)
            note.setStyleSheet("color: %s;" % theme.TEXT_MUTED.name())
            layout.addWidget(note)
        layout.addStretch(1)

        buttons = QHBoxLayout()
        buttons.setSpacing(8)
        ok = QPushButton(t("confirm.ok"))
        ok.setFont(theme.font(8.5))
        ok.setFixedHeight(30)
        ok.setCursor(Qt.CursorShape.PointingHandCursor)
        ok.setStyleSheet(
            "QPushButton { color: white; background: rgba(74,144,255,200); border: none;"
            " border-radius: 15px; padding: 0 18px; }"
            "QPushButton:hover { background: rgba(96,160,255,235); }"
            "QPushButton:disabled { background: __INK18__; color: __TEXT__; }"
        )
        ok.setEnabled(False)
        ok.clicked.connect(self._confirm_submit)
        self.confirm_ok = ok
        cancel = QPushButton(t("common.cancel"))
        cancel.setFont(theme.font(8.5))
        cancel.setFixedHeight(30)
        cancel.setCursor(Qt.CursorShape.PointingHandCursor)
        cancel.setStyleSheet(
            "QPushButton { color: __TEXT__; background: __INK18__;"
            " border: none; border-radius: 15px; padding: 0 18px; }"
            "QPushButton:hover { background: __INK34__; }"
        )
        cancel.clicked.connect(self.close_confirm)
        buttons.addWidget(ok)
        buttons.addWidget(cancel)
        buttons.addStretch(1)
        layout.addLayout(buttons)

        self.stack.addWidget(self.confirm_page)
        self._confirm: Assignment | None = None

    def _add_file_row(self) -> FilePickRow:
        row = FilePickRow(str(Path.home() / "Desktop"))
        row.changed.connect(self._refresh_submit)
        row.remove_requested.connect(self._remove_file_row)
        self.file_layout.insertWidget(self.file_layout.count() - 1, row)
        self.file_rows.append(row)
        self._refresh_submit()
        return row

    def _remove_file_row(self, row) -> None:
        # 有文件的行点 × 是清空，空行点 ×（正常情况下看不见）就直接删掉
        if row.path is not None:
            row.clear()
        elif len(self.file_rows) > 1:
            self.file_rows.remove(row)
            self.file_layout.removeWidget(row)
            row.deleteLater()
        self._refresh_submit()

    def _add_paths(self, paths) -> None:
        """拖进来的文件：先填空行，空了再新开行。"""
        for raw in paths:
            path = Path(raw)
            if not path.is_file():
                continue
            row = next((r for r in self.file_rows if r.path is None), None)
            if row is None:
                row = self._add_file_row()
            row.set_path(path)
        self._refresh_submit()

    def _refresh_submit(self) -> None:
        self.confirm_ok.setEnabled(any(r.path is not None for r in self.file_rows))

    def show_submit(self, assignment: Assignment) -> None:
        self._confirm = assignment
        self.confirm_title.setText(assignment.title)
        due = fmt_day(assignment.due_at) if assignment.due_at else t("time.nodeadline")
        self.confirm_meta.setText("%s · %s" % (assignment.course_name, due))
        for row in list(self.file_rows):
            self.file_rows.remove(row)
            self.file_layout.removeWidget(row)
            row.deleteLater()
        self._add_file_row()
        self.stack.setCurrentIndex(self.stack.indexOf(self.confirm_page))

    def close_confirm(self) -> None:
        self._confirm = None
        self._restore_tab()

    def _confirm_submit(self) -> None:
        assignment = self._confirm
        if assignment is None:
            return
        paths = [str(r.path) for r in self.file_rows if r.path is not None]
        if not paths:
            return
        self._confirm = None
        self._restore_tab()
        self.submit_confirmed.emit(assignment, paths)

    # ----------------------------------------------------------- notice reader
    def _build_notice(self, outer: QVBoxLayout) -> None:
        self.notice_page = QWidget()
        layout = QVBoxLayout(self.notice_page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        head = QHBoxLayout()
        head.setSpacing(8)
        back = QPushButton(t("detail.back"))
        back.setFont(theme.font(8))
        back.setFixedHeight(26)
        back.setCursor(Qt.CursorShape.PointingHandCursor)
        back.setStyleSheet(
            "QPushButton { color: __TEXT__; background: __INK16__;"
            " border: 1px solid __INK22__; border-radius: 13px; padding: 0 12px; }"
            "QPushButton:hover { background: __INK32__; }"
        )
        back.clicked.connect(self.close_notice)
        head.addWidget(back)
        self.notice_title = ElidedLabel("", theme.font(9.5, QFont.Weight.DemiBold), theme.TEXT)
        head.addWidget(self.notice_title, 1)
        layout.addLayout(head)

        self.notice_meta = QLabel("")
        self.notice_meta.setFont(theme.font(8))
        self.notice_meta.setStyleSheet("color: %s;" % theme.TEXT_MUTED.name())
        layout.addWidget(self.notice_meta)

        self.notice_scroll, self.notice_layout = self._scroll_page()
        layout.addWidget(self.notice_scroll, 1)

        self.notice_open = QPushButton(t("detail.open_browser"))
        self.notice_open.setFont(theme.font(8.5))
        self.notice_open.setFixedHeight(30)
        self.notice_open.setCursor(Qt.CursorShape.PointingHandCursor)
        self.notice_open.setStyleSheet(
            "QPushButton { color: __TEXT__; background: __INK18__;"
            " border: none; border-radius: 15px; padding: 0 16px; }"
            "QPushButton:hover { background: __INK34__; }"
        )
        self.notice_open.clicked.connect(self._open_notice)
        row = QHBoxLayout()
        row.addWidget(self.notice_open)
        row.addStretch(1)
        layout.addLayout(row)

        self.stack.addWidget(self.notice_page)
        self._notice = None

    def show_notice(self, notice) -> None:
        self._mark_notice_read(notice)
        self._notice = notice
        self.notice_title.setText(notice.title)
        bits = [b for b in (notice.course, notice.source.upper()) if b]
        if notice.posted_at:
            local = notice.posted_at
            if local.tzinfo:
                local = local.astimezone().replace(tzinfo=None)
            bits.append("%d月%d日 %02d:%02d" % (local.month, local.day, local.hour, local.minute))
        self.notice_meta.setText(" · ".join(bits))
        self._render_notice_body(notice)
        self.notice_open.setVisible(bool(notice.url))
        self.stack.setCurrentIndex(self.stack.indexOf(self.notice_page))

    def close_notice(self) -> None:
        self._notice = None
        self._restore_tab()

    def _open_notice(self) -> None:
        if self._notice is not None and self._notice.url:
            self.open_url.emit(self._notice.url)

    def _render_notice_body(self, notice) -> None:
        self._clear(self.notice_layout)
        body = QLabel(notice.body or "（这条公告没有正文，点下面的按钮去 Canvas 看）")
        body.setWordWrap(True)
        body.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        body.setFont(theme.font(8.5))
        body.setStyleSheet("color: %s;" % theme.TEXT_SOFT.name())
        body.setContentsMargins(4, 2, 4, 6)
        self.notice_layout.addWidget(body)
        self.notice_layout.addStretch(1)

    # ------------------------------------------------------------------ paint
    def paintEvent(self, event):  # noqa: N802
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        card = QRectF(self.rect()).adjusted(MARGIN, MARGIN, -MARGIN, -MARGIN)

        shadow = QColor(0, 0, 0, 26)
        for spread, alpha in ((10, 10), (6, 14), (3, 20)):
            painter.setBrush(QColor(0, 0, 0, alpha))
            painter.setPen(Qt.PenStyle.NoPen)
            painter.drawRoundedRect(card.adjusted(-spread, -spread + 3, spread, spread + 6),
                                    18 + spread, 18 + spread)

        path = QPainterPath()
        path.addRoundedRect(card, 18, 18)
        painter.fillPath(path, theme.BG_CARD)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.setPen(QColor(255, 255, 255, 24))
        painter.drawRoundedRect(card.adjusted(0.5, 0.5, -0.5, -0.5), 18, 18)

    # ------------------------------------------------------------- public api
    def apply_snapshot(self, snap: Snapshot) -> None:
        """Refresh the data; only the page you are looking at is rebuilt."""
        _t0 = time.perf_counter()
        self._snapshot = snap
        self._dirty = set(self.SECTIONS)
        self._render_header(snap)
        self._render_footer(snap)
        if self.stack.currentIndex() <= 3:      # 前四页是标签页，其余是内页
            self._restore_tab()
        self._render_current()
        log.info("snapshot 渲染 %.0f ms（%s）", (time.perf_counter() - _t0) * 1000, self._section)

    def _render_current(self) -> None:
        if self._snapshot is None or self._section not in self._dirty:
            return
        self._dirty.discard(self._section)
        renderer = {
            "homework": self._render_homework,
            "schedule": self._render_schedule,
            "grades": self._render_grades,
            "notices": self._render_notices,
        }.get(self._section)
        if renderer is not None:
            _t0 = time.perf_counter()
            renderer(self._snapshot)
            log.info("页面 %s 重建 %.0f ms", self._section, (time.perf_counter() - _t0) * 1000)

    def render_all(self) -> None:
        """Force every page to rebuild (used by previews and tests)."""
        if self._snapshot is None:
            return
        for section in list(self._dirty):
            self._section = section
            self._render_current()
        self._section = self.SECTIONS[max(0, self.stack.currentIndex())] \
            if self.stack.currentIndex() < len(self.SECTIONS) else "homework"

    def snapshot(self):
        return self._snapshot

    def set_busy(self, busy: bool) -> None:
        self.refresh_btn.setEnabled(not busy)
        self.refresh_btn.setText("刷新中" if busy else "刷新")

    def _agenda(self, assignments):
        settings = self.settings
        return build_agenda(
            assignments,
            overdue_days=max(1, int(getattr(settings, 'overdue_days', 7))),
            ahead_days=max(1, int(getattr(settings, 'ahead_days', 14))),
            include_older=getattr(settings, 'show_older', True),
            include_far=getattr(settings, 'show_far', True),
            include_reminders=getattr(settings, 'show_reminders', True),
        )

    def pending_count(self) -> tuple[int, bool]:
        """(how many still need handing in, anything due within 24h)"""
        if not self._snapshot:
            return 0, False
        archived_ids = archive.ids()
        items = [a for a in self._snapshot.assignments if a.id not in archived_ids]
        agenda = self._agenda(items)
        return agenda.actionable, agenda.urgent

    def mark_submitted(self, assignment) -> None:
        """Drop a just-submitted item immediately; the next poll confirms it."""
        if not self._snapshot or assignment is None:
            return
        self._snapshot.assignments = [
            a for a in self._snapshot.assignments if a.id != assignment.id
        ]
        self.apply_snapshot(self._snapshot)
        self.close_detail()

    def hover_summary(self) -> str:
        """One short line for the ball's hover strip."""
        if not self._snapshot:
            return ""
        snap = self._snapshot
        if snap.ams_ok and snap.lessons:
            now = datetime.now()
            for lesson in snap.lessons:
                if lesson.start and lesson.end and lesson.start <= now <= lesson.end:
                    where = f" · {lesson.location}" if lesson.location else ""
                    return t("hover.in_class") % (lesson.start.strftime("%H:%M"),
                                lesson.end.strftime("%H:%M"), where)
            upcoming = [l for l in snap.lessons if l.start and l.start > now]
            if upcoming:
                nxt = upcoming[0]
                return t("hover.next_class") % (nxt.start.strftime("%H:%M"), nxt.title)
        archived_ids = archive.ids()
        agenda = self._agenda([a for a in snap.assignments if a.id not in archived_ids])
        if agenda.next_item:
            item = agenda.next_item
            when = fmt_relative(item.due_at) if item.due_at else t("time.nodeadline")
            return f"下一件 {when} · {item.title}"
        return ""

    def toggle_near(self, ball_rect) -> None:
        if self.isVisible():
            self.hide()
        else:
            self.popup(ball_rect)

    def popup(self, ball_rect) -> None:
        screen = QApplication.screenAt(ball_rect.center()) or QApplication.primaryScreen()
        area = screen.availableGeometry() if screen else self.screen().availableGeometry()
        right_half = ball_rect.center().x() > area.center().x()
        x = ball_rect.left() - self.width() + 26 if right_half else ball_rect.right() - 26
        y = ball_rect.center().y() - self.height() // 2
        x = max(area.left() - 6, min(x, area.right() - self.width() + 6))
        y = max(area.top(), min(y, area.bottom() - self.height()))
        self.move(x, y)
        _t0 = time.perf_counter()
        self.show()
        self.raise_()
        self.activateWindow()
        log.info("面板弹出 %.0f ms", (time.perf_counter() - _t0) * 1000)
        self._shown_at = time.monotonic()

    def hold(self, on: bool) -> None:
        self._hold_open = on

    def retranslate(self) -> None:
        """Called after the language changes in settings."""
        self.refresh_btn.setText(t("header.refresh"))
        self.side_settings.setText(t("nav.settings"))
        # 问候语是按启动时的语言生成的，切语言后必须重算
        self.greet_label.setText(self._greeting())
        self.back_btn.setText(t("detail.back"))
        self.detail_open.setText(t("detail.open_canvas"))
        self.detail_archive.setText(t("detail.archive"))
        self.detail_focus.setText(t("detail.focus"))
        self.detail_remind.setText(t("detail.remind"))
        self.notice_open.setText(t("detail.open_browser"))
        self.detail_submit.setText(
            t("row.resubmit") if getattr(self, "_detail", None)
            and self._detail and self._detail.assignment.is_submitted else t("row.submit")
        )
        self._recreate_settings()
        if self._snapshot is not None:
            self.apply_snapshot(self._snapshot)

    def _recreate_settings(self) -> None:
        """Rebuild the settings page so every label picks up the new language."""
        current = self.stack.currentIndex()
        page = SettingsPage(self.settings)
        self._wire_settings_page(page)
        old_inner = self.settings_scroll.takeWidget()
        if old_inner is not None:
            old_inner.deleteLater()
        self.settings_scroll.setWidget(page)
        self.settings_page = page
        self.stack.setCurrentIndex(current)

    def _install_resize(self) -> None:
        from PySide6.QtWidgets import QSizeGrip
        self._grip = QSizeGrip(self)
        self._grip.setFixedSize(16, 16)
        self._move_grip()

    def _move_grip(self) -> None:
        grip = getattr(self, "_grip", None)
        if grip is not None:
            grip.move(self.width() - MARGIN - 20, self.height() - MARGIN - 20)
            grip.raise_()

    def resizeEvent(self, event):  # noqa: N802
        self._move_grip()
        self.settings.panel_w = self.width()
        self.settings.panel_h = self.height()
        self.moved.emit()
        super().resizeEvent(event)

    def moveEvent(self, event):  # noqa: N802
        self.moved.emit()
        super().moveEvent(event)

    def mousePressEvent(self, event):  # noqa: N802
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_from = (event.globalPosition().toPoint()
                               - self.frameGeometry().topLeft())
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):  # noqa: N802
        if self._drag_from is not None and event.buttons() & Qt.MouseButton.LeftButton:
            self.move(event.globalPosition().toPoint() - self._drag_from)
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):  # noqa: N802
        self._drag_from = None
        super().mouseReleaseEvent(event)

    def hideEvent(self, event):  # noqa: N802
        try:
            self.settings.save()
        except OSError:
            pass
        super().hideEvent(event)

    # ---------------------------------------------------------------- events
    def keyPressEvent(self, event):  # noqa: N802
        if event.key() == Qt.Key.Key_Escape:
            self.hide()
            return
        super().keyPressEvent(event)

    def event(self, event):  # noqa: N802
        # 面板一直开着，直到点球或点右上角 ✕ —— 失焦不再自动收起
        return super().event(event)

    def _maybe_hide(self) -> None:
        if self._hold_open or not self.isVisible():
            return
        if time.monotonic() - self._shown_at < 0.5:
            return
        active = QApplication.activeWindow()
        if active is self:
            return
        if active is not None and self.isAncestorOf(active):
            return
        if active is not None and active.windowFlags() & Qt.WindowType.Dialog:
            return
        self.hide()

    SECTIONS = ("homework", "schedule", "grades", "notices")

    def _on_tab(self, index: int) -> None:
        if index >= len(self.SECTIONS):
            self.show_settings()
            return
        self.stack.setCurrentIndex(index)
        self._section = self.SECTIONS[min(index, len(self.SECTIONS) - 1)]
        self._render_current()

    def _restore_tab(self) -> None:
        index = self.SECTIONS.index(self._section) if self._section in self.SECTIONS else 0
        self._tabs[index].setChecked(True)
        self.stack.setCurrentIndex(index)

    # --------------------------------------------------------------- rendering
    @staticmethod
    def _clear(layout: QVBoxLayout) -> None:
        while layout.count():
            item = layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.setParent(None)
                widget.deleteLater()

    def _render_header(self, snap: Snapshot) -> None:
        self._update_notice_tab(snap)
        now = datetime.now()
        self.date_label.setText(fmt_date(now))

        archived_ids = archive.ids()
        agenda = self._agenda([a for a in snap.assignments if a.id not in archived_ids])
        self.tab_homework.setText(f"作业 {agenda.actionable}" if agenda.actionable else "作业")

        if agenda.actionable == 0:
            self.summary_label.setText(
                "没有要交的作业" if not agenda.reminders
                else f"没有要交的作业 · {len(agenda.reminders)} 条仅提醒"
            )
            return

        self._update_notice_tab(snap)

        item = agenda.next_item
        if item is None:
            self.summary_label.setText(f"要交 {agenda.actionable} 项")
            return
        if item.due_at:
            self.summary_label.setText(t("header.next") % (fmt_relative(item.due_at), item.title))
        else:
            self.summary_label.setText(t("header.next") % (t("time.nodeadline"), item.title))

    def _render_footer(self, snap: Snapshot) -> None:
        stamp = snap.updated_at.strftime("%H:%M") if snap.updated_at else "--:--"
        canvas = "Canvas " + (t("footer.connected") if snap.canvas_ok else t("footer.offline"))
        ams = t("nav.schedule") + " " + (t("footer.connected") if snap.ams_ok else t("footer.offline"))
        self.footer_label.setText("%s · %s · %s %s" % (canvas, ams, stamp, t("footer.updated")))
        self.footer_label.setStyleSheet(
            f"color: {(theme.OK if snap.canvas_ok else theme.DANGER).name()};"
        )

    def _render_homework(self, snap: Snapshot) -> None:
        self._clear(self.homework_layout)
        layout = self.homework_layout

        if not snap.canvas_ok:
            layout.addWidget(EmptyState(
                "Canvas 还没有连上",
                snap.canvas_error or "打开设置，用学校账号登录一次即可。",
            ))
            layout.addStretch(1)
            return

        archived_ids = archive.ids()
        items = [a for a in snap.assignments if a.id not in archived_ids]
        agenda = self._agenda(items)
        if agenda.empty and not agenda.reminders:
            layout.addWidget(EmptyState(t("empty.no_homework"), t("empty.no_homework_hint")))
            layout.addStretch(1)
            return

        def make_rows(items: list[Assignment]) -> list[AssignmentRow]:
            rows = []
            for assignment in items:
                row = AssignmentRow(assignment)
                row.submit_requested.connect(self.submit_requested.emit)
                row.open_requested.connect(self.open_url.emit)
                row.detail_requested.connect(self.detail_requested.emit)
                row.archive_requested.connect(self._archive)
                row.remind_requested.connect(self.scheduled_remind.emit)
                row.remind_at_requested.connect(self.scheduled_remind_at.emit)
                rows.append(row)
            return rows

        for title, items in ((t("sect.overdue"), agenda.overdue), (t("sect.today"), agenda.today),
                             (t("sect.tomorrow"), agenda.tomorrow),
                             (t("sect.next7"), agenda.this_week),
                             (t("sect.later"), agenda.later)):
            if not items:
                continue
            layout.addWidget(SectionHeader(f"{title} · {len(items)}"))
            for row in make_rows(items):
                layout.addWidget(row)

        if agenda.older:
            layout.addWidget(FoldSection(t("sect.older"), count=len(agenda.older),
                                                factory=lambda: make_rows(agenda.older)))
        if agenda.far:
            layout.addWidget(FoldSection(t("sect.far"), count=len(agenda.far),
                                             factory=lambda: make_rows(agenda.far)))
        if agenda.reminders:
            layout.addWidget(FoldSection(t("sect.reminders"), count=len(agenda.reminders),
                                                   factory=lambda: make_rows(agenda.reminders)))
        if agenda.submitted:
            layout.addWidget(FoldSection(t("sect.submitted"), count=len(agenda.submitted),
                                                   factory=lambda: make_rows(agenda.submitted)))
        archived = archive.entries()
        if archived:
            rows = []
            for item in archived:
                row = AssignmentRow(item, archived=True)
                row.restore_requested.connect(self._restore)
                rows.append(row)
            layout.addWidget(FoldSection(t("sect.archived"), rows))
        layout.addStretch(1)

    def _render_grades(self, snap: Snapshot) -> None:
        self._clear(self.grades_layout)
        layout = self.grades_layout
        if not snap.grades:
            layout.addWidget(EmptyState(
                t("empty.no_grades"),
                snap.canvas_error or t("empty.no_grades_hint"),
            ))
            layout.addStretch(1)
            return
        layout.addWidget(SectionHeader("%s · %d" % (t("sect.courses"), len(snap.grades))))
        for grade in snap.grades:
            layout.addWidget(GradeRow(grade))
        layout.addStretch(1)

    def _render_notices(self, snap: Snapshot) -> None:
        self._clear(self.notices_layout)
        layout = self.notices_layout
        if not snap.notices:
            layout.addWidget(EmptyState(t("empty.no_notices"), t("empty.no_notices_hint")))
            layout.addStretch(1)
            return
        layout.addWidget(SectionHeader("%s · %d" % (t("sect.messages"), len(snap.notices))))
        for notice in snap.notices[:40]:
            row = NoticeRow(notice, unread=self._is_unread(notice))
            row.open_requested.connect(self.open_url.emit)
            row.detail_requested.connect(self.show_notice)
            layout.addWidget(row)
        layout.addStretch(1)

    def _read_uids(self) -> set:
        return set(getattr(self.settings, "read_notices", []) or [])

    def _is_unread(self, notice) -> bool:
        return notice.uid not in self._read_uids()

    def _mark_notice_read(self, notice) -> None:
        uids = self._read_uids()
        if notice.uid in uids:
            return
        uids.add(notice.uid)
        self.settings.read_notices = sorted(uids)[-500:]
        try:
            self.settings.save()
        except OSError:
            pass

    def _mark_notices_read(self) -> None:
        self._update_nav()

    def _update_notice_tab(self, snap: Snapshot) -> None:
        self._update_nav()

    def _render_schedule(self, snap: Snapshot) -> None:
        self._clear(self.schedule_layout)
        layout = self.schedule_layout

        top = QHBoxLayout()
        top.addStretch(1)
        export = QPushButton(t("sched.export"))
        export.setFont(theme.font(8))
        export.setFixedHeight(26)
        export.setCursor(Qt.CursorShape.PointingHandCursor)
        export.setStyleSheet(
            "QPushButton { color: __TEXT__; background: __INK16__;"
            " border: 1px solid __INK22__; border-radius: 13px; padding: 0 12px; }"
            "QPushButton:hover { background: __INK32__; }"
        )
        export.clicked.connect(self.export_requested.emit)
        top.addWidget(export)
        layout.addLayout(top)

        week = snap.lessons_week or snap.lessons
        if not snap.ams_ok and not week:
            # 异常原文留给日志，界面只说人话
            hint = t("empty.ams_retry") if snap.ams_error else t("empty.ams_off_hint")
            layout.addWidget(EmptyState(t("empty.ams_off"), hint))
            layout.addStretch(1)
            return

        if not week:
            layout.addWidget(EmptyState(t("empty.no_class"), t("empty.no_class_hint")))
            layout.addStretch(1)
            return

        today = datetime.now().date()
        by_day: dict = {}
        for lesson in week:
            if lesson.start is None:
                continue
            by_day.setdefault(lesson.start.date(), []).append(lesson)

        for day in sorted(by_day):
            lessons = sorted(by_day[day], key=lambda l: l.start)
            if day == today:
                label = t("time.today")
            elif day == today + timedelta(days=1):
                label = t("time.tomorrow")
            else:
                label = weekdays()[day.weekday()]
            layout.addWidget(SectionHeader("%s · %d/%d · %d" % (label, day.month, day.day, len(lessons))))
            for lesson in lessons:
                layout.addWidget(LessonRow(lesson))
        layout.addStretch(1)
