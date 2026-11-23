#!/usr/bin/env bash
# 把 dist/WestlakeDock 打成一个 .deb（在 Linux / WSL 里跑，PyInstaller 已经构建完）
set -euo pipefail
cd "$(dirname "$0")/.."
[ -d dist/WestlakeDock ] || { echo "先跑 packaging/build_linux.sh"; exit 1; }

VER="1.0.1"
PKG="westlake-dock_${VER}_amd64"
ROOT="build/deb/$PKG"
rm -rf "build/deb" && mkdir -p "$ROOT/DEBIAN" \
    "$ROOT/usr/lib/westlake-dock" \
    "$ROOT/usr/bin" \
    "$ROOT/usr/share/applications" \
    "$ROOT/usr/share/icons/hicolor/256x256/apps"

cp -r dist/WestlakeDock/. "$ROOT/usr/lib/westlake-dock/"
cp build/icon.png "$ROOT/usr/share/icons/hicolor/256x256/apps/westlake-dock.png"

cat > "$ROOT/usr/bin/westlake-dock" <<'SH'
#!/bin/sh
exec /usr/lib/westlake-dock/WestlakeDock "$@"
SH
chmod 755 "$ROOT/usr/bin/westlake-dock"

cat > "$ROOT/usr/share/applications/westlake-dock.desktop" <<'DESK'
[Desktop Entry]
Type=Application
Name=西湖课业助手
Name[en]=Westlake Dock
Comment=Canvas 作业与 AMS 课表
Exec=westlake-dock
Icon=westlake-dock
Terminal=false
Categories=Education;Utility;
DESK

cat > "$ROOT/DEBIAN/control" <<DESK
Package: westlake-dock
Version: ${VER}
Section: utils
Priority: optional
Architecture: amd64
Maintainer: Westlake Dock <noreply@example.com>
Description: 西湖课业助手
 Canvas 作业提醒、AMS 课表、成绩与消息，桌面悬浮球常驻。
DESK

mkdir -p dist
dpkg-deb --build --root-owner-group "$ROOT" "dist/${PKG}.deb"
echo "输出：dist/${PKG}.deb"
