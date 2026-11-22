# 形象设计规范 · 西湖课业助手的桌面伙伴

参考了 [CrossPet](https://github.com/lokicorvus/crosspet) 的**交互设计**（状态化立绘、贴边半身、状态跟着任务联动、待机小动作）。
它的代码是 MIT、立绘是 CC BY-NC-SA 4.0 —— 我们只学机制，角色形象全部自绘或由你提供。

---

## 一、她出现的位置

现在是一颗 62px 的圆球。有了立绘之后：

| 形态 | 尺寸 | 说明 |
|---|---|---|
| 桌面立绘 | 96×96（可调 64–128） | 站在屏幕边缘，脚底贴边 |
| 贴边半身 | 48×96 | 拖到屏幕边上时只露半个身子，鼠标靠近探头 |
| 面板头像 | 48×48 | 面板左上角/空状态里的小头像 |

## 二、状态表（决定画几张图）

| 状态名 | 什么时候 | 画什么 | 优先级 |
|---|---|---|---|
| `idle` | 没有紧急事项 | 站着、轻轻呼吸；10 分钟无交互可换 `sleep` | 最低 |
| `hover` | 鼠标悬停 | 抬头看你 / 挥手 | 低 |
| `syncing` | 正在拉 Canvas/AMS | 翻资料、转小圈 | 最高 |
| `class` | 课表里有正在上的课 | 抱着书、看表 | 高 |
| `urgent` | 24 小时内有截止或已逾期 | 着急、举小纸条 | 高 |
| `done` | 全部交完 | 伸懒腰、得意一下 | 中 |
| `error` | 登录失效 / 网络断 | 摊手、头顶问号 | 中 |

优先级从高到低：`syncing > class > urgent > error > hover > done > idle`。

`done` 只在「从有作业变成没有」的那一次闪 5 秒，之后回 `idle`。

## 三、素材规范（给我照片时按这个来）

```
assets/pet/
├─ idle.png      正面站立，脚底中线对齐
├─ idle_alt.png  （可选）呼吸第二帧
├─ hover.png
├─ syncing.png
├─ class.png
├─ urgent.png
├─ done.png
├─ error.png
└─ edge.png      贴边半身（只画左半边，镜像用于右边）
```

- **格式**：PNG-32，透明背景，不要白底，不要阴影图层（阴影程序画）
- **尺寸**：源图 512×512，人物脚底对齐画布底边，水平居中
- **留白**：四周至少 24px 透明边，避免贴边被裁
- **一致性**：所有状态用同一角色、同一服装、同一画风、同一光源方向（左上）
- 缺哪张就用 `idle` 顶；一张都没有就退回现在的矢量圆球

## 四、提示词

给你照片之后，用「图生图 / 角色参考」的方式生成，**别用纯文生图**——纯文字每次都换脸。

### 通用前缀（所有状态都要带）

```
参考图中的角色（保持脸部特征、发型、服装配色、画风完全一致），
Q 版 2.5 头身，正面站立，透明背景，脚底对齐画布底部，四周留白，
干净的赛璐璐上色，左上方向光源，无阴影投射，
512×512 PNG，无文字、无水印、无边框。
```

### 各状态（接在通用前缀后面）

| 状态 | 中文提示 | English |
|---|---|---|
| idle | 自然站立，双手垂在身侧，微笑，视线平视 | standing relaxed, arms at sides, soft smile, looking forward |
| hover | 抬头看向画面右上角，一只手抬起打招呼 | looking up toward top-right, one hand raised in a wave |
| syncing | 双手抱着一叠文件，低头翻看，旁边飘着几个小齿轮 | hugging a stack of papers, head down reading, tiny gears floating nearby |
| class | 抱着一本书，另一只手看表，表情专注 | holding a book, checking a wristwatch, focused expression |
| urgent | 着急的表情，双手举着一张小纸条，额头一滴汗 | worried face, holding up a small note with both hands, one sweat drop |
| done | 伸懒腰，闭眼笑，双手举过头顶 | stretching with arms overhead, eyes closed, happy |
| error | 摊手，头顶一个问号，表情困惑 | shrugging with palms up, question mark above head, puzzled |
| edge | 侧身抱着屏幕边缘，只画左半边身体 | side view hugging a screen edge, left half of the body only |

### 英文完整示例（idle）

```
Use the attached character sheet as reference — keep the face, hairstyle,
outfit colors and art style exactly. Chibi 2.5-head proportions, front view,
standing relaxed with arms at sides, soft smile, looking forward.
Transparent background, feet aligned to the bottom edge, 24px padding,
clean cel shading, light from upper-left, no cast shadow,
512x512 PNG, no text, no watermark, no border.
```

## 五、怎么交给我

1. 把照片（校方虚拟人物）放到任意位置，告诉我路径
2. 我会先出一张 `idle` 的试稿给你确认画风
3. 确认后批量生成其余状态
4. 全部丢进 `assets/pet/`，程序自动启用，不用改代码

## 六、程序侧的约定

- 形象放在 `assets/pet/<皮肤名>/`（例如 `assets/pet/xiaoxi/`），
  只要目录里有 `idle.png` 就算一个可用皮肤，设置页的「形象」下拉会自动列出来
- 皮肤目录里缺哪张就退回 `idle`；一张都没有就退回矢量圆球（`西` 字那个）
- 状态优先级（`wsdock/ui/ball.py: current_state`）：
  `syncing > class > urgent > error > hover > done > idle`
- `done` 不是常驻状态：待交数从「有」掉到「0」的那一次，闪 5 秒再回 `idle`
- 徽标（待交数字）叠在立绘右上角，位置随图尺寸自适应
- 立绘显示尺寸 92px（`PET_SIZE`），矢量球是 62px

## 六·补、现在这套图是怎么做出来的

七张全部来自 ChatGPT 网页版「图生图」，不是纯文生图，所以脸和服装在七张之间是连贯的。

1. **两张参考图各管一半**，一起贴给模型：
   - `assets/ref_style_flat.png`（扁平风格参考）——只学**画风与头身比**，
     提示词里写明"绝不要画它的人物、发型、服装、配饰"
   - `assets/ref_xiaoxi_official.jpg`（学校发布的设定图）——只给**角色特征**
2. 提示词里逐条列出不能改的特征：藏青偏蓝长发 + 呆毛、亮蓝眼、白色水手领连帽外套
   （藏青领口橙滚边）、橙色领结 + 正中白色小方块 W 徽章、藏青百褶裙、
   白色宽肩带斜挎兔包、白底橙边厚底鞋；并要求"只画角色，不要照搬海报版式"
2·补. 头身比要写成**可量的指标**才有效（"整个人只有 2 个头高：头顶到下巴 1 个头，
   下巴以下的身体加腿再 1 个头；头宽约占画面 45%"）。只说"约 2 头身"，模型会给回 2.8 头身
3. 要求纯品红背景 `#FF00FF`，1024×1024
4. 从 Edge 的图片缓存里把生成结果捞出来（`Cache_Data/f_*`，比右键另存稳）
5. 按品红强度算 Alpha 抠图，**预乘 Alpha 缩放**后再还原直通 Alpha，
   否则边缘会有一圈暗边、颜色发灰
6. 统一缩放到人物高 470px，画布 512×512，脚底对齐 `y=495`，水平居中
7. 拼成 `docs/preview-all-states.png` 检查：透明背景、脚底同线、光源同为左上

脚本：`tools/gen_pet_ref.py`（生成 + 抠图）、`tools/contact_sheet.py`（预览图）、
`tools/compare_ref.py`（和官方设定图并排对照）。

```bash
python tools/gen_pet_ref.py                  # 只补缺的
python tools/gen_pet_ref.py idle --force     # 只重画这一张
```

> 自动化的坑：
> 1. 输入框坐标不能写死——Edge 窗口一挪就点到窗外；现在按窗口矩形实时算（底边往上 58px 中间）。
> 2. **CrossPet 桌宠有编码工具的 hook**，每次工具调用都可能把它的窗口顶到前台。
>    `ensure_edge()` 必须带 `BringWindowToTop` 并多试几轮，每次按键前都确认前台窗口是 Edge，
>    不对就中止——宁可失败，也不能把内容贴进别的窗口。
> 3. Windows 的「任务视图」也会占住前台，`SetForegroundWindow` 直接被拒；启动前先按 Esc 关掉。
> 4. **上传的参考图本身也会进 Edge 缓存**，抓生成结果时必须排除它——只认接近正方形的大图，
>    否则会把 1145×1374 的设定图海报当成结果存下来。


---

## 六·补二、beta 的备用通道：Paper（2026-11-20 验证）
ChatGPT 免费额度用完后，改用本机 **Paper（paper.design）** 出图，效果更好：

- 生成条：工具栏 `Create Image`（快捷键 Ctrl+Shift+I），模型选 **Nano Banana Pro**
- 参考图：把画布上的图**拖进生成条**就会当参考；不能先选中再开条（有选中时条打不开）
- 提交：贴好提示词按**回车**，不用点按钮（按钮位置随缩略图数量浮动）
- 完成信号：节点名从 `Generating with …` 变成描述性名字（约 10 秒）
- 导出：MCP（`127.0.0.1:29979/mcp`）的 `export`，返回 Downloads 里的 PNG
- 抠图：Nano Banana Pro 不出 alpha，提示词里要 **纯品红 #FF00FF**，再走 `key_magenta`

**卡点（2026-11-20）**：Paper 免费版 **MCP 每周配额用完**，导出暂停，明天重置。
工具已写好：`tools/paper_gen.py`（生成 + 拖参考图 + 回车 + 轮询 + 导出 + 抠图）。

> 画布上的两张参考图要分开放：Paper 粘贴图片总是落在同一个点，会互相遮挡，
> 贴完第一张要立刻拖走再贴第二张。

---

## 七、两位角色的设定（来自你给的两张参考图）

### 小西（西湖大学发布的虚拟形象）

| 部位 | 设定 |
|---|---|
| 头发 | 深藏青长发（≈ `#1F2B5B`），发梢微卷，橙色发箍（≈ `#F7941E`） |
| 眼睛 | 蓝紫色，大眼，笑时眯成弯月 |
| 服装 | 白色水手风连帽连衣裙，藏青百褶裙与镶边，胸口橙色大蝴蝶结，中心白色 `W` 标 |
| 配饰 | 白色小兔斜挎包（兔耳是橙色的） |
| 鞋 | 白底橙边运动鞋，鞋侧 `W` |
| 体型 | Q 版 2.5 头身，干净赛璐璐上色 |
| 主色 | 藏青 `#1F2B5B` · 橙 `#F7941E` · 白 · 浅蓝灰 |

### beta（第二形象）

| 部位 | 设定 |
|---|---|
| 头发 | 银白色长发，头顶一对兔耳 |
| 发饰 | 四叶草发夹（绿色） |
| 眼睛 | 绿色 |
| 服装 | 橄榄绿连帽卫衣，抽绳两端是兔形小铃铛，衣身印小白兔 |
| 气质 | 安静、温柔，常做坐姿 |

> 两者都是学校/第三方的角色 IP。自己电脑上用没问题；**要公开发布或分发，需要学校授权**。

## 八、直接可用的生成提示词

用「参考图」模式（image-to-image / character reference），**不要纯文生图**，否则每次换脸。
每次只改「动作」那一段，其余原样保留。

### 小西 · 通用前缀

```
参考图中的角色「小西」：深藏青长发、橙色发箍、蓝紫大眼、白色水手风连帽连衣裙、
藏青百褶裙与镶边、胸口橙色蝴蝶结（中心白色 W）、白色小兔斜挎包、白底橙边运动鞋。
保持脸型、发型、服装配色、画风完全一致。Q 版 2.5 头身，全身正面站立，
脚底对齐画布底部，透明背景，四周留白 24px，干净赛璐璐上色，
左上方向光源，无投影、无文字、无水印、无边框，512×512 PNG。
```

### 小西 · 各状态动作

| 状态 | 接在前缀后面 |
|---|---|
| idle | 自然站立，双手垂在身侧，微笑平视 |
| hover | 抬头看向画面右上方，一只手抬起打招呼，笑眼 |
| syncing | 双手抱一叠资料低头翻看，身边飘 2–3 个小齿轮 |
| class | 一手抱课本，另一手抬腕看表，神情专注 |
| urgent | 着急表情，双手举起一张小纸条，额头一滴汗 |
| done | 双手举过头顶伸懒腰，闭眼笑 |
| error | 摊手，头顶一个问号，困惑表情 |

### beta · 通用前缀

```
参考图中的角色「beta」：银白色长发、头顶兔耳、绿色四叶草发夹、绿色眼睛、
橄榄绿连帽卫衣（抽绳两端是兔形铃铛，衣身印小白兔）。
保持脸型、发型、服装配色、画风完全一致。Q 版 2.5 头身，全身站立，
脚底对齐画布底部，透明背景，留白 24px，柔和赛璐璐上色，
左上方向光源，无投影、无文字、无水印，512×512 PNG。
```

beta 的动作描述可直接沿用上表，把「抱课本」换成「抱着小兔子挂件」，语气更安静。

### 生成后检查三件事

1. **背景真的是透明的**（不是白底）——PNG-32，Alpha 通道
2. **脚底在同一条线上**——否则切换状态时人会上下跳
3. **七张图的光源方向一致**——都从左上来，否则拼在一起像拼贴

## 六·补三、四书院批量流程（2026-11-21）

四个书院角色用「一张四格图 + 本机切分」的批量做法，比一个人一个人画快得多，
而且四个人的头身比天然一致：

1. **基准图**：`_archive/art/raw/houses_base.png`（四人 idle，从左到右 α β γ δ，品红底）。
2. **动作图**：在 Paper 里把基准图贴进画布、选中，Create Image（Nano Banana Pro），
   提示词里写死**从左到右的顺序**、**抬哪只手**、**每人正好两只手**、
   **纯品红 #FF00FF**。生成后把图层 W/H 改成原图比例（3168×1344）再
   Export → Copy as PNG，否则 Fill 裁切只导得半身。
3. **切分**：`tools/house_sprite.py` 按最宽的三条空白缝下刀（不是四等分，
   也不是按固定间距合并——抬起的手会伸到邻座）。
4. **归一化**：只对齐**头部高度**（HEAD_H=400），脚底统一落在 y=496。
   按总身高归一化会惩罚兔耳和帽子，β 会显得矮一截。
5. **安装**：`tools/install_houses.py` 把 idle / hover 写进
   `assets/pet/{alpha,beta,gamma,delta}/`；缺的状态会回落到 idle，
   所以可以先把 idle + hover 装上，其余五张按批次补。

目前的 hover 源图是 `_archive/art/drafts/hover4_paper_v4.png`（四人单手挥手，各两只手）。
