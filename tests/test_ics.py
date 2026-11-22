"""iCalendar export: lessons become events, deadlines become 15-minute blocks."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from wsdock.ics import build_ics
from wsdock.models import Assignment, Lesson


def lesson(title, start, end, room=""):
    return Lesson(title=title, start=start, end=end, location=room)


def assignment(id_, title, due, course="课程", submitted=False):
    return Assignment(
        id=id_, course_id=1, course_name=course, title=title, due_at=due,
        html_url="https://canvas.example/1", submitted=submitted, graded=False,
        submission_types=["online_upload"],
    )


def test_calendar_has_lessons_and_deadlines():
    base = datetime(2026, 11, 20, 9, 0)
    text = build_ics(
        [lesson("高等数学", base, base + timedelta(minutes=95), "A201")],
        [assignment(7, "Lab 报告", base + timedelta(days=1))],
        now=base,
    )
    assert text.startswith("BEGIN:VCALENDAR")
    assert text.rstrip().endswith("END:VCALENDAR")
    assert "SUMMARY:高等数学" in text
    assert "LOCATION:A201" in text
    assert "SUMMARY:交：Lab 报告" in text
    assert text.count("BEGIN:VEVENT") == 2


def test_submitted_assignments_are_left_out():
    base = datetime(2026, 11, 20, 9, 0)
    text = build_ics([], [assignment(7, "交过了", base + timedelta(days=1), submitted=True)], now=base)
    assert "交过了" not in text
    assert "BEGIN:VEVENT" not in text


def test_special_characters_are_escaped():
    base = datetime(2026, 11, 20, 9, 0)
    text = build_ics([lesson("A,B;C", base, base + timedelta(hours=1))], [], now=base)
    assert "SUMMARY:A\\,B\\;C" in text


def test_aware_times_become_local_naive():
    base = datetime(2026, 11, 20, 1, 0, tzinfo=timezone.utc)
    text = build_ics([lesson("UTC 课", base, base + timedelta(hours=1))], [], now=datetime(2026, 11, 20))
    local = base.astimezone().replace(tzinfo=None)
    assert "DTSTART:" + local.strftime("%Y%m%dT%H%M%S") in text


def test_lessons_without_end_still_get_a_block():
    base = datetime(2026, 11, 20, 9, 0)
    text = build_ics([Lesson(title="没有结束时间", start=base, end=None)], [], now=base)
    assert "DTEND:" + (base + timedelta(minutes=45)).strftime("%Y%m%dT%H%M%S") in text
