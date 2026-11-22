"""纯时间计算：勿扰时段与倒计时文案（不依赖 Qt、不读时钟，方便单测）。"""

from __future__ import annotations


def in_quiet_hours(hour: int, start: int, end: int) -> bool:
    """start=23, end=7 表示 23:00 到次日 07:00；start==end 视为不启用。"""
    if start == end:
        return False
    if start < end:
        return start <= hour < end
    return hour >= start or hour < end


def badge_left(seconds: float) -> str:
    """角标用的极短文案：40m / 5h / 2d；已逾期用负号，-2h 表示逾期两小时。"""
    sign = "-" if seconds < 0 else ""
    left = abs(seconds)
    if left < 3600:
        return "%s%dm" % (sign, max(1, int(left // 60)))
    if left < 86400:
        return "%s%dh" % (sign, int(left // 3600))
    return "%s%dd" % (sign, int(left // 86400))


def human_left(seconds: float) -> str:
    if seconds < 0:
        return "已逾期"
    if seconds < 3600:
        return "%d 分钟后" % max(1, int(seconds // 60))
    if seconds < 86400:
        return "%d 小时后" % int(seconds // 3600)
    return "%d 天后" % int(seconds // 86400)
