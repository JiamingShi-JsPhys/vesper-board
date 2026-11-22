"""Time formatting for everything the user reads.

Canvas returns UTC timestamps; every label in the UI must be local time.
Mixing the two once produced "后天 15:59" for a 23:59 deadline — the maths was
right, only the rendering was in the wrong zone. Keep it in one place.
"""

from __future__ import annotations

from datetime import datetime

from . import i18n
from .i18n import t

WEEKDAYS_ZH = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"]
WEEKDAYS_EN = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
WEEKDAYS = WEEKDAYS_ZH


def to_local(dt: datetime | None) -> datetime | None:
    """Aware datetimes become naive local ones, so comparisons stay simple.

    Everything downstream compares against `datetime.now()`, which is naive;
    keeping tzinfo here only produced "can't subtract offset-naive and
    offset-aware datetimes" at the edge of midnight.
    """
    if dt is None:
        return None
    return dt.astimezone().replace(tzinfo=None) if dt.tzinfo else dt


def fmt_time(dt: datetime | None) -> str:
    dt = to_local(dt)
    return dt.strftime("%H:%M") if dt else "--:--"


def weekdays() -> list:
    return WEEKDAYS_EN if i18n.LANG == "en" else WEEKDAYS_ZH


def fmt_date(dt: datetime | None) -> str:
    """'11月20日 周五' / 'Thu, Nov 20'."""
    dt = to_local(dt) or datetime.now()
    if i18n.LANG == "en":
        return "%s, %s %d" % (WEEKDAYS_EN[dt.weekday()], dt.strftime("%b"), dt.day)
    return "%d月%d日 %s" % (dt.month, dt.day, WEEKDAYS_ZH[dt.weekday()])


def fmt_day(dt: datetime | None) -> str:
    dt = to_local(dt)
    if not dt:
        return t("time.nodeadline")
    delta_days = (dt.date() - datetime.now().date()).days
    if delta_days == 0:
        return "%s %s" % (t("time.today"), dt.strftime("%H:%M"))
    if delta_days == 1:
        return "%s %s" % (t("time.tomorrow"), dt.strftime("%H:%M"))
    if delta_days == 2:
        return "%s %s" % (t("time.dayafter"), dt.strftime("%H:%M"))
    if i18n.LANG == "en":
        if 3 <= delta_days <= 6:
            return "%s %s" % (WEEKDAYS_EN[dt.weekday()], dt.strftime("%H:%M"))
        return "%s %d, %s" % (dt.strftime("%b"), dt.day, dt.strftime("%H:%M"))
    if 3 <= delta_days <= 6:
        return f"{WEEKDAYS_ZH[dt.weekday()]} {dt:%H:%M}"
    return f"{dt.month}月{dt.day}日 {dt:%H:%M}"


def fmt_relative(dt: datetime | None) -> str:
    dt = to_local(dt)
    if not dt:
        return ""
    seconds = (dt - datetime.now()).total_seconds()
    if seconds < 0:
        seconds = -seconds
        if seconds < 3600:
            return t("time.late_min") % int(seconds // 60)
        if seconds < 86400:
            return t("time.late_hour") % int(seconds // 3600)
        return t("time.late_day") % int(seconds // 86400)
    if seconds < 3600:
        return t("time.in_min") % max(1, int(seconds // 60))
    if seconds < 86400:
        return t("time.in_hour") % int(seconds // 3600)
    return t("time.in_day") % int(seconds // 86400)
