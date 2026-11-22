"""Turn a flat assignment list into what the panel actually shows.

Two rules decide everything here:

* **Reminders are not homework.** Canvas marks assignments that need nothing
  handed in with `submission_types: ["none"]`; they must not inflate the count
  or take the "next up" slot.
* **The list has to stay short.** Anything overdue by more than a week, or due
  more than two weeks out, is folded away instead of pushed into your face.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta

from .models import Assignment

OVERDUE_DAYS = 7
AHEAD_DAYS = 14
URGENT_HOURS = 24


def local_due(assignment: Assignment) -> datetime | None:
    """Due time as a naive local datetime, so comparisons never mix timezones."""
    due = assignment.due_at
    if due is None:
        return None
    return due.astimezone().replace(tzinfo=None) if due.tzinfo else due


@dataclass
class Agenda:
    overdue: list[Assignment] = field(default_factory=list)
    today: list[Assignment] = field(default_factory=list)
    tomorrow: list[Assignment] = field(default_factory=list)
    this_week: list[Assignment] = field(default_factory=list)
    later: list[Assignment] = field(default_factory=list)
    older: list[Assignment] = field(default_factory=list)     # 逾期超过 7 天
    far: list[Assignment] = field(default_factory=list)       # 14 天以后 / 无截止
    reminders: list[Assignment] = field(default_factory=list)  # 无需提交
    submitted: list[Assignment] = field(default_factory=list)  # 已交过

    next_item: Assignment | None = None
    urgent: bool = False

    @property
    def actionable(self) -> int:
        return (len(self.overdue) + len(self.today) + len(self.tomorrow)
                + len(self.this_week) + len(self.later)
                + len(self.older) + len(self.far))

    @property
    def visible(self) -> int:
        return (len(self.overdue) + len(self.today) + len(self.tomorrow)
                + len(self.this_week) + len(self.later))

    @property
    def empty(self) -> bool:
        return self.actionable == 0


def build(items: list[Assignment], now: datetime | None = None,
          overdue_days: int = OVERDUE_DAYS, ahead_days: int = AHEAD_DAYS,
          include_older: bool = True, include_far: bool = True,
          include_reminders: bool = True, include_submitted: bool = True) -> Agenda:
    now = now or datetime.now()
    today = now.date()
    agenda = Agenda()

    actionable: list[tuple[datetime | None, Assignment]] = []
    for item in items:
        if item.is_submitted:
            if include_submitted:
                agenda.submitted.append(item)
            continue
        if item.is_reminder:
            if include_reminders:
                agenda.reminders.append(item)
        else:
            actionable.append((local_due(item), item))

    actionable.sort(key=lambda pair: (pair[0] is None, pair[0] or now))
    agenda.reminders.sort(key=lambda a: (local_due(a) is None, local_due(a) or now))
    agenda.submitted.sort(key=lambda a: local_due(a) or now)

    for due, item in actionable:
        if due is None:
            if include_far:
                agenda.far.append(item)
            continue
        if due < now:
            if now - due > timedelta(days=overdue_days):
                if include_older:
                    agenda.older.append(item)
            else:
                agenda.overdue.append(item)
            continue
        days = (due.date() - today).days
        if days == 0:
            agenda.today.append(item)
        elif days == 1:
            agenda.tomorrow.append(item)
        elif days < 7:
            agenda.this_week.append(item)
        elif days < ahead_days:
            agenda.later.append(item)
        else:
            if include_far:
                agenda.far.append(item)

    for bucket in (agenda.overdue, agenda.today, agenda.tomorrow,
                   agenda.this_week, agenda.later, agenda.older, agenda.far):
        if bucket:
            agenda.next_item = bucket[0]
            break

    for due, item in actionable:
        if due is None:
            continue
        # 逾期超过 overdue_days 的会折叠进「更早」：既不显示、也不计入数字，
        # 就不该再让人物摆出紧张表情。否则「下一件还剩 4 天」配一张冷汗脸。
        if due < now and now - due > timedelta(days=overdue_days):
            continue
        if due <= now + timedelta(hours=URGENT_HOURS):
            agenda.urgent = True
            break

    return agenda
