"""Colours, fonts and small painting helpers shared by the widgets."""

from __future__ import annotations

import re

from PySide6.QtGui import QColor, QFont

# ------------------------------------------------------------------ palette
BG_DEEP = QColor(16, 20, 28, 246)
BG_CARD = QColor(22, 27, 37, 248)
BG_ROW = QColor(255, 255, 255, 10)
BG_ROW_HOVER = QColor(255, 255, 255, 18)
BORDER = QColor(255, 255, 255, 26)
BORDER_SOFT = QColor(255, 255, 255, 14)

TEXT = QColor(237, 241, 248)
TEXT_SOFT = QColor(178, 188, 204)
TEXT_MUTED = QColor(126, 138, 158)

ACCENT = QColor(74, 144, 255)
ACCENT_2 = QColor(48, 200, 178)
DANGER = QColor(255, 92, 108)
WARN = QColor(255, 176, 32)
OK = QColor(60, 200, 122)

COURSE_COLORS = [
    QColor(74, 144, 255),
    QColor(48, 200, 178),
    QColor(168, 130, 255),
    QColor(255, 159, 67),
    QColor(255, 107, 149),
    QColor(96, 205, 255),
    QColor(190, 220, 90),
    QColor(255, 196, 87),
]


# ------------------------------------------------------------------ modes
DARK = {
    "BG_DEEP": QColor(16, 20, 28, 246),
    "BG_CARD": QColor(22, 27, 37, 248),
    "BG_ROW": QColor(255, 255, 255, 10),
    "BG_ROW_HOVER": QColor(255, 255, 255, 18),
    "BORDER": QColor(255, 255, 255, 26),
    "BORDER_SOFT": QColor(255, 255, 255, 14),
    "TEXT": QColor(237, 241, 248),
    "TEXT_SOFT": QColor(178, 188, 204),
    "TEXT_MUTED": QColor(126, 138, 158),
    "INK": "255,255,255",
}

LIGHT = {
    "BG_DEEP": QColor(247, 249, 252, 248),
    "BG_CARD": QColor(255, 255, 255, 250),
    "BG_ROW": QColor(20, 26, 38, 8),
    "BG_ROW_HOVER": QColor(20, 26, 38, 14),
    "BORDER": QColor(20, 26, 38, 30),
    "BORDER_SOFT": QColor(20, 26, 38, 16),
    "TEXT": QColor(26, 32, 44),
    "TEXT_SOFT": QColor(54, 64, 80),
    "TEXT_MUTED": QColor(92, 104, 122),
    "INK": "24,30,40",
}

MODE = "dark"


def system_is_light() -> bool:
    """系统是否浅色。Windows 读注册表，其它平台看 Qt 的配色提示。"""
    import sys
    if sys.platform.startswith("win"):
        try:
            import winreg
            key = winreg.OpenKey(
                winreg.HKEY_CURRENT_USER,
                r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize")
            value, _ = winreg.QueryValueEx(key, "AppsUseLightTheme")
            return bool(value)
        except OSError:
            return False
    try:
        from PySide6.QtGui import QGuiApplication
        return QGuiApplication.styleHints().colorScheme() is not None and             str(QGuiApplication.styleHints().colorScheme()).endswith("Light")
    except Exception:
        return False


def apply_mode(mode: str = "system") -> str:
    """切换配色。返回实际生效的 'light' / 'dark'。"""
    global MODE
    mode = (mode or "system").lower()
    if mode == "system":
        mode = "light" if system_is_light() else "dark"
    palette = LIGHT if mode == "light" else DARK
    globals().update(palette)
    MODE = mode
    return mode


def apply_palette(app) -> None:
    """给没写样式的控件也配上对应的底色/文字色，浅色模式才不会一块黑一块白。"""
    from PySide6.QtGui import QPalette
    palette = QPalette()
    light = is_light()
    window = QColor(247, 249, 252) if light else QColor(20, 25, 34)
    base = QColor(255, 255, 255) if light else QColor(16, 20, 28)
    text = QColor(26, 32, 44) if light else QColor(237, 241, 248)
    palette.setColor(QPalette.ColorRole.Window, window)
    palette.setColor(QPalette.ColorRole.Base, base)
    palette.setColor(QPalette.ColorRole.AlternateBase, base)
    palette.setColor(QPalette.ColorRole.WindowText, text)
    palette.setColor(QPalette.ColorRole.Text, text)
    palette.setColor(QPalette.ColorRole.Button, window)
    palette.setColor(QPalette.ColorRole.ButtonText, text)
    palette.setColor(QPalette.ColorRole.ToolTipBase, base)
    palette.setColor(QPalette.ColorRole.ToolTipText, text)
    app.setPalette(palette)


def is_light() -> bool:
    return MODE == "light"


def nav_text() -> str:
    """侧栏未选中项的文字色：深色模式浅灰，浅色模式深灰。"""
    return "rgba(56,68,86,215)" if is_light() else "rgba(200,210,226,190)"


def ink(alpha: int) -> str:
    """深色模式是白，浅色模式是近黑——就是原来那些 rgba(255,255,255,N)。"""
    return "rgba(%s,%d)" % (globals().get("INK", DARK["INK"]), alpha)


_INK_TOKEN = re.compile(r"__INK(\d+)__")


def render_qss(qss: str) -> str:
    """把样式表里的 __INK16__ / __TEXT__ 换成当前配色的颜色。"""
    if qss is None:
        return qss
    if "__NAV__" in qss:
        qss = qss.replace("__NAV__", nav_text())
    if "__TEXT__" in qss:
        qss = qss.replace("__TEXT__", TEXT.name())
    if "__CARD__" in qss:
        qss = qss.replace("__CARD__", BG_CARD.name())
    if "__MUTED__" in qss:
        qss = qss.replace("__MUTED__", TEXT_MUTED.name())
    if "__SOFT__" in qss:
        qss = qss.replace("__SOFT__", TEXT_SOFT.name())
    if "__ACCENT__" in qss:
        qss = qss.replace("__ACCENT__", ACCENT.name())
    if "__INK" in qss:
        qss = _INK_TOKEN.sub(lambda m: ink(int(m.group(1))), qss)
    return qss


_QSS_HOOKED = False


def install_qss_hook() -> None:
    """让所有 setStyleSheet 自动过一遍 render_qss，浅色/深色切换才不用改每个控件。"""
    global _QSS_HOOKED
    if _QSS_HOOKED:
        return
    from PySide6.QtWidgets import QWidget
    original = QWidget.setStyleSheet

    def patched(self, sheet):  # noqa: ANN001
        original(self, render_qss(sheet) if isinstance(sheet, str) else sheet)

    QWidget.setStyleSheet = patched
    _QSS_HOOKED = True


def course_color(seed: int | str) -> QColor:
    key = str(seed)
    value = sum((i + 1) * ord(ch) for i, ch in enumerate(key))
    return COURSE_COLORS[value % len(COURSE_COLORS)]


def font(size: float = 9, weight: QFont.Weight = QFont.Weight.Normal) -> QFont:
    f = QFont("Microsoft YaHei UI", int(round(size)))
    f.setWeight(weight)
    f.setStyleStrategy(QFont.StyleStrategy.PreferAntialias)
    return f


def rgba(color: QColor, alpha: int) -> str:
    return f"rgba({color.red()},{color.green()},{color.blue()},{alpha})"


# --------------------------------------------------------------------- QSS
SCROLL_QSS = """
QScrollArea { background: transparent; border: none; }
QScrollBar:vertical {
    background: transparent; width: 6px; margin: 2px 0 2px 0;
}
QScrollBar::handle:vertical {
    background: rgba(255,255,255,40); border-radius: 3px; min-height: 28px;
}
QScrollBar::handle:vertical:hover { background: rgba(255,255,255,70); }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical { background: transparent; }
"""

BUTTON_QSS = """
QPushButton {
    color: %(text)s;
    background: rgba(255,255,255,16);
    border: 1px solid rgba(255,255,255,28);
    border-radius: 8px;
    padding: 5px 12px;
}
QPushButton:hover { background: rgba(255,255,255,30); }
QPushButton:pressed { background: rgba(255,255,255,12); }
QPushButton:disabled { color: rgba(255,255,255,60); }
QPushButton#primary {
    background: %(accent)s;
    border: none;
    color: white;
    font-weight: 600;
}
QPushButton#primary:hover { background: %(accent_hover)s; }
""" % {
    "text": "rgba(237,241,248,230)",
    "accent": "rgb(74,144,255)",
    "accent_hover": "rgb(96,160,255)",
}
