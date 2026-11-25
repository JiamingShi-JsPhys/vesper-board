#!/bin/sh
set -eu
WIN_ROOT=$(cd "$(dirname "$0")/.." && pwd)
DIST="$HOME/vesper-linux/dist"
PET="$DIST/VesperBoard/_internal/assets/pet"
if [ -d "$PET" ]; then
  for d in alpha beta gamma delta xiaoxi; do rm -rf "$PET/$d"; done
  ls "$PET"
fi

cd "$DIST/VesperBoard/_internal/PySide6"
# Windows 构建把资源放在 PySide6/resources，Linux 放在 PySide6/Qt/resources——
# 两处都要删，否则 12 MB 的 devtools 面板会跟着发行包走。
for res in resources Qt/resources; do
  rm -f "$res/qtwebengine_devtools_resources.pak" \
        "$res/qtwebengine_devtools_resources.debug.pak"
done
find translations -maxdepth 1 -type f \( -name '*.qm' -o -name '*.pak' \) \
  ! -name '*_zh_CN*' ! -name '*_zh_TW*' ! -name '*_en*' -delete 2>/dev/null || true
find translations/qtwebengine_locales -type f \
  ! -name 'en-US.pak' ! -name 'zh-CN.pak' ! -name 'zh-TW.pak' -delete 2>/dev/null || true

cd "$DIST"
python3 - <<'PY'
import os, zipfile, time
os.chdir(os.path.join(os.environ["HOME"], "vesper-linux", "dist"))
name = 'VesperBoard-1.0.2-linux-x86_64'
if os.path.exists(name + '.zip'):
    os.remove(name + '.zip')

# PyInstaller 在 _internal/ 根部放的是指向 PySide6/Qt/lib 的符号链接。
# shutil.make_archive 会把链接解引用，导致 194 MB 的 libQt6WebEngineCore.so
# 在包里存两份（zip 从 230 MB 涨到 375 MB）。这里保留链接条目本身。
t0 = time.time()
with zipfile.ZipFile(name + '.zip', 'w', zipfile.ZIP_DEFLATED, 9) as z:
    for root, dirs, files in os.walk('VesperBoard'):
        dirs.sort()
        for entry in dirs + sorted(files):
            path = os.path.join(root, entry)
            if os.path.islink(path):
                info = zipfile.ZipInfo(path)
                info.create_system = 3                      # Unix
                info.external_attr = (0o120777 & 0xFFFF) << 16
                z.writestr(info, os.readlink(path))
            elif os.path.isfile(path):
                z.write(path, path)

print('zip MB', os.path.getsize(name + '.zip') // 1048576,
      'secs', round(time.time() - t0))
PY
du -sh VesperBoard
cp VesperBoard-1.0.2-linux-x86_64.zip "$WIN_ROOT/dist/"
