"""形象切换：网格卡片，一行五张，每个角色可以有多套换装。

角色和换装的清单在 wsdock/skins.py，这里只负责画卡片。暂时没有素材的角色
也会占一个位置（灰掉、标「暂无」），以后补上素材自动变成可点。
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QRectF, Qt, Signal
from PySide6.QtGui import QColor, QFont, QLinearGradient, QPainter, QPen, QPixmap
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QVBoxLayout, QWidget

from ..i18n import LANG, t
from ..skins import all_characters
from . import theme

CARD_W = 66
CARD_H = 96
PAD = 8
PER_ROW = 5


def _crest_pix() -> QPixmap | None:
    from .. import paths as _paths
    path = _paths.bundle_dir() / "assets" / "brand_westlake_white.png"
    if not path.exists():
        return None
    pix = QPixmap(str(path))
    return pix if not pix.isNull() else None


def _emblem_thumb(key: str) -> QPixmap | None:
    from .. import paths as _paths
    name = key[:-6] if key.endswith("_crest") else key
    path = _paths.bundle_dir() / "assets" / "emblems" / (name + ".png")
    if not path.exists():
        return None
    pix = QPixmap(str(path))
    if pix.isNull():
        return None
    return pix.scaled(int((CARD_W - PAD * 2) * 0.82), int((CARD_H - 40) * 0.82),
                      Qt.AspectRatioMode.KeepAspectRatio,
                      Qt.TransformationMode.SmoothTransformation)


def _icon_thumb() -> QPixmap | None:
    from .. import paths as _paths
    path = _paths.bundle_dir() / "assets" / "app_icon.png"
    if not path.exists():
        return None
    pix = QPixmap(str(path))
    if pix.isNull():
        return None
    return pix.scaled(CARD_W - PAD * 2, CARD_H - 40, Qt.AspectRatioMode.KeepAspectRatio,
                      Qt.TransformationMode.SmoothTransformation)


def _idle_thumb(folder: Path) -> QPixmap | None:
    path = folder / "idle.png"
    if not path.exists():
        return None
    pix = QPixmap(str(path))
    if pix.isNull():
        return None
    return pix.scaled(CARD_W - PAD * 2, CARD_H - 40, Qt.AspectRatioMode.KeepAspectRatio,
                      Qt.TransformationMode.SmoothTransformation)


class SkinCard(QFrame):
    picked = Signal(str)

    def __init__(self, key: str, title: str, subtitle: str = "",
                 pixmap: QPixmap | None = None, enabled: bool = True,
                 glyph: str = "西", parent=None):
        super().__init__(parent)
        self._key = key
        self._title = title
        self._subtitle = subtitle
        self._pix = pixmap
        self._glyph = glyph
        self._enabled = enabled
        self._selected = False
        self.setFixedSize(CARD_W, CARD_H)
        self.setCursor(Qt.CursorShape.PointingHandCursor if enabled
                       else Qt.CursorShape.ForbiddenCursor)
        self.setToolTip("%s %s" % (title, subtitle) if subtitle else title)

    def set_selected(self, on: bool) -> None:
        if self._selected != on:
            self._selected = on
            self.update()

    def mousePressEvent(self, event):  # noqa: N802
        if self._enabled and event.button() == Qt.MouseButton.LeftButton:
            self.picked.emit(self._key)
        super().mousePressEvent(event)

    def paintEvent(self, event):  # noqa: N802
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setOpacity(1.0 if self._enabled else 0.42)
        rect = QRectF(0.75, 0.75, self.width() - 1.5, self.height() - 1.5)

        fill = QColor(74, 144, 255, 34) if self._selected else QColor(255, 255, 255, 10)
        painter.setBrush(fill)
        painter.setPen(QPen(theme.ACCENT if self._selected else QColor(255, 255, 255, 26),
                            1.6 if self._selected else 1.0))
        painter.drawRoundedRect(rect, 11, 11)

        box = QRectF(PAD, PAD, self.width() - PAD * 2, self.height() - 44)
        if self._pix is not None:
            painter.drawPixmap(
                int(box.center().x() - self._pix.width() / 2),
                int(box.bottom() - self._pix.height()),
                self._pix,
            )
        elif self._enabled or self._key in ("", "crest", "icon"):   # 矢量圆球
            d = min(box.width(), box.height()) * 0.72
            circle = QRectF(box.center().x() - d / 2, box.center().y() - d / 2, d, d)
            body = QLinearGradient(0, circle.top(), 0, circle.bottom())
            body.setColorAt(0, QColor(86, 158, 255, 250))
            body.setColorAt(1, QColor(44, 96, 214, 250))
            painter.setBrush(body)
            painter.setPen(QPen(QColor(255, 255, 255, 46), 1.2))
            painter.drawEllipse(circle)
            painter.setPen(QPen(QColor(255, 255, 255, 240)))
            font = QFont("Microsoft YaHei UI", 11)
            font.setWeight(QFont.Weight.DemiBold)
            painter.setFont(font)
            if self._glyph == "W":
                crest = _crest_pix()
                if crest is not None:
                    side = int(d * 0.66)
                    sc = crest.scaled(side, side, Qt.AspectRatioMode.KeepAspectRatio,
                                      Qt.TransformationMode.SmoothTransformation)
                    painter.drawPixmap(int(circle.center().x() - sc.width() / 2),
                                       int(circle.center().y() - sc.height() / 2), sc)
                else:
                    painter.drawText(circle, Qt.AlignmentFlag.AlignCenter, "W")
            else:
                painter.drawText(circle, Qt.AlignmentFlag.AlignCenter, self._glyph)
        else:                                               # 暂无素材
            painter.setPen(QPen(QColor(255, 255, 255, 60), 1.2, Qt.PenStyle.DashLine))
            d = min(box.width(), box.height()) * 0.62
            circle = QRectF(box.center().x() - d / 2, box.center().y() - d / 2, d, d)
            painter.drawEllipse(circle)

        painter.setOpacity(1.0 if self._enabled else 0.5)
        painter.setFont(theme.font(7))
        painter.setPen(QPen(theme.TEXT_SOFT))
        painter.drawText(QRectF(0, self.height() - 34, self.width(), 16),
                         Qt.AlignmentFlag.AlignCenter, self._title)
        if self._subtitle:
            painter.setFont(theme.font(6))
            painter.setPen(QPen(theme.TEXT_MUTED))
            painter.drawText(QRectF(0, self.height() - 18, self.width(), 14),
                             Qt.AlignmentFlag.AlignCenter, self._subtitle)


class SkinPicker(QWidget):
    """一行一个角色，角色的换装横着排在右边。

    key 为 "" 默认球、"crest" 校徽球，其余是素材目录名。
    """

    changed = Signal(str)

    def __init__(self, current: str = "", parent=None):
        super().__init__(parent)
        self._current = current
        self._cards: dict[str, SkinCard] = {}
        self._col = QVBoxLayout(self)
        self._col.setContentsMargins(0, 0, 0, 0)
        self._col.setSpacing(6)
        self.reload()

    def reload(self) -> None:
        """重扫一遍角色清单（导入新形象后调用）。"""
        while self._col.count():
            item = self._col.takeAt(0)
            w = item.widget()
            if w is not None:
                w.deleteLater()
            elif item.layout() is not None:
                lay = item.layout()
                while lay.count():
                    sub = lay.takeAt(0)
                    if sub.widget() is not None:
                        sub.widget().deleteLater()
        self._cards.clear()

        from .ball import pet_root
        from .. import paths as _paths

        root = pet_root()
        for ch in all_characters():
            row_widget = QWidget()
            row = QHBoxLayout(row_widget)
            row.setContentsMargins(0, 0, 0, 0)
            row.setSpacing(6)
            name = QLabel(ch.en if LANG == "en" else ch.zh)
            name.setFont(theme.font(8, QFont.Weight.DemiBold))
            name.setFixedWidth(64)
            name.setStyleSheet("color: %s;" % theme.TEXT_SOFT.name())
            row.addWidget(name)

            if ch.empty:
                soon = QLabel(t("set.skin_soon"))
                soon.setFont(theme.font(7.5))
                soon.setStyleSheet("color: %s;" % theme.TEXT_MUTED.name())
                row.addWidget(soon)
            else:
                for v in ch.variants:
                    if v.kind == "skin":
                        folder = (_paths.pet_user_dir() / v.key[5:]
                                  if v.key.startswith("user/") else root / v.key)
                    else:
                        folder = None
                    thumb = _idle_thumb(folder) if folder is not None else None
                    if v.kind == "icon":
                        thumb = _icon_thumb()
                    elif v.kind == "emblem":
                        thumb = _emblem_thumb(v.key)
                    glyph = "W" if v.key == "crest" else "西"
                    card = SkinCard(v.key, v.en if LANG == "en" else v.zh, "", thumb, True, glyph)
                    card.picked.connect(self._pick)
                    self._cards[v.key] = card
                    row.addWidget(card)
            row.addStretch(1)
            self._col.addWidget(row_widget)

        for k, card in self._cards.items():
            card.set_selected(k == self._current)

    def _pick(self, key: str) -> None:
        if key == self._current:
            return
        self.set_current(key)
        self.changed.emit(key)

    def set_current(self, key: str) -> None:
        self._current = key
        for k, card in self._cards.items():
            card.set_selected(k == key)

    def current(self) -> str:
        return self._current
