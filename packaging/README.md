# 打包说明（1.0.0）

## 会打进包里的 / 不会的

| 打进包里 | 不打进包里 |
|---|---|
| `main.py`、`wsdock/`（应用代码） | `docs/` —— 本机截图与记录 |
| `assets/pet/`（形象素材） | `tools/` —— 会操作键鼠的生成脚本 |
| 图标（`build/icon.*`） | `tests/` |
| | `assets/ref_*.jpg` —— 校方参考图 |
| | `settings.json`、`*.bin`、`web-profile/`、`dock.log` |

后三类是**运行时**才在用户目录里生成的，仓库里本来就没有，打包也不会带上。
`%LOCALAPPDATA%\VesperBoard`（macOS: `~/Library/Application Support/VesperBoard`，
Linux: `~/.local/share/VesperBoard`）是每个用户自己的，跟安装包无关。

> 形象立绘是学校/第三方的角色 IP。自己用没问题；**公开发布安装包**要学校授权。
> 不想带立绘就删掉 `assets/pet/` 再打包，程序会自动退回矢量圆球。

## Windows

两种产物，都在本机可打。

**免安装版（文件夹）**

```powershell
powershell -ExecutionPolicy Bypass -File packaging\build_windows.ps1
```

产物：`dist\VesperBoard\VesperBoard.exe`（onedir，启动比 onefile 快，也少被
杀软误伤）。把整个 `dist\VesperBoard` 文件夹一起分发。

**安装包（.exe）**

```powershell
& "$env:TEMP\nsis\nsis-3.11\makensis.exe" packaging\windows_installer.nsi
```

产物：`dist\installer\VesperBoard-1.0.0-setup.exe`。装到
`%LOCALAPPDATA%\Programs\VesperBoard`，**不需要管理员权限**；带开始菜单 / 桌面
快捷方式、可选开机自启、以及卸载项（设置 → 应用 里能看到）。

**卸载与数据**：程序数据不在安装目录，而在 `%LOCALAPPDATA%\VesperBoard`
（设置、加密的登录会话、归档、日志）。卸载器会问一句要不要连它一起删，默认保留
——这样重装后不用重新登录。

## macOS

**必须在 Mac 上打**（PyInstaller 不做交叉编译）。

```bash
bash packaging/build_macos.sh
```

产物：`dist/Vesper Board.app`。没有签名/公证，首次打开会被 Gatekeeper 拦：

```bash
xattr -dr com.apple.quarantine "dist/Vesper Board.app"
```

## Linux

同样要在 Linux 上打：

```bash
bash packaging/build_linux.sh
```

WebEngine 需要一堆系统库，脚本开头列了 Debian/Ubuntu 的 apt 包名。

## 三个平台分别改了什么

| 能力 | Windows | macOS | Linux |
|---|---|---|---|
| 密钥存储 | DPAPI | 登录钥匙串（`security`） | `secret-tool`，没有就 0600 文件 |
| 开机自启 | Run 注册表 | `~/Library/LaunchAgents` | `~/.config/autostart` |
| 窗口层级 | `SetWindowPos` | Qt 置顶标志 | Qt 置顶标志 |
| 数据目录 | `%LOCALAPPDATA%` | `~/Library/Application Support` | `~/.local/share` |
| 登录窗口 | QtWebEngine | 同左 | 同左 |

macOS/Linux 的代码路径在这台 Windows 上没法实测——首次在那两个系统上跑，
先确认：登录窗能打开、钥匙串里出现 `VesperBoard` 条目、开机自启文件生成正确。

## 不想推到 GitHub 也能出三端包

`.github/workflows/build-desktop.yml` 只是把上面三条命令搬到 CI（三个 runner 各打各的）。
不想推源码的话，借一台 Mac 和一台 Linux 各跑一次脚本即可，命令完全一样。
本机没有 Linux 时，用 `scripts/wsl_build_linux.sh` 在 WSL 里交叉构建。


## 三个平台怎么出包

| 平台 | 命令 | 产物 |
|---|---|---|
| Windows | `powershell -File packaging/build_windows.ps1` | `dist\VesperBoard\VesperBoard.exe` |
| Linux | `bash packaging/build_linux.sh` | `dist/VesperBoard/VesperBoard` |
| macOS | `bash packaging/build_macos.sh` | `dist/Vesper Board.app` |

**macOS 只能在 macOS 上打**（PyInstaller 不做交叉编译）。没有 Mac 就用仓库里的
`.github/workflows/build-desktop.yml`：推一个 `v*` 标签或手动触发，三个平台的
产物都会作为 artifact 上传。

## 包里会自动裁掉的东西

构建脚本跑完 spec 后会执行 `_trim()`：

- `qtwebengine_devtools_resources*.pak`（调试面板，约 83 MB）
- Qt 翻译只留 `zh_CN / zh_TW / en`（约 44 MB → 1 MB）
- `qtwebengine_locales` 只留 `en-US / zh-CN / zh-TW`
- `assets/pet` 默认只留 `mascot`（默认小西）；要连测试角色一起打，
  设环境变量 `WESPER_SHIP_ALL_SKINS=1` 再构建

裁剪后：Windows 约 446 MB（压缩包 179 MB），Linux 约 574 MB（压缩包 215 MB）。
体积大头是 Qt WebEngine（内置登录窗，单个库约 195 MB），去掉它要改登录方式，
见 README 的讨论。

**Linux 包里有符号链接**：`_internal/libQt6*.so` 指向 `PySide6/Qt/lib/` 里的真文件，
PyInstaller 就是这么布局的。zip 用 `zip -y` 的语义保存链接本身，不会把 194 MB 的
`libQt6WebEngineCore.so` 存两份。解压时要用会保留符号链接的工具
（Linux 上的 `unzip`、`bsdtar`、文件管理器都行）；**用 Python 的 `zipfile` 解压会把
链接写成文本文件**，程序将无法启动。不想管这些就用 `.deb`。
