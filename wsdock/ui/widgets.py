"""Row widgets used inside the panel."""

from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path

from PySide6.QtCore import QDateTime, QEvent, QRectF, Qt, Signal
from PySide6.QtGui import QColor, QFont, QFontMetrics, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import (
    QDateTimeEdit, QDialog, QFileDialog, QFrame, QHBoxLayout, QLabel, QMenu,
    QMessageBox, QPushButton, QSizePolicy, QVBoxLayout, QWidget,
)

from ..i18n import t
from ..models import Assignment, Attachment, CourseGrade, Lesson, Notice
from . import theme

from ..timefmt import WEEKDAYS, fmt_day, fmt_relative, fmt_time, to_local  # noqa: F401


def due_text(dt: datetime | None) -> str:
    """Overdue items read better as '已逾期 2 天'; everything else as a date."""
    dt = to_local(dt)
    if dt is None:
        return "无截止时间"
    rel = fmt_relative(dt)
    return rel if rel.startswith("已逾期") else fmt_day(dt)


def due_tone(dt: datetime | None) -> QColor:
    dt = to_local(dt)
    if not dt:
        return theme.TEXT_MUTED
    now = datetime.now()
    seconds = (dt - now).total_seconds()
    if seconds < 24 * 3600:          # due today/tomorrow, or already late
        return theme.DANGER
    if seconds < 7 * 86400:          # within a week
        return theme.WARN
    return theme.TEXT_MUTED


class ElidedLabel(QWidget):
    """A label that shortens itself with an ellipsis instead of widening."""

    def __init__(self, text: str, font: QFont, color: QColor, parent=None):
        super().__init__(parent)
        self._text = text
        self._font = font
        self._color = color
        self.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Fixed)
        self.setMinimumHeight(QFontMetrics(font).height() + 2)

    def setText(self, text: str) -> None:
        if text != self._text:
            self._text = text
            self.update()

    def text(self) -> str:
        return self._text

    def paintEvent(self, event) -> None:  # noqa: N802
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.TextAntialiasing)
        painter.setFont(self._font)
        painter.setPen(QPen(self._color))
        metrics = QFontMetrics(self._font)
        text = metrics.elidedText(self._text, Qt.TextElideMode.ElideRight, self.width())
        painter.drawText(self.rect(), Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft, text)


class Chip(QLabel):
    def __init__(self, text: str = "", color: QColor | None = None, parent=None):
        super().__init__(text, parent)
        self.setFont(theme.font(8))
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setFixedHeight(18)
        self.apply(color or theme.TEXT_MUTED)

    def apply(self, color: QColor) -> None:
        self.setStyleSheet(
            "QLabel { color: %s; background: rgba(%d,%d,%d,38);"
            " border-radius: 9px; padding: 0 8px; }"
            % (color.name(), color.red(), color.green(), color.blue())
        )


# ---------------------------------------------------------------------- row
class AssignmentRow(QFrame):
    submit_requested = Signal(object)
    open_requested = Signal(str)
    detail_requested = Signal(object)
    archive_requested = Signal(object)
    restore_requested = Signal(object)
    remind_requested = Signal(object, int)   # (assignment, 分钟数)
    remind_at_requested = Signal(object, object)   # (assignment, datetime)

    def __init__(self, assignment: Assignment, parent=None, archived: bool = False):
        super().__init__(parent)
        self.assignment = assignment
        self.archived = archived
        self._hover = False
        self.setFixedHeight(64)
        if not archived:
            self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setAttribute(Qt.WidgetAttribute.WA_Hover, True)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 9, 10, 9)
        layout.setSpacing(10)

        color = theme.course_color(assignment.course_id)
        bar = QFrame()
        bar.setFixedWidth(3)
        bar.setStyleSheet(
            f"background: {color.name()}; border-radius: 1.5px;"
        )
        layout.addWidget(bar)

        text_col = QVBoxLayout()
        text_col.setSpacing(3)
        title = ElidedLabel(assignment.title, theme.font(9.5, QFont.Weight.DemiBold), theme.TEXT)
        title.setToolTip(assignment.title)
        text_col.addWidget(title)

        meta = QHBoxLayout()
        meta.setSpacing(6)
        course = ElidedLabel(assignment.course_name, theme.font(8), theme.TEXT_MUTED)
        course.setToolTip(assignment.course_name)
        meta.addWidget(course, 1)
        if assignment.is_submitted:
            submitted_at = to_local(assignment.submitted_at)
            due_text_value = ("%s %d月%d日" % (t("row.submitted_on"), submitted_at.month, submitted_at.day)
                              if submitted_at else t("row.submitted"))
            due_colour = theme.TEXT_MUTED
        else:
            due_text_value = due_text(assignment.due_at)
            due_colour = theme.TEXT_MUTED if archived else due_tone(assignment.due_at)
        due = QLabel(due_text_value)
        due.setFont(theme.font(8))
        due.setStyleSheet("color: %s;" % due_colour.name())
        meta.addWidget(due, 0)
        text_col.addLayout(meta)
        layout.addLayout(text_col, 1)

        if archived:
            layout.addWidget(Chip(t("row.archived"), theme.TEXT_MUTED), 0, Qt.AlignmentFlag.AlignVCenter)
            restore = QPushButton(t("row.restore"))
            restore.setFont(theme.font(8))
            restore.setCursor(Qt.CursorShape.PointingHandCursor)
            restore.setFixedHeight(26)
            restore.setStyleSheet(
                "QPushButton { color: __TEXT__; background: __INK18__;"
                " border: none; border-radius: 13px; padding: 0 12px; }"
                "QPushButton:hover { background: __INK34__; }"
            )
            restore.clicked.connect(lambda: self.restore_requested.emit(self.assignment))
            layout.addWidget(restore, 0, Qt.AlignmentFlag.AlignVCenter)
        elif assignment.is_submitted:
            layout.addWidget(Chip(t("row.submitted"), theme.OK), 0, Qt.AlignmentFlag.AlignVCenter)
            if assignment.can_upload:
                resubmit = QPushButton(t("row.resubmit"))
                resubmit.setFont(theme.font(8))
                resubmit.setCursor(Qt.CursorShape.PointingHandCursor)
                resubmit.setFixedHeight(26)
                resubmit.setStyleSheet(
                    "QPushButton { color: white; background: rgba(74,144,255,150);"
                    " border: none; border-radius: 13px; padding: 0 12px; }"
                    "QPushButton:hover { background: rgba(96,160,255,215); }"
                )
                resubmit.clicked.connect(lambda: self.submit_requested.emit(self.assignment))
                layout.addWidget(resubmit, 0, Qt.AlignmentFlag.AlignVCenter)
        elif assignment.is_reminder:
            layout.addWidget(Chip(t("row.reminder"), theme.TEXT_MUTED), 0, Qt.AlignmentFlag.AlignVCenter)
        else:
            self.action = QPushButton(t("row.submit") if assignment.can_upload else t("row.open"))
            self.action.setFont(theme.font(8))
            self.action.setCursor(Qt.CursorShape.PointingHandCursor)
            self.action.setFixedHeight(26)
            self.action.setStyleSheet(
                "QPushButton { color: white; background: rgba(74,144,255,190);"
                " border: none; border-radius: 13px; padding: 0 12px; }"
                "QPushButton:hover { background: rgba(96,160,255,230); }"
            )
            if assignment.can_upload:
                self.action.clicked.connect(lambda: self.submit_requested.emit(self.assignment))
            else:
                self.action.clicked.connect(lambda: self.open_requested.emit(self.assignment.html_url))
                self.action.setStyleSheet(
                    "QPushButton { color: __TEXT__; background: __INK18__;"
                    " border: none; border-radius: 13px; padding: 0 12px; }"
                    "QPushButton:hover { background: __INK34__; }"
                )
            layout.addWidget(self.action, 0, Qt.AlignmentFlag.AlignVCenter)

    # ------------------------------------------------------------- painting
    def enterEvent(self, event):  # noqa: N802
        self._hover = True
        self.update()
        super().enterEvent(event)

    def leaveEvent(self, event):  # noqa: N802
        self._hover = False
        self.update()
        super().leaveEvent(event)

    def mouseReleaseEvent(self, event):  # noqa: N802
        if event.button() == Qt.MouseButton.LeftButton and not self.archived:
            self.detail_requested.emit(self.assignment)
        super().mouseReleaseEvent(event)

    def contextMenuEvent(self, event):  # noqa: N802
        if self.archived:
            return
        from datetime import datetime, timedelta
        menu = QMenu(self)
        menu.addAction(t("row.remind_30")).triggered.connect(
            lambda: self.remind_requested.emit(self.assignment, 30))
        menu.addAction(t("row.remind_1h")).triggered.connect(
            lambda: self.remind_requested.emit(self.assignment, 60))
        now = datetime.now()
        tomorrow = (now + timedelta(days=1)).replace(hour=8, minute=0, second=0, microsecond=0)
        minutes = max(1, int((tomorrow - now).total_seconds() // 60))
        menu.addAction(t("row.remind_tomorrow")).triggered.connect(
            lambda: self.remind_requested.emit(self.assignment, minutes))
        menu.addAction(t("row.remind_custom")).triggered.connect(self._remind_custom)
        menu.addSeparator()
        action = menu.addAction(t("row.archived_action"))
        action.triggered.connect(lambda: self.archive_requested.emit(self.assignment))
        menu.exec(event.globalPos())

    def _remind_custom(self) -> None:
        dialog = RemindDialog(self.window())
        if dialog.exec() == QDialog.DialogCode.Accepted:
            when = dialog.when()
            if when:
                self.remind_at_requested.emit(self.assignment, when)

    def paintEvent(self, event):  # noqa: N802
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        path = QPainterPath()
        path.addRoundedRect(QRectF(self.rect()).adjusted(0, 0, -0.5, -0.5), 10, 10)
        painter.fillPath(path, theme.BG_ROW_HOVER if self._hover else theme.BG_ROW)


class LessonRow(QFrame):
    open_requested = Signal(str)

    def __init__(self, lesson: Lesson, parent=None):
        super().__init__(parent)
        self.setFixedHeight(66)
        self.setAttribute(Qt.WidgetAttribute.WA_Hover, True)
        self._hover = False

        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setSpacing(12)

        now = datetime.now()
        active = bool(lesson.start and lesson.end and lesson.start <= now <= lesson.end)

        time_col = QVBoxLayout()
        time_col.setSpacing(1)
        start = QLabel(fmt_time(lesson.start))
        start.setFont(theme.font(10.5, QFont.Weight.DemiBold))
        start.setStyleSheet(f"color: {theme.ACCENT.name() if active else theme.TEXT.name()};")
        end = QLabel(fmt_time(lesson.end))
        end.setFont(theme.font(8))
        end.setStyleSheet(f"color: {theme.TEXT_MUTED.name()};")
        time_col.addWidget(start)
        time_col.addWidget(end)
        time_col.addStretch(1)
        layout.addLayout(time_col, 0)

        divider = QFrame()
        divider.setFixedWidth(1)
        divider.setStyleSheet(
            f"background: {theme.ACCENT.name() if active else '__INK30__'};"
        )
        layout.addWidget(divider)

        body = QVBoxLayout()
        body.setSpacing(3)
        title = ElidedLabel(lesson.title, theme.font(9.5, QFont.Weight.DemiBold), theme.TEXT)
        title.setToolTip(lesson.title)
        body.addWidget(title)

        meta_bits = [b for b in (lesson.location, lesson.teacher) if b]
        meta = ElidedLabel(" · ".join(meta_bits) or "—", theme.font(8), theme.TEXT_MUTED)
        body.addWidget(meta)
        layout.addLayout(body, 1)

        if active:
            chip = Chip("进行中", theme.ACCENT_2)
            layout.addWidget(chip, 0, Qt.AlignmentFlag.AlignVCenter)

    def enterEvent(self, event):  # noqa: N802
        self._hover = True
        self.update()
        super().enterEvent(event)

    def leaveEvent(self, event):  # noqa: N802
        self._hover = False
        self.update()
        super().leaveEvent(event)

    def paintEvent(self, event):  # noqa: N802
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        path = QPainterPath()
        path.addRoundedRect(QRectF(self.rect()).adjusted(0, 0, -0.5, -0.5), 10, 10)
        painter.fillPath(path, theme.BG_ROW_HOVER if self._hover else theme.BG_ROW)


class FoldSection(QWidget):
    """A group of rows that stays folded until asked for."""

    def __init__(self, title: str, rows: list[QWidget] | None = None,
                 expanded: bool = False, factory=None, count: int | None = None,
                 parent=None):
        super().__init__(parent)
        self._title = title
        self._rows = list(rows or [])
        self._factory = factory
        self._filled = bool(self._rows)
        self._count = count if count is not None else len(self._rows)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(4)

        self.button = QPushButton()
        self.button.setCheckable(True)
        self.button.setChecked(expanded)
        self.button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.button.setFont(theme.font(8))
        self.button.setStyleSheet(
            "QPushButton { color: __MUTED__; background: transparent; border: none;"
            " text-align: left; padding: 5px 6px; }"
            "QPushButton:hover { color: __TEXT__; }"
            "QPushButton:checked { color: __TEXT__; }"
        )
        self.button.toggled.connect(self._relabel)
        outer.addWidget(self.button)

        self.body = QWidget()
        self._body_layout = QVBoxLayout(self.body)
        self._body_layout.setContentsMargins(0, 0, 0, 0)
        self._body_layout.setSpacing(4)
        if self._rows:
            for row in self._rows:
                self._body_layout.addWidget(row)
        self.body.setVisible(expanded)
        outer.addWidget(self.body)

        self._relabel(expanded)

    def _fill(self) -> None:
        """Build the rows only when the group is first opened."""
        if self._filled:
            return
        self._filled = True
        widgets = self._factory() if self._factory is not None else []
        for widget in widgets:
            self._body_layout.addWidget(widget)

    def _relabel(self, expanded: bool) -> None:
        if expanded:
            self._fill()
        self.body.setVisible(expanded)
        suffix = t("row.collapse") if expanded else t("row.expect")
        self.button.setText("%s · %s      %s" % (self._title, t("row.items") % self._count, suffix))


class AttachmentRow(QFrame):
    """One file linked from an assignment: name, size, open and download."""

    open_requested = Signal(object)
    download_requested = Signal(object)

    def __init__(self, attachment: Attachment, parent=None):
        super().__init__(parent)
        self.attachment = attachment
        self.setFixedHeight(44)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(10, 6, 8, 6)
        layout.setSpacing(8)

        icon = QLabel("📎")
        icon.setFont(theme.font(10))
        icon.setStyleSheet(f"color: {theme.TEXT_SOFT.name()};")
        layout.addWidget(icon)

        col = QVBoxLayout()
        col.setSpacing(1)
        name = ElidedLabel(attachment.name, theme.font(8.5, QFont.Weight.DemiBold), theme.TEXT)
        name.setToolTip(attachment.name)
        col.addWidget(name)
        meta = QLabel(attachment.size_text or "附件")
        meta.setFont(theme.font(7.5))
        meta.setStyleSheet(f"color: {theme.TEXT_MUTED.name()};")
        col.addWidget(meta)
        layout.addLayout(col, 1)

        for text, signal in (("打开", self.open_requested), ("下载", self.download_requested)):
            button = QPushButton(text)
            button.setFont(theme.font(7.5))
            button.setFixedHeight(24)
            button.setCursor(Qt.CursorShape.PointingHandCursor)
            button.setStyleSheet(
                "QPushButton { color: __TEXT__; background: __INK18__;"
                " border: none; border-radius: 12px; padding: 0 10px; }"
                "QPushButton:hover { background: __INK34__; }"
            )
            button.clicked.connect(lambda _=False, sig=signal: sig.emit(self.attachment))
            layout.addWidget(button)

    def paintEvent(self, event):  # noqa: N802
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        path = QPainterPath()
        path.addRoundedRect(QRectF(self.rect()).adjusted(0, 0, -0.5, -0.5), 9, 9)
        painter.fillPath(path, theme.BG_ROW)


class GradeRow(QFrame):
    """One course, its score, and the assignments that produced it."""

    def __init__(self, grade: CourseGrade, parent=None):
        super().__init__(parent)
        self.grade = grade
        self._expanded = False
        self.setCursor(Qt.CursorShape.PointingHandCursor)

        self._layout = QHBoxLayout(self)
        self._layout.setContentsMargins(12, 8, 12, 8)
        self._layout.setSpacing(10)

        self._col = QVBoxLayout()
        self._col.setSpacing(3)
        name = ElidedLabel(grade.name, theme.font(9, QFont.Weight.DemiBold), theme.TEXT)
        name.setToolTip(grade.name)
        self._col.addWidget(name)

        hint = (t("row.graded_count") % len(grade.items)) if grade.items else t("row.ungraded")
        meta = QLabel(hint)
        meta.setFont(theme.font(7.5))
        meta.setStyleSheet("color: %s;" % theme.TEXT_MUTED.name())
        self._col.addWidget(meta)

        if grade.items:
            recent = " · ".join(
                "%s %s" % (i.name[:14], _score_text(i)) for i in grade.items[:2]
            )
            line = ElidedLabel(t("row.recent") + recent, theme.font(7.5), theme.TEXT_SOFT)
            line.setToolTip("点击展开全部已评分作业")
            self._col.addWidget(line)

        self.details = QLabel("")
        self.details.setWordWrap(True)
        self.details.setFont(theme.font(7.5))
        self.details.setStyleSheet("color: %s;" % theme.TEXT_MUTED.name())
        self.details.setText(
            "\n".join("%s    %s" % (i.name, _score_text(i)) for i in grade.items)
        )
        self.details.setVisible(False)
        self._col.addWidget(self.details)

        self._layout.addLayout(self._col, 1)

        current = grade.current
        score = QLabel("%.1f" % current if current is not None else "—")
        score.setFont(theme.font(13, QFont.Weight.DemiBold))
        if current is None:
            colour = theme.TEXT_MUTED
        elif current >= 90:
            colour = theme.OK
        elif current >= 60:
            colour = theme.TEXT
        else:
            colour = theme.DANGER
        score.setStyleSheet("color: %s;" % colour.name())
        self._layout.addWidget(score, 0, Qt.AlignmentFlag.AlignVCenter)

        self.setFixedHeight(58 if not grade.items else 74)

    def mouseReleaseEvent(self, event):  # noqa: N802
        if event.button() == Qt.MouseButton.LeftButton and self.grade.items:
            self._expanded = not self._expanded
            self.details.setVisible(self._expanded)
            base = 58 if not self.grade.items else 74
            extra = self.details.sizeHint().height() + 6 if self._expanded else 0
            self.setFixedHeight(base + extra)
            self.updateGeometry()
        super().mouseReleaseEvent(event)

    def paintEvent(self, event):  # noqa: N802
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        path = QPainterPath()
        path.addRoundedRect(QRectF(self.rect()).adjusted(0, 0, -0.5, -0.5), 10, 10)
        painter.fillPath(path, theme.BG_ROW)


def _score_text(item) -> str:
    if item.score is None:
        return "—"
    if item.points:
        return "%g/%g" % (item.score, item.points)
    return "%g" % item.score


class NoticeRow(QFrame):
    """One announcement from Canvas or AMS."""

    open_requested = Signal(str)
    detail_requested = Signal(object)

    def __init__(self, notice: Notice, unread: bool = False, parent=None):
        super().__init__(parent)
        self.notice = notice
        self.setFixedHeight(60)
        self.setAttribute(Qt.WidgetAttribute.WA_Hover, True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self._hover = False

        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 8, 12, 8)
        layout.setSpacing(8)

        dot = QLabel("●" if unread else " ")
        dot.setFont(theme.font(7))
        dot.setStyleSheet("color: %s;" % theme.ACCENT.name())
        dot.setFixedWidth(10)
        layout.addWidget(dot, 0, Qt.AlignmentFlag.AlignTop)

        col = QVBoxLayout()
        col.setSpacing(3)
        title = ElidedLabel(notice.title, theme.font(9, QFont.Weight.DemiBold), theme.TEXT)
        title.setToolTip(notice.title)
        col.addWidget(title)
        bits = [b for b in (notice.course, notice.source.upper()) if b]
        stamp = ""
        if notice.posted_at:
            local = notice.posted_at.astimezone().replace(tzinfo=None) if notice.posted_at.tzinfo else notice.posted_at
            stamp = "%d月%d日" % (local.month, local.day)
        if stamp:
            bits.append(stamp)
        meta = ElidedLabel(" · ".join(bits) or "公告", theme.font(7.5), theme.TEXT_MUTED)
        col.addWidget(meta)
        layout.addLayout(col, 1)

    def enterEvent(self, event):  # noqa: N802
        self._hover = True
        self.update()
        super().enterEvent(event)

    def leaveEvent(self, event):  # noqa: N802
        self._hover = False
        self.update()
        super().leaveEvent(event)

    def mouseReleaseEvent(self, event):  # noqa: N802
        if event.button() == Qt.MouseButton.LeftButton:
            if self.notice.body:
                self.detail_requested.emit(self.notice)
            elif self.notice.url:
                self.open_requested.emit(self.notice.url)
        super().mouseReleaseEvent(event)

    def paintEvent(self, event):  # noqa: N802
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        path = QPainterPath()
        path.addRoundedRect(QRectF(self.rect()).adjusted(0, 0, -0.5, -0.5), 10, 10)
        painter.fillPath(path, theme.BG_ROW_HOVER if self._hover else theme.BG_ROW)


class EmptyState(QWidget):
    def __init__(self, headline: str, hint: str = "", parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(32, 44, 32, 20)
        layout.setSpacing(8)
        # 这里不要给布局加 AlignHCenter：那会让换行标签拿到错误的宽度，
        # 高度按一行算，多出来的行直接压在上一行上。让标签自己撑满宽度、
        # 文字居中即可。
        layout.setAlignment(Qt.AlignmentFlag.AlignTop)

        title = QLabel(headline)
        title.setFont(theme.font(10))
        title.setWordWrap(True)
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title.setStyleSheet(f"color: {theme.TEXT_SOFT.name()};")
        layout.addWidget(title)

        if hint:
            body = QLabel(hint)
            body.setFont(theme.font(8))
            body.setWordWrap(True)
            body.setAlignment(Qt.AlignmentFlag.AlignCenter)
            body.setStyleSheet(f"color: {theme.TEXT_MUTED.name()};")
            layout.addWidget(body)
        layout.addStretch(1)


class SectionHeader(QLabel):
    def __init__(self, text: str, parent=None):
        super().__init__(text, parent)
        self.setFont(theme.font(8))
        self.setFixedHeight(24)
        self.setContentsMargins(6, 6, 0, 0)
        self.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        self.setStyleSheet(f"color: {theme.TEXT_MUTED.name()}; letter-spacing: 1px;")


def raise_above_panel(widget):
    """面板与悬浮球是 HWND_TOPMOST，普通子对话框会被压在下面。

    给对话框加置顶标志，并在显示时提到最前。
    """
    widget.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint, True)
    return widget


def warn_on_top(parent, title: str, text: str) -> None:
    """QMessageBox 也走同一条规则，否则警告框会藏在面板后面。"""
    box = QMessageBox(QMessageBox.Icon.Warning, title, text,
                      QMessageBox.StandardButton.Ok, parent)
    raise_above_panel(box)
    box.exec()


# ------------------------------------------------------------ remind dialog
class RemindDialog(QDialog):
    """自己挑日期和时间，比「30 分钟后」精确。"""

    def __init__(self, parent=None, when: datetime | None = None):
        super().__init__(parent)
        raise_above_panel(self)
        self.setWindowTitle(t("remind.title"))
        self.setModal(True)
        self.setMinimumWidth(300)
        self.setStyleSheet(
            "QDialog { background: __CARD__; }"
            "QLabel { color: __TEXT__; }"
            "QDateTimeEdit { color: __TEXT__; background: __INK14__;"
            " border: 1px solid __INK30__; border-radius: 8px; padding: 6px 8px; }"
            "QDateTimeEdit::drop-down { border: none; width: 18px; }"
            "QCalendarWidget QWidget { color: __TEXT__; background: __CARD__; }"
            "QCalendarWidget QAbstractItemView { color: __TEXT__; background: __CARD__;"
            " selection-background-color: __ACCENT__; }"
        )

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 18, 20, 16)
        layout.setSpacing(10)

        title = QLabel(t("remind.title"))
        title.setFont(theme.font(10, QFont.Weight.DemiBold))
        layout.addWidget(title)

        now = datetime.now().replace(second=0, microsecond=0)
        base = when or (now + timedelta(hours=1))
        self.edit = QDateTimeEdit(self)
        self.edit.setCalendarPopup(True)
        self.edit.setDisplayFormat("yyyy-MM-dd  HH:mm")
        self.edit.setMinimumDateTime(QDateTime(now).addSecs(60))
        self.edit.setDateTime(QDateTime(base))
        self.edit.setFont(theme.font(9.5))
        layout.addWidget(self.edit)

        hint = QLabel(t("remind.hint"))
        hint.setWordWrap(True)
        hint.setFont(theme.font(7.5))
        hint.setStyleSheet("color: __MUTED__;")
        layout.addWidget(hint)

        buttons = QHBoxLayout()
        buttons.setSpacing(8)
        buttons.addStretch(1)
        cancel = QPushButton(t("common.cancel"))
        cancel.setFixedHeight(28)
        cancel.setCursor(Qt.CursorShape.PointingHandCursor)
        cancel.clicked.connect(self.reject)
        ok = QPushButton(t("remind.ok"))
        ok.setFixedHeight(28)
        ok.setCursor(Qt.CursorShape.PointingHandCursor)
        ok.setDefault(True)
        ok.setStyleSheet(
            "QPushButton { color: white; background: #4A90FF; border: none;"
            " border-radius: 14px; padding: 0 18px; }"
            "QPushButton:hover { background: #60A0FF; }"
        )
        ok.clicked.connect(self.accept)
        buttons.addWidget(cancel)
        buttons.addWidget(ok)
        layout.addLayout(buttons)

    def showEvent(self, event) -> None:
        super().showEvent(event)
        self.raise_()
        self.activateWindow()

    def when(self) -> datetime | None:
        value = self.edit.dateTime().toPython()
        return value if value > datetime.now() else None


# -------------------------------------------------------------- file picker
class FilePickRow(QFrame):
    """提交页的一行：选文件 / 文件名 / 删除。空行默认不显示右边的 ×。"""

    changed = Signal()
    remove_requested = Signal(object)

    def __init__(self, start_dir: str = "", parent=None):
        super().__init__(parent)
        self.path: Path | None = None
        self._start_dir = start_dir
        self.setFixedHeight(42)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(10, 6, 8, 6)
        layout.setSpacing(10)

        self.choose = QPushButton(t("submit.choose"))
        self.choose.setFont(theme.font(8))
        self.choose.setFixedHeight(26)
        self.choose.setCursor(Qt.CursorShape.PointingHandCursor)
        self.choose.setStyleSheet(
            "QPushButton { color: __TEXT__; background: __INK20__;"
            " border: 1px solid __INK30__; border-radius: 13px; padding: 0 14px; }"
            "QPushButton:hover { background: __INK36__; }"
        )
        self.choose.clicked.connect(self.pick)
        layout.addWidget(self.choose, 0)

        self.name = ElidedLabel(t("submit.empty"), theme.font(8.5), theme.TEXT_MUTED)
        layout.addWidget(self.name, 1)

        self.remove_btn = QPushButton("×")
        self.remove_btn.setFixedSize(22, 22)
        self.remove_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.remove_btn.setToolTip(t("common.cancel"))
        self.remove_btn.setStyleSheet(
            "QPushButton { color: __TEXT__; background: transparent;"
            " border: none; font-size: 15px; }"
            "QPushButton:hover { color: white; background: __INK26__;"
            " border-radius: 11px; }"
        )
        self.remove_btn.setVisible(False)
        self.remove_btn.clicked.connect(lambda: self.remove_requested.emit(self))
        layout.addWidget(self.remove_btn, 0)

    def set_path(self, path) -> None:
        """按钮选择和拖拽进来都走这里。"""
        self.path = Path(path)
        size_kb = max(1, self.path.stat().st_size // 1024) if self.path.exists() else 0
        self.name.setText("%s（%d KB）" % (self.path.name, size_kb))
        self.name._color = theme.TEXT
        self.name.setToolTip(str(self.path))
        self.remove_btn.setVisible(True)
        self.changed.emit()

    def pick(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, t("submit.pick_title"), self._start_dir)
        if path:
            self.set_path(path)

    def clear(self) -> None:
        self.path = None
        self.name.setText(t("submit.empty"))
        self.name._color = theme.TEXT_MUTED
        self.name.setToolTip("")
        self.remove_btn.setVisible(False)
        self.changed.emit()

    def paintEvent(self, event) -> None:  # noqa: N802
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        path = QPainterPath()
        path.addRoundedRect(QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5), 9, 9)
        painter.fillPath(path, theme.BG_ROW)


# ------------------------------------------------------------- drop target
class DropArea(QWidget):
    """接受从资源管理器拖进来的文件；拖到上面时描一圈虚线。"""

    files_dropped = Signal(list)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAcceptDrops(True)
        self._hot = False

    @staticmethod
    def _local_files(mime) -> list[str]:
        if not mime.hasUrls():
            return []
        out = []
        for url in mime.urls():
            if not url.isLocalFile():
                continue
            path = Path(url.toLocalFile())
            if path.is_file():
                out.append(str(path))
        return out

    def dragEnterEvent(self, event) -> None:  # noqa: N802
        if self._local_files(event.mimeData()):
            event.acceptProposedAction()
            self._hot = True
            self.update()
        else:
            event.ignore()

    def dragMoveEvent(self, event) -> None:  # noqa: N802
        if self._local_files(event.mimeData()):
            event.acceptProposedAction()

    def dragLeaveEvent(self, event) -> None:  # noqa: N802
        self._hot = False
        self.update()

    def dropEvent(self, event) -> None:  # noqa: N802
        files = self._local_files(event.mimeData())
        self._hot = False
        self.update()
        if files:
            event.acceptProposedAction()
            self.files_dropped.emit(files)

    def paintEvent(self, event) -> None:  # noqa: N802
        if not self._hot:
            return
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        pen = QPen(theme.ACCENT)
        pen.setWidth(2)
        pen.setStyle(Qt.PenStyle.DashLine)
        painter.setPen(pen)
        painter.drawRoundedRect(QRectF(self.rect()).adjusted(3, 3, -3, -3), 12, 12)
