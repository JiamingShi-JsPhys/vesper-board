"""时间窗与倒计时文案的纯函数测试。"""

from __future__ import annotations

from wsdock.schedule import badge_left, human_left, in_quiet_hours


def test_quiet_wraps_midnight():
    for hour in (23, 0, 3, 6):
        assert in_quiet_hours(hour, 23, 7) is True
    for hour in (7, 9, 12, 22):
        assert in_quiet_hours(hour, 23, 7) is False


def test_quiet_same_day_window():
    assert in_quiet_hours(13, 13, 15) is True
    assert in_quiet_hours(14, 13, 15) is True
    assert in_quiet_hours(12, 13, 15) is False
    assert in_quiet_hours(15, 13, 15) is False


def test_quiet_disabled_when_equal():
    for hour in range(24):
        assert in_quiet_hours(hour, 8, 8) is False


def test_badge_left_units():
    assert badge_left(30) == "1m"
    assert badge_left(600) == "10m"
    assert badge_left(3600) == "1h"
    assert badge_left(7200) == "2h"
    assert badge_left(86400) == "1d"
    assert badge_left(86400 * 5) == "5d"


def test_badge_left_negative_means_overdue():
    assert badge_left(-30) == "-1m"
    assert badge_left(-7200) == "-2h"
    assert badge_left(-86400 * 2) == "-2d"


def test_human_left_reads_naturally():
    assert human_left(-60) == "已逾期"
    assert human_left(1500) == "25 分钟后"
    assert human_left(7200) == "2 小时后"
    assert human_left(172800) == "2 天后"
