#!/bin/sh
set -eu
WIN=$(cd "$(dirname "$0")/.." && pwd)
DST="$HOME/vesper-linux"
rm -rf "$DST"
mkdir -p "$DST"
cp -r "$WIN"/main.py "$WIN"/wsdock "$WIN"/assets "$WIN"/packaging \
      "$WIN"/requirements.txt "$WIN"/licenses "$WIN"/LICENSE \
      "$WIN"/THIRD_PARTY_LICENSES.txt "$DST"/
cd "$DST"
export PATH="$HOME/.local/bin:$PATH"
uv venv --python 3.12 .venv-build
uv pip install --python .venv-build/bin/python -r requirements.txt pyinstaller pillow
.venv-build/bin/python packaging/make_icon.py
.venv-build/bin/python -m PyInstaller packaging/WestlakeDock.spec --noconfirm --clean \
    --distpath dist --workpath build/pyinstaller > /tmp/pyi-linux.log 2>&1 || true
echo "--- tail"
tail -8 /tmp/pyi-linux.log
echo "--- size"
du -sh dist/VesperBoard 2>/dev/null || echo NO_DIST
ls dist/VesperBoard 2>/dev/null | head -5
