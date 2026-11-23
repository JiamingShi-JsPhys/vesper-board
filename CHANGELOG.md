# Changelog

本项目按 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.1.0/) 组织，
版本号遵循 [语义化版本](https://semver.org/lang/zh-CN/)。

## [1.0.1] — 2026-11-23

院徽版本：形象里加入四个书院的院徽球，并让应用能自己检查更新。

### 新增

- **院徽球**：Alpha / Beta / Gamma / Delta 四个书院各一个，直接用院徽本身的形状
  （四叶草 / 六边形 / 圆盘），背景透明，浅色桌面和深色桌面上都不带白边
- **检查更新**：设置 → 常规 里有「检查更新」，读仓库根目录的 `version.json` 取最新版本号；
  国内网络下依次回落到 jsDelivr 镜像、GitHub `releases/latest` 的跳转与 release atom，
  API 只做最后兜底

### 修复

- 检查更新此前只打 `api.github.com`，被 403 / 限流时就报「检查失败，请稍后再试」
- 设置页作者页的徽标绘制用了未导入的 `QPen`，会抛 `NameError`

### 说明

- 本版本的「形象」只到四个院徽球。书院拟人形象和其余换装仍在重绘，留在本地备份里，
  不随这一版发布

## [1.1.0] — 计划中

把 1.0.0 里因为版权原因收起来的形象，和安卓端一起放进这个版本。

### 新增

- 四个书院角色 α / β / γ / δ：idle + hover 已实装，其余五种状态（同步中 / 上课 /
  紧急 / 完成 / 出错）缺图时回落到 idle
- 可导入的默认形象包：`packs/小西·水手裙`、`packs/小贝塔`（1.0.0 安装包里不带）
- 安卓客户端 `Coding/Vesper_Board_Android`：Kotlin + Compose，WebView 登录，
  登录页有「取消 / 完成」两条出路，完成后读 cookie 交给原生层

### 变更

- 形象清单拆成两套：1.0.0 只发布图标球与默认小西，其余进本版本

## [1.0.0] — 2026-11-21

第一个对外版本。

### 新增

- 悬浮球：数字是未交作业数，6 小时内或已逾期变红；悬停向左滑出「上课中 / 下一节 / 下一件」；
  拖动后自动吸附屏幕边缘并记住位置；右键菜单可切换置顶层 / 普通窗口层 / 贴桌面
- 作业面板：按逾期 / 今天 / 明天 / 未来 7 天 / 更晚分组，重名课程自动合并，
  「仅提醒」类作业折叠在底部且不计入数字
- 提交：选多个文件 → 确认 → Canvas 三步上传；已交的收进「已提交 · N」，按钮变成「新提交」
- 详情页：作业正文、附件、课程文件，可直接打开或下载到 `~/Downloads/VesperBoard/`
- 归档：免修 / 换课 / 助教批改的作业右键收进「已归档 · N」，可恢复
- 课表：今天 + 本周七天，教室名清洗成 `E13-207` 这种；正在上的课标「进行中」
- 成绩、消息（Canvas 公告 + AMS 通知，侧栏红点）、开课前与 DDL 前提醒、勿扰时段
- 每日早报、待交角标、专注 25 分钟、导出 `.ics`、中英双语、开机自启、托盘菜单
- 形象页：卡片式切换，64–128 px 可调；支持导入自定义形象（`docs/custom-skin.md`）
- 角色说话：状态短句用气泡显示在人物头顶，45 秒内不重复，打开面板时自动收起
- 主题：跟随系统 / 浅色 / 深色三档，切换即时重建面板；光晕与右上角标点默认关闭
- 面板头部：应用名、按时段变化的问候语、Canvas 用户名
- 设置页：常规 / 形象 / 账号 / 高级四组，作者页保留项目仓库与 star 入口

### 变更

- 应用改名为 **Vesper Board（晚星看板）**；数据目录 `WestlakeDock` → `VesperBoard`，
  首次启动把旧目录整体搬过来（复制成功后才删旧的），DPAPI 熵不变，旧令牌无需重新输入
- 形象清单收敛为两套：图标球（晚星看板）+ 默认小西
- `requirements.txt` 固定版本；CI 增加 `test` job，构建前必须通过 `pytest`
- README 隐私段落按实际行为重写（提交功能会把文件交给 Canvas）
- 登录窗改为置顶并在显示时提到最前，不再被置顶的面板/悬浮球挡住；
- 主动登录从干净状态开始（清 cookie 与缓存）：修复旧会话导致 canvas↔iam
  反复重定向、登录页一直白屏；静默续期仍注入旧 cookie
- 紧急状态只统计清单里显示的项目：折叠进「更早」的逾期旧作业不再触发紧张表情
- 提醒时间对话框与设置页的警告框也改为置顶显示，不再被面板压住静默续期用的隐藏窗不抢焦点

### 打包

- Windows onedir（446 MB，zip 179 MB）与 NSIS / Inno 安装脚本
- Linux onedir（574 MB，zip 215 MB）与 `.deb`，在 WSL 里用 `scripts/wsl_build_linux.sh` 交叉构建
- macOS `.app` 只能走 GitHub Actions（`.github/workflows/build-desktop.yml`），本机无法产出
- PyInstaller 后处理裁掉 devtools pak、多余翻译与 `qtwebengine_locales`，
  并把 `assets/pet` 收窄到 `mascot`（`WESPER_SHIP_ALL_SKINS=1` 可放开）

### 安全

- 令牌用 Windows DPAPI 加密存本机，`.bin` 与 `web-profile` 都不进仓库、不进安装包
- 凭据不外发：上传/下载落到对象存储时走不带 `Authorization`、不带 cookie 的
  `TransferSession`；上传后的 `Location` 回调必须是 Canvas 自己的域名，跨来源绝对 URL
  直接拒绝；cookie 注入绑定到服务自己的主机；发请求前丢弃所有没有域名的 cookie
- 登录窗的域名判定改后缀匹配（原来的子串匹配会把 `westlake.edu.cn.evil.com`
  当成校内域）；会话校验改用绑定域名的连接且不跟随重定向
- 卸载前先结束常驻实例，避免文件占用与「删完数据目录又被写回来」
- 数据目录迁移失败时继续用旧目录、下次重试，不再建空目录把重试堵死；
  单实例检查提前到任何数据目录操作之前
- Windows 卸载脚本统一到 `VesperBoard`，选择删除数据时同时清理
  `%LOCALAPPDATA%\VesperBoard` 与改名前的 `WestlakeDock`
- 日志改轮转（1 MB × 2）；设置 / 归档 / 提醒改原子写；下载文件名按 Windows 规则清洗
- 下载与上传一样强制 https；POSIX 数据目录收紧到 0700；原子写临时文件带 pid 且
  `O_EXCL` 打开；导入形象不解引用符号链接
- CI 加 `permissions: contents: read`，构建依赖拆到 `requirements-build.txt` 固定版本
- 安卓：关掉 `allowBackup` 与明文流量，登录前清空 WebView cookie，
  `clear()` 连用户名一起清；删掉未使用的权限与 WorkManager 依赖；
  产物改为签名的 release 构建（非 debuggable、无 Compose tooling）
- 回归测试覆盖：上传/下载不带凭据、跨来源拒绝、cookie 域名绑定与无域名丢弃、
  迁移删除旧目录、迁移失败回退、域名后缀判定、文件名清洗、base URL 白名单
- DeepSec `shield scan --layer all --no-remote-l3`：源码 0 findings，产物 0 findings
- 遗留的一处 SSRF 提示位于 `tools/paper_gen.py`（开发期出图脚本），该目录不进发行包
