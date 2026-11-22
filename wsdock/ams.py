"""AMS (Supwisdom portal) client — where the timetable comes from.

Verified live on 2026-11-20:

    GET {base}/portal-service/api/v1/schedule/get-calendars
        ?startDateStr=YYYY-MM-DD&endDateStr=YYYY-MM-DD&reqType=DateView&identity=STUDENT

Authenticated with the browser's HttpOnly `SESSION` cookie (same idea as
Canvas). The reply looks like:

    {"code":0,"data":{"schedule":{"2026-11-20":{"calendarList":[
        {"title":"...","startDateStr":"2026-11-20 09:50",
         "endDateStr":"2026-11-20 12:15","address":"Campus of ...YUNGUE13E13-207,Yungu",
         "scheduleType":{"name":"上课","color":"#4585FE"}}]}}}}
"""

from __future__ import annotations

import re
from datetime import date, datetime, timedelta
from typing import Any

import requests

from .net import GuardedSession, set_cookies
from .models import Lesson, Notice

USER_AGENT = "Mozilla/5.0 VesperBoard/1.0"
COURSE_TYPE_NAMES = {"上课", "课程", "course"}


class AmsError(RuntimeError):
    pass


def _to_dt(text: str | None) -> datetime | None:
    if not text:
        return None
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%d"):
        try:
            return datetime.strptime(text.strip()[: len(fmt) + 4], fmt)
        except ValueError:
            continue
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None


def clean_location(address: str | None) -> str:
    """'Campus of YUNGUE13E13-207,Yungu' -> 'E13-207'."""
    if not address:
        return ""
    match = re.search(r"([A-Z]{1,3}\d{1,3}\s*-\s*\d{2,4})", address)
    if match:
        return match.group(1).replace(" ", "")
    text = address.replace("Campus of ", "").strip()
    return text.split(",")[0].strip()


class AmsClient:
    def __init__(self, base_url: str, cookies: dict[str, str] | None = None,
                 timeout: int = 20):
        self.base = base_url.rstrip("/") + "/portal-service"
        self.timeout = timeout
        self.session = GuardedSession()
        self.session.headers.update({
            "Accept": "application/json, text/plain, */*",
            "User-Agent": USER_AGENT,
            "Referer": base_url.rstrip("/") + "/home/",
        })
        if cookies:
            # 绑到 AMS 自己的主机，避免无域名 cookie 被发给任意站点。
            set_cookies(self.session.cookies, base_url, cookies)

    # ------------------------------------------------------------------ http
    def _get(self, path: str, params: dict | None = None) -> Any:
        url = f"{self.base}{path}"
        try:
            resp = self.session.get(url, params=params, timeout=self.timeout)
        except requests.RequestException as exc:
            raise AmsError(f"网络不通：{exc}") from exc
        if resp.status_code in (401, 403):
            raise AmsError("AMS 登录已失效，请重新登录")
        if resp.status_code >= 400:
            raise AmsError(f"AMS 返回 {resp.status_code}")
        try:
            payload = resp.json()
        except ValueError as exc:
            raise AmsError("AMS 返回的不是 JSON（可能被重定向到登录页）") from exc
        if isinstance(payload, dict) and payload.get("code") not in (0, None):
            raise AmsError(payload.get("msg") or "AMS 返回错误")
        return payload

    # ------------------------------------------------------------------- api
    def profile(self) -> dict:
        payload = self._get("/api/v1/home/index", {"identity": "STUDENT"})
        return payload.get("data") or {}

    def calendars(self, start: date, end: date) -> dict[str, list[dict]]:
        payload = self._get("/api/v1/schedule/get-calendars", {
            "startDateStr": start.isoformat(),
            "endDateStr": end.isoformat(),
            "reqType": "DateView",
            "identity": "STUDENT",
        })
        schedule = ((payload.get("data") or {}).get("schedule") or {})
        days: dict[str, list[dict]] = {}
        for day, entry in schedule.items():
            items = (entry or {}).get("calendarList") or []
            if items:
                days[day] = items
        return days

    def lessons(self, start: date, end: date, courses_only: bool = True) -> list[Lesson]:
        out: list[Lesson] = []
        for _day, items in sorted(self.calendars(start, end).items()):
            for item in items:
                lesson = self._to_lesson(item)
                if lesson is None:
                    continue
                if courses_only and not self._is_course(item):
                    continue
                out.append(lesson)
        out.sort(key=lambda x: x.start or datetime.max)
        return out

    def lessons_today(self) -> tuple[list[Lesson], list[Lesson], dict]:
        today = date.today()
        tomorrow = today + timedelta(days=1)
        all_lessons = self.lessons(today, tomorrow)
        today_list = [l for l in all_lessons if l.start and l.start.date() == today]
        tomorrow_list = [l for l in all_lessons if l.start and l.start.date() == tomorrow]
        meta = {"count": len(all_lessons), "week": self._week_number()}
        return today_list, tomorrow_list, meta

    def week(self) -> list[Lesson]:
        """Today through six days ahead, in one request."""
        today = date.today()
        return self.lessons(today, today + timedelta(days=6))

    def notices(self) -> list[Notice]:
        payload = self._get("/api/v1/notice-view/get-all-notice", {})
        data = (payload or {}).get("data") or {}
        if not isinstance(data, dict):
            return []
        items = data.get("allNotices") or data.get("noReadNotices") or []
        out: list[Notice] = []
        for item in items:
            if not isinstance(item, dict):
                continue
            title = item.get("title") or item.get("noticeTitle") or ""
            if not title:
                continue
            posted = item.get("publishTime") or item.get("publishDate") or item.get("createTime")
            out.append(Notice(
                uid="ams-%s" % (item.get("id") or item.get("noticeId") or title[:20]),
                title=str(title),
                posted_at=_to_dt(str(posted)) if posted else None,
                url="",
                source="ams",
            ))
        out.sort(key=lambda n: n.posted_at or datetime.min, reverse=True)
        return out

    def _week_number(self) -> str:
        try:
            return str(self.profile().get("weekIndex") or "")
        except AmsError:
            return ""

    @staticmethod
    def _is_course(item: dict) -> bool:
        kind = (item.get("scheduleType") or {}).get("name") or ""
        return kind.strip().lower() in COURSE_TYPE_NAMES

    def _to_lesson(self, item: dict) -> Lesson | None:
        title = item.get("title")
        if not title:
            return None
        start = _to_dt(item.get("startDateStr") or item.get("startDate"))
        end = _to_dt(item.get("endDateStr") or item.get("endDate"))
        return Lesson(
            title=str(title),
            start=start,
            end=end,
            location=clean_location(item.get("address")),
            teacher=str(item.get("teacherName") or ""),
            raw=item,
        )
