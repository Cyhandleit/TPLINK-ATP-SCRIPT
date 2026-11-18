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
| `ATP_ADMIN_PASS` | `admin1234` | 普通管理员密码（**请修改**） |
| `ATP_SUPERADMIN_USER` | `superadmin` | 超级管理员账号 |
| `ATP_SUPERADMIN_PASS` | `superadmin1234` | 超级管理员密码（**请修改**） |
| `ATP_LAN_IFACE` | `Ethernet` | 有线网卡名称（Windows） |
| `ATP_WIFI_IFACE` | `Wi-Fi` | 无线网卡名称 |
| `ATP_EXT_NIC_IP` | `192.168.43.100` | 外网副网卡 IP |
| `ATP_DDNS_USER` | `your_noip_user` | No-IP 账号 |
| `ATP_DDNS_PASS` | `your_noip_key` | No-IP 密钥 |
| `ATP_TAUC_USER` | `tauc_tester@example.com` | TAUC 账号 |
| `ATP_TAUC_PASS` | `TaucPass123!` | TAUC 密码（**请修改**） |

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

## CI

推送代码到 `main` 分支或提交 PR 会自动触发 GitHub Actions，运行：
- Python 语法检查 (`py_compile`)
- 代码风格检查 (`flake8`)
- 安全漏洞扫描 (`bandit`)

## 已知问题

详见 [`known_issues.md`](known_issues.md)。

## 贡献

发现问题或有改进建议，欢迎提交 Issue 或 Pull Request。