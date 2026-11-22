# 安全策略 / Security

## 报告漏洞

不要开公开 issue。用 GitHub 的私密漏洞报告（Security → Report a vulnerability），
或邮件至 **`jiamingshi_git@outlook.com`**，标题以 `report_vesper-board:` 开头
（例：`report_vesper-board: upload sends token to object storage host`）。
请包含：影响版本、复现步骤、确切命令行与环境、实际影响。

不支持匿名公开披露；修复前请不要公开细节。

## 支持范围

| 版本 | 状态 |
|---|---|
| 1.0.x | 接受安全修复 |
| 1.1.x | 开发中 |
| 更早 | 不再维护 |

## 这个程序碰什么数据

| 数据 | 位置 | 保护 |
|---|---|---|
| Canvas 个人访问令牌 | `%LOCALAPPDATA%\VesperBoard\*.bin` | Windows DPAPI（CurrentUser） |
| AMS 会话 cookie | 同上，`*_session.bin` | 同上 |
| 内嵌浏览器配置 | `%LOCALAPPDATA%\VesperBoard\web-profile\` | 仅文件 ACL；**cookie 值在当前 Qt 版本下是明文** |
| 设置 | 同上，`settings.json` | 明文，不含令牌 |
| 下载的附件 | `~/Downloads/VesperBoard/` | 普通文件 |

- 不保存密码，不碰企业微信 / i西湖 的数据库，没有遥测，不向开发者回传任何数据
- 带凭据的请求只发往 `canvas.westlake.edu.cn` 与 `ams.westlake.edu.cn`；
  上传/下载落到对象存储时改用不带 Authorization、不带 cookie 的 `TransferSession`，
  Canvas 返回的跨来源回调一律拒绝。只有你确认提交后，选中的文件才会交给 Canvas
- `debug/ams_lessons.json` 可能含课程名，属于个人数据，不要贴进 issue

## 令牌权限范围（重要）

Canvas 个人访问令牌**不分权限**，等同账号的完整 API 权限（能读写课程、成绩、提交）。
AMS 的会话 cookie 等同登录态。这两个文件只应留在本机 DPAPI 里，
不要复制到网盘、聊天、截图或 issue 里。

## 维护者发版前检查

1. 全目录扫密钥（含二进制）：`eyJ…`、`-----BEGIN`、`sk-`、`AKIA`、`ghp_`、`Bearer xxx`
2. 扫硬编码路径与个人信息：用户名、`C:/Users`、邮箱、学号
3. 扫危险调用：`eval`、`exec`、`os.system`、`subprocess`、`pickle`、`yaml.load`、`verify=False`
4. 确认 `dist/`、`build/`、`_archive/`、`releases/`、`*.bin`、`web-profile/` 不在提交里
5. DeepSec 扫**解包后的产物目录**，不是仓库：

   ```powershell
   python -m deepsec shield scan <解包目录> --layer all --no-remote-l3 --format json -o docs/audit/deepsec-<日期>.json
   ```

   已知：`tools/paper_gen.py` 会报一处 medium SSRF（开发期出图脚本，URL 来自本机调用），
   该目录不进安装包；报 0 findings 的应是源码树去掉 `tools/` 之后的范围。

6. 扫描记录放 `docs/audit/`，和 `docs/security-audit.md` 的结论对得上

## 已知限制

- Windows / Linux 的 zip 与安装包没有代码签名，首次运行会被 SmartScreen / Gatekeeper 拦
- macOS 只能在 CI 构建，未签名、未公证
- 内嵌浏览器的 `web-profile` cookie 明文问题见上表；介意的话在设置里取消登录后删掉该目录
