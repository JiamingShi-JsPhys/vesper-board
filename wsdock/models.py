"""Plain data objects shared by the network layer and the UI."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional


@dataclass
class Assignment:
    id: int
    course_id: int
    course_name: str
    title: str
    due_at: Optional[datetime]
    html_url: str
    submitted: bool
    graded: bool
    submission_types: list[str] = field(default_factory=list)
    points_possible: Optional[float] = None
    score: Optional[float] = None
    quiz: bool = False
    discussion: bool = False
    submitted_at: datetime | None = None

    @property
    def is_submitted(self) -> bool:
        return bool(self.submitted or self.submitted_at or self.graded)

    @property
    def can_upload(self) -> bool:
        return "online_upload" in self.submission_types

    @property
    def needs_submission(self) -> bool:
        """False for Canvas assignments that are only a reminder.

        Canvas marks those with `submission_types: ["none"]` (see the
        "Homework (No submission required)" rows) — nothing to hand in.
        """
        kinds = [str(k).lower() for k in self.submission_types]
        if not kinds:
            return False
        return "none" not in kinds

    @property
    def is_reminder(self) -> bool:
        return not self.needs_submission

    @property
    def days_left(self) -> Optional[float]:
        if not self.due_at:
            return None
        return (self.due_at - datetime.now(self.due_at.tzinfo)).total_seconds() / 86400


@dataclass
class Attachment:
    id: int
    name: str
    size: int = 0
    content_type: str = ""
    url: str = ""

    @property
    def size_text(self) -> str:
        if self.size <= 0:
            return ""
        if self.size < 1024:
            return f"{self.size} B"
        if self.size < 1024 * 1024:
            return f"{self.size / 1024:.0f} KB"
        return f"{self.size / 1024 / 1024:.1f} MB"


@dataclass
class AssignmentDetail:
    assignment: Assignment
    description: str = ""                 # 纯文本化的作业要求
    attachments: list[Attachment] = field(default_factory=list)   # 描述里链接的文件
    course_files: list[Attachment] = field(default_factory=list)  # 课程文件（讲义等）
    error: str = ""


@dataclass
class GradeItem:
    name: str
    score: float | None
    points: float | None
    graded_at: datetime | None = None


@dataclass
class CourseGrade:
    course_id: int
    name: str
    current: float | None = None
    final: float | None = None
    items: list["GradeItem"] = field(default_factory=list)


@dataclass
class Notice:
    uid: str
    title: str
    posted_at: datetime | None = None
    url: str = ""
    source: str = "canvas"
    course: str = ""
    body: str = ""


@dataclass
class Lesson:
    title: str
    start: Optional[datetime]
    end: Optional[datetime]
    location: str = ""
    teacher: str = ""
    raw: dict = field(default_factory=dict)


@dataclass
class Snapshot:
    """Everything one refresh produced, handed to the UI in a single signal."""

    assignments: list[Assignment] = field(default_factory=list)
    lessons: list[Lesson] = field(default_factory=list)
    lessons_tomorrow: list[Lesson] = field(default_factory=list)
    lessons_week: list[Lesson] = field(default_factory=list)
    grades: list[CourseGrade] = field(default_factory=list)
    notices: list[Notice] = field(default_factory=list)
    updated_at: Optional[datetime] = None
    canvas_ok: bool = False
    canvas_error: str = ""
    user_name: str = ""
    ams_ok: bool = False
    ams_error: str = ""
