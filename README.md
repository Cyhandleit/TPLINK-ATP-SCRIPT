# TP-Link ATP Automation Script

TP-Link router ATP (Auto Test Plan) automation test script, core is Web UI test platform (`atp_web.py`), used for automated functional, connectivity, throughput, and remote management testing of TP-Link router firmware. `atp_engine.py` is kept as CLI engine for local development debugging; Docker deployment delivers only the `atp-web` single service, all test stages are triggered via Web UI, no separate `atp-engine` container needed.

## Directory Structure

```
TPLINK-ATP-SCRIPT/
├── atp_engine.py          # CLI automation test execution engine (Playwright + Requests), for local development debugging
├── atp_web.py             # Flask Web UI test platform (configuration, dashboard, per-case execution), Docker single service entry
├── ci.yml                 # GitHub Actions CI (lint + security scan + Web API smoke test)
├── requirements.txt       # Python dependencies
├── known_issues.md        # Known issues and planned changes
├── .gitignore
└── reports/               # Test report and screenshot output directory (gitignored)
```

## Quick Start

### 1. Clone Repository

```bash
git clone git@github.com:Cyhandleit/TPLINK-ATP-SCRIPT.git
cd TPLINK-ATP-SCRIPT
```

### 2. Install Dependencies

```bash
pip install -r requirements.txt
playwright install chromium
```

### 3. Configure Environment Variables

All sensitive information (router password, ACS account, etc.) is injected via environment variables, do not write directly into code. You can refer to the following example to create `.env` file:

```bash
cp .env.example .env   # if .env.example is provided
# then edit .env to fill in your real values
```

Common environment variables:

| Variable | Default Value | Description |
|----------|--------------|-------------|
| `ATP_GATEWAY_SCHEME` | `http` | Gateway access protocol |
| `ATP_GATEWAY_IP` | `192.168.1.1` | Router gateway IP |
| `ATP_ADMIN_USER` | `admin` | Regular administrator account |
| `ATP_ADMIN_PASS` | none | Regular administrator password; recommended to leave blank, fill via Web UI configuration page (**please change**) |
| `ATP_SUPERADMIN_USER` | `superadmin` | Super administrator account |
| `ATP_SUPERADMIN_PASS` | none | Super administrator password; recommended to leave blank, fill via Web UI configuration page (**please change**) |
| `ATP_LAN_IFACE` | `Ethernet` | Wired network card name (Windows) |
| `ATP_WIFI_IFACE` | `Wi-Fi` | Wireless network card name |
| `ATP_EXT_NIC_IP` | `192.168.43.100` | External secondary NIC IP |
| `ATP_DDNS_USER` | `your_noip_user` | No-IP account |
| `ATP_DDNS_PASS` | `your_noip_key` | No-IP key |
| `ATP_TAUC_USER` | `tauc_tester@example.com` | TAUC account |
| `ATP_TAUC_PASS` | none | TAUC password; recommended to leave blank, fill via Web UI configuration page (**please change**) |

### 4. Run Web UI

Docker deployment delivers only `atp-web` single service, all tests (stage 1~5 and all) are triggered via Web UI:

```bash
# Run in foreground (local development)
python atp_web.py
```

Then open `http://<local IP>:5000` in browser to access the test dashboard, supports saving configuration, running single case or entire stage, viewing historical screenshots.

> `atp_engine.py` can still be run locally directly for debugging (e.g. `python atp_engine.py --stage 1`), but it is no longer delivered as standalone container; in Docker please unify test execution through `atp-web` Web API `/api/run`.

> ⚠️ Note: In production environment, do not use Flask built-in debug server directly, recommend deploying via Gunicorn/uWSGI and closing `debug` mode.

## Docker Deployment

### Linux Host (Recommended): network_mode: host

```bash
docker compose up -d --build atp-web
```

- `atp-web` Flask listens on `0.0.0.0:5000`, under `network_mode: host` host can directly connect `http://localhost:5000`, no port mapping needed.
- Test reports and screenshots are persisted to host `./reports`; optional `./config.json` can be mounted read-only to override default configuration.
- `atp-web` has configured `HEALTHCHECK` (`curl http://127.0.0.1:5000/` every 30 seconds), container health status can be viewed via `docker compose ps`.
- Open `http://localhost:5000` in browser, enter configuration page to fill in credentials, then you can run any stage (stage 1~5) or `all` on the dashboard, no extra container needed.

### macOS / Windows: bridge mode

`network_mode: host` is unavailable on macOS / Windows, please use bridge network instead:

```bash
docker compose -f docker-compose.yml -f docker-compose.bridge.yml up -d --build atp-web
```

- `docker-compose.bridge.yml` switches `atp-web` to `network_mode: bridge`, exposes Web UI via `ports: ["5000:5000"]`, access address is `http://localhost:5000`.
- `extra_hosts` points `host.docker.internal` to `host-gateway` (host gateway), making it easy for container to access services on host.
- Accessing router (default `192.168.1.1`) depends on Docker Desktop's LAN routing, **please ensure host can `ping` router first**.
- `ATP_LAN_IFACE` / `ATP_WIFI_IFACE` / `ATP_EXT_NIC_IP` usually do not apply on macOS / Windows, can keep default values; gateway IP and login credentials are recommended to be left as empty environment variables, configured and saved via Web UI (see "Configure Credentials" below).

## Configure Credentials (Fill via Web UI)

Environment variables only provide default values, **sensitive credentials are recommended not to be written in `.env` or docker-compose**. Recommended practice:

1. Leave sensitive items such as `ATP_ADMIN_PASS` / `ATP_SUPERADMIN_PASS` blank (or not defined in `.env`).
2. After starting container, open `http://localhost:5000` in browser, enter configuration page to fill in router gateway IP, protocol, administrator / super administrator login credentials.
3. After saving, credentials are written to `./config.json` (`/app/config.json` inside container), environment variables only serve as default values, Web UI configuration has higher priority.

> ⚠️ Note: In `docker-compose.yml`, `./config.json:/app/config.json:ro` is **read-only** mount, Web UI saving configuration will fail. If you need to persist configuration via Web UI, please remove `:ro` and change to read-write mount, or ensure `config.json` on host is writable.

## CI

Pushing code to `main` branch or submitting PR will automatically trigger GitHub Actions, running:
- Python syntax check (`py_compile`)
- Code style check (`flake8`)
- Security vulnerability scan (`bandit`)

## Known Issues

See [`known_issues.md`](known_issues.md).

## P1 Deployment Progress

| Project | Content | Status |
|---------|---------|--------|
| HEALTHCHECK | `atp-web` `curl http://127.0.0.1:5000/` every 30s, health status visible via `docker compose ps` | ✅ Completed |
| Dockerfile | Added `curl` (`--no-install-recommends`, keep lightweight), for HEALTHCHECK and troubleshooting | ✅ Completed |
| docker-compose.bridge.yml | macOS / Windows bridge network + `host.docker.internal:host-gateway`, port mapping 5000 | ✅ Completed |
| README.md | Added Docker deployment, bridge mode steps, P1 progress, Web UI credential configuration instructions | ✅ Completed |

Subsequent P2 expected: CI image building, multi-architecture support.

## Contributing

If you find problems or have improvement suggestions, welcome to submit Issue or Pull Request.
