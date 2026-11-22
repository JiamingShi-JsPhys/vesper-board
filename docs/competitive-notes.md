# 同类项目与 UI 参考

调研时间 2026-11-20。方法：GitHub 仓库搜索 API + 直接读各仓库 README。
（web-forager 的 `research` 对这类查询拿不到有效证据，已放弃。）

## 一、同赛道项目

| 项目 | 星 | 许可 | 定位 | 关键做法 |
|---|---:|---|---|---|
| [OyangDer/still-today](https://github.com/OyangDer/still-today) | 3 | MIT | **几乎同款**：Canvas 桌面小组件（Win/Mac） | 作业按截止分组、按课程筛选、专注计时绑定作业、日历月视图、ICS 订阅、公告、出分/改期通知 |
| [HANSEIDON/DeskCal](https://github.com/HANSEIDON/DeskCal) | 13 | MIT | 北大学生的桌面课表日历 | 贴桌面层（Win+D 仍在）、单双周、D-day 徽标、紧凑模式、ICS 导出 |
| [weixinhao929/vela-cleanroom](https://github.com/weixinhao929/vela-cleanroom) | 25 | MIT | 透明挂件画布（Tauri+React） | 34 种挂件、Dynamic Island 聚合面板、挂件可展开成沉浸视图 |
| [T0086/beacon](https://github.com/T0086/beacon) | 0 | — | PowerShell 极简桌面条 | 收起态 470×76 长条：时间+下一件事+紧急度点；置顶/沉底切换 |
| [YesDeat/TimeTable](https://github.com/YesDeat/TimeTable) | 1 | — | 桌面课表，可拖动常驻 | 截图 OCR 导入课表（Windows OCR），纯标准库 |
| [wiz-rd/Canvas-Desktop-Reminders](https://github.com/wiz-rd/Canvas-Desktop-Reminders) | 0 | — | Canvas 截止提醒 | 只做通知，不做展示 |

## 二、它们的设计共识

1. **认证优先用个人访问令牌**（still-today 明说「没有账号，没有中转服务器」）。我们的内嵌 SSO 登录是差异化优势，但要保留令牌作为备份路径。
2. **贴桌面层 > 一直置顶**（DeskCal 明确「sits just above the wallpaper」，Win+D 后仍在，但不挡任何窗口）。beacon 干脆给了「置顶/沉底」开关。
3. **信息分层**：收起态只放「下一件事」，展开才给清单（beacon 的长条、still-today 的总览）。
4. **紧迫度用颜色分级**：DeskCal 一周内橙、今天/明天红；beacon 用绿/黄/红小球。
5. **紧凑模式是刚需**（DeskCal「just today's classes」）。
6. **性能要给数字**：DeskCal 写明约 75 MB 内存、空闲 <1% CPU。
7. **课表要处理单双周和周次**，且「本周不上课」要有视觉区分（虚线）。
8. **导出/订阅**：ICS 导出与订阅是共性需求（DeskCal、Vela、still-today 都有）。

## 三、对我们这版的具体建议

### P0（直接影响可用性）

1. **收敛作业列表**
   现在 24 项里 5 项是 51 天前的逾期项，把真正要交的淹没了。
   规则：默认显示「逾期 7 天内 + 未来 14 天」；其余折叠为「更早的 N 项」。
   参考 still-today 的「7 天内还有几项要交」。

2. **头部加一行「下一件」**
   最高频的信息是「我现在要做什么」，不是清单本身。
   `下一件：17:00 交 Lab report（还剩 3 小时）`，比现在的「未完成 24 项」有用得多。

3. **紧迫度分级统一**
   现在只有 6 小时内才变红，太晚。改为：<24h 红 / <7d 橙 / 更远灰，全应用一致（球徽标、行、头部）。

### P1（体验质变）

4. **加「置顶 / 贴桌面」切换**
   默认改成贴桌面层（`Qt.WindowStaysOnBottomHint` 或 HWND 插入 desktop 层），右键可切回置顶。
   这是同类项目里最一致的一条：悬浮球挡屏是被骂最多的点。

5. **球增加「悬停横向展开」**
   悬停时球向左伸出一小条：`下一节 09:50 E13-207` 或 `17:00 截止 · Lab report`。
   参考 beacon 的收起态，信息密度比圆球高一个量级。

6. **课表加周视图**
   现在只有今天+明天。学生更常问「这周还有什么」。
   5 列×时间轴，今天列高亮，当前时刻画一条横线；单双周不上课的课用虚线框。

7. **提交后即时反馈**
   现在只有 toast。加「提交成功」后该行立刻打勾并淡出到「已提交」分组（still-today 的做法）。

### P2（打磨）

8. **通知**：新作业发布、截止前 2 小时（可关）。still-today 有出分/公告通知，说明这个位置有价值。
9. **ICS 订阅/导出**：把课表导出成 .ics，能订阅到系统日历。
10. **紧凑模式**：只显示「下一节 + 下一个截止」两行，适合放屏幕角落。

## 四、视觉参数建议

| 项 | 现状 | 建议 |
|---|---|---|
| 卡片背景 | rgba(22,27,37,248) | 保持不透明；Windows 11 可试亚克力（DwmSetWindowAttribute 38/17） |
| 圆角 | 18px | 保持；行内 10px 合适 |
| 字体 | 微软雅黑 UI | 保持；行高比现在再松 2px |
| 动效 | 无 | 展开/收起 160ms OutCubic；球悬停放大 1.05（120ms） |
| 球徽标 | 红/橙两色 | 统一为紧迫度三色，且 >9 显示 9+ |
| 空状态 | 有 | 加一句动作引导（「去 Canvas 看看」按钮） |

## 五、许可证

still-today / DeskCal / Vela 都是 **MIT**。我们的项目已经有 `LICENSE`：
代码部分当前是「保留所有权利」（只允许查看与提 issue），美术素材单独排除在外
（详见 `LICENSE`）。

不要因为竞品用 MIT 就顺手也套 MIT：这份代码里混着校方形象、校徽和第三方参考图，
代码许可证管不到它们；而且 Canvas 手动令牌 + 学校非公开接口的分发方式本身还需要
学校许可。许可证定下来之前，保持现状最安全。
