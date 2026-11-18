# DESIGN_UI.md — TP-Link ATP Web UI (Omada/Tauc/Aginet 风格对齐)

> 状态：草稿 / MVP 阶段  
> 适用：`templates/index.html`（原生 HTML/CSS/JS，无构建步骤，Flask 模板直接渲染）  
> 后端契约：`/api/state`, `/api/run`, `/api/config`, `/screenshot/<path>`, `/api/reports`  
> 伴随文件：`DESIGN.md`（架构/安全/Alternative B 评审，此处不重复）

## 1. 问题陈述（重新表述）

TP-Link ATP 自动化测试平台现有前端 `templates/index.html` 已具备深色侧边栏 + 浅色内容区布局，并已对接 Flask 五个 API。用户希望界面更贴近 TP-Link 旗下专业网管产品（Omada SDN 控制器、TAUC、Aginet）的视觉与交互风格，同时保持“免费、自托管、可容器化、无构建步骤、原生 HTML/CSS/JS”的约束，避免范围蔓延。

核心问题：需要明确哪些 UI 元素可直接沿用、哪些需替换为 Omada 风格，并给出可直接落地的代码片段与 API 对接边界；不引入 Vue/React 等新前端框架。

## 2. 调研结果（Omada / TAUC / Aginet UI 特征）

调研来源：TP-Link Omada SDN Controller 用户指南（V5.12 / V6.0）、Omada Central Start Guide、TAUC 产品页面与网络研讨会。

### 2.1 导航结构
- **左侧导航栏（Left Navigation Bar）**：任务导向菜单，固定宽度，深色背景，图标 + 文字，支持全局视图 / 站点视图切换。
- **右上角快捷区（Top-right corner）**：站点管理下拉（Sites dropdown）、关于、教程、反馈、布局切换。
- **页面标题区**：面包屑 + 当前站点/环境标识，清晰告知用户当前在“哪个站点”做“哪件事”。

### 2.2 配色方案（十六进制）
| 用途 | 值 | 说明 |
|---|---|---|
| 主蓝（TP-Link Blue） | `#005A9E` | 主按钮、活跃导航、卡片顶边框、链接 |
| 主蓝悬停 | `#004A82` | 主按钮悬停 |
| 主蓝浅色 | `#EEF4FB` | 次要背景、徽章背景 |
| 深色侧边 | `#0F172A` / `#1E293B` | 侧边栏背景 |
| 内容区背景 | `#F1F5F9` | 页面整体背景 |
| 卡片 | `#FFFFFF` | 卡片背景 |
| 浅边框 | `#E2E8F0` | 卡片/表单边框 |
| 文本 | `#334155` | 正文 |
| 辅助灰 | `#64748B` | 次要文本 |
| 通过/在线 | `#15803D` | PASS、在线状态 |
| 失败/离线 | `#DC2626` | FAIL、离线、危险操作 |
| 进行中/警告 | `#CA8A04` | RUNNING、警告 |
| 待处理 | `#64748B` | PENDING、禁用 |

### 2.3 按钮逻辑
- Primary：填充 `#005A9E`，白字，悬停加深，禁用半透明。
- Ghost/Outline：白底或透明底，浅灰/蓝边框，点击轻微背景变化。
- Success：填充 `#15803D`，用于成功反馈。
- Danger：填充 `#DC2626`，用于删除/重启/固件升级等破坏性操作。
- 状态芯片：带圆点动画（RUNNING 脉冲），PASS/FAIL 静态。

### 2.4 布局模式
- 仪表盘小部件（Widget-driven Dashboard）：统计卡片 + 进度条 + 快速操作栏。
- 设备/用例列表表格：固定表头，悬停高亮，状态芯片 + 操作按钮组。
- 截图光箱（Lightbox）：点击缩略图弹出大图，支持“在新标签页打开”。

## 3. 与现有 Flask API 的对接边界

| 前端模块 | 对应 API | 可直接对接 | 需后端配合 |
|---|---|---|---|
| 概览统计卡 | /api/state (cases, progress) | ✅ 是 | 否 |
| 执行进度条 | /api/state (progress) | ✅ 是 | 否 |
| Stage / 单用例运行 | /api/run (POST) | ✅ 是 | 否 |
| 配置表单读写 | /api/config (GET 脱敏 + POST) | ✅ 是 | 否 |
| 保存反馈 | /api/config POST 返回 {ok} | ✅ 是 | 否 |
| 截图缩略图 / 光箱 | /screenshot/<path> | ✅ 是 | 否 |
| 报告列表 | /api/reports | ✅ 是 | 否 |
| 设备在线/拓扑 | 无现成 API | ❌ 否 | 需新增 /api/devices |
| 实时执行日志 | /api/state 轮询（3s） | ⚠️ 可继续 | 若需实时，需 SSE/WebSocket |
| 配置详细校验错误 | validate_config（后端已有） | ⚠️ 基础可做 | 详细错误需接口返回 |

**结论**：现有 5 个 API 足够支撑核心测试平台流程；仅“拓扑可视化”“实时日志”“配置校验详情”三项若做增强，才需后端新增接口。

## 4. 三个实施方案比较

| 维度 | 方案 A：渐进增强（推荐 MVP） | 方案 B：Omada 全局/站点视图 | 方案 C：极简顶部标签导航 |
|---|---|---|---|
| 思路 | 现有模板上更新配色、加站点选择器、设备状态卡 | 仿 Omada 做 Global/Site View 切换，右上角站点下拉 | 去掉侧边栏，顶部标签切换视图 |
| 前端工作量 | 小 | 中 | 中 |
| 后端配合 | 无 | 需 /api/sites | 无 |
| 与现有 API 兼容性 | 100% | 需新增站点接口 | 100% |
| 风险 | 低 | 中（范围蔓延） | 低 |
| 决策 | 先落地 A，预留站点选择器 DOM，后续升级 B | — | — |

## 5. 可直接落地的代码片段（templates/index.html）

### 5.1 CSS 变量更新（替换 :root 块）

```css
:root{
  --tp-blue:#005a9e;
  --tp-blue-hover:#004a82;
  --tp-blue-light:#eef4fb;
  --ink:#0f172a;
  --surface:#1e293b;
  --bg:#f1f5f9;
  --card:#ffffff;
  --border:#e2e8f0;
  --text:#334155;
  --muted:#64748b;
  --success:#15803d;
  --success-bg:#ecfdf5;
  --danger:#dc2626;
  --danger-bg:#fef2f2;
  --warn:#ca8a04;
  --warn-bg:#fefbeb;
  --shadow:0 1px 3px rgba(0,0,0,0.08),0 1px 2px rgba(0,0,0,0.06);
  --radius:8px;
  --transition:0.2s ease;
}
```

### 5.2 右上角站点/环境选择器（插入 .topbar-right）

```html
<div class='site-select' style='display:flex;align-items:center;gap:8px;border:1px solid var(--border);border-radius:8px;padding:4px 10px;background:#fff;'>
  <span class='nav-icon' style='font-size:1rem'>🏢</span>
  <select id='site-select' style='border:none;background:transparent;font-size:0.875rem;color:var(--text);outline:none;cursor:pointer'>
    <option value='default'>Default Site · 默认站点</option>
    <option value='lab'>Lab · 实验室环境</option>
    <option value='prod'>Prod · 生产环境</option>
  </select>
</div>
```

对应 JS：

```javascript
$('#site-select').addEventListener('change', function(e){
  toast('已切换至：' + e.target.selectedOptions[0].text);
  // 预留：切换站点后可重新 load() 并带 site 参数
});
```

### 5.3 设备在线状态卡片（概览页统计卡片行之后追加）

```html
<div class='grid grid-4' style='margin-top:16px'>
  <div class='stat-card total'>
    <div style='display:flex;align-items:center;justify-content:space-between'>
      <div>
        <div class='stat-label'>网关设备</div>
        <div class='stat-value' id='stat-gateway'>1</div>
      </div>
      <span class='status PASS dot'>在线</span>
    </div>
  </div>
  <div class='stat-card pass'>
    <div style='display:flex;align-items:center;justify-content:space-between'>
      <div>
        <div class='stat-label'>在线 AP</div>
        <div class='stat-value' id='stat-ap'>3</div>
      </div>
      <span class='status PASS dot'>3 在线</span>
    </div>
  </div>
  <div class='stat-card fail'>
    <div style='display:flex;align-items:center;justify-content:space-between'>
      <div>
        <div class='stat-label'>离线设备</div>
        <div class='stat-value' id='stat-offline'>0</div>
      </div>
      <span class='status FAIL dot'>离线</span>
    </div>
  </div>
  <div class='stat-card todo'>
    <div style='display:flex;align-items:center;justify-content:space-between'>
      <div>
        <div class='stat-label'>待采集</div>
        <div class='stat-value' id='stat-pending'>0</div>
      </div>
      <span class='status PENDING dot'>待处理</span>
    </div>
  </div>
</div>
```

JS（在 renderStats 之后追加）：

```javascript
function renderDeviceStatus(){
  const c = cases || {};
  const pass = Object.values(c).filter(x => (x.status||'PENDING').toUpperCase()==='PASS').length;
  const fail = Object.values(c).filter(x => (x.status||'PENDING').toUpperCase()==='FAIL').length;
  const ids = Object.keys(c);
  $('#stat-gateway').textContent = 1;
  $('#stat-ap').textContent = pass > 0 ? pass : 3;
  $('#stat-offline').textContent = fail;
  $('#stat-pending').textContent = ids.length - pass - fail;
}
```

### 5.4 新增按钮变体（追加到 CSS）

```css
.btn.success{background:var(--success);color:#fff;border-color:var(--success)}
.btn.success:hover{background:#166534}
.btn.outline{background:#fff;color:var(--tp-blue);border-color:var(--tp-blue)}
.btn.outline:hover{background:var(--tp-blue-light)}
.btn.text{background:none;border:none;color:var(--tp-blue);padding:6px 10px;font-size:0.875rem;font-weight:500}
.btn.text:hover{background:var(--tp-blue-light);border-radius:6px}
```

### 5.5 配置保存详细反馈（替换 saveConfig）

```javascript
async function saveConfig(){
  const r = await fetch('/api/config',{
    method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(cfg)
  });
  const d = await r.json();
  const b = document.createElement('span');
  b.className = 'saved-badge';
  b.textContent = d.ok ? '已保存' : '保存失败';
  b.style.color = d.ok ? 'var(--success)' : 'var(--danger)';
  const btn = $('#btn-save'); btn.appendChild(b);
  setTimeout(()=>b.remove(),1500);
  toast(d.ok ? '配置已保存' : (d.error||'保存失败'));
}
```

## 6. MVP 范围（In Scope / Out of Scope）

### In Scope
1. CSS 变量对齐 TP-Link/Omada 调色。
2. 顶部栏右侧站点/环境选择器（静态切换提示，预留接口位）。
3. 概览页设备在线状态卡片（首版占位数据，后续接 /api/devices）。
4. 新增按钮变体 .success、.outline、.text。
5. saveConfig() 按 /api/config 返回 ok 字段给出成功/失败反馈。
6. 保持现有全部功能不变。

### Out of Scope（Phase 2，需后端配合）
1. 引入 Vue/React/Angular 或任何构建步骤。
2. 新增 /api/devices、WebSocket/SSE 实时日志、配置详细校验错误接口。
3. 多租户/组织体系、SAML SSO、云绑定。

## 7. 验收标准
- [ ] 页面在 Chrome/Edge/Firefox 下无构建步骤即可直接打开（Flask 渲染 templates/index.html）。
- [ ] 主色 #005A9E 用于主按钮、活跃导航、卡片顶边框。
- [ ] 站点选择器下拉可切换并弹出 toast 提示。
- [ ] 配置保存后显示“已保存”（绿）或“保存失败”（红）徽章。
- [ ] 所有现有 API 对接保持不变（/api/state, /api/run, /api/config, /screenshot/, /api/reports）。
- [ ] Docker 部署（docker-compose.yml network_mode: host）无需修改。

## 8. 成功状态（Golden Age）

工程师在任何 Linux 主机上执行 `docker compose up -d --build atp-web`，打开浏览器访问 `http://localhost:5000`，即可看到 Omada 风格的深色侧边栏仪表盘：左侧导航清晰（概览/配置/测试看板/报告），右上角站点选择器预留，概览页统计卡片与设备状态卡片使用 TP-Link 主蓝 `#005A9E`，运行按钮一键触发 `/api/run`，执行进度与状态芯片实时反映 `/api/state`，截图点击可放大预览，报告列表可浏览历史截图；配置表单修改后点击“保存配置”收到“已保存”绿色反馈。无构建步骤、无新前端框架、Docker 可容器化，低压输出，可持续运维。
