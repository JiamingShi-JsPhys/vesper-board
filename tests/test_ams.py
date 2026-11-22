"""Tests for the AMS timetable client (payload shape copied from the live API)."""

from __future__ import annotations

from datetime import date, datetime, timedelta

from wsdock.ams import AmsClient, clean_location, _to_dt


def sample_payload(day: str, title: str, start: str, end: str, kind: str = "上课") -> dict:
    return {
        "code": 0,
        "data": {
            "schedule": {
                day: {
                    "calendarList": [
                        {
                            "id": "abc",
                            "title": title,
                            "startDateStr": f"{day} {start}",
                            "endDateStr": f"{day} {end}",
                            "startTime": start,
                            "endTime": end,
                            "address": "Campus of YUNGUE13E13-207,Yungu",
                            "scheduleType": {"name": kind, "color": "#4585FE"},
                        }
                    ]
                }
            }
        },
        "ok": True,
    }


def test_to_dt_parses_ams_timestamps():
    assert _to_dt("2026-11-20 09:50") == datetime(2026, 11, 20, 9, 50)
    assert _to_dt("2026-11-20 09:50:00") == datetime(2026, 11, 20, 9, 50)
    assert _to_dt(None) is None


def test_clean_location_extracts_room():
    assert clean_location("Campus of YUNGUE13E13-207,Yungu") == "E13-207"
    assert clean_location("Campus of YUNGUE13E13-505,Yungu") == "E13-505"
    assert clean_location("") == ""


def test_calendars_unwraps_schedule_map():
    client = AmsClient("https://ams.westlake.edu.cn", cookies={"SESSION": "x"})
    captured = {}

    def fake_get(path, params=None):
        captured["path"] = path
        captured["params"] = params
        return sample_payload("2026-11-20", "Probability", "08:00", "10:35")

    client._get = fake_get                       # type: ignore[assignment]
    days = client.calendars(date(2026, 11, 20), date(2026, 11, 20))

    assert list(days) == ["2026-11-20"]
    assert days["2026-11-20"][0]["title"] == "Probability"
    assert captured["path"] == "/api/v1/schedule/get-calendars"
    assert captured["params"]["startDateStr"] == "2026-11-20"
    assert captured["params"]["reqType"] == "DateView"
    assert captured["params"]["identity"] == "STUDENT"


def test_lessons_become_models_and_filter_non_courses():
    client = AmsClient("https://ams.westlake.edu.cn", cookies={"SESSION": "x"})

    def fake_get(path, params=None):
        payload = sample_payload("2026-11-20", "Communication", "09:50", "12:15")
        other = {
            "title": "社团活动", "startDateStr": "2026-11-20 18:00",
            "endDateStr": "2026-11-20 19:00", "address": "",
            "scheduleType": {"name": "个人日程"},
        }
        payload["data"]["schedule"]["2026-11-20"]["calendarList"].append(other)
        return payload

    client._get = fake_get                       # type: ignore[assignment]
    lessons = client.lessons(date(2026, 11, 20), date(2026, 11, 20))

    assert [l.title for l in lessons] == ["Communication"]
    assert lessons[0].start == datetime(2026, 11, 20, 9, 50)
    assert lessons[0].location == "E13-207"

    everything = client.lessons(date(2026, 11, 20), date(2026, 11, 20), courses_only=False)
    assert len(everything) == 2


def test_lessons_today_splits_today_and_tomorrow():
    client = AmsClient("https://ams.westlake.edu.cn", cookies={"SESSION": "x"})
    today = date.today()
    tomorrow = today + timedelta(days=1)

    def fake_get(path, params=None):
        if path.endswith("get-calendars"):
            merged = sample_payload(today.isoformat(), "今天的课", "09:00", "10:35")["data"]["schedule"]
            merged.update(sample_payload(tomorrow.isoformat(), "明天的课", "13:30", "15:05")["data"]["schedule"])
            return {"code": 0, "data": {"schedule": merged}}
        return {"code": 0, "data": {"personName": "测试", "weekIndex": "12"}}

    client._get = fake_get                       # type: ignore[assignment]
    today_list, tomorrow_list, meta = client.lessons_today()

    assert [l.title for l in today_list] == ["今天的课"]
    assert [l.title for l in tomorrow_list] == ["明天的课"]
    assert meta["week"] == "12"


def test_error_code_becomes_ams_error():
    import pytest
    client = AmsClient("https://ams.westlake.edu.cn", cookies={"SESSION": "x"})

    class FakeResp:
        status_code = 200
        def json(self):
            return {"code": 4006, "msg": "查询关键字不能为空！"}

    client.session.get = lambda *a, **k: FakeResp()   # type: ignore[assignment]
    with pytest.raises(Exception) as excinfo:
        client._get("/api/v1/schedule/search")
    assert "不能为空" in str(excinfo.value)
