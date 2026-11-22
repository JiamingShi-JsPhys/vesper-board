"""本地定时提醒：点右键给某份作业定个时间，到点弹通知。

存在 archived.json 旁边（reminders.json），重启后仍然有效——所以这个功能
要求开机自启，否则程序不在跑就没人提醒。
"""

from __future__ import annotations

import json
from datetime import datetime

from . import paths


def _file():
    return paths.data_dir() / "reminders.json"


def load() -> list[dict]:
    path = _file()
    if not path.exists():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    if not isinstance(data, list):
        return []
    out = []
    for item in data:
        if not isinstance(item, dict):
            continue
        try:
            when = datetime.fromisoformat(str(item.get("when", "")))
        except ValueError:
            continue
        out.append({"id": int(item.get("id") or 0),
                    "title": str(item.get("title") or "作业"),
                    "when": when})
    return out


def _write(items: list[dict]) -> None:
    try:
        paths.write_text_atomic(_file(), json.dumps(
            [{"id": i["id"], "title": i["title"], "when": i["when"].isoformat(timespec="seconds")}
             for i in items], ensure_ascii=False, indent=2))
    except OSError:
        pass


def add(assignment_id: int, title: str, when: datetime) -> None:
    items = [i for i in load() if i["id"] != assignment_id]
    items.append({"id": assignment_id, "title": title, "when": when})
    _write(items)


def remove(assignment_id: int) -> None:
    _write([i for i in load() if i["id"] != assignment_id])


def due(now: datetime | None = None) -> list[dict]:
    now = now or datetime.now()
    return [i for i in load() if i["when"] <= now]


def upcoming(now: datetime | None = None) -> list[dict]:
    now = now or datetime.now()
    return sorted((i for i in load() if i["when"] > now), key=lambda i: i["when"])
