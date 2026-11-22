# 参与 / Contributing

## 开发环境

```powershell
python -m pip install -r requirements.txt
python -m pip install pytest
python main.py
```

Python 3.12。Windows 是主要目标平台；Linux 能跑，macOS 只在 CI 里验证过。

## 改完自检

```powershell
python -m pytest tests -q
```

`tests/` 全部离线，不应出现网络请求。改到界面时至少手动走一遍：

1. 启动 → 悬浮球出现，数字与 Canvas 待交数一致
2. 左键展开面板 → 作业 / 课表两个页签都能切
3. 设置 → 主题切浅色 / 深色 / 跟随系统，面板即时重建且文字可读
4. 设置 → 形象切一次，悬浮球不跳位
5. 按 Esc 收起，右键球能退出

## 代码风格

- 4 空格缩进，行宽约 100，跟现有文件保持一致
- 类型标注只在能说清的地方加，不为了标注而标注
- 中文注释可以，但别把界面文案写进注释里
- 界面颜色走 `wsdock/ui/theme.py` 的令牌，不要写死 `#RRGGBB`
- 新增依赖前先确认 registry 里确有这个包、维护正常，再写进 `requirements.txt`

## 素材

形象必须满足 `docs/custom-skin.md` 的尺寸与命名约定（512×512 透明、脚底 y=496、
七个状态文件名固定）。中间稿、原图、截图放 `_archive/art/`，不要放 `assets/`。

## 提 PR / 提 issue

- 一个 PR 只做一件事；顺手的重构单独拆开
- 附带复现步骤或截图（界面改动）
- 不要提交 `settings.json`、`*.bin`、`web-profile/`、`dist/`、`build/`、`_archive/`
  —— 它们都在 `.gitignore` 里，`git add -A` 前先 `git status` 看一眼
- 不要在提交里放令牌、cookie、学号或任何个人数据

## 安全

发现令牌泄露、请求外发或权限问题，按 `SECURITY.md` 的流程私下报告，不要开公开 issue。
