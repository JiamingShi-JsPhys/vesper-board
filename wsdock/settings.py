"""User settings, persisted as JSON (never contains secrets)."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from urllib.parse import urlsplit

from . import paths

DEFAULT_CANVAS = "https://canvas.westlake.edu.cn"
DEFAULT_AMS = "https://ams.westlake.edu.cn"

# settings.json 放在用户目录下，同一用户跑的其它程序都能改它。里面的 base URL
# 会被拿去发请求、带着会话 cookie，所以只认学校的 https 域名——否则 cookie 就
# 可能被送到别处（DeepSec 的 sast_ssrf 报的就是这一条）。
_ALLOWED_HOSTS = ("westlake.edu.cn",)


def safe_base_url(value: str, default: str) -> str:
    try:
        parsed = urlsplit(str(value or "").strip())
    except ValueError:
        return default
    host = (parsed.hostname or "").lower()
    if parsed.scheme != "https" or not host:
        return default
    if not any(host == h or host.endswith("." + h) for h in _ALLOWED_HOSTS):
        return default
    try:
        port = parsed.port
    except ValueError:
        return default
    # 用 hostname 重建，丢掉 user:pass@ ——否则 basic 凭据会跟着请求发出去
    return "%s://%s" % (parsed.scheme, host if port is None else "%s:%d" % (host, port))


@dataclass
class Settings:
    canvas_url: str = DEFAULT_CANVAS
    ams_url: str = DEFAULT_AMS
    poll_minutes: int = 5
    ball_x: int | None = None
    panel_w: int = 760
    panel_h: int = 620
    ball_y: int | None = None
    panel_section: str = "homework"       # homework | schedule
    opacity: float = 1.0
    show_badge: bool = False       # 右上角红/黄点：默认关
    pet_glow: bool = False         # 小球背后的柔光：默认关
    user_name: str = ""            # Canvas 上的名字，用于问候语
    star_hint: bool = False        # 已点过/关掉「给项目点个 Star」气泡
    start_with_windows: bool = False
    window_level: str = "top"      # top | normal | desktop
    show_older: bool = True        # 逾期超过一周那一组
    show_far: bool = True          # 14 天以后 / 无截止那一组
    show_reminders: bool = False   # 仅提醒（不用交）那一组，默认不显示
    overdue_days: int = 7          # 超过几天算「更早」
    ahead_days: int = 14           # 提前几天算「更晚」
    first_run_done: bool = False
    course_colors: dict = field(default_factory=dict)
    last_seen_notice: str = ""
    read_notices: list = field(default_factory=list)
    language: str = "system"   # system | zh | en
    theme_mode: str = "system"  # system | light | dark
    pet_skin: str = "icon"     # icon = APP 图标球；其余是 assets/pet/<name>/
    pet_size: int = 92         # 立绘显示边长（px），有图时生效
    badge_mode: str = "count"  # count = 待交数量，due = 离最近截止还有多久
    class_reminders: bool = True
    class_remind_minutes: int = 10
    daily_brief: bool = True
    quiet_start: int = 23      # 勿扰开始（24 小时制）
    quiet_end: int = 7
    last_brief_day: str = ""   # YYYY-MM-DD，早报每天只发一次
    use_embedded_login: bool = True

    @classmethod
    def load(cls) -> "Settings":
        f = paths.settings_file()
        if not f.exists():
            return cls()
        try:
            raw = json.loads(f.read_text(encoding="utf-8"))
        except Exception:
            return cls()
        known = {k: v for k, v in raw.items() if k in cls.__dataclass_fields__}
        obj = cls(**known)
        obj.canvas_url = safe_base_url(obj.canvas_url, DEFAULT_CANVAS)
        obj.ams_url = safe_base_url(obj.ams_url, DEFAULT_AMS)
        return obj

    def save(self) -> None:
        paths.write_text_atomic(
            paths.settings_file(),
            json.dumps(asdict(self), ensure_ascii=False, indent=2),
        )
