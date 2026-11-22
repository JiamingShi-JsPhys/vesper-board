"""Time display: Canvas gives UTC, the user must see local time."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from wsdock.timefmt import fmt_day, fmt_relative, fmt_time, to_local


def test_fmt_time_shows_the_local_clock():
    utc = datetime(2026, 11, 22, 15, 59, tzinfo=timezone.utc)
    assert fmt_time(utc) == utc.astimezone().strftime("%H:%M")


def test_naive_datetimes_pass_through_untouched():
    assert fmt_time(datetime(2026, 11, 22, 9, 50)) == "09:50"
    assert fmt_time(None) == "--:--"


def test_day_bucket_uses_the_local_date():
    # 16:30Z is already the next day in +08:00; the label must follow local time
    utc = datetime(2026, 11, 22, 16, 30, tzinfo=timezone.utc)
    local = utc.astimezone()
    label = fmt_day(utc)
    assert local.strftime("%H:%M") in label


def test_relative_math_is_timezone_safe():
    now_utc = datetime.now(timezone.utc)
    # a minute of slack: the clock moves between now_utc and the call
    assert fmt_relative(now_utc + timedelta(hours=3, minutes=1)) == "还剩 3 小时"
    assert fmt_relative(now_utc - timedelta(days=1)).startswith("已逾期")


@pytest.mark.skipif(
    datetime.now(timezone.utc).astimezone().utcoffset() != timedelta(hours=8),
    reason="需要东八区时区",
)
def test_beijing_midnight_deadline_reads_as_2359():
    """The exact bug that was on screen: 23:59 Beijing rendered as 15:59."""
    utc = datetime(2026, 11, 22, 15, 59, tzinfo=timezone.utc)
    assert to_local(utc).hour == 23
    assert fmt_time(utc) == "23:59"
