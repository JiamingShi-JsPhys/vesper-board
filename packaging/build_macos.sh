#!/usr/bin/env bash
# 在 macOS 上打出 dist/Westlake Dock.app
set -euo pipefail
cd "$(dirname "$0")/.."

python3 -m venv .venv-build
./.venv-build/bin/python -m pip install --upgrade pip
./.venv-build/bin/python -m pip install -r requirements.txt pyinstaller pillow

./.venv-build/bin/python packaging/make_icon.py
# .icns 用系统自带 iconutil；没有就跳过，BUNDLE 会用默认图标
if command -v iconutil >/dev/null; then
  ./.venv-build/bin/python packaging/make_iconset.py
  iconutil -c icns build/icon.iconset -o build/icon.icns
fi

./.venv-build/bin/python -m PyInstaller packaging/WestlakeDock.spec --noconfirm --clean \
    --distpath dist --workpath build/pyinstaller

echo
echo "输出：dist/Westlake Dock.app"
echo "首次打开会被 Gatekeeper 拦：右键 → 打开，或 xattr -dr com.apple.quarantine \"dist/Westlake Dock.app\""
