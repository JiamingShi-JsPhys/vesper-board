# 安全审查 · 西湖课业助手（2026-11-20）

范围：`main.py`、`wsdock/`、`tools/`、`tests/`（共 34 个 py 文件，约 7100 行），
运行环境 `%LOCALAPPDATA%\VesperBoard`。

## 一、结论

| 项 | 结果 |
|---|---|
| 硬编码密钥 / 令牌 | 无 |
| 凭据落盘 | Windows DPAPI 加密，仅本机本用户可解 |
| 依赖真实性 | 5 个第三方包全部真实存在，无幻觉包 |
| 出网域名 | 只有学校两个域名，无遥测 |
| DeepSec | 1 条 medium（开发工具，非发布代码） |
| 发现并修复 | 3 处（见第五节） |

## 二、密钥

- 全仓扫描 `api_key|secret|password|token=|Bearer|sk-…|AKIA…|ghp_…`：只命中
  `canvas.py` 里拼 `Authorization` 头和 i18n 里的说明文案，**没有任何字面量密钥**。
- 令牌与会话存 `canvas_token.bin` / `canvas_session.bin` / `ams_session.bin`，
  由 `wsdock/security.py` 走 `CryptProtectData`（带固定 entropy、
  `CRYPTPROTECT_UI_FORBIDDEN`）。文件被拷到别的机器 / 别的 Windows 账号下无法解密。
- 空值会直接删除文件；登出同样 unlink。
- 设置页的令牌/会话输入框是 `Password` 回显，不落 `settings.json`
  （该文件注释里明写 "never contains secrets"，实测也确实没有）。

## 三、隐私

**出网**：`canvas.westlake.edu.cn`、`ams.westlake.edu.cn` 两个域名，外加登录窗加载的
学校 SSO 页面（那些页面自身的第三方资源不受本程序控制）。无分析/上报 SDK。

**落盘**（全部在 `%LOCALAPPDATA%\VesperBoard`）：

| 文件 | 内容 | 敏感度 |
|---|---|---|
| `*.bin` | DPAPI 加密的令牌/会话 | 中（加密） |
| `settings.json` | 刷新间隔、层级、分组开关、ball 坐标 | 低，无凭据 |
| `archived.json` | 归档的作业标题/课程 id | 低 |
| `debug/ams_lessons.json` | 课表快照 | 低 |
| `dock.log` | 运行日志 | 见下 |
| `web-profile/` | QtWebEngine 的 cookie 与缓存 | **见下** |

两个需要知道的事实：

1. **日志曾经写了真实姓名**（`ams 登录成功（<姓名>）`）。已改为不输出姓名。
2. **`web-profile/Cookies` 里 cookie 是明文**（`value` 有值、`encrypted_value` 为空），
   包含 Canvas 的 `_normandy_session`、AMS 的 `SESSION`。这是 QtWebEngine 的行为，
   与普通浏览器的 profile 同级：同一 Windows 账号下的任何程序都能读到。程序自己另存
   了一份 DPAPI 加密的副本用于静默登录。要更强可以登录后清 profile，代价是 SSO 免密续期失效。

**只读自己的 profile**：`browser_cookies.read_cookies()` 打开的是本程序
`web-profile/Cookies`（`mode=ro`），不会去读 Edge / Chrome 的 cookie 库。

## 四、依赖（幻觉包核对）

声明依赖只有 `PySide6>=6.5`、`requests>=2.28`。
venv 实际安装 12 个包，全是这两个的传递依赖（certifi、charset-normalizer、idna、
urllib3、shiboken6、PySide6 及其子包），没有多余项。

逐一核对 PyPI：

| 包 | 版本 | PyPI |
|---|---|---|
| PySide6 | 6.12.0 | ✅ 存在，同为最新 |
| requests | 2.34.2 | ✅ 存在，同为最新 |
| Pillow | 13.0.0 | ✅（仅 tools/ 用，不进 app venv） |
| numpy | 2.5.5 | ✅（同上） |
| pytest | 9.2.0 | ✅（仅测试） |

## 五、DeepSec

命令：`python -m deepsec shield scan <src> --layer all --no-remote-l3`
（扫的是剔除 `.venv`/缓存后的源码副本，29 个文件）

**唯一一条 medium**：`sast_ssrf_fetch_user_url`，定位 `tools/paper_gen.py:81`
—— 那是开发工具访问本机 Paper MCP（`127.0.0.1:29979` 常量），不在发布范围，
属于规则对 `urlopen(req)` 变量的启发式误报。

不过它指出的方向是对的，顺着查出**应用侧一个真实问题**并已修：

> `settings.json` 里 `canvas_url` / `ams_url` 任何同用户进程都能改，
> 改了之后程序会把带会话 cookie 的请求发到那个地址。

修复：`Settings.load()` 里加 `safe_base_url()` 白名单——只接受 `https` 且主机名等于或
以 `.westlake.edu.cn` 结尾，否则回落默认。实测拒绝：`http://` 降级、`evil.example.com`、
`canvas.westlake.edu.cn.evil.com`、`https://user:pw@evil.com`、`file://`。

## 六、本轮修掉的三个问题

1. **DPAPI 悬垂指针**：`security._blob()` 返回的结构体只存了 `create_string_buffer`
   的裸指针，buffer 一出作用域就被回收，`CryptProtectData` 读到的是已释放内存。
   已把 buffer 挂到结构体上保活。
2. **日志泄露姓名**：改为只记录「身份已识别=True/False」。
3. **base URL 未校验**（SSRF / 会话外泄路径）：见上。

改完 `pytest` 37 项全过。

## 七、剩下的风险（已知、已接受）

- 明文 cookie profile（QtWebEngine 行为），影响面 = 同 Windows 账号的程序。
- 内置登录窗加载的是学校页面，页面里的第三方资源不受控。
- `tools/` 下的立绘自动化脚本会操作键鼠与剪贴板，只在手动运行且 ChatGPT/Paper 在前台时生效，
  不随程序启动。
- 程序未做代码签名；从别人那里拿到安装包时无法验证来源。

---

# 1.0.0 复查（2026-11-20 晚）

打包与跨平台改造之后重扫一遍。范围：`main.py`、`wsdock/`、`tools/`、`tests/`、
`packaging/`、`.github/`，以及 `dist/` 下四个产物。

## 结果

| 项 | 结果 |
|---|---|
| 源码密钥字面量 | 0 命中（含 .nsi/.iss/.sh/.ps1/.spec） |
| 产物里的本机信息 | 0 命中（`<用户名>` / 真实姓名 / `@westlake`） |
| `.deb` 里的构建路径 | 0 命中 |
| 依赖真实性 | pyinstaller 6.22.3、pillow 13.0.0、pefile 2024.8.26 均在 PyPI |
| DeepSec | 仍是那 1 条 medium（`tools/paper_gen.py:81`，本机 MCP 常量，非发布代码） |
| 测试 | 43 项通过 |

## 本轮修掉 / 处理掉的

1. **日志里的真实姓名**：`dock.log` 里两条历史记录（`ams 登录成功（<姓名>）`）已删除。
   代码在上一轮已改成只记布尔值，新日志不再出现姓名。
2. **`.gitignore` 漏了构建产物**：`dist/`（576 MB + 三个安装包）、`build/`、`.venv*/`
   之前没被忽略，直接 `git add .` 会把整个安装包塞进仓库。已补上。
3. **未使用的 Inno Setup 安装器**（14 MB）已从临时目录删除；NSIS 工具链保留在
   `%TEMP%\nsis`，方便重打安装包。

## 新增的已知风险（打包/跨平台带来）

| 风险 | 说明 | 建议 |
|---|---|---|
| macOS 钥匙串写入时密码在 argv | `security add-generic-password -w <密码>` 是命令行参数，同一台机器上的其它进程在那一瞬间能从 `ps` 看到 | 窗口只有毫秒级；若在意，改用 `keyring` 库（走 Security.framework，不进 argv） |
| Linux 无 `secret-tool` 时降级为明文文件 | 写 `canvas_token.bin.plain`，权限 0600 | 桌面发行版一般都有 libsecret；没有时至少权限是本用户可读 |
| WebEngine profile 的 cookie 是明文 | Chromium profile 的固有行为，三端一致 | 影响面 = 同账号下的进程；程序另存了 DPAPI/钥匙串加密的一份 |
| 二进制未签名 | Windows SmartScreen、macOS Gatekeeper 都会拦 | 面向他人分发前需代码签名/公证 |
| 安装包内含校方角色立绘 | `assets/pet/` 是学校 IP，属授权问题而非安全问题 | 公开发布前取得授权，或删掉该目录后重打（程序会退回矢量圆球） |
| 打包工具来源 | NSIS 3.11 来自 SourceForge 的官方 zip；Inno Setup 来自 GitHub 官方 release（已弃用） | 两者均未做签名校验；只应在本机打包，别在共享机器上跑 |
| `pefile` 装进了 mamba 的全局 Python | 为了查看 DLL 依赖装的，只在审计时用过 | 与发行无关；想清掉可 `pip uninstall pefile` |

## 出网清单（未变）

`canvas.westlake.edu.cn`、`ams.westlake.edu.cn`，以及内置登录窗加载的学校 SSO 页面。
无遥测、无分析 SDK；打包产物里也没有任何回调地址。

---

# 数据加密一览（2026-11-20 深夜）

用户问"这些信息加密了吗"。逐个文件回答：

| 位置 | 内容 | 加密 |
|---|---|---|
| `canvas_session.bin`（Canvas cookie jar） | 账号会话 | ✅ Windows DPAPI；macOS 钥匙串；Linux `secret-tool` |
| `ams_session.bin`（AMS SESSION） | 账号会话 | ✅ 同上 |
| `canvas_token.bin`（手动粘贴的令牌） | 访问令牌 | ✅ 同上 |
| `settings.json` | 形象/大小/分组/刷新间隔/球坐标 | ❌ 明文，但**不含任何凭据** |
| `archived.json` | 归档的作业标题与课程 id | ❌ 明文（只暴露你在上哪些课） |
| `dock.log` | 运行耗时、数据刷新、登录页 URL | ❌ 明文；已去掉姓名 |
| `debug/ams_lessons.json`、`web-cache/` | 课表快照、网页缓存 | ❌ 明文 |
| `web-profile/Cookies` | 登录窗的会话 cookie | ⚠️ **原为明文，已修**（见下） |

Linux 上没有 `secret-tool` 时会降级成 `*.bin.plain`（权限 0600）——这一点没有变，
报告里也一直标着。

## 本轮修复：登录窗不再把 cookie 写盘

QtWebEngine 的 cookie 库是明文的，里面就是 Canvas / AMS 的会话——等于把钥匙摊在
磁盘上。改动两处：

1. `login.py` 里 profile 的持久化策略从 `ForcePersistentCookies` 改成
   `NoPersistentCookies`：cookie 只存在于登录窗的内存里，关闭即消失。
   会话仍然可用——登录过程中我们通过 `cookieAdded` 实时抓取，随即经 DPAPI 存成
   `canvas_session.bin` / `ams_session.bin`，API 请求用的是这份。
2. 启动时清理旧版本留下的明文库（`web-profile/Cookies*` 与
   `web-profile/Network/Cookies*`），日志里记一行「已清理明文 cookie」。

配套改动：登录窗创建时把 DPAPI 里的会话 cookie **注入内存 profile**
（`LoginWindow._seed_cookies`），所以「静默续期」不会因为拿不到磁盘 cookie 而退化成
要求重新输密码。实测注入后窗口内已有 AMS `SESSION` 与 Canvas `_normandy_session`。

验证：清空后启动，`web-profile/Cookies` 不再生成；数据刷新正常（用的是 DPAPI 会话），
45 个测试通过。

---

# 1.0.0 复查（2026-11-21 晚）：凭据隔离与卸载

外部评审指出两处 P0 问题。两处都属实，已修：

## 1. 上传/下载会把 Canvas 凭据发给第三方域名

`CanvasClient` 原来把 `Authorization: Bearer <token>` 设在 Session 的默认请求头上，
cookie 又是用 `jar.update({...})` 注入的（domain 为空，`http.cookiejar` 会把它发给任意主机）。
而 `_upload_one()` 直接拿这个 Session POST Canvas 返回的 `upload_url`——
按 Instructure 的流程，这个地址常常是 Amazon S3 之类的外部对象存储。
两条凭据就这样随上传请求一起出去了。`download()` 对外部附件地址同理。

**修复**（`wsdock/net.py`、`wsdock/canvas.py`、`wsdock/ams.py`）：

- `set_cookies()` 把每个 cookie 绑定到服务自己的主机，不再有 domain 为空的 cookie
- `TransferSession`：干净 Session，不带 Authorization、不带 cookie，只用于外部上传/下载
- `_request()` 拒绝访问与 Canvas 不同来源的绝对 URL（分页 `Link` 也是输入）
- 上传成功后 `Location` 回调必须是 Canvas 自己的域名，否则直接报错，不跟过去
- 下载按目标来源分流：Canvas → 带凭据；外部 → `TransferSession`

判定用 `same_origin()`：scheme + 主机 + 端口全等，不做后缀匹配。

新增回归测试 10 项：`tests/test_canvas.py`（上传/下载不带凭据、跨来源拒绝、cookie 绑定域名）、
`tests/test_net.py`（来源比较、去重优先级）、`tests/test_paths.py`（迁移后删旧目录）。

## 2. 卸载删不掉真正的数据目录

改名后数据目录是 `%LOCALAPPDATA%\VesperBoard`，但 `windows_installer.nsi` /
`windows_installer.iss` 还在删 `%LOCALAPPDATA%\WestlakeDock`；安装目录与可执行文件名
也还停留在 `WestlakeDock.exe`。选择「同时删除本机数据」时，真正的令牌与会话会留在磁盘上。

**修复**：

- 两个安装脚本全部改成 `VesperBoard` / `VesperBoard.exe` / `%LOCALAPPDATA%\Programs\VesperBoard`
- 卸载时同时删除 `VesperBoard` 与 `WestlakeDock` 两个数据目录（注册表 Run 值也一并清）
- `paths._migrate_legacy()`：先复制到 `.migrating` 临时目录再改名，**完整成功后才删除旧目录**；
  复制失败就保留旧的，下次启动再试

## 顺带修掉的

- `requirements.txt` 固定版本（`PySide6==6.12.0`、`requests==2.34.2`）
- CI 增加独立的 `test` job，构建前必须 `pytest` 通过
- README 的隐私段落改成实际行为（原来写的「不上传任何数据」与提交功能矛盾）
- 版本号保持 1.0.0：尚未发布，直接覆盖原构建

## 仍然成立的风险

- 手动创建 Canvas Personal Access Token 的分发方式，按 Instructure 的 API Policy
  属于开发测试用途；面向其他学生发行前需要走 OAuth 并取得学校管理员许可
- AMS 接口未取得学校书面的第三方客户端许可
- 校方形象与校徽的授权、项目 LICENSE、Qt LGPL 义务：见 `LICENSE` 与 `THIRD_PARTY_LICENSES.txt`

## 重打包复扫（2026-11-21 21:30）

修完凭据与卸载问题后，对 `releases/Vesper_Board_1.0.0`（发行源码，不含 `tools/`）
重新跑 `deepsec shield scan --layer all --no-remote-l3`：33 个文件，0 findings。

---

# 第二轮复查（2026-11-21 晚，zcode 只读审查）

用 `zcode` 对全仓做了一次只读审查（显式禁用 Edit/Write）。它给了 19 条，我逐条
对着代码核过：**P0 1 条、P1 4 条全部属实**，P2 里有 10 条是真问题、2 条不修并记录。
下面只写确认过的。

## P0

**登录窗按子串判断域名**（`ui/login.py` 的 `_on_cookie`）：`if "westlake.edu.cn" in domain`
会把 `westlake.edu.cn.evil.com` 判成校内域，其 cookie 经 `save_cookie_map` 持久化，
下次 `_seed_cookies` 又按原域名注入回浏览器。改成 `net.in_domain()` 的后缀匹配；
回放时再过滤一次，存坏的旧 map 也不会被重放。

## P1

1. **登录校验绕过隔离层**：`_canvas_session_works` / `_ams_person_name` 用裸
   `requests.get(cookies=dict)`（无域名 cookie）且默认跟随重定向。改为
   `GuardedSession` + `set_cookies` 绑定域名 + `allow_redirects=False`。
2. **卸载不结束进程**：NSIS / Inno 卸载段都补上 `taskkill /IM VesperBoard.exe /F`。
   否则文件占用删不干净，程序退出时还会把 `settings.json` 写回去，数据目录「复活」。
3. **迁移失败留下空目录**：`data_dir()` 原来在迁移失败后仍 `mkdir`，下次启动
   `root.exists()` 成立就永久跳过迁移。现在失败时返回旧目录继续用，下次再试。
4. **迁移早于单实例锁**：`main()` 把 `already_running()` 提到最前；非 Windows 的
   `QLockFile` 改放数据目录的父级（`root_dir().parent`），不再触发迁移。

## P2（已修）

- `net.origin()` 捕获畸形端口（`https://h:abc/`）→ 按不同来源处理，不再抛 ValueError
- `_dedupe` 直接丢弃**没有域名**的 cookie（最危险形态），并加锁（六线程共享 Session）
- `TransferSession.trust_env = False`：不读环境代理、不让 `.netrc` 附加 basic auth
- `Retry-After` 非数字时回退 3 秒（原来是裸 `float()`）
- 下载文件名补上控制字符、结尾点/空格、`CON`/`NUL` 等保留名、超长截断
- `clear_cookies` / `clear_ams_cookies` 改走 `save_secret(path, "")`，同时清 `.plain` 与钥匙串
- 互斥量改用 `WinDLL(use_last_error=True)`，名字去掉版本号（升级共存期也只允许一个实例）
- `dock.log` 改 `RotatingFileHandler`（1 MB × 2）
- `settings/archive/reminders` 改 `os.replace` 原子写
- `safe_base_url` 用 hostname 重建，丢掉 `user:pass@`

## 未修（记录）

- 登录窗的会话校验仍在 UI 线程执行，最长 6 秒（`_throttled` 每 4 秒一次）。要彻底
  解决得把它挪进线程池，属于界面结构调整，留到下一轮。
- Canvas 错误响应体 `resp.text[:160]` 仍会进日志（不含凭据，服务端可控内容）。

## 复核阶段发现的新问题（已修）

第二轮复核（同一次 zcode 调用）在验证改动时又抓到三条，其中一条是我自己引入的：

- **单实例检查被调用了两次**：把 `already_running()` 提到 `main()` 开头时，旧调用没删。
  Windows 上第二次 `CreateMutexW` 会返回 `ERROR_ALREADY_EXISTS`（即使属主是自己），
  于是程序把自己当成「已有实例」直接退出 —— 打包后的 exe 双击秒退。
  修复：删掉旧调用，并让函数幂等（`_MUTEX` / `_LOCK` 已持有直接返回 False）。
- **`CreateMutexW` 不清零 last error**：成功时残留的上一次 183 会被误读。
  修复：调用前 `ctypes.set_last_error(0)`；句柄为 0 时抛错回退到 `QLockFile`。
- **Inno 的 taskkill 放在 `usPostUninstall` 太晚**：那时文件已经删过了，而进程还锁着 exe。
  修复：挪到 `usUninstall`（NSIS 的位置本来就是对的）。
- **`Retry-After` 的负值 / NaN**：`float()` 能解析成功，但 `time.sleep()` 会抛 ValueError。
  修复：`isfinite` 检查后夹到 `[0, 30]`。

---

# 第三轮：攻击面审查（2026-11-21 深夜）

这一轮不再只看桌面端主流程，而是按攻击面过一遍：凭据、网络、本地文件、代码执行、
供应链、安装器、安卓端、发布卫生。桌面端**没有新的 P0**，上一轮 10 项逐条回归确认未复发；
问题集中在安卓与发布卫生。

## P1（已修）

1. **安卓凭据明文 + 允许云备份**：`SessionStore` 用普通 `SharedPreferences`，
   manifest `allowBackup="true"` —— 换机/云备份会把 Canvas 会话整份带出设备。
   修复：`allowBackup="false"`、`usesCleartextTraffic="false"`。
   加密存储（EncryptedSharedPreferences/Keystore）留作下一步。
2. **1.1.0 快照含不该发布的内容**：`tools/`（会读浏览器缓存与剪贴板）、
   `assets/ref_*` 与 `assets/refs/`（校方/第三方参考图）、README 里的本机绝对路径。
   修复：删除这三类内容，README 改为 `python main.py`，CI 与 1.0.0 对齐。
3. **安卓登录整包回传 cookie 且重登不清理**：`getCookie(BASE)` 拿的是该域下全部 cookie，
   每次点「完成」都保存；重新登录直接复用旧会话。修复：进登录页先
   `removeAllCookies` + `flush`；`SessionStore.clear()` 一并清 `user_name`。

## P2（已修）

- 下载也强制 https（原来跨域附件允许 `http:`，签名 query 会明文过网）
- `browser_cookies` 与登录窗完成判定统一用 `in_domain()`（原来一处 `endswith` 少点边界）
- 数据目录在 POSIX 上 `chmod 0700`（umask 022 建出来是 0755，同机其他用户可读课程名）
- `write_text_atomic` 临时名带 pid 且用 `O_EXCL` 打开（防预置符号链接）
- 导入形象 `copytree(..., symlinks=True)`（不解引用恶意链接）
- CI 加 `permissions: contents: read`；构建依赖拆到 `requirements-build.txt` 固定版本
- 安卓删掉未使用的 `ACCESS_NETWORK_STATE` / `POST_NOTIFICATIONS` 与 `work-runtime-ktx`
- 安卓改为**签名的 release 构建**（`assembleRelease` + 自签名）：不再 `debuggable`，
  也不带 Compose `PreviewActivity`；产物放到 `build/artifacts/VesperBoard-android.apk`
- `autostart` 的 LaunchAgent 标识与钥匙串标签从 `edu.westlake.dock` / `WestlakeDock`
  统一为 `com.vesperboard.app` / `VesperBoard`
- README / SECURITY 里过时的「粘贴 Admin-Token」说明改为登录窗流程

## 记录未修

- macOS 钥匙串写入仍用 `security -w <值>`，值会短暂出现在 `ps` 里（需要用
  Security.framework 绑定才能彻底解决，本机无法验证 macOS）
- 传递依赖（certifi/urllib3/shiboken6）未做 hash 锁定；GitHub Actions 仍 pin major tag
  而非 SHA（无法离线取得 SHA）
- `dock.log` 有两条写入通道（logging 与手工 append），轮转只覆盖前者
- 安卓会话仍是明文 prefs（现由 `allowBackup=false` + 应用沙箱保护）

---

# 第四轮复核（2026-11-22 凌晨）

针对最近改动（干净登录、置顶、主题令牌、紧急状态、可移植脚本）的复审。无新增 P0；两条 P1 已修。

1. **`warn_on_top` 缺 `QMessageBox` 导入**：设置页导入形象失败时会抛 `NameError`，
   警告框永远弹不出来。已在 `widgets.py` 补导入。
2. **登出不清 `cookies.bin`**：静默续期会拿残留的 IAM/Canvas SSO cookie 把会话「复活」，
   登出在下一个刷新周期被自动撤销。新增 `session.clear_cookie_map()`，
   两个登出入口都调用；配合已有的 `clear_cookies` / `clear_ams_cookies`。

P2 处理：
- 主动登录改用**一次性内存 profile**（`QWebEngineProfile(self)`），从构造上就没有旧 cookie，
  不再依赖 `deleteAllCookies` + 600 ms 的竞态窗口；也避免与静默续期窗争同一个持久 profile。
- `--login-check` 自检改为 `seed=False`，不再带真实凭据导航。
- WSL 脚本加 `set -u`；登录窗注释里的超时数字与实际值对齐。

未改（记录）：
- 登录窗置顶后切到其它应用仍浮在最前。这是「不被面板遮挡」的代价；
  可选的改进是失焦时撤置顶、重新激活时恢复。
- `render_qss` 仍是子串替换；已核对样式表输入全是常量，无用户可控文本，暂不构成问题。

## 数据落盘加密（1.0.1 之后）

### 威胁模型

「同机其它用户 / 文件被拷走 / 云同步把数据目录搬走 / 远程入侵者拿到文件读取权限」
这几种情况下，攻击者能读到文件，但不应该有这台机器的用户凭据（DPAPI 主密钥）。

### 设计

- **算法**：AES-256-GCM（`cryptography` 的 `AESGCM`），每条记录独立 12 字节 nonce，
  tag 自带完整性校验，篡改会在解密时抛 `InvalidTag`，不会解出垃圾数据。
- **密钥**：32 字节 `os.urandom`，只以 DPAPI 密文（`key.bin`）落盘；
  macOS 写登录钥匙串、Linux 写 Secret Service，两者都不可用时降级为 0600 的
  `key.plain`（与旧令牌的降级路径一致，文档里明说不假装安全）。
- **绑定**：AAD = `"VesperBoard/" + 逻辑名`（settings / archived / reminders / log），
  两个密文文件对调或改名都会解密失败。
- **覆盖范围**：设置、归档、提醒、日志（`LogSink` 按大小轮转，逐帧加密）。
- **不在范围**：导入的形象图片（非敏感）、下载的附件与导出的 `.ics`
  （用户主动导出、需要分享）、Chromium 的运行期缓存（改为内存缓存 + 启动/退出清理）。
- **迁移**：旧版本留下的明文 JSON 仍可读，下一次写入自动转成密文；
  `.plain` 兄弟文件在首次写入后被覆盖清零再删除。

### 已知限制

- DPAPI 保护的是「同一 Windows 账户」：以该用户身份运行的恶意程序同样能解密。
  要抵御这一层需要主密码（未实现）。
- 密钥丢失（换账户、重装系统、删除 `key.bin`）等于数据丢失，程序会退回默认设置。
- Windows 上 `os.chmod(0o600)` 只动只读位，真正的保护来自 DPAPI 与用户目录 ACL。

