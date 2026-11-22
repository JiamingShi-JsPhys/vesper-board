"""Tests for the agenda: reminders are not homework, old stuff is folded."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from wsdock.agenda import build
from wsdock.models import Assignment

NOW = datetime(2026, 11, 20, 9, 0)


def make(id_, title, hours_from_now=None, kinds=("online_upload",)):
    due = None if hours_from_now is None else NOW + timedelta(hours=hours_from_now)
    return Assignment(
        id=id_, course_id=1, course_name="课程", title=title,
        due_at=due, html_url="https://x", submitted=False, graded=False,
        submission_types=list(kinds),
    )


def test_reminder_is_not_counted_as_homework():
    item = make(1, "Homework (No submission required)", 10, kinds=("none",))
    assert item.is_reminder and not item.needs_submission

    agenda = build([item], now=NOW)
    assert agenda.actionable == 0
    assert agenda.reminders == [item]
    assert agenda.next_item is None


def test_reminders_never_take_the_next_slot():
    reminder = make(1, "看视频", 1, kinds=("none",))
    real = make(2, "Lab report", 5)
    agenda = build([reminder, real], now=NOW)
    assert agenda.next_item is real
    assert agenda.actionable == 1


def test_buckets_follow_the_time_windows():
    items = [
        make(1, "3 小时前", -3),
        make(2, "今天", 6),
        make(3, "明天", 30),
        make(4, "本周", 24 * 4),
        make(5, "14 天内", 24 * 10),
        make(6, "逾期 30 天", -24 * 30),
        make(7, "无截止", None),
        make(8, "20 天后", 24 * 20),
    ]
    agenda = build(items, now=NOW)

    assert [a.title for a in agenda.overdue] == ["3 小时前"]
    assert [a.title for a in agenda.today] == ["今天"]
    assert [a.title for a in agenda.tomorrow] == ["明天"]
    assert [a.title for a in agenda.this_week] == ["本周"]
    assert [a.title for a in agenda.later] == ["14 天内"]
    assert sorted(a.title for a in agenda.older) == ["逾期 30 天"]
    assert sorted(a.title for a in agenda.far) == ["20 天后", "无截止"]
    assert agenda.visible == 5
    assert agenda.actionable == 8


def test_next_item_is_the_soonest_of_everything_still_visible():
    agenda = build([make(1, "later", 24 * 12), make(2, "tomorrow", 30)], now=NOW)
    assert agenda.next_item.title == "tomorrow"


def test_urgent_only_within_a_day():
    assert build([make(1, "5h", 5)], now=NOW).urgent is True
    assert build([make(1, "2h ago", -2)], now=NOW).urgent is True
    assert build([make(1, "3 days", 72)], now=NOW).urgent is False
    assert build([make(1, "no due", None)], now=NOW).urgent is False


def test_timezone_aware_due_times_do_not_crash():
    aware = make(1, "带时区", 5)
    aware.due_at = aware.due_at.replace(tzinfo=timezone.utc)
    agenda = build([aware], now=NOW)
    assert agenda.today or agenda.overdue or agenda.tomorrow  # just must not raise


def test_hidden_groups_are_left_out_of_the_count():
    items = [
        make(1, "逾期 30 天", -24 * 30),
        make(2, "20 天后", 24 * 20),
        make(3, "仅提醒", 5, kinds=("none",)),
        make(4, "明天要交", 30),
    ]
    agenda = build(items, now=NOW, include_older=False, include_far=False,
                   include_reminders=False)
    assert agenda.actionable == 1
    assert agenda.older == [] and agenda.far == [] and agenda.reminders == []
    assert [a.title for a in agenda.tomorrow] == ["明天要交"]


def test_thresholds_are_configurable():
    items = [make(1, "迟到 3 天", -72), make(2, "10 天后", 24 * 10)]
    agenda = build(items, now=NOW, overdue_days=1, ahead_days=5)
    assert [a.title for a in agenda.older] == ["迟到 3 天"]
    assert [a.title for a in agenda.far] == ["10 天后"]


def test_submitted_items_leave_the_queue():
    done = make(1, "已交的", 5)
    done.submitted = True
    done.submitted_at = NOW - timedelta(hours=2)
    agenda = build([done, make(2, "要交的", 6)], now=NOW)

    assert [a.title for a in agenda.submitted] == ["已交的"]
    assert agenda.actionable == 1
    assert agenda.next_item.title == "要交的"


def test_submitted_can_be_hidden_entirely():
    done = make(1, "已交的", 5)
    done.submitted = True
    agenda = build([done], now=NOW, include_submitted=False)
    assert agenda.submitted == []


def test_old_overdue_items_do_not_raise_urgency():
    """逾期超过 7 天会折叠进「更早」，不该让人物紧张。"""
    from datetime import datetime, timedelta
    from wsdock.agenda import build
    from wsdock.models import Assignment

    now = datetime(2026, 11, 21, 22, 0)

    def item(due):
        return Assignment(id=1, course_id=1, course_name="CS", title="A",
                          due_at=due, html_url="", submitted=False, graded=False,
                          submission_types=["online_upload"])

    old = build([item(now - timedelta(days=10))], now=now)
    assert old.urgent is False

    recent = build([item(now - timedelta(days=2))], now=now)
    assert recent.urgent is True

    soon = build([item(now + timedelta(hours=6))], now=now)
    assert soon.urgent is True
