# TP-Link ATP — Product and Architecture Design (CEO Product Thinker Review)

> Session Role: CEO Product Thinker (`/office-hours`). This file is an architecture, network, security, and usability review of `/root/Repos/github.com/Cyhandleit/atp-project`, with actionable follow-up tasks.

---

## 1. Problem Statement (Reframed)

The team has a TP-Link router firmware automation test script based on TPLINK-ATP-SCRIPT, initially Dockerized as two Compose services (Flask Web UI + CLI engine), startable on Linux host via `docker compose`. But it is currently at the "can run a flow" stage, still some distance from "stable, reusable, secure, maintainable":

- **Hardcoded passwords and weak defaults still in code**: `atp_engine.py` / `atp_web.py` have `default=` fallbacks for `ATP_ADMIN_PASS`, `ATP_SUPERADMIN_PASS`, etc.; `.env.example` even writes `admin1234` / `superadmin1234` / `TaucPass123!` in plaintext into the repo. User does `cp .env.example .env` without changes, tests log into router with weak default passwords (SEC-01/02 unfixed).
- **Web UI has no authentication, no TLS, listens on `0.0.0.0:5000`**: Any device on LAN can remotely trigger router restart, firmware upgrade; directly exposed to public internet / remote office environment is disaster (SEC-03 surface-fixed, but access control missing).
- **Long-stable Ping semantic error**: "Run 300 seconds" implemented as "send 300 ICMP packets", actual duration far exceeds expectation; UI click hangs for minutes with no progress hint (BEHAV-01).
- **Stage 2 inevitably fails**: `speedtest-cli` used for throughput testing but not in `requirements.txt`, container command missing, related cases all error out.
- **Report path inconsistency**: CLI engine writes `ATP_Report_*` inside container (outside volume, lost after container restart), Web UI writes `reports/` (inside volume); two directory systems, no cleanup policy, disk grows infinitely.
- **`network_mode: host` locks to Linux**: macOS / Windows cannot directly use, cross-platform claim unfulfilled; README only mentions problem, no bridge version compose reference provided.

**The core problem is not "missing features", but trying to build a full test platform at once, making core link (connectivity test → report output) unstable, security baseline unmet, maintenance cost too high.**

---

## 2. Target Users and "Hair on Fire" Problems

- **Users**: Test engineers responsible for TP-Link firmware quality, working on Linux host / intranet environment, need reproducible, containerizable automated testing, output deliverable HTML report with screenshots.
- **Hair on fire problem**: "I need one command, without modifying host environment, to run router connectivity / basic function tests end-to-end, and get an HTML report with screenshots."

---

## 3. Current Status Review (Architecture / Network / Security / Usability)

### Architecture

| Item | Status | Problem | Severity |
|------|--------|---------|----------|
| Service split | atp-web + atp-engine share same Dockerfile, distinguished via `command` | Reasonable, but atp-engine placeholder command `--help` has no actual value | Medium |
| Configuration loading | Environment variables + `config.json`; two services inconsistent order (engine only reads env vars, web prioritizes `config.json`) | `config.json` modified by Web UI invisible to engine; configuration inconsistent | Medium |
| Report path | engine → container internal `ATP_Report_*`; web → `reports/` volume | engine report lost after restart; two directory systems | High |
| Dependencies | `speedtest-cli` used for Stage 2 but not listed in `requirements.txt` | Stage 2 entirely fails due to missing command | High |
| Image size | bandit / flake8 etc. dev tools installed into production image | Size bloated, meaningless | Low |
| Entrance script | `entrypoint.sh` uses `sed` to modify `atp_web.py` in place to switch debug | Fragile; `__main__` source still keeps `debug=True`, non-standard entrance can revive debug | Medium |

### Network

| Item | Status | Problem | Severity |
|------|--------|---------|----------|
| Container network | `network_mode: host` | Only Linux available; macOS / Windows cannot directly reach LAN router, README explains but no bridge compose version provided | High (usability) |
| Port exposure | Flask binds `0.0.0.0:5000`, no `ports` mapping (cannot coexist in host mode) | Port not adjustable; host port 5000 occupied causes startup failure; directly exposed on all host NICs | Medium |
| LAN router access | Depends on host mode direct connect 192.168.1.1 | Reasonable on Linux; bridge mode needs extra routing config, documentation missing | Medium |
| WiFi cases | Container calls nmcli / netsh to switch WiFi | Container usually has no NetworkManager / dbus, unreliable; should be treated as host-side capability, not relied on inside container | High |

### Security

| Item | Status | Problem | Severity |
|------|--------|---------|----------|
| Credentials | `default="admin1234"` etc. in code; `.env.example` plaintext example | Weak default passwords silently used when `.env` not set; SEC-01/02 unfixed | High |
| Web UI access control | No auth, no TLS, listening on 0.0.0.0 | Any device on LAN can trigger restart / upgrade; must not be directly exposed to public internet | Severe |
| Flask debug | build time sed changes to False, entrypoint switches via `ATP_DEBUG` | `__main__` source still keeps `debug=True` | Medium |
| Sensitive logs / screenshots | `sensitive_regions` default `{}`, no redaction | Screenshots may leak password / SSID; report directory permission uncontrolled | Medium |
| Interface | `/api/config` returns all config plaintext (including passwords) | Frontend renders plaintext, leakage risk | Medium |

### Usability

| Item | Status | Problem | Severity |
|------|--------|---------|----------|
| Long-stable Ping | `count=ping_seconds` (default 3600 / 300) | Actually sends 300–3600 packets, duration far exceeds "second" semantics; UI click hangs for minutes without progress | High |
| Health check | No `HEALTHCHECK` | `docker compose up -d` cannot know if Web UI is ready | Medium |
| State persistence | Web UI state kept in process memory | Dashboard state cleared after container restart | Medium |
| Disk cleanup | `reports/` no cleanup policy | Long-term operation disk filled by reports and screenshots | Medium |
| Cross-platform | Locked to `network_mode: host` | Non-Linux hosts cannot directly use | High |

> Supplement: CI-01~CI-04 in `known_issues.md` reference `.github/workflows/ci.yml`, but no CI artifact exists in current repo root; these entries do not apply to current version, can archive or delete, do not treat as must-fix items.

---

## 4. Three Improvement Alternatives

### Alternative A: In-place Refinement

Retain two services + `network_mode: host` overall architecture, make necessary security and usability fixes on existing code: remove all password default values (missing → error), unify report writing to `reports/` volume, add `HEALTHCHECK`, add `speedtest-cli` to dependencies or remove Stage 2, remove dev tools from image, control Flask debug directly via environment variable (no longer `sed` source), add `.dockerignore`.

- Pros: Smallest changes, leverage existing investment, low user migration cost.
- Cons: Web UI still no auth / TLS, attack surface not reduced; `shell=True`, dead code, independent browser start per case etc. code quality issues remain; long-stable Ping semantics optionally fixed.
- Suitable for: teams wanting to quickly get existing version "running and not causing security accidents".

### Alternative B: CLI-first, Web UI Downgraded to Read-only Report Dashboard (Narrowest wedge, recommended)

Fully move test execution into `atp-engine` (CLI), Web UI only responsible for: reading HTML reports from host `reports/`, list display, deleting old reports, viewing screenshots. **Remove `/api/run`, `/api/config` write and remote-trigger destructive operation capabilities.** Engine reports uniformly write to `reports/ATP_<timestamp>/`. CLI supports `--stage 1\|2\|...\|all`, `--ping-seconds`, `--run-destructive`.

- Pros: Smallest attack surface (no remote code execution entry, no password returned plaintext over network); easiest to achieve "stable, repeatable"; best matches "free, self-hosted, no overtime" preference—run CLI and get report, Web only for post-hoc viewing.
- Cons: Lose "click UI to run single case" immediate convenience; case orchestration still in Python code rather than configurable.
- Suitable for: preferred MVP to make core link (connectivity → report) stable and secure.

### Alternative C: Library + Independent Runner + Optional Auth Sidecar

Refactor `atp_engine.py` into importable Python library, remove global side effects; Runner triggered via environment variables or JSON queue; Web UI optional, based on Flask / FastAPI, read reports only, add simple token / basic-auth auth, bind `127.0.0.1` or via reverse proxy (Tailscale / Headscale) access.

- Pros: Easiest to write unit tests, easiest to integrate into CI, easiest for future multi-tenant / cloud-native expansion.
- Cons: Large refactor effort, conflicts with "low pressure output, fast MVP" goal, can be evolution path after Alternative B stabilizes.
- Suitable for: teams planning to integrate ATP into CI/CD or SaaS later.

**Recommendation: Implement Alternative B as MVP first, simultaneously do Alternative B security mandatory items; Alternative C as subsequent evolution path.**

---

## 5. MVP Scope (Alternative B)

### In scope (P0, must do)

- CLI engine `docker compose run --rm atp-engine --stage 1`: basic connectivity (login, WAN status, Ping gateway / 8.8.8.8 / DNS) and output HTML report + screenshots to `reports/`.
- All sensitive credentials read only from environment variables; missing required items (`ATP_ADMIN_PASS`, `ATP_SUPERADMIN_PASS`) causes container run error exit, **no hardcoded default values**.
- Flask debug production default False, controlled via environment variable, no longer `sed` source code.
- Web UI: read-only report dashboard (list / details / screenshot preview / delete), **no test triggering and configuration write API**.
- `network_mode: host` retained as Linux default; provide `docker-compose.bridge.yml` for macOS / Windows reference.
- `HEALTHCHECK` for atp-web; `.dockerignore` excludes `.env`, `reports/`, `__pycache__`, `.git/`.
- Image removes bandit / flake8 (moved to dev docs, not installed into production image).

### Out of scope (MVP not doing, subsequent iteration)

- Web UI remote trigger single case / stage execution.
- WiFi switching, throughput / speed test (depends on host capability, unreliable inside container, first remove or mark experimental).
- Long-stable Ping precise "second" control (first retain count semantics, but document clearly and default to 30~60 seconds to avoid users waiting an hour).
- ACS / TR-069, firmware upgrade, DDNS etc. remote management cases (require external GenieACS and firmware files, not entering MVP first).
- Multi-user auth, RBAC, TLS termination (recommend access via Tailscale / Headscale networking, not implemented inside container).
- macOS / Windows native support bridge and auto routing (provide reference file, not automated).

---

## 6. Target Architecture Points (Simplified)

- **Configuration loading priority**: Environment variables > `config.json` (ro mount, optional) > no default passwords (missing required items → error).
- **Report unification**: engine and web both write `reports/ATP_<YYYYMMDD_HHMMSS>/`, volume mounted to host; cleanup policy executed by host cron (not implemented inside container).
- **Network**: Linux default host; non-Linux use bridge + `extra_hosts` / `host.docker.internal`, user adjusts by host network segment.
- **Security**: Web UI not directly exposed to public internet; remote office access via Tailscale / Headscale networking; host firewall only opens trusted network segments.

---

## 7. Follow-up Tasks (Actionable, with Acceptance Criteria)

### P0 (Must do this week, otherwise cannot call it MVP)

1. **Remove all password default values**: In `atp_engine.py` / `atp_web.py`, replace `default=` for `ATP_ADMIN_PASS`, `ATP_SUPERADMIN_PASS`, `TAUC_PASS`, WiFi password etc. with `required=True`, missing causes `RuntimeError` exit.
   - DoD: When `.env` password not set, `docker compose run --rm atp-engine --help` still runs; running any stage missing password errors and exits non-zero.
2. **`.env.example` desensitization**: Delete plaintext password examples, keep only variable names and placeholders (e.g. `ATP_ADMIN_PASS=***`), and prompt "do not commit real `.env`".
   - DoD: `git diff .env.example` no longer contains `admin1234` / `superadmin1234` / `TaucPass123!`.
3. **Unify report path**: Engine report changed to write `reports/ATP_<timestamp>/` (same as web); engine service also mounts `./reports:/app/reports`.
   - DoD: After `docker compose run --rm atp-engine --stage 1`, host `reports/` shows `ATP_*/summary_report.html`.
4. **Fix Stage 2 dependency**: Either add `speedtest-cli` to `requirements.txt`, or remove speed test cases from MVP (recommended remove first, mark experimental).
   - DoD: `--stage 2` no longer fails due to `command not found`.
5. **Image slimming and `.dockerignore`**: Remove bandit / flake8; add `.dockerignore` excluding `.env`, `reports/`, `__pycache__/`, `.git/`.
   - DoD: `docker compose build` image size reduced; build context does not include `.env` and `reports/`.

### P1 (Do in next two weeks)

6. **Web UI downgraded to read-only dashboard**: Delete `/api/run`, `/api/config` write and frontend "Run All / Single Case" buttons; retain report list, details, screenshot preview, delete.
   - DoD: Web UI has no interface capable of triggering test execution or modifying `config.json`.
7. **Flask debug directly controlled by environment variable**: Remove `entrypoint.sh` `sed` source modification approach; `app.run(debug=os.getenv("ATP_DEBUG") == "1", ...)`.
   - DoD: `ATP_DEBUG=0` or unset → no interactive debugger; `ATP_DEBUG=1` only enables it.
8. **Long-stable Ping semantics**: Default `ping_seconds` from 3600 / 300 lowered to 30~60; README clearly states "currently packet-count based, not precise duration".
   - DoD: `--stage 5 --ping-seconds 30` completes within 2 minutes inside container.
9. **Add `HEALTHCHECK`**: atp-web adds health check (e.g. `python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:5000/', timeout=5)" || exit 1`).
   - DoD: `docker compose ps` shows atp-web healthy.
10. **Provide `docker-compose.bridge.yml` example**: For macOS / Windows, README adds bridge mode configuration steps.
    - DoD: README has directly copyable compose snippet for non-Linux users.

### P2 (Later, optional)

11. `reports/` cleanup policy (host cron, retain recent N copies).
12. Refactor `atp_engine.py` into importable library, preparation for Alternative C.
13. Add CI (GitHub Actions): build image, run `--stage 1 --ping-seconds 10`; flake8 / bandit no longer `|| true`.

---

## 8. Success State (Golden Age)

Engineer on any Linux host executes `cp .env.example .env && fill password && docker compose up -d --build atp-web && docker compose run --rm atp-engine --stage 1`, gets host `reports/ATP_*/summary_report.html` with screenshots connectivity test report within two minutes; Web UI only viewable on intranet via read-only dashboard to browse historical reports, no worry about being remotely rebooted by others on LAN; no more staying up late sorting environments just to run one test.
