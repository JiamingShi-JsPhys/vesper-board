"""归档过的作业不该出现在「下一件」、角标和提醒里。"""

from __future__ import annotations

from datetime import datetime, timedelta

import pytest

from wsdock import archive
from wsdock.models import Assignment, Snapshot


def _assignment(aid: int, title: str, due: datetime) -> Assignment:
    return Assignment(id=aid, course_id=1, course_name="CS", title=title,
                      due_at=due, html_url="", submitted=False, graded=False,
                      submission_types=["online_upload"])


@pytest.fixture()
def snap():
    now = datetime.now()
    return Snapshot(
        assignments=[
            _assignment(1, "archived-one", now - timedelta(hours=16)),
            _assignment(2, "active-one", now + timedelta(days=2, hours=1)),
        ],
        canvas_ok=True, ams_ok=True,
    )


def test_active_skips_archived(monkeypatch, snap):
    import main
    monkeypatch.setattr(archive, "ids", lambda: {1})
    titles = [a.title for a in main.Dock._active(snap)]
    assert titles == ["active-one"]


def test_badge_ignores_archived(monkeypatch, snap):
    import main
    monkeypatch.setattr(archive, "ids", lambda: {1})

    class Stub:
        settings = type("S", (), {"badge_mode": "due"})()
        _badge_text = main.Dock._badge_text
        _active = staticmethod(main.Dock._active)

    # 归档那条已逾期 16 小时；若未过滤，角标会是 "-16h"
    assert Stub()._badge_text(snap) == "2d"
