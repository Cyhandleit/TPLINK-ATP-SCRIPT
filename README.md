# TP-Link ATP Automation Script

TP-Link 路由器 ATP（Auto Test Plan）自动化测试脚本，包含 CLI 测试执行引擎 (`atp_engine.py`) 和 Web UI 测试平台 (`atp_web.py`)，用于对 TP-Link 路由器固件进行自动化功能、连通性、吞吐量及远程管理测试。

## 目录结构

```
TPLINK-ATP-SCRIPT/
├── atp_engine.py          # CLI 自动化测试执行引擎（Playwright + Requests）
├── atp_web.py             # Flask Web UI 测试平台（配置、看板、逐用例运行）
├── ci.yml                 # GitHub Actions CI（lint + 安全扫描）
├── requirements.txt       # Python 依赖
├── known_issues.md        # 已知问题与计划修改
├── .gitignore
└── reports/               # 测试报告与截图输出目录（gitignored）
```

## 快速开始

### 1. 克隆仓库

```bash
git clone git@github.com:Cyhandleit/TPLINK-ATP-SCRIPT.git
cd TPLINK-ATP-SCRIPT
```

### 2. 安装依赖

```bash
pip install -r requirements.txt
playwright install chromium
```

### 3. 配置环境变量

所有敏感信息（路由器密码、ACS 账号等）均通过环境变量注入，不要直接写在代码中。可参考以下示例创建 `.env` 文件：

```bash
cp .env.example .env   # 如已提供 .env.example
# 然后编辑 .env 填入你的真实值
```

常用环境变量：

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `ATP_GATEWAY_SCHEME` | `http` | 网关访问协议 |
| `ATP_GATEWAY_IP` | `192.168.1.1` | 路由器网关 IP |
| `ATP_ADMIN_USER` | `admin` | 普通管理员账号 |
| `ATP_ADMIN_PASS` | 无默认值 | 普通管理员密码；建议留空，通过 Web UI 配置页填写（**请修改**） |
| `ATP_SUPERADMIN_USER` | `superadmin` | 超级管理员账号 |
| `ATP_SUPERADMIN_PASS` | 无默认值 | 超级管理员密码；建议留空，通过 Web UI 配置页填写（**请修改**） |
| `ATP_LAN_IFACE` | `Ethernet` | 有线网卡名称（Windows） |
| `ATP_WIFI_IFACE` | `Wi-Fi` | 无线网卡名称 |
| `ATP_EXT_NIC_IP` | `192.168.43.100` | 外网副网卡 IP |
| `ATP_DDNS_USER` | `your_noip_user` | No-IP 账号 |
| `ATP_DDNS_PASS` | `your_noip_key` | No-IP 密钥 |
| `ATP_TAUC_USER` | `tauc_tester@example.com` | TAUC 账号 |
| `ATP_TAUC_PASS` | 无默认值 | TAUC 密码；建议留空，通过 Web UI 配置页填写（**请修改**） |

### 4. 运行 CLI 测试

```bash
# 运行全部阶段
python atp_engine.py --stage all

# 仅运行 Stage 1（基础访问与连通性）
python atp_engine.py --stage 1

# 长稳 Ping 缩短为 10 秒（调试用）
python atp_engine.py --stage 5 --ping-seconds 10

# 执行破坏性用例（重启、固件升级）
python atp_engine.py --stage 5 --run-destructive

# 有头模式（查看浏览器界面，调试 DOM 时用）
python atp_engine.py --headed
```

测试完成后，报告将保存到 `ATP_Report_<时间戳>/` 目录，包含 `summary_report.html` 和所有自动截图。

### 5. 运行 Web UI

```bash
python atp_web.py
```

然后在浏览器打开 `http://<本机IP>:5000` 即可访问测试看板，支持保存配置、运行单个用例或整个阶段、查看历史截图。

> ⚠️ 注意：生产环境请勿直接使用 Flask 自带调试服务器，建议通过 Gunicorn/uWSGI 部署并关闭 `debug` 模式。

## Docker 部署

### Linux 宿主机（推荐）：network_mode: host

```bash
docker compose up --build -d
```

- `atp-web` Flask 监听 `0.0.0.0:5000`，`network_mode: host` 下宿主机直连 `http://localhost:5000`，无需端口映射。
- 测试报告与截图持久化到宿主机 `./reports`；可选 `./config.json` 以只读方式挂载，覆盖默认配置。
- `atp-web` 已配置 `HEALTHCHECK`（每 30 秒 `curl http://127.0.0.1:5000/`），可通过 `docker compose ps` 查看容器健康状态。

### macOS / Windows：bridge 模式

macOS / Windows 上 `network_mode: host` 不可用，请改用 bridge 网络：

```bash
docker compose -f docker-compose.yml -f docker-compose.bridge.yml up --build -d
```

- `docker-compose.bridge.yml` 将两服务切至 `network_mode: bridge`，通过 `ports: ["5000:5000"]` 暴露 Web UI，访问地址为 `http://localhost:5000`。
- `extra_hosts` 将 `host.docker.internal` 指向 `host-gateway`（宿主机网关），方便容器访问宿主机上的服务。
- 访问路由器（默认 `192.168.1.1`）依赖 Docker Desktop 的局域网路由，**请先确保宿主机能 `ping` 通路由器**。
- `ATP_LAN_IFACE` / `ATP_WIFI_IFACE` / `ATP_EXT_NIC_IP` 在 macOS / Windows 上通常不适用，可保留默认值；网关 IP 与登录凭证建议留空环境变量，通过 Web UI 配置并保存（见下文“配置凭证”）。

## 配置凭证（通过 Web UI 填写）

环境变量仅提供默认值，**敏感凭证建议不要写在 `.env` 或 docker-compose 中**。推荐做法：

1. `ATP_ADMIN_PASS` / `ATP_SUPERADMIN_PASS` 等敏感项留空（或不在 `.env` 中定义）。
2. 启动容器后，在浏览器打开 `http://localhost:5000`，进入配置页填写路由器网关 IP、协议、管理员/超级管理员登录凭证。
3. 保存后凭证写入 `./config.json`（容器内 `/app/config.json`），环境变量仅作为默认值，Web UI 配置优先级更高。

> ⚠️ 注意：`docker-compose.yml` 中 `./config.json:/app/config.json:ro` 为**只读**挂载，Web UI 保存配置会失败。如需通过 Web UI 持久化配置，请去掉 `:ro`，改为可读写挂载，或确保宿主机上的 `config.json` 可写。

## CI

推送代码到 `main` 分支或提交 PR 会自动触发 GitHub Actions，运行：
- Python 语法检查 (`py_compile`)
- 代码风格检查 (`flake8`)
- 安全漏洞扫描 (`bandit`)

## 已知问题

详见 [`known_issues.md`](known_issues.md)。

## P1 部署进度

| 项目 | 内容 | 状态 |
|------|------|------|
| HEALTHCHECK | `atp-web` 每 30s `curl http://127.0.0.1:5000/`，`docker compose ps` 可见健康状态 | ✅ 已完成 |
| Dockerfile | 加入 `curl`（`--no-install-recommends`，保持轻量），供 HEALTHCHECK 与排障使用 | ✅ 已完成 |
| docker-compose.bridge.yml | macOS / Windows bridge 网络 + `host.docker.internal:host-gateway`，端口映射 5000 | ✅ 已完成 |
| README.md | 补充 Docker 部署、bridge 模式步骤、P1 进度、Web UI 凭证配置说明 | ✅ 已完成 |

后续 P2 预计：CI 构建镜像、多架构支持、`atp-engine` 定时调度。

## 贡献

发现问题或有改进建议，欢迎提交 Issue 或 Pull Request。