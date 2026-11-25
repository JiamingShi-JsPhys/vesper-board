"""One place for the version string the UI and the installer agree on."""

from __future__ import annotations

APP_NAME = "Vesper Board"
ZH_NAME = "晚星看板"
VERSION = "1.0.2"


def version_line() -> str:
    return "%s · %s %s" % (ZH_NAME, APP_NAME, VERSION)
