# TP-Link ATP Web UI — 截图自动高亮 + Omada/Tauc/Aginet 风格界面改造

> 会话角色：CEO Product Thinker (`/office-hours`)。本文为 `/root/Repos/github.com/Cyhandleit/TPLINK-ATP-SCRIPT` 的前端/截图增强需求做产品定义与实施计划。不修改既有 `DESIGN.md`（架构/安全层面的 CEO 评审文件保持原样）。

---

## 1. 问题重新定义 (Problem Statement)

TP-Link ATP Web UI 已能在测试执行过程中通过 Playwright 截图并保存到 `reports/`，前端也有截图画廊模态框，但存在两个产品缺口：

1. **通过用例缺乏"成功状态截图"证据，且截图是盲文档**。现有逻辑在用例执行过程中零散截图，没有明确的"用例通过后自动留存最终状态截图"的保证；更重要的是，截图里没有标注"哪个按钮/哪个页面被验证了"，测试工程师翻阅报告时无法一眼定位验证点，证据价值低。
2. **前端视觉与交互粗糙**。当前 `templates/index.html` 为功能优先的原生页面（配置卡片 + 用例看板 + 画廊），缺乏 TP-Link 企业网络产品（Omada / Tauc / Aginet）的一致视觉语言：侧边栏导航、状态徽章、数据表格、统计卡片等模式缺失，日常配置/看板/报告切换路径不清晰。

目标：在**不引入新前端框架、不改动 Flask API 契约、不新增后端服务**的前提下，在单文件 Flask 模板内完成：(a) 用例通过后自动截图，并在截图上用红色方框标注关键按钮/页面元素；(b) 用 Omada/Tauc/Aginet 风格重构 Web UI。

---

## 2. 目标用户与“头枪着火”的痛点

- **用户**：TP-Link 固件测试工程师，局域网内通过 Web UI 触发路由器连接/功能自测（Stage 1~5），需要可交付的带截图证据的执行结果。
- **头枪着火问题**：“我需要一张能直接贸入报告的截图，截图里能一眼看出哪个配置项/按钮被验证通过了，而不用在几十张缩略图里猜。”
- **具体画像**：测试工程师在 `192.168.1.1` 路由器 Web UI 上完成登录 → WAN 设置 → 诊断等流程，期望 ATP 自动把"最终状态页 + 被点击的关键按钮"以红框标出并保存。

---

## 3. 最小可行范围 (MVP)

### In scope (P0)

| # | 内容 |
|---|------|
| 1 | 后端新增配置项 `case_highlights`（`case_id → CSS 选择器列表`），写入 `atp_config.py` `DEFAULT_CONFIG`，前端通过现有 `/api/config` 读写。 |
| 2 | `atp_web.py` `ATPWebEngine` 新增 `_highlight_regions`：用 Playwright 定位选择器元素、PIL 在截图上绘制 TP-Link 红 (#dc2626) 圆角方框，覆盖写回原截图文件，`/screenshot/` URL 契约不变。 |
| 3 | 用例执行结束且 `status == "PASS"` 且有截图时，对**该用例最后一张截图**（最终状态画面）应用红框高亮；FAIL/SKIP 不动，保留原始现场。选择器不匹配或页面已关闭时静默跳过，不影响用例状态。 |
| 4 | `templates/index.html` 单文件重构：侧边栏导航 + 四个视图（概览、配置管理、测试看板、报告与截图），保留全部现有 API (`/api/state`, `/api/run`, `/api/config`, `/screenshot/`, `/api/reports`)、Toast 提示、3s 自动轮询、运行忙碌状态。 |
| 5 | 配置视图新增 `case_highlights` JSON 编辑框，按路由器型号调整高亮选择器，无需改文件即可生效。 |

### Out of scope (本次不做)

- 新增后端服务、报告生成服务、前端构建工具链（Vite/React/Vue 等）。
- 对纯 API 用例（10.x ACS/TR-069）补浏览器截图——保持文字证据。
- 多用户权限、TLS、Web UI 降级为只读看板（这些已在 `DESIGN.md` Alternative B 规划，不在本次 UI 范围内）。
- 根据 `visual-designer-consultant` 的具体交付物逐像素还原（该方案未随任务交付；本设计按 Omada/Tauc/Aginet 公开视觉语言自行界定，见 §7 视觉规范）。

---

## 4. 三种方案对比（强制比选）

| 维度 | 方案 A（采用）：后端 Playwright 定位 + PIL 红框，写回原截图 | 方案 B：前端画廊 SVG/Canvas 叠加红框层 | 方案 C：Playwright 逐元素单独截图再拼接合成图 |
|---|---|---|---|
| 红框是否随图保存/分享 | ✅ 烘焙进 PNG | ❌ 仅浏览器端显示，下载后丢失 | ✅ |
| 前端复杂度 | 零侵入 | 高（需坐标换算、缩放适配、画廊裁切对齐） | 零 |
| 后端复杂度 | 中（需滚动/视口/全页截图比例换算） | 需新增元素坐标 API | 中 |
| 测试执行时间影响 | 无（仅在 PASS 后处理最后一张图） | 无 | 显著变慢（每个关键元素额外定位+截图）|
| 脆性 | 元素不可见时静默跳过 | 坐标易因截图缩放而位移，误标风险高 | 元素在两次截图间滚动即不一致 |
| 窄楔程度 | 最窄 | 中 | 宽 |

**决策：方案 A**。它是 narrowest wedge，对现有流程零侵入，且红框直接固化在证据图里，最符合测试工程师的交付需求。

---

## 5. 关键设计决策

1. **高亮只作用于每个用例的最后一张截图**（最终状态页）。多张截图页面状态不一致（如 1.1 经过了登录页→超级管理页→无线页），红框若套错页面会误导。
2. **仅 PASS 时高亮**。FAIL/SKIP 保留未修改的原始现场，便于排障对比。
3. **坐标换算**：Playwright `getBoundingClientRect() + scrollOffset` 得到文档坐标，再按 `image_size / document_scroll_size` 缩放到全页截图尺寸，避免 `bounding_box` 视口/全页歧义。
4. **配置优先于代码**：选择器通过 `case_highlights` 配置，默认 `{}`，随路由器型号（Omada SDN 控制器风格 vs 传统 SMB Web UI）调整；不写死选择器进代码。
5. **前端保持单文件、原生 JS、无构建步骤**，与现有 Docker 部署（`python atp_web.py` 或镜像）完全兼容。

---

## 6. 视觉规范（Omada / Tauc / Aginet 风格）

- 色调：TP-Link 深蓝 `#005a9e`（主色，与既有变量保持一致）、侧边栏深色 `#0f172a`、`#1e293b`、卡片白底 `#ffffff`、边框 `#e2e8f0`、正文 `#334155`、辅助文字 `#64748b`。
- 状态语义：PASS 绿 `#15803d`、FAIL 红 `#dc2626`、PENDING 灰 `#94a3b8`、RUNNING 黄 `#ca8a04`（脉冲动画）。
- 组件：侧边固定导航（概览/配置/测试看板/报告与截图）、顶栏（忙碌状态点、刷新、保存）、统计卡片（总/通过/失败/进行中）、带进度条的执行概览、数据表格 + 状态芯片 + 截图缩略图、全屏截图灯箱、Toast 轻提示。
- 字体：系统无衬线字体栈，圆角 8~12px，轻阴影，密集信息区用紧凑行高。

---

## 7. 验收标准 (DoD)

1. `python -m py_compile atp_web.py atp_config.py` 通过（本环境缺 flask/playwright，仅做语法检查；E2E 需在有真实路由器的宿主机上跑）。
2. 离线单元检查：`_highlight_regions` 在给定样本 PNG + 模拟页面对象（返回 `getBoundingClientRect`/`scroll`/`scrollSize`）时，输出文件被修改，且方框位置出现红色像素 `(220,38,38)`。
3. `GET /` 返回新模板 HTML，包含侧边栏四个视图入口及概览/配置/看板/报告四个区块；`/api/state`、`/api/run`、`/api/config`、`/screenshot/`、`/api/reports` 契约与既有前端字段完全兼容。
4. `DEFAULT_CONFIG` 新增 `case_highlights: {}`；配置视图可编辑并通过 `/api/config` 保存 JSON。
5. 产出文件：`IMPLEMENTATION_PLAN.md`（本文）、修改的 `atp_config.py`、`atp_web.py`、重构的 `templates/index.html`。

---

## 8. 后续（Out of MVP，可排入下一迭代）

- 截图红框带序号标注（1、2、3…）并配图例说明每个选择器对应什么。
- 失败用例自动对比截图（前后帧 diff）。
- 与 `DESIGN.md` Alternative B 对齐：Web UI 降级为只读报告看板，执行能力下沉到 CLI。

---

**金色时代（成功状态）**：测试工程师点击“Run All”，所有用例跑完后，概览页绿色通过数实时更新；点进测试看板，每个 PASS 用例的缩略图右下角即可见红框标注的关键按钮；点开画廊，大图上的红框清晰指示验证点；配置页一处粘贴 JSON 选择器，适配下一款路由器型号后红框自动跟随。整个流程无需离开浏览器，无需装任何前端框架。
