# UI_REDESIGN.md — TP-Link ATP Web UI 视觉重设计方案

> 参考 TP-Link Omada / Tauc / Aginet 专业网管 UI 风格。  
> 约束：自托管、免费、低复杂度、零前端构建，保持原生 Flask + 原生 HTML/CSS/JS，不改后端 API。

---

## 1. 问题陈述

现有 `templates/index.html`（单文件内联，431 行）功能可用，但与 TP-Link 旗下专业网管产品差距明显：

- 无深色/浅色主题切换
- 无侧边栏导航、无顶部设备状态栏
- 状态反馈仅靠 Toast + 表格颜色，无统一状态徽章体系
- 后端已有 `/api/reports`（历史报告）与 `state[cid].logs`（执行日志），前端未展示，功能孤岛
- 前端 `CASE_META` 与后端 `CASES` 重复维护用例标题/Stage
- 3s 轮询 + 全局 busy 锁，体验粗糙

**核心定位**：不是克隆 Omada 全功能平台（拓扑图、多租户、告警中心），而是一个单人自托管、Docker 内运行、看起来专业、能出截图报告的自动化测试控制台。

---

## 2. 用户与场景

| 维度 | 说明 |
|------|------|
| 主要用户 | TP-Link 路由器/AP QA 工程师、自托管运维人员 |
| 部署环境 | Docker 容器，访问 `http://<host>:5000` |
| 核心流程 | 查看网关状态 → 修改配置 → 选 Stage/单条用例 → 运行 → 看进度、状态、截图、日志 → 翻阅历史报告 |
| 设备 | 桌面为主（1366×768 以上），移动端仅基本可用 |
| 约束 | 免费、无外部 SaaS、无前端构建、不引入用户体系 |

---

## 3. MVP 范围（In / Out of scope）

### In scope
1. **布局**：顶部状态栏（品牌、设备在线、运行状态、主题切换） + 可折叠侧边栏（概览/配置/用例/报告/日志/设置） + 主内容区
2. **主题**：浅色/深色切换，持久化到 `localStorage`，配色参考 Omada（TP-Link 蓝 `#005a9e`）
3. **概览页**：指标卡（总数/通过/失败/运行中/跳过）+ 全局进度条
4. **配置页**：分组卡片（网关/凭证/WiFi/行为），与 `/api/config` 对齐，密码明/密文切换
5. **用例看板页**：按 Stage 分组表格，状态徽章（RUNNING 带呼吸动画）、时长、截图缩略图、重试/查看日志
6. **报告库页**：调用 `/api/reports`，列出历史运行目录，打开截图和 `summary_report.html`
7. **日志页**：展示用例执行日志（`state[cid].logs`）
8. **截图画廊**：保留并美化现有模态框，支持缩略图、点击放大、下载
9. **交互**：Toast、进度条、3s 轮询、表格悬浮高亮、空状态页

### Out of scope（V2+）
- 设备拓扑图、实时拓扑感
- WebSocket/SSE（3s 轮询先够用）
- 用户登录/权限/TLS（自托管单人场景，推荐 Tailscale/Headscale 访问）
- 前端框架（Vue/React）及构建工具
- 移动端专属体验

---

## 4. 视觉设计规范

### 4.1 色彩系统（CSS 变量）

浅色：
- `--bg-body: #f8fafc`；`--bg-surface: #ffffff`；`--bg-sidebar: #f1f5f9`
- `--brand: #005a9e`；`--brand-hover: #004a82`
- `--text-primary: #1e293b`；`--text-secondary: #64748b`
- `--border: #e2e8f0`；`--shadow: 0 1px 3px rgb(0 0 0 / 0.08)`
- `--success: #15803d`；`--danger: #dc2626`；`--warn: #ca8a04`

深色（`[data-theme="dark"]`）：
- `--bg-body: #0f172a`；`--bg-surface: #1e293b`；`--bg-sidebar: #0f172a`
- `--brand: #38bdf8`；`--brand-hover: #60a5fa`
- `--text-primary: #f1f5f9`；`--text-secondary: #94a3b8`
- `--border: #334155`；`--shadow: 0 4px 6px rgb(0 0 0 / 0.3)`
- `--success: #34d399`；`--danger: #f87171`；`--warn: #fbbf24`

通用：`--radius: 8px`；字体 `system-ui, -apple-system, Segoe UI, Roboto, "Noto Sans SC", sans-serif`

### 4.2 共用组件
- **状态徽章**：圆点 + 文字，PASS 绿 / FAIL 红 / PENDING 灰 / SKIP 灰 / RUNNING 黄色呼吸动画
- **指标卡**：大数字 + 辅助标题 + 趋势图标
- **进度条**：高 6px，圆角 3px，品牌色填充，右侧百分比
- **Toast**：顶部居中，3s 自动消失
- **模态框**：遮罩 + 圆角内容框，ESC / 点击遮罩关闭，用于截图画廊、报告预览、日志详情
- **图标**：SVG 内联或 Unicode 字符（⚡、⚙️、📋、📷、🔔、🌙/☀️），零外部依赖

---

## 5. 布局方案

```
┌─────────────────────────────────────────────────────────────┐
│  Top Bar                                                      │
│  [Logo] ATP · TP-Link Automation Test Platform   [Theme][?] │
│  [Gateway: online ●] [Run: idle] [Progress: ████ 60%]      │
├──────────┬───────────────────────────────────────────────────┤
│ Sidebar  │   Main Content                                    │
│ (collapsible)                                                 │
│ • 概览  • 配置  • 用例  • 报告  • 日志  • 设置                  │
│          │   [Page Title]                                    │
│          │   [Cards / Table / Gallery]                       │
└──────────┴───────────────────────────────────────────────────┘
```

- 桌面端：侧边栏常显（可折叠为仅图标）
- 移动端（≤768px）：侧边栏抽屉，表格横向滚动

---

## 6. 三个替代方案对比（最终决策）

| 维度 | A：渐进式单页重构（选定） | B：Flask 多页 Jinja2 模板 | C：Alpine.js / Vue CDN |
|------|--------------------------|---------------------------|------------------------|
| 改动面积 | 小（仅前端单文件） | 大（改路由 + 拆模板） | 中（引入运行时） |
| 构建依赖 | 无 | 无 | 无（CDN）但引入框架运行时 |
| 与现有 API 兼容 | 零兼容问题 | 需调整路由返回 HTML | 零兼容问题 |
| 符合“低复杂度”偏好 | ✅ 最符合 | ⚠️ 增加后端模板复杂度 | ❌ 违背无框架偏好 |
| 决策 | **采用方案 A** | V2 预留 | 备选 |

---

## 7. 前端实现建议（与后端集成）

### 7.1 文件结构
保持 `templates/index.html` 自包含单文件（`<style>` + `<script>` 按模块分节），零 Flask 路由改动。未来若需拆分，再改 `atp_web.py` 的 `index()` 为 `render_template('index.html')` 并用 `url_for('static', ...)`。

### 7.2 API 集成点

| 前端需求 | 后端接口 | 备注 |
|----------|----------|------|
| 初始化状态 + 配置 + 用例 | `GET /api/state` | 3s 轮询 |
| 保存配置 | `POST /api/config` | 返回 `{ok:true}` |
| 运行 Stage / 单条用例 | `POST /api/run` | body `{stage, case, config}` |
| 查看截图 | `GET /screenshot/<path>` | 直接用 `src` |
| 历史报告 | `GET /api/reports` | 报告库页使用 |
| 用例日志 | `GET /api/state` 中 `state[cid].logs` | 新增日志页，前端当前未展示 |

### 7.3 关键代码示例

**主题切换（CSS 变量）**
```css
:root {
  --bg-body: #f8fafc;
  --bg-surface: #ffffff;
  --bg-sidebar: #f1f5f9;
  --brand: #005a9e;
  --brand-hover: #004a82;
  --text-primary: #1e293b;
  --text-secondary: #64748b;
  --border: #e2e8f0;
  --success: #15803d;
  --danger: #dc2626;
  --warn: #ca8a04;
  --radius: 8px;
  --shadow: 0 1px 3px rgb(0 0 0 / 0.08), 0 1px 2px rgb(0 0 0 / 0.06);
}
[data-theme="dark"] {
  --bg-body: #0f172a;
  --bg-surface: #1e293b;
  --bg-sidebar: #0f172a;
  --brand: #38bdf8;
  --brand-hover: #60a5fa;
  --text-primary: #f1f5f9;
  --text-secondary: #94a3b8;
  --border: #334155;
  --success: #34d399;
  --danger: #f87171;
  --warn: #fbbf24;
  --shadow: 0 4px 6px rgb(0 0 0 / 0.3);
}
```

```js
function setTheme(theme) {
  document.documentElement.setAttribute('data-theme', theme);
  localStorage.setItem('atp-theme', theme);
  document.getElementById('theme-toggle').textContent = theme === 'dark' ? '☀️' : '🌙';
}
// 初始化
const saved = localStorage.getItem('atp-theme') || 'light';
setTheme(saved);
```

**状态徽章**
```html
<span class="badge badge--running" title="正在执行">
  <span class="badge__dot"></span> Running
</span>
<span class="badge badge--pass"> Passed </span>
<span class="badge badge--fail"> Failed </span>
```
```css
.badge { display: inline-flex; align-items: center; gap: 6px; padding: 2px 8px; border-radius: 999px; font-size: 0.72rem; font-weight: 700; }
.badge__dot { width: 6px; height: 6px; border-radius: 50%; }
.badge--running .badge__dot { background: var(--warn); animation: pulse 1.5s infinite; }
.badge--pass { background: #ecfdf5; color: var(--success); }
.badge--fail { background: #fef2f2; color: var(--danger); }
.badge--pending { background: #f3f4f6; color: var(--text-secondary); }
@keyframes pulse { 0%,100%{opacity:1} 50%{opacity:0.4} }
```

### 7.4 迁移步骤
1. 按 `UI_REDESIGN.md` 规范重写 `templates/index.html`（保留原有 API 调用逻辑，仅替换 UI 层）。
2. 前端 `CASE_META` 可保留，但建议后续让 `/api/state` 返回用例标题与 Stage，消除前后端重复维护。
3. 日志页直接使用 `/api/state` 已返回的 `logs` 字段，无需新接口。
4. Docker 容器内刷新页面即生效，无需重新构建镜像（静态文件挂载或 `docker cp` 即可）。

---

## 8. 验收标准（Definition of Done）

- [ ] 页面呈现顶部状态栏 + 侧边栏 + 主内容区三段式布局
- [ ] 点击主题切换按钮，页面立即切换浅色/深色，刷新后保持所选主题
- [ ] 配置卡片可编辑，点击保存后 Toast 提示“已保存”，后端 `/api/config` 已更新
- [ ] 用例看板按 Stage 分组，状态徽章颜色正确，RUNNING 有呼吸动画
- [ ] 点击“运行”后进度条推进，Toast 提示提交成功
- [ ] 报告库页列出 `reports/` 下历史目录，可打开截图和 `summary_report.html`
- [ ] 日志页可查看选中用例执行日志
- [ ] 在 1366×768 和 768px 宽度下均无明显布局破坏
- [ ] 不引入任何前端构建依赖，Docker 容器内直接刷新生效

---

## 9. 成功愿景（Golden Age）

用户打开 ATP Web UI，看到深色主题下的侧边栏与顶部状态栏，网关在线状态绿点常亮，进度条平滑推进，用例以红绿灯状态排列整齐，失败时一键重试并立即看到截图与日志，历史报告可在报告库里翻阅。整个体验不输于 Omada 管理控制台，但部署只需一个 `docker run`，维护只需改一个 HTML 文件。