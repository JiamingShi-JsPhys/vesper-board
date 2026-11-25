"""Settings live inside the panel, not in a separate dialog window."""

from __future__ import annotations

import logging
import re
import shutil
from pathlib import Path

from PySide6.QtCore import Qt, QThread, QUrl, Signal
from PySide6.QtGui import QDesktopServices
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QApplication, QCheckBox, QComboBox, QFileDialog, QFrame, QGridLayout,
    QHBoxLayout, QLabel, QLineEdit, QListWidget, QMessageBox, QPushButton,
    QSlider, QSpinBox, QStackedWidget, QVBoxLayout, QWidget,
)

from .. import paths, security, session as session_store
from ..ams import AmsClient, AmsError
from ..autostart import is_enabled as autostart_enabled, set_enabled as set_autostart
from ..canvas import CanvasClient, CanvasError
from ..i18n import t
from ..settings import Settings
from ..version import VERSION, version_line
from . import theme
from .widgets import warn_on_top
from .skin_picker import SkinPicker

RELEASES_URL = "https://github.com/JiamingShi-JsPhys/vesper-board/releases"
UPDATE_API = "https://api.github.com/repos/JiamingShi-JsPhys/vesper-board/releases/latest"


def _version_tuple(text: str) -> tuple[int, ...]:
    nums = re.findall(r"\d+", str(text))[:3]
    return tuple(int(x) for x in nums) or (0,)


class _UpdateCheck(QThread):
    """点「检查更新」时查一次版本号（不后台常驻）。

    国内网络下 api.github.com 经常 403/限流，所以按这个顺序试：
    1. raw.githubusercontent 上的 version.json（发版时写入，最权威）
    2. jsDelivr 镜像
    3. github.com/releases/latest 的 302 跳转（Location 里带 tag，不限流）
    4. releases.atom 的条目标题
    5. GitHub API 只做最后兜底
    """

    done = Signal(bool, str, str)      # ok, version, url

    ENDPOINTS = (
        "https://raw.githubusercontent.com/JiamingShi-JsPhys/vesper-board/main/version.json",
        "https://cdn.jsdelivr.net/gh/JiamingShi-JsPhys/vesper-board@main/version.json",
    )
    LATEST_URL = "https://github.com/JiamingShi-JsPhys/vesper-board/releases/latest"
    ATOM_URL = "https://github.com/JiamingShi-JsPhys/vesper-board/releases.atom"

    def run(self) -> None:             # noqa: D102 - QThread entry
        import requests
        headers = {"User-Agent": "VesperBoard/" + VERSION}
        for url in self.ENDPOINTS:
            try:
                resp = requests.get(url, timeout=6, headers=headers)
                if resp.status_code != 200:
                    continue
                data = resp.json() if resp.content else {}
                tag = str(data.get("version") or "").lstrip("vV")
                if tag:
                    self.done.emit(True, tag, str(data.get("url") or RELEASES_URL))
                    return
            except Exception:
                continue
        # releases/latest 会 302 到 /releases/tag/vX.Y.Z
        try:
            resp = requests.get(self.LATEST_URL, timeout=8, headers=headers,
                                allow_redirects=False)
            loc = resp.headers.get("Location") or resp.url or ""
            m = re.search(r"/tag/([^/?#]+)", loc)
            if m:
                self.done.emit(True, m.group(1).lstrip("vV"), RELEASES_URL)
                return
        except Exception:
            pass
        try:
            resp = requests.get(self.ATOM_URL, timeout=8, headers=headers)
            m = re.search(r"<entry>.*?<title>([^<]+)</title>", resp.text or "", re.S)
            if m:
                nums = re.search(r"\d+\.\d+(?:\.\d+)?", m.group(1))
                if nums:
                    self.done.emit(True, nums.group(0), RELEASES_URL)
                    return
        except Exception:
            pass
        try:
            resp = requests.get(UPDATE_API, timeout=6, headers={
                "Accept": "application/vnd.github+json",
                "User-Agent": "VesperBoard/" + VERSION,
            })
            data = resp.json() if resp.content else {}
            tag = str(data.get("tag_name") or "").lstrip("vV")
            url = str(data.get("html_url") or RELEASES_URL)
            self.done.emit(bool(tag), tag, url)
        except Exception:
            self.done.emit(False, "", RELEASES_URL)


try:
    from .login import LoginWindow
    WEB_LOGIN = True
except Exception:                       # pragma: no cover - env dependent
    LoginWindow = None                  # type: ignore[assignment]
    WEB_LOGIN = False

LEVELS = [("top", "level.top"), ("normal", "level.normal"), ("desktop", "level.desktop")]


def _caption(text: str) -> QLabel:
    label = QLabel(text)
    label.setFont(theme.font(8.5, QFont.Weight.DemiBold))
    label.setStyleSheet("color: __MUTED__; padding-top: 6px;")
    return label


def _hint(text: str = "") -> QLabel:
    label = QLabel(text)
    label.setFont(theme.font(7.5))
    label.setWordWrap(True)
    label.setStyleSheet(f"color: {theme.TEXT_MUTED.name()};")
    return label


class SettingsPage(QWidget):
    back_requested = Signal()
    changed = Signal()             # polling interval / window level / autostart
    logged_in = Signal(str)        # "canvas" | "ams"
    export_requested = Signal()
    language_changed = Signal(str)
    logged_out = Signal(str)

    def __init__(self, settings: Settings, parent=None):
        super().__init__(parent)
        self.settings = settings

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(10)
        page = root                     # 外层；每进一个分区 root 就换成卡片内部布局

        body = QHBoxLayout()
        body.setSpacing(14)
        self.nav = QListWidget()
        self.nav.setFixedWidth(104)
        self.nav.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.nav.setSpacing(2)
        self.nav.setTextElideMode(Qt.TextElideMode.ElideRight)
        self.nav.setStyleSheet(
            "QListWidget { background: __INK6__; border: none;"
            " border-radius: 10px; padding: 4px; color: %s; }"
            "QListWidget::item { height: 28px; border-radius: 7px; padding-left: 9px; }"
            "QListWidget::item:selected { background: rgba(74,144,255,170); color: white; }"
            "QListWidget::item:hover { background: __INK12__; }"
            % theme.TEXT_SOFT.name()
        )
        self.stack = QStackedWidget()
        self.nav.currentRowChanged.connect(self.stack.setCurrentIndex)
        body.addWidget(self.nav)
        body.addWidget(self.stack, 1)
        root.addLayout(body, 1)

        # ---------------------------------------------------------- 账号
        root = self._page(t("set.account"))
        self.account_status = _hint()
        root.addWidget(self.account_status)

        row_acc = QHBoxLayout()
        row_acc.setSpacing(8)
        self.login_btn = QPushButton(t("set.login"))
        self.login_btn.setFixedHeight(28)
        self.login_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.login_btn.setFont(theme.font(8))
        self.login_btn.setStyleSheet(
            "QPushButton { color: white; background: rgba(74,144,255,190); border: none;"
            " border-radius: 14px; padding: 0 16px; }"
            "QPushButton:hover { background: rgba(96,160,255,235); }"
        )
        self.login_btn.clicked.connect(self._login_any)
        row_acc.addWidget(self.login_btn)

        self.test_btn = QPushButton(t("set.test"))
        self.test_btn.setFixedHeight(28)
        self.test_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.test_btn.setFont(theme.font(8))
        self.test_btn.setStyleSheet(
            "QPushButton { color: __TEXT__; background: __INK16__;"
            " border: 1px solid __INK22__; border-radius: 14px; padding: 0 12px; }"
            "QPushButton:hover { background: __INK32__; }"
        )
        self.test_btn.clicked.connect(self._test_any)
        row_acc.addWidget(self.test_btn)

        self.logout_btn = QPushButton(t("set.logout"))
        self.logout_btn.setFixedHeight(28)
        self.logout_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.logout_btn.setFont(theme.font(8))
        self.logout_btn.setStyleSheet(
            "QPushButton { color: rgba(255,140,150,210); background: transparent;"
            " border: 1px solid rgba(255,120,130,60); border-radius: 14px; padding: 0 12px; }"
            "QPushButton:hover { background: rgba(255,90,100,30); }"
        )
        self.logout_btn.clicked.connect(self._logout_any)
        row_acc.addWidget(self.logout_btn)
        row_acc.addStretch(1)
        root.addLayout(row_acc)

        self.account_msg = _hint()
        root.addWidget(self.account_msg)

        # 只有「用浏览器登录」时才需要手动粘贴
        self.canvas_token = QLineEdit(security.load_secret(paths.canvas_token_file()))
        self.canvas_token.setEchoMode(QLineEdit.EchoMode.Password)
        self.canvas_token.setPlaceholderText(t("set.token_hint"))
        self.canvas_token.setFixedHeight(26)
        self.canvas_token.setStyleSheet(self._edit_qss())
        self.canvas_token.editingFinished.connect(self._save_canvas_token)
        root.addWidget(self.canvas_token)

        self.ams_session = QLineEdit(session_store.load_ams_cookies().get("SESSION", ""))
        self.ams_session.setEchoMode(QLineEdit.EchoMode.Password)
        self.ams_session.setPlaceholderText(t("set.session_hint"))
        self.ams_session.setFixedHeight(26)
        self.ams_session.setStyleSheet(self._edit_qss())
        self.ams_session.editingFinished.connect(self._save_ams_session)
        root.addWidget(self.ams_session)

        # ------------------------------------------------------------ 显示
        root = self._page(t("set.display"))
        self.show_older = QCheckBox(t("set.show_older"))
        self.show_far = QCheckBox(t("set.show_far"))
        self.show_reminders = QCheckBox(t("set.show_reminders"))
        for box in (self.show_older, self.show_far, self.show_reminders):
            box.setFont(theme.font(8))
            box.setStyleSheet("QCheckBox { color: %s; }" % theme.TEXT_SOFT.name())
            box.toggled.connect(self._on_display)
            root.addWidget(box)

        row_t = QHBoxLayout()
        row_t.setSpacing(8)
        row_t.addWidget(self._label(t("set.older_days")))
        self.overdue_days = QSpinBox()
        self.overdue_days.setRange(1, 60)
        self.overdue_days.setSuffix(" " + t("set.days"))
        self.overdue_days.setFixedHeight(26)
        self.overdue_days.setFixedWidth(88)
        self.overdue_days.setStyleSheet(self._spin_qss())
        self.overdue_days.valueChanged.connect(self._on_display)
        row_t.addWidget(self.overdue_days)
        row_t.addSpacing(12)
        row_t.addWidget(self._label(t("set.ahead_days")))
        self.ahead_days = QSpinBox()
        self.ahead_days.setRange(1, 90)
        self.ahead_days.setSuffix(" " + t("set.days"))
        self.ahead_days.setFixedHeight(26)
        self.ahead_days.setFixedWidth(88)
        self.ahead_days.setStyleSheet(self._spin_qss())
        self.ahead_days.valueChanged.connect(self._on_display)
        row_t.addWidget(self.ahead_days)
        row_t.addStretch(1)
        root.addLayout(row_t)
        root.addWidget(_hint(t("set.older_hint")))

        # ------------------------------------------------------------ 形象
        root = self._page(t("set.character"))
        self.skin = SkinPicker(getattr(self.settings, "pet_skin", "") or "")
        self.skin.changed.connect(self._on_skin)
        root.addWidget(self.skin)
        root.addWidget(_hint(t("set.skin_hint")))

        row_imp = QHBoxLayout()
        row_imp.setSpacing(8)
        self.import_skin_btn = QPushButton(t("set.import_skin"))
        self.import_skin_btn.setFont(theme.font(8))
        self.import_skin_btn.setFixedHeight(28)
        self.import_skin_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.import_skin_btn.setStyleSheet(
            "QPushButton { color: __TEXT__; background: __INK14__;"
            " border: 1px solid __INK26__; border-radius: 14px; padding: 0 14px; }"
            "QPushButton:hover { background: __INK22__; }"
        )
        self.import_skin_btn.clicked.connect(self._import_skin)
        row_imp.addWidget(self.import_skin_btn)
        row_imp.addStretch(1)
        root.addLayout(row_imp)
        root.addWidget(_hint(t("set.import_hint") % str(paths.pet_user_dir())))

        # ------------------------------------------------------------ 外观
        root = self._page(t("set.look"))
        row_size = QHBoxLayout()
        row_size.setSpacing(10)
        row_size.addWidget(self._label(t("set.size")))
        self.size_slider = QSlider(Qt.Orientation.Horizontal)
        self.size_slider.setRange(48, 200)
        self.size_slider.setSingleStep(4)
        self.size_slider.setPageStep(16)
        self.size_slider.setFixedWidth(180)
        self.size_slider.setStyleSheet(
            "QSlider::groove:horizontal { height: 4px; background: __INK26__;"
            " border-radius: 2px; }"
            "QSlider::handle:horizontal { width: 14px; height: 14px; margin: -5px 0;"
            " border-radius: 7px; background: #4a90ff; }"
        )
        self.size_slider.valueChanged.connect(self._on_size)
        row_size.addWidget(self.size_slider)
        self.size_value = QLabel("92 px")
        self.size_value.setFont(theme.font(8))
        self.size_value.setStyleSheet(f"color: {theme.TEXT_SOFT.name()};")
        row_size.addWidget(self.size_value)
        row_size.addStretch(1)
        root.addLayout(row_size)
        root.addWidget(_hint(t("set.size_hint")))

        self.glow_box = QCheckBox(t("set.glow"))
        self.badge_dots = QCheckBox(t("set.badge_dots"))
        for box in (self.glow_box, self.badge_dots):
            box.setFont(theme.font(8))
            box.setStyleSheet("QCheckBox { color: %s; }" % theme.TEXT_SOFT.name())
            box.toggled.connect(self._on_look)
            root.addWidget(box)
        root.addWidget(_hint(t("set.glow_hint")))

        self.badge = QComboBox()
        self.badge.addItem(t("set.badge_count"), "count")
        self.badge.addItem(t("set.badge_due"), "due")
        self.badge.setFixedHeight(26)
        self.badge.setStyleSheet(
            "QComboBox { background: __INK14__; border: 1px solid __INK26__;"
            " border-radius: 8px; padding: 2px 6px; color: __TEXT__; }"
            "QComboBox QAbstractItemView { background: __CARD__; color: __TEXT__;"
            " selection-background-color: __ACCENT__; }"
        )
        self.badge.currentIndexChanged.connect(self._on_badge)
        root.addWidget(self._row(t("set.badge"), self.badge, 170))

        row2 = QHBoxLayout()
        row2.setSpacing(8)
        row2.addWidget(self._label(t("set.level")))
        self.level = QComboBox()
        for key, label in LEVELS:
            self.level.addItem(t(label), key)
        self.level.setFixedHeight(26)
        self.level.setFixedWidth(170)
        self.level.setStyleSheet(
            "QComboBox { background: __INK14__; border: 1px solid __INK26__;"
            " border-radius: 8px; padding: 2px 6px; color: __TEXT__; }"
            "QComboBox QAbstractItemView { background: __CARD__; color: __TEXT__;"
            " selection-background-color: __ACCENT__; }"
        )
        self.level.currentIndexChanged.connect(self._on_level)
        row2.addWidget(self.level)
        row2.addStretch(1)
        root.addLayout(row2)

        row_l = QHBoxLayout()
        row_l.setSpacing(8)
        row_l.addWidget(self._label(t("set.language")))
        self.language = QComboBox()
        self.language.addItem(t("set.lang_system"), "system")
        self.language.addItem("中文", "zh")
        self.language.addItem("English", "en")
        self.language.setFixedHeight(26)
        self.language.setFixedWidth(170)
        self.language.setStyleSheet(
            "QComboBox { background: __INK14__; border: 1px solid __INK26__;"
            " border-radius: 8px; padding: 2px 6px; color: __TEXT__; }"
            "QComboBox QAbstractItemView { background: __CARD__; color: __TEXT__;"
            " selection-background-color: __ACCENT__; }"
        )
        self.language.currentIndexChanged.connect(self._on_language)
        row_l.addWidget(self.language)
        row_l.addStretch(1)
        root.addLayout(row_l)

        row_t = QHBoxLayout()
        row_t.setSpacing(8)
        row_t.addWidget(self._label(t("set.theme")))
        self.theme_box = QComboBox()
        self.theme_box.addItem(t("theme.system"), "system")
        self.theme_box.addItem(t("theme.light"), "light")
        self.theme_box.addItem(t("theme.dark"), "dark")
        self.theme_box.setFixedHeight(26)
        self.theme_box.setFixedWidth(170)
        self.theme_box.setStyleSheet(
            "QComboBox { background: __INK14__; border: 1px solid __INK26__;"
            " border-radius: 8px; padding: 2px 6px; color: __TEXT__; }"
            "QComboBox QAbstractItemView { background: __CARD__; color: __TEXT__;"
            " selection-background-color: __ACCENT__; }"
        )
        self.theme_box.currentIndexChanged.connect(self._on_theme)
        row_t.addWidget(self.theme_box)
        row_t.addStretch(1)
        root.addLayout(row_t)

        update_row = QHBoxLayout()
        ver = QLabel(version_line())
        ver.setFont(theme.font(7.5))
        ver.setStyleSheet(f"color: {theme.TEXT_MUTED.name()}; padding-top: 4px;")
        update_row.addWidget(ver, 1)
        self.update_btn = QPushButton(t("set.check_update"))
        self.update_btn.setFont(theme.font(7.5))
        self.update_btn.setFixedHeight(26)
        self.update_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.update_btn.setStyleSheet(
            "QPushButton { color: __TEXT__; background: __INK14__;"
            " border: 1px solid __INK26__; border-radius: 13px; padding: 0 14px; }"
            "QPushButton:hover { background: __INK22__; }"
            "QPushButton:disabled { color: __MUTED__; }"
        )
        self.update_btn.clicked.connect(self._check_update)
        update_row.addWidget(self.update_btn)
        root.addLayout(update_row)

        self.update_msg = QLabel("")
        self.update_msg.setFont(theme.font(7.5))
        self.update_msg.setStyleSheet(f"color: {theme.TEXT_MUTED.name()};")
        self.update_msg.setVisible(False)
        root.addWidget(self.update_msg)

        self.update_open = QPushButton(t("set.open_download"))
        self.update_open.setFont(theme.font(7.5))
        self.update_open.setFixedHeight(26)
        self.update_open.setCursor(Qt.CursorShape.PointingHandCursor)
        self.update_open.setStyleSheet(self.update_btn.styleSheet())
        self.update_open.setVisible(False)
        self.update_open.clicked.connect(self._open_releases)
        root.addWidget(self.update_open)

        # ------------------------------------------------------------ 提醒
        root = self._page(t("set.reminders"))
        row_cr = QHBoxLayout()
        row_cr.setSpacing(8)
        self.class_remind = QCheckBox(t("set.class_remind"))
        self.class_remind.setFont(theme.font(8))
        self.class_remind.setStyleSheet("QCheckBox { color: %s; }" % theme.TEXT_SOFT.name())
        self.class_remind.toggled.connect(self._on_reminders)
        row_cr.addWidget(self.class_remind)
        self.class_minutes = QSpinBox()
        self.class_minutes.setRange(1, 60)
        self.class_minutes.setSuffix(" " + t("set.min_before"))
        self.class_minutes.setFixedHeight(26)
        self.class_minutes.setFixedWidth(104)
        self.class_minutes.setStyleSheet(self._spin_qss())
        self.class_minutes.valueChanged.connect(self._on_reminders)
        row_cr.addWidget(self.class_minutes)
        row_cr.addStretch(1)
        root.addLayout(row_cr)
        root.addWidget(_hint(t("set.class_hint")))

        self.daily_brief = QCheckBox(t("set.daily_brief"))
        self.daily_brief.setFont(theme.font(8))
        self.daily_brief.setStyleSheet("QCheckBox { color: %s; }" % theme.TEXT_SOFT.name())
        self.daily_brief.toggled.connect(self._on_reminders)
        root.addWidget(self.daily_brief)

        row_q = QHBoxLayout()
        row_q.setSpacing(8)
        row_q.addWidget(self._label(t("set.quiet")))
        self.quiet_start = QSpinBox()
        self.quiet_start.setRange(0, 23)
        self.quiet_start.setSuffix(" " + t("set.oclock"))
        self.quiet_start.setFixedHeight(26)
        self.quiet_start.setFixedWidth(84)
        self.quiet_start.setStyleSheet(self._spin_qss())
        self.quiet_start.valueChanged.connect(self._on_reminders)
        row_q.addWidget(self.quiet_start)
        dash = QLabel("–")
        dash.setStyleSheet(f"color: {theme.TEXT_MUTED.name()};")
        row_q.addWidget(dash)
        self.quiet_end = QSpinBox()
        self.quiet_end.setRange(0, 23)
        self.quiet_end.setSuffix(" " + t("set.oclock"))
        self.quiet_end.setFixedHeight(26)
        self.quiet_end.setFixedWidth(84)
        self.quiet_end.setStyleSheet(self._spin_qss())
        self.quiet_end.valueChanged.connect(self._on_reminders)
        row_q.addWidget(self.quiet_end)
        row_q.addStretch(1)
        root.addLayout(row_q)

        # ------------------------------------------------------------ 常规
        root = self._page(t("set.general"))
        row = QHBoxLayout()
        row.setSpacing(8)
        row.addWidget(self._label(t("set.interval")))
        self.interval = QSpinBox()
        self.interval.setRange(1, 60)
        self.interval.setSuffix(" " + t("set.minutes"))
        self.interval.setFixedHeight(26)
        self.interval.setFixedWidth(120)
        self.interval.setStyleSheet(self._spin_qss())
        self.interval.valueChanged.connect(self._on_interval)
        row.addWidget(self.interval)
        row.addStretch(1)
        root.addLayout(row)

        self.embedded = QCheckBox(t("set.embedded"))
        self.embedded.setFont(theme.font(8))
        self.embedded.setStyleSheet("QCheckBox { color: %s; }" % theme.TEXT_SOFT.name())
        self.embedded.toggled.connect(self._on_embedded)
        root.addWidget(self.embedded)

        self.autostart = QCheckBox(t("set.autostart"))
        self.autostart.setFont(theme.font(8))
        self.autostart.setStyleSheet(f"QCheckBox {{ color: {theme.TEXT_SOFT.name()}; }}")
        self.autostart.toggled.connect(self._on_autostart)
        root.addWidget(self.autostart)

        # ------------------------------------------------------------ 数据
        root = self._page(t("set.data"))
        export_btn = QPushButton(t("set.export"))
        export_btn.setFont(theme.font(8))
        export_btn.setFixedHeight(28)
        export_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        export_btn.setStyleSheet(
            "QPushButton { color: __TEXT__; background: __INK16__;"
            " border: 1px solid __INK22__; border-radius: 14px; padding: 0 14px; }"
            "QPushButton:hover { background: __INK32__; }"
        )
        export_btn.clicked.connect(self.export_requested.emit)
        row_e = QHBoxLayout()
        row_e.addWidget(export_btn)
        row_e.addStretch(1)
        root.addLayout(row_e)
        root.addWidget(_hint(t("set.export_hint")))

        log_btn = QPushButton(t("set.export_log"))
        log_btn.setFont(theme.font(8))
        log_btn.setFixedHeight(28)
        log_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        log_btn.setStyleSheet(
            "QPushButton { color: __TEXT__; background: __INK16__;"
            " border: 1px solid __INK22__; border-radius: 14px; padding: 0 14px; }"
            "QPushButton:hover { background: __INK32__; }"
        )
        log_btn.clicked.connect(self._export_log)
        row_l = QHBoxLayout()
        row_l.addWidget(log_btn)
        row_l.addStretch(1)
        root.addLayout(row_l)
        root.addWidget(_hint(t("set.export_log_hint")))
        root.addWidget(_hint(t("set.vault_hint")))

        root.addWidget(_hint(t("set.privacy")))

        root.addStretch(1)

        self._regroup()
        self.nav.setCurrentRow(0)
        self.refresh()


    # ------------------------------------------------------------ regrouping
    def _check_update(self) -> None:
        self.update_btn.setEnabled(False)
        self.update_btn.setText(t("set.checking"))
        self.update_msg.setVisible(False)
        self.update_open.setVisible(False)
        self._update_url = RELEASES_URL
        self._update_thread = _UpdateCheck(self)
        self._update_thread.done.connect(self._on_update_result)
        self._update_thread.start()

    def _on_update_result(self, ok: bool, tag: str, url: str) -> None:
        self.update_btn.setEnabled(True)
        self.update_btn.setText(t("set.check_update"))
        if ok and tag:
            self._update_url = url or RELEASES_URL
            if _version_tuple(tag) > _version_tuple(VERSION):
                self.update_msg.setText(t("set.update_available") % tag)
                self.update_open.setVisible(True)
            else:
                self.update_msg.setText(t("set.up_to_date"))
        else:
            self.update_msg.setText(t("set.update_failed"))
            self.update_open.setVisible(True)
        self.update_msg.setVisible(True)

    def _export_log(self) -> None:
        """日志是密文，排障时才解一份明文出来。"""
        from .. import vault

        base = paths.log_file()
        target, _ = QFileDialog.getSaveFileName(
            self, t("set.export_log"),
            str(Path.home() / "VesperBoard-diagnostic.log"), "*.log")
        if not target:
            return
        parts = []
        for i in (2, 1):
            older = base.with_name("%s.%d" % (base.name, i))
            if older.exists():
                parts.append(vault.LogSink(older).read())
        parts.append(vault.log_sink().read())
        try:
            Path(target).write_text("".join(parts), encoding="utf-8")
        except OSError as exc:
            self.account_msg.setText(str(exc))

    def _open_releases(self) -> None:
        QDesktopServices.openUrl(QUrl(self._update_url or RELEASES_URL))

    def _regroup(self) -> None:
        """把六张卡片并成用户要的几组：常规 / 形象 / 账号 / 高级 / 作者。

        「用内置窗口登录」归到账号（登录相关），刷新间隔和提醒相关一起归到高级。
        """
        pages = [self.stack.widget(i) for i in range(self.stack.count())]
        drained = [self._drain(w) for w in pages]
        for w in pages:
            self.stack.removeWidget(w)
            w.deleteLater()
        self.nav.clear()

        def holds(item, widget) -> bool:
            if item.widget() is widget:
                return True
            layout = item.layout()
            if layout is not None:
                for i in range(layout.count()):
                    sub = layout.itemAt(i)
                    if sub is not None and sub.widget() is widget:
                        return True
            return False

        general = drained[5]
        login_items = [it for it in general if holds(it, self.embedded)]
        advanced_items = [it for it in general if holds(it, self.interval)]
        common_items = [it for it in general
                        if not holds(it, self.embedded) and not holds(it, self.interval)]

        self._build_page(t("set.common"), drained[3] + common_items)      # 外观 + 自启
        self._build_page(t("set.character"), drained[2])                 # 形象：角色 + 换装
        self._build_page(t("set.account"), drained[0] + login_items)     # 账号 + 内置登录
        self._build_page(t("set.advanced"),
                         drained[1] + drained[4] + advanced_items + drained[6])  # 显示 + 提醒 + 刷新 + 数据
        self._build_author_page()

    @staticmethod
    def _drain(widget) -> list:
        layout = widget.layout()
        items = []
        if layout is not None:
            while layout.count():
                items.append(layout.takeAt(0))
        return items

    def _build_page(self, title: str, items: list) -> None:
        page = QWidget()
        box = QVBoxLayout(page)
        box.setContentsMargins(6, 4, 10, 6)
        box.setSpacing(10)
        box.setAlignment(Qt.AlignmentFlag.AlignTop)
        for item in items:
            if item.spacerItem():
                continue
            if item.widget() is not None:
                box.addWidget(item.widget())
            elif item.layout() is not None:
                box.addLayout(item.layout())
        box.addStretch(1)
        self.stack.addWidget(page)
        self.nav.addItem(title)

    def _build_author_page(self) -> None:
        page = QWidget()
        box = QVBoxLayout(page)
        box.setContentsMargins(6, 8, 10, 6)
        box.setSpacing(10)
        box.setAlignment(Qt.AlignmentFlag.AlignTop)

        grid = QGridLayout()
        grid.setHorizontalSpacing(12)
        grid.setVerticalSpacing(10)
        grid.setColumnStretch(1, 1)
        valign = Qt.AlignmentFlag.AlignVCenter

        # 项目 + Star
        grid.addWidget(self._label("项目"), 0, 0, valign)
        proj = QLabel('<a href="https://github.com/JiamingShi-JsPhys/vesper-board" '
                      'style="color:%s; text-decoration:none;">Vesper Board</a>'
                      % theme.TEXT.name())
        proj.setOpenExternalLinks(True)
        proj.setFont(theme.font(10.5, QFont.Weight.DemiBold))

        star = QPushButton("★  " + t("set.star"))
        star.setFont(theme.font(9))
        star.setFixedHeight(32)
        star.setCursor(Qt.CursorShape.PointingHandCursor)
        star.setStyleSheet(
            "QPushButton { color: #1b1f27; background: #e8b64c; border: none;"
            " border-radius: 16px; padding: 0 18px; font-weight: 600; }"
            "QPushButton:hover { background: #f2c55f; }"
        )
        star.clicked.connect(lambda: QDesktopServices.openUrl(
            QUrl("https://github.com/JiamingShi-JsPhys/vesper-board")))
        # Star 紧跟在项目名右边，不再贴到最右侧
        proj_row = QHBoxLayout()
        proj_row.addWidget(proj)
        proj_row.addSpacing(28)
        proj_row.setContentsMargins(0, 0, 0, 0)
        proj_row.setSpacing(0)
        proj_row.addWidget(star)
        proj_row.addStretch(1)
        grid.addLayout(proj_row, 0, 1)

        # 分隔线
        line = QFrame()
        line.setFixedHeight(1)
        line.setStyleSheet("background: __INK26__; border: none;")
        grid.addWidget(line, 2, 0, 1, 3)

        # 作者
        grid.addWidget(self._label("作者"), 3, 0, valign)
        author = QLabel('施嘉名　<a href="https://github.com/JiamingShi-JsPhys" '
                        'style="color:#7fb0ff; text-decoration:none;">@JiamingShi-JsPhys</a>')
        author.setOpenExternalLinks(True)
        author.setFont(theme.font(9))
        grid.addWidget(author, 3, 1, valign)

        box.addLayout(grid)
        box.addStretch(1)
        self.stack.addWidget(page)
        self.nav.addItem(t("set.author"))

    @staticmethod
    def _github_badge() -> QWidget:
        from PySide6.QtCore import QRectF
        from PySide6.QtGui import QColor, QPainter, QPixmap

        badge = QLabel()
        pix = QPixmap(44, 44)
        pix.fill(Qt.GlobalColor.transparent)
        painter = QPainter(pix)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setBrush(theme.BG_DEEP)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawEllipse(QRectF(0, 0, 44, 44))
        painter.setPen(QColor("__TEXT__"))
        font = theme.font(9, QFont.Weight.Bold)
        painter.setFont(font)
        painter.drawText(QRectF(0, 0, 44, 44), Qt.AlignmentFlag.AlignCenter, "GH")
        painter.end()
        badge.setPixmap(pix)
        return badge

    # ---------------------------------------------------------------- layout
    @staticmethod
    def _label(text: str) -> QLabel:
        label = QLabel(text)
        label.setFont(theme.font(8))
        label.setStyleSheet(f"color: {theme.TEXT_SOFT.name()};")
        label.setFixedWidth(76)
        return label

    def _page(self, title: str) -> QVBoxLayout:
        """一页一个分区；左侧导航自动多一项。"""
        page = QWidget()
        box = QVBoxLayout(page)
        box.setContentsMargins(6, 4, 10, 6)
        box.setSpacing(10)
        box.setAlignment(Qt.AlignmentFlag.AlignTop)
        self.stack.addWidget(page)
        self.nav.addItem(title)
        return box

    def _row(self, text: str, widget: QWidget, width: int = 0) -> QWidget:
        """标签在左、控件紧挨着，左侧标签列同宽，扫一眼就是对齐的。"""
        wrap = QWidget()
        row = QHBoxLayout(wrap)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(10)
        row.addWidget(self._label(text))
        if width:
            widget.setFixedWidth(width)
        row.addWidget(widget)
        row.addStretch(1)
        return wrap

    def _login_row(self, mode: str, text: str, login_slot, test_slot) -> QHBoxLayout:
        row = QHBoxLayout()
        row.setSpacing(8)
        login = QPushButton(text)
        login.setFixedHeight(28)
        login.setCursor(Qt.CursorShape.PointingHandCursor)
        login.setFont(theme.font(8))
        login.setStyleSheet(
            "QPushButton { color: white; background: rgba(74,144,255,190); border: none;"
            " border-radius: 14px; padding: 0 14px; }"
            "QPushButton:hover { background: rgba(96,160,255,235); }"
            "QPushButton:disabled { background: __INK14__;"
            " color: __TEXT__; }"
        )
        login.clicked.connect(login_slot)
        if not WEB_LOGIN:
            login.setEnabled(False)
            login.setToolTip("当前环境缺少 WebEngine，请用 .venv 启动")
        row.addWidget(login)

        test = QPushButton(t("set.test"))
        test.setFixedHeight(28)
        test.setCursor(Qt.CursorShape.PointingHandCursor)
        test.setFont(theme.font(8))
        test.setStyleSheet(
            "QPushButton { color: __TEXT__; background: __INK16__;"
            " border: 1px solid __INK22__; border-radius: 14px; padding: 0 12px; }"
            "QPushButton:hover { background: __INK32__; }"
        )
        test.clicked.connect(test_slot)
        row.addWidget(test)

        logout = QPushButton(t("set.logout"))
        logout.setFixedHeight(28)
        logout.setCursor(Qt.CursorShape.PointingHandCursor)
        logout.setFont(theme.font(8))
        logout.setStyleSheet(
            "QPushButton { color: rgba(255,140,150,210); background: transparent;"
            " border: 1px solid rgba(255,120,130,60); border-radius: 14px; padding: 0 12px; }"
            "QPushButton:hover { background: rgba(255,90,100,30); }"
        )
        logout.clicked.connect(lambda: self._logout(mode))
        row.addWidget(logout)

        self._logout_buttons = getattr(self, "_logout_buttons", {})
        self._logout_buttons[mode] = logout
        row.addStretch(1)
        return row

    # ---------------------------------------------------------------- state
    def _sync_login_fields(self) -> None:
        embedded = bool(getattr(self.settings, "use_embedded_login", True))
        self.canvas_token.setVisible(not embedded)
        self.ams_session.setVisible(not embedded)

    def refresh(self) -> None:
        has_canvas = session_store.has_any_canvas_auth()
        has_ams = session_store.has_ams_session()
        if has_canvas and has_ams:
            text = t("set.signed_both")
        elif has_canvas:
            text = t("set.signed_canvas_only")
        elif has_ams:
            text = t("set.signed_ams_only")
        else:
            text = t("set.signed_out")
        self.account_status.setText(text)
        self.account_status.setStyleSheet(
            "color: %s;" % (theme.OK.name() if (has_canvas and has_ams)
                            else theme.TEXT_MUTED.name())
        )
        self.login_btn.setVisible(not (has_canvas and has_ams))
        self.logout_btn.setVisible(has_canvas or has_ams)

        self.interval.blockSignals(True)
        self.interval.setValue(max(1, self.settings.poll_minutes))
        self.interval.blockSignals(False)

        self.level.blockSignals(True)
        index = max(0, self.level.findData(self.settings.window_level or "top"))
        self.level.setCurrentIndex(index)
        self.level.blockSignals(False)

        self.skin.set_current(getattr(self.settings, "pet_skin", "") or "")
        self.size_slider.blockSignals(True)
        self.size_slider.setValue(int(getattr(self.settings, "pet_size", 92) or 92))
        self.size_slider.blockSignals(False)
        self.size_value.setText("%d px" % self.size_slider.value())

        self.badge.blockSignals(True)
        self.badge.setCurrentIndex(max(0, self.badge.findData(
            getattr(self.settings, "badge_mode", "count") or "count")))
        self.badge.blockSignals(False)

        for widget, value in (
            (self.glow_box, bool(getattr(self.settings, "pet_glow", False))),
            (self.badge_dots, bool(getattr(self.settings, "show_badge", False))),
        ):
            widget.blockSignals(True)
            widget.setChecked(value)
            widget.blockSignals(False)

        for widget, value in (
            (self.class_remind, bool(getattr(self.settings, "class_reminders", True))),
            (self.daily_brief, bool(getattr(self.settings, "daily_brief", True))),
        ):
            widget.blockSignals(True)
            widget.setChecked(value)
            widget.blockSignals(False)
        for widget, value in (
            (self.class_minutes, max(1, int(getattr(self.settings, "class_remind_minutes", 10)))),
            (self.quiet_start, int(getattr(self.settings, "quiet_start", 23))),
            (self.quiet_end, int(getattr(self.settings, "quiet_end", 7))),
        ):
            widget.blockSignals(True)
            widget.setValue(value)
            widget.blockSignals(False)

        if hasattr(self, "theme_box"):
            self.theme_box.blockSignals(True)
            self.theme_box.setCurrentIndex(max(0, self.theme_box.findData(
                getattr(self.settings, "theme_mode", "system") or "system")))
            self.theme_box.blockSignals(False)

        self.language.blockSignals(True)
        self.language.setCurrentIndex(
            max(0, self.language.findData(getattr(self.settings, "language", "zh") or "zh"))
        )
        self.language.blockSignals(False)

        self.embedded.blockSignals(True)
        self.embedded.setChecked(bool(getattr(self.settings, "use_embedded_login", False)))
        self.embedded.blockSignals(False)

        self.autostart.blockSignals(True)
        self.autostart.setChecked(autostart_enabled())
        self.autostart.blockSignals(False)
        self._sync_login_fields()

        for box, value in ((self.show_older, self.settings.show_older),
                           (self.show_far, self.settings.show_far),
                           (self.show_reminders, self.settings.show_reminders)):
            box.blockSignals(True)
            box.setChecked(bool(value))
            box.blockSignals(False)
        for spin, value in ((self.overdue_days, self.settings.overdue_days),
                            (self.ahead_days, self.settings.ahead_days)):
            spin.blockSignals(True)
            spin.setValue(int(value))
            spin.blockSignals(False)

    # -------------------------------------------------------------- actions
    def _login_any(self) -> None:
        if not session_store.has_any_canvas_auth():
            self._login_canvas()
        elif not session_store.has_ams_session():
            self._login_ams()
        else:
            self.account_msg.setText(t("set.signed_in"))

    def _test_any(self) -> None:
        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        try:
            self._run_checks()
        finally:
            QApplication.restoreOverrideCursor()

    def _run_checks(self) -> None:
        parts = []
        ok_canvas, canvas_text = self._check_canvas()
        parts.append(canvas_text)
        ok_ams, ams_text = self._check_ams()
        parts.append(ams_text)
        self.account_msg.setText(" · ".join(parts))
        self.account_msg.setStyleSheet(
            "color: %s;" % (theme.OK.name() if (ok_canvas and ok_ams) else theme.DANGER.name())
        )

    def _logout_any(self) -> None:
        session_store.clear_cookies()
        session_store.clear_cookie_map()
        security.save_secret(paths.canvas_token_file(), "")
        session_store.clear_ams_cookies()
        self.canvas_token.clear()
        self.ams_session.clear()
        self.account_msg.setText("")
        self.refresh()
        self.logged_out.emit("canvas")

    def _logout(self, mode: str) -> None:
        if mode == "canvas":
            session_store.clear_cookies()
            session_store.clear_cookie_map()
            security.save_secret(paths.canvas_token_file(), "")
            self.canvas_token.clear()
        else:
            session_store.clear_ams_cookies()
            session_store.clear_cookie_map()
            self.ams_session.clear()
        self.refresh()
        self.logged_out.emit(mode)

    def start_login(self, mode: str) -> None:
        """Used by the first-run flow."""
        (self._login_canvas if mode == "canvas" else self._login_ams)()

    def _import_skin(self) -> None:
        folder = QFileDialog.getExistingDirectory(self, t("set.import_skin"))
        if not folder:
            return
        src = Path(folder)
        if not (src / "idle.png").exists():
            warn_on_top(self, t("set.import_skin"), t("set.import_bad"))
            return
        name = re.sub(r"[^0-9A-Za-z_\-一-鿿]", "_", src.name) or "skin"
        dst = paths.pet_user_dir() / name
        n = 2
        while dst.exists():
            dst = paths.pet_user_dir() / ("%s_%d" % (name, n))
            n += 1
        try:
            shutil.copytree(src, dst, symlinks=True)
        except OSError as exc:
            warn_on_top(self, t("set.import_skin"), str(exc))
            return
        key = "user/" + dst.name
        self.skin.reload()
        self.skin.set_current(key)
        self._on_skin(key)

    def _on_skin(self, key: str) -> None:
        self.settings.pet_skin = str(key or "")
        self._persist()

    def _on_badge(self, _index: int) -> None:
        self.settings.badge_mode = str(self.badge.currentData() or "count")
        self._persist()

    def _on_reminders(self, *_args) -> None:
        self.settings.class_reminders = self.class_remind.isChecked()
        self.settings.class_remind_minutes = int(self.class_minutes.value())
        self.settings.daily_brief = self.daily_brief.isChecked()
        self.settings.quiet_start = int(self.quiet_start.value())
        self.settings.quiet_end = int(self.quiet_end.value())
        self._persist()

    def _on_look(self, *_args) -> None:
        self.settings.pet_glow = self.glow_box.isChecked()
        self.settings.show_badge = self.badge_dots.isChecked()
        self._persist()

    def _on_size(self, value: int) -> None:
        self.settings.pet_size = int(value)
        self.size_value.setText("%d px" % int(value))
        self._persist()

    def _on_embedded(self, on: bool) -> None:
        self.settings.use_embedded_login = bool(on)
        self._sync_login_fields()
        self._persist()

    def _on_theme(self, _index: int) -> None:
        self.settings.theme_mode = str(self.theme_box.currentData() or "system")
        self._persist()

    def _on_language(self, _index: int) -> None:
        code = self.language.currentData() or "system"
        self.settings.language = str(code)
        self._persist()
        self.language_changed.emit(str(code))

    def _on_interval(self, value: int) -> None:
        self.settings.poll_minutes = int(value)
        self._persist()

    def _on_level(self, index: int) -> None:
        key = self.level.itemData(index) or "top"
        self.settings.window_level = str(key)
        self._persist()

    def _on_autostart(self, on: bool) -> None:
        self.settings.start_with_windows = bool(on)
        try:
            set_autostart(bool(on))
        except OSError:
            pass
        self._persist()

    @staticmethod
    def _spin_qss() -> str:
        return (
            "QSpinBox { background: __INK14__;"
            " border: 1px solid __INK26__; border-radius: 8px;"
            " padding: 2px 6px; color: __TEXT__; }"
        )

    def _on_display(self, *_args) -> None:
        self.settings.show_older = self.show_older.isChecked()
        self.settings.show_far = self.show_far.isChecked()
        self.settings.show_reminders = self.show_reminders.isChecked()
        self.settings.overdue_days = int(self.overdue_days.value())
        self.settings.ahead_days = int(self.ahead_days.value())
        self._persist()

    def _persist(self) -> None:
        try:
            self.settings.save()
        except OSError:
            pass
        self.changed.emit()

    # ---------------------------------------------------------------- login
    @staticmethod
    def _edit_qss() -> str:
        return ("QLineEdit { background: __INK14__;"
                " border: 1px solid __INK26__; border-radius: 8px;"
                " padding: 2px 8px; color: __TEXT__; }")

    def _save_canvas_token(self) -> None:
        token = self.canvas_token.text().strip()
        if not token:
            return
        security.save_secret(paths.canvas_token_file(), token)
        self.account_msg.setText(t("set.saved"))
        self.account_msg.setStyleSheet("color: %s;" % theme.OK.name())
        self.refresh()
        self.logged_in.emit("canvas")

    def _save_ams_session(self) -> None:
        value = self.ams_session.text().strip()
        if not value:
            return
        session_store.save_ams_cookies({"SESSION": value})
        self.account_msg.setText(t("set.saved"))
        self.account_msg.setStyleSheet("color: %s;" % theme.OK.name())
        self.refresh()
        self.logged_in.emit("ams")

    def _login_canvas(self) -> None:
        if session_store.has_any_canvas_auth():
            self.account_msg.setText(t("set.signed_in"))
            self.logged_in.emit("canvas")
            return
        if not getattr(self.settings, "use_embedded_login", False):
            QDesktopServices.openUrl(QUrl("https://canvas.westlake.edu.cn/profile/settings"))
            return
        self._login("canvas")

    def _login_ams(self) -> None:
        if session_store.has_ams_session():
            self.account_msg.setText(t("set.signed_in"))
            self.logged_in.emit("ams")
            return
        if not getattr(self.settings, "use_embedded_login", False):
            QDesktopServices.openUrl(QUrl("https://ams.westlake.edu.cn/home/"))
            return
        self._login("ams")

    def _login(self, mode: str) -> None:
        if not WEB_LOGIN or LoginWindow is None:
            self.account_msg.setText("这个环境没有 WebEngine，登录窗打不开")
            return
        self.account_msg.setText("登录窗口打开中…")
        import traceback
        try:
            window = LoginWindow(mode, self, seed=False)
        except Exception as exc:          # 构造失败以前是静默的，用户只看到"没反应"
            logging.getLogger("wsdock.login").error(
                "登录窗构造失败：%s\n%s", exc, traceback.format_exc())
            self.account_msg.setText("登录窗口打不开：%s" % exc)
            return
        window.succeeded.connect(self._on_logged_in)
        try:
            window.exec()
        except Exception as exc:
            logging.getLogger("wsdock.login").error(
                "登录窗运行失败：%s\n%s", exc, traceback.format_exc())
            self.account_msg.setText("登录窗口出错：%s" % exc)
        self.account_msg.setText("")

    def _on_logged_in(self, mode: str, payload: dict) -> None:
        if mode == "canvas":
            session_store.save_cookies(payload.get("cookies") or {})
            self.account_msg.setText(t("set.saved"))
        else:
            session_store.save_ams_cookies(payload.get("cookies") or {})
            self.account_msg.setText(t("set.saved"))
        self.refresh()
        self.logged_in.emit(mode)

    # ----------------------------------------------------------------- test
    def _check_canvas(self) -> tuple[bool, str]:
        cookies = session_store.load_cookies()
        token = security.load_secret(paths.canvas_token_file())
        if not cookies and not token:
            return False, "Canvas：未登录"
        try:
            client = CanvasClient(self.settings.canvas_url,
                                  token="" if cookies else token,
                                  cookies=cookies or None, timeout=10)
            me = client.whoami()
            return True, "Canvas：%s" % (me.get("name") or me.get("login_id") or "正常")
        except CanvasError as exc:
            return False, "Canvas：%s" % exc

    def _check_ams(self) -> tuple[bool, str]:
        cookies = session_store.load_ams_cookies()
        if not cookies:
            return False, "AMS：未登录"
        try:
            client = AmsClient(self.settings.ams_url, cookies=cookies, timeout=10)
            today, _tomorrow, _meta = client.lessons_today()
            return True, "AMS：今天 %d 节" % len(today)
        except AmsError as exc:
            return False, "AMS：%s" % exc


