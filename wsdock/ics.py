"""Minimal iCalendar export: timetable lessons and assignment deadlines.

Floating local times (no Z, no TZID) — every calendar app accepts them and it
sidesteps DST rules for a university that is on +08:00 all year.
"""

from __future__ import annotations

from datetime import datetime, timedelta

from .models import Assignment, Lesson
from .timefmt import to_local


def _escape(text: str) -> str:
    return (
        text.replace("\\", "\\\\")
        .replace(";", "\\;")
        .replace(",", "\\,")
        .replace("\r", "")
        .replace("\n", "\\n")
    )


def _stamp(dt: datetime) -> str:
    return dt.strftime("%Y%m%dT%H%M%S")


def build_ics(lessons: list[Lesson], assignments: list[Assignment],
              now: datetime | None = None) -> str:
    now = now or datetime.now()
    lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//VesperBoard//CN",
        "CALSCALE:GREGORIAN",
        "METHOD:PUBLISH",
        "X-WR-CALNAME:Vesper Board",
    ]

    for index, lesson in enumerate(lessons, start=1):
        start = to_local(lesson.start)
        end = to_local(lesson.end) or (start + timedelta(minutes=45) if start else None)
        if start is None or end is None:
            continue
        lines += [
            "BEGIN:VEVENT",
            "UID:lesson-%s-%s@vesper-board" % (index, _stamp(start)),
            "DTSTAMP:" + _stamp(now),
            "DTSTART:" + _stamp(start),
            "DTEND:" + _stamp(end),
            "SUMMARY:" + _escape(lesson.title),
        ]
        if lesson.location:
            lines.append("LOCATION:" + _escape(lesson.location))
        if lesson.teacher:
            lines.append("DESCRIPTION:" + _escape(lesson.teacher))
        lines.append("END:VEVENT")

    for assignment in assignments:
        due = to_local(assignment.due_at)
        if due is None or assignment.is_submitted:
            continue
        lines += [
            "BEGIN:VEVENT",
            "UID:assignment-%s@vesper-board" % assignment.id,
            "DTSTAMP:" + _stamp(now),
            "DTSTART:" + _stamp(due - timedelta(minutes=15)),
            "DTEND:" + _stamp(due),
            "SUMMARY:" + _escape("交：" + assignment.title),
            "DESCRIPTION:" + _escape(assignment.course_name),
        ]
        if assignment.html_url:
            lines.append("URL:" + assignment.html_url)
        lines.append("END:VEVENT")

    lines.append("END:VCALENDAR")
    return "\r\n".join(lines) + "\r\n"
