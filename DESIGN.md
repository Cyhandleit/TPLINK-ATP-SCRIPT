# TP-Link ATP — 产品与架构设计（CEO Product Thinker 审评）

> 会话角色：CEO Product Thinker（/office-hours）。本文件是对 /root/Repos/github.com/Cyhandleit/atp-project 的架构、网络、安全、可用性评审，并给出可执行后续任务。

---

## 1. 问题陈述（重构后）

团队手头有一份基于 TPLINK-ATP-SCRIPT 的 TP-Link 路由器固件自动化测试脚本，已初步 Docker 化为两个 Compose 服务（Flask Web UI + CLI 引擎），可在 Linux 宿主机上通过 `docker compose` 启动。但目前处于“能跑通个流程”阶段，距离“可稳重复使用、安全、可维护”还有一段距离：

- **硬编码密码与弱默认值仍留在代码里**：`atp_engine.py` / `atp_web.py` 中 `ATP_ADMIN_PASS`、`ATP_SUPERADMIN_PASS` 等均有 `default=` 兜底；`.env.example` 还把 `admin1234` / `superadmin1234` / `TaucPass123!` 明文写进仓库。用户一路 `cp .env.example .env` 不改，测试就会用弱默认密码去登录路由器（SEC-01/02 未修复）。
- **Web UI 无认证、无 TLS、监听 `0.0.0.0:5000`**：局域网内任何设备都能远程触发路由器重启、固件升级；直接暴露到公网/远程办公环境是灾难（SEC-03 表面修复，但访问控制缺失）。
- **长稳 Ping 语义错误**：把“运行 300 秒”实现成“发 300 个 ICMP 包”，实际耗时远超预期；UI 点一下会卡数分钟且无进度提示（BEHAV-01）。
- **Stage 2 必然失败**：`speedtest-cli` 用于吞吐量测试，却不在 `requirements.txt` 中，容器内命令缺失，相关用例全面报错。
- **报告路径不一致**：CLI 引擎写容器内 `ATP_Report_*`（volume 外，容器重启后丢失），Web UI 写 `reports/`（volume 内）；两套目录体系，无清理策略，磁盘会无限增长。
- **`network_mode: host` 锁定 Linux**：macOS/Windows 无法直接使用，跨平台主张落空；README 只提了问题，未给 bridge 版本参考。

**核心问题不是“缺功能”，而是试图一次做成全套测试平台，导致核心链路（连通性测试 → 报告输出）不够稳，安全底线未达，维护成本过高。**

---

## 2. 目标用户与“头着火”的问题

- **用户**：负责 TP-Link 固件质量的测试工程师，Linux 宿主机/内网环境工作，需要可复现、可容器化的自动化测试，输出可交付的带截图 HTML 报告。
- **头着火的问题**：“我需要一条命令，在不改动宿主机环境的前提下，把路由器连通性/基础功能测试跑完，并拿到带截图的 HTML 报告。”

---

## 3. 现状评审（架构 / 网络 / 安全 / 可用性）

### 架构

| 项 | 现状 | 问题 | 严重度 |
|---|---|---|---|
| 服务划分 | atp-web + atp-engine 共用同一 Dockerfile，通过 `command` 区分 | 合理，但 atp-engine 占位命令 `--help` 无实际价值 | 中 |
| 配置加载 | 环境变量 + `config.json`；两服务顺序不一致（engine 只读环境变量，web 优先 `config.json`） | `config.json` 被 Web UI 修改后，engine 不可见；配置不一致 | 中 |
| 报告路径 | engine → 容器内 `ATP_Report_*`；web → `reports/` volume | engine 报告重启后丢失；两套目录体系 | 高 |
| 依赖 | `speedtest-cli` 用于 Stage 2 但未列在 `requirements.txt` | Stage 2 因命令缺失全面失败 | 高 |
| 镜像体积 | 把 bandit/flake8 等 dev 工具装进生产镜像 | 体积膨胀，无意义 | 低 |
| 入口脚本 | `entrypoint.sh` 用 `sed` 原地修改 `atp_web.py` 切 debug | 脆弱；`__main__` 源码仍保留 `debug=True`，非标准入口可复活 debug | 中 |

### 网络

| 项 | 现状 | 问题 | 严重度 |
|---|---|---|---|
| 容器网络 | `network_mode: host` | 仅 Linux 可用；macOS/Windows 无法直达局域网路由器，README 虽说明但未提供 bridge 版本 compose | 高（可用性） |
| 端口暴露 | Flask 绑定 `0.0.0.0:5000`，无 `ports` 映射（host 模式下不可共存） | 无法调整端口；宿主机 5000 被占用则启动失败；直接暴露在宿主机所有网卡 | 中 |
| 局域网路由器访问 | 依赖 host 模式直连 192.168.1.1 | 合理于 Linux；bridge 模式下需额外路由配置，文档缺失 | 中 |
| WiFi 用例 | 容器内调用 nmcli/netsh 切 WiFi | 容器内通常无 NetworkManager/dbus，不可靠；应视为宿主机侧能力，不应在容器内依赖 | 高 |

### 安全

| 项 | 现状 | 问题 | 严重度 |
|---|---|---|---|
| 凭据 | 代码中 `default="admin1234"` 等；`.env.example` 明文示例 | 未提供 `.env` 时静默使用弱默认密码；SEC-01/02 未修复 | 高 |
| Web UI 访问控制 | 无认证、无 TLS、监听 0.0.0.0 | 局域网内任意设备可触发重启/升级；绝不可直接暴露公网 | 严重 |
| Flask debug | build 时 sed 改为 False，entrypoint 再按 `ATP_DEBUG` 切 | 源码 `__main__` 仍保留 `debug=True` | 中 |
| 敏感日志/截图 | `sensitive_regions` 默认 `{}`，不涂黑 | 截图可能泄露密码/SSID；报告目录权限未控制 | 中 |
| 接口 | `/api/config` 明文返回全部配置（含密码） | 前端明文渲染，泄露风险 | 中 |

### 可用性

| 项 | 现状 | 问题 | 严重度 |
|---|---|---|---|
| 长稳 Ping | `count=ping_seconds`（默认 3600/300） | 实际是发 300~3600 个包，耗时远超“秒”语义；UI 点击后卡死数分钟无进度 | 高 |
| 健康检查 | 无 `HEALTHCHECK` | `docker compose up -d` 无法知道 Web UI 是否就绪 | 中 |
| 状态持久 | Web UI 状态保存在进程内存 | 容器重启后看板状态清零 | 中 |
| 磁盘清理 | `reports/` 无清理策略 | 长期运行磁盘被报告和截图撑满 | 中 |
| 跨平台 | 锁定 `network_mode: host` | 非 Linux 宿主机不可直接使用 | 高 |

> 补充：`known_issues.md` 中的 CI-01~CI-04 引用 `.github/workflows/ci.yml`，但当前仓库根目录下不存在 CI 工件，这些条目对当前版本不适用，可存档或删除，勿作为必须修复项。

---

## 4. 三个改进方案（Alternatives）

### 方案 A：原地精简迭代（In-place refinement）

保留两服务 + `network_mode: host` 总体架构，在现有代码上做必修安全与可用性修复：移除代码中所有密码默认值（缺失即报错）、统一报告写 `reports/` volume、加 `HEALTHCHECK`、把 `speedtest-cli` 加入依赖或剔除 Stage 2、去掉镜像内 dev 工具、把 Flask debug 从环境变量直接控制（不再 `sed` 源码）、加 `.dockerignore`。

- 优点：改动最小，沿用现有投入，用户迁移成本低。
- 缺点：Web UI 仍无认证/TLS，攻击面未收；`shell=True`、死代码、每个 case 独立启动浏览器等代码质量问题残留；长稳 Ping 语义可选修复。
- 适合：希望快速把现有版本“跑起来且不至于出安全事故”的团队。

### 方案 B：CLI-first，Web UI 降级为只读报告看板（Narrowest wedge，推荐）

把测试执行完全收进 `atp-engine`（CLI），Web UI 只负责：读取宿主机 `reports/` 下的 HTML 报告、列表展示、删除旧报告、查看截图。**去掉 `/api/run`、`/api/config` 写入和远程触发破坏性操作的能力。** engine 报告统一写 `reports/ATP_<timestamp>/`。CLI 支持 `--stage 1\|2\|...\|all`、`--ping-seconds`、`--run-destructive`。

- 优点：攻击面最小（无远程代码执行入口、无密码在网络传输中明文返回）；最容易做到“稳重复”；与“免费、自托管、不夜班”的偏好最契合——跑完 CLI 即得报告，Web 仅做事后查看。
- 缺点：失去“点一下 UI 就跑单用例”的即时便利；用例编排仍在 Python 代码里而非可配置。
- 适合：把核心链路（连通性 → 报告）做稳、做安全的首选 MVP。

### 方案 C：库 + 独立 Runner + 可选认证 Sidecar

把 `atp_engine.py` 重构为可导入的 Python 库，去掉全局 side effects；Runner 通过环境变量或 JSON 队列触发；Web UI 可选，基于 Flask/FastAPI，仅读报告，加简单 token/basic-auth 认证，绑定 `127.0.0.1` 或经反向代理（Tailscale/Headscale）访问。

- 优点：最易写单元测试、最易接入 CI、最易未来做多租户/云原生扩展。
- 缺点：重构量大，与“低压输出、快出 MVP”目标冲突，可作为方案 B 稳定后的演进路径。
- 适合：团队后续计划把 ATP 接入 CI/CD 或 SaaS 化时采纳。

**推荐：先落地方案 B 作为 MVP，同步做方案 A 的安全必修项；方案 C 作为后续演进。**

---

## 5. MVP 范围（方案 B）

### In scope（P0，必须做）

- CLI 引擎 `docker compose run --rm atp-engine --stage 1`：基础连通性（登录、WAN 状态、Ping 网关/8.8.8.8/DNS）并输出 HTML 报告 + 截图到 `reports/`。
- 所有敏感凭据仅从环境变量读取，缺失必填项（`ATP_ADMIN_PASS`、`ATP_SUPERADMIN_PASS`）时容器运行报错退出，**不得有硬编码默认值**。
- Flask debug 生产默认 False，通过环境变量控制，不再 `sed` 源码。
- Web UI：只读报告看板（列表/详情/截图预览/删除），**不提供测试触发和配置写入 API**。
- `network_mode: host` 保留为 Linux 默认；提供 `docker-compose.bridge.yml` 供 macOS/Windows 参考。
- `HEALTHCHECK` 对 atp-web；`.dockerignore` 排除 `.env`、`reports/`、`__pycache__`、`.git/`。
- 镜像去掉 bandit/flake8（移到 dev 文档，不装进生产镜像）。

### Out of scope（MVP 不做，后续迭代）

- Web UI 远程触发单用例/阶段执行。
- WiFi 切换、吞吐量/速度测试（依赖宿主机能力，容器内不可靠，先剔除或标记 experimental）。
- 长稳 Ping 按“秒”精确控制（先保留 count 语义，但文档明确并默认降为 30~60 秒，避免用户误等一小时）。
- ACS/TR-069、固件升级、DDNS 等远程管理用例（需外部 GenieACS 和固件文件，先不进 MVP）。
- 多用户认证、RBAC、TLS 终止（建议经 Tailscale/Headscale 组网访问，不在容器内实现）。
- macOS/Windows 原生支持 bridge 并自动路由（提供参考文件，不自动化）。

---

## 6. 目标架构要点（简版）

- **配置加载优先级**：环境变量 > `config.json`（ro 挂载，可选）> 无默认密码（必填项缺失即报错）。
- **报告统一**：engine 与 web 均写 `reports/ATP_<YYYYMMDD_HHMMSS>/`，volume 挂载到宿主机；清理策略由宿主机 cron 执行（不在容器内实现）。
- **网络**：Linux 默认 host；非 Linux 使用 bridge + `extra_hosts` / `host.docker.internal`，由用户按宿主机网段调整。
- **安全**：Web UI 不直接暴露公网；远程办公经 Tailscale/Headscale 组网访问；宿主机防火墙仅开放信任网段。

---

## 7. 后续任务（可执行，带验收标准）

### P0（本周必须做，否则不能叫 MVP）

1. **移除所有密码默认值**：`atp_engine.py` / `atp_web.py` 中 `ATP_ADMIN_PASS`、`ATP_SUPERADMIN_PASS`、`TAUC_PASS`、WiFi 密码等 `default=` 替换为 `required=True`，缺失时 `RuntimeError` 退出。
   - DoD：`.env` 未设密码时，`docker compose run --rm atp-engine --help` 仍可运行；运行任意 stage 缺密码则报错并退出非零码。
2. **`.env.example` 脱敏**：删除明文密码示例，仅保留变量名和占位（如 `ATP_ADMIN_PASS=***`），并提示“不要提交真实 `.env`”。
   - DoD：`git diff .env.example` 不再包含 `admin1234` / `superadmin1234` / `TaucPass123!`。
3. **统一报告路径**：engine 报告改写 `reports/ATP_<timestamp>/`（与 web 一致）；engine 服务也挂载 `./reports:/app/reports`。
   - DoD：`docker compose run --rm atp-engine --stage 1` 结束后，宿主机 `reports/` 下出现 `ATP_*/summary_report.html`。
4. **修复 Stage 2 依赖**：要么把 `speedtest-cli` 加入 `requirements.txt`，要么从 MVP 中剔除速度测试用例（推荐先剔除，标记 experimental）。
   - DoD：`--stage 2` 不再因 `command not found` 失败。
5. **镜像精减与 `.dockerignore`**：去掉 bandit/flake8；新增 `.dockerignore` 排除 `.env`、`reports/`、`__pycache__/`、`.git/`。
   - DoD：`docker compose build` 镜像体积减小；构建上下文不包含 `.env` 和 `reports/`。

### P1（下两周做）

6. **Web UI 降级为只读看板**：删除 `/api/run`、`/api/config` 写入及前端“运行全部/单用例”按钮；保留报告列表、详情、截图预览、删除。
   - DoD：Web UI 无任何接口可触发测试执行或修改 `config.json`。
7. **Flask debug 由环境变量直接控制**：去掉 `entrypoint.sh` 的 `sed` 源码改法；`app.run(debug=os.getenv("ATP_DEBUG") == "1", ...)`。
   - DoD：`ATP_DEBUG=0` 或未设时，无交互式调试器；`ATP_DEBUG=1` 才开启。
8. **长稳 Ping 语义**：默认 `ping_seconds` 从 3600/300 降为 30~60；README 明确“当前为按包数发送，非精确时长”。
   - DoD：`--stage 5 --ping-seconds 30` 在容器内可在 2 分钟内完成。
9. **加 `HEALTHCHECK`**：atp-web 增加健康检查（如 `python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:5000/', timeout=5)" || exit 1`）。
   - DoD：`docker compose ps` 中 atp-web 显示 healthy。
10. **提供 `docker-compose.bridge.yml` 示例**：给 macOS/Windows，README 补充 bridge 模式配置步骤。
    - DoD：README 中非 Linux 用户有可直接复制的 compose 片段。

### P2（后续，可选）

11. `reports/` 清理策略（宿主机 cron，保留最近 N 份）。
12. 把 `atp_engine.py` 重构为可导入库，方案 C 的前期准备。
13. 添加 CI（GitHub Actions）：构建镜像、跑 `--stage 1 --ping-seconds 10`；flake8/bandit 不再 `|| true`。

---

## 8. 成功状态（Golden Age）

工程师在任何 Linux 宿主机上执行 `cp .env.example .env && 填密码 && docker compose up -d --build atp-web && docker compose run --rm atp-engine --stage 1`，两分钟内获得宿主机 `reports/ATP_*/summary_report.html`，带截图的连通性测试报告；Web UI 只在内网通过只读看板查阅历史报告，不担心被局域网内他人远程重启路由器；不再为了跑一遍测试而熬夜排环境。
