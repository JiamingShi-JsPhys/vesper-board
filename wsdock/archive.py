"""Local archive: assignments you decided not to do.

Canvas has no notion of "this one doesn't apply to me" — assistantships,
already-credited transfer work, or homework from a course you dropped. The
archive lives on this machine only and never talks to Canvas.
"""

from __future__ import annotations

import json
from datetime import datetime

from . import paths
from .models import Assignment


def _file():
    return paths.data_dir() / "archived.json"


def load() -> dict[str, dict]:
    path = _file()
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    if not isinstance(data, dict):
        return {}
    return {str(k): v for k, v in data.items() if isinstance(v, dict)}


def ids() -> set[int]:
    out: set[int] = set()
    for key in load():
        try:
            out.add(int(key))
        except ValueError:
            continue
    return out


def count() -> int:
    return len(load())


def add(assignment: Assignment) -> None:
    data = load()
    due = assignment.due_at
    data[str(assignment.id)] = {
        "title": assignment.title,
        "course": assignment.course_name,
        "course_id": assignment.course_id,
        "due": due.isoformat() if due else "",
        "html_url": assignment.html_url,
        "archived_at": datetime.now().isoformat(timespec="seconds"),
    }
    _write(data)


def remove(assignment_id: int) -> None:
    data = load()
    if data.pop(str(assignment_id), None) is not None:
        _write(data)


def entries() -> list[Assignment]:
    """Archived items rendered as read-only assignments (for the 恢复 row)."""
    out: list[Assignment] = []
    for key, meta in sorted(load().items(), key=lambda kv: kv[1].get("archived_at", ""), reverse=True):
        try:
            assignment_id = int(key)
        except ValueError:
            continue
        due = None
        if meta.get("due"):
            try:
                due = datetime.fromisoformat(meta["due"])
            except ValueError:
                due = None
        out.append(Assignment(
            id=assignment_id,
            course_id=int(meta.get("course_id") or 0),
            course_name=str(meta.get("course") or ""),
            title=str(meta.get("title") or "（已归档）"),
            due_at=due,
            html_url=str(meta.get("html_url") or ""),
            submitted=False,
            graded=False,
            submission_types=["none"],
        ))
    return out


def _write(data: dict) -> None:
    try:
        paths.write_text_atomic(
            _file(), json.dumps(data, ensure_ascii=False, indent=2))
    except OSError:
        pass
