# Known Issues & Planned Changes

本文档记录 `TPLINK-ATP-SCRIPT` 当前已知问题及建议修改，供后续迭代参考。

## 1. 安全类（高优先级）

| ID | 文件 | 问题 | 严重度 | 建议修复 |
|----|------|------|--------|----------|
| SEC-01 | `atp_engine.py:39-43` | 路由器管理员/超级管理员密码硬编码在 `CONFIG` 中，默认值 `admin1234` / `superadmin1234` | 高 | 移除硬编码默认值，仅从环境变量 `ATP_ADMIN_PASS` / `ATP_SUPERADMIN_PASS` 读取；仓库中提供 `.env.example` 模板 |
| SEC-02 | `atp_web.py:17-20` | Web UI `DEFAULT_CONFIG` 中同样硬编码明文密码 | 高 | 同上，改为从环境变量或 `config.json` 读取 |
| SEC-03 | `atp_web.py:675` | Flask 以 `debug=True` 启动，监听 `0.0.0.0`，会暴露交互式调试器并可能导致远程代码执行 | 高 | 生产环境改为 `debug=False`；建议使用 Gunicorn/uWSGI 部署，仅绑定 `127.0.0.1` 或受限接口 |

## 2. CI / 构建类（中优先级）

| ID | 文件 | 问题 | 严重度 | 建议修复 |
|----|------|------|--------|----------|
| CI-01 | `.github/workflows/ci.yml:32` | `flake8 ... || true` 会吞掉非零退出码，lint 失败不阻断 CI | 中 | 移除 `|| true`，让检查失败真正阻断构建 |
| CI-02 | `.github/workflows/ci.yml:36` | `bandit ... || true` 同上 | 中 | 移除 `|| true` |
| CI-03 | `.github/workflows/ci.yml` | 缺少 Playwright 浏览器安装步骤，CI 中跑脚本会因缺少浏览器而失败 | 中 | 增加 `playwright install` 步骤 |
| CI-04 | 仓库根目录 | 缺少 `requirements.txt`，依赖版本未锁定 | 中 | 增加 `requirements.txt` 固定 Python 依赖版本 |

## 3. 代码质量类（低优先级）

| ID | 文件 | 问题 | 严重度 | 建议修复 |
|----|------|------|--------|----------|
| CODE-01 | `atp_web.py:472` | `safe_cmd = out if False else cmd` 为死代码，`out` 分支不可达 | 低 | 删除无效分支 |
| CODE-02 | `atp_web.py:456-457` | `finally: pass` 为无意义空语句 | 低 | 删除或补充真实清理逻辑 |
| CODE-03 | `atp_engine.py:207-210`、`atp_web.py:90-95` | 使用 `shell=True` 执行命令，存在潜在命令注入面 | 低 | 尽量改用 `shell=False` 并传入列表参数 |
| CODE-04 | `atp_web.py` 各 case | 每个用例独立调用 `start_browser()` / `stop_browser()`，Chromium 启动开销大 | 低 | 复用单个浏览器实例和上下文 |
| CODE-05 | `atp_web.py:54` | `CASES` 用例列表硬编码在代码中，无法通过配置文件增减 | 低 | 支持从配置文件读取用例列表 |

## 4. 行为语义类（低优先级）

| ID | 文件 | 问题 | 严重度 | 建议修复 |
|----|------|------|--------|----------|
| BEHAV-01 | `atp_engine.py:544`、`atp_web.py:443` | 长稳 Ping 用例使用 `count=ping_seconds`，实际会发送 3600 个 ICMP 包（约需 1 小时+），与“运行 3600 秒”的语义不符 | 低 | 改为基于时间的循环 ping，或明确文档说明 `count` 即发包数 |

## 5. 文档类（低优先级）

| ID | 文件 | 问题 | 严重度 | 建议修复 |
|----|------|------|--------|----------|
| DOC-01 | 仓库根目录 | 缺少 `README.md`，无安装和使用说明 | 低 | 增加 `README.md` |
| DOC-02 | 仓库根目录 | 缺少 `.env.example`，用户无法得知所需环境变量 | 低 | 增加 `.env.example` 模板 |

---
*本文档由 QA Lead Tester 自动生成，基于对仓库的静态代码审查。*