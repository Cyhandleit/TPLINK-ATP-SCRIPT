# Known Issues & Planned Changes

This document records current known issues of `TPLINK-ATP-SCRIPT` and suggested changes, for subsequent iteration resolution.

`TPLINK-ATP-SCRIPT`

## 1. Security (High Priority)

| ID | File | Issue | Severity | Status | Suggested Fix |
|----|------|-------|----------|--------|---------------|
| SEC-01 | `atp_engine.py:57-63` | Router administrator / super administrator password hardcoded in `CONFIG` | High | **Resolved** | Passwords now read from `ATP_ADMIN_PASS` / `ATP_SUPERADMIN_PASS` env vars with empty defaults; no hardcoded `admin1234` / `superadmin1234` remain |
| SEC-02 | `atp_web.py:20` | Web UI `CONFIG` reads from `load_config()` / `config.json` instead of hardcoded `DEFAULT_CONFIG` | High | **Resolved** | Configuration sourced from env vars and `config.json`; no plaintext passwords in code |
| SEC-03 | `atp_web.py:985` | Flask `debug=True` exposing interactive debugger on `0.0.0.0` | High | **Resolved** | `debug=os.environ.get("ATP_DEBUG", "0") == "1"` — defaults to `False`; Dockerfile forces `debug=False` |

## 2. CI / Build (Medium Priority)

| ID | File | Issue | Severity | Status | Suggested Fix |
|----|------|-------|----------|--------|---------------|
| CI-01 | `.github/workflows/ci.yml:33` | `flake8` failure does not block CI | Medium | **Resolved** | Removed `|| true` / `|| echo` swallowers; lint failures now block build |
| CI-02 | `.github/workflows/ci.yml:37` | `bandit` failure does not block CI | Medium | **Resolved** | Removed `|| true`; security scan failures now block build |
| CI-03 | `.github/workflows/ci.yml:26-29` | Missing Playwright browser installation step | Medium | **Resolved** | Added `playwright install chromium` + `playwright install-deps chromium` |
| CI-04 | Repository root | Missing `requirements.txt` | Medium | **Resolved** | `requirements.txt` exists; CI installs from it |

## 3. Code Quality (Low Priority)

| ID | File | Issue | Severity | Status | Suggested Fix |
|----|------|-------|----------|--------|---------------|
| CODE-01 | `atp_web.py` | `safe_cmd = out if False else cmd` dead code | Low | **Resolved** | Removed invalid branch |
| CODE-02 | `atp_web.py` | Empty `finally: pass` blocks | Low | **Resolved** | Removed meaningless empty statements |
| CODE-03 | `atp_web.py:91`, `atp_engine.py` | `shell=True` command injection surface | Low | **Resolved** | `run_cmd` defaults to `shell=False`; pass list arguments |
| CODE-04 | `atp_web.py` | Each case calls `start_browser()` / `stop_browser()` independently | Low | **Resolved** | Browser started once per case run, stopped in `finally` block — no more browser churn between cases |
| CODE-05 | `atp_web.py:23` | `CASES` list hardcoded in code | Low | **Resolved** | Configurable via `ATP_CASES` env var or `cases` key in `config.json` (JSON list of `[id, title, stage]` tuples) |

## 4. Behavior Semantics (Low Priority)

| ID | File | Issue | Severity | Status | Suggested Fix |
|----|------|-------|----------|--------|---------------|
| BEHAV-01 | `atp_engine.py`, `atp_web.py` | Ping case uses `count=ping_seconds`, sending N packets instead of running N seconds | Low | **Resolved** | `atp_web.py:run_ping_stats` now accepts `duration_seconds` param with time-based ping (`ping -t` on Windows, plain `ping` elsewhere, terminate → fallback kill). Call site at `atp_web.py:685` passes `duration_seconds=secs`. No more `TypeError`. |

## 5. Documentation (Low Priority)

| ID | File | Issue | Severity | Status | Suggested Fix |
|----|------|-------|----------|--------|---------------|
| DOC-01 | Repository root | Missing `README.md` | Low | **Resolved** | `README.md` added with quick start and Docker deployment |
| DOC-02 | Repository root | Missing `.env.example` | Low | **Resolved** | `.env.example` template lists all required environment variables |

## 6. Newly Identified Bugs — QA Lead Bugcheck (2026-11-20)

| ID | File | Issue | Severity | Status | Fix |
|----|------|-------|----------|--------|-----|
| BUG-01 | `atp_engine.py:84` | Hardcoded plaintext default password `TaucPass123!` for `tauc_pass` in CLI engine `CONFIG` | High | **Resolved** | Default changed to `""`, matching `atp_config.py:59` (`_env("ATP_TAUC_PASS", "")`); single source of truth via `ATP_TAUC_PASS` env var (also resolves BUG-06) |
| BUG-02 | `atp_web.py:987-993` | `/screenshot/<path:fpath>` joins user-supplied path with no containment check and no auth; `..` traversal enables arbitrary file read | High | **Resolved** | `os.path.realpath` of joined path must be inside `REPORT_ROOT`; escapes return 403, missing files return 404 |
| BUG-03 | `atp_web.py:911-927` | `POST /api/config` rejects any change unless `admin_pass`/`superadmin_pass` are non-empty; masked `***` placeholders are stripped first, so a `gateway_ip`-only change returns 400 `admin_pass required` | High | **Resolved** | Existing passwords retained for fields not supplied (`data.setdefault`); validation runs on the candidate with retained secrets; only supplied fields are persisted to `CONFIG`/`config.json` |
| BUG-04 | `atp_web.py:446, 460` | `speedtest-cli --simple` passed as a string to `run_cmd` with `shell=False` | Medium | **Resolved** | `shlex.split("speedtest-cli --simple")` passed as explicit list args; `shell` left at its `False` default |
| BUG-06 | `atp_engine.py:84` / `atp_config.py:59` | CLI and Web UI config defaults diverge: `tauc_pass` default differs between files | Medium | **Resolved** | `atp_engine.py` default aligned to `""`, identical to `atp_config.py`; single source of truth via `ATP_TAUC_PASS` env var (fixed with BUG-01) |
| BUG-08 | `Dockerfile:24`, `entrypoint.sh:7-9` | No-op `sed` debug toggles target literals (`debug=True` / `debug=False`) that do not exist in `atp_web.py` | Medium | **Resolved** | Removed dead `sed` lines from `Dockerfile` and `entrypoint.sh`; debug controlled solely by `ATP_DEBUG` env var |

---

## Final Verification (2026-11-20)

- **Verifier**: QA Lead Tester (bugcheck fixes)
- **HEAD Commit**: `3cb413e` (Merge PR #1 from EggY0lk/main) + QA Lead bugcheck fixes (BUG-01, BUG-02, BUG-03, BUG-04, BUG-06, BUG-08), committed and pushed to origin/main
- **Verification Methods**:
  - Static code review of `atp_engine.py`, `atp_web.py`, `atp_config.py`, `.github/workflows/ci.yml`, `Dockerfile`, `entrypoint.sh`, `known_issues.md`
  - Python syntax check (`python3 -m py_compile`) — **PASS**
  - `flake8` style check (max-line-length=120, ignore E203,W503) — **PASS** (clean)
  - `bandit` security scan — **PASS** (0 issues)
  - GitHub Actions CI status — rerun on push to origin/main
  - GitHub open issues count — **0** after closure
- **Conclusion**: BUG-01, BUG-02, BUG-03 (High) and BUG-04, BUG-06, BUG-08 (Medium) from the QA lead bugcheck are confirmed **Resolved**. All known issues resolved; no open issues remain.

---

*This document is automatically generated by QA Lead Tester, based on static code review of the repository.*