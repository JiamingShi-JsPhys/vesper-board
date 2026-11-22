#!/usr/bin/env bash
# 在 Linux 上打出 dist/WestlakeDock/WestlakeDock
# 需要系统库（Debian/Ubuntu）：
#   sudo apt install -y libgl1 libegl1 libxkbcommon-x11-0 libxcb-cursor0 \
#        libxcb-icccm4 libxcb-image0 libxcb-keysyms1 libxcb-randr0 \
#        libxcb-render-util0 libxcb-shape0 libnss3 libasound2
set -euo pipefail
cd "$(dirname "$0")/.."

python3 -m venv .venv-build
./.venv-build/bin/python -m pip install --upgrade pip
./.venv-build/bin/python -m pip install -r requirements.txt pyinstaller pillow

./.venv-build/bin/python packaging/make_icon.py
./.venv-build/bin/python -m PyInstaller packaging/WestlakeDock.spec --noconfirm --clean \
    --distpath dist --workpath build/pyinstaller

echo
echo "输出：dist/WestlakeDock/WestlakeDock"
