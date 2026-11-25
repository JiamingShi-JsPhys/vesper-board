# AGENTS.md

给在这个仓库里干活的编码代理看的速查表。用户读的说明在 `README.md`。

## 这是什么

Windows 桌面宠物：一颗悬浮球，展开是 Canvas 待交作业和 AMS 课表，作业能在球里直接提交。
Python 3.12 + PySide6，无后端、无遥测，只访问两个校内域名。

## 命令

```powershell
python main.py                     # 启动（先 python -m pip install -r requirements.txt）
python -m pytest tests -q          # 离线单测，不联网
python packaging/make_icon.py      # 由 assets/app_icon.png 生成 build/icon.ico / png
```

打包（详见 `packaging/README.md`）：

```powershell
python -m PyInstaller packaging/WestlakeDock.spec --noconfirm --clean --distpath dist --workpath build/pyinstaller
```

Linux 包没有对应系统时走 WSL：`scripts/wsl_build_linux.sh` → `scripts/wsl_pack_linux.sh`。

## 地图

| 路径 | 作用 |
|---|---|
| `main.py` | 入口：悬浮球、面板、托盘、气泡、主题切换的装配 |
| `wsdock/canvas.py` `ams.py` | 两个数据源的客户端；`worker.py` 是后台轮询线程 |
| `wsdock/security.py` `session.py` | DPAPI 加解密与会话落盘 |
| `wsdock/skins.py` `settings.py` | 形象清单、设置读写 |
| `wsdock/ui/` | `ball.py` 悬浮球、`panel.py` 面板、`settings_page.py` 设置页、`theme.py` 主题 |
| `assets/pet/<角色>/` | 运行时会读的形象素材，7 个状态 × 512×512 |
| `packs/` | 可导入的默认形象包，不进 1.0.0 安装包 |
| `releases/` | 1.0.0 / 1.1.0 待发布快照，不参与开发 |
| `_archive/` | 美术现场与旧 CI，不参与运行，已在 `.gitignore` |

## 约定

- **主题**：不要在控件里写死颜色。用 `wsdock/ui/theme.py` 的 `ink()` / `nav_text()`，
  QSS 里用 `__INKn__` / `__TEXT__` / `__NAV__` 令牌；写死颜色会在浅色模式下瞎掉。
- **形象**：512×512 透明 PNG，脚底落在 y=496，头部高度约 400。缺状态回落 idle。
  抠图流程见 `_archive/README.md` 与 `docs/character-design.md`。
- **素材与代码分开**：`assets/` 只放运行时读的；中间稿、原图、截图一律进 `_archive/art/`。
- **用户数据**：`settings.json`、`*.bin`、`web-profile/` 都是运行时生成的，
  不提交、不进安装包。运行中的程序会回写设置，改测试数据前先退出程序。
- **网络**：带凭据的请求只发往 `canvas.westlake.edu.cn` 与 `ams.westlake.edu.cn`；
  Canvas 返回的上传/附件地址可能指向对象存储，那类请求必须走 `TransferSession`（无凭据），
  跨来源绝对 URL 直接拒绝。改 `wsdock/net.py` 前先读 `docs/security-audit.md` 的 1.0.0 复查一节。
- **落盘加密**：用户数据（settings / archived / reminders / dock.log）一律走
  `wsdock/vault.py` 的 AES-256-GCM，主密钥由 DPAPI / 钥匙串封装；新增持久化文件也用
  `vault.read_json` / `write_json` / `append_log`，不要直接 `open()` 写明文。
  日志明文只能通过「设置 → 高级 → 导出诊断日志」导出。
- **不要提交或发布**：`git commit` / `push` / `tag` 与任何 Release 都要先问用户。

## 已知坑

- Java / Gradle 在本机跑不起来（`Selector.open()` → `Invalid argument: connect`），
  安卓端必须去 WSL 里构建，见 `Coding/Vesper_Board_Android` 的 `wsl_*.sh`。
- macOS `.app` 本机产不出，只能走 CI。
- `tests/` 全部离线；联网行为不要写进单测。
