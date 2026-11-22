"""The floating ball: draggable, always on top, shows the pending count."""

from __future__ import annotations

import logging
import os
from pathlib import Path

from PySide6.QtCore import (
    QPoint, QPointF, QPropertyAnimation, QRectF, Qt, QTimer, Signal,
)
from PySide6.QtGui import (
    QColor, QFont, QLinearGradient, QPainter, QPainterPath, QPen, QPixmap, QRadialGradient,
)
from PySide6.QtWidgets import QApplication, QWidget

from . import theme

log = logging.getLogger("wsdock.pet")

SIZE = 62
PET_SIZE = 92          # 有立绘时的显示尺寸
STATE_FILES = ("idle", "hover", "syncing", "class", "urgent", "done", "error")
ICON_BALL = False


SKIN = ""          # "" = assets/pet 根目录；否则 assets/pet/<skin>/
CREST = False      # 校徽风格的矢量球（没有立绘目录）


def _app_icon_pixmap():
    from .. import paths as _paths
    path = _paths.bundle_dir() / "assets" / "app_icon.png"
    if not path.exists():
        return None
    pix = QPixmap(str(path))
    return None if pix.isNull() else pix


def pet_root() -> Path:
    override = os.environ.get("WESTLAKE_PET_DIR")
    if override:
        return Path(override)
    from .. import paths as _paths
    return _paths.bundle_dir() / "assets" / "pet"


def pet_dir() -> Path:
    if SKIN.startswith("user/"):
        from .. import paths as _paths
        return _paths.pet_user_dir() / SKIN[5:]
    root = pet_root()
    return root / SKIN if SKIN else root


def _crest_pixmap() -> QPixmap | None:
    """西湖校徽的白色剪影，缩放到圆球里用。"""
    from .. import paths as _paths
    path = _paths.bundle_dir() / "assets" / "brand_westlake_white.png"
    if not path.exists():
        return None
    pix = QPixmap(str(path))
    return pix if not pix.isNull() else None


def available_skins() -> list[str]:
    root = pet_root()
    if not root.is_dir():
        return []
    return sorted(p.name for p in root.iterdir()
                  if p.is_dir() and (p / "idle.png").exists())


class Ball(QWidget):
    clicked = Signal()
    context_requested = Signal(QPoint)
    hover_in = Signal()
    hover_out = Signal()
    moved = Signal()          # 被拖走/吸边之后，面板要跟着走

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
        self._images: dict[str, QPixmap] = {}
        self._pet_size = PET_SIZE
        self._load_skin()
        size = self._pet_size if (self._images or ICON_BALL) else SIZE
        self.setFixedSize(size, size)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setToolTip("Vesper Board")

        self._press_pos: QPoint | None = None
        self._drag_origin: QPoint | None = None
        self._dragging = False
        self._hover = False
        self._count = 0
        self._urgent = False
        self._online = True
        self._mode = "idle"
        self._pulse = 0.0
        self._badge_text: str | None = None
        self._glow = False          # 背后柔光，默认关
        self._badge_on = True       # 右上角红/黄点，Dock 按设置覆盖
        self._celebrate = False
        self._done_timer = QTimer(self)
        self._done_timer.setSingleShot(True)
        self._done_timer.setInterval(5000)
        self._done_timer.timeout.connect(self._end_celebrate)
        self._anim = QPropertyAnimation(self, b"pulse", self)
        self._anim.setDuration(420)

    # ----------------------------------------------------------------- skin
    def _load_skin(self) -> None:
        folder = pet_dir()
        if not folder.is_dir():
            log.warning("形象目录不存在：%s", folder)
            return
        for name in STATE_FILES:
            path = folder / ("%s.png" % name)
            if path.exists():
                pix = QPixmap(str(path))
                if not pix.isNull():
                    self._images[name] = pix
        if not self._images and SKIN:
            # 选了具体形象却一张图都没读到，才值得记一笔；默认圆球是正常配置。
            log.warning("形象目录里没有可用的 PNG：%s", folder)

    def set_skin(self, skin: str) -> None:
        global SKIN, CREST, ICON_BALL
        skin = skin or ""
        CREST = skin == "crest"          # 校徽球：没有素材，只是换个字
        ICON_BALL = skin == "icon"       # 晚星看板：用 APP 图标当球
        SKIN = "" if (CREST or ICON_BALL) else skin
        self.reload_skin()

    def reload_skin(self) -> None:
        self._images.clear()
        self._load_skin()
        if not self._images and SKIN:
            # 选中的形象目录被删/改名了：退回 APP 图标球，别留一个空球
            self.set_skin("icon")
            return
        size = self._pet_size if (self._images or ICON_BALL) else SIZE
        self.setFixedSize(size, size)
        self.update()

    def set_glow(self, on: bool) -> None:
        """背后柔光开关（默认关）。"""
        on = bool(on)
        if on != self._glow:
            self._glow = on
            self.update()

    def set_badge(self, on: bool) -> None:
        """右上角红/黄点开关（默认关）。"""
        on = bool(on)
        if on != self._badge_on:
            self._badge_on = on
            self.update()

    def set_pet_size(self, px: int) -> None:
        """立绘边长（64–128）。没有立绘时仍是矢量球的固定尺寸。"""
        self._pet_size = max(48, min(200, int(px)))
        size = self._pet_size if (self._images or ICON_BALL) else SIZE
        if size != self.width():
            self.setFixedSize(size, size)
        self.update()

    def current_state(self) -> str:
        if self._mode == "syncing":
            return "syncing"
        if self._mode == "class":
            return "class"
        if self._urgent:
            return "urgent"
        if not self._online:
            return "error"
        if self._hover and "hover" in self._images:
            return "hover"
        if self._celebrate:
            return "done"
        return "idle"

    def _end_celebrate(self) -> None:
        self._celebrate = False
        self.update()

    # ------------------------------------------------------------- properties
    def get_pulse(self) -> float:
        return self._pulse

    def set_pulse(self, value: float) -> None:
        self._pulse = float(value)
        self.update()

    pulse = property(get_pulse, set_pulse)

    def set_mode(self, mode: str) -> None:
        if mode != self._mode:
            self._mode = mode
            self.update()

    def set_state(self, count: int, urgent: bool, online: bool,
                  badge_text: str | None = None) -> None:
        prev = self._count
        changed = (count, urgent) != (self._count, self._urgent)
        self._count = max(0, int(count))
        self._urgent = bool(urgent)
        self._online = bool(online)
        self._badge_text = badge_text          # None = 用待交数量
        if prev > 0 and self._count == 0 and online:
            self._celebrate = True
            self._done_timer.start()
        self.update()
        if changed and self._count:
            self._anim.stop()
            self._anim.setStartValue(1.0)
            self._anim.setEndValue(0.0)
            self._anim.start()

    # ------------------------------------------------------------------ input
    def enterEvent(self, event):  # noqa: N802
        self._hover = True
        self.update()
        self.hover_in.emit()
        super().enterEvent(event)

    def leaveEvent(self, event):  # noqa: N802
        self._hover = False
        self.update()
        self.hover_out.emit()
        super().leaveEvent(event)

    def mousePressEvent(self, event):  # noqa: N802
        if event.button() == Qt.MouseButton.LeftButton:
            self._press_pos = event.globalPosition().toPoint()
            self._drag_origin = self.pos()
            self._dragging = False
        elif event.button() == Qt.MouseButton.RightButton:
            self.context_requested.emit(event.globalPosition().toPoint())
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):  # noqa: N802
        if self._press_pos is None or self._drag_origin is None:
            return
        if not (event.buttons() & Qt.MouseButton.LeftButton):
            return
        delta = event.globalPosition().toPoint() - self._press_pos
        if not self._dragging and delta.manhattanLength() > 4:
            self._dragging = True
        if self._dragging:
            self.move(self._drag_origin + delta)
            self.moved.emit()

    def mouseReleaseEvent(self, event):  # noqa: N802
        if event.button() != Qt.MouseButton.LeftButton:
            return
        was_dragging = self._dragging
        self._press_pos = None
        self._drag_origin = None
        self._dragging = False
        if was_dragging:
            self._snap_to_edge()
        else:
            self.clicked.emit()
        super().mouseReleaseEvent(event)

    def _snap_to_edge(self) -> None:
        screen = self.screen() or QApplication.primaryScreen()
        if screen is None:
            return
        area = screen.availableGeometry()
        margin = 8
        x, y = self.x(), self.y()
        if x - area.left() < margin:
            x = area.left() + margin
        if area.right() - (x + self.width()) < margin:
            x = area.right() - self.width() - margin
        y = max(area.top() + margin, min(y, area.bottom() - self.height() - margin))
        self.move(x, y)
        self.moved.emit()

    # --------------------------------------------------------------- painting
    def paintEvent(self, event):  # noqa: N802
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setRenderHint(QPainter.RenderHint.TextAntialiasing, True)

        cx, cy = self.width() / 2, self.height() / 2
        radius = self.width() / 2 - 4

        if self._glow:
            # soft glow, brighter on hover and right after a change
            glow_strength = 0.30 + (0.18 if self._hover else 0) + 0.45 * self._pulse
            glow = QRadialGradient(QPointF(cx, cy), radius + 8)
            base = theme.ACCENT
            glow.setColorAt(0.55, QColor(base.red(), base.green(), base.blue(), int(60 * glow_strength / 0.3)))
            glow.setColorAt(1.0, QColor(base.red(), base.green(), base.blue(), 0))
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(glow)
            painter.drawEllipse(QPointF(cx, cy), radius + 8, radius + 8)

        if ICON_BALL:
            icon = _app_icon_pixmap()
            if icon is not None:
                side = self.width() - 8
                scaled = icon.scaled(side, side, Qt.AspectRatioMode.KeepAspectRatio,
                                     Qt.TransformationMode.SmoothTransformation)
                painter.drawPixmap((self.width() - scaled.width()) // 2,
                                   (self.height() - scaled.height()) // 2, scaled)
                if self._badge_on and (self._count > 0 or self._badge_text):
                    self._paint_badge(painter)
                return

        state = self.current_state()
        picture = self._images.get(state) or self._images.get("idle")
        if picture is not None:
            scaled = picture.scaled(self.size(), Qt.AspectRatioMode.KeepAspectRatio,
                                    Qt.TransformationMode.SmoothTransformation)
            painter.drawPixmap((self.width() - scaled.width()) // 2,
                               self.height() - scaled.height(), scaled)
            if self._badge_on and (self._count > 0 or self._badge_text):
                self._paint_badge(painter)
            return

        circle = QRectF(cx - radius, cy - radius, radius * 2, radius * 2)
        body = QLinearGradient(0, circle.top(), 0, circle.bottom())
        if self._online:
            body.setColorAt(0, QColor(86, 158, 255, 250))
            body.setColorAt(1, QColor(44, 96, 214, 250))
        else:
            body.setColorAt(0, QColor(96, 104, 120, 235))
            body.setColorAt(1, QColor(60, 66, 78, 235))
        painter.setBrush(body)
        ring = QColor(255, 255, 255, 46)
        if self._mode == "class":
            ring = QColor(theme.ACCENT_2.red(), theme.ACCENT_2.green(), theme.ACCENT_2.blue(), 190)
        elif self._mode == "syncing":
            ring = QColor(theme.ACCENT.red(), theme.ACCENT.green(), theme.ACCENT.blue(), 170)
        painter.setPen(QPen(ring, 1.6 if self._mode != "idle" else 1.2))
        painter.drawEllipse(circle)

        # top highlight
        hi = QLinearGradient(0, circle.top(), 0, cy)
        hi.setColorAt(0, QColor(255, 255, 255, 60))
        hi.setColorAt(1, QColor(255, 255, 255, 0))
        painter.setBrush(hi)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawEllipse(QRectF(cx - radius + 5, cy - radius + 4, radius * 2 - 10, radius * 0.9))

        glyph = QFont("Microsoft YaHei UI", 15)
        glyph.setWeight(QFont.Weight.DemiBold)
        painter.setFont(glyph)
        painter.setPen(QPen(QColor(255, 255, 255, 240)))
        if CREST:
            pix = _crest_pixmap()
            if pix is not None:
                side = int(self.width() * 0.62)
                scaled = pix.scaled(side, side, Qt.AspectRatioMode.KeepAspectRatio,
                                    Qt.TransformationMode.SmoothTransformation)
                painter.drawPixmap((self.width() - scaled.width()) // 2,
                                   (self.height() - scaled.height()) // 2, scaled)
            else:
                painter.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, "W")
        else:
            painter.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, "西")

        if self._badge_on and (self._count > 0 or self._badge_text):
            self._paint_badge(painter)

    def _paint_badge(self, painter: QPainter) -> None:
        if self._badge_text is not None:
            text = self._badge_text
        else:
            text = str(self._count) if self._count <= 99 else "99+"
        compact = len(text) > 2
        colour = theme.DANGER if self._urgent else theme.WARN
        small = QFont("Microsoft YaHei UI", 6.5 if compact or self._count > 9 else 7)
        small.setWeight(QFont.Weight.Bold)
        painter.setFont(small)
        width = max(18, painter.fontMetrics().horizontalAdvance(text) + 10)
        rect = QRectF(self.width() - width - 3, 2, width, 18)
        painter.setPen(QPen(QColor(20, 24, 32, 220), 2))
        painter.setBrush(colour)
        painter.drawRoundedRect(rect, 9, 9)
        painter.setPen(QPen(QColor(255, 255, 255, 245)))
        painter.drawText(rect, Qt.AlignmentFlag.AlignCenter, text)
